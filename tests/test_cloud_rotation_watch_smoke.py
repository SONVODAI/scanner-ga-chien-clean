"""Operator-safety invariants for the public HTTPS Rotation smoke script."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "cloud_rotation_watch_smoke.sh"


def test_smoke_script_never_asks_for_cli_bearer():
    src = SCRIPT.read_text(encoding="utf-8")
    header = "\n".join(src.splitlines()[:22])
    assert "cd /root && /tmp/cloud_rotation_watch_smoke.sh" in header
    assert "TOKEN=" not in header
    assert "getpass" in src
    assert "EDGE_RESEARCH_ARTIFACT_TOKEN" in src
    assert "/etc/mrbot/edge-artifacts.env" in src
    assert "Authorization: Bearer ${" not in src
    assert "curl -k" not in src
    assert "-k " not in src
    assert "CERT_NONE" not in src
    assert "unverified_context" not in src
    assert "create_default_context" in src
    assert "hostname unknown" in src
    assert "your-domain" in src
    assert "Do not put the bearer on the command line" in src
    assert "TOKEN_PRINTED=no" in src
    assert "print(token" not in src
    assert "echo \"$TOKEN\"" not in src
    assert "echo \"${TOKEN}\"" not in src
