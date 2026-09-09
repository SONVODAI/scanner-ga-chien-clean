"""CLI: python -m modules.actionable_research --trade-date YYYY-MM-DD

Not a new scheduler. Intended to be invoked from the existing daily pipeline
or operator replay. Read-only vs scientific stores.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from modules.actionable_research.engine import fuse_session
from modules.actionable_research.paths import FusionPaths


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Mr.BOT Actionable Research Fusion (RESEARCH ONLY)")
    p.add_argument("--trade-date", required=True, help="YYYY-MM-DD session date")
    p.add_argument("--cutoff", default=None, help="PIT cutoff ISO timestamp (VN or aware)")
    p.add_argument("--repo-root", default=None)
    p.add_argument("--artifact-root", default=None)
    p.add_argument("--camera-root", default=None)
    p.add_argument("--edge-data-dir", default=None)
    p.add_argument("--no-persist", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = FusionPaths(
        repo_root=Path(args.repo_root) if args.repo_root else FusionPaths().resolved_repo(),
        artifact_root=Path(args.artifact_root) if args.artifact_root else None,
        camera_root=Path(args.camera_root) if args.camera_root else None,
        edge_data_dir=Path(args.edge_data_dir) if args.edge_data_dir else None,
    )
    result = fuse_session(
        args.trade_date,
        paths=paths,
        cutoff=args.cutoff,
        persist=not args.no_persist,
    )
    summary = {
        "trade_date": result.get("trade_date"),
        "session_status": result.get("session_status"),
        "authority": result.get("authority"),
        "universe_count": result.get("universe_count"),
        "notable_count": result.get("notable_count"),
        "headline_vi": result.get("headline_vi"),
        "idempotent_replay": result.get("idempotent_replay"),
        "camera_cutoff_timestamp": result.get("camera_cutoff_timestamp"),
    }
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
