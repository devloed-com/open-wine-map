"""Parser for the Cyprus national wine product specification
(`τεχνικός φάκελος` / `ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ`) published by the Cyprus
Department of Agriculture (Τμήμα Γεωργίας) / Συμβούλιο Αμπελοοινικών
Προϊόντων on moa.gov.cy.

All 11 Cyprus wine GIs are Art.107 / Reg.1308/2013 grandfathered names
with no fetchable EU-OJ ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ HTML; the canonical public spec
is the per-wine technical-file PDF on the moa.gov.cy Lotus Domino site
(stage 01c fetches it). Each PDF embeds a full Greek single document
with numbered sections (name / categories / description / practices /
delimited area / grape varieties / link to terroir), so section routing
+ grape / style / terroir parsing reuse the Greek national-spec helpers
from `_lib.gr.specifikacija` verbatim.

CY-specific delta: a handful of the moa.gov.cy PDFs (the
`05-15-26-*.pdf` series — Πιτσιλιά, Λάρνακα, Λευκωσία) are **image-only
scans** with no text layer, so `pdftotext` returns nothing. For those we
fall back to OCR (`pdftoppm -r 300` → `tesseract -l ell`), then run the
identical Greek section/grape/terroir parsers over the OCR text. The
shared GR parser has no OCR step (the minagric specs all carry a text
layer), so the OCR fallback + a thin `parse_spec` orchestrator live here.
"""

from __future__ import annotations

import glob
import shutil
import subprocess
from pathlib import Path

from _lib.cy.eniaio_engrafo import greek_norm
from _lib.gr.specifikacija import (
    _derive_summary,
    _grape_windows,
    _pdf_to_text,
    _terroir_window,
    extract_sections,
    parse_grape_list,
    parse_styles,
    scan_grapes_prose,
)
from _lib.grape_entity import match_variety  # noqa: F401  (kept for parity / debug)

_MIN_TEXT_CHARS = 400


def _normalise_ocr(text: str) -> str:
    """Fold the OCR glyph drifts tesseract emits for Greek: the micro sign
    µ (U+00B5) for mu μ, the Latin look-alikes that sneak into Greek words,
    and runs of whitespace."""
    text = text.replace("µ", "μ")  # µ → μ
    text = text.replace("·", "·")
    return text


def _ocr_pdf(path: Path) -> str:
    """OCR an image-only PDF: rasterise at 300 dpi and run Greek tesseract
    page by page. Returns the concatenated plain text.

    The scratch dir is created *next to the source PDF* rather than under
    the system TMPDIR — tesseract/leptonica must be able to read the
    rasterised PNGs, and some sandboxed TMPDIRs are not reachable by the
    spawned binary."""
    out: list[str] = []
    td = path.parent / f".ocrtmp-{path.stem}"
    if td.exists():
        shutil.rmtree(td, ignore_errors=True)
    td.mkdir(parents=True, exist_ok=True)
    try:
        try:
            subprocess.run(
                ["pdftoppm", "-r", "300", "-png", str(path), str(td / "pg")],
                capture_output=True, timeout=300, check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("pdftoppm not on PATH (poppler)") from exc
        for png in sorted(glob.glob(str(td / "pg*.png"))):
            try:
                r = subprocess.run(
                    ["tesseract", png, "stdout", "-l", "ell", "--psm", "6"],
                    capture_output=True, timeout=180, check=False,
                )
            except FileNotFoundError as exc:
                raise RuntimeError("tesseract not on PATH (Greek OCR)") from exc
            out.append(r.stdout.decode("utf-8", errors="replace"))
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return _normalise_ocr("\n".join(out))


def to_text(path: Path) -> tuple[str, str]:
    """Reduce a CY national-spec PDF to plain text. Returns (text, method)
    where method ∈ {pdftotext, ocr-ell}. Falls back to OCR when the PDF has
    no usable text layer."""
    if path.suffix.lower().lstrip(".") != "pdf":
        raise ValueError(f"unsupported spec format: {path.name}")
    text = _pdf_to_text(path)
    if len(text.strip()) >= _MIN_TEXT_CHARS:
        return text, "pdftotext"
    return _ocr_pdf(path), "ocr-ell"


def parse_spec(path: Path, slug: str, name: str = "") -> dict:
    """Parse one Cyprus national-spec PDF into a sidecar dict. Mirrors
    `_lib.gr.specifikacija.parse_spec` but sources the text via `to_text`
    (with the OCR fallback) and tags `parser_template` with the source
    method so the audit can tell OCR'd specs apart."""
    text, method = to_text(path)
    exclude = frozenset({greek_norm(name)}) if name.strip() else frozenset()
    sections, titles = extract_sections(text)
    grape_body = sections.get("grape_varieties", "")
    grapes = parse_grape_list(grape_body, slug, exclude)
    if not grapes["principal"]:
        grapes = scan_grapes_prose(grape_body, slug, exclude)
    if not grapes["principal"]:
        best = grapes
        for window in _grape_windows(text):
            cand = scan_grapes_prose(window, slug, exclude)
            if len(cand["principal"]) > len(best["principal"]):
                best = cand
        grapes = best
    geo = sections.get("geo_area", "")
    link = sections.get("link_to_terroir", "")
    if len(link) < 400:
        link = _terroir_window(text) or link
    summary = _derive_summary(sections.get("description") or geo or "")
    return {
        "summary": summary,
        "grapes": grapes,
        "styles": parse_styles(sections),
        "geo_area_brief": geo,
        "link_to_terroir": link,
        "section_roles": sections,
        "section_titles": titles,
        "n_sections": len(sections),
        "n_grapes": len(grapes["details"]),
        "parser_template": f"cy-national-pdf-{method}",
    }
