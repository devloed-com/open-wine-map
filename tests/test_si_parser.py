"""Fixture-based regression tests for the Slovenia (SI) parsers.

Two parser surfaces, each a documented seam that historically regresses when
a tweak for one Slovenian source shape breaks another:

  - scripts/_lib/si/enotni_dokument.py  (+ the HTML driver in
    scripts/si/02_extract_pliegos.py) — the EUR-Lex "ENOTNI DOKUMENT" EU-OJ
    template. Section-keyword role routing (Ime ali imena / Razmejeno
    geografsko območje / Sorta ali sorte vinske trte / Povezava z geografskim
    območjem), the "Vrsta geografske označbe" geo_area blocklist decoy, and
    the grape-variety section's single em-dash-bulleted line
    ("— bela žlahtnina — beli pinot - weissburgunder — …"): split on the
    em-dash bullets, then on a plain hyphen for "Name - synonym" (the head
    resolves, the synonym blob is a fallback).

  - scripts/_lib/si/specifikacija.py — the national-spec parser, three
    branches:
      * mkgp-doc-v1: numbered SPECIFIKACIJA-PROIZVODA sections 1–9; §6 Sorte
        split by bele:/rdeče:/rose:; the "Tradicionalna imena" predikat-roster
        boilerplate truncated out of the style scan.
      * uradni-list-pravilnik-2007: Priloga 2 per-okoliš
        priporočene sorte -> principal / dovoljene sorte -> accessory — the
        ONLY SI source carrying a real principal/accessory split.
      * uradni-list-pravilnik-2022-ptp: strict `\\b\\d+\\. člen\\b`
        word-boundary article slicer that must NOT false-positive on the
        genitive/locative `5. člena` / `9. členu` cross-references.

Real cached docs live under raw/si/{oj-pages,specifikacije}/ (gitignored).
The Cviček ENOTNI DOKUMENT and the two pravilnik HTML branches are redacted
excerpts of those real documents; the .doc-sourced mkgp fixtures are
`# synthetic` (the binary .doc -> text path needs the antiword Docker image,
not run here) but their asserted slugs/styles are cross-checked against
raw/si/specifikacije-extracted/*.json so they match live parser output.

Assertions are on STRUCTURE (routed roles, the em-dash variety split, the
2007 priporočene/dovoljene role split, the 2022 člen word-boundary guard),
not on full-output snapshots. Where a test pins ACTUAL behaviour (the
synonym-head resolution, the matched-subset of varieties), the divergence
from the regulator's full roster is called out inline.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.si import specifikacija as spec  # noqa: E402
from _lib.si.enotni_dokument import _GEO_AREA_TITLE_BLOCKLIST  # noqa: E402

# 02_extract_pliegos starts with a digit, so import it by module path.
extract = importlib.import_module("si.02_extract_pliegos")


# ==========================================================================
# ENOTNI DOKUMENT HTML driver — section routing
# ==========================================================================

def _route_html(html: str) -> tuple[dict, dict, dict]:
    """Slice → extract numbered sections → route, the way build_record does."""
    doc = extract.slice_enotni_dokument(html)
    assert doc is not None, "ENOTNI-DOKUMENT anchor must be found"
    sections, titles = extract.extract_sections(doc)
    routed = extract.route_sections(sections, titles)
    return sections, titles, routed


def test_anchor_slice_drops_preamble(fixture_text):
    html = fixture_text("si_enotni_dokument_cvicek.html")
    doc = extract.slice_enotni_dokument(html)
    # The "PUBLICATION OF A SINGLE DOCUMENT" preamble before the anchor drops.
    assert "PUBLICATION OF A SINGLE DOCUMENT" not in doc
    assert doc.lstrip().startswith("<p")
    assert "ENOTNI DOKUMENT" in doc[:80]


def test_section_routing_cvicek(fixture_text):
    _sections, _titles, routed = _route_html(
        fixture_text("si_enotni_dokument_cvicek.html")
    )
    # The four semantic roles downstream consumers depend on are all present.
    assert {"name", "geo_area", "grape_varieties", "link_to_terroir"} <= set(routed)
    # Section 9 body lands in geo_area (area prose), section 10 in terroir.
    assert "vinorodnega okoliša Dolenjska" in routed["geo_area"]
    assert "celinsko podnebje" in routed["link_to_terroir"]
    # Section 8 body lands in grape_varieties (the em-dash list).
    assert "bela žlahtnina" in routed["grape_varieties"]
    # Section 1 name body is just the appellation.
    assert routed["name"].strip() == "Cviček"


def test_section_number_guard_keeps_number_prefixed_only(fixture_text):
    """SECTION_NUM_RE: a ti-grseq-1 header without a leading "N." number
    ("ENOTNI DOKUMENT", "„Cviček“") must NOT register as a numbered section,
    so its decoy body can't shadow a real numbered section."""
    html = fixture_text("si_enotni_dokument_cvicek.html")
    doc = extract.slice_enotni_dokument(html)
    sections, titles = extract.extract_sections(doc)
    assert set(sections) == set(titles)
    for num in sections:
        assert num[0].isdigit(), f"section key {num!r} should be number-prefixed"
    # The non-numbered decoy headers never became section titles.
    assert "ENOTNI DOKUMENT" not in titles.values()
    assert "„Cviček“" not in titles.values()


def test_regression_vrsta_oznacbe_not_routed_to_geo_area(fixture_text):
    """Section 2 "Vrsta geografske označbe" carries the keyword "geografske"
    so it would otherwise shadow the real area (section 9). The geo_area
    blocklist must keep geo_area on section 9 (area prose), NOT the section-2
    "ZOP – Zaščitena označba porekla" body."""
    # The blocklist entry is what keeps the regression closed.
    assert "vrsta geografske označbe" in _GEO_AREA_TITLE_BLOCKLIST
    _sections, _titles, routed = _route_html(
        fixture_text("si_enotni_dokument_cvicek.html")
    )
    geo = routed["geo_area"]
    assert "Zaščitena označba porekla" not in geo
    assert "vinorodnega okoliša Dolenjska" in geo


# ==========================================================================
# ENOTNI DOKUMENT — em-dash variety split + "Name - synonym" hyphen split
# ==========================================================================

def test_grape_em_dash_bullet_split_full_principal_set(fixture_text):
    """The grape section is one em-dash-bulleted line; every bullet item must
    become its own variety. The Cviček fixture reproduces the live extract's
    full 17-slug principal set (no principal/accessory split in the EU
    template -> all principal)."""
    _sections, _titles, routed = _route_html(
        fixture_text("si_enotni_dokument_cvicek.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    slugs = set(grapes["principal"])
    # Spot the load-bearing members across white + red.
    assert {"chasselas", "pinot-blanc", "chardonnay", "gamay", "kraljevina",
            "welschriesling", "lemberger", "zametovka", "zweigelt",
            "sankt-laurent"} <= slugs
    # 17 distinct varieties recovered from the 17 em-dash bullets.
    assert len(grapes["principal"]) == 17
    # No accessory split in the EU single document.
    assert grapes["accessory"] == []


def test_grape_name_synonym_hyphen_split_head_resolves(fixture_text):
    """"beli pinot - weissburgunder" splits on the plain hyphen: the HEAD
    ("beli pinot") resolves to pinot-blanc and is kept as the display name;
    the synonym blob ("weissburgunder") is only a fallback. Likewise
    "modra frankinja - frankinja" -> lemberger via the head."""
    _sections, _titles, routed = _route_html(
        fixture_text("si_enotni_dokument_cvicek.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    by_slug = {d["slug"]: d for d in grapes["details"]}
    # Head resolved, synonym dropped from the display name.
    assert by_slug["pinot-blanc"]["name"] == "beli pinot"
    assert "weissburgunder" not in by_slug["pinot-blanc"]["name"].lower()
    assert by_slug["lemberger"]["name"] == "modra frankinja"
    assert "frankinja -" not in by_slug["lemberger"]["name"]


def test_grape_typo_chardonay_still_resolves(fixture_text):
    """The cahier source carries a real spelling typo "chardonay" (one 'n');
    the lexicon matcher must still fold it to chardonnay (display name keeps
    the verbatim typo)."""
    _sections, _titles, routed = _route_html(
        fixture_text("si_enotni_dokument_cvicek.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    by_slug = {d["slug"]: d for d in grapes["details"]}
    assert "chardonnay" in grapes["principal"]
    assert by_slug["chardonnay"]["name"] == "chardonay"


def test_grape_items_split_unit():
    """_grape_items splits the single bulleted line on em-dash + newline."""
    items = extract._grape_items("— bela žlahtnina — beli pinot - weissburgunder — gamay")
    assert items == ["bela žlahtnina", "beli pinot - weissburgunder", "gamay"]


def test_item_candidates_head_then_synonyms():
    """_item_candidates returns the canonical head first, then the comma-split
    synonyms after the plain hyphen."""
    cands = extract._item_candidates("beli pinot - weissburgunder, pinot bianco")
    assert cands[0] == "beli pinot"
    assert "weissburgunder" in cands and "pinot bianco" in cands


# ==========================================================================
# specifikacija.py — mkgp-doc-v1 (numbered SPECIFIKACIJA PROIZVODA)
# ==========================================================================

def test_mkgp_section_split_numbered(fixture_text):
    text = fixture_text("si_mkgp_doc_bizeljcan.txt")
    out = spec.parse_mkgp_doc(text, "bizeljcan")
    assert out["parser_template"] == "mkgp-doc-v1"
    # Sections 1..9 sliced by the "N. Title:" headers.
    titles = out["section_titles"]
    assert set(titles) >= {"1", "2", "4", "6", "7"}
    assert "Sorte" in titles["6"]
    assert "Povezava z geografskim območjem" in titles["7"]


def test_mkgp_grape_colour_split_bele_vs_rdece(fixture_text):
    """§6 Sorte splits by colour header bele: -> blanc, rdeče: -> noir. Each
    variety carries the colour of its bucket. Asserts the stable matched
    subset (some Slovenian name forms don't resolve via the lexicon — that
    recall gap is the parser's ACTUAL behaviour, pinned here)."""
    text = fixture_text("si_mkgp_doc_bizeljcan.txt")
    out = spec.parse_mkgp_doc(text, "bizeljcan")
    by_slug = {d["slug"]: d for d in out["grapes"]["details"]}
    # White-bucket members resolve as blanc.
    for slug in ("welschriesling", "pinot-blanc", "chardonnay", "sauvignon"):
        assert by_slug[slug]["colour"] == "blanc", slug
    # Red-bucket members resolve as noir.
    for slug in ("lemberger", "zametovka", "sankt-laurent"):
        assert by_slug[slug]["colour"] == "noir", slug
    # mkgp has no principal/accessory split -> all principal.
    assert out["grapes"]["accessory"] == []


def test_regression_mkgp_tradicionalna_imena_truncated_from_styles(fixture_text):
    """The §2 description carries a "Tradicionalna imena: …" predikat roster
    (pozna trgatev / jagodni izbor / penina / …) listing every designation
    AUTHORISED for the okoliš, not styles actually produced. _parse_mkgp_styles
    must slice that boilerplate off before scanning, else every wine ends up
    tagged sparkling-quality + vendanges-tardives."""
    text = fixture_text("si_mkgp_doc_bizeljcan.txt")
    out = spec.parse_mkgp_doc(text, "bizeljcan")
    # Only the grape-colour-derived base styles survive.
    assert set(out["styles"]) == {"blanc", "rouge"}
    assert "sparkling-quality" not in out["styles"]
    assert "vendanges-tardives" not in out["styles"]
    # Sanity: WITHOUT the truncation the predikat ladder leaks in — proving the
    # slice is load-bearing, not incidental.
    desc = out["section_roles"]["description"]
    roster = desc[desc.index("Tradicionalna"):].replace("Tradicionalna imena", "", 1)
    leaked = spec._parse_mkgp_styles("opis " + roster, out["grapes"])
    assert "sparkling-quality" in leaked and "vendanges-tardives" in leaked


def test_mkgp_single_variety_no_colour_prefix_fallback(fixture_text):
    """A §6 Sorte body with NO colour prefix (Teran's lone "refošk") falls
    through to the whole-body-as-one-comma-list path. refošk folds to
    refosco-dal-peduncolo-rosso (noir), style rouge."""
    text = fixture_text("si_mkgp_doc_teran.txt")
    out = spec.parse_mkgp_doc(text, "teran")
    assert out["grapes"]["principal"] == ["refosco-dal-peduncolo-rosso"]
    by_slug = {d["slug"]: d for d in out["grapes"]["details"]}
    assert by_slug["refosco-dal-peduncolo-rosso"]["name"] == "refošk"
    assert by_slug["refosco-dal-peduncolo-rosso"]["colour"] == "noir"
    assert out["styles"] == ["rouge"]
    assert out["link_to_terroir"].startswith("Rdeča jerovica")


# ==========================================================================
# specifikacija.py — uradni-list-pravilnik-2007 (the real role split)
# ==========================================================================

def test_pravilnik_2007_dispatches_by_title(fixture_text):
    html = fixture_text("si_pravilnik_2007_bela-krajina.html")
    out = spec.parse_uradni_list_pravilnik(html, "bela-krajina")
    assert out is not None
    assert out["parser_template"] == "uradni-list-pravilnik-2007"
    assert out["matched_okoliši"] == ["Bela krajina"]


def test_regression_pravilnik_2007_priporocene_dovoljene_role_split(fixture_text):
    """Priloga 2: "a) priporočene sorte: …;" -> principal,
    "b) dovoljene sorte: …." -> accessory. This is the ONLY SI source with a
    real principal/accessory split — the split must survive verbatim. Slugs
    cross-checked against raw/si/specifikacije-extracted/bela-krajina.json."""
    html = fixture_text("si_pravilnik_2007_bela-krajina.html")
    out = spec.parse_uradni_list_pravilnik(html, "bela-krajina")
    principal = set(out["grapes"]["principal"])
    accessory = set(out["grapes"]["accessory"])
    # priporočene -> principal
    assert {"welschriesling", "pinot-blanc", "sauvignon", "pinot-gris",
            "chardonnay", "muscat-a-petits-grains", "lemberger",
            "zametovka"} == principal
    # dovoljene -> accessory
    assert {"sylvaner", "riesling", "bouvier", "kraljevina", "gewurztraminer",
            "kerner", "chasselas", "pinot-noir", "gamay", "zweigelt",
            "portugais-bleu", "sankt-laurent", "chasselas-rose"} == accessory
    # The two buckets are disjoint (no variety counted twice).
    assert principal.isdisjoint(accessory)


def test_pravilnik_2007_wrong_title_returns_none():
    # A document that is not the 2007/2022 pravilnik dispatches to None.
    out = spec.parse_uradni_list_pravilnik(
        "<html><body><p>Some unrelated regulation.</p></body></html>",
        "bela-krajina",
    )
    assert out is None


# ==========================================================================
# specifikacija.py — uradni-list-pravilnik-2022-ptp (člen word-boundary guard)
# ==========================================================================

def test_pravilnik_2022_dispatches_and_parses(fixture_text):
    html = fixture_text("si_pravilnik_2022_belokranjec.html")
    out = spec.parse_uradni_list_pravilnik(html, "belokranjec")
    assert out is not None
    assert out["parser_template"] == "uradni-list-pravilnik-2022-ptp"
    # Article 5 ¶(2) enumerated Belokranjec list -> 10 principal varieties,
    # all white (matches raw/si/specifikacije-extracted/belokranjec.json).
    assert len(out["grapes"]["principal"]) == 10
    assert {"kraljevina", "welschriesling", "pinot-blanc", "chardonnay",
            "sylvaner", "sauvignon", "riesling", "muscat-a-petits-grains",
            "kerner", "pinot-gris"} == set(out["grapes"]["principal"])
    assert out["grapes"]["accessory"] == []
    assert out["styles"] == ["blanc"]


def test_regression_2022_clen_word_boundary_ignores_genitive(fixture_text):
    """_PRAVILNIK_CLEN_RE uses `\\bčlen\\b`, so the genitive "5. člena" and
    locative "9. členu" cross-references inside the article bodies must NOT be
    parsed as new article headers. The fixture injects both forms; only the
    six real `N. člen` headers (1..6) may register, or article slicing breaks
    and the Belokranjec variety list (article 5) is lost."""
    html = fixture_text("si_pravilnik_2022_belokranjec.html")
    text = spec._html_to_text(html)
    # The inflected forms are present in the body...
    assert "5. člena" in text and "9. členu" in text
    # ...but only the six nominative `N. člen` headers are detected.
    bodies = spec._articles_2022(text)
    assert sorted(bodies) == [1, 2, 3, 4, 5, 6]
    # Header-number matches from the strict regex never include 5/9 from the
    # genitive forms beyond the real headers.
    nums = [m.group(1) for m in spec._PRAVILNIK_CLEN_RE.finditer(text)]
    assert nums == ["1", "2", "3", "4", "5", "6"]


def test_pravilnik_2022_only_belokranjec_slug(fixture_text):
    """The 2022 PTP branch is slug-gated: it parses only for "belokranjec".
    For any other slug (e.g. the sibling metliska-crnina) it returns None so
    the caller falls through."""
    html = fixture_text("si_pravilnik_2022_belokranjec.html")
    assert spec.parse_uradni_list_pravilnik(html, "metliska-crnina") is None
