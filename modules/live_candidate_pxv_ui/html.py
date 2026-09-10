"""Deterministic HTML snapshot of the read-only panel. No Streamlit required."""
from __future__ import annotations

from html import escape
from typing import Any

from modules.live_candidate_pxv_ui.view import PanelState

CSS = """
:root { color-scheme: light; }
body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 16px; background: #f6f7f9; color: #1a1d23; }
.panel { max-width: 920px; background: #fff; border: 1px solid #d8dde6; border-radius: 10px; padding: 14px 16px; }
h1 { font-size: 18px; margin: 0 0 4px; }
.sub { color: #5b6370; font-size: 12px; margin-bottom: 10px; }
.banner { background: #fff3cd; border: 1px solid #e6c200; color: #5c4d00; padding: 8px 10px; border-radius: 6px; margin: 8px 0; font-size: 13px; }
.banner.live { background: #e8f6ee; border-color: #2f9e62; color: #14532d; }
.empty { padding: 18px 8px; font-size: 16px; font-weight: 600; }
.card { border: 1px solid #e2e6ee; border-radius: 8px; padding: 10px 12px; margin: 8px 0; }
.card.stale { opacity: 0.72; border-style: dashed; }
.card.invalid { background: #fafafa; }
.row1 { display: flex; gap: 10px; flex-wrap: wrap; align-items: baseline; }
.sym { font-size: 18px; font-weight: 700; }
.reason { color: #444; }
.badge { font-size: 11px; font-weight: 700; padding: 2px 6px; border-radius: 4px; }
.STRENGTHEN { background: #d1fae5; color: #065f46; }
.WEAKEN { background: #fee2e2; color: #991b1b; }
.NEUTRAL { background: #e5e7eb; color: #374151; }
.UNUSABLE { background: #fef3c7; color: #92400e; }
.WAIT { background: #e0e7ff; color: #3730a3; }
.meta { font-size: 12px; color: #4b5563; margin-top: 4px; }
.why { margin-top: 6px; font-size: 13px; }
.hist { margin-top: 8px; font-size: 12px; color: #374151; }
.hist li { margin: 2px 0; }
"""


def render_html(state: PanelState | dict[str, Any]) -> str:
    data = state.as_dict() if isinstance(state, PanelState) else state
    runner = data.get("runner") or {}
    banner = runner.get("banner") or ""
    banner_cls = "banner" if runner.get("is_stale") else "banner live"
    cards_html = []
    if data.get("empty"):
        cards_html.append(f'<div class="empty">{escape(data.get("empty_message") or "")}</div>')
    for card in data.get("cards") or []:
        cards_html.append(_card_html(card, stale=bool(runner.get("is_stale"))))
    live_label = escape(str(runner.get("label") or ""))
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><title>LIVE CANDIDATE × P×V</title>
<style>{CSS}</style></head>
<body>
<section class="panel" data-alert-eligible="false" data-provider-called="false">
  <h1>LIVE CANDIDATE × P×V</h1>
  <div class="sub">Quan sát only · không phải lệnh mua/bán · alert_eligible=false · runner={live_label}</div>
  <div class="{banner_cls}">{escape(banner or runner.get("detail") or "")}</div>
  {"".join(cards_html)}
</section>
</body></html>
"""


def _card_html(card: dict[str, Any], *, stale: bool) -> str:
    valid = bool(card.get("evidence_valid"))
    waiting = bool(card.get("waiting_first_bar"))
    cls = "card"
    if stale:
        cls += " stale"
    if not valid:
        cls += " invalid"
    pub = card.get("published_evidence") or ("WAIT" if waiting else "—")
    raw = card.get("raw_evidence") or ("WAIT" if waiting else "—")
    pub_cls = pub if pub in {"STRENGTHEN", "WEAKEN", "NEUTRAL", "UNUSABLE"} else "WAIT"
    raw_cls = raw if raw in {"STRENGTHEN", "WEAKEN", "NEUTRAL", "UNUSABLE"} else "WAIT"
    hist = card.get("history") or []
    hist_items = "".join(
        f"<li>{escape(str(h.get('asof_hm') or ''))} {escape(str(h.get('kind') or ''))}</li>"
        for h in hist
    )
    legal = card.get("chronology_legal")
    legal_s = "true" if legal is True else ("false" if legal is False else "n/a")
    return f"""
  <article class="{cls}" data-symbol="{escape(card.get('symbol') or '')}" data-valid="{str(valid).lower()}" data-waiting="{str(waiting).lower()}">
    <div class="row1">
      <span class="sym">{escape(card.get("symbol") or "")}</span>
      <span class="reason">{escape(card.get("candidate_reason") or "")}</span>
      <span class="badge {pub_cls}">PUBLISHED {escape(str(pub))}</span>
      <span class="badge {raw_cls}">RAW {escape(str(raw))}</span>
      <span class="badge">{escape(str(card.get("data_state") or ""))}</span>
    </div>
    <div class="meta">
      Candidate {escape(card.get("candidate_first_seen_hm") or card.get("candidate_first_seen_ts") or "")}
      · eligible_from {escape(card.get("eligible_from_hm") or "")}
      · bar {escape(card.get("latest_asof_hm") or "—")}
      · observed {escape(card.get("observed_at") or "—")}
      · chronology_legal={legal_s}
      · freshness={escape(str(card.get("freshness") or ""))}
      · alert_eligible=false
    </div>
    <div class="why">{escape(card.get("explanation") or "")}</div>
    <details class="hist"><summary>Lịch sử P×V (chuyển trạng thái)</summary><ul>{hist_items}</ul></details>
  </article>
"""
