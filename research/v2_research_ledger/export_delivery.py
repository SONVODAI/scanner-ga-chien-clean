"""Copy one verified publisher trio into an isolated research store.

The publisher directory is read twice. A change between those reads is a
concurrent replacement and nothing is written. A generation is staged under a
partial name, checked again, then renamed into generations/<sha>/. current is a
relative symlink to that generation. Replacing a directory with rename is not
used. last_good.json is written only after the symlink is in place.

Recovery: if current is missing, restore it from last_good.json when that
generation still verifies. A partial directory is disposable. A current
directory is left untouched.

On Linux, current is a relative symlink and os.replace of that symlink is the
commit. On Windows, where creating a symlink is not permitted, current is a
pointer file committed with the same os.replace. The VPS export uses the
symlink.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

MANIFEST_SCHEMA = "v2_research_publisher_manifest.v1"
CLOCK_SCHEMA = "v2_research_ledger_source_clock.v1"
EXPORT_SCHEMA = "v2_research_ledger_export.v1"
MAX_BOARD_BYTES = 32 * 1024 * 1024
BOARD_NAME = "board.json"
CLOCK_NAME = "source_clock.json"
MANIFEST_NAME = "manifest.json"
NAMES = (BOARD_NAME, CLOCK_NAME, MANIFEST_NAME)
REDACTED = "[REDACTED]"
_SECRET_KEY = re.compile(
    r"(token|secret|password|authorization|api_key|bearer|credential|private_key)",
    re.IGNORECASE,
)
_GENERATION = re.compile(r"^[0-9a-f]{64}$")

EXPORTED = "EXPORTED"
UNCHANGED = "UNCHANGED"
REFUSED = "REFUSED"
RECOVERED = "RECOVERED"


@dataclass(frozen=True)
class ExportResult:
    status: str
    reason: str
    generation_id: str = ""
    rows: int = 0

    def public_line(self) -> str:
        return f"{self.status} {self.reason} {self.generation_id} {self.rows}"


def export_once(
    source: Path,
    store: Path,
    *,
    max_board_bytes: int = MAX_BOARD_BYTES,
    before_second_read: Callable[[], None] | None = None,
    replace: Callable[[str | os.PathLike[str], str | os.PathLike[str]], None] | None = None,
) -> ExportResult:
    """Validate one stable snapshot and publish it, or leave the store unchanged."""
    blobs = _snapshot(Path(source), before_second_read)
    if isinstance(blobs, ExportResult):
        return blobs
    checked = _validate(blobs, max_board_bytes)
    if isinstance(checked, ExportResult):
        return checked
    generation_id, rows = checked
    root = Path(store)
    (root / "generations").mkdir(parents=True, exist_ok=True)
    staged = _stage(root, generation_id, blobs)
    if isinstance(staged, ExportResult):
        return staged
    current = _current_id(root)
    if current == generation_id and _generation_ok(root, generation_id, blobs):
        return ExportResult(UNCHANGED, "already_current", generation_id, rows)
    promoted = _promote(root, generation_id, replace or os.replace)
    if isinstance(promoted, ExportResult):
        return promoted
    _write_last_good(root, generation_id, rows)
    return ExportResult(EXPORTED, "published", generation_id, rows)


def recover(store: Path) -> ExportResult:
    """Restore a missing current symlink from the last successful generation."""
    root = Path(store)
    link = root / "current"
    if link.is_symlink() or _is_regular(link):
        ident = _current_id(root)
        if ident and _ready_generation(root, ident):
            return ExportResult(UNCHANGED, "current_ok", ident, _rows_of(root, ident))
        return ExportResult(REFUSED, "current_broken", ident or "")
    if link.exists():
        return ExportResult(REFUSED, "current_directory")
    last = _read_last_good(root)
    if not last or not _ready_generation(root, last):
        return ExportResult(REFUSED, "no_last_good")
    promoted = _promote(root, last, os.replace)
    if isinstance(promoted, ExportResult):
        return promoted
    return ExportResult(RECOVERED, "restored", last, _rows_of(root, last))


def _snapshot(
    source: Path,
    before_second_read: Callable[[], None] | None,
) -> dict[str, bytes] | ExportResult:
    before = _source_hashes(source)
    if isinstance(before, ExportResult):
        return before
    if before_second_read is not None:
        before_second_read()
    blobs: dict[str, bytes] = {}
    try:
        for name in NAMES:
            blobs[name] = _read_regular(source / name)
    except OSError:
        return ExportResult(REFUSED, "missing")
    after = {name: hashlib.sha256(blobs[name]).hexdigest() for name in NAMES}
    again = _source_hashes(source)
    if isinstance(again, ExportResult) or before != after or after != again:
        return ExportResult(REFUSED, "concurrent")
    return blobs


def _source_hashes(source: Path) -> dict[str, str] | ExportResult:
    found: dict[str, str] = {}
    for name in NAMES:
        path = source / name
        if not _is_regular(path):
            return ExportResult(REFUSED, "missing")
        try:
            found[name] = hashlib.sha256(_read_regular(path)).hexdigest()
        except OSError:
            return ExportResult(REFUSED, "missing")
    return found


def _validate(
    blobs: dict[str, bytes],
    max_board_bytes: int,
) -> tuple[str, int] | ExportResult:
    board_bytes = blobs[BOARD_NAME]
    clock_bytes = blobs[CLOCK_NAME]
    manifest_bytes = blobs[MANIFEST_NAME]
    if len(board_bytes) > max_board_bytes or not board_bytes.endswith(b"\n"):
        return ExportResult(REFUSED, "board_bounds")
    parsed: dict[str, Any] = {}
    for name, payload in blobs.items():
        try:
            loaded = json.loads(payload)
        except (json.JSONDecodeError, UnicodeError):
            return ExportResult(REFUSED, "corrupt")
        if not isinstance(loaded, dict):
            return ExportResult(REFUSED, "corrupt")
        parsed[name] = loaded
    manifest = parsed[MANIFEST_NAME]
    clock = parsed[CLOCK_NAME]
    board = parsed[BOARD_NAME]
    if manifest.get("schema") != MANIFEST_SCHEMA or clock.get("schema") != CLOCK_SCHEMA:
        return ExportResult(REFUSED, "schema")
    if manifest.get("final_buy_enabled") is not False:
        return ExportResult(REFUSED, "final_buy")
    digest = hashlib.sha256(board_bytes).hexdigest()
    if manifest.get("board_sha256") != digest or manifest.get("generation_id") != digest:
        return ExportResult(REFUSED, "board_checksum")
    if not _GENERATION.fullmatch(digest):
        return ExportResult(REFUSED, "board_checksum")
    if manifest.get("clock_sha256") != hashlib.sha256(clock_bytes).hexdigest():
        return ExportResult(REFUSED, "clock_checksum")
    if manifest.get("board_bytes") != len(board_bytes):
        return ExportResult(REFUSED, "board_size")
    rows = board.get("rows")
    if not isinstance(rows, list) or manifest.get("rows") != len(rows):
        return ExportResult(REFUSED, "row_count")
    coverage = board.get("coverage") if isinstance(board.get("coverage"), dict) else {}
    if coverage.get("rows") not in (None, len(rows)):
        return ExportResult(REFUSED, "row_count")
    if _has_secret(parsed):
        return ExportResult(REFUSED, "secret_key")
    return digest, len(rows)


def _has_secret(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if _SECRET_KEY.search(str(key)) or _has_secret(item):
                return True
        return False
    if isinstance(value, list):
        return any(_has_secret(item) for item in value)
    return False


def _stage(store: Path, generation_id: str, blobs: dict[str, bytes]) -> ExportResult | None:
    final = _generation_dir(store, generation_id)
    if _generation_ok(store, generation_id, blobs):
        return None
    if final.exists():
        return ExportResult(REFUSED, "generation_mismatch", generation_id)
    partial = store / "generations" / f".{generation_id}.partial"
    _discard_partial(store, partial)
    partial.mkdir(parents=True)
    for name in NAMES:
        _atomic_write(partial / name, blobs[name])
    if not _same_bytes(partial, blobs):
        _discard_partial(store, partial)
        return ExportResult(REFUSED, "stage_mismatch", generation_id)
    ready = "\n".join(hashlib.sha256(blobs[name]).hexdigest() for name in NAMES) + "\n"
    _atomic_write(partial / "READY", ready.encode("utf-8"))
    _fsync_dir(partial)
    os.rename(partial, final)
    _fsync_dir(final.parent)
    if not _generation_ok(store, generation_id, blobs):
        return ExportResult(REFUSED, "stage_mismatch", generation_id)
    return None


def current_target(store: Path) -> str:
    """Generation id published as current, or an empty string."""
    return _current_id(Path(store))


def _promote(
    store: Path,
    generation_id: str,
    replace: Callable[[str | os.PathLike[str], str | os.PathLike[str]], None],
) -> ExportResult | None:
    link = store / "current"
    if link.is_dir() and not link.is_symlink():
        return ExportResult(REFUSED, "current_directory", generation_id)
    temporary = store / f".current-{generation_id[:16]}"
    if temporary.is_symlink() or temporary.exists():
        temporary.unlink()
    relative = Path("generations") / generation_id
    if os.name == "nt":
        temporary.write_text(f"{relative.as_posix()}\n", encoding="utf-8")
    else:
        os.symlink(relative, temporary, target_is_directory=True)
    try:
        replace(temporary, link)
    except OSError:
        if temporary.is_symlink() or temporary.exists():
            temporary.unlink()
        return ExportResult(REFUSED, "promotion_failed", generation_id)
    if _current_id(store) != generation_id:
        return ExportResult(REFUSED, "promotion_failed", generation_id)
    return None


def _write_last_good(store: Path, generation_id: str, rows: int) -> None:
    body = {
        "schema": EXPORT_SCHEMA,
        "generation_id": generation_id,
        "final_buy_enabled": False,
        "rows": rows,
    }
    payload = (json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    _atomic_write(store / "last_good.json", payload)


def _generation_ok(store: Path, generation_id: str, blobs: dict[str, bytes]) -> bool:
    final = _generation_dir(store, generation_id)
    if not final.is_dir() or not _ready_generation(store, generation_id):
        return False
    return _same_bytes(final, blobs)


def _ready_generation(store: Path, generation_id: str) -> bool:
    if not _GENERATION.fullmatch(generation_id):
        return False
    final = _generation_dir(store, generation_id)
    ready = final / "READY"
    if not all(_is_regular(final / name) for name in NAMES) or not _is_regular(ready):
        return False
    try:
        lines = ready.read_text(encoding="utf-8").splitlines()
        blobs = {name: _read_regular(final / name) for name in NAMES}
    except (OSError, UnicodeError):
        return False
    digest = hashlib.sha256(blobs[BOARD_NAME]).hexdigest()
    expected = [hashlib.sha256(blobs[name]).hexdigest() for name in NAMES]
    if lines != expected or digest != generation_id:
        return False
    checked = _validate(blobs, MAX_BOARD_BYTES)
    return checked == (generation_id, checked[1]) if isinstance(checked, tuple) else False


def _rows_of(store: Path, generation_id: str) -> int:
    try:
        board = json.loads(_read_regular(_generation_dir(store, generation_id) / BOARD_NAME))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return 0
    rows = board.get("rows") if isinstance(board, dict) else None
    return len(rows) if isinstance(rows, list) else 0


def _same_bytes(directory: Path, blobs: dict[str, bytes]) -> bool:
    try:
        return all(_read_regular(directory / name) == blobs[name] for name in NAMES)
    except OSError:
        return False


def _generation_dir(store: Path, generation_id: str) -> Path:
    if not _GENERATION.fullmatch(generation_id):
        raise ValueError("generation id")
    path = store / "generations" / generation_id
    root = (store / "generations").resolve()
    if root not in path.resolve().parents:
        raise ValueError("generation path")
    return path


def _discard_partial(store: Path, partial: Path) -> None:
    if not partial.exists() and not partial.is_symlink():
        return
    root = (store / "generations").resolve()
    resolved = partial.resolve()
    if partial.name.startswith(".") and partial.name.endswith(".partial") and root in resolved.parents:
        shutil.rmtree(partial)


def _current_id(store: Path) -> str:
    link = store / "current"
    if link.is_symlink():
        return _pointer_id(link.readlink())
    if _is_regular(link):
        try:
            return _pointer_id(Path(link.read_text(encoding="utf-8").strip()))
        except (OSError, UnicodeError):
            return ""
    return ""


def _pointer_id(target: Path) -> str:
    parts = target.parts
    if parts[:1] != ("generations",) or len(parts) != 2 or not _GENERATION.fullmatch(parts[1]):
        return ""
    return parts[1]


def _read_last_good(store: Path) -> str:
    path = store / "last_good.json"
    if not _is_regular(path):
        return ""
    try:
        loaded = json.loads(_read_regular(path))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return ""
    if not isinstance(loaded, dict) or loaded.get("final_buy_enabled") is not False:
        return ""
    ident = str(loaded.get("generation_id") or "")
    return ident if _GENERATION.fullmatch(ident) else ""


def _atomic_write(path: Path, payload: bytes) -> None:
    partial = path.with_name(f".{path.name}.partial")
    with partial.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(partial, path)


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        chunks: list[bytes] = []
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _is_regular(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return False
    return stat.S_ISREG(mode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export one verified research trio")
    parser.add_argument("--source", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--max-board-bytes", type=int, default=MAX_BOARD_BYTES)
    args = parser.parse_args(argv)
    result = export_once(Path(args.source), Path(args.store), max_board_bytes=args.max_board_bytes)
    print(result.public_line())
    if result.status in {EXPORTED, UNCHANGED}:
        return 0
    if result.reason == "promotion_failed":
        return 3
    return 2


if __name__ == "__main__":
    sys.exit(main())
