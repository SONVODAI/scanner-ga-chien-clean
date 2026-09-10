"""Safe-output contract for the temporary GitHub auth probe."""
from __future__ import annotations

from modules.github_auth_probe import format_safe_report, run_readonly_probe


def test_report_never_contains_token_value(monkeypatch):
    secret = "github_pat_THIS_IS_A_FAKE_TEST_TOKEN_NOT_REAL"

    class _Resp:
        status_code = 401
        text = '{"message":"Bad credentials","status":"401"}'

        def json(self):
            return {"message": "Bad credentials", "status": "401"}

    def fake_get(url, headers=None, timeout=10):
        assert "Authorization" in (headers or {})
        return _Resp()

    import modules.github_auth_probe as mod

    monkeypatch.setattr(mod.requests, "get", fake_get)
    result = run_readonly_probe(secret)
    report = format_safe_report(result)
    assert secret not in report
    assert "THIS_IS_A_FAKE" not in report
    assert "Authorization" not in report
    assert result["TOKEN_PREFIX_CLASS"] == "github_pat"
    assert result["TOKEN_LENGTH"] == len(secret)
    assert result["HAS_LEADING_SPACE"] == "NO"
    assert result["HAS_NEWLINE"] == "NO"
    assert result["AUTH_USER_HTTP_STATUS"] == 401
    assert result["AUTHENTICATED_LOGIN"] == "NONE"
    assert result["REPO_GET_HTTP_STATUS"] == "NOT_RUN"
    assert result["CONTENTS_GET_HTTP_STATUS"] == "NOT_RUN"
    assert result["GITHUB_ERROR_CLASS"] == "BAD_CREDENTIALS"


def test_whitespace_and_quote_flags():
    result = run_readonly_probe(None)
    assert result["TOKEN_LENGTH"] == 0
    from modules.github_auth_probe import _shape

    spaced = _shape(" ghp_abc\n")
    assert spaced["HAS_LEADING_SPACE"] == "YES"
    assert spaced["HAS_NEWLINE"] == "YES"
    quoted = _shape('"ghp_abc"')
    assert quoted["HAS_LITERAL_QUOTES"] == "YES"
