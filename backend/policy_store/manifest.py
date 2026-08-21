"""Load/save data/policies/manifest.json and discover new raw files.

Per specs/policy_storage.md: the manifest is "hand-maintained or appended by
the ingestion script as files are added" — `scan_raw_dir` finds files under
raw/ that aren't in the manifest yet and returns skeleton entries (id/format/
category inferred from the file itself; title/subtopics/source_url left for
a human to fill in).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import PolicyDoc

FORMAT_BY_EXT = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "doc",
    ".html": "html",
    ".htm": "html",
    ".txt": "txt",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".csv": "csv",
    ".md": "md",
    ".markdown": "md",
    ".json": "json",
}

# Formats extract.py actually has a working extractor for. Kept separate from
# FORMAT_BY_EXT so a file with an extension we've never seen still gets picked
# up by scan_raw_dir and recorded in the manifest (format = the raw extension)
# instead of being silently ignored — `build` then warns and skips it until an
# extractor for that format is added.
KNOWN_FORMATS = frozenset(FORMAT_BY_EXT.values())

VALID_CATEGORIES = {"medication", "infection"}


def _infer_format(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    return FORMAT_BY_EXT.get(ext, ext.lstrip(".") or "unknown")


def load_manifest(path: Path) -> list[PolicyDoc]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    return [PolicyDoc(**entry) for entry in raw]


def save_manifest(path: Path, docs: list[PolicyDoc]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [json.loads(d.model_dump_json()) for d in docs]
    path.write_text(json.dumps(payload, indent=2) + "\n")


def scan_raw_dir(raw_dir: Path, manifest: list[PolicyDoc]) -> list[PolicyDoc]:
    """Return skeleton PolicyDoc entries for files under raw_dir not yet in manifest."""
    known_paths = {d.raw_path for d in manifest}
    new_docs: list[PolicyDoc] = []

    if not raw_dir.exists():
        return new_docs

    for category_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        category = category_dir.name
        if category not in VALID_CATEGORIES:
            continue
        for file_path in sorted(category_dir.iterdir()):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue
            rel_path = f"{category}/{file_path.name}"
            if rel_path in known_paths:
                continue
            fmt = _infer_format(file_path)
            slug = file_path.stem
            new_docs.append(
                PolicyDoc(
                    id=slug,
                    title=slug.replace("-", " ").replace("_", " ").title(),
                    category=category,
                    subtopics=[],
                    source_url=None,
                    format=fmt,
                    date_collected=date.today(),
                    raw_path=rel_path,
                )
            )
    return new_docs
