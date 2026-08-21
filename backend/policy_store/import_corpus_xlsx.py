"""One-time import: the team's collection spreadsheet -> manifest.json.

    python -m backend.policy_store.import_corpus_xlsx /path/to/Clinical-Policy-Corpus-Manifest.xlsx

Run this once against the curation spreadsheet (its "Final Corpus" sheet).
After that, manifest.json is the canonical metadata store — edited by hand,
or extended via `ingest.py scan` as new files are dropped into
data/policies/raw/. This script is not part of the normal ingestion loop;
re-running it is safe (upserts by id) but not expected to be routine.

The spreadsheet records sources that have been verified (URL reachable,
metadata confirmed) but not necessarily downloaded into raw/ yet. Where the
source URL doesn't clearly resolve to a known file extension, the imported
entry gets `format="pending"` — `ingest.py build` already skips manifest
entries with no extractor or no file on disk (with a warning), so importing
ahead of collection is safe; fix up `format`/`raw_path` by hand once the file
is actually downloaded and its real type is known.
"""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .manifest import save_manifest, load_manifest
from .models import PolicyDoc
from .paths import MANIFEST_PATH

SHEET_NAME = "Final Corpus"
KNOWN_URL_EXTENSIONS = {"pdf", "docx", "doc", "html", "htm", "txt", "xlsx", "xls", "csv", "md", "json"}


def _clean(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "untitled"


def _infer_ext(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"\.([a-zA-Z0-9]{2,5})(?:$|\?)", url)
    ext = m.group(1).lower() if m else None
    return ext if ext in KNOWN_URL_EXTENSIONS else None


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def rows_to_docs(df: pd.DataFrame) -> list[PolicyDoc]:
    docs: list[PolicyDoc] = []
    seen_ids: set[str] = set()

    for _, row in df.iterrows():
        title = _clean(row.get("Document Title")) or "Untitled"
        category = (_clean(row.get("Category")) or "").lower()
        url = _clean(row.get("URL"))

        slug = _slugify(title)
        doc_id = slug
        suffix = 2
        while doc_id in seen_ids:
            doc_id = f"{slug}-{suffix}"
            suffix += 1
        seen_ids.add(doc_id)

        fmt = _infer_ext(url) or "pending"
        raw_path = f"{category}/{doc_id}.{fmt}"

        subtopic = _clean(row.get("Sub-topic"))
        format_number_str = _clean(row.get("Format #"))
        verified_open_raw = _clean(row.get("Verified Open (no login)"))

        row_id_str = _clean(row.get("ID"))

        docs.append(
            PolicyDoc(
                id=doc_id,
                title=title,
                category=category,
                subtopics=[subtopic] if subtopic else [],
                source_url=url,
                format=fmt,
                date_collected=None,
                raw_path=raw_path,
                source_row_id=int(row_id_str) if row_id_str else None,
                organisation=_clean(row.get("Organisation")),
                channel=_clean(row.get("Channel")),
                format_number=int(format_number_str) if format_number_str else None,
                format_name=_clean(row.get("Format Name")),
                doc_control_platform=_clean(row.get("Doc-Control Platform")),
                document_date=_clean(row.get("Document Date")),
                date_checked=_parse_iso_date(_clean(row.get("Date Checked"))),
                verified_open={"Y": True, "N": False}.get((verified_open_raw or "").upper()),
                notes=_clean(row.get("Notes")),
            )
        )
    return docs


def import_xlsx(
    xlsx_path: Path,
    manifest_path: Path = MANIFEST_PATH,
    sheet_name: str = SHEET_NAME,
) -> tuple[int, int, list[PolicyDoc]]:
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name, dtype=str)
    imported = rows_to_docs(df)

    existing = load_manifest(manifest_path)
    by_id = {d.id: d for d in existing}
    added = updated = 0
    for doc in imported:
        prior = by_id.get(doc.id)
        if prior is not None:
            updated += 1
            if prior.date_collected is not None:
                # A real file has already been found and reconciled for this
                # entry (see reconcile_raw_files.py) — don't clobber that with
                # the importer's provisional slug.<ext> guess.
                doc = doc.model_copy(
                    update={
                        "raw_path": prior.raw_path,
                        "format": prior.format,
                        "date_collected": prior.date_collected,
                    }
                )
        else:
            added += 1
        by_id[doc.id] = doc

    save_manifest(manifest_path, list(by_id.values()))
    return added, updated, imported


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("xlsx_path", type=Path)
    parser.add_argument("--sheet", default=SHEET_NAME)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args()

    added, updated, imported = import_xlsx(args.xlsx_path, manifest_path=args.manifest, sheet_name=args.sheet)
    print(f"Imported {len(imported)} rows from '{args.sheet}' -> {args.manifest} ({added} new, {updated} updated)")

    pending = [d for d in imported if d.format == "pending"]
    if pending:
        print(f"\n{len(pending)} entries have an unconfirmed file format (format=\"pending\"):")
        for d in pending:
            print(f"  {d.id}  ({d.source_url})")
        print("These are tracked but will be skipped by `ingest.py build` until downloaded and fixed up by hand.")


if __name__ == "__main__":
    main()
