"""
Phase 3K.2 — CLI entrypoint for future scheduled daily runs (NOT activated).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from modules.edge_research.adapters import build_research_panel
from modules.edge_research.opr_bridge.production_daily_run_orchestrator import (
    run_production_daily_research,
)
from modules.edge_research.opr_bridge.production_daily_run_records import (
    BACKFILL_NON_FORWARD,
    LIVE_FORWARD,
    RunDisposition,
)
from modules.edge_research.opr_bridge.production_scheduling_contract import build_scheduling_contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Production daily research run (3K.2)")
    parser.add_argument("--trade-date", required=True, help="Target trade date YYYY-MM-DD")
    parser.add_argument(
        "--mode",
        default=BACKFILL_NON_FORWARD,
        choices=[BACKFILL_NON_FORWARD, LIVE_FORWARD, "HISTORICAL_REPLAY_TEST"],
    )
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--scheduling-contract", action="store_true")
    args = parser.parse_args(argv)

    if args.scheduling_contract:
        print(json.dumps(build_scheduling_contract(), indent=2))
        return 0

    panel = build_research_panel()
    data_dir = Path(args.data_dir) if args.data_dir else None
    result = run_production_daily_research(
        panel,
        target_trade_date=args.trade_date,
        run_mode=args.mode,
        data_dir=data_dir,
    )

    disposition = result.get("run", {}).get("run_disposition", "FAILED_CLOSED")
    exit_map = {
        RunDisposition.SUCCESS.value: 0,
        RunDisposition.SKIPPED_NON_TRADING_DAY.value: 3,
        RunDisposition.WAITING_FOR_DATA.value: 2,
        RunDisposition.PARTIAL_RECOVERABLE.value: 4,
        RunDisposition.FAILED_CLOSED.value: 1,
    }
    print(json.dumps(result.get("manifest") or result.get("run"), indent=2, default=str))
    return exit_map.get(disposition, 1)


if __name__ == "__main__":
    raise SystemExit(main())
