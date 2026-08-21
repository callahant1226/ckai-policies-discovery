# Exemplar Policy Library: Storage & Indexing

> **Status: Proposed draft**
>
> Covers storage, normalization, and indexing of the exemplar policy dataset only. How retrieval scores/combines keyword and semantic results, and how the CKAI answer is used to refine retrieval, are separate concerns and remain **TBD** (see [technical_spec.md §6](technical_spec.md#6-exemplar-policy-library)) — this doc exists so storage isn't blocked on those decisions.

## Design Goal

~40 files, two categories (medication, infection), deliberately varied in source format and sub-topic. At this scale, the answer is to avoid infrastructure a larger dataset would justify (dedicated vector DB service, document store, search cluster) and instead use one file-based store that already supports both keyword and semantic lookup whenever retrieval is built.

## 1. Raw File Storage

Original files are kept as collected — no forced format conversion at collection time.

```text
data/policies/raw/medication/<slug>.<ext>
data/policies/raw/infection/<slug>.<ext>
data/policies/manifest.json
```

`manifest.json` — one entry per file, hand-maintained or appended by the ingestion script as files are added:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | Stable slug, matches filename. |
| `title` | string | |
| `category` | enum: `medication` \| `infection` | |
| `subtopics` | array of string | Free-form tags, e.g. `["dosing", "pediatric"]`. |
| `source_url` | string | Where it was collected from — needed for attribution and re-fetching. |
| `format` | enum: `pdf` \| `docx` \| `html` \| `txt` | |
| `date_collected` | date | |

## 2. Normalization / Ingestion Pipeline

A single ingestion script walks `data/policies/raw/`, and for each file:

1. Extracts plain text/markdown regardless of source format (`pypdf`/`pdfplumber` for PDF, `python-docx` for DOCX, BeautifulSoup for HTML, pass-through for `.txt`).
2. Chunks the extracted text — by heading/section where the source has structure, falling back to fixed-size chunks with overlap otherwise. Exact chunk size/overlap is a tuning question best answered once real files are in hand — **TBD**.
3. Writes chunks into the SQLite store (below), tagged with the parent doc's `id`, `category`, and `subtopics` from the manifest.

Expect this step, not the storage tech, to take the most iteration — policy PDFs commonly have multi-column layout, tables, and repeated headers/footers that plain text extraction mangles.

## 3. Index Storage: SQLite

One SQLite file (e.g. `data/policies/index.db`) holds everything retrieval will need:

| Table | Purpose |
| --- | --- |
| `docs` | One row per source file — mirrors `manifest.json`. |
| `chunks` | One row per chunk — `doc_id`, `section`, `text`, `embedding` (BLOB of floats). |
| `chunks_fts` | FTS5 virtual table over `chunks.text` — keyword/BM25-style search, built into SQLite, no extra dependency. |

Semantic search over the `embedding` column is brute-force cosine similarity computed in Python (numpy) at query time — at a few hundred chunks this is milliseconds, so no approximate-nearest-neighbor index is needed.

This gives one file, no server process, that already carries both the keyword and semantic substrate — fitting the "runs locally, deploys as one process" constraint in [technical_spec.md §2](technical_spec.md#2-architecture-overview) without committing to how the two are combined yet.

**Alternative considered:** Chroma (embedded, persists to disk, no server) — nicer vector API out of the box, but doesn't give keyword/FTS search for free, so hybrid retrieval would still need a second store alongside it. Not recommended for this scale.

## 4. Vectorization

Feasible and cheap at this scale — re-embedding all ~40 documents takes seconds. Recommend a local embedding model (e.g. `sentence-transformers`) rather than an external embedding API, so ingestion has no network/API-key dependency and can run fully offline. Final model choice is **TBD** pending a look at real policy text (medical terminology coverage matters more than general benchmark performance here).

## 5. Non-Goals For This Prototype

- No dedicated vector database service.
- No distributed or cloud object storage — local filesystem + one SQLite file is sufficient at 40 documents and re-buildable from `data/policies/raw/` at any time.
- No approximate-nearest-neighbor indexing.

## Open Items

- Chunking strategy (size/overlap, heading-aware vs. fixed) — needs real files to tune against.
- Embedding model choice.
- How keyword and semantic results are combined, and how the CKAI answer feeds back into retrieval — tracked in [technical_spec.md §6](technical_spec.md#6-exemplar-policy-library), not here.
