"""Spanish national traditional terms (Reg. (EU) 1308/2013 Art. 112(a)) per
EU-registered wine GI, from MAPA's "Listado de denominaciones de origen
protegidas e indicaciones geográficas protegidas de vinos registradas en la
Unión Europea" (column "Término tradicional": DO / DOCa / VP / VC / VT,
keyed by "Nº expediente UE"). Fetched by scripts/es/00_fetch_data.py.

`pdftotext -layout` row shape (one GI per line, page furniture between):

    DOP Priorat / Priorato            DOCa           PDO-ES-A1560
    IGP Ribera del Queiles              VT            PGI-ES-A0083

MAPA's column shorthand is expanded to the bottle wording (TERM_DISPLAY).
Curator pins live in national_term_overrides.json (regional-language legal
forms such as DOQ, file-number drift between the listado and eAmbrosia,
listado lag behind a recognition the regulator itself announced).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LISTADO_URL = (
    "https://www.mapa.gob.es/es/dam/jcr:f9643333-ef75-4a2f-8864-afd1ade63fd1/02_vinos.pdf"
)
LISTADO_DIR = ROOT / "raw" / "es" / "mapa"
LISTADO_FILE = "listado-dop-igp-vinos.pdf"
OVERRIDES_PATH = Path(__file__).with_name("national_term_overrides.json")

TERM_DISPLAY = {
    "DO": "DO",
    "DOCa": "DOCa",
    "VP": "Vino de Pago",
    "VC": "Vino de Calidad",
    "VT": "Vino de la Tierra",
}
PDO_TERMS = frozenset({"DO", "DOCa", "DOQ", "Vino de Pago", "Vino de Calidad"})
PGI_TERMS = frozenset({"Vino de la Tierra"})

_ROW_RE = re.compile(
    r"^\s*(?P<scheme>DOP|IGP)\s+(?P<name>\S.*?)\s{2,}"
    r"(?P<term>DOCa|DO|VP|VC|VT)\s+(?P<file_number>P(?:DO|GI)-ES-[A-Z0-9]+)\s*$"
)
_FILE_NUMBER_RE = re.compile(r"^(?P<scheme>P(?:DO|GI))-ES-[A-Z]*(?P<tail>\d+)$")

_TERMS_CACHE: dict[str, str] | None = None
_OVERRIDES_CACHE: dict[str, dict] | None = None


def parse_listado_text(text: str) -> dict[str, str]:
    """{file_number: MAPA shorthand} from `pdftotext -layout` output."""
    rows: dict[str, str] = {}
    for line in text.splitlines():
        m = _ROW_RE.match(line)
        if not m:
            continue
        fn, term = m.group("file_number"), m.group("term")
        if fn in rows and rows[fn] != term:
            raise ValueError(f"listado: {fn} carries both {rows[fn]} and {term}")
        rows[fn] = term
    return rows


def load_es_terms() -> dict[str, str]:
    """{file_number: display term}. Empty (with a stderr warning) when the
    listado PDF is absent; cached per process."""
    global _TERMS_CACHE
    if _TERMS_CACHE is not None:
        return _TERMS_CACHE
    pdf = LISTADO_DIR / LISTADO_FILE
    shown = pdf.relative_to(ROOT) if pdf.is_relative_to(ROOT) else pdf
    if not pdf.exists():
        print(
            f"[es-national-term] {shown} missing — run "
            "scripts/es/00_fetch_data.py; no ES traditional terms",
            file=sys.stderr,
        )
        _TERMS_CACHE = {}
        return _TERMS_CACHE
    proc = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True, text=True, check=True,
    )
    shorthand = parse_listado_text(proc.stdout)
    _TERMS_CACHE = {fn: TERM_DISPLAY[t] for fn, t in shorthand.items()}
    print(
        f"[es-national-term] {len(_TERMS_CACHE)} GIs from {shown}",
        file=sys.stderr,
    )
    return _TERMS_CACHE


def load_es_term_overrides() -> dict[str, dict]:
    global _OVERRIDES_CACHE
    if _OVERRIDES_CACHE is None:
        data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        _OVERRIDES_CACHE = {k: v for k, v in data.items() if not k.startswith("_")}
    return _OVERRIDES_CACHE


def _bridge_file_number(file_number: str, roster: dict[str, str]) -> str:
    """Bridge listado ↔ eAmbrosia file-number drift by scheme + numeric tail
    (`PDO-ES-A0117` ↔ `PDO-ES-0117`); only an unambiguous hit resolves."""
    m = _FILE_NUMBER_RE.match(file_number)
    if not m:
        return ""
    hits = set()
    for fn, term in roster.items():
        r = _FILE_NUMBER_RE.match(fn)
        if r and r.group("scheme") == m.group("scheme") and r.group("tail") == m.group("tail"):
            hits.add(term)
    return next(iter(hits)) if len(hits) == 1 else ""


def _check_scheme(term: str, kind: str, label: str) -> None:
    if kind == "IGP":
        assert term not in PDO_TERMS, f"{label}: PGI carries PDO-only term {term!r}"
    elif kind == "DOP":
        assert term not in PGI_TERMS, f"{label}: PDO carries PGI-only term {term!r}"


def es_term_for(record: dict, kind: str) -> str:
    """Display traditional term for one ES record: slug override first, then
    the listado roster by exact file_number, then the numeric-tail bridge,
    then "". Never a kind-based default — a PGI must not be stamped DO."""
    slug = record.get("slug") or ""
    override = load_es_term_overrides().get(slug)
    if override and override.get("term"):
        term = override["term"]
        _check_scheme(term, kind, slug)
        return term
    file_number = (
        (override or {}).get("file_number") or record.get("file_number") or ""
    )
    if not file_number:
        return ""
    roster = load_es_terms()
    term = roster.get(file_number) or _bridge_file_number(file_number, roster)
    if term:
        _check_scheme(term, kind, slug or file_number)
    return term


def check_sub_denomination_terms(records: list[dict]) -> list[str]:
    """Sub-denominations share the parent's file_number, so they must resolve
    to the parent's term (Rioja subzonas → DOCa). Returns one message per
    mismatch; empty means consistent."""
    by_slug = {r.get("slug"): r for r in records}
    problems = []
    for rec in records:
        if not rec.get("is_sub_denomination"):
            continue
        parent = by_slug.get(rec.get("parent_slug"))
        if parent is None:
            problems.append(f"{rec.get('slug')}: parent {rec.get('parent_slug')!r} not in corpus")
            continue
        own = es_term_for(rec, rec.get("kind", ""))
        parents_term = es_term_for(parent, parent.get("kind", ""))
        if own != parents_term:
            problems.append(
                f"{rec.get('slug')}: {own!r} != parent {parent.get('slug')} {parents_term!r}"
            )
    return problems
