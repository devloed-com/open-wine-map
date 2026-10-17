"""Dutch de / het agreement detector (scripts/_lib/nl_articles.py) and its
two consumers: the 02e back-check and the untranslated-residue report."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from _lib import terroir_backcheck as tb
from _lib.nl_articles import DE_NOUNS, HET_NOUNS, article_hits

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.mark.parametrize("text, hits", [
    ("Het wijngaard profiteert van de bescherming van het Vogezenmassief.", ["Het wijngaard"]),
    ("om het wijngaard geleidelijk terug te bevolken", ["het wijngaard"]),
    ("De productiegebied strekt zich uit over de heuvels.", ["De productiegebied"]),
    ("De hoge terras van het Günz bestaat uit zanden.", ["De hoge terras"]),
    ("Het kalksteenrijke ondergrond van de percelen.", ["Het kalksteenrijke ondergrond"]),
    ("Dit bodem is diep en deze gebied is droog.", ["Dit bodem", "deze gebied"]),
    ("In het gemeente Ourém variëren de bodems.", ["het gemeente"]),
])
def test_flags_an_article_that_does_not_agree(text, hits):
    assert article_hits(text) == hits


@pytest.mark.parametrize("text", [
    "De wijngaard ligt op de helling; het wijngebied ligt in het dal.",
    "Het heuvel- en voetheuvelgebied bestaat uit kalksteen.",          # first half of a compound
    "De klimaat- en bodemkenmerken maken de wijnen stevig.",
    "Het helling­oppervlak komt overeen met de Montagne de Corton.",  # soft hyphen
    "Het wijngaardareaal beslaat 5.259 hectare, waarmee het de grootste wijngaard is.",
    "waarom het de gemeente in de regio Murcia is met de zachtste winters",
    "omdat de phylloxera in dit type bodem geen schade heeft aangericht",
    "een van de drie bekken die de regio onderscheidt",
    "De Côte de Beaune en het oude perceel.",
    "",
])
def test_says_nothing_it_cannot_be_sure_of(text):
    assert article_hits(text) == []


def test_noun_tables_do_not_overlap():
    assert not DE_NOUNS & HET_NOUNS


def test_backcheck_feeds_the_article_detector_for_dutch_only():
    kw = dict(name="Condrieu", source_lang="fr", source_facts=[
        {"bullet": "Le vignoble se situe à quarante kilomètres au sud de Lyon.", "subsection": "facteurs_naturels"}],
        feedback=None)
    nl = tb.build_user_message(target_lang="nl", translated=[{"bullet": "Het wijngaard ligt ten zuiden van Lyon."}], **kw)
    assert "DETECTOR: article does not agree with its noun: Het wijngaard" in nl
    en = tb.build_user_message(target_lang="en", translated=[{"bullet": "Het wijngaard ligt ten zuiden van Lyon."}], **kw)
    assert "article does not agree" not in en
    assert "'het wijngaard' is wrong" in tb.system_prompt()
    assert "agreement error in the target language" in tb.system_prompt()


def test_untranslated_report_lists_dutch_article_errors():
    spec = importlib.util.spec_from_file_location("detect_untranslated", SCRIPTS / "detect_untranslated_terroir_facts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._GI_FORMS = frozenset()
    assert mod._reasons("Het wijngaard ligt ten zuiden van Lyon.", "nl", raw=False) == ["article:Het wijngaard"]
    assert mod._reasons("Het wijngaard ligt ten zuiden van Lyon.", "en", raw=False) == []


def test_backcheck_fix_cap_is_relative_to_a_long_bullet():
    long_nl = "Het wijngaard " + "ligt op kalksteen en mergel, " * 16 + "aan de voet van de causse."
    fixed = long_nl.replace("Het wijngaard", "De wijngaard", 1)
    assert len(long_nl) > tb.FIX_MAX_CHARS
    assert tb.fix_ok("Le vignoble …", long_nl, fixed) is None
    assert tb.fix_ok("Le vignoble …", long_nl, fixed + " Extra." * 20) == "length"
    assert tb.fix_ok("Le vignoble …", "Kort.", "x" * (tb.FIX_MAX_CHARS + 1)) == "length"
