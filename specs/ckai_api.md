# CKAI API

> **Status: Confirmed from live OpenAPI schema (cert) + internal Confluence workflow docs**
>
> Source of the schema: `openapi.json` fetched from `https://rag.cert.knowledge.healthcare.elsevier.systems/openapi.json` (saved in this repo). Workflow details from Confluence: [Nursing AI Workflow](https://elsevier.atlassian.net/wiki/spaces/HMOPEV/pages/119602430084529/Nursing+AI+Workflow+V1+-+Feb+2026+Eval) and [Logos (Physician) AI Workflow](https://elsevier.atlassian.net/wiki/spaces/arch/pages/119602791887058/Logos+AI+Workflow+-+4+10+26+Live+Production+Monitoring+Eval).

## Base URLs

| Environment | Base URL |
| --- | --- |
| Dev | `https://rag.dev.knowledge.healthcare.elsevier.systems` |
| Cert | `https://rag.cert.knowledge.healthcare.elsevier.systems` |
| Prod | Not yet confirmed — **TBD** |

Swagger UI: append `/docs`. OpenAPI schema: append `/openapi.json`.

## Authentication / Network Access

- No API key or bearer token is required by the deployed schema (`components.securitySchemes` is empty in the OpenAPI spec).
- Access is gated at the network level: the API is only reachable from inside the Elsevier network/VPN. This is a hosting constraint for our prototype's backend, not a credential to manage — see the technical spec's hosting section.
- Note: a separate, unrelated setup exists where CKAI engineers run the full `ckai-ai-service` backend locally with Keycloak/bearer-token auth for internal feature demos. That is **not** relevant to this prototype — we call the already-hosted cert/dev API as a client, we don't run CKAI itself.

## Relevant Endpoints

| Endpoint | Method | Experience | Streaming |
| --- | --- | --- | --- |
| `/query` | POST | Physician ("Logos") | No |
| `/streaming/query` | POST | Physician ("Logos") | Yes |
| `/nursing/query` | POST | Nurse | No |
| `/nursing/streaming` | POST | Nurse | Yes |

All four take the same request schema (`RAGRequest`, below). The API also exposes other endpoints (`/deep-research`, `/api/v2/differential-diagnosis`, `/chunks/query`, `/reading-assistant`, etc.) that are not relevant to this prototype.

## Request Schema — `RAGRequest`

| Field | Type | Notes |
| --- | --- | --- |
| `query` | string, **required** | The user's question. |
| `query_id` | string \| null | Optional client-supplied ID for tracing. |
| `enable_request_tracing` | boolean, default `false` | Enables request tracing for the call. |
| `consumer_type` | enum: `end_customer` \| `reseller`, default `end_customer` | Leave as default. |
| `historical_messages` | array of `{question: string, answer: string}` \| null | **This is how multi-turn works** — the client resends prior Q&A pairs on each call. There is no server-side session/conversation ID in this schema. The workflow docs refer to this concept as `conversation_history`; if empty/omitted, the request is treated as an initial question, otherwise as a follow-up (triggers follow-up-question rewriting internally). Worth confirming the exact field name behaves as documented once we can hit the API live. |
| `orchestration_config` | object | Large nested config controlling retrieval, LLM params, reranking, hybrid search, guardrails, and built-in eval metrics. Has a full default already (see below) — for physician endpoints the defaults appear usable as-is; for **nursing endpoints, a specific override is mandatory** (see below). |
| `guidelines_branch_source` | string \| null | Optional alias into `orchestration_config.guidelines_branch_source`. |
| `personalization_setting` | enum: `All` \| `Pediatric` \| `Adult`, default `All` | Patient age-group personalization. Nursing workflow doc explicitly recommends `All` — setting it to `Adult`/`Pediatric` triggers an extra `query_augmentation` LLM call. |

### Physician (`/query`, `/streaming/query`)

No mandatory override is documented — the `orchestration_config` default embedded in the schema (hybrid search enabled, query expansion on, HyDE on, `max_tokens: 100000`, `model_id: GPT_54`, etc.) appears to be the intended physician configuration. Confirm with the CKAI/Logos team before relying on this for the prototype, since no "you must use this" doc was found for the physician side (unlike nursing).

### Nurse (`/nursing/query`, `/nursing/streaming`)

**Must** use this exact `orchestration_config` (per the Nursing AI Workflow doc — deviating is explicitly called out as unsupported):

```json
{
  "query": "<the user's question>",
  "orchestration_config": {
    "retrieve_request": {
      "enabled": true,
      "filter_on_concepts": false,
      "vector_request": {
        "k": 30,
        "min_chunk_length": 5,
        "number_of_results_to_provide": 30,
        "number_of_results_to_try": 20,
        "query_text": "",
        "show_vector": false,
        "status_code": 0
      }
    },
    "llm_request": {
      "max_tokens": 100000,
      "model_id": "GPT_41",
      "send_prompt": true,
      "status_code": 0,
      "use_guardrails": true
    },
    "query_language_translation": false,
    "hybrid_search": { "enabled": false, "filter_on_concepts": false },
    "query_interpretation": true,
    "query_expansion": false,
    "rerank_main": 0,
    "rerank_sub": 0,
    "rerank_final": 0,
    "hyde": { "enabled": false, "filter_on_concepts": false },
    "max_reranked_results": 40,
    "max_final_results": 20,
    "citation_validation": true,
    "assess": false,
    "assess_metrics": ["completeness", "comprehension", "accuracy", "faithfulness", "chunk_relevancy", "response_relevancy"]
  },
  "personalization_setting": "All",
  "ml_flow": false
}
```

Note: `ml_flow` appears in this example but is **not** a declared field in the `RAGRequest` schema from `openapi.json` — either the schema allows extra properties, or this is stale/optional. Worth confirming when we can call the API live.

Example curl (nursing streaming, dev):

```bash
curl -X 'POST' \
  'https://rag.dev.knowledge.healthcare.elsevier.systems/nursing/streaming' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{ ... same body as above ... }'
```

(Swap `dev` for `cert` to hit the cert environment.)

## Response Schema

The OpenAPI spec types the 200 response as a generic object (`additionalProperties: true`) — it is **not strongly typed**, so the exact response envelope isn't documented in the schema itself. From the nursing workflow doc's example output, the generated answer is markdown-ish text with:

- Up to ~7 bullet points, formatted as `- **subtitle** - text [citation markers]`
- Inline citation markers like `[1a, 2a]` that map to a references list (built by the `node_references_reorder_aggregate` step)
- For the nursing case specifically, note the workflow doc's own caveat: the LLM sometimes emits an em dash (–) instead of a hyphen after the subtitle, which can cause formatting/double-subtitle issues in ~5% of responses — the front end should tolerate this.

### Confirmed from a live cert `/query` call (physician)

Captured via `local_api_test.html` + `proxy_server.py`. Top-level keys on a successful response:

| Field | Contents |
| --- | --- |
| `llm_response.output_text` | **The generated answer** — markdown-ish text with bullet points and inline citation markers like `[1a, 2a]`. |
| `llm_response.input_text` | The full prompt sent to the LLM (query + all injected citation content) — large, useful for debugging, not for display. |
| `references_with_citation_indexes` | Object keyed by citation number (`"1"`, `"2"`, …) → array of `{chunk_index, original_index, result}`, where `result` is a full retrieval hit (see `retrieve_response.results` shape below). This is what `[1a, 2a]` markers resolve to. |
| `retrieve_response.results` | Raw ranked retrieval hits: `{_id, _score, _source: {document_title, chunk_text, authors, publication_date, content_type, bread_crumbs, ...}}`. Large (48 hits in our test) — this is retrieval detail, not something to show directly. |
| `citation_validation` | Per-claim grounding check: `{claim, rating: "grounded"/other, modified_claim, final_claim}` keyed by claim index. |
| `additional_information` | Extra markdown-formatted context the model generated beyond the main answer. |
| `follow_up_questions` | Plain text list of suggested follow-up questions. |
| `guardrails_output.status` | `"NO_ERROR"` on a normal response. Not yet seen what a triggered-guardrail response looks like — likely a different status value, but the exact enum and whether `output_text` is still populated in that case is unconfirmed. |
| `conversation_history` | Echoes back `[{question, answer}]` for this turn — confirms the shape to send in `historical_messages` for follow-ups (see multi-turn note above). |
| `deidentification_output`, `interpreted_query`, `hyde_answer`, `primary_concept_tag`, `language`, `functional_classification`, `retrieve_request` | Internal pipeline diagnostics, not needed for the prototype's UI. |

**Still open:** we only have a physician (`/query`) example so far. Nursing (`/nursing/query`) likely matches this shape (same `RAGRequest`/response family) but hasn't been captured live yet — worth confirming, especially since the nursing workflow doc describes a different bullet-count/formatting convention. Also still don't have an example of a guardrail-triggered response.

## Guardrails / Error Handling

Guardrails run as an async background task (physician side runs it in parallel with the whole graph; description of nursing side implies similar). When guardrails reject a request, the front end must handle and display specific messages — these come from the platform, not something we generate ourselves:

- `Sorry, your question seems to be outside the scope of ClinicalKey AI. If at first you don't succeed, try again!`
- `Sorry, ClinicalKey AI does not currently support calculation.`

The prototype's response-handling logic should check for/pass through these guardrail cases distinctly from a normal answer.

## Open Items

- Production base URL
- Nursing (`/nursing/query`) response shape — only physician has been captured live so far
- What a guardrail-triggered response actually looks like (status value, whether `output_text` is still populated)
- Whether `historical_messages` is truly the multi-turn mechanism in practice (vs. some other conversation-state field) — confirm with a live follow-up call
- Whether the physician (`/query`, `/streaming/query`) default `orchestration_config` is actually the intended production config, or whether there's an equivalent "must use this" doc we haven't found yet
- The `ml_flow` field discrepancy noted above
