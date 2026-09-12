"""Read-only Rotation artifact loader. No KBS, no P×V recompute, no Candidate."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

from modules.rotation_watch.artifact import default_board_path, load_json
from modules.rotation_watch.artifact_get import (
    RotationArtifactNotFound,
    RotationTransportError,
    get_rotation_board_text,
    get_rotation_status_text,
    remote_rotation_configured,
    transport_error_payload,
)
from modules.rotation_watch.constants import ENV_UI_SOURCE, SCHEMA_BOARD, SCHEMA_STATUS, TRANSPORT_ERROR


def _parse_board_text(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return _validate_board(data)


def _validate_board(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    schema = data.get("schema")
    has_rows = "rows" in data
    if schema == SCHEMA_BOARD:
        return data
    if schema is None and has_rows:
        return data
    if schema not in {SCHEMA_BOARD, None} and has_rows:
        return data
    return None


def _validate_status(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    if data.get("schema") == SCHEMA_STATUS:
        return data
    return None


def _parse_status_text(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return _validate_status(data)


def resolve_ui_source(explicit: str | None = None) -> str:
    mode = (explicit or os.environ.get(ENV_UI_SOURCE) or "auto").strip().lower()
    if mode == "auto":
        return "remote" if remote_rotation_configured() else "local"
    if mode in {"remote", "local"}:
        return mode
    return "local"


def load_panel_sources(
    *,
    artifact_path: Path | None = None,
    source_mode: str | None = None,
    board_fetcher: Optional[Callable[[], str]] = None,
    status_fetcher: Optional[Callable[[], str]] = None,
) -> dict[str, Any]:
    """One read pass. No provider. Remote GET never falls back to local board."""
    if artifact_path is not None:
        board = load_json(Path(artifact_path))
        return {
            "board": _validate_board(board) if board is not None else None,
            "status": {},
            "transport": {"mode": "local", "error": None, "detail": ""},
        }

    if board_fetcher is not None or status_fetcher is not None:
        mode = "remote"
    else:
        mode = resolve_ui_source(source_mode)
    transport = {"mode": mode, "error": None, "detail": ""}
    if mode != "remote":
        board = load_json(default_board_path())
        return {
            "board": _validate_board(board) if board is not None else None,
            "status": {},
            "transport": transport,
        }

    board: dict[str, Any] | None = None
    status: dict[str, Any] = {}
    try:
        board_text = board_fetcher() if board_fetcher is not None else get_rotation_board_text()
        board = _parse_board_text(board_text)
        if board is None:
            raise RotationTransportError("invalid rotation board payload")
    except RotationArtifactNotFound as exc:
        transport["error"] = TRANSPORT_ERROR
        transport["detail"] = f"rotation board missing: {exc}"
        return {"board": None, "status": {}, "transport": transport}
    except RotationTransportError as exc:
        transport["error"] = TRANSPORT_ERROR
        transport["detail"] = str(exc)
        return {"board": None, "status": {}, "transport": transport}
    except Exception as exc:  # noqa: BLE001 — no silent local fallback
        transport["error"] = TRANSPORT_ERROR
        transport["detail"] = str(exc)
        return {"board": None, "status": {}, "transport": transport}

    try:
        status_text = status_fetcher() if status_fetcher is not None else get_rotation_status_text()
        parsed = _parse_status_text(status_text)
        if parsed is None:
            raise RotationTransportError("invalid rotation status payload")
        status = parsed
    except RotationArtifactNotFound as exc:
        transport["error"] = TRANSPORT_ERROR
        transport["detail"] = f"rotation status missing: {exc}"
        return {"board": None, "status": transport_error_payload(str(exc)), "transport": transport}
    except RotationTransportError as exc:
        transport["error"] = TRANSPORT_ERROR
        transport["detail"] = str(exc)
        return {"board": None, "status": transport_error_payload(str(exc)), "transport": transport}
    except Exception as exc:  # noqa: BLE001
        transport["error"] = TRANSPORT_ERROR
        transport["detail"] = str(exc)
        return {"board": None, "status": transport_error_payload(str(exc)), "transport": transport}

    return {"board": board, "status": status, "transport": transport}


def load_board_artifact(
    path: Path | None = None,
    *,
    source_mode: str | None = None,
    board_fetcher: Optional[Callable[[], str]] = None,
    status_fetcher: Optional[Callable[[], str]] = None,
) -> dict[str, Any] | None:
    src = load_panel_sources(
        artifact_path=path,
        source_mode=source_mode,
        board_fetcher=board_fetcher,
        status_fetcher=status_fetcher,
    )
    return src.get("board")
