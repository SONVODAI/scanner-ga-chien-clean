"""Exact-date HSX fetch for confirmation forward panel (reuse history client)."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from modules.foreign_flow_history.hsx_client import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_PACING_SEC,
    DEFAULT_TIMEOUT_SEC,
    ProviderRateLimited,
    ProviderTransientError,
    build_url,
    extract_paging,
    fetch_with_retries,
)
from modules.foreign_flow_history.parse import parse_payload_to_rows

LAST_IN_SAMPLE = "2026-08-24"


def select_exact_date_rows(
    rows: List[Dict[str, Any]],
    *,
    trade_date: str,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Fail-closed exact-date gate.
    - Keep only reportDate/trade_date == trade_date
    - Reject pre-freeze and future relative to trade_date mismatch
    - Missing date ≠ substitute with another day
    """
    target = str(trade_date)[:10]
    rejects: List[str] = []
    if target <= LAST_IN_SAMPLE:
        return [], ["freeze_boundary"]

    matched: List[Dict[str, Any]] = []
    for row in rows:
        td = str(row.get("trade_date") or "")[:10]
        if not td:
            rejects.append("missing_trade_date")
            continue
        if td != target:
            rejects.append(f"wrong_date:{td}")
            continue
        matched.append(row)

    # Deduplicate exact matches by row_hash / first-write
    seen = set()
    unique: List[Dict[str, Any]] = []
    for row in matched:
        key = row.get("row_hash") or (row.get("trade_date"), row.get("symbol"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique, rejects


def fetch_exact_trade_date_row(
    symbol: str,
    trade_date: str,
    *,
    page_size: int = 200,
    max_pages: int = 40,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    pacing_sec: float = DEFAULT_PACING_SEC,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base_sec: float = 2.0,
    opener: Optional[Callable[..., Any]] = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """
    Fetch HSX foreign pages until exact trade_date found or exhausted.

    Returns dict with keys: ok, rows, reason, pages_fetched, rate_limited, errors.
    Does not invent rows when provider omits the date.
    """
    target = str(trade_date)[:10]
    sym = str(symbol).strip().upper()
    if target <= LAST_IN_SAMPLE:
        return {
            "ok": False,
            "rows": [],
            "reason": "freeze_boundary",
            "pages_fetched": 0,
            "rate_limited": False,
            "errors": [],
        }

    collected: List[Dict[str, Any]] = []
    errors: List[str] = []
    pages_fetched = 0
    saw_older = False

    for page_index in range(1, max_pages + 1):
        url = build_url(sym, page_size=page_size, page_index=page_index)
        try:
            _status, payload = fetch_with_retries(
                url,
                timeout_sec=timeout_sec,
                max_retries=max_retries,
                backoff_base_sec=backoff_base_sec,
                opener=opener,
                sleeper=sleeper,
            )
        except ProviderRateLimited as exc:
            return {
                "ok": False,
                "rows": [],
                "reason": "rate_limited",
                "pages_fetched": pages_fetched,
                "rate_limited": True,
                "errors": [str(exc)],
            }
        except ProviderTransientError as exc:
            errors.append(str(exc))
            return {
                "ok": False,
                "rows": [],
                "reason": "provider_transient",
                "pages_fetched": pages_fetched,
                "rate_limited": False,
                "errors": errors,
            }

        pages_fetched += 1
        page_rows = parse_payload_to_rows(payload, symbol=sym)
        if not page_rows:
            break

        exact, _rej = select_exact_date_rows(page_rows, trade_date=target)
        collected.extend(exact)

        dates = [str(r.get("trade_date") or "")[:10] for r in page_rows]
        if any(d and d < target for d in dates) and not exact:
            # Provider pages typically newest-first; older than target without match → missing
            saw_older = True

        if exact:
            # Found; stop early
            break

        if saw_older:
            break

        paging = extract_paging(payload)
        try:
            total_pages = int(paging.get("totalPages") or 0)
        except Exception:
            total_pages = 0
        if total_pages and page_index >= total_pages:
            break
        if len(page_rows) < page_size:
            break
        sleeper(pacing_sec)

    exact, rejects = select_exact_date_rows(collected, trade_date=target)
    if not exact:
        return {
            "ok": False,
            "rows": [],
            "reason": "exact_date_missing",
            "pages_fetched": pages_fetched,
            "rate_limited": False,
            "errors": errors,
            "reject_samples": rejects[:20],
        }
    return {
        "ok": True,
        "rows": exact,
        "reason": "exact_date_found",
        "pages_fetched": pages_fetched,
        "rate_limited": False,
        "errors": errors,
    }
