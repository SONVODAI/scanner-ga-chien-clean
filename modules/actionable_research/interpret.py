"""Vietnamese research interpretation. Speak selectively. Never emits BUY authority."""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from modules.actionable_research.contracts import (
    AUTHORITY_LABEL,
    CAMERA_DATA_FEED_MISSING,
    CAMERA_DATA_MISSING_SYMBOL,
    EDGE_STATUS_ACTIVE_MATCH,
    EDGE_STATUS_NO_ACTIVE_EDGE_AVAILABLE,
    EDGE_STATUS_NO_ACTIVE_MATCH,
    EDGE_STATUS_UNKNOWN,
    FOREIGN_STRONG_BUY,
    FOREIGN_STRONG_SELL,
    FOREIGN_UNKNOWN,
    INTEREST_HIGH,
    INTEREST_LOW,
    INTEREST_MEDIUM,
    INTEREST_NONE,
    INTRADAY_ACTIVITY_HIGH,
    INTRADAY_ACTIVITY_UNKNOWN,
    NO_INTEREST_VI,
    OBSERVATION_AGREEMENT,
    OBSERVATION_CONFLICT,
    OBSERVATION_STANDALONE,
    PRICE_DIRECTION_DOWN,
    PRICE_DIRECTION_UP,
    RANK_ACTIVE_ACTIVITY,
    RANK_ACTIVE_FF,
    RANK_ACTIVE_ONLY,
    RANK_ACTIVITY_FF,
    RANK_ACTIVITY_STANDALONE,
    RANK_AGREEMENT_TRIPLE,
    RANK_CONFLICT,
    RANK_FF_STANDALONE,
    RANK_LEARNED_SWEETSPOT,
    RANK_NOT_NOTABLE,
    SPEAK_POLICY,
    SWEETSPOT_AUTHORITY_EVIDENCE_DERIVED,
    SWEETSPOT_STATUS_LEARNED,
    TRADING_VALUE_UNUSUALLY_HIGH,
    VOLUME_ACCELERATION_HIGH,
)

def _learned_sweetspot(rec: Dict[str, Any]) -> bool:
    if rec.get("sweetspot_status") == SWEETSPOT_STATUS_LEARNED:
        return True
    return rec.get("authority_level") == SWEETSPOT_AUTHORITY_EVIDENCE_DERIVED


def _activity_abnormal(rec: Dict[str, Any]) -> bool:
    if rec.get("activity_status") == INTRADAY_ACTIVITY_HIGH:
        return True
    if rec.get("trading_value_status") == TRADING_VALUE_UNUSUALLY_HIGH:
        return True
    if rec.get("volume_acceleration_status") == VOLUME_ACCELERATION_HIGH:
        return True
    return False


def _ff_abnormal(rec: Dict[str, Any]) -> bool:
    return rec.get("foreign_flow_status") in {FOREIGN_STRONG_BUY, FOREIGN_STRONG_SELL}


def family_polarities(rec: Dict[str, Any]) -> Set[int]:
    """
    +1 constructive (ACTIVE / learned / foreign buy).
    -1 foreign selling-ish.

    Intraday activity is unsigned: high traded value is not a buy/sell vote.
    """
    votes: Set[int] = set()
    if rec.get("edge_status") == EDGE_STATUS_ACTIVE_MATCH:
        votes.add(1)
    if _learned_sweetspot(rec):
        votes.add(1)
    if rec.get("foreign_flow_status") == FOREIGN_STRONG_BUY:
        votes.add(1)
    elif rec.get("foreign_flow_status") == FOREIGN_STRONG_SELL:
        votes.add(-1)
    return votes


def noteworthy_family_count(rec: Dict[str, Any]) -> int:
    n = 0
    if rec.get("edge_status") == EDGE_STATUS_ACTIVE_MATCH:
        n += 1
    if _learned_sweetspot(rec):
        n += 1
    if _activity_abnormal(rec):
        n += 1
    if _ff_abnormal(rec):
        n += 1
    return n


def observation_relation(rec: Dict[str, Any]) -> str:
    votes = family_polarities(rec)
    families = noteworthy_family_count(rec)
    if 1 in votes and -1 in votes:
        return OBSERVATION_CONFLICT
    if families >= 2:
        return OBSERVATION_AGREEMENT
    return OBSERVATION_STANDALONE


def is_notable(rec: Dict[str, Any]) -> bool:
    """Speak only when something unusual was actually observed. Never fill a report."""
    return noteworthy_family_count(rec) >= 1


def rank_key(rec: Dict[str, Any]) -> Tuple[int, str]:
    if not is_notable(rec):
        return RANK_NOT_NOTABLE, rec.get("symbol") or ""
    active = rec.get("edge_status") == EDGE_STATUS_ACTIVE_MATCH
    act = _activity_abnormal(rec)
    ff = _ff_abnormal(rec)
    learned = _learned_sweetspot(rec)
    relation = observation_relation(rec)
    if relation == OBSERVATION_CONFLICT:
        return RANK_CONFLICT, rec.get("symbol") or ""
    if active and act and ff:
        return RANK_AGREEMENT_TRIPLE, rec.get("symbol") or ""
    if active and act:
        return RANK_ACTIVE_ACTIVITY, rec.get("symbol") or ""
    if active and ff:
        return RANK_ACTIVE_FF, rec.get("symbol") or ""
    if act and ff:
        return RANK_ACTIVITY_FF, rec.get("symbol") or ""
    if act:
        return RANK_ACTIVITY_STANDALONE, rec.get("symbol") or ""
    if ff:
        return RANK_FF_STANDALONE, rec.get("symbol") or ""
    if learned:
        return RANK_LEARNED_SWEETSPOT, rec.get("symbol") or ""
    if active:
        return RANK_ACTIVE_ONLY, rec.get("symbol") or ""
    return RANK_NOT_NOTABLE, rec.get("symbol") or ""


def interest_level(rec: Dict[str, Any]) -> str:
    if not is_notable(rec):
        return INTEREST_NONE
    rank, _ = rank_key(rec)
    if rank in {RANK_AGREEMENT_TRIPLE, RANK_CONFLICT, RANK_ACTIVITY_FF}:
        return INTEREST_HIGH
    if rank in {RANK_ACTIVE_ACTIVITY, RANK_ACTIVE_FF}:
        return INTEREST_MEDIUM
    if rank in {RANK_ACTIVITY_STANDALONE, RANK_FF_STANDALONE, RANK_LEARNED_SWEETSPOT}:
        return INTEREST_MEDIUM
    if rank == RANK_ACTIVE_ONLY:
        return INTEREST_LOW
    return INTEREST_NONE


def missing_evidence(rec: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    if rec.get("edge_status") == EDGE_STATUS_UNKNOWN:
        missing.append("EDGE_RECOGNITION_OR_MEMORY")
    if rec.get("activity_status") == INTRADAY_ACTIVITY_UNKNOWN:
        cam = rec.get("camera_data_status")
        if cam == CAMERA_DATA_FEED_MISSING:
            missing.append("CAMERA_FEED")
        elif cam == CAMERA_DATA_MISSING_SYMBOL:
            missing.append("CAMERA_SYMBOL_BARS")
        else:
            missing.append("CAMERA_ACTIVITY_ASSESSMENT")
    if rec.get("foreign_flow_status") == FOREIGN_UNKNOWN:
        missing.append("FOREIGN_FLOW")
    if rec.get("stock_state_source_status") not in {"OK", None, ""}:
        if rec.get("stock_state_source_status") in {
            "FREEZE_UNAVAILABLE",
            "SESSION_NOT_IN_FREEZE",
        }:
            missing.append("T0_FREEZE")
    return missing


def reasons(rec: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    edge = rec.get("edge_status")
    if edge == EDGE_STATUS_ACTIVE_MATCH:
        ids = rec.get("matched_edge_ids") or []
        out.append(f"ACTIVE_MATCH:{','.join(ids) if ids else 'yes'}")
    elif edge == EDGE_STATUS_NO_ACTIVE_EDGE_AVAILABLE:
        out.append("NO_ACTIVE_EDGE_AVAILABLE")
    elif edge == EDGE_STATUS_NO_ACTIVE_MATCH:
        out.append("NO_ACTIVE_MATCH")
    elif edge == EDGE_STATUS_UNKNOWN:
        out.append("EDGE_UNKNOWN")
    if _activity_abnormal(rec):
        out.append(f"INTRADAY_ACTIVITY:{rec.get('activity_status')}")
        if rec.get("trading_value_status") == TRADING_VALUE_UNUSUALLY_HIGH:
            out.append("TRADING_VALUE_UNUSUALLY_HIGH")
        if rec.get("volume_acceleration_status") == VOLUME_ACCELERATION_HIGH:
            out.append("VOLUME_ACCELERATION_HIGH")
        direction = rec.get("price_direction") or PRICE_DIRECTION_UNKNOWN
        out.append(f"PRICE_PATH:{direction}")
        out.append("ACTIVITY_IS_NOT_MONEY_INFLOW")
    elif rec.get("activity_status") == INTRADAY_ACTIVITY_UNKNOWN:
        out.append("CAMERA_UNKNOWN_NOT_LOW")
    ff = rec.get("foreign_flow_status")
    if ff == FOREIGN_STRONG_BUY:
        out.append("FOREIGN_STRONG_BUY")
    elif ff == FOREIGN_STRONG_SELL:
        out.append("FOREIGN_STRONG_SELL")
    elif ff == FOREIGN_UNKNOWN:
        out.append("FOREIGN_UNKNOWN_NOT_ZERO")
    if _learned_sweetspot(rec):
        out.append("LEARNED_SWEETSPOT")
    elif rec.get("sweetspot_status") == "LEGACY_HEURISTIC_AUXILIARY":
        out.append("SWEETSPOT_AUXILIARY_NON_AUTHORITATIVE")
    relation = rec.get("observation_relation") or observation_relation(rec)
    out.append(f"RELATION:{relation}")
    out.append("AUTHORITY_RESEARCH_ONLY")
    out.append(SPEAK_POLICY)
    return out


def _activity_phrase(rec: Dict[str, Any]) -> str:
    bits = ["Hoạt động giao dịch intraday cao bất thường"]
    extras = []
    if rec.get("trading_value_status") == TRADING_VALUE_UNUSUALLY_HIGH:
        extras.append("giá trị giao dịch ước tính (close×volume) cao so với universe")
    if rec.get("volume_acceleration_status") == VOLUME_ACCELERATION_HIGH:
        extras.append("khối lượng tăng tốc trong phiên")
    direction = rec.get("price_direction")
    if direction == PRICE_DIRECTION_DOWN:
        extras.append("giá giảm trong phiên (open→close; không phải dòng tiền vào)")
    elif direction == PRICE_DIRECTION_UP:
        extras.append("giá tăng trong phiên (open→close; không chứng minh dòng tiền vào)")
    close_loc = rec.get("close_location")
    if close_loc == "CLOSE_NEAR_LOW":
        extras.append("giá đóng gần đáy phiên")
    elif close_loc == "CLOSE_NEAR_HIGH":
        extras.append("giá đóng gần đỉnh phiên")
    if extras:
        return bits[0] + " (" + "; ".join(extras) + ")"
    return bits[0] + " (quan sát Camera OHLCV, không phải dòng tiền vào/ra)"


def _ff_phrase(rec: Dict[str, Any]) -> str:
    ff = rec.get("foreign_flow_status")
    if ff == FOREIGN_STRONG_SELL:
        return "nước ngoài bán mạnh (EOD, không phải Camera realtime; không phải lệnh bán)"
    return "nước ngoài mua mạnh (EOD, không phải Camera realtime; không phải lệnh mua)"


def evidence_summary_vi(rec: Dict[str, Any]) -> str:
    edge = rec.get("edge_status")
    cam = rec.get("camera_data_status")
    active = edge == EDGE_STATUS_ACTIVE_MATCH
    act = _activity_abnormal(rec)
    ff = _ff_abnormal(rec)
    learned = _learned_sweetspot(rec)
    relation = observation_relation(rec)
    camera_missing = cam in {CAMERA_DATA_FEED_MISSING, CAMERA_DATA_MISSING_SYMBOL} or rec.get(
        "activity_status"
    ) == INTRADAY_ACTIVITY_UNKNOWN

    if not is_notable(rec):
        if camera_missing and cam in {CAMERA_DATA_FEED_MISSING, CAMERA_DATA_MISSING_SYMBOL}:
            return "Không thể đánh giá Camera do thiếu dữ liệu intraday."
        return "Không có bằng chứng đáng chú ý."

    if relation == OBSERVATION_CONFLICT:
        bits = []
        if active:
            bits.append("khớp ACTIVE edge")
        if act:
            bits.append(_activity_phrase(rec))
        if ff:
            bits.append(_ff_phrase(rec))
        if learned:
            bits.append("Sweetspot learned/evidence-derived")
        return "Xung đột bằng chứng: " + "; ".join(bits) + ". RESEARCH ONLY — không phải lệnh."

    if active and act and ff:
        return f"Cổ phiếu khớp ACTIVE edge + {_activity_phrase(rec)} + {_ff_phrase(rec)}."
    if active and act:
        return f"Cổ phiếu khớp ACTIVE edge; Camera: {_activity_phrase(rec)}."
    if active and ff:
        return f"Cổ phiếu khớp ACTIVE edge; {_ff_phrase(rec)}."
    if active and camera_missing:
        return "Cổ phiếu khớp ACTIVE edge; Camera chưa xác nhận hoạt động intraday bất thường (UNKNOWN)."
    if active:
        return "Cổ phiếu khớp ACTIVE edge; Camera chưa xác nhận hoạt động intraday bất thường."
    if act and ff:
        prefix = "Không có ACTIVE edge đã được xác nhận, nhưng "
        return prefix + f"{_activity_phrase(rec)} và {_ff_phrase(rec)}."
    if act:
        return "Không có ACTIVE edge đã được xác nhận, nhưng " + _activity_phrase(rec) + "."
    if ff:
        return "Không có ACTIVE edge đã được xác nhận, nhưng " + _ff_phrase(rec) + "."
    if learned:
        return "Có Sweetspot learned/evidence-derived (không phải heuristic legacy; không phải ACTIVE edge)."
    return "Bằng chứng đáng chú ý trong phiên này."


def finalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)
    out["authority"] = AUTHORITY_LABEL
    out["research_label"] = AUTHORITY_LABEL
    out["observation_relation"] = observation_relation(out)
    out["interest_level"] = interest_level(out)
    out["evidence_summary"] = evidence_summary_vi(out)
    out["reasons"] = reasons(out)
    out["missing_evidence"] = missing_evidence(out)
    rank, _ = rank_key(out)
    out["presentation_rank"] = rank
    out["notable"] = is_notable(out)
    return out


def session_surface(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    notable = [r for r in records if r.get("notable")]
    notable.sort(key=lambda r: (r.get("presentation_rank", 99), r.get("symbol") or ""))
    if not notable:
        headline = NO_INTEREST_VI
    else:
        top = notable[0]
        headline = (
            f"Đã quét {len(records)} cổ phiếu, nói {len(notable)} quan sát đáng chú ý. "
            f"{top.get('evidence_summary')}"
        )
    return {
        "speak_policy": SPEAK_POLICY,
        "notable_count": len(notable),
        "surfaced_symbols": [r.get("symbol") for r in notable],
        "observations": notable,
        "headline_vi": headline,
        "authority": AUTHORITY_LABEL,
        "no_interest": len(notable) == 0,
    }


def scan_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    def _count(pred) -> int:
        return sum(1 for r in records if pred(r))

    return {
        "scanned_count": len(records),
        "notable_count": _count(lambda r: r.get("notable")),
        "active_match_count": _count(lambda r: r.get("edge_status") == EDGE_STATUS_ACTIVE_MATCH),
        "activity_abnormal_count": _count(_activity_abnormal),
        "foreign_abnormal_count": _count(_ff_abnormal),
        "conflict_count": _count(lambda r: r.get("observation_relation") == OBSERVATION_CONFLICT),
        "agreement_count": _count(lambda r: r.get("observation_relation") == OBSERVATION_AGREEMENT),
        "camera_unknown_count": _count(lambda r: r.get("activity_status") == INTRADAY_ACTIVITY_UNKNOWN),
        "foreign_unknown_count": _count(lambda r: r.get("foreign_flow_status") == FOREIGN_UNKNOWN),
        "learned_sweetspot_count": _count(_learned_sweetspot),
        "legacy_sweetspot_not_spoken": _count(
            lambda r: r.get("sweetspot_status") == "LEGACY_HEURISTIC_AUXILIARY" and not r.get("notable")
        ),
    }
