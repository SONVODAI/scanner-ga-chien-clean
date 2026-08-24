"""
P0 foreign-flow production VPS verification helpers.

Run on the real production host (/opt/mrbot-camera). Cloud Agent / Cursor
hosts must not be treated as production evidence.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

# Canonical production paths documented in deploy docs.
PROD_REPO = Path("/opt/mrbot-camera")
PROD_VENV_APP_CANDIDATES = (
    Path("/opt/mrbot-camera-venv"),  # collector docs; may be vnstock 4.x
    Path("/opt/mrbot/venv"),
    Path("/opt/mrbot-camera/.venv"),
)
SSI_HOSE_URL = "https://iboard-query.ssi.com.vn/stock/exchange/HOSE"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_production_vps_host() -> bool:
    """True only when this process is running on the documented production tree."""
    return PROD_REPO.is_dir() and (PROD_REPO / "modules").is_dir()


def detect_runtime() -> Dict[str, Any]:
    vnstock_version = None
    vnstock_file = None
    has_fr_trade_heatmap = False
    try:
        import vnstock  # type: ignore

        vnstock_version = getattr(vnstock, "__version__", None) or "unknown"
        vnstock_file = getattr(vnstock, "__file__", None)
        has_fr_trade_heatmap = hasattr(vnstock, "fr_trade_heatmap")
        if vnstock_version == "unknown":
            try:
                from importlib.metadata import version

                vnstock_version = version("vnstock")
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        vnstock_version = f"import_error:{exc}"

    return {
        "is_production_vps": is_production_vps_host(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "cwd": os.getcwd(),
        "repo_root_guess": str(REPO_ROOT),
        "prod_repo_exists": PROD_REPO.is_dir(),
        "vnstock_version": vnstock_version,
        "vnstock_file": vnstock_file,
        "has_fr_trade_heatmap": has_fr_trade_heatmap,
        "observed_at": _utc_now_iso(),
    }


def probe_ssi_hose_http(*, timeout_s: float = 15.0) -> Dict[str, Any]:
    """
    Single GET to SSI iBoard HOSE exchange endpoint.
    Does not bypass Cloudflare / CAPTCHA / access controls.
    """
    out: Dict[str, Any] = {
        "url": SSI_HOSE_URL,
        "provider_call": "GET iboard-query.ssi.com.vn/stock/exchange/HOSE",
        "observed_at": _utc_now_iso(),
    }
    try:
        import requests

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://iboard.ssi.com.vn/",
            "Origin": "https://iboard.ssi.com.vn",
        }
        try:
            from vnstock.config import ssi_headers  # type: ignore

            headers = dict(ssi_headers)
        except Exception:  # noqa: BLE001
            pass
        resp = requests.get(SSI_HOSE_URL, headers=headers, timeout=timeout_s)
        body = (resp.text or "")[:400]
        out.update(
            {
                "reachable": resp.status_code == 200,
                "http_status": resp.status_code,
                "server": resp.headers.get("server"),
                "cf_ray": resp.headers.get("cf-ray"),
                "content_type": resp.headers.get("content-type"),
                "body_prefix": body.replace("\n", " "),
            }
        )
        if resp.status_code == 200:
            try:
                payload = resp.json()
                data = payload.get("data") if isinstance(payload, dict) else None
                out["n_rows"] = len(data) if isinstance(data, list) else None
                if isinstance(data, list) and data:
                    sample_keys = sorted({k for row in data[:5] if isinstance(row, dict) for k in row.keys()})
                    out["sample_keys"] = sample_keys[:80]
            except Exception as exc:  # noqa: BLE001
                out["json_error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        out.update(
            {
                "reachable": False,
                "http_status": None,
                "error": f"{type(exc).__name__}:{exc}",
            }
        )
    return out


def _sum_numeric(df: Any, col: Optional[str]) -> Optional[float]:
    if col is None:
        return None
    import pandas as pd

    s = pd.to_numeric(df[col], errors="coerce")
    if s.notna().sum() == 0:
        return None
    return float(s.sum(min_count=1))


def _pick_col(cols: Dict[str, Any], names: tuple) -> Optional[Any]:
    for n in names:
        if n in cols:
            return cols[n]
    for key, orig in cols.items():
        compact = key.replace("_", "")
        for n in names:
            if n.replace("_", "") in compact:
                return orig
    return None


def analyze_ssi_heatmap_dataframe(df: Any, *, trade_date: str) -> Dict[str, Any]:
    """
    Derive foreign buy/sell/net from an SSI exchange heatmap frame.
    Units are reported as provider-native (unproven) until independently verified.
    """
    import pandas as pd

    if df is None or getattr(df, "empty", True):
        return {
            "ok": False,
            "status": "MISSING" if df is not None else "SOURCE_ERROR",
            "error": "empty_or_null_dataframe",
            "foreign_flow_scope": "HOSE",
            "units": "UNPROVEN",
            "historical_semantics": "UNSUPPORTED_NO_DATE_PARAM",
        }
    cols = {str(c).lower(): c for c in df.columns}
    buy_val = _pick_col(cols, ("foreign_buy_value", "frbuyval", "buy_val", "foreignbuyvalue", "fbuy_val"))
    sell_val = _pick_col(cols, ("foreign_sell_value", "frsellval", "sell_val", "foreignsellvalue", "fsell_val"))
    buy_vol = _pick_col(cols, ("foreign_buy_volume", "frbuyvol", "buy_vol", "foreignbuyvolume"))
    sell_vol = _pick_col(cols, ("foreign_sell_volume", "frsellvol", "sell_vol", "foreignsellvolume"))

    buy_v = _sum_numeric(df, buy_val)
    sell_v = _sum_numeric(df, sell_val)
    net_v = (buy_v - sell_v) if buy_v is not None and sell_v is not None else None
    buy_vo = _sum_numeric(df, buy_vol)
    sell_vo = _sum_numeric(df, sell_vol)
    net_vo = (buy_vo - sell_vo) if buy_vo is not None and sell_vo is not None else None

    net_check = None
    if net_v is not None and buy_v is not None and sell_v is not None:
        net_check = abs(net_v - (buy_v - sell_v)) < 1e-6

    return {
        "ok": buy_v is not None and sell_v is not None,
        "status": "OK" if buy_v is not None and sell_v is not None else "SOURCE_ERROR",
        "trade_date_requested": trade_date,
        "foreign_flow_scope": "HOSE",
        "scope_note": (
            "SSI endpoint /stock/exchange/HOSE returns HOSE-listed names only; "
            "not VNINDEX constituents exclusively and not all VN exchanges."
        ),
        "n_rows": int(len(df)),
        "columns": [str(c) for c in df.columns],
        "matched_columns": {
            "buy_value": str(buy_val) if buy_val is not None else None,
            "sell_value": str(sell_val) if sell_val is not None else None,
            "buy_volume": str(buy_vol) if buy_vol is not None else None,
            "sell_volume": str(sell_vol) if sell_vol is not None else None,
        },
        "values": {
            "foreign_buy_value": buy_v,
            "foreign_sell_value": sell_v,
            "foreign_net_value": net_v,
            "foreign_buy_volume": buy_vo,
            "foreign_sell_volume": sell_vo,
            "foreign_net_volume": net_vo,
        },
        "net_equals_buy_minus_sell": net_check,
        "units": "PROVIDER_NATIVE_UNPROVEN",
        "units_note": (
            "Do not assume VND / million VND / billion VND without proving provider semantics "
            "against an independent official print for the same session."
        ),
        "historical_semantics": "UNSUPPORTED_NO_DATE_PARAM",
        "historical_note": (
            "vnstock.fr_trade_heatmap / SSI exchange endpoint accept no trade_date; "
            "response is session-current live board. Historical backfill not proven → FORWARD_ONLY."
        ),
    }


def call_fr_trade_heatmap(symbol: str = "HOSE") -> Dict[str, Any]:
    """Invoke the same provider API semantics as P0 SsiHoseForeignFlowProvider."""
    out: Dict[str, Any] = {
        "provider_call": f"vnstock.fr_trade_heatmap(symbol={symbol!r}, report_type='FrBuyVal')",
        "observed_at": _utc_now_iso(),
    }
    try:
        from vnstock import fr_trade_heatmap  # type: ignore
    except Exception as exc:  # noqa: BLE001
        out.update({"ok": False, "error": f"vnstock_import:{exc}"})
        return out
    try:
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            df = fr_trade_heatmap(symbol=symbol, report_type="FrBuyVal")
        out["stdout_stderr"] = buf.getvalue()[:500]
        if df is None:
            out.update({"ok": False, "error": "null_dataframe"})
            return out
        out["ok"] = True
        out["n_rows"] = int(len(df))
        out["columns"] = [str(c) for c in df.columns]
        out["dataframe"] = df
        return out
    except Exception as exc:  # noqa: BLE001
        out.update({"ok": False, "error": f"fetch_exception:{exc}"})
        return out


def alternative_source_feasibility_audit() -> List[Dict[str, Any]]:
    """
    Source feasibility only — no Cloudflare bypass, no new architecture.
    Quality uncertain → do not auto-implement adapters.
    """
    return [
        {
            "source": "SSI iboard fr_trade_heatmap (current P0)",
            "foreign_buy": "YES (value cols when reachable)",
            "foreign_sell": "YES",
            "net": "DERIVED buy-sell",
            "historical": "NO (no date param; live snapshot)",
            "scope": "HOSE exchange listing (or HNX/UPCOM/All if symbol changed)",
            "pit_suitable": "FORWARD_ONLY after close if reachable",
            "reliability": "Cloudflare 403 in Cursor/dev; PRODUCTION UNKNOWN",
            "already_installed": "YES (vnstock 0.2.9.2 app path); NO on vnstock 4.x collector",
            "implement_now": False,
        },
        {
            "source": "EMS earning_money_snapshots",
            "foreign_buy": "NO",
            "foreign_sell": "NO",
            "net": "NO",
            "historical": "N/A",
            "scope": "EMS research universe 142",
            "pit_suitable": "N/A — no foreign fields",
            "reliability": "Trusted for universe turnover only",
            "already_installed": "YES",
            "implement_now": False,
        },
        {
            "source": "market_daily_t0",
            "foreign_buy": "NO",
            "foreign_sell": "NO",
            "net": "NO",
            "historical": "N/A",
            "scope": "Market First canonical T0",
            "pit_suitable": "N/A — no foreign fields",
            "reliability": "Trusted for VNI OHLCV/volume",
            "already_installed": "YES",
            "implement_now": False,
        },
        {
            "source": "vnstock 4.x VCI Trading.price_board",
            "foreign_buy": "NO (ownership room/volume, not session buy value)",
            "foreign_sell": "NO",
            "net": "NO",
            "historical": "UNCLEAR",
            "scope": "Per-symbol board",
            "pit_suitable": "NO for P0 foreign flow contract",
            "reliability": "Wrong semantics (room/holding ≠ flow)",
            "already_installed": "Collector venv docs (vnstock>=4.0.5)",
            "implement_now": False,
        },
        {
            "source": "vnstock 4.x KBS price board / foreignTotal ranking",
            "foreign_buy": "VOLUME only (mapped FB)",
            "foreign_sell": "VOLUME only (mapped FS)",
            "net": "VOLUME only; value unknown",
            "historical": "UNPROVEN",
            "scope": "Broker board; exchange scope unclear",
            "pit_suitable": "UNCERTAIN",
            "reliability": "Not used by this project; auth/headers unknown; value fields absent",
            "already_installed": "API present in vnstock 4.x package; not wired in Mr.BOT",
            "implement_now": False,
        },
        {
            "source": "Official HOSE / public exchange prints",
            "foreign_buy": "POSSIBLE via official publications",
            "foreign_sell": "POSSIBLE",
            "net": "POSSIBLE",
            "historical": "Often YES in official archives",
            "scope": "Exchange-defined",
            "pit_suitable": "If dated official close prints",
            "reliability": "No existing project adapter; would be new integration",
            "already_installed": "NO",
            "implement_now": False,
        },
    ]


def run_verification(*, trade_date: Optional[str] = None, persist_json: Optional[Path] = None) -> Dict[str, Any]:
    """
    Full verification payload.
    When not on production VPS, verdict is P0_PRODUCTION_VERIFICATION_BLOCKED.
    """
    trade_date = (trade_date or datetime.now().strftime("%Y-%m-%d"))[:10]
    runtime = detect_runtime()
    http_probe = probe_ssi_hose_http()
    heatmap = call_fr_trade_heatmap("HOSE")
    analysis: Dict[str, Any] = {}
    if heatmap.get("ok") and "dataframe" in heatmap:
        analysis = analyze_ssi_heatmap_dataframe(heatmap["dataframe"], trade_date=trade_date)
        # Drop non-serializable frame
        heatmap = {k: v for k, v in heatmap.items() if k != "dataframe"}
    else:
        heatmap = {k: v for k, v in heatmap.items() if k != "dataframe"}
        analysis = {
            "ok": False,
            "status": "SOURCE_ERROR",
            "error": heatmap.get("error") or f"http:{http_probe.get('http_status')}",
            "foreign_flow_scope": "HOSE",
            "units": "UNPROVEN",
            "historical_semantics": "UNSUPPORTED_NO_DATE_PARAM",
        }

    on_vps = bool(runtime.get("is_production_vps"))
    provider_reachable = bool(http_probe.get("reachable")) and bool(analysis.get("ok"))

    if not on_vps:
        verdict = "P0_PRODUCTION_VERIFICATION_BLOCKED"
        historical = "UNRESOLVED"
    elif provider_reachable:
        # Even when live works, API has no date → forward only unless separately proven.
        verdict = "P0_FOREIGN_FLOW_FORWARD_ONLY_READY"
        historical = "FORWARD_ONLY"
    else:
        verdict = "P0_FOREIGN_PROVIDER_BLOCKED"
        historical = "FORWARD_ONLY"

    report = {
        "verdict": verdict,
        "historical_capability": historical,
        "production_result": {
            "vps_tested": "YES" if on_vps else "NO",
            "provider_reachable": "YES" if provider_reachable else "NO",
            "exact_result_or_error": {
                "http": {
                    "status": http_probe.get("http_status"),
                    "server": http_probe.get("server"),
                    "cf_ray": http_probe.get("cf_ray"),
                    "error": http_probe.get("error"),
                    "body_prefix": http_probe.get("body_prefix"),
                },
                "fr_trade_heatmap": {k: heatmap.get(k) for k in ("ok", "error", "n_rows", "columns", "stdout_stderr")},
                "analysis_error": analysis.get("error"),
            },
            "tested_trade_date": trade_date,
            "market_scope": analysis.get("foreign_flow_scope", "HOSE"),
            "units": analysis.get("units", "UNPROVEN"),
        },
        "runtime": runtime,
        "http_probe": http_probe,
        "heatmap_call": heatmap,
        "analysis": {k: v for k, v in analysis.items() if k != "dataframe"},
        "alternative_sources": alternative_source_feasibility_audit(),
        "automation_note": (
            "P0 foreign collection is hooked fail-safe via "
            "market_t0_capture → maybe_freeze_after_market_daily → maybe_collect_p0_after_market_daily "
            "and CLI --p0-collect. Streamlit need not stay open if an equivalent ≥18:00 VN "
            "host process runs market_t0_capture / daily_entrypoint on the app Python that has "
            "vnstock.fr_trade_heatmap (legacy 0.2.9.2). Collector vnstock 4.x lacks that symbol."
        ),
        "observed_at": _utc_now_iso(),
    }

    if persist_json is not None:
        persist_json.parent.mkdir(parents=True, exist_ok=True)
        persist_json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        report["persisted_to"] = str(persist_json)
    return report


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Verify P0 SSI foreign-flow on production VPS")
    parser.add_argument("--trade-date", default=None)
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "diagnostics" / "p0_foreign_flow_vps_verification" / "last_probe.json"),
    )
    args = parser.parse_args(argv)
    report = run_verification(trade_date=args.trade_date, persist_json=Path(args.out))
    # Compact stdout for operators
    slim = {
        "verdict": report["verdict"],
        "historical_capability": report["historical_capability"],
        "production_result": report["production_result"],
        "runtime": {
            k: report["runtime"][k]
            for k in (
                "is_production_vps",
                "hostname",
                "python_executable",
                "vnstock_version",
                "has_fr_trade_heatmap",
            )
        },
        "persisted_to": report.get("persisted_to"),
    }
    print(json.dumps(slim, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
