"""Shared Research D1 Archive Stage A — raw historical D1 research store.

Research-only. Adjustment status is UNVERIFIED. Candidate VNINDEX session
index is explicitly not verified. Does not feed Research Ledger B1 or
Guardian outcome engines. DNSE/vnstock specifics live in ``fetcher``.
"""

from research.shared_d1_archive.collector import (
    CollectReport,
    build_candidate_vnindex_session_index,
    collect_shared_d1_archive,
    rows_from_ohlcv,
    write_candidate_session_index,
)
from research.shared_d1_archive.contract import (
    ADJUSTMENT_UNVERIFIED,
    SCHEMA_OBSERVATION,
    SCHEMA_SESSION_INDEX,
    SESSION_INDEX_STATUS,
    VNINDEX_SYMBOL,
    observation_may_feed_research_outcomes,
    session_index_may_feed_verified_calendar,
)
from research.shared_d1_archive.fetcher import (
    DNSE_PROVIDER,
    default_fetch_provenance,
    fetch_symbol_d1,
    fetch_vnindex_d1,
    normalize_ohlcv_frame,
)
from research.shared_d1_archive.store import D1ArchiveStore, default_history_dir
from research.shared_d1_archive.universe import load_watchlist

__all__ = [
    "ADJUSTMENT_UNVERIFIED",
    "CollectReport",
    "DNSE_PROVIDER",
    "D1ArchiveStore",
    "SCHEMA_OBSERVATION",
    "SCHEMA_SESSION_INDEX",
    "SESSION_INDEX_STATUS",
    "VNINDEX_SYMBOL",
    "build_candidate_vnindex_session_index",
    "collect_shared_d1_archive",
    "default_fetch_provenance",
    "default_history_dir",
    "fetch_symbol_d1",
    "fetch_vnindex_d1",
    "load_watchlist",
    "normalize_ohlcv_frame",
    "observation_may_feed_research_outcomes",
    "rows_from_ohlcv",
    "session_index_may_feed_verified_calendar",
    "write_candidate_session_index",
]
