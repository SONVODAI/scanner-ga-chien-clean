#!/usr/bin/env python3
"""
One-shot historical/universe foreign enrichment for EMS membership dates.

Uses Official HSX only (dated reportDate). Does not rewrite MDT0/MDRR/Forecast T0.
"""

from __future__ import annotations

import json
from pathlib import Path

from modules.forecast_research.outcome_maturity import list_board_trading_dates
from modules.forecast_research.p0_daily import collect_p0_for_date, load_p0_table, update_forward_only_registry_from_p0
from modules.forecast_research.p0_universe_foreign import HsXUniverseForeignProvider, UniverseForeignFlowCascade
from modules.forecast_research.t0_builder import DEFAULT_EMS
from modules.forecast_research.t0_persistence import resolve_forecast_data_dir


def main() -> int:
    data_dir = resolve_forecast_data_dir()
    dates = list_board_trading_dates(DEFAULT_EMS)
    hsx = HsXUniverseForeignProvider(ems_path=DEFAULT_EMS, page_size=80, sleep_s=0.03)
    # Historical path: HSX only (VCI prohibited for past dates)
    cascade = UniverseForeignFlowCascade(
        hsx=hsx,
        vci=None,  # will be created in post_init — replace after
        ems_path=DEFAULT_EMS,
        enable_cross_check=False,
    )

    # Replace VCI with a stub that always MISSING so cascade never invents history
    class _NoVci:
        def fetch(self, trade_date: str):
            from modules.forecast_research.p0_providers import ProviderResult

            return ProviderResult(
                ok=False,
                status="MISSING",
                error="vci_disabled_for_historical_backfill",
                meta={"provider": "vci_disabled", "historical_capability": "FORWARD_ONLY"},
            )

    cascade.vci = _NoVci()  # type: ignore

    results = []
    for d in dates:
        r = collect_p0_for_date(
            d,
            data_dir=data_dir,
            foreign_provider=cascade,
            collect_foreign=True,
            allow_foreign_enrichment=True,
        )
        results.append(r)
        print(
            d,
            r.get("reason"),
            "uf_comp=",
            r.get("universe_foreign_completeness"),
            "net=",
            r.get("universe_foreign_net_value"),
            flush=True,
        )

    update_forward_only_registry_from_p0(data_dir=data_dir)
    table = load_p0_table(data_dir)
    summary = {
        "n_ems_dates": len(dates),
        "n_results": len(results),
        "written_or_enriched": sum(1 for r in results if r.get("written")),
        "already_present": sum(1 for r in results if r.get("reason") == "ALREADY_PRESENT"),
    }
    if not table.empty and "universe_foreign_completeness" in table.columns:
        vc = table["universe_foreign_completeness"].fillna("NA").value_counts().to_dict()
        summary["completeness_counts"] = vc
        summary["date_min"] = str(table["trade_date"].astype(str).min())
        summary["date_max"] = str(table["trade_date"].astype(str).max())
        complete = table[table["universe_foreign_completeness"] == "COMPLETE"]
        summary["complete_n"] = int(len(complete))
        summary["complete_dates"] = complete["trade_date"].astype(str).str[:10].tolist()
        partial = table[table["universe_foreign_completeness"] == "PARTIAL"]
        summary["partial_n"] = int(len(partial))
        summary["partial_dates"] = partial["trade_date"].astype(str).str[:10].tolist()
    out = Path("diagnostics/p0_foreign_flow_vps_verification/universe_foreign_backfill_summary.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "results": results}, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
