"""Keyword (FTS5/BM25) and semantic (brute-force cosine) search primitives.

These are index-verification primitives, not the hybrid retrieval layer —
how the two are scored/combined, and how a CKAI answer refines retrieval,
is explicitly TBD in specs/technical_spec.md §6 / policy_storage.md and
belongs in the intelligence_logic pipeline, not here.
"""

from __future__ import annotations

import re
import sqlite3

import numpy as np

from .db import fetch_chunk_embeddings
from .embeddings import EmbeddingModel
from .models import SearchResult

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

# Small, deliberately generic stopword list — dropped from the FTS query so a
# natural question isn't dominated by words like "the"/"what" that appear in
# nearly every chunk. Not a linguistic tokenizer; just enough to keep keyword
# search useful for real questions instead of exact title-text matches.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "by", "can", "do", "does",
    "for", "from", "get", "give", "giving", "how", "i", "if", "in", "into", "is",
    "it", "its", "need", "of", "on", "or", "our", "should", "that", "the", "their",
    "there", "this", "to", "us", "was", "we", "what", "when", "where", "which",
    "who", "why", "will", "with", "you", "your",
}


def _build_fts_query(text: str) -> str | None:
    """Turn a raw natural-language query into a safe FTS5 MATCH expression.

    FTS5's MATCH argument is itself a small query language (phrase, column,
    and boolean operators) — punctuation in a real question (apostrophes,
    hyphens, question marks) can trip a syntax error rather than just fail to
    match. Each surviving word is individually double-quoted (neutralizing
    any operator meaning) and OR-joined — FTS5 defaults to requiring every
    bare term to match, which fails almost every natural-language question.
    Returns None if the query has no word characters at all.
    """
    tokens = _TOKEN_RE.findall(text.lower())
    keywords = [t for t in tokens if t not in _STOPWORDS] or tokens
    if not keywords:
        return None
    return " OR ".join(f'"{t}"' for t in keywords)


def keyword_search(
    conn: sqlite3.Connection,
    query: str,
    top_k: int = 10,
    category: str | None = None,
) -> list[SearchResult]:
    fts_query = _build_fts_query(query)
    if fts_query is None:
        return []

    sql = (
        "SELECT chunks_fts.chunk_id, chunks_fts.doc_id, c.section, c.text, "
        "bm25(chunks_fts) AS rank, d.title, d.category "
        "FROM chunks_fts "
        "JOIN chunks c ON c.id = chunks_fts.chunk_id "
        "JOIN docs d ON d.id = c.doc_id "
        "WHERE chunks_fts MATCH ?"
    )
    params: list = [fts_query]
    if category:
        sql += " AND d.category = ?"
        params.append(category)
    sql += " ORDER BY rank LIMIT ?"
    params.append(top_k)

    rows = conn.execute(sql, params).fetchall()
    return [
        SearchResult(
            chunk_id=r[0],
            doc_id=r[1],
            section=r[2],
            text=r[3],
            score=-r[4],  # sqlite fts5 bm25(): lower (more negative) = more relevant
            doc_title=r[5],
            category=r[6],
            method="keyword",
        )
        for r in rows
    ]


def semantic_search(
    conn: sqlite3.Connection,
    embedder: EmbeddingModel,
    query: str,
    top_k: int = 10,
    category: str | None = None,
) -> list[SearchResult]:
    rows = fetch_chunk_embeddings(conn, category=category)
    if not rows:
        return []

    query_vec = embedder.embed([query])[0]
    matrix = np.stack([np.frombuffer(r[4], dtype=np.float32) for r in rows])
    scores = matrix @ query_vec
    order = np.argsort(-scores)[:top_k]

    return [
        SearchResult(
            chunk_id=rows[i][0],
            doc_id=rows[i][1],
            section=rows[i][2],
            text=rows[i][3],
            score=float(scores[i]),
            doc_title=rows[i][5],
            category=rows[i][6],
            method="semantic",
        )
        for i in order
    ]
