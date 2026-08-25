# Bias and Leakage Audit — Foreign Flow History

## Register

| Risk | Severity | Finding | Mitigation (design) |
|------|----------|---------|---------------------|
| Survivorship / current-universe projection | **HIGH** | Using today’s EMS-142 or today’s 117 HOSE names for 2009–2025 favors survivors | Prefer membership-asof when available; else label panel `CURRENT_HOSE_SUBSET_PROJECTED` and treat as biased |
| Look-ahead | **MED** | Same-day close in HSX row is after-session; using it as T0 feature for same-day signal is OK only if research defines T0 as after-close | Document T0 = after-close session snapshot; no intraday claim |
| Listing / delisting | **MED** | Newer names (NAB, SIP) have short histories; empties for non-HOSE | Per-symbol start date; don’t pad with zeros |
| Missing ≠ 0 | **HIGH** | Empty HSX list or absent date must stay NULL | Fail-closed; never fill 0 for missing foreign |
| Holidays / non-trading | **LOW** | Gaps vs business-day calendar match holiday pattern | Use trading-session calendar only |
| Provider revisions | **UNK** | Not proven whether HSX rewrites past `reportDate` rows | Store retrieved_at + raw hash; first-write-wins on research store |
| Liquidity / large-cap concentration | **HIGH** | Long history dominated by liquid HOSE names | Stratify / weight / exclude microcaps in research phase |
| Sector concentration | **MED** | Banks/real-estate heavy in EMS | Sector-aware holdout later; EMS lacks sector historically |
| Corporate actions | **MED** | OHLC from HSX may be unadjusted; return calcs sensitive to splits | Flag; prefer adjustment source if later available; sensitivity tests |
| ADV / turnover denominator leakage | **MED** | Using future volume windows | Rolling past-only ADV; or skip until volume history exists |
| Market-context leakage | **LOW** now | Context series short | Don’t invent regime labels for 2009–2025 |
| Same-day timing | **MED** | VCI forward is live board; HSX historical is dated session | Separate FORWARD vs HISTORICAL provenance |
| Exchange mislabel | **HIGH** | Aggregating HNX empties into EMS-142 without coverage | Publish `n_hose_observed` / `n_expected`; PARTIAL ≠ invent |

## Explicit prohibitions

- Do not teach “foreign selling → underperformance” as ground truth.
- Do not treat EMS-142 aggregate history as HOSE-wide market foreign flow.
- Do not backfill production P0 rows with projected membership without a labeled bias policy.
