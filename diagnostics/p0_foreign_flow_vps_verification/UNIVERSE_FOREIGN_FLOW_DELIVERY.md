# P0 Universe-142 Foreign Flow — delivery

## FINAL VERDICT

`P0_UNIVERSE_FOREIGN_FLOW_PARTIAL`

Forward collection works (COMPLETE via coherent VCI when HSX cannot cover multi-exchange EMS).  
Historical HSX aggregates are honest **PARTIAL** (~117/142) because ~25 EMS names are HNX/UPCOM (empty on official HSX foreign API).

---

### Canonical definition

| Field | Meaning |
| --- | --- |
| `universe_foreign_buy_value` | Σ foreign buy VALUE over EMS membership-asof (VND) |
| `universe_foreign_sell_value` | Σ foreign sell VALUE (VND) |
| `universe_foreign_net_value` | buy − sell (VND) |
| optional volumes | when all observed symbols have volumes |
| `universe_foreign_scope` | `EMS_RESEARCH_UNIVERSE_142` |
| units | **VND** |

**Not** HOSE-wide / VNINDEX / whole-market foreign flow.

**Membership-asof rule:** `EMS_SNAPSHOT_DATE_EXACT` — symbols = unique EMS `symbol` where `snapshot_date == trade_date`. No today’s 142 applied to past dates.

Schema: `p0_market_memory_v2` (additive columns; legacy SSI `foreign_*` left NULL).

### Source hierarchy

`HSX (prefer COMPLETE) → coherent VCI COMPLETE (forward session) → HSX PARTIAL → VCI PARTIAL → NULL/status`

One coherent source per aggregate (no silent mixed symbol rows).

### Historical recovery (EMS-backed)

| Metric | Value |
| --- | --- |
| Date range | **2026-07-31 → 2026-08-24** (17 EMS weekday sessions) |
| COMPLETE | **1** (`2026-08-24`, source=`vci_price_board`) |
| PARTIAL | **16** (HSX-only; ~117/142 HOSE names) |
| Unavailable | **0** among EMS membership dates |

Earliest recoverable PARTIAL aggregate: `2026-07-31`.  
No fabricated months beyond EMS membership history.

### Forward collection

Yes — `market_t0_capture` → `maybe_freeze_after_market_daily` → `maybe_collect_p0_after_market_daily` attempts universe foreign after close (fail-safe). Streamlit need not stay open if that host job runs. On production collector (`vnstock 4.0.5`), VCI can COMPLETE multi-exchange EMS; HSX remains primary when it can COMPLETE.

### Data quality example (`2026-08-24`)

- expected: **142**
- observed: **142**
- completeness: **COMPLETE**
- source: **vci_price_board**
- units: **VND**
- net: `208515123800` (= buy `1850960325800` − sell `1642445202000`)

Example PARTIAL (`2026-08-21` via HSX): observed ~117/142; missing HNX/UPCOM names recorded in `universe_foreign_missing_symbols_json`.

### Tests

- `tests/test_p0_universe_foreign_flow.py` + updated `test_p0_forward_market_memory.py`: **24 passed**
- Forecast / MDRR / VPS-verify regressions: **32 passed**

### Remaining gaps

| Type | Detail |
| --- | --- |
| **Intentional / structural** | Official HSX foreign API has no rows for HNX/UPCOM EMS members → historical COMPLETE impossible via HSX alone |
| **Intentional** | VCI is FORWARD_ONLY (no fake history) |
| **Intentional** | Not fed into Forecast / Market First / trading gates yet |
| **Technical** | Daily HSX probe of 142 symbols is slower than VCI batches; cascade prefers VCI COMPLETE for forward when HSX is PARTIAL |

No P1 / Forecast modeling started.
