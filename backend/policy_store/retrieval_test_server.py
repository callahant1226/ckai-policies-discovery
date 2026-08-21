"""Local test server for the "Initial retrieval" step (specs/intelligence_logic.md §4).

Serves retrieval_test.html and a GET /api/retrieve endpoint that runs a raw
question straight through keyword_search/semantic_search and returns the
retrieved policy chunks as JSON — no intent extraction, no CKAI call, no
CKAI-informed refinement (those are separate, later, still-open steps).

    python -m backend.policy_store.retrieval_test_server
Then open http://localhost:8020/

Mirrors proxy_server.py / local_api_test.html's pattern (throwaway static
page + minimal local server), but unlike that one this server isn't
stdlib-only — it imports backend.policy_store, which needs the packages in
requirements.txt.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import db as db_module
from .embeddings import EmbeddingModel
from .paths import DB_PATH, REPO_ROOT
from .search import keyword_search, semantic_search

STATIC_FILE = REPO_ROOT / "retrieval_test.html"


def make_handler(no_embed: bool, model_name: str | None) -> type[BaseHTTPRequestHandler]:
    state: dict = {"embedder": None}

    def get_embedder() -> EmbeddingModel | None:
        if no_embed:
            return None
        if state["embedder"] is None:
            state["embedder"] = EmbeddingModel(model_name=model_name)
        return state["embedder"]

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                self._serve_static()
            elif parsed.path == "/api/retrieve":
                self._handle_retrieve(parsed)
            else:
                self.send_response(404)
                self.end_headers()

        def _serve_static(self) -> None:
            if not STATIC_FILE.exists():
                self._send_json(500, {"error": f"{STATIC_FILE} not found"})
                return
            body = STATIC_FILE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _handle_retrieve(self, parsed) -> None:
            params = parse_qs(parsed.query)
            query = (params.get("query") or [""])[0].strip()
            category = (params.get("category") or [None])[0] or None
            try:
                top_k = int((params.get("top_k") or ["5"])[0])
            except ValueError:
                top_k = 5

            if not query:
                self._send_json(400, {"error": "missing 'query' parameter"})
                return
            if not DB_PATH.exists():
                self._send_json(
                    503,
                    {"error": f"{DB_PATH} does not exist yet — run `python -m backend.policy_store.ingest build` first"},
                )
                return

            conn = db_module.connect(DB_PATH)
            try:
                keyword_results = [
                    r.model_dump(mode="json") for r in keyword_search(conn, query, top_k=top_k, category=category)
                ]

                semantic_results = None
                semantic_error = None
                embedder = get_embedder()
                if embedder is not None:
                    try:
                        semantic_results = [
                            r.model_dump(mode="json")
                            for r in semantic_search(conn, embedder, query, top_k=top_k, category=category)
                        ]
                    except Exception as e:  # keep the endpoint alive even if embedding fails mid-session
                        semantic_error = str(e)
            finally:
                conn.close()

            self._send_json(
                200,
                {
                    "query": query,
                    "top_k": top_k,
                    "category": category,
                    "keyword": keyword_results,
                    "semantic": semantic_results,
                    "semantic_error": semantic_error,
                },
            )

        def log_message(self, fmt: str, *args) -> None:
            print(f"[retrieval_test_server] {self.address_string()} - {fmt % args}")

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--no-embed", action="store_true", help="Skip semantic search (index built with --no-embed)")
    parser.add_argument("--model", default=None, help="sentence-transformers model name")
    args = parser.parse_args()

    handler = make_handler(no_embed=args.no_embed, model_name=args.model)
    server = ThreadingHTTPServer(("localhost", args.port), handler)
    print(f"Retrieval test server listening on http://localhost:{args.port}")
    if args.no_embed:
        print("(--no-embed: keyword search only)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
