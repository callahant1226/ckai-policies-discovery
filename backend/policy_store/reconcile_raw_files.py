"""Match downloaded files under data/policies/raw/ to manifest.json entries
whose raw_path doesn't (yet) correspond to a real file.

`ingest.py scan` assumes files are already named `{id}.{ext}` — files
collected before their manifest entry existed, or named for a team's own
tracking convention (seen in practice: `{row_number}_{org-slug}_{title-slug}.{ext}`,
e.g. `03_providence_medication-double-check.pdf`), won't match that. This
script instead joins on the numeric prefix against each entry's
`source_row_id` (the spreadsheet row the entry was imported from — see
import_corpus_xlsx.py), which survives any filename/slug drift.

    python -m backend.policy_store.reconcile_raw_files

For each match it updates `raw_path`, `format` (from the file's actual
extension), and stamps `date_collected`. Files with no leading number, or
whose number doesn't match any manifest entry, are reported but left alone —
matching those needs a human, not a guess.
"""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from .manifest import FORMAT_BY_EXT, load_manifest, save_manifest
from .paths import MANIFEST_PATH, RAW_DIR

_LEADING_NUMBER_RE = re.compile(r"^0*(\d+)_")


def _infer_format(file_path: Path) -> str:
    return FORMAT_BY_EXT.get(file_path.suffix.lower(), file_path.suffix.lstrip(".").lower() or "unknown")


def reconcile(raw_dir: Path = RAW_DIR, manifest_path: Path = MANIFEST_PATH) -> None:
    manifest = load_manifest(manifest_path)
    by_row_id = {d.source_row_id: d for d in manifest if d.source_row_id is not None}

    matched: list[str] = []
    unmatched_files: list[str] = []
    already_ok: list[str] = []

    for category_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        category = category_dir.name
        for file_path in sorted(category_dir.iterdir()):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue

            m = _LEADING_NUMBER_RE.match(file_path.name)
            rel_path = f"{category}/{file_path.name}"
            if not m:
                # Might already be sitting at the exact raw_path a manifest
                # entry expects (the scan.py-style plain `{id}.{ext}` case).
                if any(d.raw_path == rel_path for d in manifest):
                    already_ok.append(rel_path)
                else:
                    unmatched_files.append(rel_path)
                continue

            row_id = int(m.group(1))
            doc = by_row_id.get(row_id)
            if doc is None:
                unmatched_files.append(f"{rel_path}  (no manifest entry with source_row_id={row_id})")
                continue

            if doc.category != category:
                unmatched_files.append(
                    f"{rel_path}  (source_row_id={row_id} matches '{doc.id}', but that entry's category is "
                    f"'{doc.category}', not '{category}' — check before reconciling)"
                )
                continue

            doc.raw_path = rel_path
            doc.format = _infer_format(file_path)
            doc.date_collected = date.today()
            matched.append(f"{doc.id}  <-  {rel_path}")

    save_manifest(manifest_path, manifest)

    still_missing = [d.id for d in manifest if not (raw_dir / d.raw_path).exists()]

    print(f"Reconciled {len(matched)} file(s):")
    for line in matched:
        print(f"  {line}")
    if already_ok:
        print(f"\n{len(already_ok)} file(s) already at their expected raw_path, unchanged.")
    if unmatched_files:
        print(f"\n{len(unmatched_files)} file(s) under {raw_dir} could not be matched to a manifest entry:")
        for line in unmatched_files:
            print(f"  {line}")
    if still_missing:
        print(f"\n{len(still_missing)} manifest entries still have no file on disk:")
        for doc_id in still_missing:
            print(f"  {doc_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args()
    reconcile(raw_dir=args.raw_dir, manifest_path=args.manifest)


if __name__ == "__main__":
    main()
