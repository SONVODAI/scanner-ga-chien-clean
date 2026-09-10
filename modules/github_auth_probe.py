"""TEMPORARY read-only GitHub auth probe. Remove after diagnosis.

Uses the same secret key and Authorization header as Pattern Memory.
Never prints, logs, hashes, or fingerprints the token value.
GET only. No PUT/POST/PATCH/DELETE.
"""
from __future__ import annotations

from typing import Any

import requests

GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_REPO_URL = "https://api.github.com/repos/SONVODAI/scanner-ga-chien-clean"
GITHUB_CONTENTS_URL = (
    "https://api.github.com/repos/SONVODAI/scanner-ga-chien-clean/contents/pattern_history.csv"
)


def _prefix_class(token: str) -> str:
    if token.startswith("github_pat_"):
        return "github_pat"
    if token.startswith("ghp_"):
        return "ghp"
    return "other"


def _shape(token: str) -> dict[str, Any]:
    return {
        "TOKEN_SOURCE": "streamlit_secrets",
        "TOKEN_PREFIX_CLASS": _prefix_class(token),
        "TOKEN_LENGTH": len(token),
        "HAS_LEADING_SPACE": "YES" if (token[:1].isspace() if token else False) else "NO",
        "HAS_TRAILING_SPACE": "YES" if (token[-1:].isspace() if token else False) else "NO",
        "HAS_NEWLINE": "YES" if (("\n" in token) or ("\r" in token)) else "NO",
        "HAS_LITERAL_QUOTES": "YES"
        if (token.startswith(("'", '"')) or token.endswith(("'", '"')))
        else "NO",
    }


def _error_class(status: int, body_text: str) -> str:
    if status == 200:
        return "NONE"
    low = (body_text or "").lower()
    if status == 401 or "bad credentials" in low:
        return "BAD_CREDENTIALS"
    if status == 403:
        return "FORBIDDEN"
    if status == 404:
        return "NOT_FOUND"
    return "OTHER"


def _get(url: str, token: str) -> tuple[int, dict[str, Any] | None, str]:
    """Same Authorization construction as pattern_manager.write_pattern_history."""
    headers = {"Authorization": f"token {token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except Exception:
        return 0, None, ""
    text = ""
    try:
        text = resp.text[:200]
    except Exception:
        text = ""
    payload = None
    try:
        data = resp.json()
        if isinstance(data, dict):
            payload = data
    except Exception:
        payload = None
    return int(resp.status_code), payload, text


def run_readonly_probe(token: str | None) -> dict[str, Any]:
    if not token:
        return {
            "TOKEN_SOURCE": "streamlit_secrets",
            "TOKEN_PREFIX_CLASS": "other",
            "TOKEN_LENGTH": 0,
            "HAS_LEADING_SPACE": "NO",
            "HAS_TRAILING_SPACE": "NO",
            "HAS_NEWLINE": "NO",
            "HAS_LITERAL_QUOTES": "NO",
            "AUTH_USER_HTTP_STATUS": 0,
            "AUTHENTICATED_LOGIN": "NONE",
            "REPO_GET_HTTP_STATUS": "NOT_RUN",
            "CONTENTS_GET_HTTP_STATUS": "NOT_RUN",
            "GITHUB_ERROR_CLASS": "OTHER",
        }
    out = _shape(str(token))
    user_status, user_json, user_text = _get(GITHUB_USER_URL, str(token))
    out["AUTH_USER_HTTP_STATUS"] = user_status
    login = "NONE"
    if user_status == 200 and isinstance(user_json, dict):
        raw_login = user_json.get("login")
        if isinstance(raw_login, str) and raw_login.strip():
            login = raw_login.strip()
    out["AUTHENTICATED_LOGIN"] = login
    out["REPO_GET_HTTP_STATUS"] = "NOT_RUN"
    out["CONTENTS_GET_HTTP_STATUS"] = "NOT_RUN"
    out["GITHUB_ERROR_CLASS"] = _error_class(user_status, user_text)
    if user_status != 200:
        return out
    repo_status, _repo_json, repo_text = _get(GITHUB_REPO_URL, str(token))
    out["REPO_GET_HTTP_STATUS"] = repo_status
    if repo_status != 200:
        out["GITHUB_ERROR_CLASS"] = _error_class(repo_status, repo_text)
        return out
    contents_status, _c_json, c_text = _get(GITHUB_CONTENTS_URL, str(token))
    out["CONTENTS_GET_HTTP_STATUS"] = contents_status
    if contents_status != 200:
        out["GITHUB_ERROR_CLASS"] = _error_class(contents_status, c_text)
    else:
        out["GITHUB_ERROR_CLASS"] = "NONE"
    return out


def format_safe_report(result: dict[str, Any]) -> str:
    keys = (
        "TOKEN_SOURCE",
        "TOKEN_PREFIX_CLASS",
        "TOKEN_LENGTH",
        "HAS_LEADING_SPACE",
        "HAS_TRAILING_SPACE",
        "HAS_NEWLINE",
        "HAS_LITERAL_QUOTES",
        "AUTH_USER_HTTP_STATUS",
        "AUTHENTICATED_LOGIN",
        "REPO_GET_HTTP_STATUS",
        "CONTENTS_GET_HTTP_STATUS",
        "GITHUB_ERROR_CLASS",
    )
    return "\n".join(f"{k} = {result.get(k)}" for k in keys)


def render_github_auth_probe() -> None:
    import streamlit as st

    try:
        token = st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        token = None
    result = run_readonly_probe(token)
    report = format_safe_report(result)
    with st.expander("TEMPORARY GitHub auth probe (read-only)", expanded=True):
        st.caption("GET only · no token value · Pattern Memory Authorization: token")
        st.code(report, language="text")
