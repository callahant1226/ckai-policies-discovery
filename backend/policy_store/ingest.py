"""CLI: scan data/policies/raw/ into the manifest, then build the SQLite index.

    python -m backend.policy_store.ingest scan     # discover new raw files
    python -m backend.policy_store.ingest build    # (re)build index.db from the manifest
    python -m backend.policy_store.ingest all       # scan, then build
    python -m backend.policy_store.ingest search "some question"

`build` always does a full rebuild (drop + re-insert everything) — per
specs/policy_storage.md, re-embedding ~40 docs takes seconds, so there's no
need for incremental update tracking at this scale.
"""

from __future__ import annotations

import argparse

from . import db as db_module
from .chunk import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, chunk_sections
from .embeddings import EmbeddingModel
from .extract import UnsupportedFormatError, extract_sections
from .manifest import load_manifest, save_manifest, scan_raw_dir
from .paths import DB_PATH, MANIFEST_PATH, RAW_DIR
from .search import keyword_search, semantic_search


def cmd_scan(args: argparse.Namespace) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    new_docs = scan_raw_dir(RAW_DIR, manifest)
    if not new_docs:
        print(f"No new files found under {RAW_DIR}")
        return
    manifest.extend(new_docs)
    save_manifest(MANIFEST_PATH, manifest)
    print(f"Added {len(new_docs)} skeleton manifest entries to {MANIFEST_PATH}")
    print("Fill in title / subtopics / source_url by hand:")
    for d in new_docs:
        print(f"  {d.id}  ({d.raw_path}, format={d.format})")


def cmd_build(args: argparse.Namespace) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    if not manifest:
        print(f"{MANIFEST_PATH} is empty — run `scan` first, or add entries by hand.")
        return

    embedder = None if args.no_embed else EmbeddingModel(model_name=args.model)

    conn = db_module.connect(DB_PATH)
    db_module.init_schema(conn)
    db_module.clear_all(conn)

    total_chunks = 0
    skipped: list[str] = []
    for doc in manifest:
        file_path = RAW_DIR / doc.raw_path
        if not file_path.exists():
            print(f"  SKIP {doc.id}: raw file missing at {file_path}")
            skipped.append(doc.id)
            continue

        try:
            sections = extract_sections(file_path, doc.format)
        except UnsupportedFormatError as e:
            print(f"  SKIP {doc.id}: {e}")
            skipped.append(doc.id)
            continue

        chunks = chunk_sections(doc.id, sections, chunk_size=args.chunk_size, overlap=args.chunk_overlap)
        if not chunks:
            print(f"  SKIP {doc.id}: no text extracted")
            skipped.append(doc.id)
            continue

        embeddings = embedder.embed([c.text for c in chunks]) if embedder else [None] * len(chunks)

        db_module.insert_doc(conn, doc)
        for chunk, vec in zip(chunks, embeddings):
            db_module.insert_chunk(conn, chunk, vec, embedder.model_name if embedder else None)
        total_chunks += len(chunks)
        print(f"  OK {doc.id}: {len(chunks)} chunks")

    conn.commit()
    result = db_module.stats(conn)
    conn.close()

    print(f"\nIndexed {result['docs']} docs, {result['chunks']} chunks -> {DB_PATH}")
    if embedder is None:
        print("(--no-embed: keyword/FTS search only, no embeddings stored)")
    if skipped:
        print(f"Skipped {len(skipped)} manifest entries: {', '.join(skipped)}")


def cmd_all(args: argparse.Namespace) -> None:
    cmd_scan(args)
    cmd_build(args)


def cmd_search(args: argparse.Namespace) -> None:
    conn = db_module.connect(DB_PATH)
    if args.method in ("keyword", "both"):
        print("-- keyword --")
        for r in keyword_search(conn, args.query, top_k=args.top_k, category=args.category):
            print(f"[{r.score:.2f}] {r.doc_title} ({r.section or '-'}): {r.text[:120]!r}")
    if args.method in ("semantic", "both"):
        print("-- semantic --")
        embedder = EmbeddingModel(model_name=args.model)
        for r in semantic_search(conn, embedder, args.query, top_k=args.top_k, category=args.category):
            print(f"[{r.score:.2f}] {r.doc_title} ({r.section or '-'}): {r.text[:120]!r}")
    conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Policy library ingestion: scan raw files into the manifest, then build the SQLite index."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="Discover new files under data/policies/raw/, append skeleton manifest entries").set_defaults(
        func=cmd_scan
    )

    p_build = sub.add_parser("build", help="Rebuild index.db from the current manifest + raw files")
    p_build.add_argument("--model", default=None, help="sentence-transformers model name")
    p_build.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    p_build.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    p_build.add_argument(
        "--no-embed", action="store_true", help="Skip embedding — FTS keyword search only"
    )
    p_build.set_defaults(func=cmd_build)

    p_all = sub.add_parser("all", help="scan, then build")
    p_all.add_argument("--model", default=None)
    p_all.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    p_all.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    p_all.add_argument("--no-embed", action="store_true")
    p_all.set_defaults(func=cmd_all)

    p_search = sub.add_parser("search", help="Quick manual query against index.db (not the real retrieval layer)")
    p_search.add_argument("query")
    p_search.add_argument("--method", choices=["keyword", "semantic", "both"], default="both")
    p_search.add_argument("--top-k", type=int, default=5)
    p_search.add_argument("--category", choices=["medication", "infection"], default=None)
    p_search.add_argument("--model", default=None)
    p_search.set_defaults(func=cmd_search)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
