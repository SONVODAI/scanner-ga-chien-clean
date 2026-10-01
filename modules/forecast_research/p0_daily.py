"""
P0 Forward Market Memory — canonical daily raw + derived features.

Separate from Forecast T0 and MDRR immutability:
- Writes p0_market_daily.csv (first-write-wins; foreign enrichment allowed when null)
- Does not rewrite frozen MDRR / forecast_t0 / MDT0 rows
- Missing ≠ 0
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from modules.durable_csv import durable_replace_csv
from modules.forecast_research.contract import (
    EXPECTED_UNIVERSE_SIZE,
    P0_COMPLETENESS_COMPLETE,
    P0_COMPLETENESS_PARTIAL,
    P0_COMPLETENESS_SOURCE_ERROR,
    P0_COMPLETENESS_WAITING,
    P0_DAILY_FILE,
    P0_FOREIGN_SCOPE_DEFAULT,
    P0_SCHEMA_VERSION,
    P0_STATUS_FILE,
    P0_UNIVERSE_FOREIGN_SCOPE,
    P0_UNIVERSE_TURNOVER_SCOPE,
    P0_VNINDEX_VOLUME_SCOPE,
    FORWARD_ONLY_REGISTRY_FILE,
)
from modules.forecast_research.historical_recovery import is_weekday_session
from modules.forecast_research.p0_indicators import indicators_asof
from modules.forecast_research.p0_providers import (
    ForeignFlowProvider,
    ProviderResult,
    VnindexHistoryProvider,
    VnstockVnindexHistoryProvider,
    compute_universe_turnover_from_ems,
    vnindex_volume_from_mdt0_or_fetch,
    _finite_or_none,
)
from modules.forecast_research.p0_universe_foreign import (
    UniverseForeignFlowCascade,
    empty_universe_foreign_values,
)
from modules.forecast_research.t0_builder import DEFAULT_EMS, DEFAULT_MDT0
from modules.forecast_research.t0_persistence import resolve_forecast_data_dir

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]

UNIVERSE_FOREIGN_VALUE_FIELDS = (
    "universe_foreign_buy_value",
    "universe_foreign_sell_value",
    "universe_foreign_net_value",
    "universe_foreign_buy_volume",
    "universe_foreign_sell_volume",
    "universe_foreign_net_volume",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def p0_path(data_dir: Optional[Path] = None) -> Path:
    return resolve_forecast_data_dir(data_dir) / P0_DAILY_FILE


def load_p0_table(data_dir: Optional[Path] = None) -> pd.DataFrame:
    path = p0_path(data_dir)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def persist_p0_record(
    record: Dict[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    path = p0_path(data_dir)
    existing = load_p0_table(data_dir)
    td = str(record["trade_date"])[:10]
    if not existing.empty and "trade_date" in existing.columns:
        if (existing["trade_date"].astype(str).str[:10] == td).any():
            return False, "ALREADY_PRESENT"
    row = pd.DataFrame([record])
    out = row if existing.empty else pd.concat([existing, row], ignore_index=True)
    ok, reason = durable_replace_csv(
        out,
        path,
        existing=existing if not existing.empty else None,
        date_col="trade_date",
        backup=True,
        keep=5,
    )
    if not ok:
        return False, reason
    return True, "WRITTEN"


def _universe_foreign_null(row: pd.Series) -> bool:
    if "universe_foreign_net_value" not in row.index:
        return True
    v = row.get("universe_foreign_net_value")
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    try:
        if pd.isna(v):
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _needs_universe_foreign_enrichment(row: pd.Series, trade_date: str) -> bool:
    """
    Enrich when foreign fields are null, or when PARTIAL on the current calendar
    session (VCI may complete multi-exchange EMS membership).
    Do not re-hammer historical PARTIAL rows.
    """
    from datetime import date

    if _universe_foreign_null(row):
        return True
    comp = str(row.get("universe_foreign_completeness") or "")
    if comp == P0_COMPLETENESS_COMPLETE:
        return False
    return str(trade_date)[:10] == date.today().isoformat()


def enrich_p0_universe_foreign(
    record_patch: Dict[str, Any],
    *,
    data_dir: Optional[Path] = None,
    force: bool = False,
) -> Tuple[bool, str]:
    """
    Fill/upgrade universe_foreign_* on an existing P0 row.
    Default: only when null. force=True allows PARTIAL→COMPLETE upgrade.
    Does not rewrite turnover/tech/MDT0/MDRR/Forecast.
    """
    path = p0_path(data_dir)
    existing = load_p0_table(data_dir)
    td = str(record_patch["trade_date"])[:10]
    if existing.empty or "trade_date" not in existing.columns:
        return False, "NO_EXISTING_ROW"
    mask = existing["trade_date"].astype(str).str[:10] == td
    if not mask.any():
        return False, "NO_EXISTING_ROW"
    idx = existing.index[mask][-1]
    if not force and not _universe_foreign_null(existing.loc[idx]):
        return False, "FOREIGN_ALREADY_PRESENT"
    if (
        force
        and not _universe_foreign_null(existing.loc[idx])
        and str(existing.loc[idx].get("universe_foreign_completeness") or "") == P0_COMPLETENESS_COMPLETE
    ):
        return False, "FOREIGN_ALREADY_PRESENT"

    prior_for_guard = existing.copy()
    for key, val in record_patch.items():
        if key in ("trade_date", "created_at", "record_hash"):
            continue
        if key.startswith("universe_foreign") or key in (
            "foreign_flow_scope",
            "schema_version",
            "provenance_json",
            "observed_at",
            "completeness_status",
            "forward_only",
        ):
            existing.at[idx, key] = val

    row = existing.loc[idx].to_dict()
    hash_body = {k: v for k, v in row.items() if k not in ("created_at", "record_hash")}
    existing.at[idx, "record_hash"] = _stable_hash(hash_body)
    ok, reason = durable_replace_csv(
        existing,
        path,
        existing=prior_for_guard,
        date_col="trade_date",
        backup=True,
        keep=5,
    )
    if not ok:
        return False, reason
    return True, "ENRICHED"


def _avg_turnover(prior_values: Sequence[float], window: int) -> Optional[float]:
    if len(prior_values) < window:
        return None
    chunk = prior_values[-window:]
    if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in chunk):
        return None
    return float(np.mean(chunk))


def derive_avg_turnover_from_p0(
    trade_date: str,
    current_turnover: Optional[float],
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Optional[float]]:
    out = {"avg_turnover_value_5": None, "avg_turnover_value_10": None, "avg_turnover_value_20": None}
    if current_turnover is None:
        return out
    table = load_p0_table(data_dir)
    series: List[float] = []
    if not table.empty and "universe_turnover_value" in table.columns:
        prior = table[table["trade_date"].astype(str).str[:10] < trade_date].sort_values("trade_date")
        for _, row in prior.iterrows():
            v = _finite_or_none(row.get("universe_turnover_value"))
            if v is not None:
                series.append(v)
    series.append(float(current_turnover))
    for w in (5, 10, 20):
        out[f"avg_turnover_value_{w}"] = _avg_turnover(series, w)
    return out


def derive_vnindex_technicals(
    trade_date: str,
    *,
    history_provider: Optional[VnindexHistoryProvider] = None,
) -> Tuple[Dict[str, Optional[float]], Dict[str, Any]]:
    provider = history_provider or VnstockVnindexHistoryProvider()
    hist = provider.fetch_ohlcv(trade_date, lookback_days=160)
    meta: Dict[str, Any] = {"provider": type(provider).__name__, "n_bars": int(len(hist))}
    empty = {
        "vnindex_rsi14": None,
        "vnindex_macd": None,
        "vnindex_macd_signal": None,
        "vnindex_macd_histogram": None,
        "vnindex_bb_middle": None,
        "vnindex_bb_upper": None,
        "vnindex_bb_lower": None,
        "vnindex_bb_width": None,
        "vnindex_bb_position": None,
    }
    if hist.empty or "close" not in hist.columns:
        meta["status"] = "SOURCE_ERROR"
        return empty, meta
    hist = hist[hist["date"].astype(str).str[:10] <= trade_date].copy()
    if hist.empty:
        meta["status"] = "MISSING"
        return empty, meta
    dates = hist["date"].astype(str).str[:10].tolist()
    if trade_date not in dates:
        meta["status"] = "MISSING"
        meta["last_available"] = dates[-1]
        return empty, meta
    idx = dates.index(trade_date)
    closes = pd.to_numeric(hist["close"], errors="coerce")
    vals = indicators_asof(closes, idx)
    meta["status"] = "OK"
    meta["asof"] = trade_date
    return vals, meta


def _merge_status(parts: List[str]) -> str:
    if any(p == P0_COMPLETENESS_SOURCE_ERROR for p in parts):
        if any(p in (P0_COMPLETENESS_COMPLETE, P0_COMPLETENESS_PARTIAL) for p in parts):
            return P0_COMPLETENESS_PARTIAL
        if all(p == P0_COMPLETENESS_SOURCE_ERROR for p in parts):
            return P0_COMPLETENESS_SOURCE_ERROR
    if all(p == P0_COMPLETENESS_WAITING for p in parts):
        return P0_COMPLETENESS_WAITING
    if any(p == P0_COMPLETENESS_COMPLETE for p in parts) and not any(
        p in (P0_COMPLETENESS_PARTIAL, P0_COMPLETENESS_WAITING, P0_COMPLETENESS_SOURCE_ERROR) for p in parts
    ):
        return P0_COMPLETENESS_COMPLETE
    if any(p == P0_COMPLETENESS_COMPLETE for p in parts) or any(p == P0_COMPLETENESS_PARTIAL for p in parts):
        return P0_COMPLETENESS_PARTIAL
    return P0_COMPLETENESS_WAITING


def _normalize_foreign_provider_values(fr: ProviderResult) -> Dict[str, Optional[float]]:
    """Accept universe_foreign_* or legacy mock foreign_* keys."""
    vals = empty_universe_foreign_values()
    src = fr.values or {}
    mapping = {
        "universe_foreign_buy_value": ("universe_foreign_buy_value", "foreign_buy_value"),
        "universe_foreign_sell_value": ("universe_foreign_sell_value", "foreign_sell_value"),
        "universe_foreign_net_value": ("universe_foreign_net_value", "foreign_net_value"),
        "universe_foreign_buy_volume": ("universe_foreign_buy_volume", "foreign_buy_volume"),
        "universe_foreign_sell_volume": ("universe_foreign_sell_volume", "foreign_sell_volume"),
        "universe_foreign_net_volume": ("universe_foreign_net_volume", "foreign_net_volume"),
    }
    for dest, keys in mapping.items():
        for k in keys:
            if k in src and src[k] is not None:
                vals[dest] = _finite_or_none(src[k])
                break
    if vals["universe_foreign_buy_value"] is not None and vals["universe_foreign_sell_value"] is not None:
        vals["universe_foreign_net_value"] = (
            vals["universe_foreign_buy_value"] - vals["universe_foreign_sell_value"]
        )
    return vals


def build_p0_record(
    trade_date: str,
    *,
    data_dir: Optional[Path] = None,
    ems_path: Path = DEFAULT_EMS,
    md_path: Path = DEFAULT_MDT0,
    foreign_provider: Optional[ForeignFlowProvider] = None,
    history_provider: Optional[VnindexHistoryProvider] = None,
    collect_foreign: bool = True,
) -> Optional[Dict[str, Any]]:
    trade_date = str(trade_date)[:10]
    if not is_weekday_session(trade_date):
        return None

    foreign_provider = foreign_provider or UniverseForeignFlowCascade(ems_path=ems_path)
    history_provider = history_provider or VnstockVnindexHistoryProvider()

    statuses: List[str] = []
    provenance: Dict[str, Any] = {}

    # --- Universe foreign (HSX → VCI) ---
    u_foreign = empty_universe_foreign_values()
    u_foreign_meta: Dict[str, Any] = {
        "completeness": P0_COMPLETENESS_WAITING,
        "expected_count": None,
        "observed_count": None,
        "completeness_ratio": None,
        "source": None,
        "units": "VND",
        "scope": P0_UNIVERSE_FOREIGN_SCOPE,
    }
    if collect_foreign:
        fr: ProviderResult = foreign_provider.fetch(trade_date)
        provenance["universe_foreign"] = {"status": fr.status, "meta": fr.meta, "error": fr.error}
        u_foreign_meta.update(
            {
                "completeness": fr.meta.get("completeness") or P0_COMPLETENESS_WAITING,
                "expected_count": fr.meta.get("expected_count"),
                "observed_count": fr.meta.get("observed_count"),
                "completeness_ratio": fr.meta.get("completeness_ratio"),
                "source": fr.meta.get("provider") or fr.meta.get("source_hierarchy"),
                "missing_symbols": fr.meta.get("missing_symbols"),
                "universe_hash": fr.meta.get("universe_hash"),
                "units": fr.meta.get("units") or "VND",
                "report_date_match_required": fr.meta.get("report_date_match_required", True),
            }
        )
        if fr.ok and fr.values:
            u_foreign = _normalize_foreign_provider_values(fr)
            # Incomplete universe cannot be COMPLETE
            if fr.meta.get("completeness") == P0_COMPLETENESS_COMPLETE:
                if (fr.meta.get("observed_count") or 0) < (fr.meta.get("expected_count") or EXPECTED_UNIVERSE_SIZE):
                    u_foreign_meta["completeness"] = P0_COMPLETENESS_PARTIAL
            statuses.append(
                P0_COMPLETENESS_COMPLETE
                if u_foreign_meta["completeness"] == P0_COMPLETENESS_COMPLETE
                else P0_COMPLETENESS_PARTIAL
                if u_foreign.get("universe_foreign_net_value") is not None
                else P0_COMPLETENESS_WAITING
            )
        elif fr.status == "SOURCE_ERROR":
            u_foreign_meta["completeness"] = P0_COMPLETENESS_SOURCE_ERROR
            statuses.append(P0_COMPLETENESS_SOURCE_ERROR)
        else:
            statuses.append(P0_COMPLETENESS_WAITING)

    # Legacy HOSE-SSI fields: intentionally NULL (retired preferred path)
    legacy_foreign = {
        "foreign_buy_value": None,
        "foreign_sell_value": None,
        "foreign_net_value": None,
        "foreign_buy_volume": None,
        "foreign_sell_volume": None,
        "foreign_net_volume": None,
    }

    # --- Universe turnover (EMS) ---
    turn = compute_universe_turnover_from_ems(trade_date, ems_path=ems_path)
    provenance["universe_turnover"] = {"status": turn.status, "meta": turn.meta, "error": turn.error}
    universe_turnover = _finite_or_none(turn.values.get("universe_turnover_value")) if turn.ok else None
    universe_volume = _finite_or_none(turn.values.get("universe_volume")) if turn.ok else None
    if turn.ok:
        statuses.append(P0_COMPLETENESS_PARTIAL)
    elif turn.status == "SOURCE_ERROR":
        statuses.append(P0_COMPLETENESS_SOURCE_ERROR)
    else:
        statuses.append(P0_COMPLETENESS_WAITING)

    # --- VNINDEX volume ---
    vv = vnindex_volume_from_mdt0_or_fetch(trade_date, md_path=md_path, history_provider=history_provider)
    provenance["vnindex_volume"] = {"status": vv.status, "meta": vv.meta, "error": vv.error}
    vnindex_volume = _finite_or_none(vv.values.get("vnindex_volume")) if vv.ok else None
    if vv.ok:
        statuses.append(P0_COMPLETENESS_PARTIAL)
    elif vv.status == "SOURCE_ERROR":
        statuses.append(P0_COMPLETENESS_SOURCE_ERROR)
    else:
        statuses.append(P0_COMPLETENESS_WAITING)

    avgs = derive_avg_turnover_from_p0(trade_date, universe_turnover, data_dir=data_dir)

    tech, tech_meta = derive_vnindex_technicals(trade_date, history_provider=history_provider)
    provenance["vnindex_technicals"] = tech_meta
    if tech_meta.get("status") == "OK" and any(v is not None for v in tech.values()):
        statuses.append(P0_COMPLETENESS_PARTIAL)
    elif tech_meta.get("status") == "SOURCE_ERROR":
        statuses.append(P0_COMPLETENESS_SOURCE_ERROR)

    # Overall COMPLETE only when universe foreign COMPLETE + turnover + vnindex volume + rsi
    has_foreign_complete = u_foreign_meta.get("completeness") == P0_COMPLETENESS_COMPLETE and (
        u_foreign.get("universe_foreign_net_value") is not None
    )
    has_turn = universe_turnover is not None
    has_vol = vnindex_volume is not None
    has_rsi = tech.get("vnindex_rsi14") is not None
    if has_foreign_complete and has_turn and has_vol and has_rsi:
        completeness = P0_COMPLETENESS_COMPLETE
    else:
        completeness = _merge_status(statuses) if statuses else P0_COMPLETENESS_WAITING

    expected_count = u_foreign_meta.get("expected_count")
    observed_count = u_foreign_meta.get("observed_count")

    record: Dict[str, Any] = {
        "trade_date": trade_date,
        "data_cutoff": trade_date,
        "observed_at": _utc_now_iso(),
        "schema_version": P0_SCHEMA_VERSION,
        "completeness_status": completeness,
        # Legacy label retained; preferred scope is universe_foreign_scope
        "foreign_scope": P0_FOREIGN_SCOPE_DEFAULT,
        "foreign_flow_scope": P0_UNIVERSE_FOREIGN_SCOPE,
        "universe_foreign_scope": P0_UNIVERSE_FOREIGN_SCOPE,
        "universe_turnover_scope": P0_UNIVERSE_TURNOVER_SCOPE,
        "vnindex_volume_scope": P0_VNINDEX_VOLUME_SCOPE,
        "expected_universe_size": EXPECTED_UNIVERSE_SIZE,
        **legacy_foreign,
        **u_foreign,
        "universe_foreign_expected_count": expected_count,
        "universe_foreign_observed_count": observed_count,
        "universe_foreign_completeness": u_foreign_meta.get("completeness"),
        "universe_foreign_completeness_ratio": u_foreign_meta.get("completeness_ratio"),
        "universe_foreign_source": u_foreign_meta.get("source"),
        "universe_foreign_units": "VND",
        "universe_foreign_missing_symbols_json": json.dumps(
            u_foreign_meta.get("missing_symbols") or [], ensure_ascii=False
        ),
        "universe_turnover_value": universe_turnover,
        "universe_volume": universe_volume,
        "market_turnover_value": None,
        "vnindex_volume": vnindex_volume,
        **avgs,
        **tech,
        "provenance_json": json.dumps(provenance, sort_keys=True, default=str),
        "created_at": _utc_now_iso(),
        "forward_only": True,
    }
    hash_body = {k: v for k, v in record.items() if k != "created_at"}
    record["record_hash"] = _stable_hash(hash_body)
    return record


def update_forward_only_registry_from_p0(*, data_dir: Optional[Path] = None) -> Path:
    from modules.forecast_research.mdrr import default_forward_only_registry

    root = resolve_forecast_data_dir(data_dir)
    path = root / FORWARD_ONLY_REGISTRY_FILE
    registry = default_forward_only_registry()
    table = load_p0_table(data_dir)

    def first_date(col: str) -> Optional[str]:
        if table.empty or col not in table.columns:
            return None
        s = pd.to_numeric(table[col], errors="coerce")
        hit = table.loc[s.notna(), "trade_date"]
        if hit.empty:
            return None
        return str(sorted(hit.astype(str).str[:10].tolist())[0])

    mapping = {
        "foreign_net_flow": "universe_foreign_net_value",
        "foreign_buy": "universe_foreign_buy_value",
        "foreign_sell": "universe_foreign_sell_value",
        "market_turnover": "universe_turnover_value",
        "market_adv": "avg_turnover_value_5",
        "vnindex_rsi": "vnindex_rsi14",
        "vnindex_macd": "vnindex_macd",
    }
    for field in registry["fields"]:
        name = field["feature"]
        col = mapping.get(name)
        if not col:
            continue
        fd = first_date(col)
        field["first_reliable_collection_date"] = fd
        field["forward_only"] = name.startswith("foreign")  # universe foreign may have HSX history
        if name in ("foreign_net_flow", "foreign_buy", "foreign_sell"):
            field["forward_only"] = False
            field["source"] = (
                "p0_market_daily.universe_foreign_* ← HSX official foreign (primary) / VCI board (fallback)"
            )
            field["notes"] = (
                "EMS_RESEARCH_UNIVERSE_142 VALUE in VND; NOT HOSE-wide; "
                "COMPLETE only when all membership-asof symbols observed; missing≠0"
            )
            field["scope"] = P0_UNIVERSE_FOREIGN_SCOPE
            field["units"] = "VND"
        if name == "market_turnover":
            field["source"] = "p0_market_daily.universe_turnover_value ← EMS sum(price*volume)"
            field["notes"] = "Research-universe turnover, not official exchange total"
        if name == "market_adv":
            field["source"] = "derived avg_turnover_value_20 from P0 universe_turnover_value"
            field["notes"] = "Average traded VALUE (not volume); PIT windows only"
        if name.startswith("vnindex_"):
            field["source"] = "derived from VNINDEX OHLCV via vnstock (no future bars)"
            field["historical_backfill_availability"] = False
            field["reconstruction_policy"] = "DERIVE_ON_COLLECT_FROM_OHLCV_ASOF; DO_NOT_REWRITE_MDT0"

    registry["p0_fields"] = [
        "universe_foreign_buy_value",
        "universe_foreign_sell_value",
        "universe_foreign_net_value",
        "universe_foreign_buy_volume",
        "universe_foreign_sell_volume",
        "universe_foreign_net_volume",
        "universe_foreign_expected_count",
        "universe_foreign_observed_count",
        "universe_foreign_completeness",
        "universe_foreign_completeness_ratio",
        "universe_foreign_source",
        "universe_foreign_units",
        "universe_turnover_value",
        "universe_volume",
        "market_turnover_value",
        "vnindex_volume",
        "avg_turnover_value_5",
        "avg_turnover_value_10",
        "avg_turnover_value_20",
        "vnindex_rsi14",
        "vnindex_macd",
        "vnindex_macd_signal",
        "vnindex_macd_histogram",
        "vnindex_bb_middle",
        "vnindex_bb_upper",
        "vnindex_bb_lower",
        "vnindex_bb_width",
        "vnindex_bb_position",
    ]
    registry["p0_schema_version"] = P0_SCHEMA_VERSION
    registry["universe_foreign_membership_rule"] = "EMS_SNAPSHOT_DATE_EXACT"
    path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    return path


def collect_p0_for_date(
    trade_date: str,
    *,
    data_dir: Optional[Path] = None,
    allow_foreign_enrichment: bool = True,
    **kwargs: Any,
) -> Dict[str, Any]:
    trade_date = str(trade_date)[:10]
    existing = load_p0_table(data_dir)
    if not existing.empty and (existing["trade_date"].astype(str).str[:10] == trade_date).any():
        row = existing[existing["trade_date"].astype(str).str[:10] == trade_date].iloc[-1]
        if allow_foreign_enrichment and _needs_universe_foreign_enrichment(row, trade_date):
            record = build_p0_record(trade_date, data_dir=data_dir, **kwargs)
            if record is None:
                return {"ok": False, "written": False, "reason": "non_trading_or_empty", "trade_date": trade_date}
            force = not _universe_foreign_null(row)
            ok, reason = enrich_p0_universe_foreign(record, data_dir=data_dir, force=force)
            update_forward_only_registry_from_p0(data_dir=data_dir)
            return {
                "ok": True,
                "written": ok,
                "reason": reason,
                "trade_date": trade_date,
                "completeness_status": record.get("completeness_status"),
                "universe_foreign_completeness": record.get("universe_foreign_completeness"),
                "universe_foreign_net_value": record.get("universe_foreign_net_value"),
                "record_hash": record.get("record_hash"),
            }
        return {
            "ok": True,
            "written": False,
            "reason": "ALREADY_PRESENT",
            "trade_date": trade_date,
            "completeness_status": row.get("completeness_status"),
            "record_hash": row.get("record_hash"),
        }
    record = build_p0_record(trade_date, data_dir=data_dir, **kwargs)
    if record is None:
        return {"ok": False, "written": False, "reason": "non_trading_or_empty", "trade_date": trade_date}
    written, reason = persist_p0_record(record, data_dir=data_dir)
    update_forward_only_registry_from_p0(data_dir=data_dir)
    return {
        "ok": True,
        "written": written,
        "reason": reason,
        "trade_date": trade_date,
        "completeness_status": record.get("completeness_status"),
        "universe_foreign_completeness": record.get("universe_foreign_completeness"),
        "record_hash": record.get("record_hash"),
        "universe_foreign_net_value": record.get("universe_foreign_net_value"),
        "universe_turnover_value": record.get("universe_turnover_value"),
    }


def maybe_collect_p0_after_market_daily(
    trade_date: str,
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Fail-safe hook — never raises into Market First."""
    try:
        return collect_p0_for_date(trade_date, data_dir=data_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("P0 market memory hook failed safely: %s", exc)
        return {"ok": False, "written": False, "reason": f"hook_error:{exc}"}


def run_p0_backfill(
    *,
    data_dir: Optional[Path] = None,
    dates: Optional[Sequence[str]] = None,
    collect_foreign: bool = True,
    foreign_provider: Optional[ForeignFlowProvider] = None,
) -> Dict[str, Any]:
    from modules.forecast_research.outcome_maturity import list_board_trading_dates

    target = list(dates) if dates is not None else list_board_trading_dates(DEFAULT_EMS)
    results = [
        collect_p0_for_date(
            d,
            data_dir=data_dir,
            collect_foreign=collect_foreign,
            foreign_provider=foreign_provider,
        )
        for d in target
        if is_weekday_session(d)
    ]
    update_forward_only_registry_from_p0(data_dir=data_dir)
    status = {
        "schema_version": P0_SCHEMA_VERSION,
        "written": sum(1 for r in results if r.get("written")),
        "n": len(results),
        "results": results,
    }
    (resolve_forecast_data_dir(data_dir) / P0_STATUS_FILE).write_text(
        json.dumps(status, indent=2, default=str), encoding="utf-8"
    )
    return status
