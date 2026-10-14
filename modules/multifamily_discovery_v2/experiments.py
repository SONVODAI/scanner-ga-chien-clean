"""
Staged V2 family experiments and scoreboard. Isolated artifacts only.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from modules.multifamily_discovery_v2.contracts import (
    FAMILY_VERDICTS,
    INTERACTION_ENABLE_THREE_FEATURE,
    INTERACTION_MAX_CROSS_FAMILY_PAIR_TEMPLATES,
    NESTED_INCREMENTAL_REDUNDANT_EPS,
    V2_ENGINE_VERSION,
)
from modules.multifamily_discovery_v2.discovery import generate_templates, run_v2_discovery
from modules.multifamily_discovery_v2.feature_audit import run_feature_audit
from modules.multifamily_discovery_v2.oos_eval import evaluate_oos, split_panel
from modules.multifamily_discovery_v2.panel import build_v2_panel
from modules.multifamily_discovery_v2.registry import eligible_names_for_families, registry_to_dict
from modules.multifamily_discovery_v2.robustness import evaluate_candidates
from modules.multifamily_discovery_v2.storage import artifact_root, write_json


EXPERIMENT_SPECS: tuple[dict, ...] = (
    {
        "experiment_id": "A_control",
        "label": "CONTROL RS/RSI",
        "families": ("rs_rsi",),
        "include_cross_family_pairs": False,
    },
    {
        "experiment_id": "B_obv",
        "label": "RS/RSI + OBV",
        "families": ("rs_rsi", "obv"),
        "include_cross_family_pairs": True,
    },
    {
        "experiment_id": "C_volume",
        "label": "RS/RSI + Volume",
        "families": ("rs_rsi", "volume"),
        "include_cross_family_pairs": True,
    },
    {
        "experiment_id": "D_trend",
        "label": "RS/RSI + Trend/EMA-MA",
        "families": ("rs_rsi", "trend"),
        "include_cross_family_pairs": True,
    },
    {
        "experiment_id": "E_health",
        "label": "RS/RSI + Health/Group",
        "families": ("rs_rsi", "health_group"),
        "include_cross_family_pairs": True,
    },
)


def _file_digest(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_production_hashes(repo_root: Path) -> Dict[str, Optional[str]]:
    hashes: Dict[str, Optional[str]] = {}
    earn = repo_root / "data" / "earning_learning"
    if earn.exists():
        for path in sorted(earn.glob("*")):
            if path.is_file():
                hashes[str(path.relative_to(repo_root))] = _file_digest(path)
    edge = repo_root / "data" / "edge_research"
    if edge.exists():
        for path in sorted(edge.rglob("*")):
            if path.is_file():
                hashes[str(path.relative_to(repo_root))] = _file_digest(path)
    return hashes


def assert_production_unchanged(before: Dict[str, Optional[str]], after: Dict[str, Optional[str]]) -> List[str]:
    violations: List[str] = []
    for key, digest in before.items():
        if after.get(key) != digest:
            violations.append(key)
    extra = set(after) - set(before)
    # New files under production dirs are also violations.
    for key in extra:
        if key.startswith("data/earning_learning/") or key.startswith("data/edge_research/"):
            violations.append(f"new:{key}")
    return violations


def _nested_lifts(candidates: Sequence[Dict[str, Any]]) -> List[float]:
    lifts: List[float] = []
    for cand in candidates:
        nested = cand.get("nested_rs_incremental") or {}
        val = nested.get("incremental_median")
        if val is not None:
            lifts.append(float(val))
    return lifts


def _oos_medians(oos: Dict[str, Any], horizon: str) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    key = {
        "T3": "T3",
        "T5": "T5",
        "T10": "T10",
    }[horizon]
    for ev in oos.get("evaluations") or []:
        hz = (ev.get("oos_horizons") or {}).get(key) or {}
        if hz.get("insufficient"):
            out.append(None)
        else:
            out.append((hz.get("incremental") or {}).get("incremental_median"))
    return out


def _family_coverage(audit: Dict[str, Any], family: str) -> str:
    feats = [f for f in audit.get("features", []) if f.get("family") == family and f.get("intended_search_eligible")]
    if not feats:
        return "n/a"
    miss = [f.get("missing_pct") or 0 for f in feats]
    deg = any(f.get("degenerate") for f in feats)
    if deg and all(f.get("degenerate") for f in feats):
        return "DEGENERATE"
    return f"missing~{max(miss):.1f}%"


def family_verdict(
    *,
    extra_family: str,
    audit: Dict[str, Any],
    discovery: Dict[str, Any],
    robust: Dict[str, Any],
    oos: Dict[str, Any],
) -> str:
    extra_feats = [
        f
        for f in audit.get("features", [])
        if f.get("family") == extra_family and f.get("intended_search_eligible")
    ]
    if extra_feats and all(f.get("degenerate") for f in extra_feats):
        return "DEGENERATE"
    if discovery.get("unique_hypotheses", 0) == 0:
        return "INSUFFICIENT_DATA"
    if discovery.get("raw_signal_count", 0) == 0 and discovery.get("fdr_survivors", 0) == 0:
        if discovery.get("rejected_insufficient_sample", 0) >= discovery.get("unique_hypotheses", 1) * 0.9:
            return "INSUFFICIENT_DATA"
        return "REJECT"

    extra_survivors = [
        c
        for c in discovery.get("all_fdr_survivors") or []
        if extra_family in (c.get("families") or [])
    ]
    lifts = _nested_lifts(extra_survivors)
    oos_t5 = [v for v in _oos_medians(oos, "T5") if v is not None]
    n_pass = robust.get("robustness_pass", 0)

    if extra_family == "rs_rsi":
        if discovery.get("fdr_survivors", 0) == 0:
            return "WEAK" if discovery.get("raw_signal_count", 0) else "REJECT"
        if n_pass == 0 and robust.get("robustness_fragile", 0) == 0:
            return "WEAK"
        if oos_t5 and max(oos_t5) <= 0:
            return "WEAK"
        return "PROMISING" if n_pass or robust.get("robustness_fragile", 0) else "WEAK"

    if discovery.get("fdr_survivors", 0) == 0:
        return "WEAK" if discovery.get("raw_signal_count", 0) else "REJECT"
    if extra_survivors and lifts and max(lifts) <= NESTED_INCREMENTAL_REDUNDANT_EPS:
        return "REDUNDANT"
    if extra_survivors and not lifts:
        # Family-containing survivors exist but nested RS comparison unavailable (family-only singles).
        pass
    if oos_t5 and all(v is not None and v <= 0 for v in oos_t5):
        return "WEAK"
    if n_pass == 0 and robust.get("robustness_fragile", 0) == 0:
        return "WEAK"
    if extra_survivors and lifts and max(lifts) > NESTED_INCREMENTAL_REDUNDANT_EPS:
        if n_pass or robust.get("robustness_fragile", 0):
            return "PROMISING"
        return "WEAK"
    if extra_survivors:
        return "WEAK"
    return "REDUNDANT"


def _context_summary(candidates: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not candidates:
        return {"n_transitions": 0, "top_transition_share": None, "transitions": {}}
    counts: Dict[str, int] = {}
    for c in candidates:
        key = str(c.get("market_transition", ""))
        counts[key] = counts.get(key, 0) + 1
    total = sum(counts.values())
    top = max(counts.values()) if counts else 0
    return {
        "n_transitions": len(counts),
        "top_transition_share": round(top / total, 4) if total else None,
        "transitions": counts,
        "regime_specific": bool(len(counts) == 1),
        "note": (
            "Candidates are stratified by research_market_transition; "
            "a single-transition result is regime-specific, not universal."
        ),
    }


def run_one_experiment(
    spec: Dict[str, Any],
    discovery_panel,
    oos_panel,
    *,
    demoted: Sequence[str],
    full_panel=None,
) -> Dict[str, Any]:
    discovery = run_v2_discovery(
        discovery_panel,
        families=spec["families"],
        experiment_id=spec["experiment_id"],
        demoted=demoted,
        include_cross_family_pairs=bool(spec.get("include_cross_family_pairs", True)),
        include_within_new_family_pairs=bool(spec.get("include_within_new_family_pairs", False)),
        enable_three_feature=bool(spec.get("enable_three_feature", False)),
    )
    survivors = discovery.get("all_fdr_survivors") or []
    robust = evaluate_candidates(discovery_panel, survivors)
    oos = evaluate_oos(oos_panel, survivors)
    extra_family = spec["families"][-1]
    return {
        "spec": spec,
        "discovery": discovery,
        "robustness": robust,
        "oos": oos,
        "market_context": _context_summary(survivors),
        "extra_family": extra_family,
    }


def scoreboard_row(spec: Dict[str, Any], packed: Dict[str, Any], audit: Dict[str, Any]) -> Dict[str, Any]:
    extra = packed["extra_family"]
    disc = packed["discovery"]
    rob = packed["robustness"]
    oos = packed["oos"]
    extra_survivors = [
        c for c in disc.get("all_fdr_survivors") or [] if extra in (c.get("families") or [])
    ]
    lifts = _nested_lifts(extra_survivors)
    oos_t3 = _oos_medians(oos, "T3")
    oos_t5 = _oos_medians(oos, "T5")
    oos_t10 = _oos_medians(oos, "T10")

    def _fmt(vals: List[Optional[float]]) -> Optional[float]:
        num = [v for v in vals if v is not None]
        if not num:
            return None
        return round(sorted(num)[len(num) // 2], 4)

    verdict = family_verdict(
        extra_family=extra, audit=audit, discovery=disc, robust=rob, oos=oos
    )
    conc = packed.get("market_context") or {}
    return {
        "family": extra if extra != "rs_rsi" else "rs_rsi (CONTROL)",
        "experiment_id": spec["experiment_id"],
        "coverage": _family_coverage(audit, extra),
        "hypotheses_tested": disc.get("unique_hypotheses"),
        "templates_generated": disc.get("templates_generated"),
        "fdr_survivors": disc.get("fdr_survivors"),
        "family_containing_survivors": len(extra_survivors) if extra != "rs_rsi" else disc.get("fdr_survivors"),
        "robust_pass": rob.get("robustness_pass"),
        "robust_fragile": rob.get("robustness_fragile"),
        "robust_reject": rob.get("robustness_reject"),
        "oos_t3_median_inc": _fmt(oos_t3),
        "oos_t5_median_inc": _fmt(oos_t5),
        "oos_t10_median_inc": _fmt(oos_t10),
        "nested_vs_rs_max_inc_median": round(max(lifts), 4) if lifts else None,
        "nested_vs_rs_median_inc": round(sorted(lifts)[len(lifts) // 2], 4) if lifts else None,
        "concentration_risk": conc.get("top_transition_share"),
        "regime_specific": conc.get("regime_specific"),
        "verdict": verdict if verdict in FAMILY_VERDICTS else "WEAK",
    }


def maybe_run_interactions(
    promising_extra: Sequence[str],
    discovery_panel,
    oos_panel,
    *,
    demoted: Sequence[str],
) -> Optional[Dict[str, Any]]:
    extra = [f for f in promising_extra if f != "rs_rsi"]
    if len(extra) < 1:
        return {
            "skipped": True,
            "reason": "no_non_rs_family_passed_screening",
        }
    families = ("rs_rsi",) + tuple(extra)
    features = eligible_names_for_families(families, demoted=demoted)
    try:
        templates = generate_templates(
            features,
            include_control_pairs=True,
            include_cross_family_pairs=True,
            include_within_new_family_pairs=True,
            enable_three_feature=INTERACTION_ENABLE_THREE_FEATURE,
        )
    except RuntimeError as exc:
        return {"skipped": True, "reason": str(exc)}
    cross_only = [
        t
        for t in templates
        if len({c.family for c in t}) >= 2 and any(c.family != "rs_rsi" for c in t)
    ]
    if len(templates) > INTERACTION_MAX_CROSS_FAMILY_PAIR_TEMPLATES + 154:
        return {
            "skipped": True,
            "reason": "interaction_cardinality_budget",
            "templates_generated": len(templates),
            "budget": INTERACTION_MAX_CROSS_FAMILY_PAIR_TEMPLATES,
        }
    spec = {
        "experiment_id": "F_interaction_screened",
        "label": "Screened family interactions",
        "families": families,
        "include_cross_family_pairs": True,
        "include_within_new_family_pairs": True,
        "enable_three_feature": INTERACTION_ENABLE_THREE_FEATURE,
    }
    packed = run_one_experiment(spec, discovery_panel, oos_panel, demoted=demoted)
    packed["interaction_template_count"] = len(templates)
    packed["cross_family_template_count"] = len(cross_only)
    packed["three_feature_enabled"] = INTERACTION_ENABLE_THREE_FEATURE
    return packed


def run_v2_program(*, artifact_base: Optional[Path] = None) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    before = snapshot_production_hashes(repo_root)
    root = artifact_root(artifact_base)

    audit = run_feature_audit()
    write_json("feature_audit.json", audit, base=root)
    write_json("registry.json", registry_to_dict(), base=root)

    demoted = list(audit.get("demoted_from_search") or [])
    panel = build_v2_panel()
    split = split_panel(panel)
    write_json(
        "split_meta.json",
        {
            "discovery_end_date": split.discovery_end_date,
            "oos_start_date": split.oos_start_date,
            "embargo_trading_days": split.embargo_trading_days,
            "discovery_rows": int(len(split.discovery_panel)),
            "oos_rows": int(len(split.oos_panel)),
            "engine_version": V2_ENGINE_VERSION,
        },
        base=root,
    )

    experiments: Dict[str, Any] = {}
    scoreboard: List[Dict[str, Any]] = []
    for spec in EXPERIMENT_SPECS:
        packed = run_one_experiment(
            spec, split.discovery_panel, split.oos_panel, demoted=demoted
        )
        experiments[spec["experiment_id"]] = packed
        write_json(f"experiments/{spec['experiment_id']}.json", packed, base=root)
        scoreboard.append(scoreboard_row(spec, packed, audit))

    promising = [
        row["family"].replace(" (CONTROL)", "")
        for row in scoreboard
        if row["verdict"] == "PROMISING"
    ]
    interaction = maybe_run_interactions(
        promising, split.discovery_panel, split.oos_panel, demoted=demoted
    )
    if interaction:
        write_json("experiments/F_interaction.json", interaction, base=root)

    after = snapshot_production_hashes(repo_root)
    violations = assert_production_unchanged(before, after)
    payload = {
        "engine_version": V2_ENGINE_VERSION,
        "demoted_features": demoted,
        "scoreboard": scoreboard,
        "promising_families": promising,
        "interaction": {
            "skipped": interaction.get("skipped") if interaction else True,
            "reason": (interaction or {}).get("reason"),
            "experiment_id": (interaction or {}).get("discovery", {}).get("experiment_id")
            if interaction and not interaction.get("skipped")
            else None,
        },
        "production_untouched": len(violations) == 0,
        "production_violations": violations,
        "split": {
            "discovery_end_date": split.discovery_end_date,
            "oos_start_date": split.oos_start_date,
            "discovery_rows": int(len(split.discovery_panel)),
            "oos_rows": int(len(split.oos_panel)),
        },
    }
    write_json("scoreboard.json", payload, base=root)
    payload["_experiments"] = experiments
    payload["_audit"] = audit
    payload["_interaction_full"] = interaction
    payload["_panel_n"] = int(len(panel))
    return payload
