"""
Minimum Daily Research Record V1 — forward memory infrastructure.

Preserves after-close research-relevant market state without future labels.
Does not train models or couple to Edge Research / Camera / trading.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.forecast_research.contract import (
    COMPLETENESS_COMPLETE,
    COMPLETENESS_PARTIAL,
    COMPLETENESS_WAITING,
    EXPECTED_UNIVERSE_SIZE,
    FORBIDDEN_OUTCOME_COLUMNS,
    FORWARD_ONLY_REGISTRY_FILE,
    MDRR_FILE,
    MDRR_SCHEMA_VERSION,
    MDRR_STATUS_FILE,
)
from modules.forecast_research.historical_recovery import assert_no_forbidden_outcome_fields, is_weekday_session
from modules.forecast_research.t0_builder import (
    DEFAULT_EMS,
    DEFAULT_MDT0,
    build_t0_features_from_board,
    load_board,
    load_market_daily,
)
from modules.forecast_research.t0_persistence import resolve_forecast_data_dir

REPO_ROOT = Path(__file__).resolve().parents[2]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def mdrr_path(data_dir: Optional[Path] = None) -> Path:
    return resolve_forecast_data_dir(data_dir) / MDRR_FILE


def load_mdrr_table(data_dir: Optional[Path] = None) -> pd.DataFrame:
    path = mdrr_path(data_dir)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def persist_mdrr_record(
    record: Dict[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    assert_no_forbidden_outcome_fields(record)
    for bad in FORBIDDEN_OUTCOME_COLUMNS:
        if bad in record:
            raise ValueError(f"MDRR must not contain outcome field {bad}")
    path = mdrr_path(data_dir)
    existing = load_mdrr_table(data_dir)
    td = str(record["trade_date"])[:10]
    if not existing.empty and "trade_date" in existing.columns:
        if (existing["trade_date"].astype(str).str[:10] == td).any():
            return False, "ALREADY_PRESENT"
    row = pd.DataFrame([record])
    out = row if existing.empty else pd.concat([existing, row], ignore_index=True)
    out.to_csv(path, index=False)
    return True, "WRITTEN"


def assess_mdrr_completeness(
    *,
    has_board: bool,
    universe_count: int,
    has_mdt0: bool,
    has_fc: bool,
    has_real: bool,
    has_live: bool,
) -> str:
    if not has_board and not has_mdt0:
        return COMPLETENESS_WAITING
    if (
        has_board
        and universe_count == EXPECTED_UNIVERSE_SIZE
        and has_mdt0
        and has_fc
        and has_real
        and has_live
    ):
        return COMPLETENESS_COMPLETE
    return COMPLETENESS_PARTIAL


def build_mdrr_record(
    trade_date: str,
    *,
    ems_path: Path = DEFAULT_EMS,
    md_path: Path = DEFAULT_MDT0,
    prior_mdrr: Optional[pd.DataFrame] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Build Minimum Daily Research Record for one trading session.

    Forward-only fields (foreign flow, ADV, filled VNI tech) stay null until
    collectors exist — never invented.
    """
    trade_date = str(trade_date)[:10]
    if not is_weekday_session(trade_date):
        return None, COMPLETENESS_WAITING

    board = load_board(ems_path, trade_date)
    md = load_market_daily(md_path, trade_date)

    if board.empty and md is None:
        return None, COMPLETENESS_WAITING

    feats: Dict[str, Any] = {}
    if not board.empty:
        feats = build_t0_features_from_board(board)
        # Strip market scores from board if we prefer MDT0 below — keep for now.

    if md is not None:
        for src, dst in (
            ("market_real", "market_real"),
            ("market_live", "market_live"),
            ("market_forecast", "market_forecast"),
            ("market_regime", "market_regime"),
            ("market_regime_note", "market_regime_note"),
            ("breadth_score", "breadth_score"),
            ("vnindex_open", "vnindex_open"),
            ("vnindex_high", "vnindex_high"),
            ("vnindex_low", "vnindex_low"),
            ("vnindex_close", "vnindex_close"),
            ("vnindex_volume", "vnindex_volume"),
            ("vnindex_daily_return_pct", "vnindex_daily_return_pct"),
            ("captured_at", "market_daily_captured_at"),
            ("daily_snapshot_id", "market_daily_snapshot_id"),
        ):
            if src in md and pd.notna(md.get(src)):
                feats[dst] = md.get(src)

    universe_count = int(feats.get("universe_count") or (0 if board.empty else len(board)))
    has_fc = feats.get("market_forecast") is not None and pd.notna(feats.get("market_forecast"))
    has_real = feats.get("market_real") is not None and pd.notna(feats.get("market_real"))
    has_live = feats.get("market_live") is not None and pd.notna(feats.get("market_live"))
    completeness = assess_mdrr_completeness(
        has_board=not board.empty,
        universe_count=universe_count,
        has_mdt0=md is not None,
        has_fc=bool(has_fc),
        has_real=bool(has_real),
        has_live=bool(has_live),
    )

    # FC trajectory deltas from prior MDRR only (no future).
    if prior_mdrr is not None and not prior_mdrr.empty and "market_forecast" in prior_mdrr.columns:
        prior = prior_mdrr[prior_mdrr["trade_date"].astype(str) < trade_date].sort_values("trade_date")
        cur = feats.get("market_forecast")
        for h in (1, 3, 5):
            if len(prior) < h or cur is None or pd.isna(cur):
                feats[f"market_forecast_d{h}"] = None
            else:
                prev = pd.to_numeric(prior.iloc[-h]["market_forecast"], errors="coerce")
                feats[f"market_forecast_d{h}"] = float(cur) - float(prev) if pd.notna(prev) else None
    else:
        for h in (1, 3, 5):
            feats[f"market_forecast_d{h}"] = None

    # Forward-only slots (explicit nulls; registry documents first_collection_date).
    forward_nulls = {
        "foreign_net_flow": None,
        "foreign_buy": None,
        "foreign_sell": None,
        "market_turnover": None,
        "market_adv": None,
        "vnindex_rsi": None,
        "vnindex_macd": None,
        "vnindex_bb_upper": None,
        "vnindex_bb_lower": None,
        "sector_participation_json": None,
    }

    source_hashes = {
        "earning_money_snapshots_sha256": _file_sha256(ems_path),
        "market_daily_t0_sha256": _file_sha256(md_path),
    }

    record: Dict[str, Any] = {
        "trade_date": trade_date,
        "snapshot_asof": feats.get("market_daily_captured_at") or _utc_now_iso(),
        "data_cutoff": trade_date,
        "trading_session_id": f"VN_EQUITY_{trade_date}",
        "schema_version": MDRR_SCHEMA_VERSION,
        "completeness_status": completeness,
        "expected_universe_size": EXPECTED_UNIVERSE_SIZE,
        "universe_count": universe_count,
        "created_at": _utc_now_iso(),
        "source_ems_path": str(ems_path),
        "source_md_path": str(md_path),
        "source_hashes_json": json.dumps(source_hashes, sort_keys=True),
        "camera_coupled": False,
        "outcomes_embedded": False,
        **{k: v for k, v in feats.items() if k not in FORBIDDEN_OUTCOME_COLUMNS},
        **forward_nulls,
    }
    hash_body = {k: v for k, v in record.items() if k != "created_at"}
    record["record_hash"] = _stable_hash(hash_body)
    assert_no_forbidden_outcome_fields(record)
    return record, completeness


def freeze_mdrr_for_date(
    trade_date: str,
    *,
    data_dir: Optional[Path] = None,
    ems_path: Path = DEFAULT_EMS,
    md_path: Path = DEFAULT_MDT0,
) -> Dict[str, Any]:
    trade_date = str(trade_date)[:10]
    prior = load_mdrr_table(data_dir)
    if not prior.empty and (prior["trade_date"].astype(str).str[:10] == trade_date).any():
        row = prior[prior["trade_date"].astype(str).str[:10] == trade_date].iloc[-1]
        return {
            "ok": True,
            "written": False,
            "reason": "ALREADY_PRESENT",
            "trade_date": trade_date,
            "completeness_status": row.get("completeness_status"),
            "record_hash": row.get("record_hash"),
        }
    record, completeness = build_mdrr_record(
        trade_date,
        ems_path=ems_path,
        md_path=md_path,
        prior_mdrr=prior if not prior.empty else None,
    )
    if record is None:
        return {
            "ok": False,
            "written": False,
            "reason": completeness,
            "trade_date": trade_date,
        }
    written, reason = persist_mdrr_record(record, data_dir=data_dir)
    return {
        "ok": True,
        "written": written,
        "reason": reason,
        "trade_date": trade_date,
        "completeness_status": record.get("completeness_status"),
        "record_hash": record.get("record_hash"),
        "universe_count": record.get("universe_count"),
    }


def maybe_write_mdrr_after_market_daily(
    trade_date: str,
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Fail-safe hook — never raises into Market First path."""
    try:
        return freeze_mdrr_for_date(trade_date, data_dir=data_dir)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "written": False, "reason": f"hook_error:{exc}"}


def default_forward_only_registry() -> Dict[str, Any]:
    """Machine-readable registry of forward-only fields (no historical invention)."""
    # first_reliable_collection_date is null until a collector lands values.
    fields = [
        {
            "feature": "foreign_net_flow",
            "first_reliable_collection_date": None,
            "source": "NOT_YET_COLLECTED",
            "pit_status": "FORWARD_ONLY",
            "historical_backfill_availability": False,
            "reconstruction_policy": "DO_NOT_INVENT",
            "notes": "P0 — begin prospective collection; never backfill without evidence",
        },
        {
            "feature": "foreign_buy",
            "first_reliable_collection_date": None,
            "source": "NOT_YET_COLLECTED",
            "pit_status": "FORWARD_ONLY",
            "historical_backfill_availability": False,
            "reconstruction_policy": "DO_NOT_INVENT",
            "notes": "P0",
        },
        {
            "feature": "foreign_sell",
            "first_reliable_collection_date": None,
            "source": "NOT_YET_COLLECTED",
            "pit_status": "FORWARD_ONLY",
            "historical_backfill_availability": False,
            "reconstruction_policy": "DO_NOT_INVENT",
            "notes": "P0",
        },
        {
            "feature": "market_turnover",
            "first_reliable_collection_date": None,
            "source": "NOT_YET_COLLECTED",
            "pit_status": "FORWARD_ONLY",
            "historical_backfill_availability": False,
            "reconstruction_policy": "DO_NOT_INVENT; VNINDEX volume in MDT0 is not a substitute",
            "notes": "P0 total market traded value",
        },
        {
            "feature": "market_adv",
            "first_reliable_collection_date": None,
            "source": "NOT_YET_COLLECTED",
            "pit_status": "FORWARD_ONLY",
            "historical_backfill_availability": False,
            "reconstruction_policy": "DERIVE_LATER_FROM_RAW_TURNOVER_SERIES_ONLY",
            "notes": "P0",
        },
        {
            "feature": "vnindex_rsi",
            "first_reliable_collection_date": None,
            "source": "market_daily_t0 reserved columns (currently empty)",
            "pit_status": "FORWARD_ONLY_UNTIL_FILLED_AT_FREEZE",
            "historical_backfill_availability": False,
            "reconstruction_policy": "FILL_PROSPECTIVELY_OR_DERIVE_FROM_IMMUTABLE_INDEX_OHLCV_IF_SUFFICIENT",
            "notes": "P1",
        },
        {
            "feature": "vnindex_macd",
            "first_reliable_collection_date": None,
            "source": "market_daily_t0 reserved columns (currently empty)",
            "pit_status": "FORWARD_ONLY_UNTIL_FILLED_AT_FREEZE",
            "historical_backfill_availability": False,
            "reconstruction_policy": "SAME_AS_vnindex_rsi",
            "notes": "P1",
        },
        {
            "feature": "sector_participation_json",
            "first_reliable_collection_date": None,
            "source": "optional; sector on freeze/EL, not EMS",
            "pit_status": "FORWARD_ONLY_OR_DERIVE_FROM_FREEZE_SECTOR",
            "historical_backfill_availability": "partial via t0_observation_freeze sector",
            "reconstruction_policy": "MAY_DERIVE_FROM_PIT_FREEZE_WHEN_SECTOR_PRESENT",
            "notes": "P1",
        },
    ]
    return {
        "registry_version": "forward_only_feature_registry_v1",
        "mdrr_schema_version": MDRR_SCHEMA_VERSION,
        "fields": fields,
    }


def write_forward_only_registry(data_dir: Optional[Path] = None) -> Path:
    root = resolve_forecast_data_dir(data_dir)
    path = root / FORWARD_ONLY_REGISTRY_FILE
    path.write_text(json.dumps(default_forward_only_registry(), indent=2), encoding="utf-8")
    return path


def run_mdrr_backfill(
    *,
    data_dir: Optional[Path] = None,
    ems_path: Path = DEFAULT_EMS,
    md_path: Path = DEFAULT_MDT0,
) -> Dict[str, Any]:
    from modules.forecast_research.outcome_maturity import list_board_trading_dates

    dates = list_board_trading_dates(ems_path)
    results = [
        freeze_mdrr_for_date(d, data_dir=data_dir, ems_path=ems_path, md_path=md_path) for d in dates
    ]
    write_forward_only_registry(data_dir)
    status = {
        "schema_version": MDRR_SCHEMA_VERSION,
        "n_dates": len(dates),
        "written": sum(1 for r in results if r.get("written")),
        "results": results,
        "forward_only_registry": str(resolve_forecast_data_dir(data_dir) / FORWARD_ONLY_REGISTRY_FILE),
    }
    (resolve_forecast_data_dir(data_dir) / MDRR_STATUS_FILE).write_text(
        json.dumps(status, indent=2, default=str), encoding="utf-8"
    )
    return status
