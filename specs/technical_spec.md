# Hospital Policy + CKAI Prototype: Technical Specification (v5)

> **Status: Proposed draft, supersedes v4**
>
> This revision incorporates the front end / back end split, the exemplar policy dataset scope, and the open items still pending discovery. Sections marked **TBD** are intentionally left open rather than assumed.

## 1. Technical Objective

Build one lightweight prototype application that supports two distinct experiences:

- Physician
- Nurse

The user switches between the two experiences using a tab or equivalent control at the top of the interface.

The application should:

- Accept a user question through a conversational interface
- Use the selected experience to determine which CKAI variant and prompt flow are used
- Send the user question to CKAI and the exemplar policy retrieval pipeline in parallel
- Fetch the CKAI answer
- Use the CKAI answer, where useful, to further refine retrieval from the policy dataset
- Use the CKAI answer and retrieved policy content as inputs to the selected response-generation prompt flow
- Present the resulting response to the user
- Be runnable locally
- Be deployable as a single hosted application for SME and user testing

Latency is not a design constraint for this prototype — "acceptable for testing" is the bar, not optimization.

## 2. Architecture Overview

The application is split into two modules communicating over a JSON API:

- **Front end** — a TypeScript single-page application. Framework is not yet decided; the front end is treated as framework-agnostic in this spec.
- **Backend** — a Python JSON API that owns all response creation: the CKAI call, policy retrieval, retrieval refinement, and the prompt flow. It returns JSON only — no HTML rendering or templating.

The front end never talks to CKAI or the policy store directly; it only calls the backend's API and renders the JSON it gets back.

```text
                    TypeScript SPA (front end)
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
             Physician tab                 Nurse tab
                    |                           |
                    +-------------+-------------+
                                  |
                         Selected experience
                                  |
                              User question
                                  |
                                  v
                   POST /api/query (JSON request)
                                  |
                                  v
                  Python backend (JSON API only)
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
               CKAI request              Policy retrieval
          (variant selected by                |
               experience)                    v
                    |                 Initial policy results
                    |                           |
                    v                           |
               CKAI answer --------------------+
                    |
                    v
         Optional refinement of policy
         retrieval using CKAI response
                    |
                    v
            Final policy results
                    |
                    v
         Experience-specific prompt flow
       (Python, Pydantic-based eval hooks)
                    |
                    v
          JSON response (answer + metadata)
                    |
                    v
              TypeScript SPA renders response
```

### Deployment shape (prototype)

For SME/user testing, the Python backend serves the built TypeScript static bundle from the same process — one deployable, one port. This keeps prototype hosting simple while the code stays cleanly separated (front end and backend are independent modules communicating only over HTTP/JSON), so splitting into two separately hosted services later is a small change, not a redesign.

Hosting environment itself is **TBD**.

## 3. Physician And Nurse Experiences

Two selectable experiences, each determining:

- CKAI variant (physician or nurse)
- Prompt flow (physician or nurse)
- Experience-specific presentation components where needed

Shared front-end and backend code is reused across both experiences; only the variant/prompt-flow selection and presentation differ.

## 4. Backend API Contract

The backend exposes a query endpoint (e.g. `POST /api/query`) that:

- Accepts the user question, the selected experience (physician/nurse), and — for multi-turn — prior conversation context
- Returns a JSON response containing the generated answer, and should include enough metadata (retrieved policy sources, CKAI answer, per-step data) to support later SME review and AI eval work

Multi-turn conversation is expected to be supported, contingent on how the CKAI API models conversation state (see [ckai_api.md](ckai_api.md) — pending).

Exact request/response schema is **TBD** pending the CKAI API contract and finalized retrieval output shape.

## 5. CKAI Integration

CKAI is called from the Python backend as part of initial question processing, in parallel with policy retrieval. The variant used depends on the selected experience (physician or nurse).

Once the CKAI answer returns, it can be used to refine retrieval against the exemplar policy dataset before final policy content is passed to the prompt flow.

Full integration details (base URL, auth, request/response schema, rate limits) are pending and tracked separately in [ckai_api.md](ckai_api.md).

## 6. Exemplar Policy Library

- The exemplar dataset is being collected now: approximately 40 policy files, split across two categories — medication and infection.
- Files are static documents; whether/how they get indexed is still being determined based on what's feasible for the prototype.
- Retrieval approach is intended to be hybrid (keyword + semantic), but specifics are not yet defined. Given the dataset size (~40 files), the actual implementation should stay as simple as practical rather than assuming heavy infrastructure (e.g. a dedicated vector database) up front.
- No real patient data is involved; more specific data-handling requirements will be defined later.

Indexing/retrieval approach is **TBD**.

## 7. Prompt Flows

- Physician and nurse experiences use separate prompt flows, built in Python.
- Each prompt flow receives the user question, the relevant CKAI answer, and retrieved policy content, and produces the final response.
- Conflicts between clinical guidance and hospital policy guidance (Key Risk #4 in the goals doc) are expected to be handled within the prompt flow itself, not as a separate architectural component.
- Pydantic is planned for AI eval observability around the prompt flow — the exact eval/logging shape is still open (see Section 8).

## 8. Testing, Logging, And Observability

For SME/user testing, session logs (question, CKAI answer, retrieved policy, final response) may be needed to support review and scoring. Tooling for this — including whether a tool like Ballpark is feasible for tracking behavioral data at prototype scale — is still being evaluated.

This is **TBD** and should be revisited once the retrieval and prompt-flow implementation is further along.

## 9. Local Development And Hosting

- The prototype should be buildable and runnable locally during development, with the front end and backend developed as independent modules.
- For hosting, the backend serves the built front-end bundle as a single deployable application (see Section 2), rather than deploying the front end and backend as separate services, unless hosting constraints (**TBD**) require otherwise.
- The same hosted application supports both experiences through the interface-level experience selector — there is no separate physician or nurse deployment.

## 10. Open Items

- CKAI API contract (auth, request/response schema, rate limits, multi-turn conversation model) — [ckai_api.md](ckai_api.md)
- Hosting environment
- Retrieval/indexing approach for the exemplar policy library
- Data-handling/security requirements (confirmed no real patient data, but specifics pending)
- Logging and eval tooling feasibility (e.g. Ballpark) for SME/user testing
- Front-end framework choice (React, Vue, etc.) — deferred, spec stays framework-agnostic
