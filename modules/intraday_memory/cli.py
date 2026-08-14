#!/usr/bin/env python3
"""
CLI entry point for Mr.BOT Intraday Memory V1A collector.

Usage examples:
  python -m modules.intraday_memory.cli collect --session 2026-08-13
  python -m modules.intraday_memory.cli reconcile --session 2026-08-13
  python -m modules.intraday_memory.cli bootstrap --start 2026-08-10 --end 2026-08-13 --symbols HPG,VNM

No Streamlit dependency. Runnable from cron, GitHub Actions, or VPS.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime

from modules.intraday_memory.collector import IntradayCollector
from modules.intraday_memory.config import IntradayConfig


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_symbols(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [s.strip().upper() for s in value.split(",") if s.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mr.BOT Intraday Memory V1A collector",
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="Override MRBOT_INTRADAY_DATA_ROOT",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated symbols (default: production WATCHLIST)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_collect = sub.add_parser("collect", help="Collect single session")
    p_collect.add_argument(
        "--session", required=True, type=_parse_date,
        help="Session date YYYY-MM-DD",
    )

    p_reconcile = sub.add_parser("reconcile", help="Reconcile session")
    p_reconcile.add_argument(
        "--session", required=True, type=_parse_date,
        help="Session date YYYY-MM-DD",
    )

    p_bootstrap = sub.add_parser("bootstrap", help="Bootstrap date range")
    p_bootstrap.add_argument("--start", required=True, type=_parse_date)
    p_bootstrap.add_argument("--end", required=True, type=_parse_date)

    p_universe = sub.add_parser("universe", help="Print production universe")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    config = IntradayConfig.from_env()
    if args.data_root:
        from dataclasses import replace
        config = replace(config, data_root=__import__("pathlib").Path(args.data_root))

    symbols = _parse_symbols(args.symbols)
    collector = IntradayCollector(config)

    if args.command == "universe":
        from modules.intraday_memory.universe import load_production_universe
        syms = load_production_universe(config.app_py_path)
        print(json.dumps({"count": len(syms), "symbols": list(syms)}, indent=2))
        return 0

    if args.command == "collect":
        manifest = collector.collect_session(args.session, symbols)
        print(manifest.summary_text())
        print(json.dumps(manifest.to_dict(), indent=2))
        return 1 if manifest.symbols_failed else 0

    if args.command == "reconcile":
        manifest, report = collector.reconcile(args.session, symbols)
        print(manifest.summary_text())
        print(json.dumps({"manifest": manifest.to_dict(), "report": report}, indent=2))
        return 1 if manifest.symbols_failed else 0

    if args.command == "bootstrap":
        manifest = collector.bootstrap_range(args.start, args.end, symbols)
        print(manifest.summary_text())
        print(json.dumps(manifest.to_dict(), indent=2))
        return 1 if manifest.symbols_failed else 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
