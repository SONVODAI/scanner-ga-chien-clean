# Data Quality Gates — Foreign Flow Confirmation V1

Fail **closed**. Invalid events must not enter the confirmation sample.

## Event-level gates (T0 append)

| Gate | Fail if | Action |
|------|---------|--------|
| Freeze boundary | `trade_date <= 2026-08-24` | reject |
| Foreign flow missing | `foreign_net_value` is NULL | reject |
| Lookback incomplete | <60 finite nets (`abn_abs_z20`) or <252 (`net_hi_pct90`); streak path undefined | reject (NULL≠0) |
| Feature intermediate non-finite | `net_z_60` / `net_pct_252` / streak NaN/inf | reject |
| Price missing | `close_price` NULL or ≤ 0 | reject |
| Wrong trade date | non-session / malformed / future-dated beyond known calendar | reject |
| Duplicate event key | same `candidate_id|trade_date|symbol` already logged | reject (no overwrite) |
| Corporate-action anomaly | prior→T0 close ratio >1.8 or <0.55 | reject |
| Source provenance missing | empty `source` / `source_provenance` | reject |
| T0 timing unclear | cannot assert close-as-of semantics for row | reject |
| Dataset version missing | empty `dataset_hash_or_version` | reject |

## Outcome-level gates (maturity append)

| Gate | Fail if | Action |
|------|---------|--------|
| Event missing | no matching T0 event | do not invent outcome |
| T10 price missing / ≤0 | cannot form return | `outcome_ok=false`, `ret_t10=null` |
| Session count ≠ 10 | maturity date not exactly 10 sessions later | reject / hold |
| Rewrite attempt | mutate T0 event | forbidden |

## Missingness rule

**NULL must never become zero.** Incomplete lookbacks are non-eligible, not “feature=0”.

## Cohort / coverage

- Track symbols with forward rows vs freeze cohort (117 HOSE).
- Log DQ failure counts by reason daily.
- If DQ failure rate on attempted triggers exceeds a soft ops threshold (e.g. >20% of candidate evaluations in a week), set operator `data_quality_status=DEGRADED` but do **not** loosen gates.

## Audit

Every rejected evaluation should be optionally logged to a separate `dq_rejects.jsonl` (not the confirmation sample).
