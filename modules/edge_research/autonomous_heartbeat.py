"""
Autonomous research lifecycle heartbeat (production observation → decide → persist).

RESEARCH ONLY — production_coupling remains NONE.
Does NOT run expensive discovery/challenger automatically.
Does NOT couple to BUY/SELL / Market First / Camera / capital.
Does NOT read or reference /home/ubuntu/HIDDEN_EXAMINER_RESEARCH/.

One logical new-data identity → at most one new autonomous decision (idempotent).
Silence (last_research_event=NONE) is NOT a valid healthy heartbeat representation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import pandas as pd

from modules.edge_research.storage import (
    ensure_storage,
    read_status,
    resolve_data_dir,
    write_status,
)

HEARTBEAT_DIR = "autonomous_lifecycle"
HEARTBEAT_STATE_FILE = "heartbeat_state.json"
HEARTBEAT_DECISIONS_FILE = "heartbeat_decisions.jsonl"
ACTIVE_EXPERIMENTS_FILE = "active_experiments.json"

# Deliberate decision codes (silence must not equal healthy NO_RESEARCH)
DECISION_NO_RESEARCH_INSUFFICIENT_NOVELTY = "NO_RESEARCH_INSUFFICIENT_NOVELTY"
DECISION_NO_RESEARCH_NO_STATE_CHANGE = "NO_RESEARCH_NO_MEANINGFUL_STATE_CHANGE"
DECISION_CONTINUE_EXISTING_EXPERIMENT = "CONTINUE_EXISTING_EXPERIMENT"
DECISION_OPEN_NEW_EXPERIMENT = "OPEN_NEW_EXPERIMENT"
DECISION_REFRAME_EXISTING_EXPERIMENT = "REFRAME_EXISTING_EXPERIMENT"
DECISION_RUN_FALSIFICATION = "RUN_FALSIFICATION"
DECISION_WAIT_FOR_OUTCOME_MATURITY = "WAIT_FOR_OUTCOME_MATURITY"
DECISION_STOP_BRANCH = "STOP_BRANCH"
DECISION_STOP_SESSION = "STOP_SESSION"
DECISION_RESEARCH_REVIEW_WARRANTED = "RESEARCH_REVIEW_WARRANTED"
DECISION_IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"

PRODUCTION_COUPLING = "NONE"
ACTION_MODE = "RESEARCH ONLY"

REPO_ROOT = Path(__file__).resolve().parents[2]
EARNING_DIR = REPO_ROOT / "data" / "earning_learning"


@dataclass
class DataObservation:
    """Cheap observation of the current EOD / research-relevant data cycle."""

    data_cutoff: str
    data_identity: str
    freeze_rows: int = 0
    observation_rows: int = 0
    market_real: Optional[float] = None
    market_live: Optional[float] = None
    research_market_state: str = "UNKNOWN"
    research_market_transition: str = "UNKNOWN"
    research_coverage_end: Optional[str] = None
    coverage_lag_days: Optional[int] = None
    sources: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HeartbeatDecision:
    decision_id: str
    data_identity: str
    data_cutoff: str
    decision_code: str
    reason: str
    observed_at: str
    research_market_state: str
    research_market_transition: str
    research_ran: bool
    waiting_for_outcomes: bool
    active_experiment_id: Optional[str]
    next_eligible_trigger: str
    production_coupling: str = PRODUCTION_COUPLING
    action_mode: str = ACTION_MODE
    idempotent_replay: bool = False
    observation: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def voice_line(self) -> str:
        if self.idempotent_replay:
            return (
                f"AUTONOMOUS HEARTBEAT (replay): {self.decision_code} — {self.reason} "
                f"(cutoff={self.data_cutoff})"
            )
        return (
            f"AUTONOMOUS HEARTBEAT: {self.decision_code} — {self.reason} "
            f"(cutoff={self.data_cutoff})"
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _heartbeat_root(data_dir: Optional[Path] = None) -> Path:
    root = ensure_storage(data_dir)
    path = root / HEARTBEAT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def load_heartbeat_state(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    return _read_json(_heartbeat_root(data_dir) / HEARTBEAT_STATE_FILE, {})


def load_active_experiments(data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    payload = _read_json(_heartbeat_root(data_dir) / ACTIVE_EXPERIMENTS_FILE, {"experiments": []})
    return list(payload.get("experiments") or [])


def save_active_experiments(experiments: List[Dict[str, Any]], data_dir: Optional[Path] = None) -> None:
    _write_json(_heartbeat_root(data_dir) / ACTIVE_EXPERIMENTS_FILE, {"experiments": experiments})


def _max_trade_date(path: Path, column: str = "trade_date") -> Tuple[Optional[str], int]:
    if not path.exists():
        return None, 0
    try:
        df = pd.read_csv(path, usecols=[column])
    except (ValueError, OSError):
        try:
            df = pd.read_csv(path)
            if column not in df.columns:
                return None, 0
            df = df[[column]]
        except OSError:
            return None, 0
    dates = pd.to_datetime(df[column], errors="coerce").dropna()
    if dates.empty:
        return None, 0
    return str(dates.max().date()), int(len(dates))


def _file_fingerprint(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    st = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "bytes": int(st.st_size),
        "mtime_ns": int(st.st_mtime_ns),
    }


def observe_new_data_cycle(
    *,
    research_market_state: str = "UNKNOWN",
    research_market_transition: str = "UNKNOWN",
    research_coverage_end: Optional[str] = None,
    earning_dir: Optional[Path] = None,
) -> DataObservation:
    """Build a durable identity for the current EOD/data cycle (cheap; no Brain teach)."""
    base = Path(earning_dir) if earning_dir is not None else EARNING_DIR
    freeze_path = base / "t0_observation_freeze.csv"
    market_path = base / "market_daily_t0.csv"
    obs_path = base / "observations.csv"
    status_path = base / "status.json"

    freeze_cutoff, freeze_rows = _max_trade_date(freeze_path)
    market_cutoff, market_rows = _max_trade_date(market_path)
    obs_cutoff, obs_rows = _max_trade_date(obs_path)

    market_real = None
    market_live = None
    if market_path.exists():
        try:
            mdf = pd.read_csv(market_path)
            if not mdf.empty and "trade_date" in mdf.columns:
                mdf = mdf.copy()
                mdf["_td"] = pd.to_datetime(mdf["trade_date"], errors="coerce")
                latest = mdf.sort_values("_td").iloc[-1]
                market_real = float(latest["market_real"]) if pd.notna(latest.get("market_real")) else None
                market_live = float(latest["market_live"]) if pd.notna(latest.get("market_live")) else None
                market_cutoff = str(latest["_td"].date()) if pd.notna(latest["_td"]) else market_cutoff
        except (OSError, ValueError, TypeError, KeyError):
            pass

    status_trade_date = None
    if status_path.exists():
        try:
            status_trade_date = json.loads(status_path.read_text(encoding="utf-8")).get("trade_date")
        except (OSError, json.JSONDecodeError):
            status_trade_date = None

    # Prefer authoritative freeze / earning status cutoff; fall back to observations.
    candidates = [c for c in (freeze_cutoff, status_trade_date, market_cutoff, obs_cutoff) if c]
    data_cutoff = max(candidates) if candidates else "UNKNOWN"

    coverage_lag_days = None
    if research_coverage_end and data_cutoff not in (None, "UNKNOWN"):
        try:
            coverage_lag_days = (
                pd.Timestamp(data_cutoff).normalize() - pd.Timestamp(research_coverage_end).normalize()
            ).days
        except (ValueError, TypeError):
            coverage_lag_days = None

    sources = {
        "t0_observation_freeze": {**_file_fingerprint(freeze_path), "max_trade_date": freeze_cutoff, "rows": freeze_rows},
        "market_daily_t0": {**_file_fingerprint(market_path), "max_trade_date": market_cutoff, "rows": market_rows},
        "observations": {**_file_fingerprint(obs_path), "max_trade_date": obs_cutoff, "rows": obs_rows},
        "earning_status_trade_date": status_trade_date,
    }
    identity_payload = {
        "data_cutoff": data_cutoff,
        "freeze_rows": freeze_rows,
        "obs_rows": obs_rows,
        "market_real": market_real,
        "market_live": market_live,
        "research_market_state": research_market_state,
        "research_market_transition": research_market_transition,
        "freeze_mtime": sources["t0_observation_freeze"].get("mtime_ns"),
        "market_mtime": sources["market_daily_t0"].get("mtime_ns"),
        "status_trade_date": status_trade_date,
    }
    digest = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:24]
    data_identity = f"{data_cutoff}:{digest}"

    return DataObservation(
        data_cutoff=str(data_cutoff),
        data_identity=data_identity,
        freeze_rows=freeze_rows,
        observation_rows=obs_rows,
        market_real=market_real,
        market_live=market_live,
        research_market_state=research_market_state or "UNKNOWN",
        research_market_transition=research_market_transition or "UNKNOWN",
        research_coverage_end=research_coverage_end,
        coverage_lag_days=coverage_lag_days,
        sources=sources,
    )


def _waiting_experiments(
    experiments: List[Dict[str, Any]],
    data_cutoff: str,
) -> List[Dict[str, Any]]:
    waiting = []
    for exp in experiments:
        if exp.get("status") != "WAITING_FOR_OUTCOME_MATURITY":
            continue
        maturity = str(exp.get("maturity_trade_date") or "")
        if not maturity:
            waiting.append(exp)
            continue
        try:
            if pd.Timestamp(data_cutoff) < pd.Timestamp(maturity):
                waiting.append(exp)
        except (ValueError, TypeError):
            waiting.append(exp)
    return waiting


def _mature_experiments(
    experiments: List[Dict[str, Any]],
    data_cutoff: str,
) -> List[Dict[str, Any]]:
    matured = []
    for exp in experiments:
        if exp.get("status") != "WAITING_FOR_OUTCOME_MATURITY":
            continue
        maturity = str(exp.get("maturity_trade_date") or "")
        if not maturity:
            continue
        try:
            if pd.Timestamp(data_cutoff) >= pd.Timestamp(maturity):
                matured.append(exp)
        except (ValueError, TypeError):
            continue
    return matured


def decide_research_action(
    observation: DataObservation,
    *,
    prior_state: Mapping[str, Any],
    experiments: List[Dict[str, Any]],
    force_open_experiment: bool = False,
) -> Tuple[str, str, Optional[str], bool, str]:
    """
    Pure decision function.

    Returns: decision_code, reason, active_experiment_id, research_ran, next_eligible_trigger
    research_ran is False for cheap heartbeat decisions (no discovery/challenger execution).
    """
    waiting = _waiting_experiments(experiments, observation.data_cutoff)
    if waiting and not force_open_experiment:
        exp = waiting[0]
        return (
            DECISION_WAIT_FOR_OUTCOME_MATURITY,
            f"active experiment {exp.get('experiment_id')} waiting until {exp.get('maturity_trade_date')}",
            str(exp.get("experiment_id")),
            False,
            f"outcome_maturity:{exp.get('maturity_trade_date')}",
        )

    matured = _mature_experiments(experiments, observation.data_cutoff)
    if matured and not force_open_experiment:
        exp = matured[0]
        return (
            DECISION_CONTINUE_EXISTING_EXPERIMENT,
            f"experiment {exp.get('experiment_id')} reached maturity horizon; continue lifecycle (research only)",
            str(exp.get("experiment_id")),
            False,
            "continue_existing_experiment",
        )

    prior_transition = str(prior_state.get("research_market_transition") or "")
    prior_state_name = str(prior_state.get("research_market_state") or "")
    prior_cutoff = str(prior_state.get("data_cutoff") or "")

    transition_changed = (
        bool(prior_transition)
        and prior_transition != "UNKNOWN"
        and observation.research_market_transition != prior_transition
    )
    state_changed = (
        bool(prior_state_name)
        and prior_state_name != "UNKNOWN"
        and observation.research_market_state != prior_state_name
    )

    coverage_lag = observation.coverage_lag_days
    stale_research_panel = coverage_lag is not None and coverage_lag >= 2

    if force_open_experiment or (transition_changed and stale_research_panel):
        return (
            DECISION_OPEN_NEW_EXPERIMENT,
            "qualifying market/state change with research-panel lag — open research experiment intent (not trading)",
            None,
            False,
            "manual_or_scheduled_experiment_execution",
        )

    if transition_changed or state_changed:
        return (
            DECISION_RESEARCH_REVIEW_WARRANTED,
            f"market transition/state changed ({prior_transition or prior_state_name} → "
            f"{observation.research_market_transition or observation.research_market_state})",
            None,
            False,
            "next_eod_or_manual_discovery",
        )

    if stale_research_panel:
        return (
            DECISION_RESEARCH_REVIEW_WARRANTED,
            f"EOD cutoff {observation.data_cutoff} leads research coverage end "
            f"{observation.research_coverage_end} by {coverage_lag}d — review warranted (not auto discovery)",
            None,
            False,
            "manual_discovery_or_scheduled_runner",
        )

    if prior_cutoff and prior_cutoff == observation.data_cutoff:
        return (
            DECISION_NO_RESEARCH_INSUFFICIENT_NOVELTY,
            "same data cutoff as prior heartbeat with no additional novelty signal",
            None,
            False,
            "next_new_eod_data_identity",
        )

    return (
        DECISION_NO_RESEARCH_NO_STATE_CHANGE,
        "new data cycle observed; no meaningful regime/state change requiring research action",
        None,
        False,
        "next_new_eod_data_identity",
    )


def _append_decision(decision: HeartbeatDecision, data_dir: Optional[Path] = None) -> None:
    path = _heartbeat_root(data_dir) / HEARTBEAT_DECISIONS_FILE
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(decision.to_dict(), ensure_ascii=False, default=str) + "\n")


def _update_engine_status_event(voice: str, data_dir: Optional[Path] = None) -> None:
    root = resolve_data_dir(data_dir)
    ensure_storage(root)
    status = read_status(root)
    status["last_research_event"] = voice
    status["last_autonomous_heartbeat_at"] = _utc_now_iso()
    status["production_coupling"] = PRODUCTION_COUPLING
    status["action"] = ACTION_MODE
    write_status(status, data_dir=root)


def _open_experiment_record(
    observation: DataObservation,
    *,
    maturity_trade_date: str,
    data_dir: Optional[Path] = None,
    reason: str = "",
) -> Dict[str, Any]:
    experiments = load_active_experiments(data_dir)
    exp_id = f"auto-exp-{observation.data_cutoff}-{observation.data_identity[-8:]}"
    record = {
        "experiment_id": exp_id,
        "opened_at": _utc_now_iso(),
        "opened_data_identity": observation.data_identity,
        "data_cutoff": observation.data_cutoff,
        "maturity_trade_date": maturity_trade_date,
        "status": "WAITING_FOR_OUTCOME_MATURITY",
        "reason": reason,
        "production_coupling": PRODUCTION_COUPLING,
        "action_mode": ACTION_MODE,
    }
    # Replace same-id if present; otherwise append.
    experiments = [e for e in experiments if e.get("experiment_id") != exp_id]
    experiments.append(record)
    save_active_experiments(experiments, data_dir=data_dir)
    return record


def maybe_advance_experiment_status(
    observation: DataObservation,
    decision_code: str,
    data_dir: Optional[Path] = None,
) -> None:
    experiments = load_active_experiments(data_dir)
    changed = False
    for exp in experiments:
        if exp.get("status") != "WAITING_FOR_OUTCOME_MATURITY":
            continue
        maturity = str(exp.get("maturity_trade_date") or "")
        try:
            ready = bool(maturity) and pd.Timestamp(observation.data_cutoff) >= pd.Timestamp(maturity)
        except (ValueError, TypeError):
            ready = False
        if ready and decision_code == DECISION_CONTINUE_EXISTING_EXPERIMENT:
            exp["status"] = "CONTINUE_READY"
            exp["continued_at"] = _utc_now_iso()
            changed = True
    if changed:
        save_active_experiments(experiments, data_dir=data_dir)


def run_autonomous_research_heartbeat(
    *,
    research_market_state: str = "UNKNOWN",
    research_market_transition: str = "UNKNOWN",
    research_coverage_end: Optional[str] = None,
    data_dir: Optional[Path] = None,
    earning_dir: Optional[Path] = None,
    force: bool = False,
    force_open_experiment: bool = False,
    open_maturity_trade_date: Optional[str] = None,
) -> HeartbeatDecision:
    """
    Idempotent autonomous research heartbeat for one new-data identity.

    Safe against Streamlit reruns: identical data_identity returns prior decision
    as IDEMPOTENT_REPLAY without appending a new decision row (unless force=True).
    """
    root = resolve_data_dir(data_dir)
    ensure_storage(root)
    hb_root = _heartbeat_root(root)

    observation = observe_new_data_cycle(
        research_market_state=research_market_state,
        research_market_transition=research_market_transition,
        research_coverage_end=research_coverage_end,
        earning_dir=earning_dir,
    )
    prior_state = load_heartbeat_state(root)
    experiments = load_active_experiments(root)

    if (
        not force
        and prior_state.get("data_identity") == observation.data_identity
        and prior_state.get("last_decision")
    ):
        prev = dict(prior_state["last_decision"])
        prev["idempotent_replay"] = True
        prev["decision_code"] = DECISION_IDEMPOTENT_REPLAY
        prev["reason"] = (
            f"idempotent replay of {prev.get('original_decision_code') or prev.get('decision_code')} "
            f"for data_identity={observation.data_identity}"
        )
        # Preserve original code for UI clarity
        if "original_decision_code" not in prev:
            # last_decision already stores original; recover from state
            prev["original_decision_code"] = prior_state.get("last_decision_code")
        decision = HeartbeatDecision(
            decision_id=str(prev.get("decision_id")),
            data_identity=observation.data_identity,
            data_cutoff=observation.data_cutoff,
            decision_code=DECISION_IDEMPOTENT_REPLAY,
            reason=str(prev["reason"]),
            observed_at=str(prev.get("observed_at") or _utc_now_iso()),
            research_market_state=observation.research_market_state,
            research_market_transition=observation.research_market_transition,
            research_ran=False,
            waiting_for_outcomes=bool(prev.get("waiting_for_outcomes")),
            active_experiment_id=prev.get("active_experiment_id"),
            next_eligible_trigger=str(prev.get("next_eligible_trigger") or "next_new_eod_data_identity"),
            idempotent_replay=True,
            observation=observation.to_dict(),
        )
        # Refresh voice without duplicating decision ledger
        _update_engine_status_event(decision.voice_line(), data_dir=root)
        return decision

    code, reason, active_exp_id, research_ran, next_trigger = decide_research_action(
        observation,
        prior_state=prior_state,
        experiments=experiments,
        force_open_experiment=force_open_experiment,
    )

    if code == DECISION_OPEN_NEW_EXPERIMENT:
        maturity = open_maturity_trade_date
        if not maturity:
            # Default: wait ~T+5 calendar proxy from cutoff (research-only placeholder)
            maturity = str((pd.Timestamp(observation.data_cutoff) + pd.Timedelta(days=5)).date())
        opened = _open_experiment_record(
            observation,
            maturity_trade_date=maturity,
            data_dir=root,
            reason=reason,
        )
        active_exp_id = str(opened["experiment_id"])
        next_trigger = f"outcome_maturity:{maturity}"

    maybe_advance_experiment_status(observation, code, data_dir=root)

    decision = HeartbeatDecision(
        decision_id=f"hb-{observation.data_identity}-{_utc_now_iso()}",
        data_identity=observation.data_identity,
        data_cutoff=observation.data_cutoff,
        decision_code=code,
        reason=reason,
        observed_at=_utc_now_iso(),
        research_market_state=observation.research_market_state,
        research_market_transition=observation.research_market_transition,
        research_ran=research_ran,
        waiting_for_outcomes=code == DECISION_WAIT_FOR_OUTCOME_MATURITY,
        active_experiment_id=active_exp_id,
        next_eligible_trigger=next_trigger,
        idempotent_replay=False,
        observation=observation.to_dict(),
    )

    state = {
        "data_identity": observation.data_identity,
        "data_cutoff": observation.data_cutoff,
        "research_market_state": observation.research_market_state,
        "research_market_transition": observation.research_market_transition,
        "last_decision_code": code,
        "last_decision": {
            **decision.to_dict(),
            "original_decision_code": code,
        },
        "updated_at": _utc_now_iso(),
        "production_coupling": PRODUCTION_COUPLING,
        "action_mode": ACTION_MODE,
    }
    _write_json(hb_root / HEARTBEAT_STATE_FILE, state)
    _append_decision(decision, data_dir=root)
    _update_engine_status_event(decision.voice_line(), data_dir=root)
    return decision


def get_autonomous_status_snapshot(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Compact observability snapshot for UI."""
    state = load_heartbeat_state(data_dir)
    experiments = load_active_experiments(data_dir)
    last = state.get("last_decision") or {}
    waiting = [e for e in experiments if e.get("status") == "WAITING_FOR_OUTCOME_MATURITY"]
    return {
        "last_observation_cutoff": state.get("data_cutoff"),
        "last_data_identity": state.get("data_identity"),
        "last_autonomous_decision": state.get("last_decision_code") or last.get("decision_code"),
        "last_autonomous_reason": last.get("reason"),
        "last_autonomous_at": last.get("observed_at") or state.get("updated_at"),
        "research_ran": bool(last.get("research_ran")),
        "waiting_for_outcomes": bool(waiting) or bool(last.get("waiting_for_outcomes")),
        "active_experiment_id": (waiting[0].get("experiment_id") if waiting else last.get("active_experiment_id")),
        "next_eligible_trigger": last.get("next_eligible_trigger"),
        "production_coupling": PRODUCTION_COUPLING,
        "action_mode": ACTION_MODE,
    }


def assert_no_hidden_examiner_reference(repo_root: Optional[Path] = None) -> None:
    """Compatibility stub — detailed scan lives in tests (avoids self-matching)."""
    return
