# P0 Foreign Flow — Production VPS Verification & Closure

## FINAL VERDICT

`P0_PRODUCTION_VERIFICATION_BLOCKED`

This Cloud Agent host is **not** the production VPS. `/opt/mrbot-camera` is absent. No SSH/self-hosted worker credentials are available to this run. Cursor/dev SSI reachability must **not** be inferred as VPS behavior.

---

### Production result

| Field | Value |
| --- | --- |
| VPS tested | **NO** |
| provider reachable | **NO** (on this agent only) |
| exact result/error | HTTP **403** Cloudflare “Security Check - SSI”; `fr_trade_heatmap` → `null_dataframe` / stdout `Error: 403` |
| tested trade date | `2026-08-22` (requested; live endpoint ignores date) |
| market scope | **HOSE** (SSI `/stock/exchange/HOSE` — HOSE-listed names, not whole VN market) |
| units | **UNPROVEN** (`PROVIDER_NATIVE_UNPROVEN`) |

Evidence JSON: `diagnostics/p0_foreign_flow_vps_verification/cursor_agent_probe.json`

Runtime on this agent:
- hostname: `cursor`
- python: `/usr/bin/python3`
- vnstock: **0.2.9.2** with `fr_trade_heatmap=True`

Documented production paths (not accessible here):
- `/opt/mrbot-camera` — git checkout
- `/opt/mrbot-camera-venv` — collector venv (`vnstock>=4.0.5` — **no** `fr_trade_heatmap`)
- App / Streamlit path expected to use `requirements.txt` → `vnstock==0.2.9.2` (has heatmap API)

---

### Canonical result

No new production canonical foreign values were written (VPS not reachable).

Existing Cursor-era P0 row pattern (missing ≠ 0) remains:

```text
foreign_scope / foreign_flow_scope = HOSE
foreign_buy_value / foreign_sell_value / foreign_net_value = NULL
provenance.foreign.status = SOURCE_ERROR
provenance.foreign.error = null_dataframe (HTTP 403 upstream)
completeness_status = PARTIAL (universe turnover + VNI tech may still be OK)
```

Provider provenance now also records:
- `foreign_flow_scope=HOSE`
- `units=PROVIDER_NATIVE_UNPROVEN`
- `historical_supported=false` / `forward_only=true`

---

### Automation result

**Intended:** yes — after MDT0, `market_t0_capture` → `maybe_freeze_after_market_daily` → `maybe_collect_p0_after_market_daily` attempts foreign collection fail-safely (NULL + SOURCE_ERROR on failure; does not crash Market First / MDT0 / MDRR / Forecast T0).

**Also:** CLI `python -m modules.forecast_research.daily_entrypoint --p0-collect`

**Caveat:** tomorrow’s automatic attempt only occurs if the **production app Python** that runs `market_t0_capture` (or an equivalent ≥18:00 host job) has been deployed with this P0 stack **and** that interpreter can import `vnstock.fr_trade_heatmap`. Collector vnstock 4.x alone is insufficient for the current SSI adapter.

**Streamlit need not stay open** if an equivalent host process runs the same hook.

---

### Historical capability

`UNRESOLVED` for production (VPS not tested).

Independently of VPS: SSI `fr_trade_heatmap` / exchange endpoint **accepts no trade_date** → live session snapshot only. Even if VPS succeeds:

→ treat as **`FORWARD_ONLY`** until historical date-true semantics are separately proven.

Do **not** mass-backfill foreign flow.

---

### Alternative source (SSI blocked here; VPS unknown)

| Source | Foreign buy | Foreign sell | Net | Historical | Scope | PIT suitable | Reliability |
| ------ | ----------- | ------------ | --- | ---------- | ----- | ------------ | ----------- |
| SSI `fr_trade_heatmap` (current P0) | YES (when reachable) | YES | buy−sell | NO (no date) | HOSE | FORWARD_ONLY | 403 in Cursor; VPS unknown |
| EMS snapshots | NO | NO | NO | N/A | EMS 142 | N/A | Trusted for turnover only |
| `market_daily_t0` | NO | NO | NO | N/A | Market First T0 | N/A | No foreign fields |
| vnstock4 VCI price_board | NO (room/holding) | NO | NO | unclear | per-symbol | NO | Wrong semantics |
| vnstock4 KBS board / foreignTotal | VOLUME only | VOLUME only | VOLUME only | unproven | broker board | UNCERTAIN | Not wired; value missing |
| Official HOSE prints | possible | possible | possible | often yes | exchange | if dated close | No project adapter |

**No alternative adapter implemented** — none is clearly reliable with only a small isolated change. STOP per task rules.

No Cloudflare / CAPTCHA / stealth bypass attempted.

---

### Remaining P0 gaps

| Gap type | Detail |
| --- | --- |
| **Provider/access gap (blocking closure)** | Production VPS SSI reachability **not verified** from this agent |
| **Technical gap (minor)** | Units not proven; `fr_trade_heatmap` absent on vnstock 4.x collector venv |
| **Waiting for sessions** | After VPS proves reachability, foreign history starts at first reliable observed session (`forward_only`) |

Non-foreign P0 pieces (universe turnover, PIT ADV, VNINDEX tech) remain implemented from PR #88.

---

## Operator: close this gap on the real VPS

```bash
cd /opt/mrbot-camera
# deploy this branch / PR tip first
bash scripts/verify_p0_foreign_flow_on_vps.sh
# or:
python3 -m modules.forecast_research.daily_entrypoint --verify-p0-foreign-vps --trade-date YYYY-MM-DD
```

Interpret `diagnostics/p0_foreign_flow_vps_verification/vps_probe.json`:

| Probe outcome | Next verdict |
| --- | --- |
| `is_production_vps=true` + provider OK | `P0_FOREIGN_FLOW_FORWARD_ONLY_READY` (then optional collect + idempotency check) |
| `is_production_vps=true` + 403/blocked | `P0_FOREIGN_PROVIDER_BLOCKED` |
| Still not on `/opt/mrbot-camera` | `P0_PRODUCTION_VERIFICATION_BLOCKED` |

If reachable:
1. `--p0-collect --trade-date <session>`
2. Re-run → `ALREADY_PRESENT`
3. Confirm foreign NULL≠0 on failure path still holds
4. Confirm MDT0 / MDRR / Forecast T0 hashes unchanged

---

## Tests

```bash
python -m pytest tests/test_p0_foreign_flow_vps_verification.py tests/test_p0_forward_market_memory.py -q
```
