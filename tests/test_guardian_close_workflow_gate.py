"""The T+ refresh follows a finished seal and the publish commit stays scoped."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "guardian-close.yml"
SEALED = ROOT / "data" / "guardian_research" / "sessions" / "2026-11-06.json"
SEALED_FILE_SHA256 = "5ecacd69e3026ded470a31e66c2c5ef7023292e344743cbdff0edbb441afc03c"
SEALED_CONTENT_SHA256 = "85c5665a8bffe484f105720690721a85d555cb6af58a32752bc3457a57d31a1e"


def _steps(text: str) -> list[dict[str, str]]:
    """Split the guardian job into top-level steps. Nested script lines stay in the body."""
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("    steps:"))
    blocks: list[list[str]] = []
    for line in lines[start + 1 :]:
        if line.startswith("jobs:") or (line and not line.startswith(" ")):
            break
        if line.startswith("      - "):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
    steps = []
    for block in blocks:
        header = block[0][len("      - ") :]
        body = "\n".join(block[1:])
        name = header.split("name:", 1)[1].strip() if header.startswith("name:") else header
        steps.append({"name": name, "body": body, "raw": "\n".join(block)})
    return steps


def _step(text: str, step_id: str) -> dict[str, str]:
    found = [step for step in _steps(text) if f"id: {step_id}" in step["body"] or step["raw"].startswith(f"      - id: {step_id}")]
    assert len(found) == 1
    return found[0]


def test_failed_seal_still_refreshes_outcomes_and_stays_failed():
    text = WORKFLOW.read_text(encoding="utf-8")
    seal = _step(text, "seal")
    outcomes = _step(text, "outcomes")
    assert "continue-on-error" not in text
    assert "steps.seal.outcome == 'success'" not in text
    assert "if: always() && steps.seal.outcome != 'skipped'" in outcomes["body"]
    assert "python -m research.guardian_research.outcomes" in outcomes["body"]
    assert "python -m research.guardian_research.close_job" in seal["body"]
    assert "continue-on-error" not in seal["raw"]


def test_publish_commits_only_the_outcomes_file():
    text = WORKFLOW.read_text(encoding="utf-8")
    publish = next(step for step in _steps(text) if step["name"] == "Publish changed T+ evidence")
    body = publish["body"]
    assert "if: always() && steps.outcomes.outcome == 'success'" in body
    assert "git checkout -- ." in body
    assert "git clean -fd -- data/guardian_research/sessions" in body
    assert "git add research/guardian_research/outcomes.json" in body
    assert "git add data/guardian_research" not in body
    assert "git add -A" not in body
    assert "git add ." not in text
    assert body.count("git add ") == 1
    assert "2026-11-09" not in text
    assert "backfill" not in text.lower()


def test_sealed_2026_11_06_snapshot_is_unchanged_and_november_9_is_absent():
    assert SEALED.is_file()
    raw = SEALED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SEALED_FILE_SHA256
    document = json.loads(raw)
    assert document["session"] == "2026-11-06"
    assert document["content_sha256"] == SEALED_CONTENT_SHA256
    assert len(document["rows"]) == 143
    assert not (SEALED.parent / "2026-11-09.json").exists()
