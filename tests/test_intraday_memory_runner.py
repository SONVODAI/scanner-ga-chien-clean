"""Tests for intraday memory unattended runner and scheduler."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from modules.intraday_memory.config import IntradayConfig
from modules.intraday_memory.manifest import STATUS_NO_TRADING_DAY, STATUS_SUCCESS
from modules.intraday_memory.runner import (
    EXIT_ALREADY_RUNNING,
    EXIT_SUCCESS,
    main,
    run_scheduled_collect,
    run_scheduled_reconcile,
)
from modules.intraday_memory.scheduler import (
    ESTIMATED_FULL_UNIVERSE_SEC,
    GUEST_RPM,
    PRODUCTION_UNIVERSE_SIZE,
    THROTTLE_FLOOR_SEC,
    estimate_full_universe_duration_sec,
    is_vn_weekend,
    minimum_timer_spacing_minutes,
    resolve_collect_session_date,
    resolve_reconcile_session_date,
)
from modules.intraday_memory.timezone_policy import VN_TZ

REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_DIR = REPO_ROOT / "deploy" / "systemd"


class TestRuntimeEstimate:
    def test_full_universe_exceeds_five_minutes_at_guest_rpm(self):
        estimate = estimate_full_universe_duration_sec()
        assert estimate > 300.0
        assert THROTTLE_FLOOR_SEC > 300.0
        assert ESTIMATED_FULL_UNIVERSE_SEC > 300.0

    def test_minimum_timer_spacing_allows_non_overlap(self):
        spacing = minimum_timer_spacing_minutes(requests_per_minute=GUEST_RPM)
        assert spacing >= 10

    def test_142_symbols_at_18_rpm_throttle_floor(self):
        floor = (PRODUCTION_UNIVERSE_SIZE / GUEST_RPM) * 60.0
        assert abs(floor - 473.33) < 1.0


class TestSchedulerSessionDates:
    def test_friday_post_close_collects_friday(self):
        now = datetime(2026, 8, 14, 18, 30, tzinfo=VN_TZ)
        session, skip = resolve_collect_session_date(now)
        assert skip is None
        assert session == date(2026, 8, 14)

    def test_monday_morning_collect_targets_friday(self):
        now = datetime(2026, 8, 17, 6, 0, tzinfo=VN_TZ)
        session, skip = resolve_collect_session_date(now)
        assert skip is None
        assert session == date(2026, 8, 14)

    def test_tuesday_morning_reconcile_targets_monday(self):
        now = datetime(2026, 8, 18, 7, 30, tzinfo=VN_TZ)
        session, skip = resolve_reconcile_session_date(now)
        assert skip is None
        assert session == date(2026, 8, 17)

    def test_saturday_skip_weekend(self):
        now = datetime(2026, 8, 15, 10, 0, tzinfo=VN_TZ)
        session, skip = resolve_collect_session_date(now)
        assert session is None
        assert skip == "weekend"
        assert is_vn_weekend(now.date())


class TestRunnerSkipManifest:
    def test_weekend_collect_writes_no_trading_day_manifest(self, tmp_path):
        config = IntradayConfig(data_root=tmp_path)
        saturday = datetime(2026, 8, 15, 18, 30, tzinfo=VN_TZ)
        with patch(
            "modules.intraday_memory.runner.resolve_collect_session_date",
            return_value=(None, "weekend"),
        ):
            code = run_scheduled_collect(config)

        assert code == EXIT_SUCCESS
        manifests = list((tmp_path / "manifests").glob("*.json"))
        assert len(manifests) == 1
        data = json.loads(manifests[0].read_text())
        assert data["final_status"] == STATUS_NO_TRADING_DAY
        assert data["mode"] == "scheduled_collect"


class TestRunnerCollect:
    def test_scheduled_collect_invokes_collector(self, tmp_path):
        config = IntradayConfig(data_root=tmp_path)
        mock_manifest = MagicMock()
        mock_manifest.symbols_failed = {}
        mock_manifest.final_status = STATUS_SUCCESS
        mock_manifest.summary_text.return_value = "ok"

        with patch(
            "modules.intraday_memory.runner.resolve_collect_session_date",
            return_value=(date(2026, 8, 14), None),
        ), patch(
            "modules.intraday_memory.runner.IntradayCollector"
        ) as collector_cls:
            collector_cls.return_value.collect_session.return_value = mock_manifest
            code = run_scheduled_collect(config)

        assert code == EXIT_SUCCESS
        collector_cls.return_value.collect_session.assert_called_once_with(
            date(2026, 8, 14)
        )


class TestRunnerLocking:
    def test_overlap_returns_already_running(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MRBOT_INTRADAY_DATA_ROOT", str(tmp_path))
        lock_file = tmp_path / ".collector.lock"
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file.write_text("held")

        import fcntl

        holder = lock_file.open("a+")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)

        try:
            with patch(
                "modules.intraday_memory.runner.resolve_collect_session_date",
                return_value=(None, "weekend"),
            ):
                code = main(["collect"])
            assert code == EXIT_ALREADY_RUNNING
        finally:
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
            holder.close()


class TestSystemdUnits:
    REQUIRED_SERVICE_KEYS = (
        "Type=oneshot",
        "WorkingDirectory=/opt/mrbot-camera",
        "ExecStart=/opt/mrbot-camera-venv/bin/python -m modules.intraday_memory.runner",
        "EnvironmentFile=-/etc/mrbot/intraday.env",
        "SuccessExitStatus=75",
    )

    @pytest.mark.parametrize(
        "filename",
        [
            "mrbot-intraday-collect.service",
            "mrbot-intraday-reconcile.service",
        ],
    )
    def test_service_units_contain_required_directives(self, filename):
        text = (SYSTEMD_DIR / filename).read_text()
        for key in self.REQUIRED_SERVICE_KEYS:
            assert key in text

    def test_collect_timer_weekday_only_and_spaced(self):
        text = (SYSTEMD_DIR / "mrbot-intraday-collect.timer").read_text()
        assert "Mon..Fri" in text
        assert "18:30:00 Asia/Ho_Chi_Minh" in text
        assert "Persistent=true" in text

    def test_reconcile_timer_morning_only(self):
        text = (SYSTEMD_DIR / "mrbot-intraday-reconcile.timer").read_text()
        assert "07:30:00 Asia/Ho_Chi_Minh" in text
        assert "Mon..Fri" in text

    def test_install_script_exists(self):
        assert (SYSTEMD_DIR / "install.sh").exists()
