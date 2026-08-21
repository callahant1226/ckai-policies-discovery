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
| `format` | string, e.g. `pdf`, `docx`, `doc`, `xlsx`, `xls`, `csv`, `html`, `txt`, `md`, `json`, or `pending` | Open-ended, not a fixed enum — the real dataset mixes more formats than the four originally scoped here, and some are still TBD (see `backend/policy_store/extract.py`); `ingest.py scan` records whatever extension it finds, `build` skips (with a warning) any format that doesn't have an extractor yet. `pending` marks a source whose actual file type isn't confirmed yet (imported from a URL, not yet downloaded) — see `import_corpus_xlsx.py` below. |
| `date_collected` | date | When the raw file was actually saved into `data/policies/raw/` — null until then. Distinct from `date_checked` below. |

### 1.1 Curation/provenance fields

The team's collection process (tracked outside this repo in a spreadsheet, `Clinical-Policy-Corpus-Manifest.xlsx`, imported via `backend/policy_store/import_corpus_xlsx.py`) verifies and records more per-document metadata than retrieval itself needs. Rather than keep that spreadsheet as a second, divergent source of truth once entries are imported, `PolicyDoc` carries the extra fields directly — not consumed by extract/chunk/index, kept for attribution and re-verification:

| Field | Type | Notes |
| --- | --- | --- |
| `organisation` | string | Source health system, e.g. `"OHSU"`. |
| `channel` | string | Collection channel (the spreadsheet's own taxonomy for *how* it was found, e.g. public PolicyStat tenant vs. direct site search). |
| `format_number` / `format_name` | int / string | A content-type taxonomy (narrative policy, procedural checklist, order set, ...) — **not** the file-extension `format` field above; a `format_number` of 3 (checklist) can equally be a `.pdf` or `.docx` file. |
| `doc_control_platform` | string | e.g. `"PolicyStat"`, `"None (native)"`. |
| `document_date` | string | The source document's own date, as reported — kept as free text since real values are inconsistent (e.g. `"not dated on face"`), not a parseable date. |
| `date_checked` | date | Last confirmed `source_url` was reachable without login. |
| `verified_open` | bool | Whether `source_url` was confirmed publicly reachable, no login required. |
| `notes` | string | Free-text curation notes. |

## 2. Normalization / Ingestion Pipeline

**Implemented** in `backend/policy_store/` (`ingest.py` is the CLI entry point: `scan` discovers new raw files and appends skeleton manifest entries, `build` (re)creates `index.db` from the manifest).

A single ingestion script walks `data/policies/raw/`, and for each file:

1. Extracts plain text, heading-aware where the format supports it (`pdfplumber` for PDF page-by-page; `python-docx` for DOCX, splitting on heading styles; `.doc` via a LibreOffice `soffice --headless` conversion to `.docx` first; BeautifulSoup for HTML, splitting on `h1`–`h6`; pass-through for `.txt`/`.md` — `.md` splits on `#` headings; `pandas`/`openpyxl`/`xlrd` for `.xlsx`/`.xls`, one section per sheet; `pandas` for `.csv`; `.json` flattened to `path: value` lines). A format with no extractor yet is skipped with a warning rather than failing the whole run — see `backend/policy_store/extract.py`.
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

## Known Environment Limitations

**Resolved (2026-08):** the original concern here was that the dev machine only had Python 3.14 installed and `torch` (a `sentence-transformers` dependency) often lags new CPython releases by months. Checked again once real files were in hand: `torch==2.13.0` installs and imports fine on Python 3.14 — no action needed. `ingest.py build --no-embed` (keyword/FTS5 only, no torch) remains available as a fallback if a *future* environment hits this.

**TLS / model download, on the Elsevier network or VPN:** the first `ingest.py build` (or anything constructing an `EmbeddingModel`) downloads model weights from huggingface.co, and Python's default cert bundle doesn't trust whatever root CA the network puts in front of HTTPS — the exact same issue [proxy_server.py](../proxy_server.py) documents for calling CKAI. `backend/policy_store/embeddings.py` works around it the more robust way that file's own comment recommends: the `truststore` package (in `requirements.txt`), which makes Python's `ssl` module consult the OS trust store — already trusted by curl/the browser — instead of disabling verification outright. Confirmed working. After the first successful download the model is cached to disk (`~/.cache/huggingface/`), so this only matters once per machine.
