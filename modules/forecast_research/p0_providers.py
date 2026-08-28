"""
P0 market data providers — fail-safe, injectable.

Missing source → None (never coerce to 0).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

import numpy as np
import pandas as pd

from modules.forecast_research.contract import (
    P0_FOREIGN_SCOPE_DEFAULT,
    P0_UNIVERSE_TURNOVER_SCOPE,
    P0_VNINDEX_VOLUME_SCOPE,
)
from modules.forecast_research.t0_builder import DEFAULT_EMS, DEFAULT_MDT0, load_board, load_market_daily

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _finite_or_none(value: Any) -> Optional[float]:
    """Convert to float; missing/invalid → None. Explicit 0.0 is preserved."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(v) or np.isinf(v):
        return None
    return v


@dataclass
class ProviderResult:
    ok: bool
    status: str  # OK | MISSING | SOURCE_ERROR
    values: Dict[str, Optional[float]] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class ForeignFlowProvider(Protocol):
    def fetch(self, trade_date: str) -> ProviderResult: ...


class VnindexHistoryProvider(Protocol):
    def fetch_ohlcv(self, end_date: str, lookback_days: int = 120) -> pd.DataFrame: ...


@dataclass
class SsiHoseForeignFlowProvider:
    """
    Aggregate foreign buy/sell value from SSI iBoard exchange heatmap (HOSE).

    Scope: HOSE-listed names returned by the endpoint (not full Vietnam market).
    Units: provider-native until independently proven — do not assume VND scale.
    Historical: unsupported (API has no trade_date) → forward-only collection.
    """

    scope: str = P0_FOREIGN_SCOPE_DEFAULT

    def _meta(self, **extra: Any) -> Dict[str, Any]:
        base = {
            "provider": "ssi_fr_trade_heatmap",
            "scope": self.scope,
            "foreign_flow_scope": self.scope,  # explicit provenance alias
            "units": "PROVIDER_NATIVE_UNPROVEN",
            "historical_supported": False,
            "forward_only": True,
        }
        base.update(extra)
        return base

    def fetch(self, trade_date: str) -> ProviderResult:
        try:
            from vnstock import fr_trade_heatmap
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(
                ok=False,
                status="SOURCE_ERROR",
                error=f"vnstock_import:{exc}",
                meta=self._meta(),
            )
        try:
            import contextlib
            import io

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                df = fr_trade_heatmap(symbol=self.scope, report_type="FrBuyVal")
            captured = buf.getvalue()[:500]
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(
                ok=False,
                status="SOURCE_ERROR",
                error=f"fetch_exception:{exc}",
                meta=self._meta(),
            )
        if df is None:
            return ProviderResult(
                ok=False,
                status="SOURCE_ERROR",
                error="null_dataframe",
                meta=self._meta(provider_stdout=captured or None),
            )
        if getattr(df, "empty", True):
            return ProviderResult(
                ok=False,
                status="MISSING",
                error="empty_dataframe",
                meta=self._meta(),
            )

        cols = {str(c).lower(): c for c in df.columns}
        buy_val_col = self._pick(cols, ("foreign_buy_value", "frbuyval", "buy_val", "foreignbuyvalue", "fbuy_val"))
        sell_val_col = self._pick(cols, ("foreign_sell_value", "frsellval", "sell_val", "foreignsellvalue", "fsell_val"))
        buy_vol_col = self._pick(cols, ("foreign_buy_volume", "frbuyvol", "buy_vol", "foreignbuyvolume"))
        sell_vol_col = self._pick(cols, ("foreign_sell_volume", "frsellvol", "sell_vol", "foreignsellvolume"))

        if buy_val_col is None and sell_val_col is None:
            return ProviderResult(
                ok=False,
                status="SOURCE_ERROR",
                error=f"no_foreign_value_columns:{list(df.columns)[:20]}",
                meta=self._meta(),
            )

        def _sum_col(col: Optional[Any]) -> Optional[float]:
            if col is None:
                return None
            s = pd.to_numeric(df[col], errors="coerce")
            if s.notna().sum() == 0:
                return None  # missing, not zero
            return float(s.sum(min_count=1))

        buy_v = _sum_col(buy_val_col)
        sell_v = _sum_col(sell_val_col)
        net_v = None
        if buy_v is not None and sell_v is not None:
            net_v = buy_v - sell_v

        buy_vol = _sum_col(buy_vol_col)
        sell_vol = _sum_col(sell_vol_col)
        net_vol = None
        if buy_vol is not None and sell_vol is not None:
            net_vol = buy_vol - sell_vol

        return ProviderResult(
            ok=True,
            status="OK",
            values={
                "foreign_buy_value": buy_v,
                "foreign_sell_value": sell_v,
                "foreign_net_value": net_v,
                "foreign_buy_volume": buy_vol,
                "foreign_sell_volume": sell_vol,
                "foreign_net_volume": net_vol,
            },
            meta=self._meta(
                n_rows=int(len(df)),
                observed_at=_utc_now_iso(),
                trade_date_requested=trade_date,
                note=(
                    "Live HOSE exchange heatmap; response is session-current "
                    "(no historical date parameter). Label as HOSE foreign flow, not whole-market."
                ),
            ),
        )

    @staticmethod
    def _pick(cols: Dict[str, Any], names: tuple) -> Optional[Any]:
        for n in names:
            if n in cols:
                return cols[n]
        # fuzzy contains
        for key, orig in cols.items():
            for n in names:
                if n in key.replace("_", ""):
                    return orig
        return None


@dataclass
class VnstockVnindexHistoryProvider:
    """VNINDEX daily OHLCV via existing project provider (vnstock stock_historical_data)."""

    def fetch_ohlcv(self, end_date: str, lookback_days: int = 120) -> pd.DataFrame:
        try:
            from vnstock import stock_historical_data
        except Exception:
            return pd.DataFrame()
        end = pd.Timestamp(end_date).date()
        start = (pd.Timestamp(end_date) - pd.Timedelta(days=int(lookback_days))).date()
        for cfg in ({"symbol": "VNINDEX", "type": "index"}, {"symbol": "VNINDEX", "type": "stock"}):
            try:
                df = stock_historical_data(
                    symbol=cfg["symbol"],
                    start_date=start.isoformat(),
                    end_date=end.isoformat(),
                    resolution="1D",
                    type=cfg["type"],
                    beautify=True,
                )
            except Exception:
                continue
            if df is None or df.empty:
                continue
            rename = {}
            for col in df.columns:
                cl = str(col).lower()
                if "time" in cl or "date" in cl:
                    rename[col] = "date"
                elif cl == "open":
                    rename[col] = "open"
                elif cl == "high":
                    rename[col] = "high"
                elif cl == "low":
                    rename[col] = "low"
                elif cl == "close":
                    rename[col] = "close"
                elif cl == "volume":
                    rename[col] = "volume"
            df = df.rename(columns=rename)
            if "date" not in df.columns or "close" not in df.columns:
                continue
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
            df = df.dropna(subset=["date", "close"]).sort_values("date")
            return df.reset_index(drop=True)
        return pd.DataFrame()


def compute_universe_turnover_from_ems(
    trade_date: str,
    *,
    ems_path: Path = DEFAULT_EMS,
) -> ProviderResult:
    """
    Observed research-universe traded value = sum(price * volume) on EMS snapshot.

    Scope: EMS 142 research board — NOT official whole-market HOSE/VN turnover.
    Missing price/volume → that symbol contributes nothing; if board empty → MISSING.
    """
    board = load_board(ems_path, trade_date)
    meta = {
        "provider": "earning_money_snapshots",
        "scope": P0_UNIVERSE_TURNOVER_SCOPE,
        "path": str(ems_path),
    }
    if board.empty:
        return ProviderResult(ok=False, status="MISSING", error="empty_board", meta=meta)
    if "price" not in board.columns or "volume" not in board.columns:
        return ProviderResult(ok=False, status="SOURCE_ERROR", error="missing_price_or_volume_cols", meta=meta)
    price = pd.to_numeric(board["price"], errors="coerce")
    volume = pd.to_numeric(board["volume"], errors="coerce")
    # Do not fillna(0) for missing — exclude NaN pairs only
    mask = price.notna() & volume.notna()
    if not mask.any():
        return ProviderResult(ok=False, status="MISSING", error="all_price_volume_nan", meta=meta)
    turnover = float((price[mask] * volume[mask]).sum())
    total_volume = float(volume[mask].sum())
    meta.update(
        {
            "universe_count": int(board["symbol"].nunique()) if "symbol" in board.columns else int(len(board)),
            "n_with_price_volume": int(mask.sum()),
            "observed_at": _utc_now_iso(),
        }
    )
    return ProviderResult(
        ok=True,
        status="OK",
        values={
            "universe_turnover_value": turnover,
            "universe_volume": total_volume,
        },
        meta=meta,
    )


def vnindex_volume_from_mdt0_or_fetch(
    trade_date: str,
    *,
    md_path: Path = DEFAULT_MDT0,
    history_provider: Optional[VnindexHistoryProvider] = None,
) -> ProviderResult:
    meta = {"scope": P0_VNINDEX_VOLUME_SCOPE}
    md = load_market_daily(md_path, trade_date)
    if md is not None and pd.notna(md.get("vnindex_volume")):
        vol = _finite_or_none(md.get("vnindex_volume"))
        meta.update({"provider": "market_daily_t0", "observed_at": _utc_now_iso()})
        return ProviderResult(
            ok=vol is not None,
            status="OK" if vol is not None else "MISSING",
            values={"vnindex_volume": vol},
            meta=meta,
        )
    provider = history_provider or VnstockVnindexHistoryProvider()
    hist = provider.fetch_ohlcv(trade_date, lookback_days=30)
    if hist.empty:
        return ProviderResult(
            ok=False,
            status="SOURCE_ERROR",
            error="vnindex_history_unavailable",
            meta={**meta, "provider": "vnstock_stock_historical_data"},
        )
    hit = hist[hist["date"].astype(str).str[:10] == trade_date]
    if hit.empty or "volume" not in hit.columns:
        return ProviderResult(
            ok=False,
            status="MISSING",
            error="trade_date_not_in_history",
            meta={**meta, "provider": "vnstock_stock_historical_data"},
        )
    vol = _finite_or_none(hit.iloc[-1]["volume"])
    return ProviderResult(
        ok=vol is not None,
        status="OK" if vol is not None else "MISSING",
        values={"vnindex_volume": vol},
        meta={**meta, "provider": "vnstock_stock_historical_data", "observed_at": _utc_now_iso()},
    )
