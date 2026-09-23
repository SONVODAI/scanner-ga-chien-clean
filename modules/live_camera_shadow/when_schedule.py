"""VN cash-session clocks for the live V2 WHEN oneshot.

Morning fires start when the 09:15 slot is complete (09:20) and stop at the
11:30 completion. Afternoon fires start at the 13:05 completion and stop at
14:50. Each fire is 45 seconds after the slot completion. Lunch and the
post-close archive clocks are not in this list.
"""

from __future__ import annotations

from datetime import datetime, time

from modules.live_candidate.calendar import as_vn

FIRE_OFFSET_SEC = 45

# Inclusive minute ranges. The oneshot may run for the rest of that minute.
MORNING_START = time(9, 20)
MORNING_END = time(11, 30, 59)
AFTERNOON_START = time(13, 5)
AFTERNOON_END = time(14, 50, 59)


def _step(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    hour, minute = start
    end_h, end_m = end
    out: list[tuple[int, int]] = []
    while (hour, minute) <= (end_h, end_m):
        out.append((hour, minute))
        minute += 5
        if minute >= 60:
            hour += 1
            minute -= 60
    return out


def live_when_fire_clocks() -> tuple[tuple[int, int, int], ...]:
    """(hour, minute, second) of each scheduled cycle start, ICT."""
    slots = _step((9, 20), (11, 30)) + _step((13, 5), (14, 50))
    return tuple((hour, minute, FIRE_OFFSET_SEC) for hour, minute in slots)


def is_live_when_window(now: datetime) -> bool:
    """True during a scheduled fire minute on a weekday. False at lunch and after 14:50."""
    local = as_vn(now)
    if local.weekday() >= 5:
        return False
    current = local.timetz().replace(tzinfo=None)
    if MORNING_START <= current <= MORNING_END:
        return True
    if AFTERNOON_START <= current <= AFTERNOON_END:
        return True
    return False
