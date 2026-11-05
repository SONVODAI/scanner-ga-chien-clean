"""
Frozen hypothesis persistence and safe OOS entry (Phase A).

A candidate may freeze only when Challenger PASS + READY_FOR_OOS and the
condition/spec can be reconstructed faithfully. FRAGILE / REJECT never freeze.
Rerunning freeze is idempotent: the same unchanged hypothesis does not get a
second different frozen spec.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from modules.edge_research.contracts import (
    FEATURE_BUCKET_CONFIG_VERSION,
    FREEZE_CHALLENGER_PENDING,
    FREEZE_ELIGIBLE,
    FREEZE_FRAGILE,
    FREEZE_HISTORICAL_ONLY,
    FREEZE_NON_FREEZABLE,
    FREEZE_REJECT,
    FROZEN_SPECS_DIRNAME,
    GUARDRAILS_CONFIG_VERSION,
    MARKET_STATE_CONFIG_VERSION,
    OOS_MODE_HOLDOUT_SPLIT,
    OOS_MODE_PROSPECTIVE_AFTER_FREEZE,
    OOS_STATUS_PENDING,
    ROBUSTNESS_FRAGILE,
    ROBUSTNESS_PASS,
    ROBUSTNESS_REJECT,
)
from modules.edge_research.discovery import canonical_condition_key, canonical_condition_text
from modules.edge_research.hypothesis import (
    FrozenHypothesisSpec,
    ScientificStatus,
    build_frozen_hypothesis_spec,
    canonical_feature_clauses,
)
from modules.edge_research.oos import DEFAULT_EMBARGO_TRADING_DAYS, unique_trading_sessions
from modules.edge_research.oos_policy import OOS_EMBARGO_TRADING_SESSIONS
from modules.edge_research.robustness import reconstruct_clauses_from_ledger_row
from modules.edge_research.storage import (
    ensure_storage,
    read_challenger_run,
    read_discovery_run,
    read_ledger,
    resolve_data_dir,
)


class FreezeError(ValueError):
    """Spec reconstruction or freeze contract failed safely."""


@dataclass
class FreezeDecision:
    edge_id: str
    eligible: bool
    eligibility: str
    reason: str
    spec: Optional[FrozenHypothesisSpec] = None
    reused_existing: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "eligible": self.eligible,
            "eligibility": self.eligibility,
            "reason": self.reason,
            "hypothesis_id": self.spec.hypothesis_id if self.spec else "",
            "spec_hash": self.spec.spec_hash if self.spec else "",
            "reused_existing": self.reused_existing,
        }


@dataclass
class FreezeRunResult:
    frozen: List[FreezeDecision] = field(default_factory=list)
    skipped: List[FreezeDecision] = field(default_factory=list)

    @property
    def frozen_count(self) -> int:
        return sum(1 for d in self.frozen if d.eligible)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frozen": [d.to_dict() for d in self.frozen],
            "skipped": [d.to_dict() for d in self.skipped],
            "frozen_count": self.frozen_count,
            "skipped_count": len(self.skipped),
        }


def frozen_specs_dir(data_dir: Optional[Path] = None) -> Path:
    root = ensure_storage(data_dir)
    path = root / FROZEN_SPECS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def frozen_spec_path(hypothesis_id: str, data_dir: Optional[Path] = None) -> Path:
    return frozen_specs_dir(data_dir) / f"{hypothesis_id}.json"


def load_frozen_spec(hypothesis_id: str, data_dir: Optional[Path] = None) -> Optional[FrozenHypothesisSpec]:
    path = frozen_spec_path(hypothesis_id, data_dir)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return FrozenHypothesisSpec.from_dict(payload)


def load_all_frozen_specs(data_dir: Optional[Path] = None) -> List[FrozenHypothesisSpec]:
    specs: List[FrozenHypothesisSpec] = []
    root = frozen_specs_dir(data_dir)
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            specs.append(FrozenHypothesisSpec.from_dict(payload))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return specs


def persist_frozen_spec(spec: FrozenHypothesisSpec, data_dir: Optional[Path] = None) -> Tuple[Path, bool]:
    """
    Write spec if absent. If present with the same scientific identity, reuse it.

    Returns (path, reused_existing).
    """
    path = frozen_spec_path(spec.hypothesis_id, data_dir)
    if path.exists():
        existing = FrozenHypothesisSpec.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if existing.canonical_identity_json() != spec.canonical_identity_json():
            raise FreezeError(
                f"Frozen spec identity conflict for {spec.hypothesis_id}: "
                "a materially different hypothesis cannot reuse this id"
            )
        return path, True
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(spec.serialize(), encoding="utf-8")
    tmp.replace(path)
    return path, False


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() in ("", "nan", "None", "<NA>")


def _notes_guardrails(row: pd.Series) -> Dict[str, Any]:
    notes_val = row.get("notes", "")
    if _is_missing(notes_val):
        return {}
    raw = str(notes_val).strip()
    if not raw.startswith("{"):
        return {}
    try:
        return json.loads(raw).get("guardrails", {}) or {}
    except json.JSONDecodeError:
        return {}


def reconstruction_matches_ledger(row: pd.Series) -> Tuple[bool, str, Tuple[Any, ...]]:
    """
    Faithful reconstruction required for freeze.

    Old EDGE-XXXX rows that only store feature_1/2 cannot be guessed into a
    3-clause spec. Mismatch → historical-only / non-freezable.
    """
    clauses = reconstruct_clauses_from_ledger_row(row)
    if not clauses:
        return False, "reconstruction_empty_clauses", ()
    text = canonical_condition_text(clauses)
    key = f"{row.get('market_transition', '')}|{canonical_condition_key(clauses)}"
    ledger_text = "" if _is_missing(row.get("condition_text")) else str(row.get("condition_text")).strip()
    ledger_key = "" if _is_missing(row.get("condition_key")) else str(row.get("condition_key")).strip()
    if ledger_text and text != ledger_text:
        return False, "reconstruction_condition_text_mismatch", clauses
    if ledger_key and ledger_key != key and not ledger_key.endswith(canonical_condition_key(clauses)):
        return False, "reconstruction_condition_key_mismatch", clauses
    return True, "ok", clauses


def classify_freeze_eligibility(row: pd.Series) -> FreezeDecision:
    edge_id = str(row.get("edge_id", ""))
    robustness = "" if _is_missing(row.get("robustness_status")) else str(row.get("robustness_status"))
    scientific = "" if _is_missing(row.get("scientific_status")) else str(row.get("scientific_status"))

    if robustness == ROBUSTNESS_FRAGILE or scientific == ScientificStatus.FRAGILE.value:
        return FreezeDecision(edge_id, False, FREEZE_FRAGILE, "FRAGILE cannot enter OOS")
    if robustness == ROBUSTNESS_REJECT or scientific == ScientificStatus.REJECTED.value:
        return FreezeDecision(edge_id, False, FREEZE_REJECT, "REJECT cannot enter OOS")
    if robustness in ("", "nan") or robustness not in (ROBUSTNESS_PASS, ROBUSTNESS_FRAGILE, ROBUSTNESS_REJECT):
        return FreezeDecision(
            edge_id,
            False,
            FREEZE_CHALLENGER_PENDING,
            "Challenger not run; no OOS until Challenger eligibility",
        )
    if robustness != ROBUSTNESS_PASS:
        return FreezeDecision(edge_id, False, FREEZE_NON_FREEZABLE, f"robustness_status={robustness}")
    if scientific and scientific not in (
        ScientificStatus.READY_FOR_OOS.value,
        ScientificStatus.SPEC_FROZEN.value,
        ScientificStatus.OOS_PENDING.value,
        ScientificStatus.OOS_PASS.value,
        ScientificStatus.OOS_FAIL.value,
        ScientificStatus.OOS_INCONCLUSIVE.value,
        "",
    ):
        return FreezeDecision(
            edge_id,
            False,
            FREEZE_NON_FREEZABLE,
            f"scientific_status={scientific} is not READY_FOR_OOS",
        )
    if scientific in ("", "nan", "None") and robustness == ROBUSTNESS_PASS:
        # Legacy PASS rows without persisted scientific_status: treat as READY_FOR_OOS
        # only after reconstruction succeeds; Challenger PASS still is not validated.
        pass
    elif scientific not in (
        ScientificStatus.READY_FOR_OOS.value,
        ScientificStatus.SPEC_FROZEN.value,
        ScientificStatus.OOS_PENDING.value,
        "",
    ) and scientific not in (
        ScientificStatus.OOS_PASS.value,
        ScientificStatus.OOS_FAIL.value,
        ScientificStatus.OOS_INCONCLUSIVE.value,
    ):
        return FreezeDecision(
            edge_id,
            False,
            FREEZE_NON_FREEZABLE,
            f"scientific_status={scientific} cannot freeze",
        )

    ok, reason, clauses = reconstruction_matches_ledger(row)
    if not ok:
        return FreezeDecision(edge_id, False, FREEZE_HISTORICAL_ONLY, reason)

    if scientific in (
        ScientificStatus.OOS_PASS.value,
        ScientificStatus.OOS_FAIL.value,
        ScientificStatus.OOS_INCONCLUSIVE.value,
        ScientificStatus.SPEC_FROZEN.value,
        ScientificStatus.OOS_PENDING.value,
    ) or (not _is_missing(row.get("hypothesis_id")) and not _is_missing(row.get("frozen_spec_hash"))):
        return FreezeDecision(edge_id, True, FREEZE_ELIGIBLE, "already_frozen_or_oos", spec=None)

    return FreezeDecision(edge_id, True, FREEZE_ELIGIBLE, "READY_FOR_OOS reconstructable")


def _resolve_oos_mode(row: pd.Series, discovery: Dict[str, Any]) -> Tuple[str, str, bool]:
    """
    New discovery architecture with a chronological holdout may use HOLDOUT_SPLIT.
    Existing historical candidates searched on already-seen history must use
    PROSPECTIVE_AFTER_FREEZE — never a fake retrospective tail split.
    """
    holdout = bool(discovery.get("holdout_applied"))
    disc_end = str(discovery.get("discovery_end_date") or "")
    row_end = "" if _is_missing(row.get("discovery_end_date")) else str(row.get("discovery_end_date"))
    oos_start = str(discovery.get("oos_start_date") or "")
    if holdout and disc_end and (not row_end or row_end == disc_end) and oos_start:
        return OOS_MODE_HOLDOUT_SPLIT, oos_start, True
    return OOS_MODE_PROSPECTIVE_AFTER_FREEZE, "", False


def build_spec_for_ledger_row(
    row: pd.Series,
    *,
    data_cutoff_date: str,
    discovery: Optional[Dict[str, Any]] = None,
    challenger: Optional[Dict[str, Any]] = None,
    freeze_timestamp: Optional[str] = None,
) -> FrozenHypothesisSpec:
    ok, reason, clauses = reconstruction_matches_ledger(row)
    if not ok:
        raise FreezeError(f"{row.get('edge_id')}: {reason}")
    discovery = discovery or {}
    challenger = challenger or {}
    oos_mode, oos_start, holdout = _resolve_oos_mode(row, discovery)
    guardrails = _notes_guardrails(row)
    evidence = {
        "candidate_n": row.get("candidate_n"),
        "baseline_n": row.get("baseline_n"),
        "incremental_median": row.get("incremental_median"),
        "incremental_mean": row.get("incremental_mean"),
        "incremental_win_rate": row.get("incremental_win_rate"),
        "best_horizon": row.get("best_horizon"),
        "note": "Discovery/challenger evidence frozen at freeze time; OOS must not rewrite these values.",
    }
    condition_key = "" if _is_missing(row.get("condition_key")) else str(row.get("condition_key"))
    if not condition_key:
        condition_key = f"{row.get('market_transition', '')}|{canonical_condition_key(clauses)}"
    cutoff = data_cutoff_date
    disc_start = "" if _is_missing(row.get("discovery_start_date")) else str(row.get("discovery_start_date"))
    disc_end = "" if _is_missing(row.get("discovery_end_date")) else str(row.get("discovery_end_date"))
    return build_frozen_hypothesis_spec(
        condition_key=condition_key,
        condition_text=str(row.get("condition_text", "")),
        market_transition=str(row.get("market_transition", "")),
        market_state=str(row.get("market_state", "")),
        feature_clauses=canonical_feature_clauses(clauses),
        best_horizon=str(row.get("best_horizon", "T5")),
        discovery_run_id=str(row.get("discovery_run_id") or discovery.get("run_id") or ""),
        discovery_evidence=evidence,
        challenger_status=str(row.get("robustness_status") or ""),
        guardrails_summary=guardrails,
        data_cutoff_date=cutoff,
        guardrails_config_version=GUARDRAILS_CONFIG_VERSION,
        freeze_timestamp=freeze_timestamp,
        edge_id=str(row.get("edge_id", "")),
        baseline_type=str(row.get("baseline_type", "")),
        discovery_start_date=disc_start,
        discovery_end_date=disc_end or cutoff,
        challenger_research_cutoff=cutoff,
        feature_bucket_config_version=FEATURE_BUCKET_CONFIG_VERSION,
        market_state_config_version=MARKET_STATE_CONFIG_VERSION,
        challenger_run_id=str(
            row.get("robustness_run_id") or row.get("challenger_run_id") or challenger.get("run_id") or ""
        ),
        oos_mode=oos_mode,
        oos_start_date=oos_start,
        embargo_trading_sessions=int(
            discovery.get("embargo_trading_days") or OOS_EMBARGO_TRADING_SESSIONS or DEFAULT_EMBARGO_TRADING_DAYS
        ),
        holdout_applied=holdout,
    )


def _cutoff_from_panel_or_discovery(
    panel: Optional[pd.DataFrame],
    row: pd.Series,
    discovery: Dict[str, Any],
) -> str:
    oos_mode, _, holdout = _resolve_oos_mode(row, discovery)
    if holdout and discovery.get("discovery_end_date"):
        return str(discovery.get("discovery_end_date"))
    if panel is not None and not panel.empty:
        sessions = unique_trading_sessions(panel)
        if sessions:
            return sessions[-1].strftime("%Y-%m-%d")
    if not _is_missing(row.get("discovery_end_date")):
        return str(row.get("discovery_end_date"))
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _update_ledger_freeze_row(
    ledger: pd.DataFrame,
    edge_id: str,
    spec: FrozenHypothesisSpec,
    spec_relpath: str,
    eligibility: str,
) -> pd.DataFrame:
    mask = ledger["edge_id"].astype(str) == str(edge_id)
    if not mask.any():
        return ledger
    ledger.loc[mask, "hypothesis_id"] = spec.hypothesis_id
    ledger.loc[mask, "frozen_spec_path"] = spec_relpath
    ledger.loc[mask, "frozen_spec_hash"] = spec.spec_hash
    ledger.loc[mask, "oos_status"] = OOS_STATUS_PENDING
    ledger.loc[mask, "oos_mode"] = spec.oos_mode
    ledger.loc[mask, "scientific_status"] = ScientificStatus.OOS_PENDING.value
    ledger.loc[mask, "freeze_eligibility"] = eligibility
    ledger.loc[mask, "condition_key"] = spec.condition_key
    ledger.loc[mask, "feature_clauses_json"] = json.dumps(list(spec.feature_clauses), ensure_ascii=False)
    if "challenger_run_id" in ledger.columns:
        ledger.loc[mask, "challenger_run_id"] = spec.challenger_run_id
    return ledger


def freeze_eligible_candidates(
    *,
    data_dir: Optional[Path] = None,
    panel: Optional[pd.DataFrame] = None,
    freeze_timestamp: Optional[str] = None,
) -> FreezeRunResult:
    """
    Freeze every currently eligible Challenger PASS + READY_FOR_OOS candidate.

    Idempotent. Does not rewrite discovery/challenger metrics.
    """
    root = ensure_storage(data_dir)
    ledger = read_ledger("edge_hypothesis_ledger.csv", data_dir=root)
    result = FreezeRunResult()
    if ledger.empty:
        return result

    discovery = read_discovery_run(root)
    challenger = read_challenger_run(root)
    ts = freeze_timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for idx, row in ledger.iterrows():
        decision = classify_freeze_eligibility(row)
        if not decision.eligible:
            ledger.at[idx, "freeze_eligibility"] = decision.eligibility
            if _is_missing(row.get("scientific_status")):
                if decision.eligibility == FREEZE_FRAGILE:
                    ledger.at[idx, "scientific_status"] = ScientificStatus.FRAGILE.value
                elif decision.eligibility == FREEZE_REJECT:
                    ledger.at[idx, "scientific_status"] = ScientificStatus.REJECTED.value
                elif decision.eligibility == FREEZE_HISTORICAL_ONLY:
                    ledger.at[idx, "scientific_status"] = ScientificStatus.HISTORICAL_ONLY.value
            result.skipped.append(decision)
            continue

        existing_hid = "" if _is_missing(row.get("hypothesis_id")) else str(row.get("hypothesis_id"))
        if existing_hid:
            existing = load_frozen_spec(existing_hid, root)
            if existing is not None:
                decision.spec = existing
                decision.reused_existing = True
                decision.reason = "idempotent_reuse"
                result.frozen.append(decision)
                continue

        cutoff = _cutoff_from_panel_or_discovery(panel, row, discovery)
        spec = build_spec_for_ledger_row(
            row,
            data_cutoff_date=cutoff,
            discovery=discovery,
            challenger=challenger,
            freeze_timestamp=ts,
        )
        path, reused = persist_frozen_spec(spec, root)
        rel = f"{FROZEN_SPECS_DIRNAME}/{spec.hypothesis_id}.json"
        ledger = _update_ledger_freeze_row(ledger, spec.edge_id, spec, rel, FREEZE_ELIGIBLE)
        decision.spec = spec
        decision.reused_existing = reused
        result.frozen.append(decision)

    ledger.to_csv(root / "edge_hypothesis_ledger.csv", index=False)
    return result
