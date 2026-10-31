"""Follow-up Watch SHADOW runtime orchestration (flag-gated).

Wires ingest → per-session re-eval (Candidate Guardian / TTL) → camera queue
→ optional as-of outcome maturity. Default OFF via MRBOT_V2_FOLLOWUP_WATCH.

Never enables production BUY. Never mutates ordinary V2 Action result rows.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from modules.live_candidate.calendar import as_vn
from modules.live_candidate_v2_followup.contract import (
    ENV_FOLLOWUP_DIR,
    ENV_FOLLOWUP_WATCH,
    MODE,
    REASON_FLAG_OFF,
    REMOTE_DIR,
    SLICE,
    followup_enabled,
)
from modules.live_candidate_v2_followup.guardian_bridge import guardian_map_from_scan
from modules.live_candidate_v2_followup.measure import (
    mature_buy_ready_outcomes,
    measure_dir,
    record_baseline_action_rows,
)
from modules.live_candidate_v2_followup.registry import (
    RegistryCorruptError,
    load_registry,
    registry_path,
    save_registry,
)
from modules.live_candidate_v2_followup.session import (
    normalize_trading_dates,
    run_followup_session,
)

logger = logging.getLogger(__name__)

ENV_MARKET_REAL = "MRBOT_V2_FOLLOWUP_MARKET_REAL"
ENV_TRADING_DATES = "MRBOT_V2_FOLLOWUP_TRADING_DATES"
ENV_TRADING_DATES_FILE = "MRBOT_V2_FOLLOWUP_TRADING_DATES_FILE"
ENV_SCAN_CSV = "MRBOT_V2_FOLLOWUP_SCAN_CSV"
ENV_PRICE_JSON = "MRBOT_V2_FOLLOWUP_PRICE_JSON"
ENV_VNINDEX_JSON = "MRBOT_V2_FOLLOWUP_VNINDEX_JSON"
CAMERA_QUEUE_NAME = "followup_camera_queue.json"
SESSION_LOCK_NAME = "followup_session_lock.json"


def _dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    raw = os.environ.get(ENV_FOLLOWUP_DIR, "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[2] / REMOTE_DIR


def camera_queue_path(directory: Path | None = None) -> Path:
    return _dir(directory) / CAMERA_QUEUE_NAME


def session_lock_path(directory: Path | None = None) -> Path:
    return _dir(directory) / SESSION_LOCK_NAME


def write_camera_queue(
    rows: Sequence[Mapping[str, Any]],
    *,
    session: str,
    directory: Path | None = None,
) -> Path:
    path = camera_queue_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Strip any stale buy rights before Camera sees the row.
    cleaned: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        row["candidate_is_buy"] = False
        row["alert_eligible"] = False
        row["pxv_implies_buy"] = False
        row.pop("shadow_action", None)
        row.pop("action_state", None)
        row.pop("prior_action_state", None)
        row["v2_followup"] = True
        cleaned.append(row)
    payload = {
        "schema": "live_candidate_v2_followup_camera_queue.v1",
        "mode": MODE,
        "slice": SLICE,
        "session": str(session)[:10],
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "rows": cleaned,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def load_camera_queue_rows(
    *,
    session: str | None = None,
    directory: Path | None = None,
) -> list[dict[str, Any]]:
    path = camera_queue_path(directory)
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("followup camera queue unreadable path=%s err=%s", path, exc)
        return []
    if not isinstance(doc, dict):
        return []
    if session and str(doc.get("session") or "")[:10] != str(session)[:10]:
        logger.info(
            "followup camera queue stale queue_session=%s want=%s",
            doc.get("session"),
            session,
        )
        return []
    rows = doc.get("rows")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for raw in rows:
        if isinstance(raw, Mapping):
            row = dict(raw)
            row["candidate_is_buy"] = False
            row["alert_eligible"] = False
            row["pxv_implies_buy"] = False
            out.append(row)
    return out


def weekday_trading_dates(as_of: str, *, lookback_calendar_days: int = 45) -> tuple[str, ...]:
    """Weekday-only fallback. May include VN holidays — prefer VNINDEX/env list."""
    end = date.fromisoformat(str(as_of)[:10])
    start = end - timedelta(days=max(1, int(lookback_calendar_days)))
    out: list[str] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return tuple(out)


def resolve_trading_dates(
    *,
    session: str,
    explicit: Sequence[str] | None = None,
    now: datetime | None = None,
) -> tuple[str, ...]:
    if explicit:
        return normalize_trading_dates(explicit)
    env_csv = os.environ.get(ENV_TRADING_DATES, "").strip()
    if env_csv:
        return normalize_trading_dates(env_csv.split(","))
    env_file = os.environ.get(ENV_TRADING_DATES_FILE, "").strip()
    if env_file:
        path = Path(env_file)
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    return normalize_trading_dates(raw)
                if isinstance(raw, dict) and isinstance(raw.get("trading_dates"), list):
                    return normalize_trading_dates(raw["trading_dates"])
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("followup trading_dates file unreadable path=%s err=%s", path, exc)
    # Best-effort VNINDEX (may be unavailable offline).
    try:
        from modules.live_candidate_v2_nomination.sweet_brain_b import (
            fetch_vnindex_trading_dates,
        )

        dates = fetch_vnindex_trading_dates(as_vn(now or datetime.now().astimezone()), lookback_days=45)
        if dates:
            return normalize_trading_dates(dates)
    except Exception as exc:  # noqa: BLE001 — research fallback path
        logger.warning("followup VNINDEX trading_dates unavailable err=%s", exc)
    fallback = weekday_trading_dates(session)
    logger.warning(
        "followup using weekday trading_dates fallback n=%s (holidays may be wrong)",
        len(fallback),
    )
    return fallback


def resolve_market_real(
    *,
    explicit: object = None,
    sidecar_rows: Sequence[Mapping[str, Any]] | None = None,
) -> float | None:
    if explicit is not None and str(explicit).strip() != "":
        try:
            return float(explicit)
        except (TypeError, ValueError):
            logger.error("followup invalid explicit market_real=%r", explicit)
    env_raw = os.environ.get(ENV_MARKET_REAL, "").strip()
    if env_raw:
        try:
            return float(env_raw)
        except ValueError:
            logger.error("followup invalid %s=%r", ENV_MARKET_REAL, env_raw)
    vals: list[float] = []
    for row in sidecar_rows or ():
        if not isinstance(row, Mapping):
            continue
        try:
            v = float(row.get("market_real"))
        except (TypeError, ValueError):
            continue
        if v == v:
            vals.append(v)
    if vals:
        vals.sort()
        return vals[len(vals) // 2]
    return None


def load_scan_by_symbol(
    *,
    scan_csv: Path | None = None,
    sidecar_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    path = scan_csv
    if path is None:
        env = os.environ.get(ENV_SCAN_CSV, "").strip()
        path = Path(env) if env else None
    if path is not None and path.exists():
        try:
            import pandas as pd

            frame = pd.read_csv(path)
            if "symbol" in frame.columns:
                for _, row in frame.iterrows():
                    sym = str(row.get("symbol") or "").strip().upper()
                    if sym:
                        out[sym] = dict(row)
        except Exception as exc:  # noqa: BLE001
            logger.error("followup scan_csv unreadable path=%s err=%s", path, exc)
    for raw in sidecar_rows or ():
        if not isinstance(raw, Mapping):
            continue
        sym = str(raw.get("symbol") or "").strip().upper()
        if not sym or sym in out:
            continue
        # Sidecar proxy scan — never carries buy rights into Guardian.
        out[sym] = {
            "symbol": sym,
            "group": raw.get("group") or raw.get("setup") or "",
            "setup": raw.get("setup") or raw.get("group") or "",
            "price": raw.get("price") or raw.get("price_at_first_seen"),
            "ema9": raw.get("ema9") or raw.get("ema9_at_first_seen"),
            "ma20": raw.get("ma20") or raw.get("sma20"),
            "breakout_ref": raw.get("breakout_ref") or raw.get("breakout_ref_at_first_seen"),
            "rs5": raw.get("rs5") or raw.get("RS5"),
            "rs10": raw.get("rs10") or raw.get("RS10"),
            "obv_status": raw.get("obv_status") or "",
            "volume_ratio": raw.get("volume_ratio") or raw.get("vol_ratio"),
        }
    return out


def load_price_maps() -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    sym: dict[str, dict[str, float]] = {}
    vni: dict[str, float] = {}
    price_path = os.environ.get(ENV_PRICE_JSON, "").strip()
    if price_path:
        try:
            raw = json.loads(Path(price_path).read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, dict):
                        sym[str(k).upper()] = {
                            str(d)[:10]: float(px)
                            for d, px in v.items()
                            if str(d)[:10] and float(px) == float(px)
                        }
        except Exception as exc:  # noqa: BLE001
            logger.error("followup price json unreadable path=%s err=%s", price_path, exc)
    vni_path = os.environ.get(ENV_VNINDEX_JSON, "").strip()
    if vni_path:
        try:
            raw = json.loads(Path(vni_path).read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                vni = {
                    str(d)[:10]: float(px)
                    for d, px in raw.items()
                    if str(d)[:10] and float(px) == float(px)
                }
        except Exception as exc:  # noqa: BLE001
            logger.error("followup vnindex json unreadable path=%s err=%s", vni_path, exc)
    return sym, vni


def _session_already_complete(session: str, directory: Path | None) -> bool:
    path = session_lock_path(directory)
    if not path.exists():
        return False
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(isinstance(doc, dict) and str(doc.get("session") or "")[:10] == str(session)[:10] and doc.get("ok"))


def _mark_session_complete(session: str, directory: Path | None, summary: Mapping[str, Any]) -> None:
    path = session_lock_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session": str(session)[:10],
        "ok": True,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "summary": dict(summary),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def run_followup_runtime_cycle(
    *,
    session: str,
    observed_at: datetime,
    sidecar_rows: Sequence[Mapping[str, Any]] | None = None,
    action_baseline_rows: Sequence[Mapping[str, Any]] | None = None,
    market_real: object = None,
    trading_dates: Sequence[str] | None = None,
    scan_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
    directory: Path | None = None,
    force: bool = False,
    allow_retry: bool = False,
) -> dict[str, Any]:
    """One SHADOW runtime tick: baseline + ingest + re-eval + camera queue + mature.

    Idempotent per session unless ``allow_retry`` / ``force``.
    """
    sess = str(session)[:10]
    # ``force`` only bypasses the feature flag (tests / explicit ops).
    # Idempotency is controlled solely by ``allow_retry``.
    if not force and not followup_enabled():
        return {
            "ok": True,
            "enabled": False,
            "reason": REASON_FLAG_OFF,
            "session": sess,
            "camera_rows": [],
        }

    if not allow_retry and _session_already_complete(sess, directory):
        camera_rows = load_camera_queue_rows(session=sess, directory=directory)
        logger.info(
            "followup runtime skip idempotent session=%s camera_rows=%s",
            sess,
            len(camera_rows),
        )
        return {
            "ok": True,
            "enabled": True,
            "reason": "SESSION_ALREADY_COMPLETE",
            "session": sess,
            "idempotent_skip": True,
            "camera_rows": camera_rows,
            "ingested": [],
            "results": [],
        }

    try:
        dates = resolve_trading_dates(session=sess, explicit=trading_dates, now=observed_at)
        mr = resolve_market_real(explicit=market_real, sidecar_rows=sidecar_rows)
        scan_map = (
            {str(k).upper(): dict(v) for k, v in scan_by_symbol.items()}
            if scan_by_symbol
            else load_scan_by_symbol(sidecar_rows=sidecar_rows)
        )
        guard_map: dict[str, str] = {}
        try:
            import pandas as pd

            if scan_map:
                guard_map = guardian_map_from_scan(pd.DataFrame(list(scan_map.values())))
        except Exception as exc:  # noqa: BLE001
            logger.warning("followup guardian map failed err=%s", exc)

        if action_baseline_rows:
            record_baseline_action_rows(
                session=sess,
                action_rows=action_baseline_rows,
                directory=directory,
            )

        result = run_followup_session(
            session=sess,
            observed_at=observed_at,
            market_real=mr,
            trading_dates=dates,
            sidecar_rows=sidecar_rows,
            scan_by_symbol=scan_map,
            guardian_by_symbol=guard_map,
            directory=directory,
            force=True,  # flag already checked above
        )
        camera_rows = list(result.get("camera_rows") or [])
        write_camera_queue(camera_rows, session=sess, directory=directory)

        # As-of maturity: only sessions <= current session (no future peek).
        sym_px, vni_px = load_price_maps()
        matured = {"ok": True, "matured": 0, "skipped_reason": "NO_PRICE_MAPS"}
        if sym_px:
            asof_dates = [d for d in dates if d <= sess]
            matured = mature_buy_ready_outcomes(
                directory=directory,
                symbol_session_prices=sym_px,
                vnindex_session_prices=vni_px,
                trading_dates=asof_dates,
                as_of_session=sess,
            )

        summary = {
            "ingested": list(result.get("ingested") or []),
            "n_results": len(result.get("results") or []),
            "n_camera_rows": len(camera_rows),
            "n_matured": matured.get("matured"),
            "market_real": mr,
            "n_trading_dates": len(dates),
            "registry_path": str(registry_path(directory)),
        }
        _mark_session_complete(sess, directory, summary)
        logger.info(
            "followup runtime ok session=%s ingested=%s results=%s camera=%s matured=%s",
            sess,
            len(summary["ingested"]),
            summary["n_results"],
            summary["n_camera_rows"],
            summary["n_matured"],
        )
        return {
            "ok": True,
            "enabled": True,
            "reason": "OK",
            "session": sess,
            "camera_rows": camera_rows,
            "ingested": summary["ingested"],
            "results": list(result.get("results") or []),
            "matured": matured,
            "market_real": mr,
            "trading_dates": list(dates),
            "registry_path": summary["registry_path"],
            "followup_dir": str(_dir(directory)),
        }
    except RegistryCorruptError as exc:
        logger.error("followup registry corrupt session=%s err=%s", sess, exc)
        return {
            "ok": False,
            "enabled": True,
            "reason": "REGISTRY_CORRUPT",
            "session": sess,
            "error": str(exc),
            "camera_rows": [],
        }
    except Exception as exc:  # noqa: BLE001 — isolate SHADOW from production observe
        logger.exception("followup runtime failed session=%s err=%s", sess, exc)
        return {
            "ok": False,
            "enabled": True,
            "reason": "RUNTIME_ERROR",
            "session": sess,
            "error": str(exc),
            "camera_rows": [],
        }


def enrich_rows_with_followup_camera(
    sidecar_rows: Sequence[Mapping[str, Any]] | None,
    *,
    now: datetime,
    session: str,
    directory: Path | None = None,
) -> dict[str, Any]:
    """Flag-gated Camera merge helper used by LiveShadowFeed."""
    from modules.live_candidate_v2_followup.camera_bridge import (
        apply_followup_to_universe,
    )

    if not followup_enabled():
        from modules.live_candidate_v2_action.live_universe import select_actionable_v2

        universe = select_actionable_v2(sidecar_rows, now=now)
        return {
            "enabled": False,
            "reason": REASON_FLAG_OFF,
            "universe": universe,
            "followup_added": [],
        }
    camera_rows = load_camera_queue_rows(session=session, directory=directory)
    return apply_followup_to_universe(
        sidecar_rows,
        camera_rows,
        now=now,
    )


__all__ = [
    "ENV_FOLLOWUP_WATCH",
    "ENV_MARKET_REAL",
    "ENV_TRADING_DATES",
    "camera_queue_path",
    "enrich_rows_with_followup_camera",
    "load_camera_queue_rows",
    "load_price_maps",
    "load_scan_by_symbol",
    "resolve_market_real",
    "resolve_trading_dates",
    "run_followup_runtime_cycle",
    "weekday_trading_dates",
    "write_camera_queue",
]
