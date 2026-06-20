"""Fixture-based regression tests for the Austria (AT) parser.

Two target modules, both landed in a single commit (38387ab "austria and
slovenia") — there are no later "fix"-flavoured commits to mine, so the
cases below pin the documented seams of the parser instead of past bugs:

  - scripts/at/02_extract_pliegos.py — the EUR-Lex "EINZIGES DOKUMENT"
    HTML driver: slice from the anchor, find numbered `ti-grseq-1`
    section headers (the SECTION_NUM_RE guard drops the numberless decoy
    headers "KURZE TEXTBESCHREIBUNG" / italic "Wachau g.U." the same way
    the RO parser drops "DOCUMENT UNIC"), route bodies by German title
    keyword, and parse the section-7 "Offizieller Name - Synonym, …"
    variety lines (canonical name = segment before the dash; the synonym
    blob is a fallback).
  - scripts/_lib/at/einziges_dokument.py — the German keyword/role tables,
    the geo_area title blocklist ("Art der geografischen Angabe" carries
    "geografische" but its body is just "g.U."), the German colour
    vocabulary, and the Prädikat/Schaumwein STYLE_MARKERS.
  - scripts/_lib/at/region.py — Bundesland derivation: the curated
    file_number map (authoritative) + a free-text scan fallback.

Real cached docs live under raw/at/oj-pages/ (gitignored). The fixtures
here are short redacted excerpts under tests/fixtures/at_*.html.

Assertions are on STRUCTURE (routed roles, slug sets, colour split,
section keys), not full-output snapshots. Several tests pin ACTUAL
parser behaviour that diverges from the docstring's ideal — the empty
`colour` field for VIVC-folded varieties (Blaufränkisch→lemberger,
Weißer Burgunder→pinot-blanc, Weißer Riesling→riesling) and the
adjective-vs-noun gap in find_bundesland_in_text. The divergence is
called out inline at each such test.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.at import region  # noqa: E402
from _lib.at.einziges_dokument import (  # noqa: E402
    _GEO_AREA_TITLE_BLOCKLIST,
    COLOUR_BY_KEYWORD,
    SECTION_ROLE_KEYWORDS,
    STYLE_MARKERS,
)

# 02_extract_pliegos starts with a digit, so import it by module path.
extract = importlib.import_module("at.02_extract_pliegos")


def _route_html(html: str) -> tuple[dict, dict, dict]:
    """Slice → extract numbered sections → route. Returns (sections,
    titles, routed) the way build_record drives them."""
    doc = extract.slice_einziges_dokument(html)
    assert doc is not None, "EINZIGES-DOKUMENT anchor must be found"
    sections, titles = extract.extract_sections(doc)
    routed = extract.route_sections(sections, titles)
    return sections, titles, routed


# ==========================================================================
# EINZIGES DOKUMENT HTML driver — anchor slice + section routing
# ==========================================================================

def test_anchor_slice_drops_preamble(fixture_text):
    html = fixture_text("at_einziges_dokument_wachau.html")
    doc = extract.slice_einziges_dokument(html)
    # The "VERÖFFENTLICHUNG EINES ÄNDERUNGSANTRAGS" modification preamble
    # before EINZIGES DOKUMENT is dropped.
    assert "ÄNDERUNGSANTRAGS" not in doc
    assert doc.lstrip().startswith("<p")
    # The slice begins at the anchor paragraph itself.
    assert "EINZIGES DOKUMENT" in doc[:80]


def test_section_routing_wachau(fixture_text):
    _sections, _titles, routed = _route_html(
        fixture_text("at_einziges_dokument_wachau.html")
    )
    # The four semantic roles downstream consumers depend on.
    assert "geo_area" in routed
    assert "grape_varieties" in routed
    assert "link_to_terroir" in routed
    assert "name" in routed
    # Section 6 body lands in geo_area (the Gemeinden list), NOT terroir.
    assert "niederösterreichischen Gemeinden" in routed["geo_area"]
    assert "Spitz" in routed["geo_area"]
    # Section 7 body lands in grape_varieties.
    assert "Grüner Veltliner" in routed["grape_varieties"]
    # Section 8 body lands in link_to_terroir.
    assert "Terrassenanlagen" in routed["link_to_terroir"]


def test_numberless_decoy_headers_are_not_sections(fixture_text):
    """The SECTION_NUM_RE guard: a `ti-grseq-1` header without a leading
    "N." number (the anchor "EINZIGES DOKUMENT", the italic "Wachau g.U."
    sub-title, the all-caps "KURZE TEXTBESCHREIBUNG") must NOT register as
    a numbered section — otherwise those decoy bodies would shadow the
    real numbered sections. (The AT analogue of the RO "DOCUMENT UNIC"
    uppercase-decoy guard.)"""
    html = fixture_text("at_einziges_dokument_wachau.html")
    doc = extract.slice_einziges_dokument(html)
    sections, titles = extract.extract_sections(doc)
    # Section keys are numeric prefixes only.
    assert set(sections) == set(titles)
    for num in sections:
        assert num[0].isdigit(), f"section key {num!r} should be number-prefixed"
    # No decoy heading registered as a section title.
    assert "KURZE TEXTBESCHREIBUNG" not in titles.values()
    assert "EINZIGES DOKUMENT" not in titles.values()
    assert not any(v == "Wachau g.U." for v in titles.values())


def test_nested_subsection_numbering_preserved(fixture_text):
    """Section 5 carries nested "5.1 Spezifische önologische Verfahren"
    and "5.2 Höchsterträge" subsections. The dotted keys must survive
    intact alongside the flat 1..9 keys — _gather_subsections relies on
    the dotted prefix to fold a blank parent body."""
    html = fixture_text("at_einziges_dokument_wachau.html")
    doc = extract.slice_einziges_dokument(html)
    sections, titles = extract.extract_sections(doc)
    assert {"5", "5.1", "5.2"} <= set(sections)
    assert titles["5.1"] == "Spezifische önologische Verfahren"
    assert titles["5.2"] == "Höchsterträge"
    # The flat top-level run is complete (no decoy shadowing a real one).
    assert {"1", "2", "3", "4", "5", "6", "7", "8", "9"} <= set(sections)


# ==========================================================================
# geo_area title blocklist — the "Art der geografischen Angabe" decoy
# ==========================================================================

def test_geo_area_blocklist_table_present():
    # Section 2's title "Art der geografischen Angabe" contains the
    # "geografische" keyword that would otherwise route geo_area to it;
    # the blocklist must carry it so geo_area stays on section 6.
    assert "art der geografischen angabe" in _GEO_AREA_TITLE_BLOCKLIST


def test_regression_art_der_geografischen_angabe_not_routed_to_geo_area(fixture_text):
    """Section 2 is titled "Art der geografischen Angabe" and its body is
    just "g.U. – Geschützte Ursprungsbezeichnung". Its title carries
    "geografische", so without the blocklist it would shadow the real
    area (section 6). The blocklist must keep geo_area on the section-6
    Gemeinden list, NOT the g.U. decoy."""
    _sections, titles, routed = _route_html(
        fixture_text("at_einziges_dokument_wachau.html")
    )
    # Confirm section 2 really is the decoy this test guards against.
    assert titles["2"] == "Art der geografischen Angabe"
    geo = routed.get("geo_area", "")
    assert "Geschützte Ursprungsbezeichnung" not in geo
    # The real area (section-6 commune list) is what landed.
    assert "Gemeinden" in geo
    assert "Mautern an der Donau" in geo


# ==========================================================================
# Section-7 grape parsing — dash-synonym split, colour split, fallback
# ==========================================================================

def test_grape_parsing_dash_synonym_split(fixture_text):
    """`Grüner Veltliner - Weißgipfler` → the canonical name BEFORE the
    " - " synonym separator resolves; the display name keeps the head
    only (the synonym is dropped). Repeated lines for one variety
    (Weißer Riesling appears twice) emit a single slug."""
    _sections, _titles, routed = _route_html(
        fixture_text("at_einziges_dokument_wachau.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    assert set(grapes["principal"]) == {"gruner-veltliner", "riesling"}
    by_slug = {d["slug"]: d for d in grapes["details"]}
    # Display name is the segment BEFORE " - " (the synonym is dropped).
    assert by_slug["gruner-veltliner"]["name"] == "Grüner Veltliner"
    assert "Weißgipfler" not in by_slug["gruner-veltliner"]["name"]
    # No principal/accessory split in the AT single document → all principal.
    assert grapes["accessory"] == []


def test_grape_parsing_colour_split_and_synonym_fallback(fixture_text):
    """Carnuntum section 7 mixes red and white varieties. ACTUAL behaviour
    pinned here:
      - the colour split is per-match (Chardonnay/Grüner Veltliner →
        blanc, Zweigelt → noir);
      - VIVC-folded names resolve to the canonical slug but carry an EMPTY
        colour: Blaufränkisch → lemberger (''), Weißer Burgunder →
        pinot-blanc (''). The empty colour is a divergence from the
        ideal — the slug is correct, the colour just isn't filled for
        these folds — so the style floor at stage 04 backfills it.
      - the synonym-fallback path works: "Weißer Burgunder - Klevner" /
        "- Pinot Blanc" resolve to pinot-blanc even though the canonical
        head needs the synonym to disambiguate."""
    _sections, _titles, routed = _route_html(
        fixture_text("at_section7_carnuntum.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    slugs = set(grapes["principal"])
    assert {"lemberger", "chardonnay", "gruner-veltliner",
            "pinot-blanc", "zweigelt"} == slugs
    by_slug = {d["slug"]: d for d in grapes["details"]}
    # Per-match colours where the lexicon fills them.
    assert by_slug["chardonnay"]["colour"] == "blanc"
    assert by_slug["gruner-veltliner"]["colour"] == "blanc"
    assert by_slug["zweigelt"]["colour"] == "noir"
    # VIVC folds resolve to the canonical slug but with empty colour.
    assert by_slug["lemberger"]["name"] == "Blaufränkisch"
    assert by_slug["lemberger"]["colour"] == ""
    assert by_slug["pinot-blanc"]["name"] == "Weißer Burgunder"
    assert by_slug["pinot-blanc"]["colour"] == ""
    # Three "Weißer Burgunder - …" lines collapse to one pinot-blanc slug.
    assert grapes["principal"].count("pinot-blanc") == 1
    assert grapes["accessory"] == []


def test_grape_role_keyword_in_section7_header_only():
    """The section-7 title may carry "Wichtigste Keltertraubensorte(n)"
    but that is the section header, not an inline role marker. The body
    is a flat variety list, so every match defaults to `principal`."""
    assert SECTION_ROLE_KEYWORDS["grape_varieties"][0] == "wichtigste keltertraubensorte"
    text = "Grüner Veltliner - Weißgipfler\nWeißer Riesling - Riesling"
    grapes = extract.parse_grapes(text)
    assert grapes["principal"] == ["gruner-veltliner", "riesling"]
    assert grapes["accessory"] == []


# ==========================================================================
# Style detection — German colour vocabulary + Prädikat / Schaumwein
# ==========================================================================

def test_style_colour_vocabulary_table():
    # The colour vocabulary must map both ß and ss spellings of the white
    # adjective to blanc; a missing entry silently drops a colour style.
    assert COLOUR_BY_KEYWORD["weißwein"] == "blanc"
    assert COLOUR_BY_KEYWORD["weisswein"] == "blanc"
    assert COLOUR_BY_KEYWORD["rotwein"] == "noir"
    assert COLOUR_BY_KEYWORD["roséwein"] == "rose"


def test_style_detection_colour_from_description(fixture_text):
    """parse_styles scans the description / category / additional sections.
    Wachau's section-4 body names "Weißweine" and "Rotweine", so the
    colour styles blanc + noir are detected."""
    sections, titles, _routed = _route_html(
        fixture_text("at_einziges_dokument_wachau.html")
    )
    styles = extract.parse_styles(sections, titles)
    assert "blanc" in styles
    assert "noir" in styles


def test_style_detection_praedikat_and_sekt_markers(fixture_text):
    """Wien's description names "Sekt" / "Schaumwein" (→ sparkling) and the
    Prädikat terms "Spätlese" / "Eiswein" (→ vendanges-tardives). The
    STYLE_MARKERS table must surface both alongside the colour styles."""
    sections, titles, _routed = _route_html(
        fixture_text("at_styles_wien.html")
    )
    styles = extract.parse_styles(sections, titles)
    assert "sparkling" in styles
    assert "vendanges-tardives" in styles
    # The white description also yields blanc.
    assert "blanc" in styles


def test_style_markers_cover_botrytis_and_strohwein():
    """The Austrian Prädikat ladder maps the botrytis / straw-wine tiers
    onto the noble-rot / raisin-wine leaves. Pin the table so a reorder
    can't silently drop one (markers are tried in declaration order)."""
    markers = {slug for _pat, slug in STYLE_MARKERS}
    assert "grains-nobles" in markers   # Beeren-/Trockenbeerenauslese, Ausbruch
    assert "vin-de-paille" in markers    # Strohwein
    assert "sparkling" in markers        # Sekt / Schaumwein
    # A literal Strohwein body resolves to vin-de-paille.
    found = [slug for pat, slug in STYLE_MARKERS if pat.search("Strohwein wird erzeugt.")]
    assert "vin-de-paille" in found


# ==========================================================================
# region.py — Bundesland derivation
# ==========================================================================

def test_bundesland_file_number_map():
    # The curated map is authoritative (hand-verified). DOPs map to one
    # state; the multi-state Landwein PGIs are tagged Österreich except
    # Steirerland, which is coextensive with Steiermark.
    assert region.bundesland_for_file_number("PDO-AT-A0205") == "Niederösterreich"  # Wachau
    assert region.bundesland_for_file_number("PDO-AT-A0228") == "Steiermark"        # Südsteiermark
    assert region.bundesland_for_file_number("PDO-AT-A0235") == "Wien"
    assert region.bundesland_for_file_number("PGI-AT-A0211") == "Österreich"        # Bergland
    assert region.bundesland_for_file_number("PGI-AT-A0213") == "Steiermark"        # Steirerland
    # Unknown file_number → empty string, never a guess.
    assert region.bundesland_for_file_number("PDO-AT-XXXXX") == ""
    assert region.bundesland_for_file_number("") == ""


def test_bundesland_text_scan_matches_standalone_noun():
    # A free-standing Bundesland noun is matched; the ASCII-folded variant
    # "Karnten" resolves to the diacritic canonical "Kärnten".
    assert region.find_bundesland_in_text("liegt in Niederösterreich heute") == "Niederösterreich"
    assert region.find_bundesland_in_text("Region Karnten im Süden") == "Kärnten"
    assert region.find_bundesland_in_text("ganz Österreich") == "Österreich"
    # No Bundesland token → None (and an empty string is safe).
    assert region.find_bundesland_in_text("Kein Bundesland hier.") is None
    assert region.find_bundesland_in_text("") is None


def test_bundesland_text_scan_earliest_match_wins():
    # Two Bundesland nouns in one string: the earliest position wins.
    assert region.find_bundesland_in_text("zuerst Steiermark dann Burgenland") == "Steiermark"


def test_regression_text_scan_skips_inflected_adjective():
    """ACTUAL behaviour, divergent from the ideal: the section-6 geo body
    says "die niederösterreichischen Gemeinden …" — an inflected ADJECTIVE
    with a glued suffix, not the bare noun "Niederösterreich". The needle
    is whitespace-delimited, so the adjective does NOT match and the scan
    returns None. This is harmless because the curated file_number map is
    the authoritative path (it runs first in derive_bundesland); the test
    pins the gap so a future edit to the matcher is a conscious choice."""
    assert region.find_bundesland_in_text("die niederösterreichischen Gemeinden") is None
    # The bare noun form DOES match — proving it's the inflection, not the
    # state, that the scan misses.
    assert region.find_bundesland_in_text("in Niederösterreich") == "Niederösterreich"


def test_derive_bundesland_precedence():
    # explicit record['bundesland'] > curated file_number map > text scan.
    assert region.derive_bundesland(
        {"bundesland": "Wien", "file_number": "PDO-AT-A0205"}
    ) == "Wien"
    # Curated map wins over a misleading text candidate.
    assert region.derive_bundesland(
        {"file_number": "PDO-AT-A0228"}, "irgendwo in Niederösterreich"
    ) == "Steiermark"
    # Text scan is the fallback only when the file_number is unknown.
    assert region.derive_bundesland(
        {"file_number": "PDO-AT-ZZZZZ"}, "das Gebiet liegt in der Steiermark"
    ) == "Steiermark"
    # Nothing resolves → empty string.
    assert region.derive_bundesland({"file_number": "PDO-AT-ZZZZZ"}, "nichts") == ""


def test_derive_bundesland_end_to_end_wachau(fixture_text):
    """End-to-end through the real build path: Wachau's file_number
    PDO-AT-A0205 resolves to Niederösterreich via the curated map even
    though the section-6 text only carries the inflected adjective."""
    _sections, _titles, routed = _route_html(
        fixture_text("at_einziges_dokument_wachau.html")
    )
    bl = region.derive_bundesland(
        {"file_number": "PDO-AT-A0205"},
        routed.get("geo_area", ""),
        routed.get("link_to_terroir", ""),
        "Wachau",
    )
    assert bl == "Niederösterreich"
