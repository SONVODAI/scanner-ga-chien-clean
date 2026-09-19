"""Read-only V2 SHADOW observe from already-collected Camera parquet.

Does not poll KBS. Does not run Brain A. Does not write the Camera archive.
Consumes Gate B sidecar + ``load_session`` bars only.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from modules.intraday_memory.storage import load_session
from modules.live_candidate.calendar import as_vn
from modules.live_candidate_v2_action.artifact import V2ActionStore, persist_cycle
from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    MODE,
    PXV_IMPLIES_BUY,
    SCHEMA_STATE,
    SLICE,
    WAITING_FOR_NEXT_LIVE_ELIGIBLE_5M,
)
from modules.live_candidate_v2_action.observe_bars import (
    interpret_legal_history,
    legal_completed_from_frame,
)
from modules.live_candidate_v2_action.sidecar_source import (
    SOURCE_GITHUB,
    resolve_published_v2_sidecar,
)
from modules.live_candidate_v2_action.state import evaluate_shadow_action, nomination_from_mapping
from modules.live_shadow_transport.contract import (
    FORBIDDEN_CAMERA_ARCHIVE,
    V2_ACTION_SUBDIR,
    VPS_SHADOW_STORE,
)
from modules.live_shadow_transport.shadow_store import publish_v2_action_state, resolve_shadow_store

DEFAULT_CAMERA_ROOT = Path("/var/lib/mrbot/intraday_memory")
ENV_CAMERA_ROOT = "MRBOT_INTRADAY_DATA_ROOT"


def resolve_camera_root(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    raw = os.environ.get(ENV_CAMERA_ROOT, "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_CAMERA_ROOT


def _refuse_camera_write(path: Path) -> None:
    dest = str(Path(path).resolve()) if Path(path).exists() or Path(path).parent.exists() else str(path)
    if dest.startswith(FORBIDDEN_CAMERA_ARCHIVE) or dest == FORBIDDEN_CAMERA_ARCHIVE:
        raise RuntimeError("refusing Camera archive write")


def _base_state(session: str, now: datetime, sidecar: Any, camera_root: Path) -> dict[str, Any]:
    return {
        "schema": SCHEMA_STATE,
        "slice": SLICE,
        "mode": MODE,
        "candidate_is_buy": CANDIDATE_IS_BUY,
        "pxv_implies_buy": PXV_IMPLIES_BUY,
        "alert_eligible": ALERT_ELIGIBLE,
        "session": session,
        "observed_at": as_vn(now).isoformat(),
        "v2_sidecar": sidecar.as_dict() if sidecar is not None else {},
        "camera_root": str(camera_root),
        "kbs_polled": False,
        "collector": "mrbot-intraday-collect",
        "rows": [],
        "notes": [
            "SHADOW / RESEARCH only. Reads collected Camera parquet. Does not poll KBS.",
            "BUY_READY is not a production BUY instruction.",
        ],
    }


def observe_from_collected_session(
    *,
    session: date | str,
    now: datetime,
    camera_root: Path | None = None,
    out_dir: Path,
    shadow_store_dir: Path | None = None,
    sidecar_source: str = SOURCE_GITHUB,
    sidecar_path: Path | None = None,
    sidecar_fetcher: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Evaluate SHADOW action from collected parquet. Never invents OHLCV."""
    now_l = as_vn(now)
    sess = session if isinstance(session, date) else date.fromisoformat(str(session)[:10])
    sess_s = sess.isoformat()
    root = resolve_camera_root(camera_root)
    action_dir = Path(out_dir) / V2_ACTION_SUBDIR
    _refuse_camera_write(action_dir)

    sidecar = resolve_published_v2_sidecar(
        session=sess,
        source=sidecar_source,
        path=sidecar_path,
        fetcher=sidecar_fetcher,
    )
    payload = _base_state(sess_s, now_l, sidecar, root)
    if not sidecar.ok:
        payload["waiting"] = WAITING_FOR_NEXT_LIVE_ELIGIBLE_5M
        payload["observe_reason"] = sidecar.reason
        V2ActionStore(action_dir).write_state(payload)
        _publish(action_dir, shadow_store_dir)
        return payload

    frame = load_session(root, sess)
    items = []
    n_legal = 0
    for raw in sidecar.rows:
        nom = nomination_from_mapping(raw)
        if not nom.symbol:
            continue
        legal = legal_completed_from_frame(frame, symbol=nom.symbol, now=now_l)
        history = interpret_legal_history(nom, legal) if legal else []
        n_legal += len(history)
        result = evaluate_shadow_action(
            nom,
            history,
            now=now_l,
            observed=True,
            observation_reason="" if history else "NOMINATED_NO_LEGAL_COMPLETED_BARS",
        )
        items.append((nom, history, result))
    if items:
        persist_cycle(
            session=sess,
            observed_at=now_l,
            items=items,
            union={"n_v2": len(sidecar.rows), "source": sidecar.source},
            out_dir=action_dir,
        )
        stored = V2ActionStore(action_dir).read_state() or payload
        stored["v2_sidecar"] = sidecar.as_dict()
        stored["kbs_polled"] = False
        stored["collector"] = "mrbot-intraday-collect"
        if n_legal == 0:
            stored["waiting"] = WAITING_FOR_NEXT_LIVE_ELIGIBLE_5M
        V2ActionStore(action_dir).write_state(stored)
        payload = stored
    else:
        payload["waiting"] = WAITING_FOR_NEXT_LIVE_ELIGIBLE_5M
        payload["observe_reason"] = "NO_CURRENT_SESSION_V2_ROWS"
        V2ActionStore(action_dir).write_state(payload)
    _publish(action_dir, shadow_store_dir)
    return payload


def _publish(action_dir: Path, shadow_store_dir: Path | None) -> None:
    dest = resolve_shadow_store(shadow_store_dir)
    if dest is None:
        raw = os.environ.get("MRBOT_LIVE_PXV_SHADOW_STORE", "").strip()
        dest = Path(raw) if raw else Path(VPS_SHADOW_STORE)
    _refuse_camera_write(dest)
    src_state = Path(action_dir) / "v2_action_state.json"
    publish_v2_action_state(src_state, dest)
