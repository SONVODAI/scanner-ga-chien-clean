# Forecast Brain Readiness (Design Assessment Only)

**No model training. No Brain implementation.**

---

## Stage assessments

| Stage | Goal | Classification | Evidence |
|-------|------|----------------|----------|
| **1** Descriptive conditional research: given Market state X at T0, what usually happened at T3/T5/T10? | `LIMITED` | ~42 weekday Market-Core sessions with FC+REAL; only **14** market-level T3 outcomes, **12** T5, **7** T10. Breadth/LIVE only ~8 sessions. Enough for **exploratory** contingency tables on FC bins; **not** enough for stable conditionals across regimes. |
| **2** Simple falsifiable Forecast candidates | `NOT_READY` → borderline `LIMITED` only for ultra-coarse FC→T3 hypotheses | Need more COMPLETE 142 T0 + matured horizons. Currently 17 full-142 days. Candidates would be underpowered and regime-confounded. |
| **3** Out-of-sample / episode-separated validation | `NOT_READY` | Only ~7 regime-label transitions and ~15 FC direction flips on a ~2-month span. Independent episodes are few; holdout would leave almost no train mass. |
| **4** Autonomous Forecast Research Brain (Edge-analog) | `NOT_READY` | Requires durable observation grammar, matured labels, multi-episode search accounting — all gated on Stages 1–3 depth. |

---

## Do not confuse rows with episodes

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Root PH rows | 33,343 | Intraday scans × symbols — **not** independent market days |
| Weekday FC sessions | 42 | Independent **calendar sessions** for Market Core |
| Full-142 T0 | 17 | Forecast-schema episodes |
| Regime label changes | 7 | Weak episode segmentation |
| Matured market T3 | 14 | Labelled Forecast episodes |

---

## Heuristic milestones (not statistical claims)

These are **collection planning heuristics**, not proof of sufficiency:

| Milestone | Heuristic session count | Approx calendar if collecting continuously |
|-----------|-------------------------|--------------------------------------------|
| Stage 1 becomes meaningfully stronger | ~60–90 weekday sessions with FC+REAL+**breadth** + ≥40 matured T3 | ~3–4.5 months from now |
| Stage 2 candidates worth falsifying | ~40–60 COMPLETE 142 T0 with matured T5 | ~2–3 additional months of EMS+MDT0+P0 |
| Stage 3 OOS plausible | Multiple distinct regime episodes (≫7 transitions) + holdout block | Often **6+ months** continuous; evidence-driven, not calendar-driven |

---

## Research dataset architecture (design only)

```
[RAW OBSERVATIONS — retain forever]
  EMS boards | MDT0 | root PH scans | P0 providers | Camera bars

        ↓ (PIT freeze; never write labels into this layer)

[Market T0 state]  forecast_t0_daily / mdrr / p0_market_daily
  features only; first-write-wins; schema_versioned

        ↓ (maturity on trading-session calendar)

[T3/T5/T10 outcomes]  forecast_outcomes.csv
  separate files; append-only; never join back into T0 writers

        ↓

[Episodes / regimes]  research-only indexes
  regime transitions, FC regimes, breadth regimes

        ↓

[Propositions → falsification → OOS]
  Forecast Research (not production Forecast output)

        ↓ (graduation gate — future)

[Production Forecast output]  strict authority boundary
```

**Hard rules:** observations ≠ labels ≠ research results ≠ production Forecast. No human rule hard-coded as truth. No future columns in T0 features.

---

## Daily memory adequacy (accepted unattended path)

If left running 3–6 months with MDT0 present:

| Class | Auto-accumulate? | Notes |
|-------|------------------|-------|
| Forecast T0 (142) | **YES** | MDT0-gated freeze |
| MDRR | **YES** | Hooked in daily stage |
| P0 foreign / turnover / VNI tech | **YES** | P0 hook |
| Outcome maturity T3/T5/T10 | **YES** | Maturity in stage |
| Hist core | **YES** | Hooked |
| Root PH MARKET CORE | **PARTIAL** | Depends on Streamlit/scan writers, not Forecast timer |
| LIVE/breadth outside MDT0 | **PARTIAL** | Only when MDT0 capture runs |
| Camera late-session trajectory | **NO** in Forecast stage | Separate collector; verify VPS |
| Sector on EMS | **NO** | Still absent from EMS schema |
| Intraday FC trajectory archive | **NO** | Multi-scan PH exists but not first-write Forecast layer |

---

## Collection priorities (summary)

**P0 (must never lose):** EMS 142 board, MDT0 (FC/REAL/LIVE/breadth/VNI OHLCV), Forecast T0/outcomes/MDRR/P0, root PH (until replaced by better append-only archive).

**P1:** Sector on board, MDT0 technical fills, Camera late-session aggregates, FC intraday trajectory snapshots.

**P2:** Speculative microstructure / alternative foreign sources — only after Stage 1–2 evidence.
