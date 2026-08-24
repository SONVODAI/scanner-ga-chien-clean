"""
Historical Market Core recovery — separate from Forecast T0 contract.

Recovers genuine FC / REAL / market context into historical_market_core.csv.
Never upgrades incomplete history to COMPLETE Forecast T0 equivalence.
Never copies t*_return / future labels into feature fields.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from modules.forecast_research.contract import (
    EXPECTED_UNIVERSE_SIZE,
    FORBIDDEN_OUTCOME_COLUMNS,
    GROUPS,
    HISTORICAL_CORE_FILE,
    HISTORICAL_CORE_SCHEMA_VERSION,
    HISTORICAL_CORE_STATUS_FILE,
    QUALITY_LEAKAGE_RISK_SOURCE,
    QUALITY_NOT_PROVABLY_PIT_SAFE,
    QUALITY_PIT_RECONSTRUCTABLE,
    QUALITY_PIT_SAFE_COMPLETE,
    QUALITY_PIT_SAFE_PARTIAL,
    ROOT_PH_FC_RULE,
)
from modules.forecast_research.t0_builder import (
    DEFAULT_EMS,
    DEFAULT_MDT0,
    _calc_fc,
    build_t0_features_from_board,
    load_board,
    load_market_daily,
)
from modules.forecast_research.t0_persistence import resolve_forecast_data_dir

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT_PH = REPO_ROOT / "pattern_history.csv"
DEFAULT_BUY_ELITE = REPO_ROOT / "buy_elite_learning_history.csv"
DEFAULT_EL_PH = REPO_ROOT / "data" / "earning_learning" / "pattern_history.csv"
DEFAULT_FREEZE = REPO_ROOT / "data" / "earning_learning" / "t0_observation_freeze.csv"


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


def is_weekday_session(trade_date: str) -> bool:
    try:
        return datetime.strptime(str(trade_date)[:10], "%Y-%m-%d").weekday() < 5
    except ValueError:
        return False


def assert_no_forbidden_outcome_fields(record: Dict[str, Any]) -> None:
    bad = [k for k in record if k in FORBIDDEN_OUTCOME_COLUMNS or str(k).startswith("label_")]
    if bad:
        raise ValueError(f"forbidden outcome fields in historical/MDRR record: {bad}")


def _parse_time_key(time_val: Any) -> Optional[str]:
    if time_val is None or (isinstance(time_val, float) and np.isnan(time_val)):
        return None
    s = str(time_val).strip()
    if not s or s.lower() in {"nan", "none", "nat"}:
        return None
    # Accept HH:MM:SS or HH:MM
    parts = s.split(":")
    if len(parts) < 2:
        return None
    try:
        hh, mm = int(parts[0]), int(parts[1])
        ss = int(float(parts[2])) if len(parts) > 2 else 0
        return f"{hh:02d}:{mm:02d}:{ss:02d}"
    except (ValueError, TypeError):
        return None


def _time_ge_close(time_key: str, close_hhmm: str = "15:00:00") -> bool:
    return time_key >= close_hhmm


def resolve_root_ph_fc(day_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Resolve FC from root pattern_history for one date.

    Rule ROOT_PH_FC_RULE: last scan with time >= 15:00.
    If no post-close scan or unparseable times with multiple FC → ambiguous.
    """
    fc = pd.to_numeric(day_df["market_forecast"], errors="coerce")
    real = pd.to_numeric(day_df["market_real"], errors="coerce") if "market_real" in day_df.columns else pd.Series(dtype=float)
    times = day_df["time"].map(_parse_time_key) if "time" in day_df.columns else pd.Series([None] * len(day_df))
    candidates = sorted({float(x) for x in fc.dropna().unique().tolist()})
    out: Dict[str, Any] = {
        "fc_candidates": candidates,
        "fc_nunique": len(candidates),
        "fc_ambiguous": False,
        "fc": None,
        "real": float(real.mode().iloc[0]) if real.notna().any() else None,
        "snapshot_asof_time": None,
        "reconstruction_method": None,
        "source_carries_leakage_columns": True,
    }
    if not candidates:
        out["fc_ambiguous"] = True
        return out
    if len(candidates) == 1:
        out["fc"] = candidates[0]
        # still prefer last post-close time as asof if present
        post = [(t, i) for i, t in enumerate(times) if t and _time_ge_close(t)]
        if post:
            t_last = max(post, key=lambda x: x[0])[0]
            out["snapshot_asof_time"] = t_last
        out["reconstruction_method"] = "root_ph_unique_fc"
        return out

    post_idx = [i for i, t in enumerate(times) if t and _time_ge_close(t)]
    if not post_idx:
        out["fc_ambiguous"] = True
        out["reconstruction_method"] = "root_ph_multi_fc_no_post_close"
        return out
    # last post-close by time string
    best_i = max(post_idx, key=lambda i: times.iloc[i])
    best_t = times.iloc[best_i]
    same_t = day_df.loc[times == best_t]
    fc_at = pd.to_numeric(same_t["market_forecast"], errors="coerce").dropna().unique()
    if len(fc_at) != 1:
        out["fc_ambiguous"] = True
        out["reconstruction_method"] = "root_ph_multi_fc_at_last_post_close"
        return out
    out["fc"] = float(fc_at[0])
    out["snapshot_asof_time"] = best_t
    out["reconstruction_method"] = ROOT_PH_FC_RULE
    return out


def _safe_mode(series: pd.Series) -> Optional[float]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return None
    return float(s.mode().iloc[0])


def _group_counts_from_board(board: pd.DataFrame) -> Dict[str, Any]:
    feats: Dict[str, Any] = {}
    n = len(board)
    feats["universe_count"] = int(n)
    if n == 0 or "group" not in board.columns:
        return feats
    for gr in GROUPS:
        cnt = int((board["group"] == gr).sum())
        feats[f"cnt_{gr}"] = cnt
        feats[f"share_{gr}"] = (cnt / n) if n else None
    return feats


def _breadth_from_board(board: pd.DataFrame) -> Dict[str, Any]:
    if board.empty:
        return {}
    # Reuse T0 feature builder but strip anything forbidden (none expected).
    feats = build_t0_features_from_board(board)
    keep = {
        k: v
        for k, v in feats.items()
        if k
        in {
            "universe_count",
            "rsi40_share",
            "rsi50_share",
            "rsi60_share",
            "obv_green_share",
            "slope_pos_share",
            "near_low20_share",
            "near_low60_share",
            "near_high20_share",
            "lead_conc_top10",
            "mean_rs5",
            "mean_rs10",
        }
        or k.startswith("cnt_")
        or k.startswith("share_")
    }
    return keep


def historical_core_path(data_dir: Optional[Path] = None) -> Path:
    return resolve_forecast_data_dir(data_dir) / HISTORICAL_CORE_FILE


def load_historical_core(data_dir: Optional[Path] = None) -> pd.DataFrame:
    path = historical_core_path(data_dir)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def persist_historical_record(
    record: Dict[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    """First-write-wins by trade_date. Deterministic; no silent mutation."""
    assert_no_forbidden_outcome_fields(record)
    path = historical_core_path(data_dir)
    existing = load_historical_core(data_dir)
    td = str(record["trade_date"])[:10]
    if not existing.empty and "trade_date" in existing.columns:
        if (existing["trade_date"].astype(str).str[:10] == td).any():
            return False, "ALREADY_PRESENT"
    row = pd.DataFrame([record])
    out = row if existing.empty else pd.concat([existing, row], ignore_index=True)
    out.to_csv(path, index=False)
    return True, "WRITTEN"


def collect_candidate_dates(
    *,
    root_ph: Path = DEFAULT_ROOT_PH,
    buy_elite: Path = DEFAULT_BUY_ELITE,
    el_ph: Path = DEFAULT_EL_PH,
    ems: Path = DEFAULT_EMS,
    mdt0: Path = DEFAULT_MDT0,
) -> Dict[str, Any]:
    raw_calendar: set = set()
    sources: Dict[str, List[str]] = {}

    def add(name: str, dates: Sequence[str]) -> None:
        sources[name] = sorted({str(d)[:10] for d in dates})
        raw_calendar.update(sources[name])

    if root_ph.exists():
        df = pd.read_csv(root_ph, usecols=["date"], low_memory=False)
        add("root_pattern_history", df["date"].astype(str).str[:10].tolist())
    if buy_elite.exists():
        df = pd.read_csv(buy_elite, usecols=["date"], low_memory=False)
        add("buy_elite_learning_history", df["date"].astype(str).str[:10].tolist())
    if el_ph.exists():
        df = pd.read_csv(el_ph, usecols=["trade_date"], low_memory=False)
        add("el_pattern_history", df["trade_date"].astype(str).str[:10].tolist())
    if ems.exists():
        df = pd.read_csv(ems, usecols=["snapshot_date"], low_memory=False)
        add("earning_money_snapshots", df["snapshot_date"].astype(str).str[:10].tolist())
    if mdt0.exists():
        df = pd.read_csv(mdt0, usecols=["trade_date"], low_memory=False)
        add("market_daily_t0", df["trade_date"].astype(str).str[:10].tolist())

    raw = sorted(raw_calendar)
    trading = [d for d in raw if is_weekday_session(d)]
    excluded = [d for d in raw if not is_weekday_session(d)]
    return {
        "raw_calendar_dates": raw,
        "trading_session_dates": trading,
        "excluded_non_session_dates": excluded,
        "sources": sources,
    }


def build_historical_record_for_date(
    trade_date: str,
    *,
    root_ph: Path = DEFAULT_ROOT_PH,
    buy_elite: Path = DEFAULT_BUY_ELITE,
    el_ph: Path = DEFAULT_EL_PH,
    ems: Path = DEFAULT_EMS,
    mdt0: Path = DEFAULT_MDT0,
    freeze: Path = DEFAULT_FREEZE,
) -> Optional[Dict[str, Any]]:
    """Build one historical market-core row. Returns None for non-sessions."""
    trade_date = str(trade_date)[:10]
    if not is_weekday_session(trade_date):
        return None

    md = load_market_daily(mdt0, trade_date)
    board = load_board(ems, trade_date)
    freeze_board = load_board(freeze, trade_date) if freeze.exists() and freeze.suffix == ".csv" else pd.DataFrame()
    # freeze uses trade_date not snapshot_date
    if freeze.exists() and freeze_board.empty:
        try:
            fr = pd.read_csv(freeze, low_memory=False)
            if "trade_date" in fr.columns:
                freeze_board = fr[fr["trade_date"].astype(str).str[:10] == trade_date].copy()
        except Exception:  # noqa: BLE001
            freeze_board = pd.DataFrame()

    el_day = pd.DataFrame()
    if el_ph.exists():
        try:
            el = pd.read_csv(el_ph, low_memory=False)
            if "trade_date" in el.columns:
                el_day = el[el["trade_date"].astype(str).str[:10] == trade_date].copy()
        except Exception:  # noqa: BLE001
            el_day = pd.DataFrame()

    root_day = pd.DataFrame()
    if root_ph.exists():
        try:
            ph = pd.read_csv(root_ph, low_memory=False)
            if "date" in ph.columns:
                root_day = ph[ph["date"].astype(str).str[:10] == trade_date].copy()
        except Exception:  # noqa: BLE001
            root_day = pd.DataFrame()

    be_day = pd.DataFrame()
    if buy_elite.exists():
        try:
            be = pd.read_csv(buy_elite, low_memory=False)
            if "date" in be.columns:
                be_day = be[be["date"].astype(str).str[:10] == trade_date].copy()
        except Exception:  # noqa: BLE001
            be_day = pd.DataFrame()

    # --- Primary quality path ---
    fc = None
    real = None
    live = None
    regime = None
    phase = None
    breadth_score = None
    universe_count = None
    quality = QUALITY_NOT_PROVABLY_PIT_SAFE
    reconstruction_method = "none"
    primary_source = None
    source_files: List[str] = []
    fc_ambiguous = False
    fc_candidates: List[float] = []
    leakage_source = False
    snapshot_asof = None
    extras: Dict[str, Any] = {}

    if md is not None:
        primary_source = "market_daily_t0"
        source_files.append(str(mdt0))
        fc = float(md["market_forecast"]) if pd.notna(md.get("market_forecast")) else None
        real = float(md["market_real"]) if pd.notna(md.get("market_real")) else None
        live = float(md["market_live"]) if pd.notna(md.get("market_live")) else None
        regime = md.get("market_regime")
        breadth_score = md.get("breadth_score")
        snapshot_asof = md.get("captured_at")
        reconstruction_method = "canonical_mdt0_copy"
        for k in (
            "vnindex_open",
            "vnindex_high",
            "vnindex_low",
            "vnindex_close",
            "vnindex_volume",
        ):
            if k in md and pd.notna(md.get(k)):
                extras[k] = md.get(k)
        board_for_u = freeze_board if not freeze_board.empty else board
        if not board_for_u.empty:
            extras.update(_breadth_from_board(board_for_u))
            universe_count = int(extras.get("universe_count") or len(board_for_u))
            source_files.append(str(freeze if not freeze_board.empty else ems))
        if (
            fc is not None
            and real is not None
            and live is not None
            and universe_count == EXPECTED_UNIVERSE_SIZE
        ):
            quality = QUALITY_PIT_SAFE_COMPLETE
        else:
            quality = QUALITY_PIT_SAFE_PARTIAL

    elif not el_day.empty and pd.to_numeric(el_day.get("market_forecast"), errors="coerce").notna().any():
        primary_source = "el_pattern_history"
        source_files.append(str(el_ph))
        fc_s = pd.to_numeric(el_day["market_forecast"], errors="coerce")
        candidates = sorted({float(x) for x in fc_s.dropna().unique()})
        fc_candidates = candidates
        if len(candidates) == 1:
            fc = candidates[0]
            reconstruction_method = "el_ph_unique_fc"
            quality = QUALITY_PIT_RECONSTRUCTABLE
            real = _safe_mode(el_day["market_real"]) if "market_real" in el_day.columns else None
            live = _safe_mode(el_day["market_live"]) if "market_live" in el_day.columns else None
            universe_count = int(el_day["symbol"].nunique()) if "symbol" in el_day.columns else None
            if "group" in el_day.columns:
                last = el_day.drop_duplicates("symbol", keep="last")
                extras.update(_breadth_from_board(last))
        elif not board.empty:
            # Prefer unambiguous EMS board reconstruction over ambiguous EL multi-FC.
            primary_source = "earning_money_snapshots"
            source_files.append(str(ems))
            persisted = pd.to_numeric(board.get("market_forecast"), errors="coerce")
            if persisted is not None and persisted.notna().any():
                fc = float(persisted.dropna().iloc[-1])
                reconstruction_method = "ems_persisted_fc_el_ambiguous_fallback"
            else:
                fc = float(_calc_fc(board))
                reconstruction_method = "ems_group_composition_recon_fc_el_ambiguous_fallback"
            fc_ambiguous = False
            fc_candidates = candidates  # retain EL ambiguity evidence
            real = None
            live = None
            if "market_real" in board.columns and not pd.to_numeric(board["market_real"], errors="coerce").isna().all():
                real = _safe_mode(board["market_real"])
            if "market_live" in board.columns and not pd.to_numeric(board["market_live"], errors="coerce").isna().all():
                live = _safe_mode(board["market_live"])
            extras.update(_breadth_from_board(board))
            universe_count = int(extras.get("universe_count") or len(board))
            quality = QUALITY_PIT_RECONSTRUCTABLE
        else:
            fc_ambiguous = True
            fc = None
            reconstruction_method = "el_ph_multi_fc_ambiguous"
            quality = QUALITY_NOT_PROVABLY_PIT_SAFE
            real = _safe_mode(el_day["market_real"]) if "market_real" in el_day.columns else None
            live = _safe_mode(el_day["market_live"]) if "market_live" in el_day.columns else None
            universe_count = int(el_day["symbol"].nunique()) if "symbol" in el_day.columns else None
            if "group" in el_day.columns:
                last = el_day.drop_duplicates("symbol", keep="last")
                extras.update(_breadth_from_board(last))

    elif not board.empty:
        primary_source = "earning_money_snapshots"
        source_files.append(str(ems))
        # EMS market_forecast is historically null — reconstruct from groups only.
        persisted = pd.to_numeric(board.get("market_forecast"), errors="coerce")
        if persisted is not None and persisted.notna().any():
            fc = float(persisted.dropna().iloc[-1])
            reconstruction_method = "ems_persisted_fc"
        else:
            fc = float(_calc_fc(board))
            reconstruction_method = "ems_group_composition_recon_fc"
        real = _safe_mode(board["market_real"]) if "market_real" in board.columns else None
        live = _safe_mode(board["market_live"]) if "market_live" in board.columns else None
        if real is not None and (isinstance(real, float) and np.isnan(real)):
            real = None
        if live is not None and (isinstance(live, float) and np.isnan(live)):
            live = None
        # Treat all-null score columns as missing
        if "market_real" in board.columns and pd.to_numeric(board["market_real"], errors="coerce").isna().all():
            real = None
        if "market_live" in board.columns and pd.to_numeric(board["market_live"], errors="coerce").isna().all():
            live = None
        extras.update(_breadth_from_board(board))
        universe_count = int(extras.get("universe_count") or len(board))
        quality = QUALITY_PIT_RECONSTRUCTABLE

    elif not root_day.empty:
        primary_source = "root_pattern_history"
        source_files.append(str(root_ph))
        leakage_source = True
        resolved = resolve_root_ph_fc(root_day)
        fc_candidates = resolved["fc_candidates"]
        fc_ambiguous = bool(resolved["fc_ambiguous"])
        fc = resolved["fc"]
        real = resolved["real"]
        reconstruction_method = resolved["reconstruction_method"]
        snapshot_asof = (
            f"{trade_date}T{resolved['snapshot_asof_time']}" if resolved.get("snapshot_asof_time") else None
        )
        universe_count = int(root_day["symbol"].nunique()) if "symbol" in root_day.columns else None
        if "market_regime" in root_day.columns:
            regime = root_day["market_regime"].dropna().astype(str).mode().iloc[0] if root_day["market_regime"].notna().any() else None
        if "market_phase" in root_day.columns:
            phase = root_day["market_phase"].dropna().astype(str).mode().iloc[0] if root_day["market_phase"].notna().any() else None
        if "breadth_score" in root_day.columns:
            breadth_score = _safe_mode(root_day["breadth_score"])
        # T0-safe stock features from last post-close subset if available
        if "group" in root_day.columns:
            if resolved.get("snapshot_asof_time") and "time" in root_day.columns:
                tkeys = root_day["time"].map(_parse_time_key)
                sub = root_day.loc[tkeys == resolved["snapshot_asof_time"]].drop_duplicates("symbol", keep="last")
            else:
                sub = root_day.drop_duplicates("symbol", keep="last")
            extras.update(_group_counts_from_board(sub))
        if fc_ambiguous or fc is None:
            quality = QUALITY_NOT_PROVABLY_PIT_SAFE
        else:
            # Source file carries leakage columns — retain that label even when FC resolved.
            quality = QUALITY_LEAKAGE_RISK_SOURCE

    elif not be_day.empty:
        primary_source = "buy_elite_learning_history"
        source_files.append(str(buy_elite))
        fc_s = pd.to_numeric(be_day["market_forecast"], errors="coerce")
        candidates = sorted({float(x) for x in fc_s.dropna().unique()})
        fc_candidates = candidates
        if len(candidates) == 1:
            fc = candidates[0]
        else:
            # try last time
            if "time" in be_day.columns:
                tkeys = be_day["time"].map(_parse_time_key)
                if tkeys.notna().any():
                    best_t = tkeys.dropna().max()
                    sub = be_day.loc[tkeys == best_t]
                    fc_at = pd.to_numeric(sub["market_forecast"], errors="coerce").dropna().unique()
                    if len(fc_at) == 1:
                        fc = float(fc_at[0])
                        snapshot_asof = f"{trade_date}T{best_t}"
                        reconstruction_method = "buy_elite_last_time_unique_fc"
                    else:
                        fc_ambiguous = True
                        fc = None
                        reconstruction_method = "buy_elite_multi_fc_ambiguous"
                else:
                    fc_ambiguous = True
                    fc = None
                    reconstruction_method = "buy_elite_multi_fc_no_time"
            else:
                fc_ambiguous = True
                fc = None
                reconstruction_method = "buy_elite_multi_fc_no_time"
        if reconstruction_method == "none":
            reconstruction_method = "buy_elite_unique_fc"
        real = _safe_mode(be_day["market_real"]) if "market_real" in be_day.columns else None
        universe_count = int(be_day["symbol"].nunique()) if "symbol" in be_day.columns else None
        if "regime" in be_day.columns and be_day["regime"].notna().any():
            regime = str(be_day["regime"].dropna().astype(str).mode().iloc[0])
        quality = QUALITY_NOT_PROVABLY_PIT_SAFE
    else:
        return None

    body = {
        "trade_date": trade_date,
        "snapshot_asof": snapshot_asof,
        "data_cutoff": trade_date,
        "fc": fc,
        "market_real": real,
        "market_live": live,
        "market_regime": regime,
        "market_phase": phase,
        "breadth_score": breadth_score,
        "universe_count": universe_count,
        "expected_universe_size": EXPECTED_UNIVERSE_SIZE,
        "quality_tier": quality,
        "fc_ambiguous": bool(fc_ambiguous),
        "fc_candidates_json": json.dumps(fc_candidates, sort_keys=True),
        "reconstruction_method": reconstruction_method,
        "primary_source": primary_source,
        "source_files_json": json.dumps(sorted(set(source_files)), sort_keys=True),
        "source_hashes_json": json.dumps(
            {str(p): _file_sha256(Path(p)) for p in sorted(set(source_files))},
            sort_keys=True,
        ),
        "source_carries_leakage_columns": bool(leakage_source),
        "schema_version": HISTORICAL_CORE_SCHEMA_VERSION,
        "created_at": _utc_now_iso(),
        **extras,
    }
    # feature hash excludes created_at
    hash_body = {k: v for k, v in body.items() if k != "created_at"}
    body["record_hash"] = _stable_hash(hash_body)
    assert_no_forbidden_outcome_fields(body)
    return body


def recover_all_historical(
    *,
    data_dir: Optional[Path] = None,
    dates: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    catalog = collect_candidate_dates()
    target = list(dates) if dates is not None else catalog["trading_session_dates"]
    written = 0
    skipped = 0
    ambiguous = 0
    excluded = []
    results = []
    for d in sorted({str(x)[:10] for x in target}):
        if not is_weekday_session(d):
            excluded.append({"trade_date": d, "reason": "non_trading_weekday_or_weekend"})
            skipped += 1
            continue
        rec = build_historical_record_for_date(d)
        if rec is None:
            skipped += 1
            results.append({"trade_date": d, "written": False, "reason": "no_evidence"})
            continue
        ok, reason = persist_historical_record(rec, data_dir=data_dir)
        if rec.get("fc_ambiguous"):
            ambiguous += 1
        results.append(
            {
                "trade_date": d,
                "written": ok,
                "reason": reason,
                "quality_tier": rec.get("quality_tier"),
                "fc": rec.get("fc"),
                "fc_ambiguous": rec.get("fc_ambiguous"),
                "primary_source": rec.get("primary_source"),
                "record_hash": rec.get("record_hash"),
            }
        )
        if ok:
            written += 1
        else:
            skipped += 1

    table = load_historical_core(data_dir)
    summary = {
        "ok": True,
        "schema_version": HISTORICAL_CORE_SCHEMA_VERSION,
        "written": written,
        "skipped": skipped,
        "ambiguous_fc_dates": ambiguous,
        "n_rows": int(len(table)),
        "earliest": str(table["trade_date"].min()) if not table.empty else None,
        "latest": str(table["trade_date"].max()) if not table.empty else None,
        "quality_tier_counts": (
            table["quality_tier"].value_counts().to_dict() if not table.empty else {}
        ),
        "n_with_fc": int(pd.to_numeric(table["fc"], errors="coerce").notna().sum()) if not table.empty else 0,
        "n_with_real": int(pd.to_numeric(table["market_real"], errors="coerce").notna().sum()) if not table.empty else 0,
        "n_with_live": int(pd.to_numeric(table["market_live"], errors="coerce").notna().sum()) if not table.empty else 0,
        "catalog": catalog,
        "excluded": excluded,
        "results": results,
    }
    status_path = resolve_forecast_data_dir(data_dir) / HISTORICAL_CORE_STATUS_FILE
    status_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary
