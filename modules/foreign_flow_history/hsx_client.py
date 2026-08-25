"""Respectful official HSX foreign-history HTTP client (paginated, paced, resumable)."""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# Official HSX endpoint established in foreign-flow historical audit / PR #93.
HSX_FOREIGN_URL = "https://api.hsx.vn/mk/api/v1/market/securities/foreign/{symbol}"

HSX_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.hsx.vn",
    "Referer": "https://www.hsx.vn/du-lieu-giao-dich/giao-dich-ndtnn",
    "User-Agent": "MRBOT-ForeignFlowHistory/1.0 (research-backfill; respectful)",
}

# Prefer moderate page size + pagination over flaky huge payloads.
DEFAULT_PAGE_SIZE = 1000
FULL_HISTORY_PAGE_SIZE = 5000
DEFAULT_TIMEOUT_SEC = 60.0
DEFAULT_PACING_SEC = 0.3
DEFAULT_MAX_RETRIES = 4
DEFAULT_BACKOFF_BASE_SEC = 2.0


class ProviderRateLimited(RuntimeError):
    """Raised when the provider signals rate limiting / rejection."""


class ProviderTransientError(RuntimeError):
    """Transient network/provider failure after retries exhausted."""


@dataclass
class FetchResult:
    symbol: str
    pages: List[Dict[str, Any]] = field(default_factory=list)
    page_count: int = 0
    raw_row_count: int = 0
    total_count_hint: Optional[int] = None
    http_status_last: Optional[int] = None
    stopped_reason: str = "ok"
    mode: str = "paginated"
    errors: List[str] = field(default_factory=list)


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


def build_url(symbol: str, *, page_size: int, page_index: Optional[int] = None) -> str:
    sym = urllib.parse.quote(str(symbol).strip().upper(), safe="")
    base = HSX_FOREIGN_URL.format(symbol=sym)
    qs = f"pageSize={int(page_size)}"
    if page_index is not None:
        qs += f"&pageIndex={int(page_index)}"
    return f"{base}?{qs}"


def extract_paging(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict) and isinstance(data.get("paging"), dict):
        return dict(data["paging"])
    if isinstance(payload.get("paging"), dict):
        return dict(payload["paging"])
    return {}


def http_get_json(
    url: str,
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    opener: Optional[Callable[..., Any]] = None,
) -> Tuple[int, Dict[str, Any]]:
    req = urllib.request.Request(url, headers=dict(HSX_HEADERS), method="GET")

    def _default_open(request: urllib.request.Request, timeout: float):
        return urllib.request.urlopen(request, timeout=timeout, context=_ssl_context())

    open_fn = opener or _default_open
    try:
        with open_fn(req, timeout_sec) as resp:
            status = int(getattr(resp, "status", None) or resp.getcode())
            body = resp.read()
    except urllib.error.HTTPError as e:
        status = int(e.code)
        if status in (403, 429, 503):
            raise ProviderRateLimited(f"HTTP {status} for {url}") from e
        if status >= 500:
            raise ProviderTransientError(f"HTTP {status} for {url}") from e
        raise ProviderTransientError(f"HTTP {status} for {url}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        # IncompleteRead often surfaces as ProtocolError / OSError subclass
        raise ProviderTransientError(f"URL/IO error for {url}: {e}") from e
    except Exception as e:
        raise ProviderTransientError(f"Request failed for {url}: {e}") from e

    if status in (403, 429, 503):
        raise ProviderRateLimited(f"HTTP {status} for {url}")

    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except Exception as e:
        raise ProviderTransientError(f"Invalid JSON for {url}: {e}") from e
    if not isinstance(payload, dict):
        raise ProviderTransientError(f"Non-object JSON for {url}")
    return status, payload


def fetch_with_retries(
    url: str,
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base_sec: float = DEFAULT_BACKOFF_BASE_SEC,
    opener: Optional[Callable[..., Any]] = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> Tuple[int, Dict[str, Any]]:
    last_err: Optional[BaseException] = None
    for attempt in range(max_retries + 1):
        try:
            return http_get_json(url, timeout_sec=timeout_sec, opener=opener)
        except ProviderRateLimited:
            raise
        except ProviderTransientError as e:
            last_err = e
            if attempt >= max_retries:
                break
            sleeper(backoff_base_sec * (2**attempt))
    raise ProviderTransientError(str(last_err) if last_err else "fetch failed")


def _page_row_count(payload: Dict[str, Any]) -> int:
    from modules.foreign_flow_history.parse import extract_list

    return len(extract_list(payload))


def fetch_symbol_pages(
    symbol: str,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    # Default False: large pageSize=5000 often IncompleteReads; paginated 500–1000 is safer.
    prefer_full_page: bool = False,
    full_page_size: int = FULL_HISTORY_PAGE_SIZE,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    pacing_sec: float = DEFAULT_PACING_SEC,
    max_retries: int = DEFAULT_MAX_RETRIES,
    max_pages: int = 80,
    opener: Optional[Callable[..., Any]] = None,
    sleeper: Callable[[float], None] = time.sleep,
    stop_on_rate_limit: bool = True,
) -> FetchResult:
    """
    Fetch full HSX foreign history for one symbol.

    Strategy:
    1. Prefer a single large ``pageSize`` request (audit-proven ~5000).
    2. On transient failure, fall back to moderate ``pageSize`` + ``pageIndex`` walk.
    """
    result = FetchResult(symbol=str(symbol).strip().upper())

    if prefer_full_page:
        url = build_url(result.symbol, page_size=full_page_size, page_index=None)
        try:
            status, payload = fetch_with_retries(
                url,
                timeout_sec=timeout_sec,
                max_retries=max_retries,
                opener=opener,
                sleeper=sleeper,
            )
            result.http_status_last = status
            result.pages = [payload]
            result.page_count = 1
            result.raw_row_count = _page_row_count(payload)
            paging = extract_paging(payload)
            try:
                result.total_count_hint = int(paging["totalCount"]) if "totalCount" in paging else None
            except Exception:
                result.total_count_hint = None
            result.mode = "full_page"
            # If we clearly under-fetched vs totalCount, fall through to pagination.
            if (
                result.total_count_hint is not None
                and result.raw_row_count < result.total_count_hint
                and result.raw_row_count < full_page_size
            ):
                result.errors.append(
                    f"full_page_short n={result.raw_row_count} total={result.total_count_hint}"
                )
            else:
                result.stopped_reason = "ok"
                return result
        except ProviderRateLimited as e:
            result.errors.append(str(e))
            result.stopped_reason = "rate_limited"
            if stop_on_rate_limit:
                return result
        except ProviderTransientError as e:
            result.errors.append(f"full_page_failed:{e}")
            # fall through to pagination

    # Paginated walk: pageIndex is 1-based for recent window; higher indices → older.
    result.mode = "paginated"
    result.pages = []
    result.page_count = 0
    result.raw_row_count = 0
    total_pages: Optional[int] = None

    for page_idx in range(1, max_pages + 1):
        if page_idx > 1 and pacing_sec > 0:
            sleeper(pacing_sec)
        url = build_url(result.symbol, page_size=page_size, page_index=page_idx)
        try:
            status, payload = fetch_with_retries(
                url,
                timeout_sec=timeout_sec,
                max_retries=max_retries,
                opener=opener,
                sleeper=sleeper,
            )
        except ProviderRateLimited as e:
            result.errors.append(str(e))
            result.stopped_reason = "rate_limited"
            if stop_on_rate_limit:
                return result
            break
        except ProviderTransientError as e:
            result.errors.append(str(e))
            result.stopped_reason = "transient_error"
            return result

        result.http_status_last = status
        n = _page_row_count(payload)
        result.pages.append(payload)
        result.page_count += 1
        result.raw_row_count += n

        paging = extract_paging(payload)
        try:
            if "totalCount" in paging:
                result.total_count_hint = int(paging["totalCount"])
            if "totalPages" in paging:
                total_pages = int(paging["totalPages"])
        except Exception:
            pass

        if n == 0:
            result.stopped_reason = "empty_page"
            break
        if total_pages is not None and page_idx >= total_pages:
            result.stopped_reason = "total_pages_exhausted"
            break
        if n < page_size:
            result.stopped_reason = "short_page"
            break
    else:
        result.stopped_reason = "max_pages"

    return result


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "FULL_HISTORY_PAGE_SIZE",
    "FetchResult",
    "HSX_FOREIGN_URL",
    "ProviderRateLimited",
    "ProviderTransientError",
    "build_url",
    "extract_paging",
    "fetch_symbol_pages",
    "fetch_with_retries",
    "http_get_json",
]
