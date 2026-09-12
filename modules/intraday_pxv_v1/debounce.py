"""Published evidence debounce — Slice 1C, shadow only.

RAW one-bar P×V classification is unchanged. This module only maps a RAW
sequence to PUBLISHED evidence:

- 2 consecutive RAW STRENGTHEN before publishing STRENGTHEN
- 2 consecutive RAW WEAKEN before publishing WEAKEN
- published S→W (and W→S) only after 2 consecutive opposite RAW bars
- a single RAW NEUTRAL returns published S/W to NEUTRAL
- UNUSABLE remains authoritative
- CONFLICT is treated as a fade (not S, not W) so directional state is not held

Not hysteresis. Not cooldown. Not threshold tuning. Not T+n.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.intraday_pxv_v1.constants import (
    EV_CONFLICT,
    EV_NEUTRAL,
    EV_STRENGTHEN,
    EV_UNUSABLE,
    EV_WEAKEN,
    RESEARCH_DEFAULT_PUBLISH_CONFIRM_BARS,
)

SW = (EV_STRENGTHEN, EV_WEAKEN)
FADE = {EV_NEUTRAL, EV_CONFLICT}


@dataclass
class DebounceState:
    published: str = EV_NEUTRAL
    raw_run: str | None = None
    raw_run_len: int = 0


class PublishedDebouncer:
    def __init__(self, confirm_bars: int = RESEARCH_DEFAULT_PUBLISH_CONFIRM_BARS):
        self.confirm_bars = confirm_bars
        self.state = DebounceState()

    def step(self, raw: str) -> tuple[str, str]:
        raw = str(raw or EV_NEUTRAL)
        st = self.state

        if raw == EV_UNUSABLE:
            st.published = EV_UNUSABLE
            st.raw_run = EV_UNUSABLE
            st.raw_run_len = 1
            return st.published, "gate UNUSABLE — published follows RAW"

        if st.published == EV_UNUSABLE:
            st.published = EV_NEUTRAL

        if st.raw_run == raw:
            st.raw_run_len += 1
        else:
            st.raw_run = raw
            st.raw_run_len = 1

        if raw in FADE:
            if st.published in SW:
                st.published = EV_NEUTRAL
                return st.published, "single RAW fade returns published S/W to NEUTRAL"
            return st.published, "published NEUTRAL (RAW fade)"

        if raw in SW:
            if st.published == raw:
                return st.published, f"published {raw} continues"
            if st.raw_run == raw and st.raw_run_len >= self.confirm_bars:
                prev = st.published
                st.published = raw
                if prev in SW and prev != raw:
                    return (
                        st.published,
                        f"published {prev}->{raw} after {self.confirm_bars} consecutive RAW {raw}",
                    )
                return (
                    st.published,
                    f"published {raw} after {self.confirm_bars} consecutive RAW {raw}",
                )
            if st.published in SW:
                return (
                    st.published,
                    f"published {st.published} held — need {self.confirm_bars} consecutive RAW {raw} to reverse",
                )
            return (
                st.published,
                f"published NEUTRAL — awaiting {self.confirm_bars} consecutive RAW {raw}",
            )

        st.published = EV_NEUTRAL
        return st.published, f"published NEUTRAL (unrecognized RAW {raw})"


def publish_sequence(raw_labels: list[str]) -> list[str]:
    deb = PublishedDebouncer()
    return [deb.step(r)[0] for r in raw_labels]
