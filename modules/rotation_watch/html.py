"""Deterministic HTML snapshot of Rotation Watch. No Streamlit required."""

from __future__ import annotations

from html import escape
from typing import Any

from modules.rotation_watch.engine import RotationBoard

CSS = """
:root { color-scheme: light; }
body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 16px; background: #f4f6f8; color: #1a1d23; }
.panel { max-width: 1400px; background: #fff; border: 1px solid #d5dbe3; border-radius: 10px; padding: 14px 16px; }
h1 { font-size: 20px; margin: 0 0 4px; }
.sub { color: #5b6370; font-size: 12px; margin-bottom: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { border: 1px solid #e2e6ee; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #f3f5f8; }
.BUY_READY, .act-BUY { background: #d1fae5; color: #065f46; font-weight: 700; }
.SELL_READY, .act-SELL { background: #fee2e2; color: #991b1b; font-weight: 700; }
.TREND_HOLD, .act-TREND { background: #dbeafe; color: #1e3a8a; font-weight: 700; }
.RISK, .act-RISK { background: #ffedd5; color: #9a3412; font-weight: 700; }
.DATA_UNCERTAIN, .act-WAIT-U { background: #fef3c7; color: #92400e; font-weight: 700; }
.HOLD { background: #ecfdf3; }
.LOWER_ZONE, .UPPER_ZONE, .WATCH { background: #f8fafc; }
.empty { padding: 16px; font-weight: 700; }
.evidence { font-size: 12px; color: #374151; }
"""

HIGHLIGHT = {
    "BUY_READY": "BUY_READY",
    "SELL_READY": "SELL_READY",
    "TREND_HOLD": "TREND_HOLD",
    "RISK": "RISK",
    "DATA_UNCERTAIN": "DATA_UNCERTAIN",
}


def render_html(board: RotationBoard | dict[str, Any]) -> str:
    data = board.as_dict() if isinstance(board, RotationBoard) else board
    if data.get("empty"):
        body = f'<div class="empty">{escape(str(data.get("empty_message") or ""))}</div>'
    else:
        rows = []
        for row in data.get("rows") or []:
            state = str(row.get("rotation_state") or "")
            cls = HIGHLIGHT.get(state, state)
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
                f"<td class=\"{cls}\">{escape(state)}</td>"
                f"<td>{escape(str(row.get('suggested_action') or ''))}</td>"
                f"<td>{escape(str(row.get('raw_pxv') or ''))}</td>"
                f"<td>{escape(str(row.get('published_pxv') or ''))}</td>"
                f"<td class=\"evidence\">{escape(str(row.get('pxv_why') or ''))}</td>"
                f"<td>{escape(str(row.get('last_bar_ts') or ''))}</td>"
                f"<td>{escape(str(row.get('freshness') or ''))}</td>"
                f"<td>{escape('—' if entry is None else str(entry))}</td>"
                f"<td>{escape(pnl_s)}</td>"
                f"<td class=\"evidence\">{ev}</td>"
                "</tr>"
            )
        body = (
            "<table><thead><tr>"
            "<th>Symbol</th><th>Current Price</th><th>Lower Zone</th><th>Upper Zone</th>"
            "<th>Range Position %</th><th>Rotation State</th><th>Suggested Action</th>"
            "<th>Raw P×V</th><th>Published P×V</th><th>P×V evidence / why</th>"
            "<th>Last completed 5m bar</th><th>Data Freshness</th>"
            "<th>Entry Price</th><th>P/L %</th><th>Rotation evidence</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
    src = ""
    rows_data = data.get("rows") or []
    if rows_data:
        src = str(rows_data[0].get("data_source_label") or rows_data[0].get("data_source") or "")
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><title>ROTATION WATCH</title>
<style>{CSS}</style></head>
<body>
<section class="panel" data-alert-eligible="false" data-candidate-required="false">
  <h1>🔄 ROTATION WATCH</h1>
  <div class="sub">Danh sách xoay vòng thủ công · không tự mua/bán · độc lập Candidate · source={escape(src)}</div>
  {body}
</section>
</body></html>
"""
