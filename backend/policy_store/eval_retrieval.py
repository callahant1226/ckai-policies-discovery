"""Retrieval smoke test: does the index surface the right policy document
for a realistic clinician question?

Deliberately narrow in scope — this only exercises the "Initial retrieval"
step from specs/intelligence_logic.md §4 (deterministic, no LLM call): a raw
user question straight into keyword_search and semantic_search. No intent
extraction, no CKAI-informed refinement — those are separate, later steps
and still open per specs/technical_spec.md §6 / policy_storage.md.

    python -m backend.policy_store.eval_retrieval
    python -m backend.policy_store.eval_retrieval --no-embed   # keyword-only index
    python -m backend.policy_store.eval_retrieval --queries path/to/other_set.json

The test set (data/policies/eval/retrieval_queries.json) is hand-written,
paraphrased away from each document's actual title/section text on purpose
— matching on paraphrase is a real test of retrieval quality; matching on
verbatim title words would trivially pass regardless of chunking/embedding
quality. Each entry lists expected_doc_ids (usually one; a couple of queries
allow either of two equally-valid documents) — a "hit" means at least one
expected id appears in that method's top-k, not that it ranks first.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import db as db_module
from .embeddings import EmbeddingModel
from .paths import DB_PATH, REPO_ROOT
from .search import keyword_search, semantic_search

DEFAULT_QUERIES_PATH = REPO_ROOT / "data" / "policies" / "eval" / "retrieval_queries.json"


def load_queries(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def run_eval(
    queries_path: Path = DEFAULT_QUERIES_PATH,
    top_k: int = 5,
    model: str | None = None,
    no_embed: bool = False,
    db_path: Path = DB_PATH,
) -> None:
    queries = load_queries(queries_path)
    conn = db_module.connect(db_path)
    embedder = None if no_embed else EmbeddingModel(model_name=model)

    keyword_hits = 0
    semantic_hits = 0
    for q in queries:
        query = q["query"]
        expected = set(q["expected_doc_ids"])

        kw_results = keyword_search(conn, query, top_k=top_k)
        kw_doc_ids = {r.doc_id for r in kw_results}
        kw_hit = bool(expected & kw_doc_ids)
        keyword_hits += kw_hit

        sem_hit = None
        sem_doc_ids: set[str] = set()
        if embedder is not None:
            sem_results = semantic_search(conn, embedder, query, top_k=top_k)
            sem_doc_ids = {r.doc_id for r in sem_results}
            sem_hit = bool(expected & sem_doc_ids)
            semantic_hits += sem_hit

        status_kw = "HIT" if kw_hit else "MISS"
        status_sem = "HIT" if sem_hit else ("MISS" if sem_hit is False else "SKIPPED")
        print(f"[keyword {status_kw:5} | semantic {status_sem:7}] {query!r}")
        print(f"    expected:      {sorted(expected)}")
        print(f"    keyword top-{top_k}:  {sorted(kw_doc_ids)}")
        if embedder is not None:
            print(f"    semantic top-{top_k}: {sorted(sem_doc_ids)}")

    conn.close()
    n = len(queries)
    print(f"\nkeyword hit rate:  {keyword_hits}/{n}")
    if embedder is not None:
        print(f"semantic hit rate: {semantic_hits}/{n}")
    else:
        print("semantic search skipped (--no-embed)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES_PATH)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--model", default=None, help="sentence-transformers model name")
    parser.add_argument("--no-embed", action="store_true", help="Skip semantic search (index was built with --no-embed)")
    args = parser.parse_args()
    run_eval(args.queries, top_k=args.top_k, model=args.model, no_embed=args.no_embed)


if __name__ == "__main__":
    main()
