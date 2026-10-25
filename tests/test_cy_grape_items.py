"""The CY single-document roster reader (scripts/cy/02_extract_pliegos.py):
an em dash on a line of its own is a bullet, one inside a content line
separates a name from its synonym (Larnaka C/2026/4992, 2026-10-25 — read as
a bullet, "Malvasia Aromatica" became a second pill)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location("cy02", ROOT / "scripts" / "cy" / "02_extract_pliegos.py")
cy02 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cy02)

LARNAKA = "—\nMalvasia Lunga\n—\nMalvasia di Candia — Malvasia Aromatica\n—\nΑθήρι Μαύρο — Μαυράθηρο\n—\nΜοσχάτο Κύπρου\n"


def test_inline_em_dash_is_a_synonym_separator():
    items = cy02._grape_items(LARNAKA)
    assert items == ["Malvasia Lunga", "Malvasia di Candia - Malvasia Aromatica",
                     "Αθήρι Μαύρο - Μαυράθηρο", "Μοσχάτο Κύπρου"]
    slugs = [d["slug"] for d in cy02.parse_grapes(LARNAKA)["details"]]
    assert slugs == ["malvasia-bianca-lunga", "malvasia-di-candia", "mavrathiro", "moschato-kyprou"]


def test_inline_bullets_without_bullet_lines_stay_bullets():
    assert cy02._grape_items("— Merlot — Syrah — Grenache") == ["Merlot", "Syrah", "Grenache"]
