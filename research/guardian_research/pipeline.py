"""Post-close capture from the scan frame the page already computed.

This module does not download prices, call a market-data API, or read holdings.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

from research.guardian_research.contract import SCAN_COLUMNS
from research.guardian_research.indicators import finite_number
from research.guardian_research.snapshot import (
    SnapshotExists,
    _digest,
    build_snapshot,
    label_observation_origin,
    load_prior_snapshots,
    read_snapshot,
    write_snapshot,
)
from research.guardian_research.universe import load_tracked_symbols

POST_CLOSE = time(15, 10)
CANONICAL_CLOSE = time(18, 0)
SCAN_PROVENANCE = "production_scan.price"
SCAN_QUALITY = "production_scan_row"
SCAN_SOURCE = "production_scan"
MARKET_PROVENANCE = "production_scan.calc_market_real"


def canonical_close_verified(now: datetime, session: str) -> tuple[bool, str]:
    """True in the same window the unattended close scan is allowed to run."""
    from modules.intraday_execution_boundary import as_vn

    local = as_vn(now)
    if local.weekday() >= 5:
        return False, "NOT_A_WEEKDAY_SESSION"
    if local.strftime("%Y-%m-%d") != session:
        return False, "CLOCK_SESSION_MISMATCH"
    if local.timetz().replace(tzinfo=None) < CANONICAL_CLOSE:
        return False, "BEFORE_CANONICAL_WINDOW"
    return True, "ok"


def capture_from_close_payload(
    payload: dict,
    *,
    now: datetime,
    root: Path,
    symbols: tuple[str, ...] | None = None,
) -> dict:
    """Seal from the close-scan frame. A scan that raised symbol errors does not seal."""
    if not isinstance(payload, dict):
        return {"status": "refused", "reason": "SCAN_ABSENT", "path": None, "document": None}
    session = str(payload.get("trade_date") or "")
    if payload.get("ok") is not True or payload.get("source") != "close_scan":
        return {"status": "refused", "reason": "CLOSE_SCAN_NOT_READY", "path": None, "document": None}
    witness_reason = _witness_reason(payload)
    if witness_reason:
        return {"status": "refused", "reason": witness_reason, "path": None, "document": None}
    observed_at, timing_reason = _observation_clock(payload, session, now)
    if timing_reason:
        return {"status": "refused", "reason": timing_reason, "path": None, "document": None}
    coverage = payload.get("scan_coverage")
    if not isinstance(coverage, dict):
        return {"status": "refused", "reason": "SCAN_COVERAGE_ABSENT", "path": None, "document": None}
    tracked = tuple(symbols) if symbols is not None else load_tracked_symbols()
    requested = [str(symbol).strip().upper() for symbol in coverage.get("requested") or []]
    if len(requested) != len(set(requested)) or set(requested) != set(tracked):
        return {"status": "refused", "reason": "UNIVERSE_INCOMPLETE", "path": None, "document": None}
    errors = [str(symbol).strip().upper() for symbol in coverage.get("errors") or [] if str(symbol).strip()]
    if errors:
        return {"status": "refused", "reason": "PARTIAL_SCAN", "path": None, "document": None}
    remote, remote_state = read_remote_snapshot(root, session)
    if remote_state == "unverified":
        return {"status": "refused", "reason": "REMOTE_UNVERIFIED", "path": None, "document": None}
    preview = capture_post_close(
        payload.get("scan_df"),
        now=now,
        session=session,
        root=root,
        market_real=payload.get("market_real"),
        symbols=tracked,
        observed_at=observed_at,
        commit=False,
    )
    if preview.get("status") != "preview":
        return preview
    if remote_state == "present":
        if remote.get("content_sha256") == preview["document"]["content_sha256"]:
            preview["status"] = "unchanged"
            preview["remote"] = "unchanged"
            return preview
        return {"status": "conflict", "reason": "SNAPSHOT_CONFLICT", "path": None, "document": None, "remote": "conflict"}
    result = capture_post_close(
        payload.get("scan_df"),
        now=now,
        session=session,
        root=root,
        market_real=payload.get("market_real"),
        symbols=tracked,
        observed_at=observed_at,
    )
    if result.get("status") in {"created", "unchanged"}:
        result["remote"] = publish_snapshot(root, session)
    return result


def post_close_verified(now: datetime, session: str) -> tuple[bool, str]:
    """True only for the same weekday after 15:10 Asia/Ho_Chi_Minh."""
    from modules.intraday_execution_boundary import as_vn

    local = as_vn(now)
    if local.weekday() >= 5:
        return False, "NOT_A_WEEKDAY_SESSION"
    if local.strftime("%Y-%m-%d") != session:
        return False, "CLOCK_SESSION_MISMATCH"
    if local.timetz().replace(tzinfo=None) < POST_CLOSE:
        return False, "BEFORE_POST_CLOSE"
    return True, "ok"


def observations_from_scan(scan_df, session: str) -> tuple[dict, dict]:
    """Map an existing production scan frame. Missing symbols are left absent."""
    if scan_df is None or not isinstance(scan_df, pd.DataFrame):
        return {}, {"verified": False, "reason": "SCAN_ABSENT", "matched_rows": 0}
    missing = [name for name in SCAN_COLUMNS if name not in scan_df.columns]
    if missing:
        return {}, {
            "verified": False,
            "reason": "SCAN_COLUMNS_ABSENT",
            "missing": missing,
            "matched_rows": 0,
        }
    observations = {}
    matched = 0
    for _, item in scan_df.iterrows():
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        input_session = _session_text(item.get("date"))
        price = finite_number(item.get("price"))
        ema9 = finite_number(item.get("ema9"))
        ma20 = finite_number(item.get("ma20"))
        if input_session == session and price is not None and ema9 is not None and ma20 is not None:
            matched += 1
        live = item.get("is_live_adjusted") if "is_live_adjusted" in scan_df.columns else None
        observations[symbol] = {
            "kind": "scan_row",
            "input_session": input_session,
            "reference_price_provenance": SCAN_PROVENANCE,
            "quality": SCAN_QUALITY,
            "source": SCAN_SOURCE,
            "live_injected": bool(live) if live is not None and not _missing(live) else False,
            "price": item.get("price"),
            "ema9": item.get("ema9"),
            "ma20": item.get("ma20"),
            "obv": item.get("obv"),
            "obv_ema9": item.get("obv_ema9"),
        }
    if matched == 0:
        return observations, {"verified": False, "reason": "NO_SESSION_ROWS", "matched_rows": 0}
    return observations, {"verified": True, "reason": "ok", "matched_rows": matched}


def capture_post_close(
    scan_df,
    *,
    now: datetime,
    session: str,
    root: Path,
    market_real=None,
    symbols: tuple[str, ...] | None = None,
    observed_at: datetime | None = None,
    commit: bool = True,
) -> dict:
    """Write one research snapshot. A same-content retry does not write again."""
    date.fromisoformat(session)
    if observed_at is None:
        allowed, reason = post_close_verified(now, session)
        if not allowed:
            return {"status": "refused", "reason": reason, "path": None, "document": None}
    else:
        allowed, reason = canonical_close_verified(observed_at, session)
        if not allowed:
            return {"status": "refused", "reason": reason, "path": None, "document": None}
        from modules.intraday_execution_boundary import as_vn

        if as_vn(now) < as_vn(observed_at):
            return {"status": "refused", "reason": "SEAL_BEFORE_OBSERVATION", "path": None, "document": None}
    observations, info = observations_from_scan(scan_df, session)
    if not info["verified"]:
        return {
            "status": "refused",
            "reason": info["reason"],
            "path": None,
            "document": None,
            "missing": info.get("missing"),
        }
    tracked = tuple(symbols) if symbols is not None else load_tracked_symbols()
    market = {"market_real": market_real, "market_real_provenance": MARKET_PROVENANCE}
    document = build_snapshot(
        session,
        observations=observations,
        market=market,
        symbols=tracked,
        priors=load_prior_snapshots(root, session),
    )
    if observed_at is not None:
        from modules.intraday_execution_boundary import as_vn

        observation = as_vn(observed_at)
        seal = as_vn(now)
        document = label_observation_origin(
            document,
            "CONTEMPORANEOUS" if seal == observation else "DELAYED",
            reconstruction={
                "observation_at": observation.isoformat(),
                "sealed_at": seal.isoformat(),
                "timestamp_provenance": "close_scan.observed_at",
            },
        )
    if not commit:
        return {"status": "preview", "reason": "ok", "path": None, "document": document}
    dest = Path(root) / "sessions" / f"{session}.json"
    if dest.exists():
        try:
            existing = read_snapshot(dest)
        except (OSError, ValueError, json.JSONDecodeError):
            existing = None
        if existing is not None and _same_observation(existing, document):
            return {
                "status": "unchanged",
                "reason": "ok",
                "path": dest,
                "document": existing,
                "tracked_count": existing["tracked_count"],
                "counts": existing["counts"],
            }
    existed = dest.exists()
    try:
        path = write_snapshot(root, document)
    except SnapshotExists:
        return {"status": "conflict", "reason": "SNAPSHOT_CONFLICT", "path": dest, "document": None}
    return {
        "status": "unchanged" if existed else "created",
        "reason": "ok",
        "path": path,
        "document": document,
        "tracked_count": document["tracked_count"],
        "counts": document["counts"],
    }


def _observation_clock(payload: dict, session: str, now: datetime) -> tuple[datetime | None, str | None]:
    """Separate the scan clock from a later seal. A file-save clock is not a scan clock."""
    from modules.intraday_execution_boundary import as_vn

    if "observed_at" not in payload:
        if payload.get("saved_at"):
            return None, "OBSERVATION_TIMESTAMP_NOT_INDEPENDENT"
        allowed, reason = canonical_close_verified(now, session)
        if not allowed:
            return None, reason
        return None, None
    try:
        parsed = datetime.fromisoformat(str(payload.get("observed_at") or ""))
    except ValueError:
        return None, "OBSERVATION_TIMESTAMP_NOT_INDEPENDENT"
    if parsed.tzinfo is None:
        return None, "OBSERVATION_TIMESTAMP_NOT_INDEPENDENT"
    observation = as_vn(parsed)
    allowed, reason = canonical_close_verified(observation, session)
    if not allowed:
        return None, reason
    if as_vn(now) < observation:
        return None, "SEAL_BEFORE_OBSERVATION"
    return observation, None


def _same_observation(existing: dict, candidate: dict) -> bool:
    """A later seal of the same scan keeps the first file."""
    return _digest(_without_seal_clock(existing)) == _digest(_without_seal_clock(candidate))


def _without_seal_clock(document: dict) -> dict:
    body = {
        key: value
        for key, value in document.items()
        if key not in {"content_sha256", "observation_origin"}
    }
    recorded = body.get("reconstruction")
    if isinstance(recorded, dict):
        body["reconstruction"] = {
            key: value for key, value in recorded.items() if key != "sealed_at"
        }
    return body


def _witness_reason(payload: dict) -> str | None:
    """The close scan already asked whether the VNINDEX daily bar is this session."""
    if "trading_today" not in payload:
        return "SESSION_EVIDENCE_ABSENT"
    if payload.get("trading_today") is not True:
        return "NON_TRADING_SESSION"
    if not str(payload.get("trading_reason") or "").strip():
        return "SESSION_EVIDENCE_ABSENT"
    return None


def _session_text(value) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def read_remote_snapshot(root: Path, session: str) -> tuple[dict | None, str]:
    """Read the sealed GitHub copy. ``disabled`` means this process has no token."""
    store = _github_store(root)
    if not store.github.enabled:
        return None, "disabled"
    try:
        payload = store._github_read(session + ".json")
    except Exception:
        return None, "unverified"
    if payload is None:
        return None, "absent"
    try:
        import json

        document = json.loads(payload.text)
    except (TypeError, ValueError):
        return None, "unverified"
    if not isinstance(document, dict):
        return None, "unverified"
    return document, "present"


def publish_snapshot(root: Path, session: str) -> str:
    """Upload the local sealed file. An existing different remote file is left unchanged."""
    store = _github_store(root)
    if not store.github.enabled:
        return "disabled"
    text = (Path(root) / "sessions" / (session + ".json")).read_text(encoding="utf-8")
    try:
        existing = store._github_read(session + ".json")
    except Exception:
        return "unverified"
    if existing is not None:
        return "unchanged" if existing.text == text else "conflict"
    try:
        return store._github_write(
            session + ".json",
            text,
            "Guardian Research snapshot " + session,
        )
    except Exception:
        return "unverified"


def _github_store(root: Path):
    from modules.earning_learning import GitHubLocalStorage, _load_github_config

    return GitHubLocalStorage(
        Path(root) / "sessions",
        _load_github_config("data/guardian_research/sessions"),
    )


def _missing(value) -> bool:
    try:
        return bool(pd.isna(value))
    except TypeError:
        return False
