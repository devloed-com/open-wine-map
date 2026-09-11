"""Italian national term (DOC / DOCG / IGT) per appellation.

The EU register carries only the scheme (PDO / PGI). The traditional term
Italy attaches to each GI under Reg. (EU) 1308/2013 Art. 112(a) — DOC or
DOCG for a DOP, IGT for an IGP — is published by MASAF in the "Elenco
alfabetico dei vini DOP italiani" (stage 00 caches it under
raw/it/masaf-elenchi/). Each roster row carries the eAmbrosia file number,
which is the join key: the register writes it as `PDO-IT-A1896` for older
GIs and `PDO-IT-01896` for post-2023 ones, so both sides are reduced to the
bare numeric tail before joining.

Curator pins live in national_term_overrides.json (slug-keyed, with cited
sources) for GIs the roster does not yet carry — a term registered after
the roster was compiled — and take precedence over the roster.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ELENCHI_DIR = ROOT / "raw" / "it" / "masaf-elenchi"
DOP_ELENCO_PATH = ELENCHI_DIR / "elenco-dop.pdf"
OVERRIDES_PATH = Path(__file__).with_name("national_term_overrides.json")

_ROW_RE = re.compile(r"\b(DOCG|DOC)\b\s+(PDO-IT-[A-Z]?\d+)")
_TAIL_RE = re.compile(r"([A-Za-z]*)(\d+)\s*$")


def file_number_tail(fn: str) -> str:
    """`PDO-IT-A1896` and `PDO-IT-01896` → `1896`."""
    m = _TAIL_RE.search((fn or "").rsplit("-", 1)[-1])
    if not m:
        return ""
    return m.group(2).lstrip("0") or "0"


def parse_elenco_text(text: str) -> dict[str, str]:
    """`pdftotext -layout` output of the DOP elenco → {file_number_tail: term}.

    A row's name may wrap over several lines, but the term and the file
    number always sit on the same line, so the pair is the row anchor."""
    roster: dict[str, str] = {}
    for term, fn in _ROW_RE.findall(text):
        tail = file_number_tail(fn)
        prev = roster.get(tail)
        if prev and prev != term:
            print(f"[national_term] WARNING {fn}: {prev} vs {term} in elenco",
                  file=sys.stderr)
        roster[tail] = term
    return roster


@lru_cache(maxsize=1)
def load_it_terms() -> dict[str, str]:
    if not DOP_ELENCO_PATH.exists():
        print(f"[national_term] WARNING {DOP_ELENCO_PATH.relative_to(ROOT)} absent — "
              "run scripts/it/00_fetch_data.py; IT DOC/DOCG terms unresolved",
              file=sys.stderr)
        return {}
    if not shutil.which("pdftotext"):
        print("[national_term] WARNING pdftotext not on PATH; IT DOC/DOCG terms unresolved",
              file=sys.stderr)
        return {}
    out = subprocess.run(
        ["pdftotext", "-layout", str(DOP_ELENCO_PATH), "-"],
        capture_output=True, text=True, check=True,
    ).stdout
    roster = parse_elenco_text(out)
    n_docg = sum(1 for t in roster.values() if t == "DOCG")
    print(f"[national_term] elenco DOP: {len(roster)} rows "
          f"({n_docg} DOCG / {len(roster) - n_docg} DOC)", file=sys.stderr)
    return roster


@lru_cache(maxsize=1)
def load_it_term_overrides() -> dict[str, dict]:
    if not OVERRIDES_PATH.exists():
        return {}
    return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))


def it_term_for(record: dict, kind: str) -> str:
    kind = (kind or "").upper()
    if kind == "IGP":
        return "IGT"
    if kind != "DOP":
        return ""
    overrides = load_it_term_overrides()
    for slug in (record.get("slug"), record.get("parent_slug")):
        if slug and slug in overrides:
            return overrides[slug].get("term", "")
    return load_it_terms().get(file_number_tail(record.get("file_number") or ""), "")
