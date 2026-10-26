# Foreign-flow alternative source audit

**Date:** 2026-08-24  
**Premise:** Production VPS (`mrbot-camera`) confirmed `P0_FOREIGN_PROVIDER_BLOCKED` for SSI (`vnstock 4.0.5`, `has_fr_trade_heatmap=false`, HTTP 403 Cloudflare). SSI is retired as preferred path.  
**Scope of this task:** SOURCE AUDIT ONLY — no adapter, no deploy, no package changes, no production edits.

---

## Recommendation (exact)

`FOREIGN_FLOW_UNIVERSE_PROXY_FOUND`

No clean, automated **HOSE-wide exchange aggregate** VALUE feed was proven.  
A **reliable, legitimate, dateable per-stock foreign buy/sell VALUE** source **was** proven (official HSX API), and the existing **142 EMS universe** can be aggregated deterministically into:

- `universe_foreign_buy_value`
- `universe_foreign_sell_value`
- `universe_foreign_net_value`

**Never label this as HOSE-wide / whole-market foreign flow.**

---

## Candidate comparison

| Source | Buy value | Sell value | Net value | Historical dates | Market scope | Units documented | Automated daily access | PIT suitability | Stability |
| ------ | --------- | ---------- | --------- | ---------------- | ------------ | ---------------- | ---------------------- | --------------- | --------- |
| **Official HSX API** `GET https://api.hsx.vn/mk/api/v1/market/securities/foreign/{SYM}?pageSize=N` | **YES** `mainBuyerForeignValue` (+ optional `bigLotBuyerForeignValue`) | **YES** `mainSellerForeignValue` (+ bigLot) | **DERIVED** buy−sell | **YES** — `reportDate` list (pageable; VNM returned distinct session dates e.g. 2026-08-24, 08-21, 08-20, …) | **Per HOSE-listed symbol** (empty for `HOSE`/`VNINDEX`/`VN30` aggregate symbols) | **VND** (matches VCI; VNM buy `53104069800`) | **YES** — public JSON, no key observed in probe | **HISTORICAL_AND_FORWARD** for per-symbol; universe aggregate if requested asof date | **High** (official `api.hsx.vn`; SPA “Giao dịch NĐTNN”) |
| **vnstock 4.0.5 VCI** `Trading.price_board` | **YES** `match_foreign_buy_value` | **YES** `match_foreign_sell_value` | **DERIVED** | **NO** — live board + `listing_trading_date` current session only | Per symbol; filter `listing_exchange==HSX` or EMS 142 | **VND** (identical to HSX same-day for VNM/FPT/VCB) | **YES** — already in production collector package | **FORWARD_ONLY** | **High** for after-close snapshot; depends on VCI upstream |
| **VPS** `bgapidatafeed.vps.com.vn/getliststockdata/{SYM}` | **YES** `fBValue` | **YES** `fSValue` | **DERIVED** | **NO** — live snapshot | Per symbol | **Likely VND÷1000** vs HSX/VCI (VNM `5.31040698E7` ×1000 = HSX) — **units trap** | Public; intermittent timeouts from this agent | **FORWARD_ONLY** | Medium (public but flaky; unit scale undocumented) |
| **vnstock 4.0.5 KBS** price board / `foreignTotal` ranking URL | VOLUME only (`FB`/`FS`) | VOLUME only | VOLUME only | Unproven | Broker board | N/A for VALUE | Partial | **NOT_RELIABLE** for VALUE contract | Low for this need |
| **SSI** `fr_trade_heatmap` | N/A on vnstock 4.x | N/A | N/A | N/A | HOSE | N/A | **Blocked** VPS HTTP 403 | **NOT_RELIABLE** | Blocked |
| **CafeF** foreign history UI/CSV | Claimed (tỷ VNĐ) | Claimed | Claimed | Claimed dated | HOSE/HNX/… UI | UI says **tỷ VNĐ** | HTML portal; probed JSON history endpoints **404 / unusable** | Unproven automation | Medium content / **weak** automation without fragile HTML |
| **oanor hose-api** `/v1/foreign` | YES (docs) | YES | DERIVED | Live short-cache | Per ticker | Unclear | Needs **API key** + third party; wraps VPS | FORWARD_ONLY | Not in project; dependency risk |
| **vnstock-data** `foreign_flow()` (docs) | Documented | Documented | Documented | Documented | Per equity | Docs imply value+volume | **Not installed** on production (`vnstock` only) | Would need new package — out of scope | N/A until separately approved |
| **EMS / MDT0** | NO | NO | NO | N/A | Research T0 | N/A | Existing | N/A | Trusted non-foreign fields only |

Probe evidence (this agent, 2026-08-24): HSX API 200 with dated lists; VCI board 200 with VALUE columns; VPS 200 with `fBValue`/`fSValue` (scale≠VCI); SSI previously 403 on VPS; CafeF history ashx 404.

**VPS accessibility of HSX/VCI:** not re-tested in this audit session (SSI already proven on VPS). HSX/VCI probes above are from Cursor. Operator should run the read-only one-liner in §VPS check before implementation.

---

### Recommended primary source

| Field | Value |
| --- | --- |
| **Source/provider** | Official HOSE API `api.hsx.vn` — `GET /mk/api/v1/market/securities/foreign/{symbol}` |
| **Exact semantics** | Per-symbol daily foreign **main** (+ optional **big-lot**) buy/sell **VALUE** and volume; `reportDate` = session date |
| **Canonical fields to store later** | `universe_foreign_buy_value` / `sell` / `net` = Σ over EMS 142 symbols for that `reportDate` (use `main* + bigLot*` for value) |
| **Scope** | `EMS_RESEARCH_UNIVERSE_142` (subset of HOSE/other listings in EMS — **not** all HOSE) |
| **Units** | **VND** (cross-checked vs VCI same day) |
| **Expected availability** | After session close; same-day row present in API during/after trading (probe on 2026-08-24 showed that date’s row) |
| **Historical capability** | **`HISTORICAL_AND_FORWARD`** at **symbol** level (date list proven). Universe history = Σ of per-symbol histories for EMS membership **asof that date** (membership drift must be versioned — do not silently use today’s 142 for past dates without a rule) |
| **VPS accessibility** | **Untested this session** — see §VPS check |
| **Implementation complexity** | **Medium**: 142 GETs (batched/throttled) or cache; map `reportDate`; fail-safe NULL on gaps; never call it `hose_foreign_*` |

### Recommended fallback

**vnstock 4.0.5 VCI `Trading.price_board`** (already on collector):  
`match_foreign_buy_value` / `match_foreign_sell_value` → same VND semantics for **current** `listing_trading_date` only → **`FORWARD_ONLY`**.  
Use when HSX API unavailable; same universe aggregation; identical field naming `universe_foreign_*`.

### 142-universe aggregation option

**YES — feasible with current infrastructure.**

- EMS already defines the 142 symbols (`data/earning_money_snapshots.csv`).
- **VCI** (in production `vnstock 4.0.5`): batch probe of 20 EMS symbols returned non-null buy/sell VALUE for all 20; ~3s/batch → ~142 symbols ≈ 8 batches, low complexity.
- **HSX official**: same VALUE for VNM as VCI; dated history; aggregate by summing selected symbols for a target `reportDate`.
- Must publish scope as **`universe_foreign_*` / `EMS_RESEARCH_UNIVERSE_142`**, never HOSE-wide.
- Missing symbol that day → exclude from sum and record coverage count (missing ≠ 0 for the aggregate if coverage below threshold — policy TBD at implement time).

### HOSE exchange-level (semantic A)

**Not recommended yet.**  
Official site exposes NĐTNN UI, but aggregate symbols (`HOSE`/`VNINDEX`/…) returned **empty lists**. Building HOSE-wide totals would require summing **all** HOSE listings (larger than 142, listing maintenance, higher load). CafeF UI claims exchange totals but no stable public JSON was confirmed.

---

## Classification summary

| Candidate | Class |
| --- | --- |
| HSX official per-symbol (+ 142 Σ) | `HISTORICAL_AND_FORWARD` (symbol); universe backfill only with membership rule |
| VCI price_board (+ 142 Σ) | `FORWARD_ONLY` |
| VPS bgapi | `FORWARD_ONLY` (units caution) |
| SSI / KBS-volume / CafeF-automation | `NOT_RELIABLE` for this contract |

---

## §VPS check (read-only, no deploy) — operator optional

```bash
# Official HSX (one symbol)
curl -fsS 'https://api.hsx.vn/mk/api/v1/market/securities/foreign/VNM?pageSize=3' \
  -H 'Accept: application/json' -H 'Origin: https://www.hsx.vn' | head -c 600; echo

# VCI via production collector python (no install)
/opt/mrbot-camera-venv/bin/python - <<'PY'
from vnstock.explorer.vci.trading import Trading
df = Trading(show_log=False).price_board(["VNM","FPT"], flatten_columns=True, show_log=False)
cols=[c for c in df.columns if "foreign" in c.lower()]
print(cols)
print(df[["listing_symbol","listing_trading_date"]+[c for c in cols if "value" in c.lower()]].to_string(index=False))
PY
```

If both succeed on VPS → proceed to adapter design review.  
If HSX blocked but VCI works → forward-only universe path.  
If both blocked → revisit (do not hammer SSI).

---

## Explicit non-actions (this task)

- No P0 collector / MDRR / Forecast / Market First / Camera changes  
- No production package install / vnstock downgrade  
- No Cloudflare bypass  
- No adapter implementation pending review  

---

## FINAL VERDICT

`FOREIGN_FLOW_UNIVERSE_PROXY_FOUND`
