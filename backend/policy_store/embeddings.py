"""Local embedding model wrapper.

Per specs/policy_storage.md §4: a local sentence-transformers model, not an
external embedding API, so ingestion has no network/API-key dependency.
Final model choice is TBD pending real policy text — medical-terminology
coverage matters more than general benchmark performance here. Swap
DEFAULT_MODEL_NAME (or pass --model to ingest.py) once real files are in hand.

Imports sentence-transformers lazily so callers that only need keyword
search (or `ingest.py build --no-embed`) don't need torch installed at all.
"""

from __future__ import annotations

import numpy as np

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_tls_fixed = False


def _fix_huggingface_tls_for_corporate_networks() -> None:
    """The first `SentenceTransformer(...)` call downloads model weights from
    huggingface.co (cached to disk after that). On the Elsevier network/VPN,
    Python's default cert bundle doesn't trust the corporate root CA in front
    of HTTPS — the same TLS issue proxy_server.py documents for CKAI — so that
    first download fails with a certificate error. `truststore` (optional
    dependency) makes Python's ssl module consult the OS trust store instead,
    which already trusts it (curl/the browser do). No-ops if unavailable or
    already applied, and doesn't affect any other TLS-verification behavior.
    """
    global _tls_fixed
    if _tls_fixed:
        return
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass
    _tls_fixed = True


class EmbeddingModel:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or DEFAULT_MODEL_NAME
        self._model = None

    def _load(self):
        if self._model is None:
            _fix_huggingface_tls_for_corporate_networks()
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        """Returns an (n, dim) float32 array, L2-normalized so a dot product
        between two rows is a cosine similarity."""
        model = self._load()
        vectors = model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)
