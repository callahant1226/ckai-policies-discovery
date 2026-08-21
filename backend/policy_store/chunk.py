"""Chunk extracted Sections into ChunkRecords.

Per specs/policy_storage.md §2 and Open Items: exact chunk size/overlap is
"a tuning question best answered once real files are in hand". These
defaults are a starting point, not a tuned value — pass --chunk-size /
--chunk-overlap to backend.policy_store.ingest to experiment once real
policy files are in data/policies/raw/.
"""

from __future__ import annotations

from .models import ChunkRecord, Section

DEFAULT_CHUNK_SIZE = 1000  # characters
DEFAULT_CHUNK_OVERLAP = 150  # characters


def chunk_sections(
    doc_id: str,
    sections: list[Section],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    index = 0
    for section in sections:
        for piece in _split_text(section.text, chunk_size, overlap):
            chunks.append(
                ChunkRecord(
                    id=f"{doc_id}::{index}",
                    doc_id=doc_id,
                    chunk_index=index,
                    section=section.title,
                    text=piece,
                )
            )
            index += 1
    return chunks


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Word-boundary-respecting fixed-size windows with character overlap.

    A whole section that already fits within chunk_size becomes one chunk
    (this is what gives heading-aware sources, e.g. docx/html, effectively
    heading-aware chunking) — only sections longer than chunk_size get split.
    """
    words = text.split()
    if not words:
        return []

    pieces: list[str] = []
    start = 0
    n = len(words)
    while start < n:
        end = start
        length = 0
        while end < n and (length == 0 or length < chunk_size):
            length += len(words[end]) + 1
            end += 1
        pieces.append(" ".join(words[start:end]))
        if end >= n:
            break

        overlap_len = 0
        back = end
        while back > start and overlap_len < overlap:
            back -= 1
            overlap_len += len(words[back]) + 1
        start = max(start + 1, back)
    return pieces
