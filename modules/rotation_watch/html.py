"""Deterministic HTML snapshot. Dict-only — no engine / KBS import."""

from __future__ import annotations

from html import escape
from typing import Any

CSS = """
:root { color-scheme: light; }
body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 16px; background: #f4f6f8; color: #1a1d23; }
.panel { max-width: 1400px; background: #fff; border: 1px solid #d5dbe3; border-radius: 10px; padding: 14px 16px; }
h1 { font-size: 20px; margin: 0 0 4px; }
.sub { color: #5b6370; font-size: 12px; margin-bottom: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { border: 1px solid #e2e6ee; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #f3f5f8; }
.BUY_READY { background: #d1fae5; color: #065f46; font-weight: 700; }
.SELL_READY { background: #fee2e2; color: #991b1b; font-weight: 700; }
.TREND_HOLD { background: #dbeafe; color: #1e3a8a; font-weight: 700; }
.RISK { background: #ffedd5; color: #9a3412; font-weight: 700; }
.DATA_UNCERTAIN, .WAIT { background: #fef3c7; color: #92400e; font-weight: 700; }
.empty { padding: 16px; font-weight: 700; }
.evidence { font-size: 12px; color: #374151; }
"""

HIGHLIGHT = {
    "BUY_READY": "BUY_READY",
    "SELL_READY": "SELL_READY",
    "TREND_HOLD": "TREND_HOLD",
    "RISK": "RISK",
    "DATA_UNCERTAIN": "DATA_UNCERTAIN",
    "WAIT": "WAIT",
}


def render_html(panel: dict[str, Any]) -> str:
    data = panel
    if data.get("empty"):
        body = f'<div class="empty">{escape(str(data.get("empty_message") or ""))}</div>'
    else:
        rows = []
        for row in data.get("rows") or []:
            last = str(row.get("last_session_state") or row.get("rotation_state") or "")
            action = str(row.get("suggested_action") or "")
            ev = escape(" · ".join(row.get("rotation_evidence") or []))
            rng = row.get("range_position_pct")
            rng_s = "" if rng is None else f"{float(rng):.1f}"
            pnl = row.get("pnl_pct")
            pnl_s = "" if pnl is None else f"{float(pnl):.2f}"
            price = row.get("current_price")
            entry = row.get("entry_price")
            rows.append(
                "<tr>"
                f"<td><strong>{escape(str(row.get('symbol') or ''))}</strong></td>"
                f"<td>{escape('—' if price is None else str(price))}</td>"
                f"<td>{escape(str(row.get('lower_zone') or ''))}</td>"
                f"<td>{escape(str(row.get('upper_zone') or ''))}</td>"
                f"<td>{escape(rng_s)}</td>"
                f"<td class=\"{HIGHLIGHT.get(last, '')}\">{escape(last)}</td>"
                f"<td class=\"{HIGHLIGHT.get(action, '')}\">{escape(action)}</td>"
                f"<td>{escape(str(row.get('session_phase') or ''))}</td>"
                f"<td>{escape(str(row.get('raw_pxv') or ''))}</td>"
                f"<td>{escape(str(row.get('published_pxv') or ''))}</td>"
                f"<td class=\"evidence\">{escape(str(row.get('pxv_why') or row.get('evidence_why') or ''))}</td>"
                f"<td>{escape(str(row.get('last_bar_ts') or ''))}</td>"
                f"<td>{escape(str(row.get('freshness') or ''))}</td>"
                f"<td>{escape('—' if entry is None else str(entry))}</td>"
                f"<td>{escape(pnl_s)}</td>"
                f"<td class=\"evidence\">{ev}</td>"
                f"<td class=\"evidence\">{escape(str(row.get('action_gate_reason') or ''))}</td>"
                "</tr>"
            )
        body = (
            "<table><thead><tr>"
            "<th>Symbol</th><th>Current Price</th><th>Lower Zone</th><th>Upper Zone</th>"
            "<th>Range Position %</th><th>Last-session State</th><th>Suggested Action</th>"
            "<th>Session</th><th>Raw P×V</th><th>Published P×V</th><th>P×V evidence / why</th>"
            "<th>Last completed 5m bar</th><th>Data Freshness</th>"
            "<th>Entry Price</th><th>P/L %</th><th>Rotation evidence</th><th>Action gate</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><title>ROTATION WATCH</title>
<style>{CSS}</style></head>
<body>
<section class="panel" data-alert-eligible="false" data-candidate-required="false" data-kbs-called="false">
  <h1>🔄 ROTATION WATCH</h1>
  <div class="sub">Artifact read-only · không tự mua/bán · không KBS từ Streamlit · session={escape(str(data.get('session_phase') or ''))}</div>
  {body}
</section>
</body></html>
"""
