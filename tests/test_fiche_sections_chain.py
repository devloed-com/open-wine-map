"""The register-fiche section parser builds its header chain twice (6 and 12
spaces of indent) and takes the deeper pass only when it extends the shallow
chain without changing a header of it (2026-10-22)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.fiche_technique import parse_fiche_sections  # noqa: E402

ANCHOR = ("JEDINÝ DOKLAD",)
END = ("DALŠÍ INFORMACE",)


def test_sobes_layout_deep_first_headers_then_margin():
    """Šobes: the single document's first three headers sit 11 spaces in,
    the rest at the margin — the shallow pass finds nothing, the deep one
    the whole run."""
    text = (
        "V. JEDINÝ DOKLAD\n"
        "           1. DRUHY VÝROBKŮ Z RÉVY VINNÉ\n                 1. Víno\n"
        "           2. POPIS VÍNA (VÍN)\n             bílá vína\n"
        "           3. TRADIČNÍ VÝRAZY\n              a. Bod a)\n"
        "4. POSTUPY VINIFIKACE\n  text\n"
        "5. VYMEZENÁ OBLAST\n  text\n"
        "6. HROZNY\n  a. Seznam hlavních moštových odrůd\n     08 Sauvignon\n"
        "7. SOUVISLOST SE ZEMĚPISNOU OBLASTÍ\n  text\n"
        "VI. DALŠÍ INFORMACE\n   1. ÚDAJE O ZPROSTŘEDKOVATELI\n"
    )
    sections, titles = parse_fiche_sections(text, ANCHOR, END)
    assert list(titles.values()) == [
        "DRUHY VÝROBKŮ Z RÉVY VINNÉ", "POPIS VÍNA (VÍN)", "TRADIČNÍ VÝRAZY", "POSTUPY VINIFIKACE",
        "VYMEZENÁ OBLAST", "HROZNY", "SOUVISLOST SE ZEMĚPISNOU OBLASTÍ",
    ]
    assert "08 Sauvignon" in sections["6"]


def test_indented_uppercase_variety_line_never_replaces_a_shallow_header():
    """Six Greek fiches: an indented "7. ASSYRTIKO" inside section 6 must
    not become section 7 when the shallow chain already has one."""
    text = (
        "I. JEDINÝ DOKLAD\n"
        "1. NÁZEV\n  x\n2. POPIS\n  x\n3. VÝRAZY\n  x\n4. POSTUPY\n  x\n5. OBLAST\n  x\n"
        "6. ODRŮDY\n        7. ASSYRTIKO\n        8. ATHIRI\n"
        "7. SOUVISLOST\n  the link\n8. PODMÍNKY\n  x\n"
        "II. DALŠÍ INFORMACE\n"
    )
    sections, titles = parse_fiche_sections(text, ANCHOR, END)
    assert titles["7"] == "SOUVISLOST"
    assert "ASSYRTIKO" in sections["6"]
    assert sections["7"] == "the link"


def test_deep_pass_extends_a_shallow_chain_that_stops_early():
    """HU Etyek-Buda: sections 3–9 sit past the 6-space guard; the deeper
    pass continues the shallow chain 1–2 unchanged."""
    text = (
        "I. JEDINÝ DOKLAD\n"
        "1. KATEGÓRIÁI\n  x\n2. LEÍRÁSA\n  x\n"
        "        3. KIFEJEZÉSEK\n  x\n        4. ELJÁRÁSOK\n  x\n"
        "II. DALŠÍ INFORMACE\n"
    )
    _, titles = parse_fiche_sections(text, ANCHOR, END)
    assert list(titles.values()) == ["KATEGÓRIÁI", "LEÍRÁSA", "KIFEJEZÉSEK", "ELJÁRÁSOK"]
