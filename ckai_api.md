# CKAI API

> **Status: To be populated**
>
> This document will describe the CKAI API contract used by the prototype. Details are pending access to the API documentation.

## Known So Far

- CKAI exposes two variants: physician and nurse.
- Endpoint reference (Swagger UI, requires VPN/auth to view): `https://rag.cert.knowledge.healthcare.elsevier.systems/docs#/default/query_query_post`

## To Be Filled In

- Base URL(s) for each environment (cert/staging, production)
- Authentication method (API key, OAuth, VPN-only access, etc.)
- Request schema for the query endpoint (fields, types, required vs optional, enums for variant selection)
- Response schema (answer text, citations/sources, metadata, streaming vs single response)
- Rate limits and error responses
- Whether/how multi-turn conversation state is passed (conversation ID, message history, etc.)
