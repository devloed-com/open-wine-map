"""Regression + behaviour tests for the FR cahier des charges parser
(`scripts/02_extract_cahiers.py`).

Covers the pure text helpers (slug / normalize_name / candidate_keys /
parse_communes) and the section-slicer `extract_sections`, including the two
latent regex bugs fixed in commit f1ad98c that silently dropped section X
("Lien au terroir"):

  1. CHAPITRE_RE was case-insensitive, so a line-wrapped body reference like
     "...visé au\nchapitre II du présent cahier..." matched and truncated the
     body early, losing sections VIII–XII. The fix made it case-sensitive.
  2. SECTION_HDR_RE's leading-whitespace class lacked \x0c, so a Roman-numeral
     heading landing right after a pdftotext page break (\x0c) failed to match.
     The fix added \x0c to the class.

These use small synthetic segments rather than raw fixtures — the behaviours
under test are about regex routing, which is exercised precisely by minimal
crafted input.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import importlib

# 02_extract_cahiers starts with a digit, so it can't be imported by name.
extract = importlib.import_module("02_extract_cahiers")


# --------------------------------------------------------------------------
# Pure text helpers
# --------------------------------------------------------------------------

def test_slug_basic_and_diacritics():
    assert extract.slug("Côte de Nuits-Villages") == "cote-de-nuits-villages"
    assert extract.slug("Châteauneuf-du-Pape") == "chateauneuf-du-pape"
    assert extract.slug("  Édge   Cäse!! ") == "edge-case"


def test_normalize_name_strips_punctuation_and_case():
    # Same loose key regardless of spacing / hyphen / diacritics / case.
    assert extract.normalize_name("Saint-Émilion") == extract.normalize_name("saint emilion")
    assert extract.normalize_name("Côtes du Rhône") == "cotesdurhone"


def test_candidate_keys_splits_aliases():
    # "ou" / "et" / comma aliases each yield a match key, full form first.
    keys = extract.candidate_keys("Cidre de Normandie ou Cidre normand")
    assert keys[0] == extract.normalize_name("Cidre de Normandie ou Cidre normand")
    assert extract.normalize_name("Cidre normand") in keys
    assert extract.normalize_name("Cidre de Normandie") in keys


def test_candidate_keys_comma_and_et_list():
    keys = extract.candidate_keys("Côtes de Bourg, Bourg et Bourgeais")
    assert extract.normalize_name("Côtes de Bourg") in keys
    assert extract.normalize_name("Bourg") in keys
    assert extract.normalize_name("Bourgeais") in keys


# --------------------------------------------------------------------------
# parse_communes
# --------------------------------------------------------------------------

def test_parse_communes_top_level_separators():
    out = extract.parse_communes("Commune A, Commune B et Commune C")
    assert out == ["Commune A", "Commune B", "Commune C"]


def test_parse_communes_keeps_parenthetical_commas_attached():
    field = (
        "Le Controis-en-Sologne (pour le territoire des communes déléguées de "
        "Feings, Fougères-sur-Bièvre et Ouchamps), Cheverny"
    )
    out = extract.parse_communes(field)
    assert len(out) == 2
    assert out[0].startswith("Le Controis-en-Sologne (")
    assert out[0].endswith(")")
    assert out[1] == "Cheverny"


def test_parse_communes_reglues_soft_wrapped_hyphen():
    # pdftotext leaves "Saint-\n Claude" -> "Saint- Claude"; must re-glue.
    out = extract.parse_communes("Saint- Claude-de-Diray, Candé-sur-Beuvron")
    assert out == ["Saint-Claude-de-Diray", "Candé-sur-Beuvron"]


# --------------------------------------------------------------------------
# extract_sections — section slicing + the f1ad98c regressions
# --------------------------------------------------------------------------

def _wrap(body: str) -> str:
    """Wrap section body text in the CHAPITRE Ier envelope extract_sections
    expects, plus a CHAPITRE II so the slicer keeps only chapter I."""
    return (
        "CHAPITRE Ier\n"
        + body
        + "\nCHAPITRE II - OBLIGATIONS DÉCLARATIVES\n"
        "Some declaration boilerplate that must be excluded.\n"
    )


def test_extract_sections_basic_routing():
    seg = _wrap(
        "I. - Nom de l'appellation\n"
        "Coulée de Serrant.\n"
        "IV. - Aire géographique\n"
        "La récolte des raisins est assurée sur la commune de Savennières.\n"
        "X. - Lien au terroir\n"
        "Le vignoble s'étend sur des coteaux schisteux.\n"
    )
    bodies, titles = extract.extract_sections(seg)
    assert set(bodies) >= {"I", "IV", "X"}
    assert "schisteux" in bodies["X"]
    assert "Lien au terroir" in titles["X"]
    # CHAPITRE II content must be excluded.
    assert "declaration boilerplate" not in bodies["X"]


def test_extract_sections_header_after_page_break():
    # Regression 2: a \x0c page break immediately before the X heading must
    # NOT prevent the heading from matching.
    seg = _wrap(
        "IX. - Mesures transitoires\n"
        "Néant.\n"
        "\x0cX. - Lien au terroir\n"
        "Les sols argilo-calcaires confèrent au vin sa minéralité.\n"
    )
    bodies, _titles = extract.extract_sections(seg)
    assert "X" in bodies, "section X heading after \\x0c page break was dropped"
    assert "minéralité" in bodies["X"]


def test_extract_sections_lowercase_chapitre_in_body_does_not_truncate():
    # Regression 1: a line-wrapped lowercase "chapitre" reference inside a
    # section body must not be treated as a CHAPITRE boundary and truncate the
    # remaining sections.
    seg = _wrap(
        "IV. - Aire géographique\n"
        "La récolte est assurée dans l'aire définie au\n"
        "chapitre II du présent cahier des charges.\n"
        "X. - Lien au terroir\n"
        "Terroir de coteaux exposés au sud.\n"
    )
    bodies, _titles = extract.extract_sections(seg)
    assert "X" in bodies, "lowercase body 'chapitre' truncated the segment early"
    assert "coteaux exposés au sud" in bodies["X"]
