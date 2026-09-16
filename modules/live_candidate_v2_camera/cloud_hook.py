"""Slice 3A: gated Cloud local V2 sidecar writer.

Default OFF. No GitHub publish. No VPS. No runner.
A sidecar failure must not break Elite / production Candidate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from modules.live_candidate.calendar import as_vn
from modules.live_candidate_v2_camera.contract import (
    ENV_V2_CLOUD_SIDECAR,
    ENV_V2_CLOUD_SIDECAR_FALSY,
    ENV_V2_CLOUD_SIDECAR_TRUTHY,
)
from modules.live_candidate_v2_camera.sidecar import (
    DEFAULT_SIDECAR_PATH,
    SidecarShadowError,
    build_sidecar_from_scan,
    freeze_records_from_document,
    load_sidecar_document,
    write_sidecar,
)
from modules.live_candidate_v2_nomination.contract import ELITE_BUY_GRADES

REASON_GATE_OFF = "GATE_OFF"
REASON_WROTE = "WROTE"
REASON_LOAD_FAILED = "LOAD_FAILED"
REASON_WRITE_FAILED = "WRITE_FAILED"


def v2_cloud_sidecar_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Default OFF. Only explicit truthy values enable the local writer."""
    raw = str((env or os.environ).get(ENV_V2_CLOUD_SIDECAR, "") or "").strip().lower()
    if raw in ENV_V2_CLOUD_SIDECAR_TRUTHY:
        return True
    if raw in ENV_V2_CLOUD_SIDECAR_FALSY:
        return False
    return False


def early_lab_symbols_from_frame(early_buy_lab_df: Any) -> tuple[str, ...]:
    if early_buy_lab_df is None:
        return ()
    try:
        if getattr(early_buy_lab_df, "empty", True):
            return ()
        col = "MÃ" if "MÃ" in early_buy_lab_df.columns else "symbol"
        if col not in early_buy_lab_df.columns:
            return ()
        return tuple(
            str(s).strip().upper()
            for s in early_buy_lab_df[col].tolist()
            if str(s).strip()
        )
    except Exception:
        return ()


def attach_elite_buy_grade_metadata(
    rows: Sequence[Mapping[str, Any]],
    buy_elite_df: Any,
) -> list[dict[str, Any]]:
    """Join Elite KẾT LUẬN as elite_buy_grade metadata only. Does not copy LOẠI/WATCHLIST."""
    grades: dict[tuple[str, str], str] = {}
    by_symbol: dict[str, str] = {}
    if buy_elite_df is not None and not getattr(buy_elite_df, "empty", True):
        try:
            sym_col = "MÃ" if "MÃ" in buy_elite_df.columns else "symbol"
            conc_col = "KẾT LUẬN" if "KẾT LUẬN" in buy_elite_df.columns else "conclusion"
            date_col = next(
                (c for c in ("session", "date", "session_date") if c in buy_elite_df.columns),
                None,
            )
            for rec in buy_elite_df.to_dict("records"):
                sym = str(rec.get(sym_col) or "").strip().upper()
                grade = str(rec.get(conc_col) or "").strip()
                if not sym or grade not in ELITE_BUY_GRADES:
                    continue
                by_symbol[sym] = grade
                if date_col:
                    session = str(rec.get(date_col) or "")[:10]
                    if session:
                        grades[(session, sym)] = grade
        except Exception:
            pass

    out: list[dict[str, Any]] = []
    for raw in rows or ():
        row = dict(raw)
        sym = str(row.get("symbol") or row.get("MÃ") or "").strip().upper()
        session = str(row.get("session") or row.get("date") or row.get("session_date") or "")[:10]
        grade = grades.get((session, sym)) or by_symbol.get(sym) or ""
        if grade:
            row["elite_buy_grade"] = grade
        out.append(row)
    return out


@dataclass(frozen=True)
class CloudSidecarResult:
    ok: bool
    skipped: bool = False
    reason: str = ""
    path: str = ""
    n_rows: int = 0
    n_freeze: int = 0
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "skipped": self.skipped,
            "reason": self.reason,
            "path": self.path,
            "n_rows": self.n_rows,
            "n_freeze": self.n_freeze,
            "error": self.error,
        }


def run_v2_cloud_sidecar(
    *,
    scan_rows: Sequence[Mapping[str, Any]] | None,
    market_real: object,
    observed_at: datetime,
    buy_elite_df: Any = None,
    early_buy_lab_df: Any = None,
    path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> CloudSidecarResult:
    """Load prior freeze → nominate → atomic local write. No GitHub."""
    if not v2_cloud_sidecar_enabled(env):
        return CloudSidecarResult(ok=True, skipped=True, reason=REASON_GATE_OFF)

    dest = Path(path) if path is not None else DEFAULT_SIDECAR_PATH
    try:
        prior_doc = load_sidecar_document(dest)
    except SidecarShadowError as exc:
        return CloudSidecarResult(
            ok=False,
            skipped=False,
            reason=REASON_LOAD_FAILED,
            path=str(dest),
            error=str(exc),
        )

    prior_freeze = freeze_records_from_document(prior_doc) if prior_doc is not None else ()
    rows = attach_elite_buy_grade_metadata(list(scan_rows or ()), buy_elite_df)
    early_lab = early_lab_symbols_from_frame(early_buy_lab_df)
    now = as_vn(observed_at)
    try:
        report, sidecar_rows = build_sidecar_from_scan(
            rows,
            market_real=market_real,
            observed_at=now,
            prior_freeze=prior_freeze,
            early_lab_symbols=early_lab,
        )
        write_sidecar(
            sidecar_rows,
            observed_at=now,
            path=dest,
            market_real=report.market_real,
            market_permission=report.market_permission,
            freeze_ledger=report.freeze_ledger,
            generated_at=now,
            session=now.date().isoformat(),
        )
    except SidecarShadowError as exc:
        return CloudSidecarResult(
            ok=False,
            skipped=False,
            reason=REASON_WRITE_FAILED,
            path=str(dest),
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 — isolate shadow from production scan
        return CloudSidecarResult(
            ok=False,
            skipped=False,
            reason=REASON_WRITE_FAILED,
            path=str(dest),
            error=f"{type(exc).__name__}: {exc}",
        )
    return CloudSidecarResult(
        ok=True,
        skipped=False,
        reason=REASON_WROTE,
        path=str(dest),
        n_rows=len(sidecar_rows),
        n_freeze=len(report.freeze_ledger),
    )
