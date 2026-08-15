#!/usr/bin/env python3
"""
Unattended runner for Mr.BOT Intraday Memory V1A.

Invoked by systemd timers on the dedicated collector VPS. Wraps the existing
CLI/collector without duplicating collection logic.

Usage:
  python -m modules.intraday_memory.runner collect
  python -m modules.intraday_memory.runner reconcile
"""

from __future__ import annotations

import argparse
import fcntl
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from modules.intraday_memory.collector import IntradayCollector
from modules.intraday_memory.config import (
    COLLECTOR_VERSION,
    IntradayConfig,
    detect_tier,
)
from modules.intraday_memory.manifest import (
    STATUS_NO_TRADING_DAY,
    RunManifest,
)
from modules.intraday_memory.scheduler import (
    resolve_collect_session_date,
    resolve_reconcile_session_date,
)
from modules.intraday_memory.timezone_policy import VN_TZ

logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_COLLECTOR_FAILURE = 1
EXIT_USAGE = 2
EXIT_ALREADY_RUNNING = 75


def _lock_path(config: IntradayConfig) -> Path:
    return Path(config.data_root) / ".collector.lock"


def _acquire_lock(lock_file: Path):
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_file.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise
    handle.seek(0)
    handle.truncate()
    handle.write(f"pid={os.getpid()} started={datetime.now(VN_TZ).isoformat()}\n")
    handle.flush()
    return handle


def _write_skip_manifest(
    config: IntradayConfig,
    *,
    mode: str,
    reason: str,
) -> RunManifest:
    manifest = RunManifest(
        mode=f"scheduled_{mode}",
        provider=config.provider_source,
        collector_version=COLLECTOR_VERSION,
        storage_root=str(config.data_root),
        final_status=STATUS_NO_TRADING_DAY,
        tier=detect_tier(),
        requests_per_minute=config.requests_per_minute,
    )
    manifest.finish()
    manifest.duration_sec = max(
        0.0,
        (manifest.finished_at - manifest.started_at).total_seconds(),  # type: ignore[operator]
    )
    manifests_dir = Path(config.data_root) / "manifests"
    manifest.save(manifests_dir)
    logger.info(
        "Scheduled %s skipped (%s) | status=%s | manifest=%s",
        mode,
        reason,
        manifest.final_status,
        manifest.run_id,
    )
    return manifest


def run_scheduled_collect(config: IntradayConfig) -> int:
    session_date, skip_reason = resolve_collect_session_date()
    if skip_reason:
        _write_skip_manifest(config, mode="collect", reason=skip_reason)
        return EXIT_SUCCESS

    assert session_date is not None
    collector = IntradayCollector(config=config)
    manifest = collector.collect_session(session_date)
    print(manifest.summary_text())
    if manifest.final_status == STATUS_NO_TRADING_DAY:
        return EXIT_SUCCESS
    return EXIT_COLLECTOR_FAILURE if manifest.symbols_failed else EXIT_SUCCESS


def run_scheduled_reconcile(config: IntradayConfig) -> int:
    session_date, skip_reason = resolve_reconcile_session_date()
    if skip_reason:
        _write_skip_manifest(config, mode="reconcile", reason=skip_reason)
        return EXIT_SUCCESS

    assert session_date is not None
    collector = IntradayCollector(config=config)
    manifest, report = collector.reconcile(session_date)
    print(manifest.summary_text())
    logger.info("Reconcile comparison: %s", report.get("comparison"))
    return EXIT_COLLECTOR_FAILURE if manifest.symbols_failed else EXIT_SUCCESS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mr.BOT Intraday Memory unattended runner",
    )
    parser.add_argument(
        "command",
        choices=("collect", "reconcile"),
        help="Scheduled operation to run",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    config = IntradayConfig.from_env()
    lock_handle = None
    try:
        lock_handle = _acquire_lock(_lock_path(config))
    except BlockingIOError:
        logger.warning(
            "Collector already running (lock=%s); exiting without overlap",
            _lock_path(config),
        )
        return EXIT_ALREADY_RUNNING

    try:
        if args.command == "collect":
            return run_scheduled_collect(config)
        return run_scheduled_reconcile(config)
    finally:
        if lock_handle is not None:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()


if __name__ == "__main__":
    sys.exit(main())
