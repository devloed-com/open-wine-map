"""Fixture-based regression tests for the Hungary (HU) parser.

Target module: scripts/_lib/hu/egyseges_dokumentum.py — the keyword/role
tables for the EUR-Lex "EGYSÉGES DOKUMENTUM" template — driven through the
HTML machinery in scripts/hu/02_extract_pliegos.py (the slice-from-anchor +
numbered-section extractor + keyword router + grape parser).

The CRITICAL seam is `extract_sections`: a monotonic-number state machine
that must NOT be fooled by wine-type subsections nested inside section 4
(description of wines) — and the analogous link subsections inside section 8
— which re-use `<p class="ti-grseq-1">` and RESTART numbering at 1
("1. Bor – Rozé fajta és küvé", "2. Bor – Siller…", "1. CLASSICUS BOROK:").
A naive first-occurrence dedupe would let those nested decoys shadow the
real top-level sections 5–9. Two guards collaborate: (a) accept a top-level
header only when it is the next expected integer; (b) drop a candidate whose
title matches a known nested-subsection prefix (`Bor –`, `Pezsgő`,
`Classicus`, …) even when its number would otherwise fit.

Real cached docs live under raw/hu/oj-pages/*.html (gitignored). The fixtures
here are short redacted excerpts under tests/fixtures/:
  - hu_egyseges_dokumentum_eger.html — Eger, the canonical document carrying
    BOTH nested-subsection decoy families (the `Bor –` rows inside §4 and
    the `1./2.` `CLASSICUS`/`SUPERIOR` rows between §6 and §7, and the
    `1./2./3.` link rows inside §8).
  - hu_egyseges_dokumentum_soltvadkerti.html — the older-template variant
    whose §8 link title "Kapcsolat a földrajzi területtel" carries the
    "földrajzi terület" geo_area keyword and must be blocklisted out of
    geo_area.

Assertions are on STRUCTURE (accepted section keys, routed roles, the
monotonic-number guard dropping the nested decoys, variety slug set), not
full-output snapshots. Where a test pins ACTUAL parser behaviour that
diverges from the obvious expectation (Furmint resolving with an EMPTY
colour string, the Hungarian display names folding to international slugs),
the divergence is called out inline.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.hu.egyseges_dokumentum import (  # noqa: E402
    _GEO_AREA_TITLE_BLOCKLIST,
    SECTION_ROLE_KEYWORDS,
)

# 02_extract_pliegos starts with a digit, so import it by module path.
extract = importlib.import_module("hu.02_extract_pliegos")


def _route_html(html: str) -> tuple[dict, dict, dict]:
    """Slice → extract numbered sections → route. Returns
    (sections, titles, routed) the way build_record drives them."""
    doc = extract.slice_egyseges_dokumentum(html)
    assert doc is not None, "EGYSÉGES DOKUMENTUM anchor must be found"
    sections, titles = extract.extract_sections(doc)
    routed = extract.route_sections(sections, titles)
    return sections, titles, routed


def _ordered_keys(sections: dict) -> list[str]:
    return sorted(sections, key=lambda k: [int(p) for p in k.split(".")])


# ==========================================================================
# Anchor slice + section routing
# ==========================================================================

def test_anchor_slice_drops_preamble(fixture_text):
    html = fixture_text("hu_egyseges_dokumentum_eger.html")
    doc = extract.slice_egyseges_dokumentum(html)
    assert doc is not None
    # The STANDARD-AMENDMENT modification preamble before the anchor is dropped.
    assert "STANDARD AMENDMENT" not in doc
    assert doc.lstrip().lower().startswith("<p")


def test_section_routing_eger(fixture_text):
    _sections, _titles, routed = _route_html(
        fixture_text("hu_egyseges_dokumentum_eger.html")
    )
    # The semantic roles downstream consumers depend on.
    for role in ("name", "geo_area", "grape_varieties", "link_to_terroir"):
        assert role in routed, role
    # Section 1 → name; the dual Eger/Egri form survives.
    assert "Eger" in routed["name"]
    # Section 6 body → geo_area (commune list), NOT terroir prose.
    assert "Andornaktálya" in routed["geo_area"]
    assert "Természeti tényezők" not in routed["geo_area"]
    # Section 7 body → grape_varieties.
    assert "kadarka" in routed["grape_varieties"].lower()
    # Section 8 body → link_to_terroir.
    assert "Természeti tényezők" in routed["link_to_terroir"]
    assert "Bükk-hegység" in routed["link_to_terroir"]


# ==========================================================================
# CRITICAL: the monotonic-number nested-subsection guard (extract_sections)
# ==========================================================================

def test_extract_sections_accepts_contiguous_top_level_1_to_9(fixture_text):
    """The full 1→9 top-level chain is accepted; nothing else is."""
    html = fixture_text("hu_egyseges_dokumentum_eger.html")
    doc = extract.slice_egyseges_dokumentum(html)
    sections, titles = extract.extract_sections(doc)
    assert _ordered_keys(sections) == ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
    # Every accepted key is a bare top-level integer (no 5.x / 8.x children
    # in this redacted Eger excerpt).
    for k in sections:
        assert "." not in k
    # Section keys and title keys agree.
    assert set(sections) == set(titles)


def test_regression_nested_bor_subsection_decoy_inside_section_4(fixture_text):
    """Section 4 ("A bor(ok) leírása") is followed by `1. Bor – Rozé fajta és
    küvé` and `2. Bor – Siller fajta és küvé` rows that re-use the
    `<p class="ti-grseq-1">` tag and RESTART numbering at 1. They must NOT be
    accepted as top-level sections — otherwise their bodies would shadow the
    real sections 5–9. (egyseges_dokumentum nested-subsection guard.)"""
    html = fixture_text("hu_egyseges_dokumentum_eger.html")
    doc = extract.slice_egyseges_dokumentum(html)
    _sections, titles = extract.extract_sections(doc)
    # No accepted title is one of the nested `Bor –` wine-type decoys.
    for t in titles.values():
        assert not t.startswith("Bor –"), t
    # The real description section 4 kept its own title, not a decoy's.
    assert titles["4"] == "A bor(ok) leírása"


def test_regression_classicus_superior_decoys_between_section_6_and_7(fixture_text):
    """Eger restarts numbering again between §6 and §7 with
    `1. CLASSICUS BOROK:` / `2. SUPERIOR ÉS GRAND SUPERIOR BOROK:`. These
    nested rows must not be accepted as top-level sections; their commune
    text lands as section 6's BODY (geo_area), and the real section 7
    (grapes) still wins."""
    html = fixture_text("hu_egyseges_dokumentum_eger.html")
    doc = extract.slice_egyseges_dokumentum(html)
    sections, titles = extract.extract_sections(doc)
    assert "CLASSICUS BOROK:" not in titles.values()
    assert "SUPERIOR ÉS GRAND SUPERIOR BOROK:" not in titles.values()
    # The decoy commune text is captured as part of section 6's body.
    assert "CLASSICUS" in sections["6"]
    assert "Andornaktálya" in sections["6"]
    # Section 7 is the real grape section, not a CLASSICUS decoy.
    assert titles["7"] == "Fontosabb borszőlőfajták"


def test_regression_link_subsection_decoys_inside_section_8(fixture_text):
    """Section 8 ("A KAPCSOLAT(OK) LEÍRÁSA") nests `1. Körülhatárolt terület
    bemutatása`, `2. A borok leírása`, `3. Az okszerű kapcsolat…` rows that
    restart numbering at 1. A naive first-occurrence dedupe would let
    "2. A borok leírása" (an innocuous-looking title) be accepted as a
    top-level section and shadow the real section 9. The monotonic guard
    (number 1/2/3 ≠ last_top+1 once §8 is accepted) drops them all."""
    html = fixture_text("hu_egyseges_dokumentum_eger.html")
    doc = extract.slice_egyseges_dokumentum(html)
    sections, titles = extract.extract_sections(doc)
    assert "A borok leírása" not in titles.values()
    assert "Az okszerű kapcsolat bemutatása és bizonyítása" not in titles.values()
    # The link subsection text is captured as part of section 8's body.
    assert "okszerű kapcsolat" in sections["8"].lower() or \
        "Körülhatárolt terület bemutatása" in sections["8"]
    # The real section 9 (additional conditions) survived.
    assert titles["9"].startswith("További alapvető feltételek")


def test_regression_prefix_guard_drops_decoy_when_number_would_fit():
    """Isolates the title-prefix guard (`_looks_like_nested_subsection`) from
    the monotonic-number guard: a `Bor –` decoy numbered as the NEXT expected
    integer (5, right after §4) would pass the monotonic check, so only the
    prefix guard can drop it. The real section 5 (Borkészítési eljárások)
    must then win the `5` slot."""
    def H(n: str, t: str) -> str:
        return (
            f'<p class="ti-grseq-1">{n}.&#160;<span class="bold">{t}</span></p>'
            f"<p>body of {n} {t[:8]}</p>"
        )
    doc = (
        H("1", "Elnevezés")
        + H("2", "A földrajzi árujelző típusa")
        + H("3", "A szőlőből készült termékek kategóriái")
        + H("4", "A bor(ok) leírása")
        + H("5", "Bor – Rozé fajta és küvé")   # prefix decoy, number fits
        + H("5", "Borkészítési eljárások")     # the real section 5
    )
    _sections, titles = extract.extract_sections(doc)
    assert titles["5"] == "Borkészítési eljárások"
    assert not any(t.startswith("Bor –") for t in titles.values())


def test_looks_like_nested_subsection_table():
    """Direct unit on the prefix predicate: the documented decoy prefixes
    fire; the real top-level section titles do not."""
    f = extract._looks_like_nested_subsection
    assert f("Bor – Rozé fajta és küvé")
    assert f("Bor - Siller")          # plain hyphen variant
    assert f("Pezsgő")
    assert f("CLASSICUS BOROK:")       # `classicus` prefix
    assert f("Likőrbor")
    # Real top-level section titles are NOT nested decoys.
    assert not f("A bor(ok) leírása")
    assert not f("Körülhatárolt földrajzi terület")
    assert not f("Fontosabb borszőlőfajták")
    assert not f("A kapcsolat(ok) leírása")


# ==========================================================================
# Grape parsing — "Canonical name – Synonym" en-dash split + alias folding
# ==========================================================================

def test_grape_parsing_endash_synonym_split(fixture_text):
    """Section 7 lists `Canonical name – Synonym, …`. The canonical name is
    the segment BEFORE the en-dash; the synonym tail is only a fallback. The
    display name keeps the canonical Hungarian spelling, sans synonyms."""
    _sections, _titles, routed = _route_html(
        fixture_text("hu_egyseges_dokumentum_eger.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    slugs = set(grapes["principal"])
    # Direct-name resolutions.
    assert {"kadarka", "furmint", "syrah", "cabernet-franc", "pinot-noir"} <= slugs
    # Display name is the segment before the en-dash (synonyms dropped).
    by_slug = {d["slug"]: d for d in grapes["details"]}
    assert by_slug["kadarka"]["name"] == "kadarka"
    assert "jenei fekete" not in by_slug["kadarka"]["name"]
    # No principal/accessory split in the HU single document → all principal.
    assert grapes["accessory"] == []
    assert set(grapes["principal"]) == set(by_slug)


def test_grape_parsing_hungarian_names_fold_to_international_slugs(fixture_text):
    """The GRAPE_ALIAS / matcher folds Hungarian variety names onto the
    shared international canonical slugs: tramini → gewurztraminer,
    kékfrankos → blaufrankisch, olasz rizling → welschriesling,
    királyleányka → feteasca-regala, leányka → feteasca-alba."""
    _sections, _titles, routed = _route_html(
        fixture_text("hu_egyseges_dokumentum_eger.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    slugs = set(grapes["principal"])
    assert "gewurztraminer" in slugs      # tramini
    assert "blaufrankisch" in slugs       # kékfrankos
    assert "welschriesling" in slugs      # olasz rizling
    assert "feteasca-regala" in slugs     # királyleányka
    assert "feteasca-alba" in slugs       # leányka


def test_grape_colour_actual_behaviour(fixture_text):
    """Per-grape colour comes from the matcher. ACTUAL behaviour pinned:
    a noir variety (kadarka / syrah) carries colour 'noir', but Furmint
    resolves with an EMPTY colour string here (the lexicon entry carries no
    default colour for the bare Furmint match in this context) — pinned so a
    future lexicon edit is a conscious change, not an accident."""
    _sections, _titles, routed = _route_html(
        fixture_text("hu_egyseges_dokumentum_eger.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    by_slug = {d["slug"]: d for d in grapes["details"]}
    assert by_slug["kadarka"]["colour"] == "noir"
    assert by_slug["syrah"]["colour"] == "noir"
    # Divergence: Furmint resolves with no colour string.
    assert by_slug["furmint"]["colour"] == ""


def test_item_candidates_endash_and_hyphen_split():
    """`_item_candidates` splits a name/synonym item on a spaced en-dash OR a
    spaced hyphen, returning the canonical head first then the synonyms."""
    assert extract._item_candidates("kadarka – jenei fekete") == [
        "kadarka", "jenei fekete"]
    assert extract._item_candidates("cabernet franc - carbonet") == [
        "cabernet franc", "carbonet"]
    # Multiple comma-separated synonyms after the dash all become candidates.
    assert extract._item_candidates("furmint – zapfner, posipel, som") == [
        "furmint", "zapfner", "posipel", "som"]


# ==========================================================================
# Style detection
# ==========================================================================

def test_style_detection_rose_from_description(fixture_text):
    """parse_styles scans the description + additional-conditions bodies for
    Hungarian colour adjectives + Tokaji-ladder markers. The Eger excerpt's
    §4 mentions `Rozébor` → the `rose` style tag is detected."""
    html = fixture_text("hu_egyseges_dokumentum_eger.html")
    doc = extract.slice_egyseges_dokumentum(html)
    sections, titles = extract.extract_sections(doc)
    styles = extract.parse_styles(sections, titles)
    assert "rose" in styles


# ==========================================================================
# Regression: older-template link title carries the geo_area keyword
# ==========================================================================

def test_geo_area_blocklist_table_present():
    # The blocklist must keep both diacritic + ASCII-folded forms of the
    # "Kapcsolat a földrajzi…" link-title decoy. A missing entry re-opens the
    # regression where the terroir section steals the geo_area role.
    assert "kapcsolat a földrajzi" in _GEO_AREA_TITLE_BLOCKLIST
    assert "kapcsolat a foldrajzi" in _GEO_AREA_TITLE_BLOCKLIST


def test_regression_kapcsolat_foldrajzi_title_not_routed_to_geo_area(fixture_text):
    """Older template: section 8 is titled "Kapcsolat a földrajzi területtel",
    which contains the "földrajzi terület" geo_area keyword and would
    otherwise shadow the real area in section 6. The blocklist must keep
    geo_area on section 6 and route section 8 to link_to_terroir."""
    _sections, _titles, routed = _route_html(
        fixture_text("hu_egyseges_dokumentum_soltvadkerti.html")
    )
    assert "geo_area" in routed and "link_to_terroir" in routed
    assert routed["geo_area"] != routed["link_to_terroir"]
    # The real area (section 6) is what landed in geo_area.
    assert "Soltvadkert" in routed["geo_area"]
    assert "Természeti" not in routed["geo_area"]
    # Section 8's terroir prose landed in link_to_terroir.
    assert "Természeti" in routed["link_to_terroir"]


def test_grape_keywords_routing_table_priority():
    """The grape-variety keyword tuple lists the most specific inflected
    forms first; the bare "szőlőfajták" stem is last so a more specific
    title wins. Pin the head of the tuple so a re-order is deliberate."""
    grape_keywords = SECTION_ROLE_KEYWORDS["grape_varieties"]
    assert grape_keywords[0] == "fontosabb borszőlőfajták"
    # geo_area's most specific keyword leads its tuple too.
    geo_keywords = SECTION_ROLE_KEYWORDS["geo_area"]
    assert geo_keywords[0] == "körülhatárolt földrajzi terület"
