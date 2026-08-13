"""Shared pytest fixtures — isolate runtime brain/ forward files from the repo."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_BRAIN = REPO_ROOT / "brain"

WATCHED_REPO_BRAIN_FILES = (
    REPO_BRAIN / "regime_alpha_shadow_ledger.csv",
    REPO_BRAIN / "learning_insight_forward_ledger.csv",
    REPO_BRAIN / "regime_alpha_forward_outcomes.csv",
    REPO_BRAIN / "ai_recommendation.csv",
    REPO_BRAIN / "ai_recommendation_shadow.csv",
)


def _file_digest(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(autouse=True)
def isolate_brain_runtime_paths(tmp_path, monkeypatch):
    """Redirect brain/ forward and recommendation runtime paths to temp storage."""
    brain = tmp_path / "brain"
    brain.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MRBOT_BRAIN_DIR", str(brain))

    import leader_memory as lm
    import modules.regime_alpha_forward_eval as fe
    import modules.regime_alpha_shadow as rs

    monkeypatch.setattr(lm, "BRAIN_DIR", brain)
    monkeypatch.setattr(lm, "RECOMMENDATION_FILE", brain / "ai_recommendation.csv")
    monkeypatch.setattr(lm, "BRAIN_FILE", brain / "leader_brain.csv")
    monkeypatch.setattr(lm, "HISTORY_FILE", brain / "leader_history.csv")
    monkeypatch.setattr(lm, "PATTERN_FILE", brain / "pattern_library.csv")
    monkeypatch.setattr(lm, "HALL_OF_FAME_FILE", brain / "hall_of_fame.csv")
    monkeypatch.setattr(lm, "LOCK_FILE", brain / ".leader_memory.lock")
    monkeypatch.setattr(lm, "LOG_FILE", brain / "leader_memory.log")

    monkeypatch.setattr(fe, "LEDGER_FILE", brain / "regime_alpha_shadow_ledger.csv")
    monkeypatch.setattr(fe, "INSIGHT_LEDGER_FILE", brain / "learning_insight_forward_ledger.csv")
    monkeypatch.setattr(fe, "OUTCOMES_FILE", brain / "regime_alpha_forward_outcomes.csv")

    monkeypatch.setattr(rs, "SHADOW_SNAPSHOT_FILE", brain / "ai_recommendation_shadow.csv")
    monkeypatch.setattr(rs, "SHADOW_COMPARISON_FILE", brain / "regime_alpha_shadow_comparison.csv")

    try:
        import modules.learning_trajectory_memory as traj

        monkeypatch.setattr(
            traj,
            "TRAJECTORY_LEDGER_FILE",
            brain / "learning_trajectory_forward_ledger.csv",
        )
    except Exception:
        pass

    lm.reset_runtime_recommendations()
    yield brain


@pytest.fixture(autouse=True)
def protect_repo_brain_files():
    """Fail tests that mutate committed/runtime brain CSVs in the repository tree."""
    before = {path: _file_digest(path) for path in WATCHED_REPO_BRAIN_FILES}
    yield
    for path, digest in before.items():
        after = _file_digest(path)
        assert after == digest, f"Repository brain file mutated during tests: {path}"
