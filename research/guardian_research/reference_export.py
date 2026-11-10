"""Read-only export of approximate last-5-minute closes from canonical bars.

The camera archive is only read. A bar before 14:45 is not a closing reference.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

from research.approximate_returns.contract import PRICE_BASIS, SCHEMA_REFERENCE, SOURCE, TRUNCATION_CLOCK
from research.approximate_returns.reference import build_reference_store
from research.guardian_research.universe import load_tracked_symbols

PUBLISHED_PATH = "/current/guardian_research/reference_store.json"
CLOSE_START = TRUNCATION_CLOCK
CLOSE_END = "15:00"
STORE_FILENAME = "reference_store.json"


class ReferenceExportError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def export_reference_store(camera_root: Path, symbols: tuple[str, ...] | None = None) -> dict:
    """Build a store from canonical parquet. Raises if a session file cannot be read."""
    root = Path(camera_root)
    sessions = _session_dates(root)
    if not sessions:
        raise ReferenceExportError("SESSIONS_ABSENT")
    tracked = tuple(symbols) if symbols is not None else load_tracked_symbols()
    accepted: list[dict] = []
    rejections: list[dict] = []
    seen: set[str] = set()
    for session in sessions:
        frame = _read_session(root, session)
        rows, rejected, present = _select_session(frame, session, tracked)
        accepted.extend(rows)
        rejections.extend(rejected)
        seen.update(present)
    if not accepted:
        raise ReferenceExportError("NO_ACCEPTED_CLOSES")
    as_of = sessions[-1].isoformat()
    calendar = [item.isoformat() for item in sessions]
    store = build_reference_store(pd.DataFrame(accepted), calendar, as_of=as_of)
    store["rejections"] = sorted(rejections, key=lambda item: (item["session"], item["symbol"], item["reason"]))
    store["coverage"] = {
        "tracked_count": len(tracked),
        "symbols_never_seen": sorted(set(tracked) - seen),
        "sessions_read": len(sessions),
        "accepted_rows": len(store["rows"]),
        "rejected_count": len(store["rejections"]),
        "close_window": [CLOSE_START, CLOSE_END],
    }
    store["content_sha256"] = _digest(store)
    return store


def write_reference_store(store: dict, destination: Path, *, camera_root: Path | None = None) -> Path:
    """Atomic replace. Refuses to write inside the canonical archive."""
    target = Path(destination)
    if _inside_canonical(target, camera_root):
        raise ReferenceExportError("OUTPUT_INSIDE_ARCHIVE")
    if store.get("content_sha256") != _digest(store):
        raise ReferenceExportError("CHECKSUM_MISMATCH")
    payload = json.dumps(store, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.partial")
    partial.write_text(payload, encoding="utf-8")
    partial.replace(target)
    return target


def read_reference_store(path: Path) -> dict | None:
    """Return the store only when the checksum, basis, and source match."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(document, dict):
        return None
    if document.get("schema") != SCHEMA_REFERENCE or document.get("price_basis") != PRICE_BASIS:
        return None
    if document.get("source") != SOURCE:
        return None
    if document.get("content_sha256") != _digest(document):
        return None
    return document


def guardian_reference_url(value: str) -> str | None:
    """Accept only an HTTPS reference endpoint, including the public Caddy path."""
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    path = parsed.path or ""
    if not path.endswith(PUBLISHED_PATH):
        return None
    prefix = path[: -len(PUBLISHED_PATH)]
    if _published_path(prefix) != path:
        return None
    return f"https://{parsed.netloc}{path}"


def fetch_published_store(url: str, token: str, destination: Path, *, opener=None) -> Path | None:
    """Download the allowlisted artifact. Redirects are not followed."""
    if not str(token or "").strip():
        return None
    endpoint = guardian_reference_url(url)
    if endpoint is None:
        return None
    open_fn = opener or _open_https
    try:
        body = open_fn(endpoint, token)
    except Exception:
        return None
    if not body:
        return None
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.partial")
    partial.write_bytes(body if body.endswith(b"\n") else body + b"\n")
    partial.replace(target)
    if read_reference_store(target) is None:
        target.unlink(missing_ok=True)
        return None
    return target


def resolve_store_path(local_root: Path) -> Path | None:
    """Local file first. A published file is used only when it verifies."""
    local = Path(local_root) / STORE_FILENAME
    if local.is_file():
        return local
    configured = os.environ.get("GUARDIAN_REFERENCE_STORE", "").strip()
    if configured and Path(configured).is_file():
        return Path(configured)
    url = os.environ.get("GUARDIAN_REFERENCE_URL", "").strip()
    token = os.environ.get("GUARDIAN_REFERENCE_TOKEN", "").strip()
    if not url or not token:
        return None
    destination = Path(os.environ.get("GUARDIAN_REFERENCE_DOWNLOAD", "/tmp/guardian_reference_store.json"))
    return fetch_published_store(url, token, destination)


def _select_session(frame: pd.DataFrame, session: date, tracked: tuple[str, ...]) -> tuple[list[dict], list[dict], set[str]]:
    day = session.isoformat()
    if frame is None or frame.empty:
        return [], [_reject(day, symbol, "SYMBOL_ABSENT", "") for symbol in tracked], set()
    work = frame.copy()
    work["symbol"] = work["symbol"].astype(str).str.strip().str.upper()
    present = set(work["symbol"])
    rejections = [_reject(day, symbol, "SYMBOL_ABSENT", "") for symbol in tracked if symbol not in present]
    accepted = []
    for symbol, group in work.groupby("symbol", sort=True):
        usable, rejected = _usable_bars(group, day, str(symbol))
        rejections.extend(rejected)
        chosen, reason, clock = _closing_bar(usable)
        if chosen is None:
            rejections.append(_reject(day, str(symbol), reason, clock))
            continue
        accepted.append({
            "symbol": str(symbol),
            "session": day,
            "close": chosen,
            "clock": clock,
        })
    return accepted, rejections, present


def _usable_bars(group: pd.DataFrame, day: str, symbol: str) -> tuple[list[tuple[str, int]], list[dict]]:
    usable = []
    rejections = []
    for item in group.itertuples(index=False):
        clock, reason = _clock_and_reason(item, day)
        close = _integer_price(getattr(item, "close", None))
        source = str(getattr(item, "source", "") or "")
        quality = str(getattr(item, "quality_flag", "") or "")
        if reason:
            rejections.append(_reject(day, symbol, reason, clock))
            continue
        if source != SOURCE:
            rejections.append(_reject(day, symbol, "SOURCE_MISMATCH", clock))
            continue
        if quality != "ok":
            rejections.append(_reject(day, symbol, "QUALITY_NOT_OK", clock))
            continue
        if close is None:
            rejections.append(_reject(day, symbol, "PRICE_INVALID", clock))
            continue
        usable.append((clock, close))
    return usable, rejections


def _closing_bar(bars: list[tuple[str, int]]) -> tuple[int | None, str, str]:
    window = [(clock, close) for clock, close in bars if CLOSE_START <= clock <= CLOSE_END]
    if not window:
        last = max((clock for clock, _close in bars), default="")
        return None, "LAST_BAR_BEFORE_CLOSE", last
    winner = max(clock for clock, _close in window)
    closes = {close for clock, close in window if clock == winner}
    if len(closes) != 1:
        return None, "CONFLICTING_CLOSE", winner
    return next(iter(closes)), "OK", winner


def _clock_and_reason(item, day: str) -> tuple[str, str]:
    raw = getattr(item, "timestamp", None)
    try:
        stamp = pd.Timestamp(raw)
    except (TypeError, ValueError):
        return "", "TIMESTAMP_INVALID"
    if pd.isna(stamp):
        return "", "TIMESTAMP_INVALID"
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("Asia/Ho_Chi_Minh")
    else:
        stamp = stamp.tz_convert("Asia/Ho_Chi_Minh")
    clock = stamp.strftime("%H:%M")
    if stamp.strftime("%Y-%m-%d") != day:
        return clock, "SESSION_DATE_MISMATCH"
    recorded = getattr(item, "session_date", None)
    if recorded is not None and not pd.isna(recorded):
        text = str(recorded)[:10]
        if text != day:
            return clock, "SESSION_DATE_MISMATCH"
    return clock, ""


def _integer_price(value) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0 or number != int(number):
        return None
    return int(number)


def _reject(session: str, symbol: str, reason: str, clock: str) -> dict:
    return {"session": session, "symbol": symbol, "reason": reason, "clock": clock}


def _read_session(root: Path, session: date) -> pd.DataFrame:
    path = (
        Path(root)
        / "canonical"
        / f"year={session.year}"
        / f"month={session.month:02d}"
        / f"session_date={session.isoformat()}"
        / "bars.parquet"
    )
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:
        raise ReferenceExportError("SESSION_UNREADABLE") from exc
    return frame


def _session_dates(root: Path) -> list[date]:
    canon = Path(root) / "canonical"
    if not canon.is_dir():
        return []
    found = []
    for path in sorted(canon.glob("**/session_date=*/bars.parquet")):
        token = path.parent.name.split("=", 1)[-1]
        try:
            found.append(date.fromisoformat(token))
        except ValueError as exc:
            raise ReferenceExportError("SESSION_NAME_INVALID") from exc
    if found != sorted(set(found)):
        raise ReferenceExportError("SESSION_INDEX_INVALID")
    return found


def _inside_canonical(target: Path, camera_root: Path | None) -> bool:
    if camera_root is None:
        return False
    canonical = (Path(camera_root) / "canonical").resolve()
    try:
        resolved = target.resolve()
    except OSError:
        resolved = target
    return resolved == canonical or canonical in resolved.parents


def _digest(document: dict) -> str:
    body = {key: value for key, value in document.items() if key != "content_sha256"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _published_path(prefix: str) -> str | None:
    text = str(prefix or "").strip()
    if text in {"", "/"}:
        return PUBLISHED_PATH
    if not text.startswith("/") or text.endswith("/") or "//" in text or ".." in text.split("/"):
        return None
    parts = [part for part in text.split("/") if part]
    if not parts or any(not part.replace("-", "").replace("_", "").isalnum() for part in parts):
        return None
    return text + PUBLISHED_PATH


def _open_https(url: str, token: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "User-Agent": "mrbot-guardian-reference/1.0"},
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=20) as response:
            if getattr(response, "status", 200) != 200:
                return b""
            return response.read(8_000_000)
    except urllib.error.HTTPError:
        return b""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Export approximate closes from canonical bars")
    parser.add_argument("--root", default=os.environ.get("MRBOT_INTRADAY_DATA_ROOT", "/var/lib/mrbot/intraday_memory"))
    parser.add_argument("--output", default=os.environ.get("GUARDIAN_REFERENCE_STORE", "/var/lib/mrbot/guardian_reference/reference_store.json"))
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        store = export_reference_store(root)
        write_reference_store(store, Path(args.output), camera_root=root)
    except ReferenceExportError as exc:
        print(json.dumps({"status": "refused", "reason": exc.reason}, ensure_ascii=False))
        return 1
    coverage = store["coverage"]
    print(json.dumps({
        "status": "exported",
        "as_of": store["as_of"],
        "sessions_read": coverage["sessions_read"],
        "accepted_rows": coverage["accepted_rows"],
        "symbols_never_seen": coverage["symbols_never_seen"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
