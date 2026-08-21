"""Extract plain text (as heading-aware Sections where the format supports it)
from each source format in the exemplar policy library.

Per specs/policy_storage.md §2: "Expect this step, not the storage tech, to
take the most iteration" — policy PDFs especially. Heavy per-format
dependencies are imported lazily so `import extract` stays cheap and a
missing optional dependency only breaks the format that needs it.
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import Section

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")


class UnsupportedFormatError(ValueError):
    """Raised when a manifest entry's format has no extractor yet.

    Not fatal to a whole ingestion run — callers (ingest.py) catch this per
    document, warn, and skip, since the manifest may list formats "we may
    understand only later" before an extractor for them is written.
    """


def extract_sections(path: Path, fmt: str) -> list[Section]:
    if fmt == "pdf":
        return _extract_pdf(path)
    if fmt == "docx":
        return _extract_docx(path)
    if fmt == "doc":
        return _extract_doc(path)
    if fmt == "html":
        return _extract_html(path)
    if fmt == "txt":
        return _extract_txt(path)
    if fmt in ("xlsx", "xls"):
        return _extract_excel(path)
    if fmt == "csv":
        return _extract_csv(path)
    if fmt == "md":
        return _extract_md(path)
    if fmt == "json":
        return _extract_json(path)
    raise UnsupportedFormatError(
        f"No extractor for format {fmt!r} (file: {path.name}). "
        "Add one in backend/policy_store/extract.py, or convert the file to "
        "a supported format and update its entry in manifest.json."
    )


def _extract_txt(path: Path) -> list[Section]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [Section(title=None, text=text)] if text.strip() else []


def _extract_pdf(path: Path) -> list[Section]:
    import pdfplumber

    sections: list[Section] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                sections.append(Section(title=f"page {i}", text=text))
    return sections


def _extract_docx(path: Path) -> list[Section]:
    import docx

    document = docx.Document(str(path))
    sections: list[Section] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        if current_lines:
            sections.append(Section(title=current_title, text="\n".join(current_lines)))

    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style_name = para.style.name if para.style else ""
        if style_name and style_name.lower().startswith("heading"):
            flush()
            current_title = text
            current_lines = []
        else:
            current_lines.append(text)
    flush()
    return sections


def _extract_doc(path: Path) -> list[Section]:
    docx_path = _convert_doc_to_docx(path)
    return _extract_docx(docx_path)


def _convert_doc_to_docx(path: Path) -> Path:
    """Legacy binary .doc has no pure-Python reader; shell out to LibreOffice."""
    import shutil
    import subprocess
    import tempfile

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError(
            f"Cannot extract legacy .doc file '{path.name}': no 'soffice'/'libreoffice' "
            "found on PATH. Install LibreOffice, or convert the file to .docx by hand "
            "and update its raw_path/format in manifest.json."
        )
    out_dir = Path(tempfile.mkdtemp(prefix="policy_doc_convert_"))
    subprocess.run(
        [soffice, "--headless", "--convert-to", "docx", "--outdir", str(out_dir), str(path)],
        check=True,
        capture_output=True,
    )
    converted = out_dir / (path.stem + ".docx")
    if not converted.exists():
        raise RuntimeError(f"LibreOffice conversion of '{path.name}' did not produce a .docx file")
    return converted


def _extract_html(path: Path) -> list[Section]:
    from bs4 import BeautifulSoup, NavigableString, Tag

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    root = soup.body or soup

    sections: list[Section] = []
    current_title: str | None = None
    current_parts: list[str] = []

    def flush() -> None:
        text = "\n".join(p for p in current_parts if p.strip())
        if text.strip():
            sections.append(Section(title=current_title, text=text))

    for el in root.descendants:
        if isinstance(el, Tag) and el.name in HEADING_TAGS:
            flush()
            current_title = el.get_text(strip=True)
            current_parts = []
        elif isinstance(el, NavigableString):
            parent = el.parent
            if parent is not None and parent.name not in HEADING_TAGS:
                stripped = str(el).strip()
                if stripped:
                    current_parts.append(stripped)
    flush()

    if not sections:
        whole_text = root.get_text("\n", strip=True)
        return [Section(title=None, text=whole_text)] if whole_text.strip() else []
    return sections


def _dataframe_to_text(df) -> str:
    df = df.fillna("")
    header = " | ".join(str(c) for c in df.columns)
    rows = [" | ".join(str(v) for v in row) for row in df.itertuples(index=False)]
    return "\n".join([header, *rows])


def _extract_excel(path: Path) -> list[Section]:
    import pandas as pd

    sections: list[Section] = []
    sheets = pd.read_excel(path, sheet_name=None, dtype=str)
    for sheet_name, df in sheets.items():
        if df.empty:
            continue
        sections.append(Section(title=sheet_name, text=_dataframe_to_text(df)))
    return sections


def _extract_csv(path: Path) -> list[Section]:
    import pandas as pd

    df = pd.read_csv(path, dtype=str)
    if df.empty:
        return []
    return [Section(title=None, text=_dataframe_to_text(df))]


def _extract_md(path: Path) -> list[Section]:
    text = path.read_text(encoding="utf-8", errors="replace")
    sections: list[Section] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append(Section(title=current_title, text=body))

    for line in text.splitlines():
        m = _MD_HEADING_RE.match(line)
        if m:
            flush()
            current_title = m.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)
    flush()

    if not sections:
        whole = text.strip()
        return [Section(title=None, text=whole)] if whole else []
    return sections


def _extract_json(path: Path) -> list[Section]:
    import json as json_lib

    data = json_lib.loads(path.read_text(encoding="utf-8", errors="replace"))
    text = "\n".join(_flatten_json(data))
    return [Section(title=None, text=text)] if text.strip() else []


def _flatten_json(obj, prefix: str = "") -> list[str]:
    """Turn arbitrary JSON into "path: value" lines — searchable/embeddable
    text, without assuming any particular schema (policy JSON exports vary)."""
    lines: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            lines.extend(_flatten_json(value, child_prefix))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            lines.extend(_flatten_json(item, f"{prefix}[{i}]"))
    else:
        lines.append(f"{prefix}: {obj}" if prefix else str(obj))
    return lines
