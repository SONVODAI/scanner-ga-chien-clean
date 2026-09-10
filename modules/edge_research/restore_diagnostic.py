"""Temporary, read-only Cloud restore diagnostics.

Classifies already-produced restore results into finite safe labels.
Never logs, prints, or returns URL/token/hostname/raw exception text.
Does not call restore, GET, PUT, Discovery, or Challenger.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Mapping, Optional

# Finite HTTP / transport classes shown in the TEMP diagnostic.
HTTP_NONE = "n/a"
HTTP_401 = "HTTP_401"
HTTP_403 = "HTTP_403"
HTTP_404 = "HTTP_404"
HTTP_5XX = "HTTP_5XX"
TIMEOUT = "TIMEOUT"
CONNECTION_ERROR = "CONNECTION_ERROR"

# Finite reason / category labels (never raw free text).
BACKEND_NOT_CONFIGURED = "BACKEND_NOT_CONFIGURED"
VALIDATION_REJECTED = "VALIDATION_REJECTED"
UNKNOWN_ERROR = "UNKNOWN_ERROR"
RESTORED = "restored"
SKIPPED_LOCAL_NEWER = "keeping newer/equal local state"
NO_REMOTE_BUNDLE = "no remote bundle"
HTTP_LOAD_FAILED_401 = "HTTP load failed: 401"
HTTP_LOAD_FAILED_403 = "HTTP load failed: 403"
HTTP_LOAD_FAILED_404 = "HTTP load failed: 404"
HTTP_LOAD_FAILED_5XX = "HTTP load failed: 5xx"
VALIDATION_REJECTED_REASON = "validation rejected"
NO_REMOTE_SIDECAR = "no remote sidecar"

_UNSAFE_RE = re.compile(
    r"("
    r"https?://"
    r"|wss?://"
    r"|www\."
    r"|\b\d{1,3}(?:\.\d{1,3}){3}\b"
    r"|bearer\s+\S+"
    r"|authorization\s*[:=]"
    r"|EDGE_RESEARCH_DURABLE_(?:URL|TOKEN)"
    r"|token['\"]?\s*[:=]"
    r")",
    re.IGNORECASE,
)

_HTTP_401_RE = re.compile(r"(?:http\s*(?:error|load failed)?[:\s]*|status[:\s]*)401\b|\b401\b", re.I)
_HTTP_403_RE = re.compile(r"(?:http\s*(?:error|load failed)?[:\s]*|status[:\s]*)403\b|\b403\b", re.I)
_HTTP_404_RE = re.compile(r"(?:http\s*(?:error|load failed)?[:\s]*|status[:\s]*)404\b|\b404\b", re.I)
_HTTP_5XX_RE = re.compile(r"(?:http\s*(?:error|load failed)?[:\s]*|status[:\s]*)(5\d{2})\b|\b5\d{2}\b")


def contains_unsafe_material(text: str) -> bool:
    """True when text looks like a URL, host, bearer, or token assignment."""
    if not text:
        return False
    if _UNSAFE_RE.search(text):
        return True
    if "://" in text:
        return True
    return False


def classify_restore_detail(raw: Optional[str]) -> Dict[str, str]:
    """Map raw restore detail to safe finite http_class + reason.

    Never returns the input string when it is unsafe or unknown free text.
    """
    text = "" if raw is None else str(raw)
    lowered = text.lower()

    http_class = HTTP_NONE
    reason = UNKNOWN_ERROR

    if not text.strip():
        return {"http_class": HTTP_NONE, "reason": UNKNOWN_ERROR, "category": UNKNOWN_ERROR}

    if "not configured" in lowered or "durable_backend_disabled" in lowered or "http_url_missing" in lowered:
        return {
            "http_class": HTTP_NONE,
            "reason": "durable backend not configured",
            "category": BACKEND_NOT_CONFIGURED,
        }
    if "backend disabled" in lowered:
        return {
            "http_class": HTTP_NONE,
            "reason": "durable backend not configured",
            "category": BACKEND_NOT_CONFIGURED,
        }

    if "remote_sidecar_404" in lowered or "production_observations_not_found" in lowered:
        return {"http_class": HTTP_404, "reason": NO_REMOTE_SIDECAR, "category": HTTP_404}

    if "no remote bundle" in lowered:
        return {"http_class": HTTP_404, "reason": NO_REMOTE_BUNDLE, "category": HTTP_404}

    if "keeping newer/equal local" in lowered or "conflict_winner" in lowered:
        return {"http_class": HTTP_NONE, "reason": SKIPPED_LOCAL_NEWER, "category": SKIPPED_LOCAL_NEWER}

    if (
        "invalid" in lowered
        or "rejected" in lowered
        or "validation" in lowered
        or "disallowed path" in lowered
    ):
        return {
            "http_class": HTTP_NONE,
            "reason": VALIDATION_REJECTED_REASON,
            "category": VALIDATION_REJECTED,
        }

    if "timeout" in lowered or "timed out" in lowered:
        http_class = TIMEOUT
        reason = TIMEOUT
    elif "connection" in lowered or "urlopen" in lowered or "errno" in lowered or "name resolution" in lowered:
        http_class = CONNECTION_ERROR
        reason = CONNECTION_ERROR
    elif _HTTP_401_RE.search(text):
        http_class = HTTP_401
        reason = HTTP_LOAD_FAILED_401
    elif _HTTP_403_RE.search(text):
        http_class = HTTP_403
        reason = HTTP_LOAD_FAILED_403
    elif _HTTP_404_RE.search(text):
        http_class = HTTP_404
        reason = HTTP_LOAD_FAILED_404
    elif _HTTP_5XX_RE.search(text):
        http_class = HTTP_5XX
        reason = HTTP_LOAD_FAILED_5XX
    elif "restored canonical" in lowered or lowered.strip() == "restored":
        return {"http_class": HTTP_NONE, "reason": RESTORED, "category": RESTORED}

    # Never echo unknown / unsafe free text.
    if contains_unsafe_material(text) and http_class == HTTP_NONE:
        return {"http_class": UNKNOWN_ERROR, "reason": UNKNOWN_ERROR, "category": UNKNOWN_ERROR}
    if http_class == HTTP_NONE and reason == UNKNOWN_ERROR:
        return {"http_class": HTTP_NONE, "reason": UNKNOWN_ERROR, "category": UNKNOWN_ERROR}
    return {"http_class": http_class, "reason": reason, "category": http_class if http_class != HTTP_NONE else reason}


def _backend_configured(backend: str) -> str:
    name = (backend or "").strip().lower()
    if name in ("", "none", "disabled", "off"):
        return "NO"
    return "YES"


def _safe_result(raw: str) -> str:
    value = (raw or "none").strip().lower()
    if value in {"restored", "skipped", "rejected", "error", "none", "published", "failed"}:
        if value == "published":
            return "restored"
        if value == "failed":
            return "error"
        return value
    return "error"


def _field(status: Any, name: str, default: str = "") -> str:
    if status is None:
        return default
    if isinstance(status, Mapping):
        value = status.get(name, default)
    else:
        value = getattr(status, name, default)
    return default if value is None else str(value)


def challenger_diagnostic_from_status(status: Any) -> Dict[str, str]:
    """Read-only view of existing PersistenceStatus. Does not restore."""
    backend = _field(status, "backend", "none")
    last_result = _field(status, "last_result", "none")
    message = _field(status, "message", "")
    classified = classify_restore_detail(message)
    result = _safe_result(last_result)
    reason = classified["reason"]
    http_class = classified["http_class"]
    if result == "restored" and http_class == HTTP_NONE:
        reason = RESTORED
    if result == "skipped" and classified["category"] == BACKEND_NOT_CONFIGURED:
        reason = "durable backend not configured"
    return {
        "CHALLENGER_BACKEND_CONFIGURED": _backend_configured(backend),
        "CHALLENGER_RESTORE_RESULT": result,
        "CHALLENGER_RESTORE_REASON": reason,
        "CHALLENGER_HTTP_CLASS": http_class,
    }


def autonomous_diagnostic_from_restore_result(payload: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    """Classify the existing restore return dict. Does not call restore."""
    data: Mapping[str, Any] = payload if isinstance(payload, Mapping) else {}
    ok = bool(data.get("ok"))
    skipped = bool(data.get("skipped"))
    reason_raw = str(data.get("reason") or "")
    error_raw = str(data.get("error") or "")
    combined = " ".join(p for p in (reason_raw, error_raw) if p)
    classified = classify_restore_detail(combined) if combined else {
        "http_class": HTTP_NONE,
        "reason": UNKNOWN_ERROR,
        "category": UNKNOWN_ERROR,
    }

    if ok:
        result = "restored"
        configured = "YES"
        reason = RESTORED
        http_class = HTTP_NONE
    elif skipped:
        result = "skipped"
        configured = "NO" if classified["category"] == BACKEND_NOT_CONFIGURED else "YES"
        reason = classified["reason"]
        http_class = classified["http_class"]
        if not combined:
            configured = "NO"
            reason = "durable backend not configured"
            classified = {"category": BACKEND_NOT_CONFIGURED, "http_class": HTTP_NONE, "reason": reason}
    elif error_raw:
        result = "error"
        configured = "NO" if classified["category"] == BACKEND_NOT_CONFIGURED else "YES"
        reason = classified["reason"]
        http_class = classified["http_class"]
    else:
        result = "none"
        configured = "NO"
        reason = UNKNOWN_ERROR
        http_class = HTTP_NONE

    return {
        "AUTONOMOUS_BACKEND_CONFIGURED": configured,
        "AUTONOMOUS_RESTORE_RESULT": result,
        "AUTONOMOUS_RESTORE_REASON": reason,
        "AUTONOMOUS_HTTP_CLASS": http_class,
    }


def cloud_token_presence_diagnostic() -> Dict[str, str]:
    """Presence + 8-hex fingerprint of already-loaded Cloud durable token.

    Uses the same ``_secret_or_env("EDGE_RESEARCH_DURABLE_TOKEN")`` resolution
    as durable restore. Never returns the token, full hash, or length.
    """
    from modules.edge_research.durable import _secret_or_env

    raw = _secret_or_env("EDGE_RESEARCH_DURABLE_TOKEN")
    token = "" if raw is None else str(raw).strip()
    if not token:
        return {"CLOUD_TOKEN_PRESENT": "NO"}
    fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()[:8]
    return {
        "CLOUD_TOKEN_PRESENT": "YES",
        "CLOUD_TOKEN_FINGERPRINT": fingerprint,
    }


def _safe_fingerprint(value: str) -> str:
    fp = (value or "").strip().lower()
    if len(fp) == 8 and all(c in "0123456789abcdef" for c in fp):
        return fp
    return ""


def format_restore_diagnostic_text(
    *,
    challenger: Mapping[str, str],
    autonomous: Mapping[str, str],
    cloud_token: Optional[Mapping[str, str]] = None,
) -> str:
    """Machine-readable TEMP diagnostic. Values are already classified/safe."""
    token_info = cloud_token or {}
    present = str(token_info.get("CLOUD_TOKEN_PRESENT") or "NO")
    if present not in ("YES", "NO"):
        present = "NO"
    lines = [
        "READ ONLY / TEMPORARY DIAGNOSTIC",
        f"CHALLENGER_BACKEND_CONFIGURED={challenger.get('CHALLENGER_BACKEND_CONFIGURED', 'NO')}",
        f"CHALLENGER_RESTORE_RESULT={challenger.get('CHALLENGER_RESTORE_RESULT', 'none')}",
        f"CHALLENGER_RESTORE_REASON={challenger.get('CHALLENGER_RESTORE_REASON', UNKNOWN_ERROR)}",
        f"CHALLENGER_HTTP_CLASS={challenger.get('CHALLENGER_HTTP_CLASS', HTTP_NONE)}",
        f"AUTONOMOUS_BACKEND_CONFIGURED={autonomous.get('AUTONOMOUS_BACKEND_CONFIGURED', 'NO')}",
        f"AUTONOMOUS_RESTORE_RESULT={autonomous.get('AUTONOMOUS_RESTORE_RESULT', 'none')}",
        f"AUTONOMOUS_RESTORE_REASON={autonomous.get('AUTONOMOUS_RESTORE_REASON', UNKNOWN_ERROR)}",
        f"AUTONOMOUS_HTTP_CLASS={autonomous.get('AUTONOMOUS_HTTP_CLASS', HTTP_NONE)}",
        f"CLOUD_TOKEN_PRESENT={present}",
    ]
    if present == "YES":
        fingerprint = _safe_fingerprint(str(token_info.get("CLOUD_TOKEN_FINGERPRINT") or ""))
        if fingerprint:
            lines.append(f"CLOUD_TOKEN_FINGERPRINT={fingerprint}")
    text = "\n".join(lines)
    if contains_unsafe_material(text):
        return (
            "READ ONLY / TEMPORARY DIAGNOSTIC\n"
            "CHALLENGER_BACKEND_CONFIGURED=NO\n"
            "CHALLENGER_RESTORE_RESULT=error\n"
            "CHALLENGER_RESTORE_REASON=UNKNOWN_ERROR\n"
            "CHALLENGER_HTTP_CLASS=UNKNOWN_ERROR\n"
            "AUTONOMOUS_BACKEND_CONFIGURED=NO\n"
            "AUTONOMOUS_RESTORE_RESULT=error\n"
            "AUTONOMOUS_RESTORE_REASON=UNKNOWN_ERROR\n"
            "AUTONOMOUS_HTTP_CLASS=UNKNOWN_ERROR\n"
            "CLOUD_TOKEN_PRESENT=NO"
        )
    return text
