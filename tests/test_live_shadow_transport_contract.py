"""Transport contract constants only. No network, no Camera, no session start."""

from modules.live_shadow_transport.contract import (
    ALERT_ELIGIBLE,
    ARTIFACT_EVIDENCE_PATH,
    EMPTY_WATCHLIST_TEXT,
    FORBIDDEN_CAMERA_ARCHIVE,
    GITHUB_WATCHLIST_PATH,
    IMMUTABLE_ON_TRANSPORT,
)


def test_watchlist_path_is_research_not_camera():
    assert GITHUB_WATCHLIST_PATH == "data/live_candidate/dynamic_watchlist.json"
    assert "intraday_memory" not in GITHUB_WATCHLIST_PATH


def test_artifact_shadow_paths_are_not_edge_bundle():
    assert ARTIFACT_EVIDENCE_PATH.startswith("/current/live_shadow/")
    assert ARTIFACT_EVIDENCE_PATH != "/current/bundle.tar.gz"


def test_camera_archive_forbidden():
    assert FORBIDDEN_CAMERA_ARCHIVE == "/var/lib/mrbot/intraday_memory"


def test_empty_universe_is_present_list_not_missing_object():
    assert GITHUB_WATCHLIST_PATH == "data/live_candidate/dynamic_watchlist.json"
    assert EMPTY_WATCHLIST_TEXT == "[]"


def test_clocks_immutable_and_no_alerts():
    assert "candidate_first_seen_ts" in IMMUTABLE_ON_TRANSPORT
    assert "eligible_from" in IMMUTABLE_ON_TRANSPORT
    assert "chronology_legal" in IMMUTABLE_ON_TRANSPORT
    assert ALERT_ELIGIBLE is False
