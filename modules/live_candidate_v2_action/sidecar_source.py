"""Read-only V2 sidecar for VPS Camera observe.

Authoritative source is the Gate B published GitHub sidecar.
Does not run Brain A. Does not treat Elite rows as V2 nominations.
Fail closed on absent / invalid / unrelated stale documents.
Accepts T−1 documents only when rows are evaluation-eligible for the cycle day.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping

from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    PXV_IMPLIES_BUY,
)
from modules.live_candidate_v2_action.universe import (
    current_session_v2_rows,
    rows_for_evaluation_session,
)
from modules.live_candidate_v2_camera.contract import GITHUB_V2_SIDECAR_PATH
from modules.live_candidate_v2_camera.github_bus import (
    STATUS_NOT_FOUND,
    STATUS_TRANSPORT_ERROR,
    fetch_v2_sidecar,
    validate_v2_sidecar_document,
)
from modules.live_candidate_v2_camera.observe import pxv_implies_buy

SOURCE_GITHUB = "github"
SOURCE_FILE = "file"
SOURCE_INJECTED = "injected"

REASON_OK = "OK"
REASON_ABSENT = "SIDECAR_ABSENT"
REASON_INVALID = "SIDECAR_INVALID"
REASON_STALE_SESSION = "SIDECAR_STALE_SESSION"
REASON_PERMISSIONS = "SIDECAR_PERMISSIONS_NOT_SHADOW"
REASON_TRANSPORT = "SIDECAR_TRANSPORT_ERROR"


@dataclass
class SidecarResolveResult:
    ok: bool
    rows: list[dict[str, Any]] = field(default_factory=list)
    reason: str = REASON_ABSENT
    source: str = ""
    session: str = ""
    n_raw: int = 0
    detail: str = ""
    sidecar_session: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "source": self.source,
            "session": self.session,
            "sidecar_session": self.sidecar_session,
            "n_raw": self.n_raw,
            "n_current_session": len(self.rows),
            "detail": self.detail,
        }


def _fail(
    reason: str,
    *,
    source: str,
    session: str,
    detail: str = "",
    sidecar_session: str = "",
    n_raw: int = 0,
) -> SidecarResolveResult:
    return SidecarResolveResult(
        ok=False,
        rows=[],
        reason=reason,
        source=source,
        session=session,
        detail=detail,
        sidecar_session=sidecar_session,
        n_raw=n_raw,
    )


def _permissions_ok(doc: Mapping[str, Any]) -> bool:
    if doc.get("candidate_is_buy") is True:
        return False
    if doc.get("alert_eligible") is True:
        return False
    if doc.get("pxv_implies_buy") is True:
        return False
    return (
        pxv_implies_buy(None) is False
        and CANDIDATE_IS_BUY is False
        and PXV_IMPLIES_BUY is False
        and ALERT_ELIGIBLE is False
    )


def accept_sidecar_document(
    doc: Mapping[str, Any] | None,
    *,
    session: date | str,
    source: str,
) -> SidecarResolveResult:
    """Validate + evaluation-session filter. Never invents V2 rows.

    Same-day sidecar documents keep rows whose evaluation trading session
    equals the cycle day (including same-day eligible_from). A prior-day
    sidecar is accepted only when at least one row is evaluation-eligible
    for the cycle day via ``eligible_from`` / ``evaluation_trading_session``.
    Unrelated stale, future, or empty-carry documents fail closed.
    """
    sess = session.isoformat() if isinstance(session, date) else str(session or "").strip()
    if not isinstance(doc, Mapping):
        return _fail(REASON_ABSENT, source=source, session=sess, detail="missing document")
    reason = validate_v2_sidecar_document(doc)
    if reason:
        return _fail(REASON_INVALID, source=source, session=sess, detail=reason)
    if not _permissions_ok(doc):
        return _fail(REASON_PERMISSIONS, source=source, session=sess)
    doc_session = str(doc.get("session") or "").strip()
    raw = list(doc.get("rows") or [])

    if doc_session == sess:
        # Same-day document: provenance session filter (unchanged live/feed contract).
        rows = current_session_v2_rows(raw, sess)
        return SidecarResolveResult(
            ok=True,
            rows=rows,
            reason=REASON_OK,
            source=source,
            session=sess,
            sidecar_session=doc_session,
            n_raw=len(raw),
            detail=GITHUB_V2_SIDECAR_PATH if source == SOURCE_GITHUB else source,
        )

    if doc_session > sess:
        return _fail(
            REASON_STALE_SESSION,
            source=source,
            session=sess,
            detail=f"future sidecar session={doc_session}",
            sidecar_session=doc_session,
            n_raw=len(raw),
        )

    # Prior-day document: only rows whose evaluation trading session is today.
    actionable = rows_for_evaluation_session(raw, sess)
    if actionable:
        return SidecarResolveResult(
            ok=True,
            rows=actionable,
            reason=REASON_OK,
            source=source,
            session=sess,
            sidecar_session=doc_session,
            n_raw=len(raw),
            detail=(
                f"carry_from_sidecar_session={doc_session};"
                f"n_eval_eligible={len(actionable)}"
            ),
        )

    return _fail(
        REASON_STALE_SESSION,
        source=source,
        session=sess,
        detail=f"sidecar session={doc_session};no_eval_eligible_rows",
        sidecar_session=doc_session,
        n_raw=len(raw),
    )


def load_sidecar_file(path: Path) -> dict[str, Any] | None:
    src = Path(path)
    if not src.exists():
        return None
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def resolve_published_v2_sidecar(
    *,
    session: date | str,
    source: str = SOURCE_GITHUB,
    path: Path | None = None,
    rows: list[dict[str, Any]] | None = None,
    fetcher: Callable[..., Any] | None = None,
) -> SidecarResolveResult:
    """Resolve V2 rows. Injected list is tests only. GitHub is the VPS default."""
    sess = session.isoformat() if isinstance(session, date) else str(session or "").strip()
    if rows is not None:
        raw = list(rows)
        filtered = rows_for_evaluation_session(raw, sess)
        return SidecarResolveResult(
            ok=True,
            rows=filtered,
            reason=REASON_OK,
            source=SOURCE_INJECTED,
            session=sess,
            sidecar_session=sess,
            n_raw=len(raw),
            detail="injected rows (tests)",
        )

    src = (source or SOURCE_GITHUB).strip().lower()
    if src == SOURCE_FILE or path is not None:
        if path is None:
            return _fail(REASON_ABSENT, source=SOURCE_FILE, session=sess, detail="no path")
        doc = load_sidecar_file(path)
        if doc is None:
            return _fail(REASON_ABSENT, source=SOURCE_FILE, session=sess, detail=str(path))
        return accept_sidecar_document(doc, session=sess, source=SOURCE_FILE)

    fetched = fetcher() if fetcher is not None else fetch_v2_sidecar()
    if not getattr(fetched, "ok", False):
        status = str(getattr(fetched, "status", "") or "")
        if status == STATUS_NOT_FOUND:
            reason = REASON_ABSENT
        elif status == STATUS_TRANSPORT_ERROR:
            reason = REASON_TRANSPORT
        else:
            reason = REASON_INVALID
        return _fail(
            reason,
            source=SOURCE_GITHUB,
            session=sess,
            detail=str(getattr(fetched, "error", "") or status),
        )
    return accept_sidecar_document(fetched.document, session=sess, source=SOURCE_GITHUB)
