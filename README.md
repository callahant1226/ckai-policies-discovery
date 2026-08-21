# ckai-policies-discovery

Working repo for CS Discovery team artifacts, version-tracked drafts, reviews, and iterations of strategic and design work.

Current focus: a prototype that presents hospital institutional policy content alongside CKAI (ClinicalKey AI) answers, for physician and nurse experiences, to test with SMEs and users.

## Goals

Assess whether combining hospital policy content with CKAI's answer is useful, accurate, and understandable for physicians and nurses — and surface where that combination breaks down (policy accuracy, user trust, policy content extraction, and conflicts between clinical vs. policy guidance).

Full detail: [specs/goals_and_aims.md](specs/goals_and_aims.md)

## Repository Structure

```
specs/                        Planning and design documents
  goals_and_aims.md              Why this prototype exists, primary goal, key risks
  technical_spec.md              Proposed architecture (v5): TypeScript front end + Python backend, CKAI integration, open items
  ckai_api.md                    CKAI API contract: endpoints, request/response schema, auth, guardrails
  discovery-team-framework.md    Discovery team working framework

openapi.json                   CKAI's OpenAPI schema, captured live from the cert environment
local_api_test.html            Throwaway browser test page for the CKAI API (physician/nurse switchable)
proxy_server.py                Local CORS proxy so the test page can call CKAI from a browser
README.md                      This file
```

## Current Status

- **Architecture drafted.** TypeScript front end (framework TBD) as a pure client, Python backend as a JSON API doing the CKAI call, policy retrieval, and prompt flow — see [specs/technical_spec.md](specs/technical_spec.md).
- **CKAI API confirmed and documented.** No API key required; access is gated by being on the Elsevier network/VPN. Full endpoint list, request schema, the mandatory nursing `orchestration_config`, and a real captured response shape are in [specs/ckai_api.md](specs/ckai_api.md).
- **End-to-end smoke test working.** [local_api_test.html](local_api_test.html) calls the real cert CKAI API (via [proxy_server.py](proxy_server.py), which works around both a CORS restriction and a local TLS trust issue) and renders the actual generated answer, with the full raw JSON available in a collapsed accordion for debugging.
- **Not yet started:** the real Python backend, the real front end, and the exemplar policy retrieval pipeline (~40 policy files across medication and infection categories, still being collected).

## Running The Test Harness

1. Start the local proxy (stdlib only, no install needed):
   ```bash
   python3 proxy_server.py
   ```
2. Serve this folder and open `local_api_test.html` in a browser, e.g.:
   ```bash
   python3 -m http.server 5500
   ```
   then visit `http://localhost:5500/local_api_test.html`.
3. You must be on the Elsevier network/VPN. Switch the Physician/Nurse tabs and ask a question — the generated answer renders directly, with the full JSON response collapsed below it.

## Open Items

See [specs/technical_spec.md § Open Items](specs/technical_spec.md) for the full list, including hosting environment, retrieval/indexing approach, data-handling requirements, and logging/eval tooling. Notable CKAI-specific gaps are tracked in [specs/ckai_api.md § Open Items](specs/ckai_api.md).
