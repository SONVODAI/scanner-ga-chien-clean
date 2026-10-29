"""Append-only research ledger. In memory unless an explicit directory is passed.

Does not import scanners, nomination engines, the V2 Action evaluator,
or execution code. Canonical rows and episodes are rebuilt from stored
records. Outcome rows never compute an adjusted return.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from research.v2_research_ledger.contract import (
    ACTION_STATES,
    ADJUSTMENT_EXPLICIT_UNADJUSTED,
    ADJUSTMENT_UNAVAILABLE,
    END_CENSORED,
    END_REVERTED_WAIT,
    END_WEAKENED,
    EXECUTION_FLAG_FIELDS,
    HORIZONS,
    KIND_FIRST,
    KIND_REPEAT,
    LINK_OVERLAP,
    QUALITY_EXECUTION_FLAG,
    QUALITY_PROVENANCE_DATES,
    QUALITY_STATE_CONFLICT,
    RECORD_CANONICAL,
    RECORD_EPISODE,
    RECORD_LINK,
    RECORD_NOMINATION,
    RECORD_OUTCOME,
    RECORD_QUALITY,
    RECORD_RAW,
    SCHEMA_VERSION,
    STATE_BUY_READY,
    STATE_WAIT,
    STATE_WEAKENED,
    STATUS_BLOCKED,
    STATUS_MISSING,
    STATUS_PENDING,
    STATUS_VALID,
    STREAM_RANK,
)

_VN = timezone(timedelta(hours=7))


def _text(value: object) -> str:
    return str(value or "").strip()


def _symbol(value: object) -> str:
    return _text(value).upper()


def _opt_str(raw: Mapping[str, Any], key: str) -> str | None:
    if key not in raw or raw.get(key) in (None, ""):
        return None
    return _text(raw.get(key))


def _opt_num(raw: Mapping[str, Any], key: str) -> float | None:
    if key not in raw or raw.get(key) is None or raw.get(key) == "":
        return None
    return float(raw[key])


def _opt_bool(raw: Mapping[str, Any], key: str) -> bool | None:
    if key not in raw or raw.get(key) is None:
        return None
    return bool(raw[key])


def nomination_id(source: str, provenance_session: str, symbol: str, first_seen: str) -> str:
    return f"{source}|{provenance_session}|{symbol}|{first_seen}"


def event_id(symbol: str, bar_ts: str) -> str:
    return f"{symbol}|{bar_ts}"


def raw_id(stream: str, symbol: str, bar_ts: str, observed_at: str) -> str:
    return f"{stream}|{symbol}|{bar_ts}|{observed_at}"


def episode_id(symbol: str, evaluation_session: str, route: str, entry_bar_ts: str) -> str:
    return f"{symbol}|{evaluation_session}|{route}|{entry_bar_ts}"


def _observed_sort_value(ts: str) -> tuple:
    try:
        parsed = datetime.fromisoformat(ts)
    except ValueError:
        return (1, ts)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_VN)
    return (0, parsed.timestamp())


def _canonical_sort_key(raw: Mapping[str, Any]) -> tuple:
    stream = _text(raw.get("source_stream"))
    return (
        _observed_sort_value(_text(raw.get("observed_at"))),
        STREAM_RANK.get(stream, 9),
        _text(raw.get("raw_id")),
    )


def add_weekdays(day: date, n: int) -> date:
    """Move forward `n` weekdays. Saturdays and Sundays are skipped."""
    if n < 0:
        raise ValueError("horizon must be non-negative")
    current = day
    left = n
    while left:
        current += timedelta(days=1)
        if current.weekday() < 5:
            left -= 1
    return current


def _stamp(record_type: str, fields: dict[str, Any]) -> dict[str, Any]:
    body = {"schema_version": SCHEMA_VERSION, "record_type": record_type}
    body.update(fields)
    return body


def _execution_flags(raw: Mapping[str, Any]) -> list[str]:
    tripped = []
    for key in EXECUTION_FLAG_FIELDS:
        if raw.get(key) is True:
            tripped.append(key)
    return tripped


class ResearchLedger:
    """In-memory append-only log. Disk writes require an explicit directory."""

    def __init__(self) -> None:
        self.nominations: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self.raw_events: list[dict[str, Any]] = []
        self.canonical: list[dict[str, Any]] = []
        self.episodes: list[dict[str, Any]] = []
        self.outcomes: list[dict[str, Any]] = []
        self.quality: list[dict[str, Any]] = []
        self._nomination_ids: set[str] = set()
        self._raw_ids: set[str] = set()
        self._link_ids: set[str] = set()
        self._outcome_ids: set[str] = set()

    def add_nomination(self, raw: Mapping[str, Any]) -> dict[str, Any] | None:
        source = _text(raw.get("source"))
        provenance = _text(raw.get("provenance_session"))
        symbol = _symbol(raw.get("symbol"))
        first_seen = _text(raw.get("candidate_first_seen_ts"))
        if not source or not provenance or not symbol or not first_seen:
            raise ValueError("nomination requires source, provenance_session, symbol, candidate_first_seen_ts")
        ident = nomination_id(source, provenance, symbol, first_seen)
        if ident in self._nomination_ids:
            return None
        market_real = _opt_num(raw, "market_real_at_nomination")
        record = _stamp(
            RECORD_NOMINATION,
            {
                "nomination_id": ident,
                "source": source,
                "provenance_session": provenance,
                "symbol": symbol,
                "setup": _opt_str(raw, "setup"),
                "group": _opt_str(raw, "group"),
                "candidate_first_seen_ts": first_seen,
                "eligible_from": _opt_str(raw, "eligible_from"),
                "price_at_first_seen": _opt_num(raw, "price_at_first_seen"),
                "ema9_at_first_seen": _opt_num(raw, "ema9_at_first_seen"),
                "breakout_ref_at_first_seen": _opt_num(raw, "breakout_ref_at_first_seen"),
                "market_permission": _opt_str(raw, "market_permission"),
                "market_real_at_nomination": market_real,
                "market_context_source": _opt_str(raw, "market_context_source") if market_real is not None else None,
                "published_document_session": _opt_str(raw, "published_document_session"),
                "published_observed_at": _opt_str(raw, "published_observed_at"),
                "price_source": _opt_str(raw, "price_source"),
                "adjustment_status": _opt_str(raw, "adjustment_status"),
                "is_live_adjusted": _opt_bool(raw, "is_live_adjusted"),
            },
        )
        self.nominations.append(record)
        self._nomination_ids.add(ident)
        document_session = record["published_document_session"]
        if document_session and document_session != provenance:
            self._add_quality(
                QUALITY_PROVENANCE_DATES,
                ident,
                {
                    "provenance_session": provenance,
                    "published_document_session": document_session,
                },
            )
        return record

    def link_overlap(self, left_id: str, right_id: str) -> dict[str, Any] | None:
        """Link two stored nominations. Symbol and date do not create a link."""
        left = _text(left_id)
        right = _text(right_id)
        if not left or not right or left == right:
            return None
        if left not in self._nomination_ids or right not in self._nomination_ids:
            return None
        ident = "OVERLAP|" + "|".join(sorted((left, right)))
        if ident in self._link_ids:
            return None
        record = _stamp(
            RECORD_LINK,
            {
                "link_id": ident,
                "link_kind": LINK_OVERLAP,
                "left_id": left,
                "right_id": right,
            },
        )
        self.links.append(record)
        self._link_ids.add(ident)
        return record

    def add_raw_action(self, raw: Mapping[str, Any]) -> dict[str, Any] | None:
        tripped = _execution_flags(raw)
        symbol = _symbol(raw.get("symbol"))
        bar_ts = _text(raw.get("bar_ts"))
        if tripped:
            self._add_quality(
                QUALITY_EXECUTION_FLAG,
                event_id(symbol, bar_ts) if symbol and bar_ts else symbol or "UNKNOWN",
                {"flags": tripped},
            )
            return None
        stream = _text(raw.get("source_stream"))
        observed_at = _text(raw.get("observed_at"))
        state = _text(raw.get("action_state"))
        if not stream or not symbol or not bar_ts or not observed_at:
            raise ValueError("raw action requires source_stream, symbol, bar_ts, observed_at")
        if state not in ACTION_STATES:
            raise ValueError(f"unsupported action_state {state}")
        ident = raw_id(stream, symbol, bar_ts, observed_at)
        if ident in self._raw_ids:
            return None
        market_real = _opt_num(raw, "market_real_at_decision")
        record = _stamp(
            RECORD_RAW,
            {
                "raw_id": ident,
                "event_id": event_id(symbol, bar_ts),
                "source_stream": stream,
                "symbol": symbol,
                "bar_ts": bar_ts,
                "asof": _opt_str(raw, "asof"),
                "observed_at": observed_at,
                "action_state": state,
                "action_reason": _opt_str(raw, "action_reason"),
                "route": _opt_str(raw, "route") or "UNKNOWN",
                "setup": _opt_str(raw, "setup"),
                "group": _opt_str(raw, "group"),
                "evaluation_session": _opt_str(raw, "evaluation_session"),
                "provenance_session": _opt_str(raw, "provenance_session"),
                "candidate_first_seen_ts": _opt_str(raw, "candidate_first_seen_ts"),
                "eligible_from": _opt_str(raw, "eligible_from"),
                "open": _opt_num(raw, "open"),
                "high": _opt_num(raw, "high"),
                "low": _opt_num(raw, "low"),
                "close": _opt_num(raw, "close"),
                "volume": _opt_num(raw, "volume"),
                "frozen_reference_kind": _opt_str(raw, "frozen_reference_kind"),
                "frozen_reference_value": _opt_num(raw, "frozen_reference_value"),
                "market_permission": _opt_str(raw, "market_permission"),
                "market_real_at_decision": market_real,
                "market_context_source": _opt_str(raw, "market_context_source") if market_real is not None else None,
                "price_source": _opt_str(raw, "price_source"),
                "adjustment_status": _opt_str(raw, "adjustment_status"),
                "origin_nomination_id": _opt_str(raw, "origin_nomination_id"),
                "candidate_is_buy": False,
                "pxv_implies_buy": False,
                "alert_eligible": False,
            },
        )
        self.raw_events.append(record)
        self._raw_ids.add(ident)
        return record

    def rebuild_canonical(self) -> list[dict[str, Any]]:
        """First observed_at wins. Equal clocks break by stream rank, then raw_id."""
        self.quality = [row for row in self.quality if row["kind"] != QUALITY_STATE_CONFLICT]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for raw in self.raw_events:
            grouped.setdefault(raw["event_id"], []).append(raw)
        chosen: list[dict[str, Any]] = []
        for ident in sorted(grouped):
            rows = sorted(grouped[ident], key=_canonical_sort_key)
            winner = rows[0]
            record = _stamp(
                RECORD_CANONICAL,
                {
                    "event_id": ident,
                    "chosen_raw_id": winner["raw_id"],
                    "first_write": True,
                    "symbol": winner["symbol"],
                    "bar_ts": winner["bar_ts"],
                    "observed_at": winner["observed_at"],
                    "source_stream": winner["source_stream"],
                    "action_state": winner["action_state"],
                    "action_reason": winner["action_reason"],
                    "route": winner["route"],
                    "setup": winner["setup"],
                    "group": winner["group"],
                    "evaluation_session": winner["evaluation_session"],
                    "provenance_session": winner["provenance_session"],
                    "candidate_first_seen_ts": winner["candidate_first_seen_ts"],
                    "eligible_from": winner["eligible_from"],
                    "close": winner["close"],
                    "high": winner["high"],
                    "low": winner["low"],
                    "frozen_reference_kind": winner["frozen_reference_kind"],
                    "frozen_reference_value": winner["frozen_reference_value"],
                    "market_permission": winner["market_permission"],
                    "market_real_at_decision": winner["market_real_at_decision"],
                    "market_context_source": winner["market_context_source"],
                    "price_source": winner["price_source"],
                    "adjustment_status": winner["adjustment_status"],
                    "origin_nomination_id": winner["origin_nomination_id"],
                    "candidate_is_buy": False,
                    "pxv_implies_buy": False,
                    "alert_eligible": False,
                },
            )
            chosen.append(record)
            for other in rows[1:]:
                if other["action_state"] == winner["action_state"]:
                    continue
                self._add_quality(
                    QUALITY_STATE_CONFLICT,
                    ident,
                    {
                        "kept_raw_id": winner["raw_id"],
                        "kept_state": winner["action_state"],
                        "other_raw_id": other["raw_id"],
                        "other_state": other["action_state"],
                    },
                )
        self.canonical = chosen
        return chosen

    def rebuild_episodes(self) -> list[dict[str, Any]]:
        """Contiguous BUY_READY runs. Outcomes are not an input."""
        if not self.canonical:
            self.rebuild_canonical()
        by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for event in self.canonical:
            session = event.get("evaluation_session") or ""
            key = (event["symbol"], session, event.get("route") or "UNKNOWN")
            by_key.setdefault(key, []).append(event)
        built: list[dict[str, Any]] = []
        for key in sorted(by_key):
            ordered = sorted(by_key[key], key=lambda row: row["bar_ts"])
            run: list[dict[str, Any]] = []
            for event in ordered:
                if event["action_state"] == STATE_BUY_READY:
                    run.append(event)
                    continue
                if run:
                    built.append(_close_episode(run, event))
                    run = []
            if run:
                built.append(_close_episode(run, None))
        _mark_first_and_repeat(built)
        built.sort(key=lambda row: (row["symbol"], row["evaluation_session"], row["entry_bar_ts"], row["route"]))
        self.episodes = built
        return built

    def add_outcomes(
        self,
        episode: Mapping[str, Any],
        *,
        as_of: date,
        prices: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """One row per horizon. Prices stay null unless status is VALID.

        Adjusted returns are not calculated. A snapshot or an unknown
        adjustment is BLOCKED and stores a null price.
        """
        session_text = _text(episode.get("evaluation_session"))
        origin = date.fromisoformat(session_text)
        written: list[dict[str, Any]] = []
        price_map = prices or {}
        for horizon in HORIZONS:
            target = add_weekdays(origin, horizon)
            target_key = target.isoformat()
            label = f"T+{horizon}"
            observation = price_map.get(target_key)
            record = _outcome_row(episode, label, target_key, as_of, observation)
            if record["outcome_id"] in self._outcome_ids:
                continue
            self.outcomes.append(record)
            self._outcome_ids.add(record["outcome_id"])
            written.append(record)
        return written

    def export_append(self, directory: Path) -> None:
        """Append JSONL under `directory` only. Never chooses a default path."""
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        _append_jsonl(root / "nomination.jsonl", self.nominations)
        _append_jsonl(root / "nomination_link.jsonl", self.links)
        _append_jsonl(root / "action_event_raw.jsonl", self.raw_events)
        _append_jsonl(root / "action_event.jsonl", self.canonical)
        _append_jsonl(root / "episode.jsonl", self.episodes)
        _append_jsonl(root / "outcome.jsonl", self.outcomes)
        _append_jsonl(root / "quality_event.jsonl", self.quality)

    def note_quality(self, kind: str, subject_id: str, detail: Mapping[str, Any]) -> None:
        """Append one quality row. The same id is not stored twice."""
        self._add_quality(kind, subject_id, detail)

    def _add_quality(self, kind: str, subject_id: str, detail: Mapping[str, Any]) -> None:
        detail_key = json.dumps(detail, sort_keys=True, default=str)
        ident = f"{kind}|{subject_id}|{detail_key}"
        if any(row["quality_id"] == ident for row in self.quality):
            return
        self.quality.append(
            _stamp(
                RECORD_QUALITY,
                {
                    "quality_id": ident,
                    "kind": kind,
                    "subject_id": subject_id,
                    "detail": dict(detail),
                },
            )
        )


def _close_episode(run: list[dict[str, Any]], nxt: Mapping[str, Any] | None) -> dict[str, Any]:
    entry = run[0]
    if nxt is None:
        end_state = END_CENSORED
    elif nxt.get("action_state") == STATE_WAIT:
        end_state = END_REVERTED_WAIT
    elif nxt.get("action_state") == STATE_WEAKENED:
        end_state = END_WEAKENED
    else:
        end_state = END_CENSORED
    session = entry.get("evaluation_session") or ""
    return _stamp(
        RECORD_EPISODE,
        {
            "episode_id": episode_id(entry["symbol"], session, entry["route"], entry["bar_ts"]),
            "symbol_day_id": f"{entry['symbol']}|{session}",
            "episode_kind": KIND_REPEAT,
            "symbol": entry["symbol"],
            "evaluation_session": session,
            "route": entry["route"],
            "entry_bar_ts": entry["bar_ts"],
            "entry_close": entry.get("close"),
            "n_bars": len(run),
            "last_bar_ts": run[-1]["bar_ts"],
            "end_state": end_state,
            "origin_nomination_id": entry.get("origin_nomination_id"),
            "candidate_is_buy": False,
            "pxv_implies_buy": False,
            "alert_eligible": False,
        },
    )


def _mark_first_and_repeat(episodes: list[dict[str, Any]]) -> None:
    by_day: dict[str, list[dict[str, Any]]] = {}
    for episode in episodes:
        by_day.setdefault(episode["symbol_day_id"], []).append(episode)
    for group in by_day.values():
        group.sort(key=lambda row: (row["entry_bar_ts"], row["route"], row["episode_id"]))
        for index, episode in enumerate(group):
            episode["episode_kind"] = KIND_FIRST if index == 0 else KIND_REPEAT


def _outcome_row(
    episode: Mapping[str, Any],
    label: str,
    target_session: str,
    as_of: date,
    observation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    target = date.fromisoformat(target_session)
    price_source = None
    adjustment_status = None
    is_live_adjusted = None
    price = None
    price_ts = None
    if target > as_of:
        status = STATUS_PENDING
    elif observation is None:
        status = STATUS_MISSING
    else:
        price_source = _opt_str(observation, "price_source")
        adjustment_status = _opt_str(observation, "adjustment_status") or ADJUSTMENT_UNAVAILABLE
        is_live_adjusted = _opt_bool(observation, "is_live_adjusted")
        explicit = (
            adjustment_status == ADJUSTMENT_EXPLICIT_UNADJUSTED
            and is_live_adjusted is False
            and price_source not in (None, "snapshot")
            and observation.get("price") is not None
        )
        if explicit:
            status = STATUS_VALID
            price = float(observation["price"])
            price_ts = _opt_str(observation, "price_ts")
        else:
            status = STATUS_BLOCKED
    source_key = price_source or "none"
    return _stamp(
        RECORD_OUTCOME,
        {
            "outcome_id": f"{episode['episode_id']}|{label}|{source_key}",
            "episode_id": episode["episode_id"],
            "horizon": label,
            "target_session": target_session,
            "status": status,
            "price": price,
            "price_ts": price_ts,
            "price_source": price_source,
            "adjustment_status": adjustment_status,
            "is_live_adjusted": is_live_adjusted,
            "return_value": None,
            "mfe": None,
            "mae": None,
            "time_to_peak_bars": None,
        },
    )


def _append_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    if not rows:
        return
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
