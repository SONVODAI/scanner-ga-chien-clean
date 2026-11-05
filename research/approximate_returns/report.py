"""Primary statistics exclude truncated sessions and suspected discontinuities."""

from __future__ import annotations

import math

from research.approximate_returns.contract import (
    COMPARISON_COHORTS,
    COHORT_UNATTRIBUTED,
    HORIZONS,
    STATUS_AVAILABLE,
    STATUS_DISCONTINUITY,
    STATUS_NOT_YET,
    STATUS_T0_MISSING,
    STATUS_TARGET_MISSING,
    STATUS_TRUNCATED,
)

REGIME_BANDS = (
    ("market_real_below_5", 0, 5),
    ("market_real_5_to_below_7", 5, 7),
    ("market_real_7_or_higher", 7, None),
)


def coverage(rows: list[dict]) -> dict:
    counts = {}
    for step in HORIZONS:
        label = f"T+{step}"
        bucket = {
            STATUS_AVAILABLE: 0,
            STATUS_TRUNCATED: 0,
            STATUS_DISCONTINUITY: 0,
            STATUS_NOT_YET: 0,
            STATUS_TARGET_MISSING: 0,
            STATUS_T0_MISSING: 0,
        }
        for row in rows:
            status = row["horizons"][label]["status"]
            bucket[status] = bucket.get(status, 0) + 1
        counts[label] = bucket
    return {"rows": len(rows), "horizons": counts}


def overall_performance(rows: list[dict]) -> dict:
    """One deduplicated sample across every cohort. Returns stay the stored values."""
    chosen = _dedupe(rows)
    return {
        "observations": len(chosen),
        "horizons": {f"T+{step}": _performance(chosen, f"T+{step}") for step in HORIZONS},
    }


def summarize(rows: list[dict]) -> dict:
    """Deduped source comparison plus the retained exclusions."""
    deduped = _dedupe(rows)
    cohorts = {}
    for name in (*COMPARISON_COHORTS, COHORT_UNATTRIBUTED):
        cohort_rows = [row for row in deduped if row["comparison_cohort"] == name]
        cohorts[name] = {
            "observations": len(cohort_rows),
            "horizons": {f"T+{step}": _performance(cohort_rows, f"T+{step}") for step in HORIZONS},
        }
    return {
        "records": len(rows),
        "deduped_observations": len(deduped),
        "coverage": coverage(rows),
        "cohorts": cohorts,
        "action_states": _count(rows, "action_state"),
        "lifecycles": _count(rows, "lifecycle"),
        "action_performance": {
            f"T+{step}": _by_field(deduped, f"T+{step}", "action_state") for step in (1, 5, 10)
        },
        "market_context": _market(deduped),
        "primary_excludes": [STATUS_TRUNCATED, STATUS_DISCONTINUITY, STATUS_TARGET_MISSING, STATUS_T0_MISSING, STATUS_NOT_YET],
    }


def _dedupe(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for row in rows:
        key = (row["comparison_cohort"], row["symbol"], row["t0_date"])
        groups.setdefault(key, []).append(row)
    chosen = []
    for group in groups.values():
        group.sort(key=lambda item: item["row_id"])
        representative = dict(group[0])
        if len({item["action_state"] for item in group}) > 1:
            representative["action_state"] = "STATE_CONFLICT"
        chosen.append(representative)
    return chosen


def _performance(rows: list[dict], label: str) -> dict:
    statuses = [row["horizons"][label]["status"] for row in rows]
    primary = [
        row["horizons"][label]["return_pct"]
        for row in rows
        if row["horizons"][label]["included_in_primary"]
    ]
    review = [
        row["horizons"][label]["return_pct"]
        for row in rows
        if row["horizons"][label]["status"] == STATUS_DISCONTINUITY and row["horizons"][label]["return_pct"] is not None
    ]
    return {
        "observations": len(rows),
        "primary": len(primary),
        "immature": statuses.count(STATUS_NOT_YET),
        "truncated": statuses.count(STATUS_TRUNCATED),
        "discontinuity": statuses.count(STATUS_DISCONTINUITY),
        "missing": statuses.count(STATUS_TARGET_MISSING) + statuses.count(STATUS_T0_MISSING),
        "average_return_pct": _mean(primary),
        "median_return_pct": _median(primary),
        "win_rate_above_3pct": _share(primary, lambda value: value > 3),
        "win_rate_above_5pct": _share(primary, lambda value: value > 5),
        "loss_rate": _share(primary, lambda value: value < 0),
        "loss_rate_at_or_below_minus_3pct": _share(primary, lambda value: value <= -3),
        "loss_rate_at_or_below_minus_5pct": _share(primary, lambda value: value <= -5),
        "downside_p10_pct": _percentile(primary, 10),
        "downside_p25_pct": _percentile(primary, 25),
        "review_discontinuity_count": len(review),
    }


def _by_field(rows: list[dict], label: str, field: str) -> dict:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(str(row.get(field) or "ABSENT"), []).append(row)
    return {name: _performance(group, label) for name, group in sorted(groups.items())}


def _market(rows: list[dict]) -> dict:
    usable = []
    absent = 0
    for row in rows:
        value = row.get("market_real")
        provenance = row.get("market_real_provenance")
        if value is None or not provenance:
            absent += 1
            continue
        usable.append(row)
    bands = {}
    for name, lower, upper in REGIME_BANDS:
        chosen = [
            row for row in usable
            if row["market_real"] >= lower and (upper is None or row["market_real"] < upper)
        ]
        bands[name] = {
            "observations": len(chosen),
            "horizons": {f"T+{step}": _performance(chosen, f"T+{step}") for step in (1, 5, 10)},
        }
    return {
        "basis": "frozen market_real with provenance",
        "usable_observations": len(usable),
        "absent_observations": absent,
        "bands": bands,
    }


def _count(rows: list[dict], field: str) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        name = str(row.get(field) or "ABSENT")
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def _mean(values: list[float]):
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _median(values: list[float]):
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[mid], 4)
    return round((ordered[mid - 1] + ordered[mid]) / 2, 4)


def _share(values: list[float], predicate) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if predicate(value)) / len(values), 4)


def _percentile(values: list[float], percentile: int):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 4)
    rank = (len(ordered) - 1) * (percentile / 100)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return round(ordered[low], 4)
    weight = rank - low
    return round(ordered[low] * (1 - weight) + ordered[high] * weight, 4)
