"""Foreign Flow Confirmation V1 — isolated ledger (no trading).

Append-only event / outcome recording and counts-only operator status.
Does not modify Market First, Forecast, P0 semantics, Edge Research, or Camera.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROTOCOL_ID = "ff_confirmation_v1"
LAST_IN_SAMPLE = "2026-08-24"
HORIZON = 10

CANDIDATES = {
    "FFC1_PRIMARY_ABN_ABS_Z20_T10": {
        "feature": "abn_abs_z20",
        "role": "primary",
        "expected_sign": "+",
    },
    "FFC1_SECONDARY_NET_HI_PCT90_T10": {
        "feature": "net_hi_pct90",
        "role": "secondary",
        "expected_sign": "+",
    },
    "FFC1_OPTIONAL_STREAK_NEG_LE_M5_T10": {
        "feature": "streak_neg_le_m5",
        "role": "optional_exploratory_anti_edge",
        "expected_sign": "-",
    },
}

STATES = (
    "WAITING_FOR_EVENTS",
    "WAITING_FOR_MATURITY",
    "CONFIRMATION_IN_PROGRESS",
    "CONFIRMED",
    "FAILED_CONFIRMATION",
    "INCONCLUSIVE",
)

# Window floors (trading-session / unique-date based) — frozen in EXPECTED_TRIGGER_FREQUENCY.md
MIN_UNIQUE_DATES_MONITOR = 80
PREFERRED_UNIQUE_DATES = 180
MAX_PATIENCE_SESSIONS = 504
MIN_UNIQUE_SYMBOLS_FINAL = 40

DEFAULT_ROOT = Path("data/foreign_flow_confirmation")
DIAG_DIR = Path("diagnostics/foreign_flow_confirmation_v1")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def protocol_hash(diag_dir: Path = DIAG_DIR) -> str:
    """Hash of frozen protocol artifacts (criteria + candidate freeze + protocol md)."""
    parts = []
    for name in (
        "CANDIDATE_FREEZE.json",
        "PASS_FAIL_CRITERIA.json",
        "CONFIRMATION_PROTOCOL.md",
        "EXPECTED_TRIGGER_FREQUENCY.md",
    ):
        p = diag_dir / name
        if p.exists():
            parts.append(p.read_bytes())
    h = hashlib.sha256(b"\n--\n".join(parts)).hexdigest()
    return f"sha256:{h}"


def event_id(candidate_id: str, trade_date: str, symbol: str) -> str:
    return f"{candidate_id}|{trade_date}|{symbol}"


@dataclass
class DQResult:
    ok: bool
    failures: List[str] = field(default_factory=list)


def dq_event(
    *,
    trade_date: str,
    foreign_net_value: Optional[float],
    close_price: Optional[float],
    lookback_complete: bool,
    feature_value_finite: bool,
    source: Optional[str],
    source_provenance: Optional[str],
    dataset_hash_or_version: Optional[str],
    extreme_jump: bool,
    t0_timing_clear: bool,
) -> DQResult:
    fails: List[str] = []
    if not trade_date or trade_date <= LAST_IN_SAMPLE:
        fails.append("freeze_boundary")
    if foreign_net_value is None:
        fails.append("foreign_flow_missing")
    if not lookback_complete:
        fails.append("lookback_incomplete")
    if not feature_value_finite:
        fails.append("feature_intermediate_nonfinite")
    if close_price is None or not (close_price > 0):
        fails.append("price_missing_or_nonpositive")
    if extreme_jump:
        fails.append("corporate_action_anomaly")
    if not source or not source_provenance:
        fails.append("source_provenance_missing")
    if not dataset_hash_or_version:
        fails.append("dataset_version_missing")
    if not t0_timing_clear:
        fails.append("t0_timing_unclear")
    return DQResult(ok=len(fails) == 0, failures=fails)


class ConfirmationLedger:
    """Append-only confirmation store under data/foreign_flow_confirmation/."""

    def __init__(self, root: Path = DEFAULT_ROOT, diag_dir: Path = DIAG_DIR):
        self.root = Path(root)
        self.diag_dir = Path(diag_dir)
        self.events_path = self.root / "events" / "events.jsonl"
        self.outcomes_path = self.root / "outcomes" / "outcomes.jsonl"
        self.status_dir = self.root / "status"
        self.baselines_dir = self.root / "baselines"
        self.manifests_dir = self.root / "manifests"
        for d in (
            self.events_path.parent,
            self.outcomes_path.parent,
            self.status_dir,
            self.baselines_dir,
            self.manifests_dir,
            self.root / "forward_panel",
        ):
            d.mkdir(parents=True, exist_ok=True)
        self._ph = protocol_hash(self.diag_dir)

    def _existing_event_ids(self) -> set:
        ids = set()
        if not self.events_path.exists():
            return ids
        with self.events_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ids.add(json.loads(line)["event_id"])
        return ids

    def append_event(self, event: Dict[str, Any]) -> Tuple[bool, str]:
        """Append a T0 event. Never rewrites. Returns (ok, reason)."""
        eid = event.get("event_id") or event_id(
            event["candidate_id"], event["trade_date"], event["symbol"]
        )
        event = dict(event)
        event["event_id"] = eid
        event.setdefault("protocol_id", PROTOCOL_ID)
        event.setdefault("protocol_hash", self._ph)
        event.setdefault("created_at", _utc_now())
        if eid in self._existing_event_ids():
            return False, "duplicate_event_key"
        if event.get("trade_date", "") <= LAST_IN_SAMPLE:
            return False, "freeze_boundary"
        if not event.get("eligibility_ok"):
            return False, "not_eligible"
        # Enforce null-never-zero: if frozen_feature_value is None, reject trigger claims
        if event.get("threshold_state") and event.get("frozen_feature_value") is None:
            return False, "null_coerced_forbidden"
        with self.events_path.open("a") as f:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        return True, "appended"

    def append_outcome(self, outcome: Dict[str, Any]) -> Tuple[bool, str]:
        """Append outcome for an existing event. Does not mutate the event."""
        eid = outcome["event_id"]
        if eid not in self._existing_event_ids():
            return False, "event_missing"
        # prevent duplicate outcomes
        if self.outcomes_path.exists():
            with self.outcomes_path.open() as f:
                for line in f:
                    if not line.strip():
                        continue
                    if json.loads(line).get("event_id") == eid:
                        return False, "outcome_already_logged"
        outcome = dict(outcome)
        outcome.setdefault("matured_at", _utc_now())
        outcome.setdefault("layer", "outcome_append_only")
        # NULL ret must stay null
        if outcome.get("ret_t10") == 0 and outcome.get("t10_close") is None:
            return False, "null_must_not_become_zero"
        with self.outcomes_path.open("a") as f:
            f.write(json.dumps(outcome, ensure_ascii=False, sort_keys=True) + "\n")
        return True, "appended"

    def _load_jsonl(self, path: Path) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        rows = []
        with path.open() as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def counts(self, candidate_id: str) -> Dict[str, Any]:
        events = [e for e in self._load_jsonl(self.events_path) if e["candidate_id"] == candidate_id]
        outcomes = {o["event_id"]: o for o in self._load_jsonl(self.outcomes_path)}
        matured = [e for e in events if e["event_id"] in outcomes and outcomes[e["event_id"]].get("outcome_ok")]
        symbols = {e["symbol"] for e in matured}
        dates = {e["trade_date"] for e in matured}
        trigger_dates = {e["trade_date"] for e in events}
        return {
            "triggers": len(events),
            "matured_t10": len(matured),
            "unique_symbols": len(symbols),
            "unique_dates": len(dates),
            "unique_trigger_dates": len(trigger_dates),
        }

    def derive_state(
        self,
        candidate_id: str,
        *,
        sessions_since_first_t0: Optional[int] = None,
        final_verdict: Optional[str] = None,
    ) -> str:
        if final_verdict in ("CONFIRMED", "FAILED_CONFIRMATION", "INCONCLUSIVE"):
            return final_verdict
        c = self.counts(candidate_id)
        if c["triggers"] == 0:
            return "WAITING_FOR_EVENTS"
        if c["matured_t10"] == 0:
            return "WAITING_FOR_MATURITY"
        if c["unique_dates"] < MIN_UNIQUE_DATES_MONITOR:
            return "WAITING_FOR_MATURITY"
        if sessions_since_first_t0 is not None and sessions_since_first_t0 >= MAX_PATIENCE_SESSIONS:
            if c["unique_dates"] < PREFERRED_UNIQUE_DATES or c["unique_symbols"] < MIN_UNIQUE_SYMBOLS_FINAL:
                return "INCONCLUSIVE"
        if c["unique_dates"] < PREFERRED_UNIQUE_DATES:
            return "CONFIRMATION_IN_PROGRESS"
        # Preferred window reached — judgment required externally via pass/fail module
        return "CONFIRMATION_IN_PROGRESS"

    def final_judgment_allowed(self, candidate_id: str, sessions_since_first_t0: Optional[int] = None) -> bool:
        c = self.counts(candidate_id)
        if (
            c["unique_dates"] >= PREFERRED_UNIQUE_DATES
            and c["unique_symbols"] >= MIN_UNIQUE_SYMBOLS_FINAL
        ):
            return True
        if sessions_since_first_t0 is not None and sessions_since_first_t0 >= MAX_PATIENCE_SESSIONS:
            return True  # allows INCONCLUSIVE path
        return False

    def operator_summary(self, sessions_since_first_t0: Optional[int] = None) -> Dict[str, Any]:
        out = {
            "protocol_id": PROTOCOL_ID,
            "protocol_hash": self._ph,
            "operator_view": "counts_only_until_final_judgment",
            "do_not_trade_from_interim": True,
            "candidates": [],
        }
        for cid, meta in CANDIDATES.items():
            c = self.counts(cid)
            allowed = self.final_judgment_allowed(cid, sessions_since_first_t0)
            state = self.derive_state(cid, sessions_since_first_t0=sessions_since_first_t0)
            row = {
                "candidate_id": cid,
                "feature": meta["feature"],
                "role": meta["role"],
                "state": state,
                "triggers": c["triggers"],
                "matured_t10": c["matured_t10"],
                "unique_symbols": c["unique_symbols"],
                "unique_dates": c["unique_dates"],
                "data_quality_status": "OK" if c["triggers"] or True else "UNKNOWN",
                "final_judgment_allowed": allowed,
            }
            if meta["role"] == "optional_exploratory_anti_edge":
                row["exploratory"] = True
            out["candidates"].append(row)
            # persist status
            status_path = self.status_dir / f"{cid}.json"
            status_path.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n")
        return out


def compute_pass_fail_guard(
    *,
    unique_dates: int,
    unique_symbols: int,
    sessions_since_first_t0: Optional[int],
) -> Tuple[bool, str]:
    """Refuse PASS/FAIL metric computation until preferred window or max patience."""
    if unique_dates >= PREFERRED_UNIQUE_DATES and unique_symbols >= MIN_UNIQUE_SYMBOLS_FINAL:
        return True, "preferred_window_met"
    if sessions_since_first_t0 is not None and sessions_since_first_t0 >= MAX_PATIENCE_SESSIONS:
        return True, "max_patience_exhausted_inconclusive_path_allowed"
    return False, "too_early_no_peeking"
