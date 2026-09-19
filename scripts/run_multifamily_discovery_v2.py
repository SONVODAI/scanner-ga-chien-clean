"""
Run Multi-Family Discovery V2 (research-only).

Writes exclusively to data/multifamily_discovery_v2/.
Never invokes production discovery/challenger engines.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.multifamily_discovery_v2.experiments import run_v2_program
from modules.multifamily_discovery_v2.insight_compare import compare_with_learning_insight
from modules.multifamily_discovery_v2.report import render_report
from modules.multifamily_discovery_v2.storage import write_json, write_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-Family Discovery V2 research runner")
    parser.add_argument(
        "--artifact-dir",
        default=None,
        help="Optional override artifact directory (default data/multifamily_discovery_v2)",
    )
    args = parser.parse_args()
    artifact_base = Path(args.artifact_dir) if args.artifact_dir else None
    payload = run_v2_program(artifact_base=artifact_base)
    insight = compare_with_learning_insight(payload.get("scoreboard") or [])
    payload["_insight"] = insight
    write_json("insight_comparison.json", insight, base=artifact_base)
    report = render_report(payload)
    write_text("report.md", report, base=artifact_base)
    docs = REPO_ROOT / "docs" / "multifamily_discovery_v2_report.md"
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text(report, encoding="utf-8")
    print(report)
    if not payload.get("production_untouched"):
        print("PRODUCTION HASH VIOLATIONS:", payload.get("production_violations"), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
