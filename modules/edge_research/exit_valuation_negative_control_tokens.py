"""Scanner vocabulary for Phase 3H.8 negative-control audits (not runtime behavior)."""

FORBIDDEN_EXIT_TOKENS = frozenset(
    {
        "stop_bonus",
        "negative_erv_stop_rule",
        "branch_depth_stop_threshold",
        "force_switch",
        "diversity_bonus",
        "branch_quota",
        "bb10_special_case",
        "blind_benchmark",
        "chatgpt",
    }
)
