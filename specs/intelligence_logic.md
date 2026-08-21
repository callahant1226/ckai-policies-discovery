# Intelligence Logic: Prompt Flow & Response Generation

> **Status: Proposed draft**
>
> Covers the orchestration architecture that turns a user question, the CKAI answer, and retrieved policy evidence into a final response — the part of the system that gets changed off the back of eval results and user testing sessions. Response-creation prompt *content* (physician and nurse) is not yet designed; this doc defines the pipeline contract that content will plug into. Retrieval scoring/combination itself is tracked in [technical_spec.md §6](technical_spec.md#6-exemplar-policy-library) / [policy_storage.md](policy_storage.md), not here.

## 1. Design Goal

Physician and nurse experiences must be able to differ not just in prompt wording but potentially in flow topology (extra/skipped/reordered steps). The system is iterated primarily off eval results and user-testing sessions, so the architecture needs to make a given answer's failure attributable to a specific step and reproducible across prompt versions — not just "the answer got better/worse."

## 2. Pipeline Architecture: Typed Steps

Each step in a flow is a small unit with:

- A Pydantic input model and output model.
- If LLM-backed, a prompt template kept as its own versioned file, not an inline string:

```text
backend/prompts/<experience>/<step_name>/v1.md
```

A prompt change is a file diff with a version number, so it can be directly compared against eval results (did `v2` of a given step's prompt actually improve outcomes) rather than relying on memory of what changed.

## 3. Flow Definition Per Experience

A flow is an ordered list of step instances defined in plain Python — no flow-definition DSL, which isn't justified at two flows and this prototype's scale. Physician and nurse each get their own list. Steps may share an implementation with a different prompt/parameters (e.g. initial retrieval logic identical, filtered differently), or a flow may add, skip, or reorder a step entirely relative to the other experience's flow.

## 4. Steps In The Flow

| Step | Type | Notes |
| --- | --- | --- |
| Intent extraction | LLM, structured output | Question → `Intent` (topic hints, category signal, key terms). Feeds initial retrieval. |
| Initial retrieval | Deterministic | Queries the SQLite/FTS+vector index from [policy_storage.md](policy_storage.md). No LLM call. |
| CKAI call | External API | Runs concurrently with the two steps above via `asyncio.gather`, per [technical_spec.md §2](technical_spec.md#2-architecture-overview). |
| Retrieval refinement | LLM, structured output | Question + CKAI answer + initial results → refined query/filters → re-query the index. Runs after CKAI resolves, before anything is shown to the user. |
| Response creation | Pluggable, not yet designed | Sub-steps below. |

## 5. Response Creation

Prompt content here isn't designed yet; the contract is fixed so content can be dropped in once it exists. Default shape, as a fixed chain (see §7 on why not agentic):

### 5.1 Draft Answer

Produces a candidate answer plus its citations as structured data (see §5.2), from the question, CKAI answer, and final retrieved policy content.

### 5.2 Citation Validation

Purpose: verify every claim attributed to policy content is (a) attributed to evidence actually retrieved for this request, and (b) actually supported by that evidence's text — directly de-risking Key Risk #1 (accurate presentation) and Key Risk #2 (user trust) from [goals_and_aims.md](goals_and_aims.md).

The draft step is forced to return structured citations rather than inline prose markers:

```python
class Citation(BaseModel):
    chunk_id: str             # must match a chunk actually retrieved this request
    claim_text: str           # the specific assertion being attributed
    quoted_span: str | None   # exact source text, if directly quoted

class DraftAnswer(BaseModel):
    answer_text: str
    citations: list[Citation]
```

Two distinct checks run against this:

1. **Referential integrity (Pydantic-only, no extra LLM call).** A `@model_validator` on `DraftAnswer` checks each `chunk_id` against the set of chunk_ids actually retrieved for the request. Catches fabricated/hallucinated citations for free.
2. **Semantic support (needs an LLM or heuristic call — Pydantic does not judge this itself).** A separate structured call checks whether the cited chunk's text actually entails the claim:

```python
class SupportCheck(BaseModel):
    claim_text: str
    chunk_text: str

class SupportVerdict(BaseModel):
    supported: bool
    confidence: float
    explanation: str
```

A failed check (bad `chunk_id`, or `supported: false`) raises rather than silently passing through — the pipeline must explicitly strip the claim, flag it, or trigger a bounded regeneration attempt. This step runs before conflict checking (§5.3) so that conflict resolution never operates on a hallucinated policy claim.

### 5.3 Conflict Check

Explicit step comparing the CKAI (clinical) answer against validated policy claims — handles Key Risk #4 from the goals doc within the flow itself, not as a separate architectural component.

### 5.4 Experience-Specific Formatting

Presentation differences between physician and nurse outputs.

## 6. Pydantic's Role

Two distinct jobs, and a boundary worth being explicit about:

- **Contract enforcement.** Every step's LLM call returns a typed Pydantic model instead of free text — this applies pipeline-wide, not just to citation validation. It's what makes downstream checks (like referential integrity) possible without text-parsing.
- **Free, deterministic checks.** Model/field validators can enforce things like chunk_id membership synchronously, with no extra model call.
- **What it does *not* do:** semantic/factual judgment (e.g. "does this text support this claim") requires an LLM or heuristic call — Pydantic's job there is only to give that call a clean, structured, loggable contract (`SupportCheck` → `SupportVerdict`), not to make the judgment itself.
- **Eval/observability.** A `PipelineRun` model wraps a full request: run_id, experience, and per-step records (prompt_version, input, output, latency_ms, model_id, and for citation validation, proposed/accepted/rejected citations with reasons). This is the same structure that feeds the metadata requirement in [technical_spec.md §4](technical_spec.md#4-backend-api-contract) and the session logs in [technical_spec.md §8](technical_spec.md#8-testing-logging-and-observability) — the log record *shape* is decided here; the storage/tool destination is still open there.

**Constraint: open-source `pydantic` (core library) only.** No Pydantic Logfire or other Pydantic-hosted SaaS — everything above runs as plain Python classes inside the backend process, with no account or external service involved. If an agentic step is ever adopted later (§7) via Pydantic AI, that library's core is also open source, but its quickstarts default to wiring in Logfire for tracing — that would need to be skipped or swapped for the same self-rolled `PipelineRun` logging.

## 7. Agents: Deferred, Not Adopted At This Stage

Decision: a manually designed flow with explicit conditional logic, not an agentic/autonomous framework, for this stage of the prototype. Reasons:

- **Reproducibility for eval.** A fixed pipeline takes the same path every run, so `PipelineRun` traces are directly comparable across prompt versions. An agent's control flow can vary run to run on identical input, making it hard to attribute a change in outcome to a specific prompt edit.
- **The flow shape is already known.** Agent autonomy earns its keep when *what to do next* is genuinely undetermined at runtime — that's not the current situation; the step sequence is already designed.
- **Auditability in a clinical/policy context.** Bounded, fixed steps are easier to trust and review for SME testing than a loop that decides its own next action.

**Condition to revisit:** if eval data shows one specific step genuinely needs variable-length reasoning a fixed step can't express (e.g. retrieval sometimes needing one more pass, sometimes three), scope a bounded loop (fixed max iterations, same `PipelineRun` logging) to that one step only — not autonomy for the whole pipeline.

## 8. Non-Goals For This Prototype

- No agent framework or autonomous control flow adopted at this stage.
- No hosted/SaaS observability (Logfire or equivalent).
- No flow-definition DSL or config language — flows are plain Python.

## Open Items

- Response-creation prompt content itself (physician and nurse) — not yet designed; this doc defines the contract it plugs into.
- Semantic support-check implementation for citation validation (LLM prompt vs. heuristic) — not yet chosen.
- Whether any step is ever upgraded to a bounded agentic loop — deferred pending eval results (§7).
- Logging/eval tooling destination (e.g. Ballpark) — record shape is decided here; storage target is tracked in [technical_spec.md §8](technical_spec.md#8-testing-logging-and-observability).
