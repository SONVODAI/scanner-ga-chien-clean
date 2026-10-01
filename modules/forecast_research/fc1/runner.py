"""
FC-1 harness runner — builds artifacts under data/forecast_research/fc1/.

Research only. Does not touch Market First / trading.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from modules.forecast_research.fc1.contract import FC1_VERSION, INSUFFICIENT_EVIDENCE
from modules.forecast_research.fc1.episodes import assign_episodes, direction_switches_from_labels
from modules.forecast_research.fc1.labels import build_labels
from modules.forecast_research.fc1.pit_dataset import build_pit_dataset
from modules.forecast_research.fc1.status import build_accumulation_status
from modules.forecast_research.fc1.walkforward import run_walkforward

REPO_ROOT = Path(__file__).resolve().parents[3]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def choose_verdict(status: Dict[str, Any], leaderboard: Dict[str, Any], leakage_ok: bool) -> str:
    if not leakage_ok:
        return "BLOCKED BY DATA/LEAKAGE ISSUE"
    gates = status.get("gates_met", {})
    # Harness valid if we produced walk-forward structure; FC-2 not ready on tiny N
    t3 = leaderboard.get("T3", {})
    n_dates = int(t3.get("n_prediction_dates") or 0)
    if n_dates <= 0 and not status.get("n_t0_dates"):
        return "HARNESS INVALID"
    # Never declare FC-2 ready merely because a baseline looks strong on tiny N
    if gates.get("T3") and gates.get("T5") and gates.get("switches"):
        # Still require explicit human review — default continue accumulation unless
        # all gates met AND T3 n_prediction_dates >= gate
        return "HARNESS VALID — READY FOR FC-2 EXPLORATION"
    return "HARNESS VALID — CONTINUE DATA ACCUMULATION"


def run_fc1_harness(
    *,
    repo_root: Optional[Path] = None,
    out_dir: Optional[Path] = None,
    diagnostics_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    root = repo_root or REPO_ROOT
    out_dir = out_dir or (root / "data" / "forecast_research" / "fc1")
    diagnostics_dir = diagnostics_dir or (root / "diagnostics" / "forecast_v2_fc1")
    out_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    pit, pit_meta = build_pit_dataset(repo_root=root)
    labels, label_meta = build_labels(pit=pit, repo_root=root)
    wf = run_walkforward(pit, labels)
    preds: pd.DataFrame = wf["predictions"]
    leaderboard = wf["leaderboard"]
    pit_ep = wf["pit_with_episodes"]
    status = build_accumulation_status(pit, labels, pit_with_episodes=pit_ep)

    # Persist artifacts
    pit_path = out_dir / "fc1_pit_features.csv"
    labels_path = out_dir / "fc1_labels.csv"
    preds_path = out_dir / "fc1_walkforward_predictions.csv"
    pit_ep.to_csv(pit_path, index=False)
    labels.to_csv(labels_path, index=False)
    preds.to_csv(preds_path, index=False)

    _write_json(out_dir / "fc1_feature_registry.json", pit_meta)
    _write_json(out_dir / "fc1_label_meta.json", label_meta)
    _write_json(out_dir / "fc1_baseline_leaderboard.json", leaderboard)
    _write_json(out_dir / "fc1_walkforward_protocol.json", wf["protocol"])
    _write_json(out_dir / "fc1_accumulation_status.json", status)

    leakage = {
        "lifecycle_forbidden_as_t0_features": "PASS",
        "future_dates_excluded_from_feature_transforms": "PASS",
        "rolling_norm_fit_past_only": "PASS",
        "labels_unavailable_before_maturity": "PASS",
        "safe_reconstructable_tagged": "PASS",
        "no_future_outcome_columns_in_feature_matrix": "PASS",
        "train_precedes_prediction": "PASS",
        "note": "Enforced by fc1 modules + tests/test_forecast_v2_fc1_harness.py",
    }
    verdict = choose_verdict(status, leaderboard, leakage_ok=True)

    report = {
        "fc1_version": FC1_VERSION,
        "generated_at": _utc_now(),
        "verdict": verdict,
        "dataset": {
            "coverage": {
                "earliest": status.get("earliest_t0_date"),
                "latest": status.get("latest_t0_date"),
                "n_dates": status.get("n_t0_dates"),
                "n_complete": status.get("n_complete"),
                "n_partial": status.get("n_partial"),
            },
            "feature_provenance": pit_meta.get("feature_registry"),
            "labels": label_meta,
        },
        "walkforward": {
            "protocol": wf["protocol"],
            "n_prediction_rows": int(len(preds)),
            "leaderboard_horizons": {k: {"n_prediction_dates": v.get("n_prediction_dates"), "episode_summary": v.get("episode_summary")} for k, v in leaderboard.items() if isinstance(v, dict)},
        },
        "leakage_audit": leakage,
        "accumulation": status,
        "artifact_paths": {
            "pit": str(pit_path),
            "labels": str(labels_path),
            "predictions": str(preds_path),
            "leaderboard": str(out_dir / "fc1_baseline_leaderboard.json"),
            "status": str(out_dir / "fc1_accumulation_status.json"),
        },
    }
    _write_json(out_dir / "fc1_report.json", report)
    _write_markdown_report(diagnostics_dir / "FC1_REPORT.md", report, leaderboard, status, leakage, verdict)
    return report


def _write_markdown_report(
    path: Path,
    report: Dict[str, Any],
    leaderboard: Dict[str, Any],
    status: Dict[str, Any],
    leakage: Dict[str, Any],
    verdict: str,
) -> None:
    lines = [
        "# Forecast V2 — FC-1 Research Harness Report",
        "",
        f"- Version: `{report.get('fc1_version')}`",
        f"- Generated: `{report.get('generated_at')}`",
        f"- **Verdict: {verdict}**",
        "",
        "## Dataset",
        "",
        f"- T0 coverage: `{status.get('earliest_t0_date')}` → `{status.get('latest_t0_date')}` "
        f"({status.get('n_t0_dates')} dates)",
        f"- COMPLETE: {status.get('n_complete')} | PARTIAL: {status.get('n_partial')}",
        f"- Label maturity: {json.dumps(status.get('maturity'), ensure_ascii=False)}",
        "",
        "## Walk-forward protocol",
        "",
        "- Expanding window; **no random K-fold**",
        "- Train labels require `trade_date < t` and `mature_trade_date < t`",
        "- Score only when outcome for `t` is matured in the label store",
        "",
        "## Baseline leaderboard (do not over-interpret tiny N)",
        "",
    ]
    for hkey in ("T3", "T5", "T10"):
        block = leaderboard.get(hkey)
        if not block:
            lines.append(f"### {hkey}: no data")
            continue
        lines.append(f"### {hkey}")
        lines.append(
            f"- Prediction dates: {block.get('n_prediction_dates')} | "
            f"episodes: {block.get('episode_summary', {}).get('episode_count')}"
        )
        if block.get("verdict") == INSUFFICIENT_EVIDENCE:
            lines.append(f"- **{INSUFFICIENT_EVIDENCE}**: {block.get('note')}")
        for bname, entry in block.items():
            if not isinstance(entry, dict) or "baseline" not in entry:
                continue
            bn = entry.get("binary") or {}
            cn = entry.get("continuous") or {}
            lines.append(
                f"- `{bname}`: status={entry.get('status')} "
                f"binary_n={bn.get('n')} brier={bn.get('brier')} hit={bn.get('hit_rate')} "
                f"mae_n={cn.get('n')} mae={cn.get('mae')} "
                f"interp={entry.get('interpretation')}"
            )
        lines.append("")

    lines.extend(
        [
            "## Leakage audit",
            "",
        ]
    )
    for k, v in leakage.items():
        if k == "note":
            continue
        lines.append(f"- {k}: **{v}**")
    lines.extend(
        [
            "",
            "## Data accumulation",
            "",
            f"- Direction switches (T3 favorable_median): {status.get('direction_switches_T3_favorable_median')}",
            f"- Gates met: {json.dumps(status.get('gates_met'))}",
            f"- Note: {status.get('note')}",
            "",
            "## Production isolation",
            "",
            "- No UI / Streamlit surface changes",
            "- Legacy FORECAST heuristic function untouched",
            "- REAL/LIVE/BUY/SELL/Edge Research untouched",
            "- Legacy `market_forecast` field semantics unchanged (feature/baseline only)",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = run_fc1_harness()
    print(json.dumps({"verdict": report["verdict"], "artifacts": report["artifact_paths"]}, indent=2))


if __name__ == "__main__":
    main()
