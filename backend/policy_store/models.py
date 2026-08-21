"""Pydantic models for the exemplar policy library.

Mirrors the manifest/index shape from specs/policy_storage.md, extended
with doc/xlsx/xls/csv formats (the spec's format enum was pdf|docx|html|txt
only, but the real dataset includes spreadsheets and legacy Word docs).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["medication", "infection"]
# Deliberately a plain str, not a Literal: new formats will keep showing up as
# more files are collected (md, json seen already) and the manifest should be
# able to record a format `scan` doesn't have an extractor for yet — see
# manifest.KNOWN_FORMATS for the set extract.py can actually handle today.
FileFormat = str
SearchMethod = Literal["keyword", "semantic"]


class PolicyDoc(BaseModel):
    """One row of manifest.json / the `docs` table."""

    id: str
    title: str
    category: Category
    subtopics: list[str] = Field(default_factory=list)
    source_url: str | None = None
    format: FileFormat
    date_collected: date | None = None
    raw_path: str  # relative to data/policies/raw/, e.g. "medication/foo.pdf"

    # Curation/provenance fields, sourced from the team's collection spreadsheet
    # (Clinical-Policy-Corpus-Manifest.xlsx, "Final Corpus" sheet) via
    # import_corpus_xlsx.py. Not consumed by extract/chunk/index — kept so that
    # attribution, re-verification, and dataset-composition questions ("how many
    # formats represented", "which channel did this come from") don't need the
    # spreadsheet kept around as a second source of truth.
    source_row_id: int | None = None  # row "ID" from the spreadsheet's Final Corpus sheet — stable join key for reconcile_raw_files.py
    organisation: str | None = None
    channel: str | None = None  # collection channel, e.g. "A"-"F" — see the spreadsheet's own docs
    format_number: int | None = None  # content-type taxonomy (narrative policy, checklist, order set, ...) — NOT the file format above
    format_name: str | None = None
    doc_control_platform: str | None = None  # e.g. "PolicyStat", "None (native)"
    document_date: str | None = None  # free text — sources are inconsistently dated (e.g. "not dated on face")
    date_checked: date | None = None  # last confirmed source_url was reachable without login
    verified_open: bool | None = None  # was source_url confirmed publicly reachable, no login
    notes: str | None = None


class Section(BaseModel):
    """A titled span of extracted text — a heading-delimited section where the
    source format has structure (docx/html), or a whole page/sheet otherwise."""

    title: str | None = None
    text: str


class ChunkRecord(BaseModel):
    """One row of the `chunks` table."""

    id: str  # f"{doc_id}::{chunk_index}"
    doc_id: str
    chunk_index: int
    section: str | None = None
    text: str


class SearchResult(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str
    category: Category
    section: str | None = None
    text: str
    score: float
    method: SearchMethod
