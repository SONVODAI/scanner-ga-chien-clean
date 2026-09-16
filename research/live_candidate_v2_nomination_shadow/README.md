# LIVE CANDIDATE V2 — Slice 1 Brain A nomination (SHADOW ONLY)

Candidate means **Camera observation allocation**, not BUY.

This directory is the human-audit artifact for Slice 1. It is not the
production watchlist. Do not overwrite `data/live_candidate/dynamic_watchlist.json`.

## Nomination predicate

A scan row is nominated only if all of the following hold:

1. `symbol` is present.
2. `market_real >= 6` (existing Market REAL gate). Else reject `MARKET_WEAK`
   (`WATCHLIST - MARKET YẾU`). Do not spend Camera.
3. Not hard-bad: warning does not contain `OBV gãy` or `Giá dưới EMA9`, and
   conclusion is not `LOẠI - TRỤC XẤU`. Else reject `HARD_BAD`.
4. Setup/group is in the Slice 1 universe:
   - **PRIMARY** (always, no new score): `PULL ĐẸP` | `PULL VỪA` | `MUA BREAK` | `CP MẠNH`
   - **SECONDARY**: `MUA EARLY` only when existing `InEarlyLab` **or** existing
     `buy_recommendation` action **TEST EARLY**
     (`total_score >= 3` and `obv_status == 🟢` and `|dist_from_ema9_pct| <= 2.5`)

Never nominated in Slice 1:

- `THEO DÕI`, `TÍCH LŨY`
- bare `MUA EARLY` (no InEarlyLab, not TEST EARLY)
- `GÀ TĂNG TỐC` (reserved)
- `WATCHLIST` alone, WinProb/top-N alone
- `BUY ELITE` / `MUA NHỎ / ƯU TIÊN` alone (metadata only: `elite_buy_grade`)

## observation_intent source (existing text only)

Copied from `app.py::buy_recommendation` action + lý do:

| setup | observation_action | lý do |
| --- | --- | --- |
| PULL ĐẸP | MUA PULL ĐẸP | Pull sát EMA9, OBV còn xanh |
| PULL VỪA | MUA PULL VỪA | Pull vừa, mua thăm dò |
| MUA BREAK | MUA BREAK | Break xác nhận, không đuổi quá xa |
| CP MẠNH, dist > 4 | CHỜ PULL | CP mạnh nhưng xa EMA9 |
| CP MẠNH, else | CANH ADD CP MẠNH | CP mạnh, có thể add nhỏ |
| qualified MUA EARLY | TEST EARLY | Early sạch, test nhỏ |

Intent is a task description for Camera, not a buy rule. No P×V thresholds.

## Chronology

- `candidate_first_seen_ts` is stamped at the first **legal nomination** for
  `(session, symbol)`, not at BUY ELITE.
- Later rescans keep that timestamp and the frozen refs (`price_at_first_seen`,
  `ema9_at_first_seen`, `breakout_ref_at_first_seen`).
- `eligible_from` uses the existing Candidate `episode_window` (after cash close
  → next session 09:15 VN).
- Router objects are used only inside this shadow path, with
  `enabled_sources={brain_a_scan_setup}`. Production `ENABLED_SOURCES` stays
  Elite-only. Rotation adapter still returns `()`.

## Files

- Writer: `modules/live_candidate_v2_nomination/`
- Default artifact: `research/live_candidate_v2_nomination_shadow/nominations.json`
- Sample: `research/live_candidate_v2_nomination_shadow/nominations.sample.json`
