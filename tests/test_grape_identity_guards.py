"""Grape-identity guards from the 2026-10-22 sweep after the Piemonte flag.

1. A MASAF Article 2 phrase that restates the appellation's name, wholly or in
   part, binds a grape only when the lexicon vouches for that name: VIVC keeps
   place names as synonyms ("Valtellina" → Veltliner rot, "Avola" → Ribolla
   gialla, "Barolo" → Nebbiolo), and such a binding gave nine Valtellina
   cards Roter Veltliner and Barolo's pill the label "Barolo".
2. Names the matcher had bound to another cultivar by fuzzy score resolve to
   their own VIVC-verified entry; wine-style words resolve to nothing.
3. The second pass: a canonical slug keeps its own name against another
   passport's legacy synonym, a short word never fuzzy-matches, the colour
   code is stripped after any letter, and the parsers keep a wrapped name
   whole (MASAF register tables, ES pliego lines that open on a colour word,
   a decimal point in "Incrocio Manzoni 2.15").
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.grape_entity import is_curated_surface, match_variety  # noqa: E402
from _lib.it.masaf import parse_grapes_with  # noqa: E402


def _grapes(body: str, name: str) -> dict[str, str]:
    out = parse_grapes_with(match_variety, body, wine_name=name)
    return {d["slug"]: d["name"] for d in out["details"]}


def test_part_of_the_name_is_not_a_grape():
    body = ('Base ampelografica I vini a denominazione di origine controllata e garantita '
            '"Valtellina Superiore", devono essere ottenuti da uve provenienti da vigneti aventi la '
            'seguente composizione varietale: Nebbiolo, (localmente denominato Chiavennasca) minimo il 90%.')
    assert _grapes(body, "Valtellina Superiore") == {"nebbiolo": "Nebbiolo"}


def test_the_genuine_phrase_labels_the_grape():
    body = ('Base ampelografica 1. I vini a denominazione di origine controllata e garantita «Barolo», '
            'devono essere ottenuti da uve provenienti dai vigneti composti esclusivamente dal vitigno Nebbiolo.')
    assert _grapes(body, "Barolo") == {"nebbiolo": "Nebbiolo"}


def test_an_igt_that_names_no_variety_has_no_grape():
    body = ('Base ampelografica 1. I vini a Indicazione Geografica Tipica “Avola” bianchi, rossi e rosati '
            'devono essere ottenuti da uve provenienti da vigneti composti da uno o più vitigni idonei '
            'alla coltivazione nel territorio della Regione Siciliana, riportati nell’allegato 1.')
    assert _grapes(body, "Avola") == {}


def test_a_variety_that_is_the_appellation_name_is_kept():
    body = ('Il vino “Cesanese di Affile” deve essere ottenuto dalle uve prodotte dai vigneti aventi la '
            'seguente composizione ampelografica: Cesanese di Affile minimo 90%.')
    assert "cesanese-di-affile" in _grapes(body, "Cesanese di Affile")


def test_malvasia_di_casorzo_is_its_own_red_variety():
    body = ('La denominazione è riservata ai vini rossi ottenuti dalle uve provenienti da vigneti composti '
            'per almeno il 90% dal vitigno Malvasia di Casorzo; possono concorrere fino al 10% le uve dei '
            'vitigni Freisa, Grignolino, Barbera.')
    got = _grapes(body, "Malvasia di Casorzo d'Asti")
    assert "malvasia-di-casorzo" in got and "malvasia-istriana" not in got


def test_curated_surface():
    assert is_curated_surface("Cesanese di Affile")
    assert is_curated_surface("Nebbiolo")
    assert is_curated_surface("Carignano")
    assert not is_curated_surface("Valtellina Superiore")


@pytest.mark.parametrize("token,slug", [
    ("Ruché N.", "ruche"), ("Timorasso B.", "timorasso"), ("Nosiola B", "nosiola"),
    ("Verdealbara B", "erbamat"), ("Pinela B", "pinella"), ("Pinella B", "pinella"),
    ("Caloria", "caloria"), ("Verdiso B.", "verdiso"), ("Corbina N.", "corbina"),
    ("Fokiano N", "fokiano"), ("Baron N", "baron"), ("Karát", "karat"), ("Rubinet", "rubinet"),
    ("Blauer Silvaner", "blauer-silvaner"), ("Carignano", "carignan"),
    ("Bianco d'Alessano B.", "bianco-di-alessano"), ("Bianco d’Alessano", "bianco-di-alessano"),
    ("Malvasia nera di Casorzo", "malvasia-di-casorzo"), ("Карменер", "carmenere"),
    ("Pinot blanc", "pinot-blanc"), ("Sauvignon blanc", "sauvignon"),
    ("Malvasia bianca B.", "malvasia-bianca"), ("Korona", "korona"),
    ("Lambrusco Benetti N.", "lambrusco-benetti"), ("Lambrusco Marani", "lambrusco-marani"),
    ("Groppello di Mocasina N.", "groppello-di-mocasina"), ("Groppello di Revò N.", "groppello-di-revo"),
    ("Ner d’Ala N.", "ner-d-ala"), ("Silcher B", "silcher"), ("Forcada", "forcada"),
    ("Moschatela B", "moschatela"), ("Sumoitinto", "sumoll-tinto"), ("Babić N", "babic"),
    ("ΑΣΥΡΤΙΚΟ Β", "assyrtiko"), ("Incrocio Manzoni 2.15 N.", "incrocio-manzoni-2-15"),
])
def test_identity(token, slug):
    m = match_variety(token)
    assert m is not None and m.slug == slug, (token, m)


@pytest.mark.parametrize("token", ["Siller", "csillag", "piros", "kretzer", "blanc", "gentile", "Rosa",
                                   "Lacryma", "Κάβα", "Πάτρα", "Μοναστήρι", "m 2", "Roche", "Montagna",
                                   "Ασπρούδα", "moscati", "grano", "Μοσχάτο", "doña"])
def test_style_and_place_words_are_not_grapes(token):
    assert match_variety(token) is None


def test_a_four_letter_word_never_fuzzy_matches():
    from _lib.grape_entity import _fuzzy_passes_sanity
    assert not _fuzzy_passes_sanity("dona", "donna", 88.9)
    assert _fuzzy_passes_sanity("pamidi", "pamid", 90.9)


def test_the_family_names_carry_no_single_passport():
    import json
    overrides = ROOT / "raw" / "vivc" / "slug_overrides.json"
    if not overrides.exists():
        pytest.skip("raw/vivc not on disk")
    entries = json.loads(overrides.read_text(encoding="utf-8"))["entries"]
    for slug in ("lambrusco", "groppello"):
        assert entries[slug]["vivc_id"] is False
        assert match_variety(slug.capitalize()).slug == slug


def test_masaf_register_rows_that_wrap_are_rebuilt():
    from _lib.it.masaf import _annex_candidates
    body = (
        "  73     Dolcetto N.               Nero                             IDONEO\n\n"
        "         Lambrusco del\n"
        " 851                               Nero                             IDONEO\n"
        "         Pellegrino N.\n\n"
        "         Lambrusco di Sorbara                Lambrusco\n"
        " 115                               Nero                             IDONEO\n"
        "         N.\n\n"
        " 117     Lambrusco Maestri N.      Nero      Lambrusco              IDONEO\n\n"
        "                                             Incrocio Manzoni\n"
        " 299     Manzoni Bianco B.        Bianco                         IDONEO\n"
        "                                             6.0.13 B.\n")
    got = [c for c in _annex_candidates(body) if not c.startswith("6.0")]
    assert got == ["Dolcetto N.", "Lambrusco del Pellegrino N.", "Lambrusco di Sorbara N.",
                   "Lambrusco Maestri N.", "Manzoni Bianco B."]


def test_a_decimal_point_does_not_end_a_variety_name():
    from _lib.it.masaf import _scan_vitigno_phrases
    got = _scan_vitigno_phrases("le uve della varietà Incrocio\nManzoni 2.15 e/o Refosco p.r.;")
    assert match_variety(got[0]).slug == "incrocio-manzoni-2-15"


@pytest.mark.parametrize("line,heading", [
    ("Blanca o Cigüente, Sauvignon Blanc, Gewürztraminer", False),
    ("Negramoll, y Merenzao o Tintilla.", False),
    ("Tinta, Cabernet Franc, Mazuela (Cariñena)", False),
    ("TINTAS                  BLANCAS", True),
    ("Blancas recomendadas:", True),
    ("- Tintas: Garnacha", True),
    ("Tintas", True),
])
def test_es_colour_heading(line, heading):
    from _lib.es.national_pliego import _colour_heading
    assert (_colour_heading(line) is not None) is heading


def test_es_wrapped_dona_blanca_stays_whole():
    from _lib.es.national_pliego import _stitch_continuations
    text = ("Chardonnay, Montúa o Chelva, Beba o Eva, Malvar, Parellada, Pedro Ximénez, Verdejo, Doña\n"
            "Blanca o Cigüente, Sauvignon Blanc, Gewürztraminer, Moscatel de Alejandría, Moscatel de\n"
            "grano Menudo, Perruno.")
    assert "Doña Blanca o Cigüente" in _stitch_continuations(text)


def test_ch_commune_with_a_canton_suffix_is_a_place():
    from _lib.ch.geometry import CHCommuneIndex
    idx = CHCommuneIndex.__new__(CHCommuneIndex)
    idx._bfs_by_name = {"rochevd": [5409]}
    idx._bare_names = {"roche"}
    assert idx.is_commune_name("Roche") and idx.is_commune_name("Roche (VD)")
    assert not idx.is_commune_name("Chasselas")


@pytest.mark.parametrize("token", ["Fehér", "fehér", "vörös", "bílá", "červené", "modrá", "crna", "črna",
                                   "bela", "albe", "negru", "negre", "nera", "nere", "bianco", "bianche",
                                   "weiss", "weisser", "roter", "blauer", "grauer", "blanche", "rouge",
                                   "noir", "branco", "λευκό", "ερυθρό", "rood", "white"])
def test_a_bare_colour_word_is_not_a_grape(token):
    """The Majarcă albă passport lists FEHER, VIVC lists NERA under Pinot noir
    and ROTER under Roter Veltliner — a block header or an adjective is never
    a variety (review of 2026-10-22)."""
    assert match_variety(token) is None


@pytest.mark.parametrize("token,slug", [("Bianca", "bianca"), ("Nero", "nero")])
def test_a_variety_named_like_a_colour_still_resolves(token, slug):
    m = match_variety(token)
    assert m is not None and m.slug == slug
