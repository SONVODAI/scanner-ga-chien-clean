# Phase 3I.0 — Autonomous Proposition Generation Readiness & Blind Evaluation Design

**Branch:** `cursor/phase-3i0-proposition-generation-readiness-aad2`  
**Mode:** AUDIT + DESIGN ONLY — **no production code modified**  
**Readiness:** **PARTIALLY READY**

---

## 1. Branch / HEAD / Git Status

| Item | Value |
|------|-------|
| Branch | `cursor/phase-3i0-proposition-generation-readiness-aad2` |
| HEAD | `a9b87b11f` (based on 3H.14 audit; no production changes) |
| Artifacts | `diagnostics/phase_3i0_proposition_generation_readiness/` |

---

## 2. Current Question-Generation Dependency Graph

```
[Frozen Panel CSV] ──human seed──► [ROOT_CONFIG bootstrap]
        │                                    │
        ▼                                    ▼
[panel_preflight]              [Root OBSERVATION + QUESTION + ExperimentSpec]
        │                                    │
        │                                    ▼
        │                         [execute_research_experiment]
        │                                    │
        │                                    ▼
        │                         [ToolResult + OBS_* codes]
        │                                    │
        │                                    ▼
        │                         [interpret_tool_result → ResearchAssessment]
        │                           gaps, falsify targets, observation_kind
        │                                    │
        │                                    ▼
        │              ┌────── [generate_action_candidates] ◄── FIXED TEMPLATE CATALOG
        │              │         research_actions.py (24 template families)
        │              │         + grammar propose_* (combinatorics)
        │              │         + frame propose_* (reframes)
        │              └──────► [ResearchActionCandidate + question_text + draft_spec]
        │                                    │
        │                                    ▼
        │                         [derive_identity → CanonicalPropositionCore]
        │                                    │
        │                                    ▼
        │                         [score → rank → select_global_opportunity]
        │                                    │
        └────────────────────────────────────▼
                              [spawn_child_question + add_experiment]

MISSING LINK: No path from [panel/market structure] → [novel scientific proposition]
MISSING LINK: No path from [observation] → [question text outside template catalog]
```

**Parallel but disconnected:** Phase 2 `discovery.py` → `challenger.py` (grid search over `SEARCH_FEATURES`; not wired to Research Brain Q-gen).

---

## 3. Hard-Coded Proposition-Source Inventory

| Source | Location | Classification |
|--------|----------|----------------|
| 24 `question_template_id` families | `research_actions.py` | **SCIENTIFIC PRIOR** |
| Fixed English `question_text` per template | `research_actions.py` | **SCIENTIFIC PRIOR** |
| 12 `GAP_*` information gap codes | `research_interpreter.py` | **SCIENTIFIC PRIOR** |
| 4 `FALSIFY_*` target codes | `research_interpreter.py` | **SCIENTIFIC PRIOR** |
| `ResearchNeedType` registry (13 needs) | `research_competence.py` | **SCIENTIFIC PRIOR** |
| `SEARCH_FEATURES` / `FEATURE_BUCKETS` | `contracts.py` | **HUMAN-SEED** |
| `ROOT_CONFIG` bootstrap question | `bb07_run_benchmark.py` | **HUMAN-SEED** |
| Outcome/population grammar kinds | `research_grammar.py` | **REPRESENTATIONAL CONSTRAINT** |
| Tool registry (14 tools) | `research_tools.py`, `research_adaptive_tools.py` | **EXECUTION SAFETY + REPRESENTATIONAL** |
| `RETURN_COLUMNS`, horizon lists | `contracts.py`, `research_grammar.py` | **REPRESENTATIONAL CONSTRAINT** |
| Panel preflight / prohibited columns | `research_panel_preflight.py` | **EXECUTION SAFETY CONSTRAINT** |
| Frame transformation types (7) | `research_frame.py` | **SCIENTIFIC PRIOR** (implicit hypothesis families) |

Full inventory: `artifacts/01_hard_coded_inventory.json`

---

## 4. What Is Autonomous vs Template-Bound Today

| Capability | Status |
|------------|--------|
| Execute experiments on panel data | **Autonomous** |
| Emit OBS_* observation codes from tools | **Autonomous** |
| Derive information gaps from branch coverage | **Autonomous** |
| Select among generated candidates | **Autonomous** |
| Rank by ERV with semantic novelty | **Autonomous** |
| Compose population/outcome within grammar | **Combinatorial** (not novel semantics) |
| Reframe via fixed frame transforms | **Catalog-selected** |
| Parameterize template (feature, threshold) | **Template-bound** |
| Root scientific question | **Human-seeded** |
| Child question natural language | **Template-bound** (fixed English strings) |
| Novel uncertainty family | **Not possible** (closed GAP_* set gates candidates) |
| Invent proposition not in catalog | **Not possible** |

**Combinatorial template variation ≠ autonomous proposition generation.**

---

## 5. Precise Definition of Autonomous Proposition Generation

A genuinely autonomous proposition must specify — derived from observed structure, not selected from a fixed catalog:

1. **Motivating observation** — what structural anomaly or evidence pattern triggered it
2. **Population/context** — who/what is being compared or conditioned
3. **Explanatory relation or contrast** — what explanatory feature or mechanism is hypothesized
4. **Outcome** — what is being predicted or compared
5. **Horizon** — temporal scope where relevant
6. **Uncertainty resolved** — the scientific question being answered (not merely a GAP_* label)
7. **Falsifiable expectation** — what result would refute the proposition
8. **Evidence required** — what experiment would test it

**Success criterion:** The proposition's `scientific_question_key` is not isomorphic to any existing template-family × parameter combination, AND its motivating observation is traceable to structured evidence.

**Design challenge:** Derive (1)–(8) from observed structure while remaining executable under grammar + tool constraints.

---

## 6. Pseudo-Creativity Failure Modes

| Failure Mode | Detection |
|--------------|-----------|
| Random feature combinations | Require OBS_* or metric grounding link; reject ungrounded propositions |
| Template permutation explosion | Semantic dedup via proposition core; spam penalty metrics |
| Synonym/rewording | Embedding or key-hash match against template question_text corpus |
| Arbitrary threshold generation | Require shape/gradient OBS_* precedent for threshold_exploration |
| Unmotivated population slicing | Require concentration/dispersion evidence for refine/widen |
| Horizon change for novelty only | Semantic freshness audit; reject if outcome/pop unchanged |
| Hypothesis spam | Penalize high volume + low survivor rate + low grounding |
| Template family rediscovery | Map generated core to nearest template_id; flag isomorphic |
| Semantic duplicates | 3H.10/3H.12 relationship classifier on generated cores |
| Unfalsifiable hypotheses | Require executable comparison operator + outcome spec |
| Future-data leakage | Temporal legality audit + cutoff enforcement (existing) |

---

## 7. Observation-Layer Readiness

### What exists today (experiment-level)

- **OBS_* codes** from tools: concentration, heterogeneity, shape, sensitivity, trajectory
- **ResearchAssessment**: gaps, falsification targets, observation_kind, descriptive strength
- **Shape interpreter**: monotonic, gradient, step, flat, extreme bin
- **Adaptive tool metrics**: category separation, threshold regions
- **Panel preflight**: eligible explanatory features, sample sizes

### What is missing (market/proposition-level)

- No automated **market anomaly detector** feeding root questions (`AUTONOMOUS_SEED` not `ANOMALY`)
- No **cross-sectional anomaly catalog** beyond experiment OBS_* codes
- No **residual/unexplained structure** detector
- No **evidence conflict** resolver (contradictory branch results → new proposition)
- No **regime-conditioned anomaly** beyond market_conditioning tool output
- Phase 2 **discovery grid** not connected to proposition synthesis

---

## 8. Candidate Architectures & Tradeoffs

### Architecture A — Observation-Derived Proposition Synthesis (RECOMMENDED)

Structured anomalies → `PropositionRecord` (core + motivation) → grammar validates → tool binding.

| Criterion | Rating |
|-----------|--------|
| Autonomy | High |
| Pseudo-creativity risk | Medium (mitigated by grounding requirement) |
| Executability | High |
| Falsifiability | High |
| Explosion risk | Medium |
| Leakage risk | Low (with evaluator separation) |
| Compatibility | High |
| Minimality | **Highest** |

### Architecture B — Open Proposition Grammar

Direct construction of proposition components under grammar — no template catalog.

| Criterion | Rating |
|-----------|--------|
| Autonomy | Very high |
| Pseudo-creativity risk | **High** |
| Explosion risk | **High** |
| Minimality | Low |

**Deferred** — too much scope for first implementation.

### Architecture C — Hypothesis Mutation / Evolution

Mutate existing proposition cores based on unresolved evidence (narrow, broaden, contradict, abandon).

| Criterion | Rating |
|-----------|--------|
| Autonomy | Medium |
| Pseudo-creativity risk | Low |
| Compatibility | Very high |
| Best as | Evidence-responsive follow-on to Architecture A |

---

## 9. Recommended Architecture

**Phase 3I.1 proposal:** Architecture **A** (Observation-Derived Proposition Synthesis) as the minimal first capability, with Architecture **C** designed in parallel for evidence-responsive redirection but implemented second.

Do not implement Architecture B until A+C are evaluated on blind benchmark.

---

## 10. Hidden / Blind Benchmark Design (BB-Prop-01)

### Three-way separation

| Zone | Contents | Access |
|------|----------|--------|
| Generator development | Panels without hidden-edge labels; synthetic fixtures | Generator code |
| Frozen blind eval | Held-out panel fingerprint + hidden phenomena definitions | Never in generator |
| Hidden evaluator | Offline semantic matcher | Post-hoc only |

### Convergence classes

1. **EXACT_HIDDEN_EDGE_REDISCOVERY** — proposition core matches hidden phenomenon
2. **PARTIAL_SEMANTIC_CONVERGENCE** — overlapping population/outcome/uncertainty
3. **SCIENTIFICALLY_ADJACENT_INDEPENDENT** — valid but different scientific question
4. **UNRELATED_PROPOSITION** — no semantic overlap
5. **TEMPLATE_LEAKAGE_OR_ANSWER_IMITATION** — isomorphic to known template or encodes hidden predicate

### Leakage controls

- Hidden predicates never in `SEARCH_FEATURES`, template text, or generation examples
- Evaluator commit frozen after generator commit
- Human/ChatGPT edges used **only** as frozen hidden benchmark outcomes

Design artifact: `artifacts/03_blind_benchmark_design.json`

---

## 11. Creativity & Scientific-Quality Metrics

**Do not use raw question count as primary metric.**

| Metric | Purpose |
|--------|---------|
| Semantic proposition diversity | Unique `scientific_question_key` / session |
| Observational grounding rate | Propositions linked to OBS_* or metric evidence |
| Scientific independence rate | GENUINELY_INDEPENDENT / total generated |
| Falsifiability score | Executable comparison/contrast present |
| Executability rate | Pass grammar + tool validation |
| Evidence responsiveness | Changes attributable to new evidence |
| Abandoned hypothesis rate | Explicit abandon after falsification |
| Duplicate rate | NEAR_DUPLICATE + IDENTICAL / total |
| Useful survivor rate | Propositions receiving follow-up investigation |
| Hidden benchmark convergence | Blind evaluator class distribution |
| Budget efficiency | Independent lines / experiment |
| Hypothesis spam penalty | High volume × low grounding × low survivor |

Artifact: `artifacts/04_metrics_design.json`

---

## 12. Evidence-Responsive Generation Design

Future generator must support evidence-driven transitions:

| Evidence signal | Proposition response | vs template progression |
|-----------------|---------------------|------------------------|
| Strengthening effect | Narrow population / refine threshold | Not predetermined next template |
| Flat/noisy shape | Abandon or change explanatory feature | Not automatic threshold_explore |
| Concentration detected | Decompose or falsify | Grounded in OBS_* not GAP checklist |
| Contradictory branch | New independent proposition | Not frame reframe catalog |
| Falsification survived | Broaden or change outcome | Evidence-driven not HORIZON_ADVANCE template |

**Genuine redirection criterion:** New `scientific_question_key` with evidence audit trail showing motivating OBS_* change — not merely next unchecked GAP_* in fixed order.

Architecture C (hypothesis mutation) implements this without expanding template catalog.

---

## 13. Falsification Integration Assessment

### In-session (Research Brain)

- `interpret_tool_result()` emits `FALSIFY_*` targets from concentration/sensitivity
- `generate_action_candidates()` emits falsification templates (`sensitivity_analysis`)
- Falsification competes in planner scoring — no separate pipeline stage
- **Can ask "what would disprove this?"** — but only via **3 fixed falsification templates**

### Challenger (Phase 2–3)

- Runs robustness battery on **discovery ledger rows only**
- **Not wired** to Research Brain question generation
- **Architectural separation** prevents in-session falsification from using Challenger infrastructure

### Assessment

Existing falsification is **template-bound** (3 falsification families). It can support future autonomous falsification **if** Architecture A/C generates falsification-seeking propositions, but Challenger integration requires new bridge (out of scope for 3I.0).

---

## 14. Readiness: **PARTIALLY READY**

| Layer | Status |
|-------|--------|
| ExperimentSpec + tools + grammar | READY |
| Proposition identity + semantic ranking | READY |
| Experiment-level observation codes | READY |
| Template catalog candidate generation | READY (but template-bound) |
| Market→proposition synthesis | **NOT READY** |
| Novel question semantics | **NOT READY** |
| Root question autonomy | **NOT READY** |

---

## 15. Single Highest-Leverage Prerequisite

**Observation-to-Proposition Record (OPR) bridge**

A deterministic, auditable layer that converts structured observation evidence (`ToolResult` metrics, `OBS_*` codes, panel statistics) into a `CanonicalPropositionCore` plus motivation metadata **before** any `question_template_id` binding.

**Why it must precede synthesis:** All downstream infrastructure (grammar, tools, identity, ranking, falsification) already consumes `ExperimentSpec` and proposition cores. The sole missing capability is **originating the scientific question from observed structure** rather than selecting from `research_actions.py` templates.

---

## 16. Proposed Next Phase (Proposal Only)

**Phase 3I.1 — Observation-to-Proposition Record (OPR) Bridge (Design + Minimal Prototype Scope)**

- Define `PropositionRecord` schema (motivation, core, falsifiability claim)
- Specify OPR derivation rules from existing OBS_* codes (no new detectors)
- Pre-register BB-Prop-01 blind benchmark fixtures
- Implement **only** the bridge — not full autonomous generation
- Evaluate: can OPR produce proposition cores not isomorphic to template catalog?

Do not implement in 3I.0.

---

## Final Answers

### A. Can Mr.BOT today invent a scientific market question not implicitly present in its template catalog?

**No.** All child `question_text` strings are fixed English templates in `research_actions.py`. The root question is human-seeded via `ROOT_CONFIG`. Grammar and frame transforms vary population/outcome/parameters within closed hypothesis families — they do not originate novel scientific uncertainties. The closed `GAP_*` set gates which templates can fire, defining the universe of askable questions.

### B. What is the smallest architectural change that could make the answer genuinely "yes"?

**An Observation-to-Proposition Record (OPR) bridge** — a new layer between `interpret_tool_result()` and `generate_action_candidates()` that synthesizes a `CanonicalPropositionCore` plus motivating evidence from structured observations, producing a scientific uncertainty not isomorphic to existing template families, then binds to executable grammar/tools. This is one module, not a planner/scoring/identity rewrite.

### C. How will we prove a future "yes" is real creativity rather than template permutation or hidden-answer leakage?

1. **Blind benchmark separation** — generator never sees hidden phenomena; offline evaluator only
2. **Semantic isomorphism test** — map generated cores to nearest template; reject if isomorphic
3. **Observational grounding audit** — every proposition must link to OBS_* or metric evidence
4. **Convergence taxonomy** — distinguish exact rediscovery, partial convergence, adjacent independent, unrelated, leakage
5. **Spam/diversity metrics** — penalize volume without survivor rate or independence
6. **Frozen commit discipline** — no post-hoc tuning after seeing blind eval

---

**STOP — Phase 3I.0 complete. No implementation. No deployment.**
