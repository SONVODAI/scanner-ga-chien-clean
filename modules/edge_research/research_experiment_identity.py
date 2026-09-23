"""
Experiment identity and deduplication for global allocation (Phase 3G.4.1).

Authoritative canonical identity reuses compute_experiment_content_hash from
research_state — the same hash used by ResearchGraph.experiment_index and
DuplicateExperimentError at spawn time.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from modules.edge_research.research_actions import ResearchActionCandidate
    from modules.edge_research.research_graph import ResearchGraph

EXPERIMENT_IDENTITY_VERSION = "research_experiment_identity_v1"

# Structured exclusion reason prefixes (auditable, stable).
REASON_ALREADY_EXECUTED = "duplicate_experiment_already_executed"
REASON_SAME_CYCLE = "duplicate_same_cycle_representative"


# Identity contract (documentation — enforced via compute_experiment_content_hash):
#
# Canonical experiment identity is the SHA-256 of JSON-serialized:
#   tool_name, tool_version, inputs, research_scope, data_cutoff_date
#
# Included (material semantics):
#   - research tool / experiment type (tool_name, tool_version)
#   - tool inputs: features, thresholds, partition params, horizons in inputs
#   - PopulationSpec / OutcomeSpec / frame scope (inside research_scope)
#   - observation horizon (research_scope.pending_question_context, frame fields)
#
# Excluded (path/UI identity):
#   - action_id, frontier_id, branch_root_id, node IDs, planner scores,
#     creation sequence, source path (LOCAL/FRONTIER/etc.)
#
# Equivalent LOCAL and FRONTIER candidates with the same ExperimentSpec draft
# resolve to the same canonical identity.


def canonical_experiment_content_hash(spec: "Any") -> str:
    """Return authoritative session-level experiment identity hash."""
    from modules.edge_research.research_state import (
        ExperimentSpec,
        compute_experiment_content_hash,
    )

    if isinstance(spec, ExperimentSpec):
        return compute_experiment_content_hash(spec)
    if isinstance(spec, dict):
        return compute_experiment_content_hash(ExperimentSpec.from_dict(spec))
    raise TypeError(f"Expected ExperimentSpec or dict, got {type(spec)!r}")


def canonical_hash_from_candidate(
    candidate: Optional["ResearchActionCandidate"],
) -> Optional[str]:
    """Canonical identity for a planner/frontier candidate, or None if no spec."""
    if candidate is None or candidate.draft_spec is None:
        return None
    return canonical_experiment_content_hash(candidate.draft_spec)


def executed_experiment_identities(graph: "ResearchGraph") -> Dict[str, str]:
    """
    Session-level ledger: content_hash -> experiment_node_id.

    Mirrors ResearchGraph.experiment_index — every experiment added to the
    session is registered here before spawn-time DuplicateExperimentError.
    """
    return dict(graph.experiment_index)


def exclusion_reason_already_executed(content_hash: str) -> str:
    return f"{REASON_ALREADY_EXECUTED}:{content_hash}"


def exclusion_reason_same_cycle(content_hash: str, representative_id: str) -> str:
    return f"{REASON_SAME_CYCLE}:{content_hash}:kept={representative_id}"


def _source_priority(source: str) -> int:
    order = {
        "LOCAL": 0,
        "REVISIT": 1,
        "DEFERRED": 2,
        "FRONTIER": 3,
    }
    return order.get(source, 99)


def representative_sort_key(
    *,
    expected_research_value: float,
    source: str,
    action_id: str,
    opportunity_id: str,
) -> Tuple[float, int, str, str]:
    """Deterministic tie-break for same-cycle duplicate representative selection."""
    return (
        -expected_research_value,
        _source_priority(source),
        action_id,
        opportunity_id,
    )


def apply_experiment_identity_deduplication(
    comparable: Sequence[Any],
    excluded: Sequence[Any],
    graph: "ResearchGraph",
) -> Tuple[List[Any], List[Any]]:
    """
    Exclude experiment duplicates before global ERV competition.

    1. Already-executed identities (session experiment_index)
    2. Same-cycle duplicate representations (one representative per hash)

    Returns (updated_comparable, updated_excluded). Opportunities are mutated
    in place for audit fields (comparable, exclusion_reason, experiment_content_hash).
    """
    executed = executed_experiment_identities(graph)
    out_comparable: List[Any] = []
    out_excluded = list(excluded)

    # Pass 1: exclude already-executed equivalents
    pending: List[Any] = []
    for opp in comparable:
        content_hash = getattr(opp, "experiment_content_hash", None)
        if content_hash is None:
            content_hash = canonical_hash_from_candidate(getattr(opp, "action_candidate", None))
            opp.experiment_content_hash = content_hash or ""

        if content_hash and content_hash in executed:
            opp.comparable = False
            opp.exclusion_reason = exclusion_reason_already_executed(content_hash)
            opp.duplicate_of_experiment_id = executed[content_hash]
            out_excluded.append(opp)
        elif content_hash:
            pending.append(opp)
        else:
            out_comparable.append(opp)

    # Pass 2: same-cycle dedup — one representative per content_hash
    by_hash: Dict[str, List[Any]] = {}
    no_hash: List[Any] = []
    for opp in pending:
        h = opp.experiment_content_hash
        if not h:
            no_hash.append(opp)
            continue
        by_hash.setdefault(h, []).append(opp)

    for content_hash, group in by_hash.items():
        if len(group) == 1:
            out_comparable.append(group[0])
            continue
        sorted_group = sorted(
            group,
            key=lambda o: representative_sort_key(
                expected_research_value=o.expected_research_value,
                source=o.source,
                action_id=o.action_id,
                opportunity_id=o.opportunity_id,
            ),
        )
        keeper = sorted_group[0]
        out_comparable.append(keeper)
        for dup in sorted_group[1:]:
            dup.comparable = False
            dup.exclusion_reason = exclusion_reason_same_cycle(
                content_hash, keeper.opportunity_id
            )
            dup.duplicate_representative_id = keeper.opportunity_id
            out_excluded.append(dup)

    out_comparable.extend(no_hash)
    return out_comparable, out_excluded


def sync_frontier_with_executed_identity(graph: "ResearchGraph", content_hash: str) -> int:
    """
    Mark unexplored frontier items semantically equivalent to an executed experiment.

    Called when a new experiment enters experiment_index — keeps frontier lifecycle
    aligned with session identity ledger.
    """
    frontier = graph.get_frontier()
    executed_node = graph.find_experiment_by_content_hash(content_hash) or ""
    return frontier.mark_duplicate_by_content_hash(
        content_hash,
        executed_node_id=executed_node,
    )
