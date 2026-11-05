"""Pure Guardian evaluation. Calls production generate_signal and writes nothing."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from research.guardian_research.contract import (
    CLASS_UNAVAILABLE,
    GENERATE_SIGNAL_SHA256,
    MINIMUM_DAILY_BARS,
    PRODUCTION_TO_RESEARCH,
    SCOPE_MARKET_TECHNICAL,
)
from research.guardian_research.indicators import finite_number, scan_fields_from_daily

_REPO = Path(__file__).resolve().parents[2]
_SIGNAL_BODY = re.compile(
    r"def generate_signal\(row\):.*?(?=\n# =+\n# SELL SCORE COLOR)",
    re.S,
)
_POSITION_KEYS = frozenset(
    {
        "entry_price",
        "entry_date",
        "holding_days",
        "quantity",
        "position_size",
        "portfolio",
        "pnl",
        "pnl_pct",
    }
)


class ClassificationDrift(RuntimeError):
    """Production generate_signal no longer matches the pinned Guardian formula."""


def classification_version(source: str | None = None) -> str:
    body = _signal_body(source)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if digest != GENERATE_SIGNAL_SHA256:
        raise ClassificationDrift(digest)
    return "position_guardian.generate_signal:" + digest


def _signal_body(source: str | None) -> str:
    text = source if source is not None else (_REPO / "position_guardian.py").read_text(encoding="utf-8")
    match = _SIGNAL_BODY.search(text)
    if match is None:
        raise ClassificationDrift("generate_signal not found")
    return match.group(0)


def _as_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nat", "none", "nan"}:
        return None
    return date.fromisoformat(text[:10])


def _blank_row(symbol: str, session: str, reason: str, **extra) -> dict:
    row = {
        "symbol": symbol,
        "session": session,
        "classification": CLASS_UNAVAILABLE,
        "classification_scope": SCOPE_MARKET_TECHNICAL,
        "portfolio_decision": False,
        "position_inputs_used": False,
        "position_inputs_required": False,
        "production_signal": None,
        "reason": reason,
        "score": None,
        "score_parts": None,
        "reference_price": None,
        "reference_price_provenance": None,
        "inputs": {
            "price": None,
            "ema9": None,
            "ma20": None,
            "obv": None,
            "obv_ema9": None,
        },
        "freshness": {
            "input_session": None,
            "session_match": False,
            "bar_count": None,
            "minimum_bars": MINIMUM_DAILY_BARS,
            "live_injected": None,
            "quality": None,
            "source": None,
        },
        "classification_version": classification_version(),
    }
    row.update(extra)
    return row


def _score_parts(price, ema9, ma20, obv, obv_ema9) -> dict:
    price_below = int(price is not None and ema9 is not None and price < ema9)
    trend_break = int(ema9 is not None and ma20 is not None and ema9 < ma20)
    obv_confirm = int(trend_break == 1 and obv is not None and obv_ema9 is not None and obv < obv_ema9)
    return {
        "price_below_ema9": 40 * price_below,
        "ema9_below_ma20": 60 * trend_break,
        "obv_confirm": 20 * obv_confirm,
    }


def _prepare_inputs(observation: dict, session: str, symbol: str) -> tuple[dict | None, dict | None]:
    kind = observation.get("kind")
    position_ignored = bool(_POSITION_KEYS.intersection(observation))
    provenance = observation.get("reference_price_provenance")
    quality = observation.get("quality")
    source = observation.get("source")
    input_session = _as_date(observation.get("input_session"))
    expected = _as_date(session)
    freshness = {
        "input_session": input_session.isoformat() if input_session else None,
        "session_match": input_session == expected and expected is not None,
        "bar_count": observation.get("bar_count"),
        "minimum_bars": MINIMUM_DAILY_BARS,
        "live_injected": observation.get("live_injected"),
        "quality": quality if isinstance(quality, str) and quality.strip() else None,
        "source": source if isinstance(source, str) and source.strip() else None,
    }
    if kind == "daily_bars":
        fields = scan_fields_from_daily(observation.get("bars"))
        freshness["bar_count"] = fields.get("bar_count")
        freshness["live_injected"] = False
        if not fields.get("ok"):
            return None, _blank_row(
                symbol,
                session,
                fields.get("reason") or "INPUT_INCOMPLETE",
                freshness=freshness,
                position_inputs_ignored=position_ignored,
            )
        bar_date = _as_date(fields.get("bar_date"))
        if bar_date is None:
            return None, _blank_row(
                symbol,
                session,
                "BAR_DATE_ABSENT",
                freshness=freshness,
                position_inputs_ignored=position_ignored,
            )
        freshness["input_session"] = bar_date.isoformat()
        freshness["session_match"] = bar_date == expected
        if bar_date != expected:
            return None, _blank_row(
                symbol,
                session,
                "BAR_DATE_MISMATCH",
                freshness=freshness,
                position_inputs_ignored=position_ignored,
            )
        prepared = {
            "price": finite_number(fields.get("price")),
            "ema9": finite_number(fields.get("ema9")),
            "ma20": finite_number(fields.get("ma20")),
            "obv": finite_number(fields.get("obv")),
            "obv_ema9": finite_number(fields.get("obv_ema9")),
        }
    elif kind == "scan_row":
        prepared = {
            "price": finite_number(observation.get("price")),
            "ema9": finite_number(observation.get("ema9")),
            "ma20": finite_number(observation.get("ma20")),
            "obv": finite_number(observation.get("obv")),
            "obv_ema9": finite_number(observation.get("obv_ema9")),
        }
        if not freshness["session_match"]:
            return None, _blank_row(
                symbol,
                session,
                "SESSION_MISMATCH",
                freshness=freshness,
                position_inputs_ignored=position_ignored,
            )
    else:
        return None, _blank_row(
            symbol,
            session,
            "OBSERVATION_ABSENT",
            freshness=freshness,
            position_inputs_ignored=position_ignored,
        )
    if not isinstance(provenance, str) or not provenance.strip():
        return None, _blank_row(
            symbol,
            session,
            "PROVENANCE_ABSENT",
            freshness=freshness,
            inputs=prepared,
            position_inputs_ignored=position_ignored,
        )
    if freshness["quality"] is None or freshness["source"] is None:
        return None, _blank_row(
            symbol,
            session,
            "QUALITY_ABSENT",
            freshness=freshness,
            inputs=prepared,
            reference_price_provenance=provenance.strip(),
            position_inputs_ignored=position_ignored,
        )
    if prepared["price"] is None or prepared["ema9"] is None or prepared["ma20"] is None:
        return None, _blank_row(
            symbol,
            session,
            "INPUT_INCOMPLETE",
            freshness=freshness,
            inputs=prepared,
            reference_price=prepared["price"],
            reference_price_provenance=provenance.strip(),
            position_inputs_ignored=position_ignored,
        )
    prepared["provenance"] = provenance.strip()
    prepared["position_inputs_ignored"] = position_ignored
    prepared["freshness"] = freshness
    return prepared, None


def evaluate_symbol(symbol: str, session: str, observation: dict | None) -> dict:
    """Classify one symbol from market inputs. Position fields are ignored."""
    code = str(symbol or "").strip().upper()
    if observation is None:
        return _blank_row(code, session, "OBSERVATION_ABSENT")
    prepared, rejected = _prepare_inputs(observation, session, code)
    if rejected is not None:
        return rejected
    from position_guardian import generate_signal

    signal, reason, score = generate_signal(
        pd.Series(
            {
                "price": prepared["price"],
                "ema9": prepared["ema9"],
                "ma20": prepared["ma20"],
                "obv": prepared["obv"] if prepared["obv"] is not None else float("nan"),
                "obv_ema9": prepared["obv_ema9"] if prepared["obv_ema9"] is not None else float("nan"),
            }
        )
    )
    research = PRODUCTION_TO_RESEARCH.get(signal)
    if research is None:
        return _blank_row(
            code,
            session,
            "UNMAPPED_PRODUCTION_SIGNAL",
            production_signal=signal,
            freshness=prepared["freshness"],
            inputs={key: prepared[key] for key in ("price", "ema9", "ma20", "obv", "obv_ema9")},
            reference_price=prepared["price"],
            reference_price_provenance=prepared["provenance"],
            position_inputs_ignored=prepared["position_inputs_ignored"],
        )
    parts = _score_parts(
        prepared["price"],
        prepared["ema9"],
        prepared["ma20"],
        prepared["obv"],
        prepared["obv_ema9"],
    )
    return {
        "symbol": code,
        "session": session,
        "classification": research,
        "classification_scope": SCOPE_MARKET_TECHNICAL,
        "portfolio_decision": False,
        "position_inputs_used": False,
        "position_inputs_required": False,
        "position_inputs_ignored": prepared["position_inputs_ignored"],
        "production_signal": signal,
        "reason": reason,
        "score": int(score),
        "score_parts": parts,
        "reference_price": prepared["price"],
        "reference_price_provenance": prepared["provenance"],
        "inputs": {key: prepared[key] for key in ("price", "ema9", "ma20", "obv", "obv_ema9")},
        "freshness": prepared["freshness"],
        "classification_version": classification_version(),
    }


def normalize_market_context(market: dict | None) -> dict:
    """Record Market Real only when the caller supplies both value and provenance."""
    supplied = market or {}
    value = finite_number(supplied.get("market_real")) if "market_real" in supplied else None
    provenance = supplied.get("market_real_provenance")
    proven = isinstance(provenance, str) and bool(provenance.strip())
    context = {
        "market_real": value if proven else None,
        "market_real_provenance": provenance.strip() if proven and value is not None else None,
        "market_real_status": "supplied" if proven and value is not None else "unavailable",
        "used_by_generate_signal": False,
    }
    for key in ("market_live", "market_forecast", "regime"):
        if key in supplied and supplied[key] not in (None, ""):
            item_provenance = supplied.get(key + "_provenance")
            if isinstance(item_provenance, str) and item_provenance.strip():
                context[key] = supplied[key]
                context[key + "_provenance"] = item_provenance.strip()
            else:
                context[key] = None
                context[key + "_status"] = "provenance_absent"
    return context
