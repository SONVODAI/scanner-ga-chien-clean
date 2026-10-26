#!/usr/bin/env python3
"""
STANDALONE read-only SSI HOSE foreign-flow probe for production VPS.

- Does NOT import Mr.BOT application modules
- Does NOT write under /opt/mrbot-camera unless --out is pointed there
- Does NOT start/stop systemd, Streamlit, Market First, Forecast, Edge, or Camera
- Does NOT bypass Cloudflare / CAPTCHA / access controls
- Single GET + optional vnstock.fr_trade_heatmap call

Safe usage on VPS (from /tmp, no git deploy):

  curl -fsSL -o /tmp/standalone_ssi_foreign_flow_probe.py \\
    https://raw.githubusercontent.com/SONVODAI/scanner-ga-chien-clean/cursor/p0-foreign-flow-vps-verification-aad2/scripts/standalone_ssi_foreign_flow_probe.py
  python3 /tmp/standalone_ssi_foreign_flow_probe.py --out /tmp/ssi_foreign_probe.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SSI_HOSE_URL = "https://iboard-query.ssi.com.vn/stock/exchange/HOSE"
PROD_REPO = "/opt/mrbot-camera"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def detect_runtime() -> Dict[str, Any]:
    vnstock_version: Optional[str] = None
    vnstock_file: Optional[str] = None
    has_fr = False
    try:
        import vnstock  # type: ignore

        vnstock_file = getattr(vnstock, "__file__", None)
        has_fr = hasattr(vnstock, "fr_trade_heatmap")
        vnstock_version = getattr(vnstock, "__version__", None) or "unknown"
        if vnstock_version == "unknown":
            try:
                from importlib.metadata import version

                vnstock_version = version("vnstock")
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        vnstock_version = f"import_error:{type(exc).__name__}:{exc}"

    return {
        "is_production_vps_tree_present": os.path.isdir(PROD_REPO) and os.path.isdir(os.path.join(PROD_REPO, "modules")),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "cwd": os.getcwd(),
        "vnstock_version": vnstock_version,
        "vnstock_file": vnstock_file,
        "has_fr_trade_heatmap": has_fr,
        "observed_at": _utc_now(),
    }


def probe_http(timeout_s: float = 15.0) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "url": SSI_HOSE_URL,
        "provider_call": "GET iboard-query.ssi.com.vn/stock/exchange/HOSE",
        "observed_at": _utc_now(),
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
        body = (resp.text or "")[:400].replace("\n", " ")
        out.update(
            {
                "reachable": resp.status_code == 200,
                "http_status": resp.status_code,
                "server": resp.headers.get("server"),
                "cf_ray": resp.headers.get("cf-ray"),
                "content_type": resp.headers.get("content-type"),
                "body_prefix": body,
            }
        )
        if resp.status_code == 200:
            try:
                payload = resp.json()
                data = payload.get("data") if isinstance(payload, dict) else None
                out["n_rows"] = len(data) if isinstance(data, list) else None
                if isinstance(data, list) and data:
                    keys = sorted({k for row in data[:5] if isinstance(row, dict) for k in row.keys()})
                    out["sample_keys"] = keys[:80]
                    # Aggregate foreign value columns if present (provider-native units).
                    buy = sell = 0.0
                    n_buy = n_sell = 0
                    for row in data:
                        if not isinstance(row, dict):
                            continue
                        # common SSI camelCase keys observed in vnstock heatmap
                        for bk in ("foreignBuyValue", "frBuyVal", "buyVal", "foreign_buy_value"):
                            if bk in row and row[bk] is not None:
                                try:
                                    buy += float(row[bk])
                                    n_buy += 1
                                    break
                                except (TypeError, ValueError):
                                    pass
                        for sk in ("foreignSellValue", "frSellVal", "sellVal", "foreign_sell_value"):
                            if sk in row and row[sk] is not None:
                                try:
                                    sell += float(row[sk])
                                    n_sell += 1
                                    break
                                except (TypeError, ValueError):
                                    pass
                    out["aggregate"] = {
                        "foreign_flow_scope": "HOSE",
                        "foreign_buy_value": buy if n_buy else None,
                        "foreign_sell_value": sell if n_sell else None,
                        "foreign_net_value": (buy - sell) if (n_buy and n_sell) else None,
                        "n_buy_rows": n_buy,
                        "n_sell_rows": n_sell,
                        "units": "PROVIDER_NATIVE_UNPROVEN",
                        "historical_semantics": "UNSUPPORTED_NO_DATE_PARAM",
                    }
            except Exception as exc:  # noqa: BLE001
                out["json_error"] = f"{type(exc).__name__}:{exc}"
    except Exception as exc:  # noqa: BLE001
        out.update({"reachable": False, "http_status": None, "error": f"{type(exc).__name__}:{exc}"})
    return out


def call_fr_trade_heatmap() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "provider_call": "vnstock.fr_trade_heatmap(symbol='HOSE', report_type='FrBuyVal')",
        "observed_at": _utc_now(),
    }
    try:
        from vnstock import fr_trade_heatmap  # type: ignore
    except Exception as exc:  # noqa: BLE001
        out.update({"ok": False, "error": f"vnstock_import:{type(exc).__name__}:{exc}"})
        return out
    try:
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            df = fr_trade_heatmap(symbol="HOSE", report_type="FrBuyVal")
        out["stdout_stderr"] = buf.getvalue()[:500]
        if df is None:
            out.update({"ok": False, "error": "null_dataframe"})
            return out
        out["ok"] = True
        out["n_rows"] = int(len(df))
        out["columns"] = [str(c) for c in getattr(df, "columns", [])]
        return out
    except Exception as exc:  # noqa: BLE001
        out.update({"ok": False, "error": f"fetch_exception:{type(exc).__name__}:{exc}"})
        return out


def pick_pythons() -> List[str]:
    cands = [
        os.environ.get("MRBOT_APP_PYTHON") or "",
        "/opt/mrbot-camera/.venv/bin/python",
        "/opt/mrbot-camera-venv/bin/python",
        sys.executable,
        "python3",
    ]
    out: List[str] = []
    for p in cands:
        if not p or p in out:
            continue
        out.append(p)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Standalone read-only SSI HOSE foreign-flow probe")
    parser.add_argument("--out", default="/tmp/ssi_foreign_probe.json")
    parser.add_argument("--also-try-collector-venv", action="store_true", help="Print note only; run this file under each python manually")
    args = parser.parse_args(argv)

    runtime = detect_runtime()
    http = probe_http()
    heatmap = call_fr_trade_heatmap()
    reachable = bool(http.get("reachable"))
    on_vps = bool(runtime.get("is_production_vps_tree_present"))

    if not on_vps:
        verdict = "P0_PRODUCTION_VERIFICATION_BLOCKED"
    elif reachable:
        verdict = "P0_FOREIGN_FLOW_FORWARD_ONLY_READY"
    else:
        verdict = "P0_FOREIGN_PROVIDER_BLOCKED"

    report = {
        "verdict": verdict,
        "historical_capability": "FORWARD_ONLY" if on_vps else "UNRESOLVED",
        "note": (
            "Read-only probe. Missing script on VPS checkout is NOT provider failure. "
            "SSI endpoint has no trade_date → FORWARD_ONLY even when reachable. "
            "Units unproven until cross-checked against official print."
        ),
        "production_result": {
            "vps_tree_present": "YES" if on_vps else "NO",
            "provider_reachable": "YES" if reachable else "NO",
            "http_status": http.get("http_status"),
            "server": http.get("server"),
            "cf_ray": http.get("cf_ray"),
            "fr_trade_heatmap_ok": heatmap.get("ok"),
            "fr_trade_heatmap_error": heatmap.get("error"),
            "market_scope": "HOSE",
            "units": "PROVIDER_NATIVE_UNPROVEN",
            "aggregate": http.get("aggregate"),
        },
        "runtime": runtime,
        "http_probe": http,
        "heatmap_call": heatmap,
        "python_candidates_to_retry_manually": pick_pythons(),
        "observed_at": _utc_now(),
    }

    out_path = args.out
    parent = os.path.dirname(out_path) or "."
    os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    slim = {
        "verdict": report["verdict"],
        "historical_capability": report["historical_capability"],
        "production_result": report["production_result"],
        "runtime": {
            k: runtime[k]
            for k in (
                "is_production_vps_tree_present",
                "hostname",
                "python_executable",
                "vnstock_version",
                "has_fr_trade_heatmap",
            )
        },
        "wrote": out_path,
    }
    print(json.dumps(slim, indent=2, default=str))
    if args.also_try_collector_venv:
        print(
            "\nRetry under each candidate python:\n"
            + "\n".join(f"  {p} {sys.argv[0]} --out /tmp/ssi_foreign_probe_{os.path.basename(p)}.json" for p in pick_pythons()),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
