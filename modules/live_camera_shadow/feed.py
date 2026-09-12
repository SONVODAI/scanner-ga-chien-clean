"""Isolated live 5m Camera → P×V shadow feed.

Read path only: Dynamic Watchlist → provider.fetch_session → completed bars →
chronology-gated interpret_asof + PublishedDebouncer.

Never writes the canonical Camera parquet archive.
Never changes Interpreter thresholds, debounce rules, or Candidate logic.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import pandas as pd

from modules.intraday_pxv_v1.candidates import CandidateEvent
from modules.intraday_pxv_v1.debounce import DebounceState, PublishedDebouncer
from modules.intraday_pxv_v1.interpret import interpret_asof
from modules.intraday_pxv_v1.time_contract import asof_allowed, resolve_legal_existence
from modules.live_candidate.calendar import as_vn
from modules.live_candidate.watchlist import WATCHLIST_NAME, output_root
from modules.live_camera_shadow.bars import (
    classify_stale,
    completed_to_overlay,
    validate_live_records,
)
from modules.live_camera_shadow.rate import GUEST_RPM, LIVE_UNIVERSE_CAP, rate_report
from modules.live_camera_shadow.universe import eligible_watchlist_symbols
from modules.live_shadow_transport.contract import (
    EVIDENCE_TRANSPORT_ERROR,
    WATCHLIST_TRANSPORT_ERROR,
)
from modules.live_shadow_transport.freshness import classify_freshness
from modules.live_shadow_transport.shadow_store import (
    publish_shadow_artifacts,
    resolve_shadow_store,
)
from modules.live_shadow_transport.watchlist_bus import fetch_published_watchlist

logger = logging.getLogger(__name__)

STATUS_NO_DATA = "NO_DATA"
STATUS_STALE_BAR = "STALE_BAR"
STATUS_RATE_LIMITED = "RATE_LIMITED"
STATUS_PROVIDER_ERROR = "PROVIDER_ERROR"
STATUS_NOT_YET_ELIGIBLE = "NOT_YET_ELIGIBLE"
STATUS_UNUSABLE = "UNUSABLE"
STATUS_WAITING_COMPLETED_BAR = "WAITING_COMPLETED_BAR"
STATUS_OK = "OK"
STATUS_SKIPPED_CAP = "SKIPPED_CAP"

BARS_NAME = "live_bars.jsonl"
EVIDENCE_NAME = "live_evidence.jsonl"
STATUS_NAME = "live_shadow_status.json"
EMITTED_NAME = "emitted_keys.json"
DEBOUNCE_NAME = "debounce_state.json"


def default_shadow_dir() -> Path:
    raw = os.environ.get("MRBOT_LIVE_CAMERA_SHADOW_OUT", "").strip()
    if raw:
        return Path(raw)
    return Path("data/intraday_pxv_live_shadow")


def default_watchlist_path() -> Path:
    return output_root() / WATCHLIST_NAME


def load_watchlist_rows(path: Path | None = None) -> list[dict[str, Any]]:
    src = path or default_watchlist_path()
    if not src.exists():
        return []
    data = json.loads(src.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.get("rows") or [])
    return []


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return as_vn(value)
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return as_vn(ts.to_pydatetime())


def _iso(ts: Optional[datetime]) -> Optional[str]:
    if ts is None:
        return None
    return as_vn(ts).isoformat()


def _classify_provider_error(exc: BaseException) -> str:
    msg = str(exc).lower()
    if any(tok in msg for tok in ("rate limit", "429", "too many requests")):
        return STATUS_RATE_LIMITED
    return STATUS_PROVIDER_ERROR


def _asof_hm(ts: datetime) -> str:
    return as_vn(ts).strftime("%H:%M")


def _bar_key(symbol: str, bar_ts: datetime) -> str:
    return f"{symbol}|{_iso(bar_ts)}"


@dataclass
class LiveShadowFeed:
    """One or more sweeps: eligible watchlist symbols → legal completed bars → shadow evidence."""

    provider: Any
    out_dir: Path
    now_fn: Callable[[], datetime] = field(default=lambda: datetime.now())
    archive_root: Path | None = None
    watchlist_path: Path | None = None
    hard_cap: int = LIVE_UNIVERSE_CAP
    rpm: int = GUEST_RPM
    tod_qualified_sessions: int = 0
    watchlist_source: str = "file"
    watchlist_fetcher: Optional[Callable[[], Any]] = None
    shadow_store_dir: Path | None = None

    statuses: list[dict[str, Any]] = field(default_factory=list)
    fetched_symbols: list[str] = field(default_factory=list)
    new_evidence_rows: list[dict[str, Any]] = field(default_factory=list)
    new_bar_rows: list[dict[str, Any]] = field(default_factory=list)
    _last_overlay: dict[str, pd.DataFrame] = field(default_factory=dict)
    _emitted: set[str] = field(default_factory=set)
    _debounce: dict[str, dict[str, Any]] = field(default_factory=dict)
    _watchlist_transport: str = field(default="OK", init=False)
    _watchlist_transport_detail: str = field(default="", init=False)
    _evidence_publish: str = field(default="OK", init=False)
    _evidence_publish_detail: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.out_dir = Path(self.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        if self.archive_root is not None:
            self.archive_root = Path(self.archive_root)
        if self.shadow_store_dir is not None:
            self.shadow_store_dir = Path(self.shadow_store_dir)
        self._emitted = self._load_json_set(EMITTED_NAME)
        self._debounce = self._load_json(DEBOUNCE_NAME) or {}

    def _resolve_watchlist(self, watchlist: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """In-memory list wins. GitHub fetch never falls back to a stale local file."""
        if watchlist is not None:
            self._watchlist_transport = "OK"
            self._watchlist_transport_detail = "injected"
            return list(watchlist)
        source = (self.watchlist_source or "file").strip().lower()
        if source == "github":
            fetched = fetch_published_watchlist(fetcher=self.watchlist_fetcher)
            if not fetched.ok:
                self._watchlist_transport = WATCHLIST_TRANSPORT_ERROR
                self._watchlist_transport_detail = fetched.error or WATCHLIST_TRANSPORT_ERROR
                return []
            self._watchlist_transport = "OK"
            self._watchlist_transport_detail = "github"
            return list(fetched.rows)
        self._watchlist_transport = "OK"
        self._watchlist_transport_detail = "file"
        return load_watchlist_rows(self.watchlist_path)

    def run_cycle(self, watchlist: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
        now = as_vn(self.now_fn())
        session = now.date()
        rows = self._resolve_watchlist(watchlist)
        universe = eligible_watchlist_symbols(rows, now=now, cap=self.hard_cap)

        self.statuses = []
        self.fetched_symbols = []
        self.new_evidence_rows = []
        self.new_bar_rows = []
        self._last_overlay = {}

        eligible: list[dict[str, Any]] = []
        for rec in universe:
            if rec.get("_skip") == "NOT_YET_ELIGIBLE":
                self.statuses.append(
                    self._status(
                        rec,
                        STATUS_NOT_YET_ELIGIBLE,
                        detail="now < eligible_from",
                        observed_at=now,
                        chronology_legal=False,
                        fetched=False,
                    )
                )
            else:
                eligible.append(rec)

        # Symbols that were eligible but dropped by the hard cap never appear
        # in `universe` (cap applies before skipped-not-yet rows are appended).
        listed = {str(r.get("symbol") or "").upper() for r in universe}
        for rec in rows:
            sym = str(rec.get("symbol") or "").strip().upper()
            elig = _parse_ts(rec.get("eligible_from"))
            if not sym or elig is None:
                continue
            if now >= elig and sym not in listed:
                self.statuses.append(
                    self._status(
                        rec,
                        STATUS_SKIPPED_CAP,
                        detail=f"hard cap {self.hard_cap}",
                        observed_at=now,
                        fetched=False,
                    )
                )

        for rec in eligible:
            self._process_symbol(rec, now=now, session=session)

        self._flush(now=now, session=session)
        return self.status_payload(now=now, session=session)

    def read_evidence(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.out_dir / EVIDENCE_NAME)

    def read_bars(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.out_dir / BARS_NAME)

    def status_payload(self, *, now: datetime | None = None, session: date | None = None) -> dict[str, Any]:
        now = as_vn(now or self.now_fn())
        session = session or now.date()
        fresh = classify_freshness(now, now)
        return {
            "schema": "live_camera_shadow_status.v1",
            "session": session.isoformat(),
            "observed_at": _iso(now),
            "hard_cap": self.hard_cap,
            "rpm": self.rpm,
            "rate": rate_report(self.rpm),
            "fetched_symbols": list(self.fetched_symbols),
            "n_evidence": len(self.new_evidence_rows),
            "n_bars": len(self.new_bar_rows),
            "n_evidence_total": len(self.read_evidence()),
            "archive_writes": 0,
            "alert_eligible": False,
            "production_unchanged": True,
            "runner_label": fresh["label"],
            "freshness": fresh["label"],
            "watchlist_transport": self._watchlist_transport,
            "watchlist_transport_detail": self._watchlist_transport_detail,
            "evidence_publish": self._evidence_publish,
            "evidence_publish_detail": self._evidence_publish_detail,
            "symbols": list(self.statuses),
        }

    def _process_symbol(self, rec: dict[str, Any], *, now: datetime, session: date) -> None:
        symbol = str(rec.get("symbol") or "").strip().upper()
        first_seen = _parse_ts(rec.get("candidate_first_seen_ts"))
        eligible_from = _parse_ts(rec.get("eligible_from"))
        if not symbol or first_seen is None or eligible_from is None:
            self.statuses.append(
                self._status(
                    rec,
                    STATUS_UNUSABLE,
                    detail="missing symbol / candidate_first_seen_ts / eligible_from",
                    observed_at=now,
                    fetched=False,
                )
            )
            return

        if now < eligible_from:
            self.statuses.append(
                self._status(
                    rec,
                    STATUS_NOT_YET_ELIGIBLE,
                    detail="now < eligible_from",
                    observed_at=now,
                    chronology_legal=False,
                    fetched=False,
                )
            )
            return

        try:
            raw_records = self.provider.fetch_session(symbol, session)
            self.fetched_symbols.append(symbol)
        except Exception as exc:  # noqa: BLE001 — never invent bars
            logger.warning("live shadow provider error %s: %s", symbol, exc)
            self.statuses.append(
                self._status(
                    rec,
                    _classify_provider_error(exc),
                    detail=str(exc),
                    observed_at=now,
                    fetched=True,
                )
            )
            return

        # Isolation invariant: never call upsert_session / collector.
        if self.archive_root is not None:
            # Tests inject a path that must remain empty. Do not mkdir or write.
            pass

        if not raw_records:
            self.statuses.append(
                self._status(
                    rec,
                    STATUS_NO_DATA,
                    detail="provider returned no bars",
                    observed_at=now,
                    fetched=True,
                )
            )
            return

        completed, other = validate_live_records(
            symbol,
            raw_records,
            session_date=session,
            observed_at=now,
        )
        rejected = [x for x in other if x.get("reason") not in {"UNFINISHED"}]
        unfinished = [x for x in other if x.get("reason") == "UNFINISHED"]

        if not completed and rejected and not unfinished:
            self.statuses.append(
                self._status(
                    rec,
                    STATUS_UNUSABLE,
                    detail="all provider rows rejected",
                    observed_at=now,
                    fetched=True,
                )
            )
            return

        if not completed:
            self.statuses.append(
                self._status(
                    rec,
                    STATUS_WAITING_COMPLETED_BAR,
                    detail="no completed 5m bar at now",
                    observed_at=now,
                    fetched=True,
                )
            )
            return

        latest_ts = completed[-1]["bar_ts"]
        if classify_stale(latest_ts, now):
            self.statuses.append(
                self._status(
                    rec,
                    STATUS_STALE_BAR,
                    detail="latest completed bar older than stale window",
                    observed_at=now,
                    bar_ts=latest_ts,
                    fetched=True,
                )
            )
            return

        overlay = completed_to_overlay(completed)
        self._last_overlay[symbol] = overlay
        event = CandidateEvent(
            symbol=symbol,
            session=session,
            candidate_reason=str(rec.get("candidate_reason") or "BUY ELITE"),
            candidate_ts=str(rec.get("candidate_first_seen_ts") or ""),
            bot_context=str(rec.get("bot_context") or ""),
            source="live_shadow",
            candidate_first_seen_ts=str(rec.get("candidate_first_seen_ts") or ""),
            candidate_updated_ts=str(rec.get("candidate_updated_ts") or ""),
        )
        legal = resolve_legal_existence(event)

        legal_completed: list[dict[str, Any]] = []
        for bar in completed:
            asof = bar["bar_ts"]
            if not asof_allowed(asof, legal):
                continue
            if asof < eligible_from:
                continue
            legal_completed.append(bar)

        if not legal_completed:
            waiting = bool(unfinished)
            self.statuses.append(
                self._status(
                    rec,
                    STATUS_WAITING_COMPLETED_BAR if waiting else STATUS_NOT_YET_ELIGIBLE,
                    detail="no completed bar with asof >= eligible_from",
                    observed_at=now,
                    bar_ts=latest_ts,
                    chronology_legal=False,
                    fetched=True,
                )
            )
            return

        emitted_any = False
        last_bar_ts: datetime | None = None
        debouncer = self._debouncer_for(symbol)
        for bar in legal_completed:
            bar_ts = bar["bar_ts"]
            key = _bar_key(symbol, bar_ts)
            if key in self._emitted:
                continue
            row = interpret_asof(
                overlay,
                asof=bar_ts,
                candidate=event,
                tod_store=None,
                tod_qualified_sessions=self.tod_qualified_sessions,
            )
            raw = row.raw_evidence
            published, pub_why = debouncer.step(raw)
            row.published_evidence = published
            row.published_why = pub_why
            row.evidence = published
            row.alert_eligible = False
            row.would_be_alert = False
            if "PUBLISHED_DEBOUNCE_2BAR" not in row.research_default_flags:
                row.research_default_flags.append("PUBLISHED_DEBOUNCE_2BAR")

            bar_row = {
                "symbol": symbol,
                "session": session.isoformat(),
                "bar_ts": _iso(bar_ts),
                "asof": _iso(bar_ts),
                "asof_hm": _asof_hm(bar_ts),
                "observed_at": _iso(now),
                "candidate_first_seen_ts": _iso(first_seen),
                "eligible_from": _iso(eligible_from),
                "source": "live_shadow",
                "data_quality": bar.get("data_quality"),
                "open": bar.get("open"),
                "high": bar.get("high"),
                "low": bar.get("low"),
                "close": bar.get("close"),
                "volume": bar.get("volume"),
                "chronology_legal": True,
            }
            evidence_row = {
                **bar_row,
                "raw_evidence": raw,
                "published_evidence": published,
                "published_why": pub_why,
                "evidence_why": row.evidence_why,
                "data_state": row.data_state,
                "gate_reason": row.gate_reason,
                "alert_eligible": False,
                "chronology_legal": True,
                "overlay_applied": bool(row.overlay_applied),
                "bar_source": row.bar_source_last,
                "candidate_time_provenance": legal.provenance,
            }
            self.new_bar_rows.append(bar_row)
            self.new_evidence_rows.append(evidence_row)
            self._emitted.add(key)
            emitted_any = True
            last_bar_ts = bar_ts

        self._store_debouncer(symbol, debouncer)
        if emitted_any:
            self.statuses.append(
                self._status(
                    rec,
                    STATUS_OK,
                    detail="interpreted completed legal bar(s)",
                    observed_at=now,
                    bar_ts=last_bar_ts,
                    chronology_legal=True,
                    fetched=True,
                )
            )
        else:
            self.statuses.append(
                self._status(
                    rec,
                    STATUS_OK,
                    detail="duplicate symbol/bar_ts skipped",
                    observed_at=now,
                    bar_ts=legal_completed[-1]["bar_ts"],
                    chronology_legal=True,
                    fetched=True,
                )
            )

    def _status(
        self,
        rec: dict[str, Any],
        status: str,
        *,
        detail: str = "",
        observed_at: datetime | None = None,
        bar_ts: datetime | None = None,
        chronology_legal: bool | None = None,
        fetched: bool = False,
    ) -> dict[str, Any]:
        return {
            "symbol": str(rec.get("symbol") or "").upper(),
            "status": status,
            "detail": detail,
            "eligible_from": rec.get("eligible_from"),
            "candidate_first_seen_ts": rec.get("candidate_first_seen_ts"),
            "bar_ts": _iso(bar_ts) if bar_ts is not None else None,
            "observed_at": _iso(observed_at) if observed_at is not None else None,
            "chronology_legal": chronology_legal,
            "fetched": fetched,
        }

    def _debouncer_for(self, symbol: str) -> PublishedDebouncer:
        d = PublishedDebouncer()
        saved = self._debounce.get(symbol) or {}
        if saved:
            d.state = DebounceState(
                published=str(saved.get("published") or d.state.published),
                raw_run=saved.get("raw_run"),
                raw_run_len=int(saved.get("raw_run_len") or 0),
            )
        return d

    def _store_debouncer(self, symbol: str, d: PublishedDebouncer) -> None:
        self._debounce[symbol] = {
            "published": d.state.published,
            "raw_run": d.state.raw_run,
            "raw_run_len": d.state.raw_run_len,
        }

    def _flush(self, *, now: datetime, session: date) -> None:
        if self.new_bar_rows:
            self._append_jsonl(self.out_dir / BARS_NAME, self.new_bar_rows)
        ev_path = self.out_dir / EVIDENCE_NAME
        if self.new_evidence_rows:
            self._append_jsonl(ev_path, self.new_evidence_rows)
        elif not ev_path.exists():
            ev_path.write_text("", encoding="utf-8")
        self._write_json(self.out_dir / EMITTED_NAME, sorted(self._emitted))
        self._write_json(self.out_dir / DEBOUNCE_NAME, self._debounce)
        self._write_json(self.out_dir / STATUS_NAME, self.status_payload(now=now, session=session))
        dest = resolve_shadow_store(self.shadow_store_dir)
        if dest is None:
            return
        pub = publish_shadow_artifacts(self.out_dir, dest)
        if pub.get("ok"):
            self._evidence_publish = "OK"
            self._evidence_publish_detail = str(pub.get("dest") or dest)
            return
        self._evidence_publish = EVIDENCE_TRANSPORT_ERROR
        self._evidence_publish_detail = str(pub.get("detail") or EVIDENCE_TRANSPORT_ERROR)
        self._write_json(self.out_dir / STATUS_NAME, self.status_payload(now=now, session=session))
        publish_shadow_artifacts(self.out_dir, dest)

    def _load_json(self, name: str) -> Any:
        path = self.out_dir / name
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_json_set(self, name: str) -> set[str]:
        data = self._load_json(name)
        if not data:
            return set()
        return set(data)

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    def _append_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out


def run_live_shadow(
    *,
    now: datetime,
    provider: Any,
    watchlist: Iterable[dict[str, Any]] | None = None,
    out_dir: Path | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    feed = LiveShadowFeed(
        provider=provider,
        out_dir=out_dir or default_shadow_dir(),
        now_fn=lambda: now,
        **kwargs,
    )
    return feed.run_cycle(watchlist)
