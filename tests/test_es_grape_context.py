"""The ES per-record context pin (scripts/_lib/es/grape_context_overrides.json,
2026-10-24): the Catalan single documents' "MERSEGUERA - SUMOLL BLANCO" is one
entry — INCAVI names Sumoll blanc, VIVC keeps #7660 and #12073 apart — so the
pinned records bind the surface to sumoll-blanco; every other record keeps the
lexicon's Merseguera. A pin's slug must be in the lexicon.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.grape_entity import set_pliego_context  # noqa: E402
from _lib.grape_lexicon import DEFAULT_COLOUR, GRAPE_ALIAS  # noqa: E402

spec = importlib.util.spec_from_file_location("es02", ROOT / "scripts" / "es" / "02_extract_pliegos.py")
es02 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(es02)


def test_pins_name_lexicon_slugs():
    data = json.loads(es02.CONTEXT_OVERRIDES_PATH.read_text(encoding="utf-8"))
    for record, table in data.items():
        if record.startswith("_"):
            continue
        for surface, pin in table.items():
            known = set(GRAPE_ALIAS) | set(GRAPE_ALIAS.values()) | set(DEFAULT_COLOUR)
            assert pin["slug"] in known, (record, surface)
            assert pin.get("reason") and pin.get("source") and pin.get("verified"), (record, surface)


def test_the_catalan_line_is_one_pill():
    try:
        set_pliego_context("penedes")
        grapes = es02.parse_grapes("MERSEGUERA - SUMOLL BLANCO\nSUMOLL TINTO\n")
    finally:
        set_pliego_context(None)
    assert grapes["principal"] == ["sumoll-blanco", "sumoll-tinto"]
    assert grapes["details"][0]["name"] == "sumoll blanco"


def test_other_records_keep_merseguera():
    try:
        set_pliego_context("valencia")
        grapes = es02.parse_grapes("MERSEGUERA - SUMOLL BLANCO\n")
    finally:
        set_pliego_context(None)
    assert grapes["principal"] == ["merseguera", "sumoll-blanco"]


def test_agudelo_is_chenin_everywhere():
    assert GRAPE_ALIAS["agudelo"] == "chenin"
    grapes = es02.parse_grapes("AGUDELO - CHENIN BLANC\nGODELLO\n")
    assert grapes["principal"] == ["chenin", "godello"]


def test_two_names_written_without_their_comma_are_two_pills():
    # La Palma §7 (2026-10-25): MAPA lists Listán Prieto (T.) and Moscatel
    # Negro (T.) apart; a lexicon slug had kept the fused string
    grapes = es02.parse_grapes("- Autorizadas: Bastardo negro o Baboso negro, "
                               "Listán Prieto Moscatel negro y Vijariego Negro.\n")
    assert {"listan-prieto", "moscatel-negro"} <= set(grapes["accessory"])
    assert not any("listan-prieto-moscatel" in s for s in grapes["accessory"])
    # El Hierro: a roster line wrapped without its comma
    grapes = es02.parse_grapes("- Preferentes: Güal, Malvasía aromática, Malvasía volcánica\n"
                               "    Moscatel de Alejandría y Vijariego blanco o Diego.\n")
    assert {"malvasia-volcanica", "muscat-d-alexandrie"} <= set(grapes["principal"])


def test_castello_subirat_is_alarije():
    try:
        set_pliego_context("castello")
        grapes = es02.parse_grapes("- Blancas: Chardonnay, Subirat, Merseguera, Viura o Macabeo.\n")
    finally:
        set_pliego_context(None)
    assert "alarije" in grapes["principal"] and "macabeu" in grapes["principal"]
