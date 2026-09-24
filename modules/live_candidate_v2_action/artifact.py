"""Dedicated V2 Action Layer evidence artifact.

Separate from production BUY / Elite live_evidence.jsonl.
Fail closed: never invent OHLCV or mint a production BUY flag.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from modules.live_candidate.calendar import as_vn
from modules.live_candidate_v2_action.contract import (
    ALERT_ELIGIBLE,
    CANDIDATE_IS_BUY,
    DEFAULT_ARTIFACT_RELPATH,
    ENV_ACTION_OUT,
    EVIDENCE_NAME,
    EMITTED_NAME,
    MODE,
    PXV_IMPLIES_BUY,
    SCHEMA_EVIDENCE,
    SCHEMA_STATE,
    SLICE,
    STATE_BUY_READY,
    STATE_NAME,
)
from modules.live_candidate_v2_action.state import ActionResult, BarEvidence, FrozenNomination
from modules.live_candidate_v2_action.universe import UnionReport
from modules.live_candidate_v2_camera.observe import pxv_implies_buy

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / DEFAULT_ARTIFACT_RELPATH


def buy_ready_identity(rec: Mapping[str, Any]) -> str:
    """One trigger. Does not invent fields that the stored row lacks."""
    symbol = str(rec.get("symbol") or "").upper()
    session = str(rec.get("session") or "")
    trigger = str(rec.get("trigger_bar_ts") or rec.get("last_legal_bar_ts") or "")
    return f"{symbol}|{session}|{trigger}"


def _closed_buy_ready(rec: object) -> bool:
    if not isinstance(rec, Mapping):
        return False
    state = str(rec.get("shadow_action") or rec.get("action_state") or "")
    if state != STATE_BUY_READY:
        return False
    if rec.get("candidate_is_buy") is True or rec.get("pxv_implies_buy") is True:
        return False
    if rec.get("alert_eligible") is True:
        return False
    return True


def merge_historical_buy_ready(
    new_doc: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Keep validation BUY_READY when a later publisher replaces the file.

    Carries records only while the document session is unchanged. A later
    session starts clean. Current rows are never rewritten from history.
    WAIT / NOMINATED / WEAKENED / NO_OBSERVATION are not retained.
    """
    out = dict(new_doc)
    current_symbols = {
        str(rec.get("symbol") or "").upper()
        for rec in (out.get("rows") or [])
        if isinstance(rec, Mapping) and str(rec.get("symbol") or "").strip()
    }
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []

    def _add(rec: object) -> None:
        if not _closed_buy_ready(rec):
            return
        assert isinstance(rec, Mapping)
        symbol = str(rec.get("symbol") or "").upper()
        if symbol and symbol in current_symbols:
            return
        ident = buy_ready_identity(rec)
        if ident in seen:
            return
        seen.add(ident)
        kept.append(dict(rec))

    for rec in out.get("historical_buy_ready") or []:
        _add(rec)
    new_session = str(out.get("session") or "").strip()
    prev_session = str((previous or {}).get("session") or "").strip() if isinstance(previous, Mapping) else ""
    if new_session and prev_session and new_session == prev_session:
        for key in ("historical_buy_ready", "rows"):
            for rec in (previous or {}).get(key) or []:
                _add(rec)
    if kept or "historical_buy_ready" in out:
        out["historical_buy_ready"] = kept
    return out


def default_action_dir() -> Path:
    raw = os.environ.get(ENV_ACTION_OUT, "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_ARTIFACT_DIR


def _iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return as_vn(ts).isoformat()


def evidence_row(
    nom: FrozenNomination,
    bar: BarEvidence,
    result: ActionResult,
    *,
    session: str,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """One legal completed 5m observation — enough to replay the decision."""
    return {
        "schema": SCHEMA_EVIDENCE,
        "slice": SLICE,
        "mode": MODE,
        "candidate_is_buy": CANDIDATE_IS_BUY,
        "pxv_implies_buy": pxv_implies_buy(bar.published_evidence),
        "alert_eligible": ALERT_ELIGIBLE,
        "session": session,
        "symbol": nom.symbol,
        "setup": nom.setup,
        "group": nom.group,
        "route": nom.route,
        "candidate_first_seen_ts": nom.candidate_first_seen_ts,
        "eligible_from": nom.eligible_from,
        "bar_ts": _iso(bar.bar_ts),
        "asof": _iso(bar.asof),
        "completed_bar": bool(bar.completed) and not bar.unfinished,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "frozen_reference_kind": bar.reference_kind or nom.required_ref,
        "frozen_reference_value": bar.reference_value,
        "close_canonical": bar.close_canonical,
        "reference_canonical": bar.reference_canonical,
        "close_vs_ref": bar.close_vs_ref,
        "close_vs_ref_pct": bar.close_vs_ref_pct,
        "reference_state": bar.reference_state,
        "data_state": bar.data_state,
        "gate_reason": bar.gate_reason,
        "raw_evidence": bar.raw_evidence,
        "published_evidence": bar.published_evidence,
        "volume_expansion_state": bar.volume_expansion_state,
        "price_volume_state": bar.price_volume_state,
        "fam_sell": bar.fam_sell,
        "sell_expansion": bar.sell_expansion,
        "conflict": str(bar.published_evidence or "") == "CONFLICT",
        "overlay_truth_class": bar.overlay_truth_class,
        "overlay_applied": bar.overlay_applied,
        "chronology_legal": bar.chronology_legal,
        "action_state": result.action_state,
        "action_reason": result.action_reason,
        "shadow_label": result.shadow_label,
        "observed": result.observed,
        "observed_at": _iso(observed_at),
        "market_permission": nom.market_permission,
    }


def state_document(
    *,
    session: str,
    observed_at: datetime,
    results: Sequence[ActionResult],
    union: UnionReport | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rows = []
    for r in results:
        rows.append(
            {
                "symbol": r.symbol,
                "setup": r.setup,
                # Nomination / freeze provenance. Not rewritten on rollover.
                "session": r.session,
                # Cash session of this observation. Independent of row.session.
                "observation_session": session,
                "shadow_action": r.action_state,
                "shadow_label": r.shadow_label,
                "action_reason": r.action_reason,
                "route": r.route,
                "source": r.source,
                "last_legal_bar_ts": r.last_legal_bar_ts,
                "trigger_bar_ts": r.last_legal_bar_ts,
                "trigger_price": r.trigger_price,
                "frozen_ref_kind": r.frozen_ref_kind,
                "frozen_ref_value": r.frozen_ref_value,
                "published_evidence": r.published_evidence,
                "volume_expansion_state": r.volume_expansion_state,
                "price_volume_state": r.price_volume_state,
                "market_permission": r.market_permission,
                "close_canonical": r.close_canonical,
                "close_vs_ref": r.close_vs_ref,
                "close_vs_ref_pct": r.close_vs_ref_pct,
                "reference_state": r.reference_state,
                "n_legal_bars": r.n_legal_bars,
                "observed": r.observed,
                "candidate_is_buy": CANDIDATE_IS_BUY,
                "pxv_implies_buy": PXV_IMPLIES_BUY,
                "alert_eligible": ALERT_ELIGIBLE,
            }
        )
    return {
        "schema": SCHEMA_STATE,
        "slice": SLICE,
        "mode": MODE,
        "candidate_is_buy": CANDIDATE_IS_BUY,
        "pxv_implies_buy": PXV_IMPLIES_BUY,
        "alert_eligible": ALERT_ELIGIBLE,
        "session": session,
        "observed_at": as_vn(observed_at).isoformat(),
        "union": union.as_dict() if isinstance(union, UnionReport) else (dict(union) if union else {}),
        "rows": rows,
        "notes": [
            "SHADOW / RESEARCH only. BUY_READY is not a production BUY instruction.",
            "Not Telegram. Not NAV. Not order/execution. Not SELL.",
            "source_action / Elite BUY metadata are not the action state.",
        ],
    }


class V2ActionStore:
    """Append-only evidence + latest shadow state. Isolated from Elite artifacts."""

    def __init__(self, out_dir: Path | None = None) -> None:
        self.out_dir = Path(out_dir) if out_dir is not None else default_action_dir()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._emitted = self._load_emitted()

    def _load_emitted(self) -> set[str]:
        path = self.out_dir / EMITTED_NAME
        if not path.exists():
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        if isinstance(data, list):
            return set(str(x) for x in data)
        return set()

    def bar_key(self, symbol: str, bar_ts: datetime) -> str:
        return f"{symbol}|{_iso(bar_ts)}"

    def append_evidence(self, rows: Sequence[Mapping[str, Any]]) -> int:
        if not rows:
            return 0
        path = self.out_dir / EVIDENCE_NAME
        added = 0
        with path.open("a", encoding="utf-8") as fh:
            for row in rows:
                key = f"{row.get('symbol')}|{row.get('bar_ts')}"
                if key in self._emitted:
                    continue
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                self._emitted.add(key)
                added += 1
        self._write_json(self.out_dir / EMITTED_NAME, sorted(self._emitted))
        return added

    def write_state(self, document: Mapping[str, Any]) -> Path:
        path = self.out_dir / STATE_NAME
        self._write_json(path, document)
        return path

    def read_evidence(self) -> list[dict[str, Any]]:
        path = self.out_dir / EVIDENCE_NAME
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def read_state(self) -> dict[str, Any] | None:
        path = self.out_dir / STATE_NAME
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)


def persist_cycle(
    *,
    session: str | date,
    observed_at: datetime,
    items: Sequence[tuple[FrozenNomination, Sequence[BarEvidence], ActionResult]],
    union: UnionReport | Mapping[str, Any] | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    store = V2ActionStore(out_dir)
    sess = session.isoformat() if isinstance(session, date) else str(session)
    ev_rows: list[dict[str, Any]] = []
    results: list[ActionResult] = []
    for nom, bars, result in items:
        results.append(result)
        for bar in bars:
            if not bar.completed or bar.unfinished:
                continue
            ev_rows.append(evidence_row(nom, bar, result, session=sess, observed_at=observed_at))
    store.append_evidence(ev_rows)
    doc = state_document(session=sess, observed_at=observed_at, results=results, union=union)
    store.write_state(doc)
    return doc
