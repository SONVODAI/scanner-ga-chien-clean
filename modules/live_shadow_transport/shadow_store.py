"""Copy minimum live-shadow UI artifacts into the isolated VPS store.

Never writes /var/lib/mrbot/intraday_memory. Never writes Edge bundle.tar.gz.
Elite live_evidence.jsonl + live_shadow_status.json stay required.
V2 SHADOW state is optional: missing V2 must not fail Elite publication.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Mapping

from modules.live_shadow_transport.contract import (
    ENV_SHADOW_STORE,
    EVIDENCE_NAME,
    EVIDENCE_TRANSPORT_ERROR,
    FORBIDDEN_CAMERA_ARCHIVE,
    STATUS_NAME,
    V2_ACTION_EVIDENCE_NAME,
    V2_ACTION_OBSERVE_FAILURE_NAME,
    V2_ACTION_STATE_NAME,
    V2_ACTION_SUBDIR,
    VPS_SHADOW_STORE,
)

ALLOWED_SHADOW_FILES = (EVIDENCE_NAME, STATUS_NAME)

# Sidecar resolve failures: must not replace valid published state.
# Row count is irrelevant — a failed reason with spurious rows is still failed.
# NO_CURRENT_SESSION_V2_ROWS stays publishable so same-day historical_buy_ready
# merge / empty handoff behavior is unchanged.
_FAILED_OBSERVE_REASONS = frozenset(
    {
        "SIDECAR_STALE_SESSION",
        "SIDECAR_ABSENT",
        "SIDECAR_INVALID",
        "SIDECAR_PERMISSIONS_NOT_SHADOW",
        "SIDECAR_TRANSPORT_ERROR",
    }
)
# Backward-compatible alias for callers/tests that imported the old name.
_FAILED_EMPTY_OBSERVE_REASONS = _FAILED_OBSERVE_REASONS


def default_shadow_store() -> Path:
    raw = os.environ.get(ENV_SHADOW_STORE, "").strip()
    if raw:
        return Path(raw)
    return Path(VPS_SHADOW_STORE)


def resolve_shadow_store(explicit: Path | None = None) -> Path | None:
    """Only auto-use the VPS default when env is set or a path is injected.

    Unit tests without env skip the copy so they never touch /var/lib/mrbot.
    The --live runner passes the isolated default explicitly.
    """
    if explicit is not None:
        return Path(explicit)
    raw = os.environ.get(ENV_SHADOW_STORE, "").strip()
    if raw:
        return Path(raw)
    return None


def _atomic_replace(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.tmp")
    tmp.write_bytes(src.read_bytes())
    os.replace(tmp, dest)


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _publish_state_merging_history(src_state: Path, dest: Path) -> None:
    """Atomic replace. Same-session BUY_READY validation survives the replace."""
    from modules.live_candidate_v2_action.artifact import merge_historical_buy_ready

    new_doc = _read_json_object(src_state)
    if new_doc is None:
        _atomic_replace(src_state, dest)
        return
    merged = merge_historical_buy_ready(new_doc, _read_json_object(dest))
    if merged.get("historical_buy_ready") == new_doc.get("historical_buy_ready") or (
        not merged.get("historical_buy_ready") and "historical_buy_ready" not in new_doc
    ):
        _atomic_replace(src_state, dest)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(merged, ensure_ascii=False, indent=2, default=str) + "\n"
    tmp = dest.with_name(f".{dest.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, dest)


def _row_count(doc: Mapping[str, Any] | None) -> int:
    if not isinstance(doc, dict):
        return 0
    rows = doc.get("rows")
    if not isinstance(rows, list):
        return 0
    return sum(1 for rec in rows if isinstance(rec, dict))


def is_failed_observation(doc: Mapping[str, Any] | None) -> bool:
    """True when this payload is a failed observe that must not clobber.

    Detected by ``observe_reason`` / failed ``v2_sidecar`` reason. Spurious
    non-empty ``rows`` do not make a failed observe publishable.
    """
    if not isinstance(doc, dict):
        return False
    reason = str(doc.get("observe_reason") or "").strip()
    if reason in _FAILED_OBSERVE_REASONS:
        return True
    sidecar = doc.get("v2_sidecar")
    if isinstance(sidecar, dict):
        side_reason = str(sidecar.get("reason") or "").strip()
        if side_reason in _FAILED_OBSERVE_REASONS and sidecar.get("ok") is False:
            return True
    return False


def is_failed_empty_observation(doc: Mapping[str, Any] | None) -> bool:
    """Alias for :func:`is_failed_observation` (name kept for existing imports)."""
    return is_failed_observation(doc)


def is_valid_nonempty_published_state(doc: Mapping[str, Any] | None) -> bool:
    """Prior published evidence worth retaining across a failed observe."""
    if not isinstance(doc, dict):
        return False
    if _row_count(doc) <= 0:
        return False
    # Execution permission must never be implied by a retained document alone.
    if doc.get("candidate_is_buy") is True or doc.get("alert_eligible") is True:
        return False
    if doc.get("pxv_implies_buy") is True:
        return False
    return True


def _sanitize_failed_observe_for_publish(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Drop any rows/flags from a failed observe before it may become the head."""
    out = dict(doc)
    out["rows"] = []
    out["candidate_is_buy"] = False
    out["pxv_implies_buy"] = False
    out["alert_eligible"] = False
    notes = list(out["notes"]) if isinstance(out.get("notes"), list) else []
    notes.append(
        "Failed observe rows discarded at publish gate; not a fresh actionable evaluation."
    )
    out["notes"] = notes
    return out


def _write_observe_failure_diagnostic(
    dest_dir: Path,
    *,
    failed_doc: Mapping[str, Any],
    retained: Mapping[str, Any],
) -> Path:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / V2_ACTION_OBSERVE_FAILURE_NAME
    retained_rows = retained.get("rows") if isinstance(retained.get("rows"), list) else []
    buy_ready_n = sum(
        1
        for rec in retained_rows
        if isinstance(rec, dict) and str(rec.get("shadow_action") or "") == "BUY_READY"
    )
    payload = {
        "schema": "live_candidate_v2_action_observe_failure.v1",
        "failed_at": failed_doc.get("observed_at"),
        "cycle_session": failed_doc.get("session"),
        "observe_reason": failed_doc.get("observe_reason")
        or (failed_doc.get("v2_sidecar") or {}).get("reason"),
        "v2_sidecar": failed_doc.get("v2_sidecar") or {},
        "failed_had_rows": _row_count(failed_doc) > 0,
        "published_state_retained": True,
        "retained_session": retained.get("session"),
        "retained_observed_at": retained.get("observed_at"),
        "retained_n_rows": _row_count(retained),
        "retained_had_buy_ready_rows": buy_ready_n > 0,
        "actionable": False,
        "fresh_current_session_evaluation": False,
        "candidate_is_buy": False,
        "pxv_implies_buy": False,
        "alert_eligible": False,
        "notes": [
            "Failed observe did not overwrite published v2_action_state.json.",
            "Retained rows are historical evidence only — not a fresh actionable evaluation.",
            "BUY_READY / alert / execution permission require a fresh valid observe.",
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def publish_v2_action_state(src_state: Path, dest_dir: Path) -> dict[str, Any]:
    """Copy only v2_action_state.json. Does not rewrite Elite evidence.

    A STALE/invalid/absent failed observation does not overwrite the last valid
    non-empty published state (even if the failed payload carries spurious rows).
    Diagnostics go to ``v2_action_observe_failure.json`` instead.
    """
    dest_dir = Path(dest_dir)
    dest_s = str(dest_dir)
    if dest_s.startswith(FORBIDDEN_CAMERA_ARCHIVE) or dest_s == FORBIDDEN_CAMERA_ARCHIVE:
        return {"v2_status": "ERROR", "v2_detail": "refusing Camera archive path", "v2_copied": []}
    if not Path(src_state).exists():
        return {"v2_status": "ABSENT", "v2_detail": "no v2_action_state.json", "v2_copied": []}
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_state = dest_dir / V2_ACTION_STATE_NAME
    new_doc = _read_json_object(Path(src_state))
    prior = _read_json_object(dest_state)
    if is_failed_observation(new_doc):
        if is_valid_nonempty_published_state(prior):
            diag = _write_observe_failure_diagnostic(
                dest_dir, failed_doc=new_doc or {}, retained=prior or {}
            )
            return {
                "v2_status": "RETAINED",
                "v2_detail": f"preserved {dest_state}; diagnostic {diag}",
                "v2_copied": [],
                "v2_retained": True,
                "v2_diagnostic": str(diag),
                "actionable": False,
            }
        # No retainable prior: never install failed-observe rows as the head.
        if new_doc is not None and _row_count(new_doc) > 0:
            sanitized = _sanitize_failed_observe_for_publish(new_doc)
            tmp = dest_dir / ".v2_action_state.failed_sanitize.tmp"
            tmp.write_text(
                json.dumps(sanitized, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            try:
                _publish_state_merging_history(tmp, dest_state)
            finally:
                tmp.unlink(missing_ok=True)
            return {
                "v2_status": "OK",
                "v2_detail": f"sanitized failed observe -> {dest_state}",
                "v2_copied": [V2_ACTION_STATE_NAME],
                "v2_retained": False,
                "v2_sanitized_failed": True,
                "actionable": False,
            }
    _publish_state_merging_history(Path(src_state), dest_state)
    return {
        "v2_status": "OK",
        "v2_detail": str(dest_state),
        "v2_copied": [V2_ACTION_STATE_NAME],
        "v2_retained": False,
    }


def _copy_optional_v2(src_dir: Path, dest_dir: Path) -> dict[str, Any]:
    """Publish V2 SHADOW state next to Elite artifacts. Fail-open for Elite."""
    src_state = src_dir / V2_ACTION_SUBDIR / V2_ACTION_STATE_NAME
    if not src_state.exists():
        src_state = src_dir / V2_ACTION_STATE_NAME
    if not src_state.exists():
        return {"v2_status": "ABSENT", "v2_detail": "no v2_action_state.json", "v2_copied": []}
    copied: list[str] = []
    try:
        pub = publish_v2_action_state(src_state, dest_dir)
        if pub.get("v2_status") == "OK":
            copied.extend(list(pub.get("v2_copied") or []))
        src_ev = src_dir / V2_ACTION_SUBDIR / V2_ACTION_EVIDENCE_NAME
        if not src_ev.exists():
            src_ev = src_dir / V2_ACTION_EVIDENCE_NAME
        # Only refresh evidence alongside a successful state publish.
        if src_ev.exists() and pub.get("v2_status") == "OK":
            dest_ev = dest_dir / V2_ACTION_EVIDENCE_NAME
            shutil.copy2(src_ev, dest_ev)
            copied.append(V2_ACTION_EVIDENCE_NAME)
        return {**pub, "v2_copied": copied}
    except OSError as exc:
        return {
            "v2_status": "ERROR",
            "v2_detail": f"copy V2 SHADOW failed: {exc}",
            "v2_copied": copied,
        }


def publish_shadow_artifacts(
    src_dir: Path,
    dest_dir: Path,
) -> dict[str, Any]:
    """Copy Elite live_evidence + status. Optionally copy V2 SHADOW state."""
    src_dir = Path(src_dir)
    dest_dir = Path(dest_dir)
    dest_s = str(dest_dir.resolve()) if dest_dir.exists() or dest_dir.parent.exists() else str(dest_dir)
    if dest_s.startswith(FORBIDDEN_CAMERA_ARCHIVE) or dest_s == FORBIDDEN_CAMERA_ARCHIVE:
        return {
            "ok": False,
            "status": EVIDENCE_TRANSPORT_ERROR,
            "detail": "refusing Camera archive path",
            "copied": [],
            "v2_status": "ABSENT",
            "v2_detail": "",
            "v2_copied": [],
        }
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            "ok": False,
            "status": EVIDENCE_TRANSPORT_ERROR,
            "detail": f"mkdir failed: {exc}",
            "copied": [],
            "v2_status": "ABSENT",
            "v2_detail": "",
            "v2_copied": [],
        }
    copied: list[str] = []
    for name in ALLOWED_SHADOW_FILES:
        src = src_dir / name
        if not src.exists():
            return {
                "ok": False,
                "status": EVIDENCE_TRANSPORT_ERROR,
                "detail": f"missing {name}",
                "copied": copied,
                "v2_status": "ABSENT",
                "v2_detail": "",
                "v2_copied": [],
            }
        dest = dest_dir / name
        try:
            shutil.copy2(src, dest)
        except OSError as exc:
            return {
                "ok": False,
                "status": EVIDENCE_TRANSPORT_ERROR,
                "detail": f"copy {name} failed: {exc}",
                "copied": copied,
                "v2_status": "ABSENT",
                "v2_detail": "",
                "v2_copied": [],
            }
        copied.append(name)
    extra = _copy_optional_v2(src_dir, dest_dir)
    return {
        "ok": True,
        "status": "OK",
        "detail": "",
        "copied": copied,
        "dest": str(dest_dir),
        **extra,
    }
