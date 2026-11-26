"""One scheduled run ingests sealed rows, then publishes every complete session.

The Price Book is the only calendar. A weekday the book does not contain is
not invented and is not a gap. The first session that fails the completeness
gate stops the run; later sessions are not written. A second run on the same
bytes appends nothing and does not rewrite a sealed identity.

This module does not delete ledger rows, does not dispatch a workflow, and
does not treat the sealed T0 price as a return denominator.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from research.approximate_returns.contract import PRICE_BASIS, SOURCE
from research.guardian_research.reference_export import _digest, fetch_published_store, read_reference_store
from research.guardian_research.universe import load_tracked_symbols
from research.v2_research_ledger.forward_outcomes import (
    ForwardBuildError,
    build_forward_document,
    publish_forward_document,
)
from research.v2_research_ledger.incremental_ingest import incremental_ingest

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
TRACKED_COUNT = 142
NEXT_CONFIRMATION = "publish-next-session"
HOLIDAY_CONFIRMATION = "publish-holiday-gap"
DURABLE_ROOT = "research/v2_research_ledger/durable"
OUTCOMES_ROOT = "research/v2_research_ledger/outcomes"
INDEX_RELATIVE = f"{OUTCOMES_ROOT}/index.json"
DURABLE_FILES = ("identities.jsonl", "links.jsonl", "conflicts.jsonl", "manifest.json")
DURABLE_PATHS = tuple(f"{DURABLE_ROOT}/{name}" for name in DURABLE_FILES)
LOCK_RELATIVE = f"{DURABLE_ROOT}/.ingest.lock"
INDEX_SCHEMA = "v2_research_forward_index.v1"
MAX_PUSH_ATTEMPTS = 3
PINNED_GENERATIONS = {
    "research/v2_research_ledger/outcomes/generations/2026-11-18_41f36ca0cad9_a90e163943d8.json":
        "14aeba749aee6d3d4811ab68257ea2819a75c85aa1f3b253a1fa34287cc80dc6",
    "research/v2_research_ledger/outcomes/generations/2026-11-19_41f36ca0cad9_63b98229a9f9.json":
        "5329e539635ce7393400b83ef7d5cc507184fc152f4aad657db4d257df59f1a5",
    "research/v2_research_ledger/outcomes/generations/2026-11-20_41f36ca0cad9_a15e1c653ed5.json":
        "d935157f682071d94c5838bdc6e39a593c436be51eed2e303b0ac96a10198997",
}


class CatchupRefusal(RuntimeError):
    def __init__(self, reason: str, session: str | None = None, missing: list | None = None, skipped: list | None = None):
        super().__init__(reason)
        self.reason = reason
        self.session = session
        self.missing = list(missing or [])
        self.skipped = list(skipped or [])


def ingest_ledger(
    directory: Path,
    *,
    sidecar_path: Path | None,
    sweet_csv: Path | None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    """Append missing identities. The bytes already on disk stay a prefix."""
    root = Path(directory)
    identities = root / "identities.jsonl"
    before = identities.read_bytes() if identities.is_file() else b""
    before_count = before.count(b"\n")
    report = incremental_ingest(
        root,
        sidecar_path=sidecar_path,
        sweet_csv=sweet_csv,
        evidence_dir=evidence_dir,
    )
    after = identities.read_bytes()
    if not after.startswith(before):
        raise CatchupRefusal("HISTORICAL_IDENTITY_MUTATED")
    if report.get("sealed_identities_unchanged") is not True:
        raise CatchupRefusal("HISTORICAL_IDENTITY_MUTATED")
    report["identity_bytes_before"] = len(before)
    report["identity_lines_before"] = before_count
    report["identity_bytes_after"] = len(after)
    return report


def plan_catchup(
    store: Mapping[str, Any],
    prior: Mapping[str, Any],
    tracked: set[str],
    *,
    today: str,
    moment: datetime.datetime | None = None,
) -> dict[str, Any]:
    """List every complete book session after the published generation.

    Sessions are taken from the book in order. A day that is not in the book
    is left out. The walk stops at the first session the completeness gate
    refuses, and that session is not included.
    """
    sessions = _sessions(store)
    as_of = _iso_day(store.get("as_of"))
    if sessions[-1] != as_of:
        raise CatchupRefusal("CALENDAR_INVALID")
    today_text = _iso_day(today)
    prior_as_of = _iso_day(prior.get("as_of"))
    prior_sessions = [str(item) for item in prior.get("trading_sessions") or []]
    if not prior_sessions or prior_sessions[-1] != prior_as_of or prior_sessions != sorted(set(prior_sessions)):
        raise CatchupRefusal("CALENDAR_INVALID")
    if as_of < prior_as_of:
        raise CatchupRefusal("STALE_PRICE_BOOK", session=as_of)
    if sessions[: len(prior_sessions)] != prior_sessions:
        raise CatchupRefusal("CALENDAR_INVALID")
    if as_of == prior_as_of:
        if store.get("content_sha256") != prior.get("reference_sha256") or sessions != prior_sessions:
            raise CatchupRefusal("PRICE_BOOK_REVISED", session=as_of)
        action = "already_published" if moment is None else _unchanged_disposition(as_of, moment)
        if action == "PRICE_BOOK_NOT_ADVANCED":
            raise CatchupRefusal("PRICE_BOOK_NOT_ADVANCED", session=as_of)
        return {"action": action, "as_of": as_of, "sessions": [], "stopped": None}
    accepted: list[str] = []
    stopped = None
    for session in sessions[len(prior_sessions) :]:
        if datetime.date.fromisoformat(session).weekday() >= 5:
            stopped = _stop(session, "WEEKEND_SESSION", [])
            break
        if session > today_text:
            stopped = _stop(session, "FUTURE_SESSION", [])
            break
        gate = session_gate(slice_reference(store, session), tracked)
        if not gate["ok"]:
            stopped = _stop(session, gate["reason"], gate["missing"], gate["skipped"])
            break
        accepted.append(session)
    return {
        "action": "publish" if accepted else "stopped",
        "as_of": accepted[-1] if accepted else prior_as_of,
        "sessions": accepted,
        "stopped": stopped,
    }


def session_gate(store: Mapping[str, Any], tracked: set[str]) -> dict[str, Any]:
    """Same completeness rule as the daily workflow, with the failing symbol named."""
    sessions = [str(item) for item in store.get("trading_sessions") or []]
    if len(sessions) < 2:
        return _gate(False, "PRICE_BOOK_INCOMPLETE", [])
    new_session = sessions[-1]
    previous = sessions[-2]
    rejections = store.get("rejections")
    if not isinstance(rejections, list):
        return _gate(False, "PRICE_BOOK_INCOMPLETE", [])
    skipped = []
    blocked = []
    for item in rejections:
        if not isinstance(item, dict) or str(item.get("session") or "") != new_session:
            continue
        record = {
            "clock": str(item.get("clock") or ""),
            "reason": str(item.get("reason") or "") or "REJECTION",
            "session": new_session,
            "symbol": str(item.get("symbol") or "").strip().upper(),
        }
        if not record["symbol"] or record["symbol"] in tracked:
            blocked.append(record)
        else:
            skipped.append(record)
    skipped.sort(key=lambda record: (record["symbol"], record["reason"], record["clock"]))
    if blocked:
        return _gate(False, "PRICE_BOOK_INCOMPLETE", blocked, skipped)
    coverage = store.get("coverage")
    declared = coverage.get("tracked_count") if isinstance(coverage, dict) else None
    outside = {record["symbol"] for record in skipped}
    if not isinstance(declared, int) or declared != len(tracked) + len(outside):
        return _gate(
            False,
            "UNIVERSE_MISMATCH",
            [{"symbol": "", "reason": "UNIVERSE_MISMATCH", "declared": declared, "expected": len(tracked) + len(outside)}],
            skipped,
        )
    current, current_problems = _ok_symbols(store, new_session, tracked, strict=True)
    if current_problems:
        return _gate(False, "PRICE_BOOK_INCOMPLETE", current_problems, skipped)
    prior, prior_problems = _ok_symbols(store, previous, tracked, strict=False)
    if prior_problems:
        return _gate(False, "PRICE_BOOK_INCOMPLETE", prior_problems, skipped)
    if not prior:
        return _gate(False, "PRICE_BOOK_INCOMPLETE", [{"symbol": "", "reason": "PRIOR_SESSION_EMPTY", "session": previous}], skipped)
    if current != tracked or not current.issuperset(prior):
        missing = [{"symbol": symbol, "reason": "SYMBOL_ABSENT", "session": new_session} for symbol in sorted(tracked - current)]
        missing.extend(
            {"symbol": symbol, "reason": "PRIOR_SYMBOL_DROPPED", "session": new_session}
            for symbol in sorted(prior - current)
        )
        return _gate(False, "PRICE_BOOK_INCOMPLETE", missing, skipped)
    return _gate(True, "", [], skipped)


def publish_catchup(
    ledger_dir: Path,
    outcomes_root: Path,
    store: Mapping[str, Any],
    sessions: list[str],
    *,
    on_session: Any = None,
) -> list[dict[str, Any]]:
    """Write one generation per session. A raised hook writes nothing for that session or after it."""
    written: list[dict[str, Any]] = []
    source_updated_at = _ledger_source_updated_at(Path(ledger_dir))
    with tempfile.TemporaryDirectory(prefix="ledger-catchup-") as temporary:
        for session in sessions:
            if on_session is not None:
                on_session(session)
            viewed = slice_reference(dict(store), session)
            reference = Path(temporary) / f"{session}.json"
            reference.write_text(json.dumps(viewed, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            try:
                document = build_forward_document(ledger_dir, reference)
            except ForwardBuildError as exc:
                raise CatchupRefusal(exc.reason, session=session) from None
            _require_measurement(document, session)
            _annotate(document, source_updated_at)
            report = publish_forward_document(document, outcomes_root, ledger_dir)
            written.append({
                "as_of": session,
                "file_status": report.get("file_status"),
                "generation_id": report.get("generation_id"),
                "index_status": report.get("index_status"),
                "official_pnl": False,
                "reference_sha256": document.get("reference_sha256"),
                "source_updated_at": document.get("source_updated_at"),
                "latest_sealed_t0": document.get("latest_sealed_t0"),
                "trading_sessions": list(document.get("trading_sessions") or []),
            })
    return written


def run_scheduled_publication(
    repo: Path | None = None,
    *,
    reference_path: Path | None = None,
    now: datetime.datetime | None = None,
    push: bool = True,
) -> int:
    """Ingest, then catch up. A refusal still commits an allowlisted append."""
    root = Path(repo or ".").resolve()
    baseline: dict[str, str] | None = None
    ingested_ok = False
    try:
        _dispatch_mode()
        assert_pinned_generations(root)
        if reference_path is None:
            reference_path = _fetch_reference()
        store = read_reference_store(Path(reference_path))
        if store is None:
            return _finish(False, "REFERENCE_NOT_VALIDATED")
        tracked = _require_universe(load_tracked_symbols())
        baseline = generation_snapshot(root)
        ledger = root / DURABLE_ROOT
        sidecar, sweet = _default_sources(root)
        ingested = ingest_ledger(ledger, sidecar_path=sidecar, sweet_csv=sweet, evidence_dir=None)
        ingested_ok = True
        prior = load_prior(root)
        moment = now or datetime.datetime.now(ICT)
        plan = plan_catchup(store, prior, tracked, today=moment.date().isoformat(), moment=moment)
        published = publish_catchup(ledger, root / OUTCOMES_ROOT, store, plan["sessions"]) if plan["sessions"] else []
        _assert_baseline(root, baseline)
        commit = commit_catchup(root, baseline, _commit_message(plan, published, ingested))
        pushed = push_fast_forward(root) if push and commit is not None else None
        stopped = plan.get("stopped")
        payload = {
            "as_of": plan.get("as_of"),
            "commit": None if commit is None else commit,
            "identity_count": ingested.get("identity_count"),
            "inserted_identities": len(ingested.get("inserted_identities") or []),
            "mode": plan.get("action"),
            "ok": stopped is None,
            "published": published,
            "push": pushed,
            "stopped": stopped,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if stopped is None else 1
    except CatchupRefusal as refusal:
        saved = _save_progress(root, baseline, push=push) if ingested_ok and baseline is not None else None
        return _finish(False, refusal.reason, session=refusal.session, missing=refusal.missing, skipped=refusal.skipped, save=saved)


def assert_pinned_generations(repo: Path) -> None:
    for relative, digest in PINNED_GENERATIONS.items():
        path = Path(repo) / relative
        if not path.is_file() or _sha256(path) != digest:
            raise CatchupRefusal("HISTORICAL_GENERATION_CHANGED")


def generation_snapshot(repo: Path) -> dict[str, str]:
    root = Path(repo) / OUTCOMES_ROOT / "generations"
    if not root.is_dir():
        return {}
    return {
        f"{OUTCOMES_ROOT}/generations/{path.name}": _sha256(path)
        for path in sorted(root.glob("*.json"))
        if path.is_file()
    }


def commit_catchup(repo: Path, baseline: Mapping[str, str], message: str) -> str | None:
    """Commit durable rows and new generations only. Historical files must still match."""
    root = Path(repo)
    _assert_baseline(root, baseline)
    dirty = _porcelain(root)
    if not dirty:
        return None
    current = generation_snapshot(root)
    new_files = set(current) - set(baseline)
    allowed = set(DURABLE_PATHS) | {INDEX_RELATIVE} | new_files
    if any(path not in allowed for path in dirty):
        raise CatchupRefusal("ALLOWLIST_REFUSED")
    _git(root, "add", "--", *sorted(dirty))
    staged = _names(root, "--cached")
    if sorted(staged) != sorted(dirty):
        raise CatchupRefusal("ALLOWLIST_REFUSED")
    _git(
        root,
        "-c",
        "user.name=github-actions[bot]",
        "-c",
        "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit",
        "-m",
        message,
    )
    if _porcelain(root):
        raise CatchupRefusal("WORKSPACE_DIRTY")
    return _rev(root, "HEAD")


def push_fast_forward(repo: Path, attempts: int = MAX_PUSH_ATTEMPTS) -> dict[str, Any]:
    """Fast-forward main. A force push is refused, and a ledger race is not rebased."""
    root = Path(repo)
    rebases = 0
    for _attempt in range(attempts):
        _git(root, "fetch", "origin", "main")
        head = _rev(root, "HEAD")
        origin = _rev(root, "origin/main")
        if origin == head:
            return {"commit": head, "rebases": rebases}
        if _git(root, "merge-base", head, origin, check=False).returncode != 0:
            raise CatchupRefusal("UPSTREAM_REWRITTEN")
        ahead = _git(root, "rev-list", "--count", f"{origin}..HEAD").stdout.strip()
        if ahead != "1":
            raise CatchupRefusal("HISTORY_REFUSED")
        parent = _rev(root, "HEAD^")
        behind = _git(root, "rev-list", "--count", f"HEAD..{origin}").stdout.strip()
        if behind != "0":
            if _blocks(root, parent, origin):
                raise CatchupRefusal("UPSTREAM_LEDGER_CHANGED")
            rebase = _git(root, "rebase", "origin/main", check=False)
            if rebase.returncode != 0:
                _git(root, "rebase", "--abort", check=False)
                raise CatchupRefusal("REBASE_REFUSED")
            rebases += 1
            continue
        push = _git(root, "push", "origin", "HEAD:main", check=False)
        if push.returncode != 0:
            continue
        _git(root, "fetch", "origin", "main")
        if _rev(root, "HEAD") == _rev(root, "origin/main"):
            return {"commit": _rev(root, "HEAD"), "rebases": rebases}
    raise CatchupRefusal("PUSH_REJECTED")


def slice_reference(store: Mapping[str, Any], as_of: str) -> dict[str, Any]:
    """A checksummed book that ends on ``as_of``. The full book is returned unchanged."""
    sessions = [str(item) for item in store.get("trading_sessions") or []]
    target = _iso_day(as_of)
    if str(store.get("as_of") or "") == target and sessions and sessions[-1] == target:
        return dict(store)
    prefix = [item for item in sessions if item <= target]
    if not prefix or prefix[-1] != target or prefix != sorted(set(prefix)):
        raise CatchupRefusal("CALENDAR_INVALID", session=target)
    body = {key: value for key, value in store.items() if key != "content_sha256"}
    body["as_of"] = target
    body["trading_sessions"] = prefix
    body["rows"] = [row for row in store.get("rows") or [] if isinstance(row, dict) and str(row.get("session") or "") <= target]
    if isinstance(store.get("rejections"), list):
        body["rejections"] = [
            row for row in store["rejections"] if isinstance(row, dict) and str(row.get("session") or "") <= target
        ]
    if isinstance(store.get("discontinuities"), list):
        body["discontinuities"] = [
            row for row in store["discontinuities"]
            if not isinstance(row, dict) or str(row.get("session") or "") <= target
        ]
    body["content_sha256"] = _digest(body)
    return body


def load_prior(repo: Path) -> dict[str, Any]:
    index_path = Path(repo) / INDEX_RELATIVE
    try:
        loaded = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatchupRefusal("INDEX_INVALID") from exc
    if not isinstance(loaded, dict) or loaded.get("schema") != INDEX_SCHEMA:
        raise CatchupRefusal("INDEX_INVALID")
    generations = loaded.get("generations")
    if not isinstance(generations, list) or not generations:
        raise CatchupRefusal("PRIOR_GENERATION_ABSENT")
    chosen = [item for item in generations if isinstance(item, dict)]
    if len(chosen) != len(generations):
        raise CatchupRefusal("INDEX_INVALID")
    latest = max(_iso_day(item.get("as_of")) for item in chosen)
    current = [item for item in chosen if str(item.get("as_of") or "") == latest]
    if len(current) != 1:
        raise CatchupRefusal("DUPLICATE_AS_OF")
    entry = current[0]
    relative = str(entry.get("path") or "")
    if not relative.startswith("generations/") or ".." in relative.split("/"):
        raise CatchupRefusal("INDEX_INVALID")
    path = Path(repo) / OUTCOMES_ROOT / relative
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatchupRefusal("PRIOR_GENERATION_ABSENT") from exc
    sessions = [str(item) for item in document.get("trading_sessions") or []] if isinstance(document, dict) else []
    generation_id = str(entry.get("generation_id") or "")
    if path.name != f"{generation_id}.json" or document.get("as_of") != latest or document.get("reference_sha256") != entry.get("reference_sha256"):
        raise CatchupRefusal("PRIOR_GENERATION_ABSENT")
    if not sessions or sessions != sorted(set(sessions)) or sessions[-1] != latest:
        raise CatchupRefusal("CALENDAR_INVALID")
    return {
        "as_of": latest,
        "generation_id": generation_id,
        "reference_sha256": str(entry.get("reference_sha256") or ""),
        "trading_sessions": sessions,
    }


def _annotate(document: dict[str, Any], source_updated_at: str | None) -> None:
    dates = [str(row.get("t0_date") or "") for row in document.get("rows") or [] if row.get("t0_date")]
    if dates:
        document["latest_sealed_t0"] = max(dates)
    if source_updated_at:
        document["source_updated_at"] = source_updated_at


def _require_measurement(document: Mapping[str, Any], session: str) -> None:
    if document.get("official_pnl") is not False or document.get("price_basis") != PRICE_BASIS:
        raise CatchupRefusal("DOCUMENT_INVALID", session=session)
    if document.get("reference_source") != SOURCE or document.get("as_of") != session:
        raise CatchupRefusal("DOCUMENT_INVALID", session=session)
    sessions = [str(item) for item in document.get("trading_sessions") or []]
    if not sessions or sessions[-1] != session:
        raise CatchupRefusal("CALENDAR_INVALID", session=session)
    for row in document.get("rows") or []:
        if row.get("t0_price_used_as_denominator") is not False:
            raise CatchupRefusal("SEALED_PRICE_DENOMINATOR", session=session)


def _ledger_source_updated_at(ledger_dir: Path) -> str | None:
    path = Path(ledger_dir) / "identities.jsonl"
    if not path.is_file():
        return None
    latest = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        for key in ("created_at", "candidate_first_seen_ts"):
            value = str(row.get(key) or "")
            if value > latest:
                latest = value
    return latest or None


def _ok_symbols(store: Mapping[str, Any], session: str, tracked: set[str], *, strict: bool) -> tuple[set[str], list[dict[str, str]]]:
    seen: list[str] = []
    problems: list[dict[str, str]] = []
    for row in store.get("rows") or []:
        if not isinstance(row, dict) or str(row.get("session") or "") != session:
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol not in tracked:
            if strict:
                problems.append({"symbol": symbol, "reason": "OUTSIDE_OK_ROW", "session": session})
            continue
        if str(row.get("quality") or "") != "OK":
            if strict:
                problems.append({"symbol": symbol, "reason": "QUALITY_NOT_OK", "session": session})
            continue
        seen.append(symbol)
    if len(seen) != len(set(seen)):
        problems.append({"symbol": "", "reason": "DUPLICATE_OK_ROW", "session": session})
    return set(seen), problems


def _gate(ok: bool, reason: str, missing: list, skipped: list | None = None) -> dict[str, Any]:
    return {"ok": ok, "reason": reason, "missing": missing, "skipped": list(skipped or [])}


def _stop(session: str, reason: str, missing: list, skipped: list | None = None) -> dict[str, Any]:
    return {"session": session, "reason": reason, "missing": missing, "skipped": list(skipped or [])}


def _sessions(store: Mapping[str, Any]) -> list[str]:
    sessions = [_iso_day(item) for item in store.get("trading_sessions") or []]
    if not sessions or sessions != sorted(set(sessions)):
        raise CatchupRefusal("CALENDAR_INVALID")
    return sessions


def _iso_day(value: object) -> str:
    text = str(value or "")
    try:
        parsed = datetime.date.fromisoformat(text)
    except ValueError as exc:
        raise CatchupRefusal("CALENDAR_INVALID") from exc
    if parsed.isoformat() != text:
        raise CatchupRefusal("CALENDAR_INVALID")
    return text


def _unchanged_disposition(as_of: str, moment: datetime.datetime) -> str:
    if moment.tzinfo is None:
        raise CatchupRefusal("CLOCK_INVALID")
    ict = moment.astimezone(ICT)
    if 6 <= ict.hour < 18:
        if as_of < _previous_weekday(ict.date()).isoformat():
            return "PRICE_BOOK_NOT_ADVANCED"
        return "already_published"
    if as_of < ict.date().isoformat():
        return "waiting_for_price_book"
    return "already_published"


def _previous_weekday(day: datetime.date) -> datetime.date:
    cursor = day - datetime.timedelta(days=1)
    while cursor.weekday() >= 5:
        cursor -= datetime.timedelta(days=1)
    return cursor


def _require_universe(symbols: tuple[str, ...]) -> set[str]:
    tracked = {str(item).strip().upper() for item in symbols}
    if len(symbols) != TRACKED_COUNT or len(tracked) != TRACKED_COUNT or "F88" in tracked:
        raise CatchupRefusal("UNIVERSE_MISMATCH")
    return tracked


def _dispatch_mode() -> str:
    enabled = os.environ.get("LEDGER_FORWARD_DAILY_ENABLED")
    confirm = os.environ.get("CONFIRM")
    ref = os.environ.get("GITHUB_REF")
    event = os.environ.get("GITHUB_EVENT_NAME")
    if enabled != "true":
        raise CatchupRefusal("PUBLICATION_DISABLED")
    if ref != "refs/heads/main":
        raise CatchupRefusal("BRANCH_REFUSED")
    if event == "schedule":
        return "schedule"
    if event == "workflow_dispatch":
        if confirm == NEXT_CONFIRMATION:
            return "next"
        if confirm == HOLIDAY_CONFIRMATION:
            return "holiday"
        raise CatchupRefusal("CONFIRMATION_REFUSED")
    raise CatchupRefusal("EVENT_REFUSED")


def _default_sources(repo: Path) -> tuple[Path, Path]:
    return (
        Path(repo) / "research/live_candidate_v2_camera_sidecar/camera_sidecar.json",
        Path(repo) / "data/earning_learning/market_aware_sweetspot_observer_ledger.csv",
    )


def _fetch_reference() -> Path:
    destination = Path("/tmp/reference_store.json")
    fetched = fetch_published_store(
        os.environ.get("GUARDIAN_REFERENCE_URL", ""),
        os.environ.get("GUARDIAN_REFERENCE_TOKEN", ""),
        destination,
    )
    if fetched is None:
        raise CatchupRefusal("REFERENCE_NOT_VALIDATED")
    return fetched


def _assert_baseline(repo: Path, baseline: Mapping[str, str]) -> None:
    current = generation_snapshot(repo)
    for relative, digest in baseline.items():
        if current.get(relative) != digest:
            raise CatchupRefusal("HISTORICAL_GENERATION_CHANGED")


def _commit_message(plan: Mapping[str, Any], published: list[dict[str, Any]], ingested: Mapping[str, Any]) -> str:
    inserted = len(ingested.get("inserted_identities") or [])
    if published:
        last = str(published[-1].get("as_of") or plan.get("as_of") or "")
        if inserted:
            return f"Append research ledger identities and publish T+ through {last}"
        return f"Publish Research Ledger T+ through {last}"
    if inserted:
        return "Append research ledger identities"
    return "Research ledger daily catch-up found nothing to publish"


def _save_progress(repo: Path, baseline: Mapping[str, str], *, push: bool) -> str | None:
    """Keep an allowlisted append when a later session is refused. Push failures stay visible."""
    try:
        commit = commit_catchup(repo, baseline, "Append research ledger identities")
        if push and commit is not None:
            push_fast_forward(repo)
        return commit
    except CatchupRefusal as refusal:
        return refusal.reason


def _finish(ok: bool, reason: str, **extra: Any) -> int:
    payload = {"ok": ok, "reason": reason, **extra}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 1


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _porcelain(repo: Path) -> list[str]:
    completed = _git(repo, "status", "--porcelain", "--untracked-files=all")
    paths = []
    for line in completed.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"')
        if path == LOCK_RELATIVE:
            continue
        paths.append(path)
    return paths


def _blocks(repo: Path, earlier: str, later: str) -> bool:
    protected = (DURABLE_ROOT, OUTCOMES_ROOT)
    for path in _names(repo, earlier, later):
        if any(path == root or path.startswith(root + "/") for root in protected):
            return True
    return False


def _names(repo: Path, *args: str) -> list[str]:
    completed = _git(repo, "diff", "--name-only", *args)
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _rev(repo: Path, revision: str) -> str:
    return _git(repo, "rev-parse", revision).stdout.strip()


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    if any(arg in {"--force", "--force-with-lease", "--force-if-includes"} or str(arg).startswith("+") for arg in args):
        raise CatchupRefusal("FORCE_PUSH_REFUSED")
    completed = subprocess.run(
        ["git", "-C", str(repo), "-c", "color.ui=false", "-c", "commit.gpgsign=false", *args],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true"},
    )
    if check and completed.returncode != 0:
        raise CatchupRefusal("GIT_FAILED")
    return completed
