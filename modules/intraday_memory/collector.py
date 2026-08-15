"""
Intraday collector core — independent of Streamlit.

Modes:
  - collect_session: single session EOD collection
  - reconcile_session: refetch and compare
  - bootstrap_range: historical range (controlled use)
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

from modules.intraday_memory.config import (
    COLLECTOR_VERSION,
    IntradayConfig,
    detect_tier,
)
from modules.intraday_memory.manifest import RunManifest, symbol_summary_entry
from modules.intraday_memory.provider import KBSProvider, ProviderAdapter
from modules.intraday_memory.reconciliation import reconcile_session
from modules.intraday_memory.schema import CanonicalBar
from modules.intraday_memory.storage import upsert_session
from modules.intraday_memory.timezone_policy import VN_TZ
from modules.intraday_memory.universe import load_production_universe
from modules.intraday_memory.validate import validate_raw_bar

logger = logging.getLogger(__name__)


class IntradayCollector:
    """
    Independent 5-minute OHLCV collector.

    No Streamlit, browser, or app.py runtime dependency.
    """

    def __init__(
        self,
        config: IntradayConfig | None = None,
        provider: ProviderAdapter | None = None,
    ) -> None:
        self.config = config or IntradayConfig.from_env()
        self.provider = provider or KBSProvider(
            requests_per_minute=self.config.requests_per_minute,
            max_retries=self.config.max_retries,
            retry_base_delay=self.config.retry_base_delay_sec,
        )
        self.data_root = Path(self.config.data_root)
        self.manifests_dir = self.data_root / "manifests"

    def _universe(self, symbols: Sequence[str] | None = None) -> list[str]:
        if symbols is not None:
            return sorted(set(s.upper() for s in symbols))
        return list(load_production_universe(self.config.app_py_path))

    def _new_manifest(self, **kwargs: Any) -> RunManifest:
        return RunManifest(
            provider=self.config.provider_source,
            collector_version=COLLECTOR_VERSION,
            storage_root=str(self.data_root),
            **kwargs,
        )

    def _finalize_and_save(
        self,
        manifest: RunManifest,
        per_symbol_summary: list[dict[str, Any]],
    ) -> RunManifest:
        manifest.finalize_observability(
            tier=detect_tier(),
            requests_per_minute=self.config.requests_per_minute,
            per_symbol_summary=per_symbol_summary,
        )
        manifest.save(self.manifests_dir)
        logger.info(manifest.summary_text())
        return manifest

    def _process_symbol_session(
        self,
        symbol: str,
        session_date: date,
        manifest: RunManifest,
        collected_at: datetime,
    ) -> tuple[list[CanonicalBar], dict[str, Any] | None]:
        raw_bars = self.provider.fetch_session(symbol, session_date)
        fetched = len(raw_bars)
        manifest.bars_fetched += fetched
        valid: list[CanonicalBar] = []
        rejected = 0

        for raw in raw_bars:
            outcome = validate_raw_bar(
                symbol,
                raw,
                collected_at=collected_at,
                source=self.config.source_tag,
                expected_session_date=session_date,
            )
            if outcome.accepted and outcome.bar:
                valid.append(outcome.bar)
                manifest.bars_valid += 1
            else:
                rejected += 1
                manifest.bars_rejected += 1
                logger.debug(
                    "Rejected bar %s %s: %s",
                    symbol, raw.get("time"), outcome.reason,
                )

        if fetched == 0:
            return valid, symbol_summary_entry(
                symbol,
                status="empty",
                reason="no_rows_returned",
            )
        if not valid:
            return valid, symbol_summary_entry(
                symbol,
                status="unusable",
                reason="all_bars_rejected",
                bars_fetched=fetched,
                bars_valid=0,
                bars_rejected=rejected,
            )
        return valid, None

    def collect_session(
        self,
        session_date: date,
        symbols: Sequence[str] | None = None,
    ) -> RunManifest:
        """Mode A: fetch completed 5m bars for all symbols, validate, persist."""
        universe = self._universe(symbols)
        manifest = self._new_manifest(
            mode="collect_session",
            requested_session=session_date.isoformat(),
            universe_count=len(universe),
        )
        collected_at = datetime.now(VN_TZ)
        all_bars: list[CanonicalBar] = []
        per_symbol_summary: list[dict[str, Any]] = []

        for symbol in universe:
            try:
                bars, issue = self._process_symbol_session(
                    symbol, session_date, manifest, collected_at
                )
                all_bars.extend(bars)
                manifest.symbols_success.append(symbol)
                if issue:
                    per_symbol_summary.append(issue)
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                manifest.symbols_failed[symbol] = reason
                per_symbol_summary.append(
                    symbol_summary_entry(
                        symbol,
                        status="failed",
                        reason=reason,
                    )
                )
                logger.error("Failed to collect %s: %s", symbol, reason)

        upsert = upsert_session(self.data_root, session_date, all_bars)
        manifest.bars_new = upsert.new
        manifest.bars_existing = upsert.existing
        manifest.bars_changed = upsert.changed
        manifest.duplicate_count = upsert.duplicate_count
        manifest.finish()
        return self._finalize_and_save(manifest, per_symbol_summary)

    def collect_session_idempotent(
        self,
        session_date: date,
        symbols: Sequence[str] | None = None,
    ) -> RunManifest:
        """Collect and return manifest; safe to run twice."""
        return self.collect_session(session_date, symbols)

    def reconcile(
        self,
        session_date: date,
        symbols: Sequence[str] | None = None,
    ) -> tuple[RunManifest, dict[str, Any]]:
        """Mode B: refetch session, compare, fill missing, detect changes."""
        universe = self._universe(symbols)
        symbol_bars: dict[str, list[dict[str, Any]]] = {}
        per_symbol_summary: list[dict[str, Any]] = []

        for symbol in universe:
            try:
                bars = self.provider.fetch_session(symbol, session_date)
                symbol_bars[symbol] = bars
                if not bars:
                    per_symbol_summary.append(
                        symbol_summary_entry(
                            symbol,
                            status="empty",
                            reason="no_rows_returned",
                        )
                    )
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                per_symbol_summary.append(
                    symbol_summary_entry(
                        symbol,
                        status="failed",
                        reason=reason,
                    )
                )

        manifest, report = reconcile_session(
            self.data_root,
            session_date,
            symbol_bars,
            source=self.config.source_tag,
            requests_per_minute=self.config.requests_per_minute,
        )
        manifest.symbols_failed = {
            s["symbol"]: s["reason"]
            for s in per_symbol_summary
            if s.get("status") == "failed"
        }
        manifest.symbols_success = [
            s for s in universe if s not in manifest.symbols_failed
        ]
        manifest.finish()
        self._finalize_and_save(manifest, per_symbol_summary)
        return manifest, report

    def bootstrap_range(
        self,
        start: date,
        end: date,
        symbols: Sequence[str] | None = None,
    ) -> RunManifest:
        """Mode C: fetch 5m history for date range, persist idempotently."""
        universe = self._universe(symbols)
        manifest = self._new_manifest(
            mode="bootstrap_range",
            requested_range=f"{start.isoformat()}..{end.isoformat()}",
            universe_count=len(universe),
        )
        collected_at = datetime.now(VN_TZ)
        per_symbol_summary: list[dict[str, Any]] = []

        current = start
        while current <= end:
            day_bars: list[CanonicalBar] = []
            for symbol in universe:
                try:
                    raw_list = self.provider.fetch_range(symbol, current, current)
                    manifest.bars_fetched += len(raw_list)
                    sym_valid = 0
                    sym_rejected = 0
                    for raw in raw_list:
                        outcome = validate_raw_bar(
                            symbol, raw,
                            collected_at=collected_at,
                            source=self.config.source_tag,
                            expected_session_date=current,
                        )
                        if outcome.accepted and outcome.bar:
                            day_bars.append(outcome.bar)
                            sym_valid += 1
                            manifest.bars_valid += 1
                        else:
                            sym_rejected += 1
                            manifest.bars_rejected += 1
                    if not raw_list:
                        per_symbol_summary.append(
                            symbol_summary_entry(
                                symbol,
                                status="empty",
                                reason=f"no_rows_returned:{current.isoformat()}",
                            )
                        )
                    elif sym_valid == 0:
                        per_symbol_summary.append(
                            symbol_summary_entry(
                                symbol,
                                status="unusable",
                                reason=f"all_bars_rejected:{current.isoformat()}",
                                bars_fetched=len(raw_list),
                                bars_rejected=sym_rejected,
                            )
                        )
                    manifest.symbols_success.append(symbol)
                except Exception as exc:
                    reason = str(exc)
                    manifest.symbols_failed[symbol] = reason
                    per_symbol_summary.append(
                        symbol_summary_entry(
                            symbol,
                            status="failed",
                            reason=reason,
                        )
                    )
            upsert = upsert_session(self.data_root, current, day_bars)
            manifest.bars_new += upsert.new
            manifest.bars_existing += upsert.existing
            manifest.bars_changed += upsert.changed
            current += timedelta(days=1)

        manifest.symbols_success = sorted(set(manifest.symbols_success))
        manifest.finish()
        return self._finalize_and_save(manifest, per_symbol_summary)
