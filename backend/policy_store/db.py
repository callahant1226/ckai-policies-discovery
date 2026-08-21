"""SQLite index: docs + chunks + chunks_fts (FTS5), per specs/policy_storage.md §3.

One file, no server process. `chunks_fts` is a standalone FTS5 table (not
content-linked to `chunks`) so there's no rowid-sync trigger machinery to
maintain — fine at this scale since the whole index is rebuilt from
data/policies/raw/ on every `ingest.py build` run anyway.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

from .models import ChunkRecord, PolicyDoc

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('medication', 'infection')),
    subtopics TEXT NOT NULL DEFAULT '[]',
    source_url TEXT,
    format TEXT NOT NULL,
    date_collected TEXT,
    raw_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES docs(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    section TEXT,
    text TEXT NOT NULL,
    embedding BLOB,
    embedding_model TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    chunk_id UNINDEXED,
    doc_id UNINDEXED
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def clear_all(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM chunks_fts")
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM docs")


def insert_doc(conn: sqlite3.Connection, doc: PolicyDoc) -> None:
    conn.execute(
        """
        INSERT INTO docs (id, title, category, subtopics, source_url, format, date_collected, raw_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            category=excluded.category,
            subtopics=excluded.subtopics,
            source_url=excluded.source_url,
            format=excluded.format,
            date_collected=excluded.date_collected,
            raw_path=excluded.raw_path
        """,
        (
            doc.id,
            doc.title,
            doc.category,
            json.dumps(doc.subtopics),
            doc.source_url,
            doc.format,
            doc.date_collected.isoformat() if doc.date_collected else None,
            doc.raw_path,
        ),
    )


def insert_chunk(
    conn: sqlite3.Connection,
    chunk: ChunkRecord,
    embedding: np.ndarray | None,
    embedding_model: str | None,
) -> None:
    blob = embedding.astype(np.float32).tobytes() if embedding is not None else None
    conn.execute(
        """
        INSERT INTO chunks (id, doc_id, chunk_index, section, text, embedding, embedding_model)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (chunk.id, chunk.doc_id, chunk.chunk_index, chunk.section, chunk.text, blob, embedding_model),
    )
    conn.execute(
        "INSERT INTO chunks_fts (text, chunk_id, doc_id) VALUES (?, ?, ?)",
        (chunk.text, chunk.id, chunk.doc_id),
    )


def fetch_chunk_embeddings(conn: sqlite3.Connection, category: str | None = None) -> list[tuple]:
    """Rows of (chunk_id, doc_id, section, text, embedding_blob, doc_title, category)
    for every chunk that has an embedding — used by search.semantic_search."""
    sql = (
        "SELECT c.id, c.doc_id, c.section, c.text, c.embedding, d.title, d.category "
        "FROM chunks c JOIN docs d ON d.id = c.doc_id WHERE c.embedding IS NOT NULL"
    )
    params: list[str] = []
    if category:
        sql += " AND d.category = ?"
        params.append(category)
    return conn.execute(sql, params).fetchall()


def stats(conn: sqlite3.Connection) -> dict:
    n_docs = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    n_embedded = conn.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL").fetchone()[0]
    return {"docs": n_docs, "chunks": n_chunks, "chunks_with_embeddings": n_embedded}
