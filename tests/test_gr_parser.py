"""Fixture-based regression tests for the Greece (GR) ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ parser.

Target modules:

  - scripts/_lib/gr/eniaio_engrafo.py — the Greek keyword/role tables plus
    the `greek_norm` comparator (casefold + polytonic/monotonic diacritic
    strip + FINAL SIGMA fold ς→σ + short parenthetical/slash inflection
    drop). The final-sigma fold is the critical seam: a Greek section
    title typed with a final ς (e.g. "Κυριότερες οινοποιήσιμες ποικιλίες")
    casefolds to a medial σ via capital Σ, so without the ς→σ fold the
    keyword table — typed with ς — would never match and the grape
    section would never route. See the GR section of CLAUDE.md and the
    module docstring.
  - scripts/gr/02_extract_pliegos.py — the EU-OJ HTML driver
    (slice_document_unic → extract_sections → route_sections →
    parse_grapes / parse_styles). Reuses the ES/IT/RO idiom: walk the
    `ti-grseq-1` headers, find the ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ anchor, keep a monotonic
    1→N run of role-titled top-level sections, route by Greek title
    keyword.
  - scripts/_lib/grape_entity.py — `_COLOUR_LETTER_TO_NAME` and
    `match_variety`. Greek section-7/8 variety lines carry an OIV colour
    code (Greek capital Β/Ν/Γ — glyph-identical to but distinct code
    points from Latin B/N/G — or Latin B/N/G/Rs/Rg). The colour-letter
    suffix overrides the variety's natural colour.

Real cached docs live under raw/gr/oj-pages/ (gitignored); the fixtures
here are short redacted excerpts under tests/fixtures/gr_*.html.

Assertions are on STRUCTURE (greek_norm behaviour, routed roles, slug set
+ colour split), not full-output snapshots.

DISCREPANCY (pinned to ACTUAL behaviour, flagged inline at
test_regression_2024_country_decoy_routes_as_geo_area): the post-2024
template's section "Χώρα στην οποία ανήκει η γεωγραφική περιοχή" (body
"Ελλάδα") carries the substring "γεωγραφική περιοχή", so it collides with
the geo_area keyword and — because it is NOT in _GEO_AREA_TITLE_BLOCKLIST —
the parser routes the "Ελλάδα" country decoy as geo_area. This is the GR
analogue of RO's "Țara căreia → România" decoy, which RO *does* blocklist
(see tests/test_ro_parser.py). The GR blocklist has the gap.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.gr.eniaio_engrafo import (  # noqa: E402
    _GEO_AREA_TITLE_BLOCKLIST,
    DOC_ANCHOR_NORM,
    SECTION_ROLE_KEYWORDS,
    greek_norm,
)
from _lib.grape_entity import _COLOUR_LETTER_TO_NAME  # noqa: E402

# 02_extract_pliegos starts with a digit, so import it by module path.
extract = importlib.import_module("gr.02_extract_pliegos")


def _route_html(html: str) -> tuple[dict, dict, dict]:
    """Slice → extract numbered sections → route, the way build_record drives
    them. Returns (sections, titles, routed)."""
    doc = extract.slice_document_unic(html)
    assert doc is not None, "ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ anchor must be found"
    sections, titles = extract.extract_sections(doc)
    routed = extract.route_sections(sections, titles)
    return sections, titles, routed


# ==========================================================================
# greek_norm — the comparator seam (final sigma + diacritics + inflection)
# ==========================================================================

def test_greek_norm_folds_final_sigma():
    """ς (U+03C2) and medial σ (U+03C3) collapse to the same key. This is
    THE critical fold: `.casefold()` of capital Σ yields medial σ, so a
    title rendered in capitals ("…ΠΟΙΚΙΛΙΕΣ") casefolds to a trailing σ
    while the keyword table is typed with ς — without the fold they never
    compare equal."""
    assert greek_norm("ποικιλίες") == greek_norm("ποικιλίεσ") == "ποικιλιεσ"
    # No final sigma survives in any normalised output.
    assert "ς" not in greek_norm("ΟΙΝΟΠΟΙΗΣΙΜΕΣ ΠΟΙΚΙΛΙΕΣ")
    # A capital-Σ title and a final-ς keyword normalise to the same key.
    assert greek_norm("Κυριότερες οινοποιήσιμες ποικιλίες") == greek_norm(
        "κυριοτερεσ οινοποιησιμεσ ποικιλιεσ"
    )


def test_greek_norm_strips_polytonic_and_monotonic_diacritics():
    # Polytonic accents (older OJ pages) collapse to the monotonic / bare
    # base, so the anchor matches regardless of accent style.
    assert greek_norm("ΕΝΙΑΊΟ ΈΓΓΡΑΦΟ") == greek_norm("ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ")
    assert greek_norm("ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ") == DOC_ANCHOR_NORM == "ενιαιο εγγραφο"


def test_greek_norm_drops_short_inflection_groups():
    # The combined singular/plural template splices `(εσ)` into a heading;
    # greek_norm drops short (≤5-char) parens so the canonical wording is
    # contiguous again.
    assert greek_norm("Κύρια(εσ) ποικιλία(εσ)") == greek_norm("Κύρια ποικιλία")
    # The post-2024 slash variant `ποικιλίας/-ών` drops the same way.
    assert greek_norm("ποικιλίας/-ών αμπέλου") == "ποικιλιασ αμπελου"
    # But a real long alternation (`λευκός/ερυθρός`) is preserved (the
    # trailing-letter lookahead leaves the slash in place).
    assert "/" in greek_norm("λευκός/ερυθρός")


def test_regression_final_sigma_section7_routes_to_grapes(fixture_text):
    """The Mantinia section-7 title "Κυριότερες οινοποιήσιμες ποικιλίες"
    ends in a final ς. Its body must route to grape_varieties — this is
    the exact title that the final-sigma fold first unblocked (per the
    module docstring + CLAUDE.md GR section). Without the ς→σ fold the
    title would never match the `ποικιλίες`/`ποικιλιεσ` keyword."""
    _sections, titles, routed = _route_html(
        fixture_text("gr_eniaio_engrafo_mantinia.html")
    )
    # The section-7 title carries a final sigma.
    assert titles["7"].endswith("ποικιλίες")
    assert "grape_varieties" in routed
    # Its body (the variety table), not section 6's area body, landed.
    assert "Μοσχοφίλερο" in routed["grape_varieties"]
    assert "επαρχία Μαντινε" not in routed["grape_varieties"]


# ==========================================================================
# HTML driver — anchor slice + section routing
# ==========================================================================

def test_anchor_slice_drops_modification_preamble(fixture_text):
    """The modification-preamble template carries an outer
    ΑΙΤΗΣΗ-ΓΙΑ-ΤΡΟΠΟΠΟΙΗΣΗ block (numbered 1 / 2.1) BEFORE the inner
    ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ anchor; slice_document_unic must drop it so the
    preamble's own numbered headers don't pollute the section run."""
    html = fixture_text("gr_eniaio_engrafo_mantinia.html")
    doc = extract.slice_document_unic(html)
    assert doc is not None
    # The preamble marker text is gone — slice starts at the anchor.
    assert "ΠΡΟΟΙΜΙΟ" not in doc
    assert "ΑΙΤΗΣΗ ΓΙΑ ΤΡΟΠΟΠΟΙΗΣΗ" not in doc
    assert doc.lstrip().startswith("<p")


def test_section_role_routing_mantinia(fixture_text):
    """The Greek title keywords route the four semantic roles downstream
    consumers depend on: Καταχωρισμένη ονομασία → name, Οριοθετημένη
    γεωγραφική περιοχή → geo_area, …ποικιλίες → grape_varieties,
    Περιγραφή του δεσμού → link_to_terroir."""
    _sections, titles, routed = _route_html(
        fixture_text("gr_eniaio_engrafo_mantinia.html")
    )
    assert titles["1"] == "Καταχωρισμένη ονομασία"
    for role in ("name", "geo_area", "grape_varieties", "link_to_terroir"):
        assert role in routed, role
    # Section 6 body (area prose), NOT the grape table, lands in geo_area.
    assert "επαρχία Μαντινε" in routed["geo_area"]
    assert "Μοσχοφίλερο" not in routed["geo_area"]
    # Section 8 body lands in link_to_terroir.
    assert "οροπεδίου" in routed["link_to_terroir"]


def test_section_keys_are_number_prefixed(fixture_text):
    """extract_sections keys sections by their numeric prefix only; the
    nested per-style sub-headers and the all-caps preamble blocks must not
    register as top-level numbered sections."""
    html = fixture_text("gr_eniaio_engrafo_mantinia.html")
    doc = extract.slice_document_unic(html)
    sections, titles = extract.extract_sections(doc)
    assert set(sections) == set(titles)
    for num in sections:
        assert num[0].isdigit(), f"section key {num!r} should be number-prefixed"


def test_paren_inflected_titles_still_route_santorini(fixture_text):
    """Santorini's titles are the combined-inflection variant with `(εσ)`
    parenthetical suffixes ("Ονομασία(εσ)", "Κύρια(εσ) οινοποιήσιμη(εσ)
    ποικιλία(εσ) σταφυλιού") AND final sigma. greek_norm drops the short
    parens + folds the sigma, so name + grape_varieties still route."""
    _sections, titles, routed = _route_html(
        fixture_text("gr_eniaio_engrafo_santorini.html")
    )
    assert titles["1"] == "Ονομασία(εσ)"
    assert "(εσ)" in titles["7"]
    assert "name" in routed
    assert "grape_varieties" in routed
    assert "Ασύρτικο" in routed["grape_varieties"]


# ==========================================================================
# §6/§7/§8 variety list — OIV colour codes (Greek Β/Ν vs Latin B/N/Rs)
# ==========================================================================

def test_colour_letter_table_greek_and_latin():
    """The shared colour-letter table maps both the Greek capitals (Β/Ν/Γ,
    distinct code points from Latin) and the Latin codes (B/N/G/Rs/Rg) to
    the same colour buckets. A missing Greek entry would silently degrade
    these to fuzzy matches (see the colour-letter-lookbehind memory)."""
    # Greek capital Beta U+0392 is NOT Latin B U+0042 — distinct code points.
    assert ord("Β") == 0x392 and ord("B") == 0x42
    assert _COLOUR_LETTER_TO_NAME["Β"] == "blanc"
    assert _COLOUR_LETTER_TO_NAME["Ν"] == "noir"
    assert _COLOUR_LETTER_TO_NAME["Γ"] == "gris"
    assert _COLOUR_LETTER_TO_NAME["Rs"] == "rose"


def test_grape_colour_split_santorini(fixture_text):
    """Santorini §7: every Β-suffixed variety resolves blanc, the lone
    Rs-suffixed Ροδίτης resolves rose. Greek-script native varieties
    resolve to their English canonical slug."""
    _sections, _titles, routed = _route_html(
        fixture_text("gr_eniaio_engrafo_santorini.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    by_slug = {d["slug"]: d for d in grapes["details"]}
    # The blanc set (Greek capital Β colour code).
    assert {"aidani", "athiri", "assyrtiko", "monemvasia"} <= set(grapes["principal"])
    for slug in ("aidani", "athiri", "assyrtiko", "monemvasia"):
        assert by_slug[slug]["colour"] == "blanc", slug
    # Ροδίτης Rs → rose (Latin two-letter code).
    assert by_slug["roditis"]["colour"] == "rose"
    # Greek single documents carry no principal/accessory split.
    assert grapes["accessory"] == []
    assert set(grapes["principal"]) == set(by_slug)


def test_regression_colour_letter_overrides_natural_colour(fixture_text):
    """Mantinia §7 carries "Μοσχοφίλερο N" — Moschofilero's natural colour
    is rose (a grey-skinned variety), but the explicit Latin N colour code
    overrides it to noir. The colour-letter suffix is authoritative, and
    the display name keeps the colour letter while dropping the synonym
    blob after " - "."""
    _sections, _titles, routed = _route_html(
        fixture_text("gr_eniaio_engrafo_mantinia.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    by_slug = {d["slug"]: d for d in grapes["details"]}
    assert "moschofilero" in by_slug
    # Colour-letter N wins over the variety's natural rose.
    assert by_slug["moschofilero"]["colour"] == "noir"
    # Display name = segment before " - " (Latin synonym Μαυροφίλερο dropped).
    assert by_slug["moschofilero"]["name"] == "Μοσχοφίλερο N"
    assert "Μαυροφίλερο" not in by_slug["moschofilero"]["name"]
    # The Greek capital Β code on Ασπρούδες resolves blanc.
    assert by_slug["asproudes"]["colour"] == "blanc"


# ==========================================================================
# style detection
# ==========================================================================

def test_style_detection_santorini_liqueur(fixture_text):
    """Santorini's description/categories sections mention "Οίνος λικέρ"
    (vin de liqueur) + "λιαστά / λιασμένα" (sun-dried straw-wine). The
    style markers + the colour-keyword scan must surface vin-de-liqueur
    and blanc."""
    html = fixture_text("gr_eniaio_engrafo_santorini.html")
    doc = extract.slice_document_unic(html)
    sections, titles = extract.extract_sections(doc)
    styles = extract.parse_styles(sections, titles)
    assert "blanc" in styles
    assert "vin-de-liqueur" in styles


# ==========================================================================
# post-2024 (Reg. (EU) 2024/1143) template — section shifts + the decoy
# ==========================================================================

def test_2024_template_grapes_in_section_8_terroir_in_section_10(fixture_text):
    """In the newer template varieties move to section 8 and the terroir
    link to section 10; the `oj-ti-grseq-1` class variant still matches the
    `\\bti-grseq-1\\b` header regex. Both route correctly."""
    _sections, titles, routed = _route_html(
        fixture_text("gr_eniaio_engrafo_2024_makedonia.html")
    )
    assert "8" in titles and titles["8"].startswith("Ένδειξη της/των")
    assert "10" in titles and titles["10"].startswith("Δεσμός")
    grapes = extract.parse_grapes(routed["grape_varieties"])
    slugs = set(grapes["principal"])
    assert {"cabernet-sauvignon", "chardonnay", "ugni-blanc",
            "agiorgitiko", "xinomavro"} <= slugs
    assert "link_to_terroir" in routed
    assert "ηπειρωτικό" in routed["link_to_terroir"]


def test_2024_template_em_dash_synonym_and_colour_codes(fixture_text):
    """The §8 em-dash-bulleted list splits cleanly; mixed Greek (Ν) and
    Latin (N/B/Rs) colour codes resolve, and "Ugni Blanc B - Trebbiano"
    keeps the head name + drops the Latin synonym. Gewürztraminer carries
    an explicit Rs code → rose (overriding its natural white)."""
    _sections, _titles, routed = _route_html(
        fixture_text("gr_eniaio_engrafo_2024_makedonia.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    by_slug = {d["slug"]: d for d in grapes["details"]}
    assert by_slug["ugni-blanc"]["colour"] == "blanc"
    assert by_slug["cabernet-sauvignon"]["colour"] == "noir"
    assert by_slug["agiorgitiko"]["colour"] == "noir"  # Greek Ν
    assert by_slug["xinomavro"]["colour"] == "noir"  # Greek Ν
    # Explicit Rs code overrides Gewürztraminer's natural white.
    assert by_slug["gewurztraminer"]["colour"] == "rose"


def test_regression_2024_country_decoy_routes_as_geo_area(fixture_text):
    """DISCREPANCY pinned to ACTUAL behaviour.

    The post-2024 template's section "Χώρα στην οποία ανήκει η γεωγραφική
    περιοχή" (Country to which the area belongs) has the body "Ελλάδα"
    (Greece). Its title contains the substring "γεωγραφική περιοχή", so it
    collides with the geo_area keyword. Unlike the RO parser — which
    blocklists the equivalent "Țara căreia → România" decoy — the GR
    `_GEO_AREA_TITLE_BLOCKLIST` does NOT carry a "Χώρα στην οποία…" entry,
    so the parser routes the "Ελλάδα" country decoy as geo_area.

    This test pins the bug so a future blocklist fix is a conscious change.
    The fix would be to add greek_norm("Χώρα στην οποία ανήκει η γεωγραφική
    περιοχή") to _GEO_AREA_TITLE_BLOCKLIST; this assertion would then flip."""
    _sections, titles, routed = _route_html(
        fixture_text("gr_eniaio_engrafo_2024_makedonia.html")
    )
    # The decoy section carries the geographic substring.
    assert "γεωγραφική περιοχή" in titles["4"]
    # The "Χώρα στην οποία…" title is NOT in the blocklist (the gap).
    norm_block = {greek_norm(b) for b in _GEO_AREA_TITLE_BLOCKLIST}
    assert greek_norm(titles["4"]) not in norm_block
    # ACTUAL behaviour: the country decoy body is what landed in geo_area.
    assert routed["geo_area"].strip() == "Ελλάδα"


def test_geo_area_blocklist_blocks_category_section():
    """The blocklist that DOES exist keeps section 2/3 ("Είδος / Τύπος
    γεωγραφικής ένδειξης", "Κατηγορίες αμπελοοινικών προϊόντων") — which
    also carry the "γεωγραφικής" inflection — out of geo_area."""
    norm_block = {greek_norm(b) for b in _GEO_AREA_TITLE_BLOCKLIST}
    assert greek_norm("Είδος γεωγραφικής ένδειξης") in norm_block
    assert greek_norm("Τύπος γεωγραφικής ένδειξης") in norm_block
    # geo_area's own keyword list must NOT accidentally include the decoy.
    assert "χωρα στην οποια ανηκει η γεωγραφικη περιοχη" not in {
        greek_norm(kw) for kw in SECTION_ROLE_KEYWORDS["geo_area"]
    }
