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


def test_2024_template_country_decoy_is_blocklisted_and_section_9_routes(fixture_text):
    """The post-2024 template's section "Χώρα στην οποία ανήκει η (οριοθετημένη)
    γεωγραφική περιοχή" has the body "Ελλάδα" and a title that carries the
    geo_area keyword — the Greek twin of RO's "Țara căreia → România" decoy.
    Until 2026-09-24 the parser routed that "Ελλάδα" as the area and DROPPED
    section 9 "Συνοπτικός καθορισμός της οριοθετημένης γεωγραφικής περιοχής"
    altogether, because its genitive title matched no keyword; Μακεδονία's
    thirteen regional units never reached the record."""
    sections, titles, routed = _route_html(
        fixture_text("gr_eniaio_engrafo_2024_makedonia.html")
    )
    assert "γεωγραφική περιοχή" in titles["4"]
    norm_block = [greek_norm(b) for b in _GEO_AREA_TITLE_BLOCKLIST]
    assert any(b in greek_norm(titles["4"]) for b in norm_block)
    assert "9" in sections
    assert routed["geo_area"].strip() != "Ελλάδα"
    assert "Περιφερειακή Ενότητα Χαλκιδικής" in routed["geo_area"]


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


# ---------------------------------------------------------------------------
# Section-6 commune parsing + the GISCO LAU join (ΠΓΕ Άγιο Όρος regression).
#
# Reported 2026-09-23: the page published a GeoShape box of 37.93-39.27 N /
# 21.38-24.68 E for ΠΓΕ Άγιο Όρος — the whole of Στερεά Ελλάδα, ~42,000 km²,
# with its NORTHERN edge ~93 km south of the peninsula's southern tip, while
# the page's own prose correctly cited the Athos peninsula. Five independent
# defects chained into that one box; each test below pins one of them.
# ---------------------------------------------------------------------------

AYIO_OROS_GEO_AREA = (
    "Η οριοθετημένη περιοχή για την παραγωγή των οίνων Π.Γ.Ε. Άγιο Όρος "
    "περιλαμβάνει τη διοικητική περιοχή του Αγίου Όρους και το όμορο "
    "δημοτικό διαμέρισμα Ουρανούπολης του Δήμου Σταγίρων – Ακάνθου του "
    "Ν. Χαλκιδικής σε υψόμετρο από 10 ως 400 μέτρα."
)


def test_admin_area_idiom_yields_the_self_governing_unit():
    """`τη διοικητική περιοχή του X` names a unit that carries no δήμος /
    κοινότητα tier word. A bare `του` used to be listed as a region marker,
    so Mount Athos itself was deleted from its own area description."""
    from _lib.gr.commune import parse_commune_list

    names = parse_commune_list(AYIO_OROS_GEO_AREA)
    assert "Αγίου Όρους" in names


def test_subunit_of_a_dimos_does_not_pull_in_the_dimos():
    """The spec includes the δ.δ. Ουρανούπολης *of* the Δήμος Σταγίρων -
    Ακάνθου. Στάγιρα is a separate GISCO community and is not in the
    appellation, so the parent δήμος must not become a candidate."""
    from _lib.gr.commune import parse_commune_list

    names = parse_commune_list(AYIO_OROS_GEO_AREA)
    assert names == ["Αγίου Όρους", "Ουρανούπολης"]


def test_pseudo_municipal_tier_prefix_is_stripped_from_lau_names():
    """GISCO gives Greece's 68 self-governing communities the tier
    `Ψευδοδημοτική Κοινότητα`, which the LAU-side strip did not know — so
    Mount Athos was indexed under its tier word and unreachable by name."""
    from _lib.gr.commune import _normalise_commune

    assert (
        _normalise_commune("Ψευδοδημοτική Κοινότητα Άγιο Όρος (Αυτοδιοίκητο)")
        == _normalise_commune("Άγιο Όρος")
    )


def test_commune_alias_folds_the_declension_drift():
    """Greek administrative names drift between demotic and katharevousa
    and between nominative and genitive; GISCO follows ELSTAT, which is
    not consistent. Both sides must land on one key."""
    from _lib.gr.commune import _normalise_commune

    assert _normalise_commune("Αγίου Όρους") == _normalise_commune("Άγιο Όρος")
    assert _normalise_commune("Ουρανούπολης") == _normalise_commune(
        "Δημοτική Κοινότητα Ουρανοπόλεως"
    )


def test_region_marker_branches_are_not_shadowed_by_a_bare_article():
    """Alternation is first-match-wins, so listing bare `του` / `της`
    first made `περιφερειακή ενότητα` / `νομός` dead code — Τύρναβος kept
    "περιφερειακής Ενότητας Λάρισας" as a commune candidate."""
    from _lib.gr.commune import parse_commune_list

    names = parse_commune_list(
        "περιλαμβάνει τις Τοπικές Κοινότητες Δελερίων και Ροδιάς της "
        "περιφερειακής Ενότητας Λάρισας."
    )
    assert not any("νότητα" in n for n in names)
    assert "Δελερίων" in names


def test_elevation_clause_is_not_a_commune():
    from _lib.gr.commune import parse_commune_list

    assert not any(
        any(ch.isdigit() for ch in n) for n in parse_commune_list(AYIO_OROS_GEO_AREA)
    )


def test_region_facet_is_not_a_geometry_candidate():
    """`region` is a soft label that falls back to a text scan. Άγιο Όρος
    was drawn as Στερεά Ελλάδα because its lien mentions "…η Αττική" in a
    comparison 6 kB in. A facet must never become a polygon."""
    import inspect

    from _lib.gr.geometry import GRPolygonIndex

    src = inspect.getsource(GRPolygonIndex.nuts_region)
    candidates = src[src.index("candidates = ["):src.index("]", src.index("candidates = ["))]
    assert "region" not in candidates


def test_ayio_oros_carries_no_nuts_pin():
    """It resolves at community precision through the commune list; a
    coarse pin would mask a parser regression instead of letting it
    surface as stub-no-geometry."""
    from _lib.gr.nuts import override_ids

    assert override_ids("ayio-oros") is None


def test_ayio_oros_region_facet_is_macedonia():
    from _lib.gr.region import region_for_file_number

    assert region_for_file_number("PGI-GR-A0873") == "Μακεδονία"


def _bare_index():
    """A GRPolygonIndex with no data files — the polygon dicts are
    injected so the guards can be tested without the 6,142-row GISCO
    read."""
    from pathlib import Path

    from _lib.gr.geometry import GRPolygonIndex

    return GRPolygonIndex(Path("/nonexistent.gpkg"))


def test_ambiguous_commune_name_is_skipped_not_unioned():
    """Greek community names repeat nationwide — Ροδιά is six communes,
    one of them on Crete. Unioning them all stretched ΠΓΕ Τύρναβος from
    Thessaly to 35.3 N. An ambiguous name must contribute nothing and be
    reported."""
    from shapely.geometry import box

    idx = _bare_index()
    from _lib.gr.commune import _normalise_commune

    idx._lau_by_name = {
        _normalise_commune("Ροδιάς"): [("EL_22010101", box(21, 39, 22, 40)),
                                       ("EL_74010101", box(24, 35, 25, 36))],
        _normalise_commune("Δελερίων"): [("EL_22060103", box(22, 39.5, 22.2, 39.7))],
    }
    geom, stats = idx.commune_union(["Ροδιάς", "Δελερίων"])
    # neither Ροδιά sits in the δήμος (EL_2206) of the unambiguous match
    assert stats["matched"] == 1
    assert stats["names_ambiguous"] == ["Ροδιάς (2)"]
    assert geom.bounds[1] > 39  # nothing from Crete
    # …but one in the same δήμος as the others is the right one
    idx._lau_by_name[_normalise_commune("Ροδιάς")][0] = ("EL_22060105", box(21, 39, 22, 40))
    geom, stats = idx.commune_union(["Ροδιάς", "Δελερίων"])
    assert stats["matched"] == 2 and stats["names_ambiguous"] == []


def test_area_units_outrank_a_curated_nuts_pin_when_the_text_enumerates():
    """Πλαγιές Παϊκού and Τύρναβος enumerate their communities; until
    2026-09-24 a curated NUTS pin outranked the parse (which then drew them
    across the country). Now the units step wins when the guard passes and
    the pin is the fallback — here for a text that resolves nothing."""
    from _lib.gr.commune import _normalise_commune
    from shapely.geometry import box

    idx = _bare_index()
    idx._lau_by_name = {
        _normalise_commune("Τούμπας"): [("EL_23010301", box(22.6, 40.9, 22.7, 41.0))],
        _normalise_commune("Γρίβας"): [("EL_23010302", box(22.7, 40.9, 22.8, 41.0))],
    }
    idx._lau_keys_by_head = {}
    idx._nuts_by_id = {"EL524": box(22, 40.6, 22.6, 41.1), "EL523": box(22.6, 40.8, 23.2, 41.3)}
    text = "περιλαμβάνει τις περιοχές των Τοπικών Κοινοτήτων Γρίβας και Τούμπας."
    geom, source, stats = idx.resolve("PGI-GR-A1088", [], {"slug": "playies-paikou"}, area_text=text)
    assert (source, stats["how"], stats["matched"]) == ("gisco-commune-list", "area-units", 2)
    # a whole-unit text is left to the pin
    geom, source, stats = idx.resolve(
        "PGI-GR-A1088", [], {"slug": "playies-paikou"},
        area_text="περιλαμβάνει όλες τις περιοχές του νομού Πέλλας.",
    )
    assert (source, stats["how"]) == ("gisco-nuts-region", "nuts-override")
    # a bare homonym that GISCO also carries qualified in the same
    # prefecture is ambiguous, so a text naming only it falls to the pin
    idx._lau_by_name[_normalise_commune("Τούμπας Πέλλας")] = [("EL_23020101", box(22, 40.7, 22.1, 40.8))]
    idx._lau_keys_by_head = {"τούμπασ": {_normalise_commune("Τούμπας Πέλλας")}}
    geom, source, stats = idx.resolve(
        "PGI-GR-A1088", [], {"slug": "playies-paikou"},
        area_text="περιλαμβάνει τις περιοχές της Τοπικής Κοινότητας Τούμπας.",
    )
    assert source == "gisco-nuts-region"


def test_region_from_the_spec_cited_nuts_unit():
    """The PGI facet comes from the NUTS unit the geometry resolved to, not
    from the terroir narrative, which filed the 15 retsinas under Κρήτη,
    Achaia under Θράκη and Zakynthos under Νησιά Αιγαίου (live site before
    2026-09-24). Geographic regions cut across administrative ones."""
    from _lib.gr.region import REGIONS, region_for_nuts_ids

    assert region_for_nuts_ids(["EL434"]) == "Κρήτη"            # Χανιά
    assert region_for_nuts_ids(["EL30"]) == "Στερεά Ελλάδα"      # retsina cluster
    assert region_for_nuts_ids(["EL632"]) == "Πελοπόννησος"      # Αχαΐα
    assert region_for_nuts_ids(["EL633"]) == "Πελοπόννησος"      # Ηλεία
    assert region_for_nuts_ids(["EL631"]) == "Στερεά Ελλάδα"     # Αιτωλοακαρνανία
    assert region_for_nuts_ids(["EL621"]) == "Ιόνια Νησιά"       # Ζάκυνθος
    assert region_for_nuts_ids(["EL515"]) == ""                  # Θάσος, Καβάλα straddles
    assert region_for_nuts_ids(["EL513"]) == "Θράκη"             # Ροδόπη
    assert region_for_nuts_ids(["EL524", "EL523"]) == "Μακεδονία"
    # straddling or mixed units resolve to nothing, never to a guess
    assert region_for_nuts_ids(["EL307"]) == ""
    assert region_for_nuts_ids(["EL51", "EL52", "EL53"]) == ""
    assert region_for_nuts_ids(["EL434", "EL621"]) == ""
    assert region_for_nuts_ids([]) == ""
    from _lib.gr import region as gr_region
    assert set(gr_region._REGION_BY_NUTS.values()) <= set(REGIONS)


def test_review_2026_09_24_subunit_and_plural_markers():
    """Findings of the 2026-09-24 review of the Άγιο Όρος parser change."""
    from _lib.gr.commune import parse_commune_list

    # the δήμος sweep is capital-anchored: it must not eat the next item
    assert parse_commune_list(
        "περιλαμβάνει την τοπική κοινότητα Δαμασίου του Δήμου Τυρνάβου και Δελερίων."
    ) == ["Δαμασίου", "Δελερίων"]
    # … nor a nomos qualifier after the δήμος
    assert parse_commune_list(
        "Δημοτικής Ενότητας Λεύκης του Δήμου Σητείας του Νομού Λασιθίου"
    ) == ["Λεύκης"]
    # a multi-word sub-unit still drops its δήμος (the Στάγιρα case)
    assert parse_commune_list(
        "Περιλαμβάνει το δημοτικό διαμέρισμα Αγίου Παύλου του Δήμου Σταγίρων – Ακάνθου."
    ) == ["Αγίου Παύλου"]
    assert parse_commune_list(
        "Δημοτικής Ενότητας Νίκου Καζαντζάκη του Δήμου Αρχανών - Αστερουσίων"
    ) == ["Νίκου Καζαντζάκη"]
    # all-caps headings keep working without IGNORECASE on the names
    assert parse_commune_list(
        "ΤΟ ΔΗΜΟΤΙΚΟ ΔΙΑΜΕΡΙΣΜΑ ΟΥΡΑΝΟΥΠΟΛΗΣ ΤΟΥ ΔΗΜΟΥ ΣΤΑΓΙΡΩΝ - ΑΚΑΝΘΟΥ"
    ) == ["ΟΥΡΑΝΟΥΠΟΛΗΣ"]
    # the genitive plural moves the accent: κοινοτήτων, not κοινότητων
    assert parse_commune_list(
        "των Τοπικών Κοινοτήτων Αργυροπουλείου και Βρυοτόπου"
    ) == ["Αργυροπουλείου", "Βρυοτόπου"]
    assert parse_commune_list(
        "στις Τοπικές Κοινότητες Αργυροπουλείου, Δαμασίου"
    ) == ["Αργυροπουλείου", "Δαμασίου"]
    # "καθώς και" separates list items like "και"
    assert parse_commune_list("Φαρακλάτων καθώς και Πόρου") == ["Φαρακλάτων", "Πόρου"]
    # Άγιο Όρος itself is unchanged
    assert parse_commune_list(
        "Περιλαμβάνει τη διοικητική περιοχή του Αγίου Όρους και το όμορο δημοτικό "
        "διαμέρισμα Ουρανούπολης του Δήμου Σταγίρων - Ακάνθου."
    ) == ["Αγίου Όρους", "Ουρανούπολης"]


def test_trailing_genitive_qualifier_regex():
    from _lib.gr.geometry import _GENITIVE_QUALIFIER_RE

    assert _GENITIVE_QUALIFIER_RE.sub("", "Δαμασίου της Λάρισας") == "Δαμασίου"
    assert _GENITIVE_QUALIFIER_RE.sub("", "Βλαχάτων της Κεφαλονιάς") == "Βλαχάτων"
    assert _GENITIVE_QUALIFIER_RE.sub("", "Λεύκης του Νομού Λασιθίου") == "Λεύκης"
    # a lower-case tail is prose, not a place qualifier
    assert _GENITIVE_QUALIFIER_RE.sub("", "Αγίου Όρους") == "Αγίου Όρους"


def test_epanomi_is_drawn_from_its_community_not_a_nuts_pin():
    from _lib.gr.nuts import override_ids
    from _lib.gr.region import region_for_file_number

    assert override_ids("epanomi") is None
    assert region_for_file_number("PGI-GR-A0858") == "Μακεδονία"


def test_makedonia_pgi_is_geographic_macedonia_not_thrace():
    """OJ C/2026/2625 section 9 lists the thirteen Macedonian regional
    units; the earlier EL51 pin drew Evros, Xanthi and Rodopi as well."""
    from _lib.gr.nuts import override_ids
    from _lib.gr.region import region_for_nuts_ids

    ids = override_ids("makedonia")
    assert ids == ["EL514", "EL515", "EL52", "EL53"]
    assert "EL51" not in ids and "EL511" not in ids
    # EL515 straddles Μακεδονία and the Aegean islands, so the facet is curated
    from _lib.gr.region import region_for_file_number

    assert region_for_nuts_ids(ids) == ""
    assert region_for_file_number("PGI-GR-A1616") == "Μακεδονία"


def test_thasos_kavala_paggaio_share_a_nuts_unit_but_not_a_region():
    """EL515 "Θάσος, Καβάλα": the island PGI is Νησιά Αιγαίου by the cited
    article, the two mainland PGIs Μακεδονία — curated, since the unit itself
    resolves to nothing."""
    from _lib.gr.region import region_for_file_number

    assert region_for_file_number("PGI-GR-A0121") == "Νησιά Αιγαίου"   # Θάσος
    assert region_for_file_number("PGI-GR-A0137") == "Μακεδονία"       # Καβάλα
    assert region_for_file_number("PGI-GR-A0865") == "Μακεδονία"       # Παγγαίο


def test_limits_phrase_is_a_list_separator_only_before_a_list_noun():
    from _lib.gr.commune import _normalise_commune, parse_commune_list

    assert parse_commune_list(
        "περιλαμβάνει τις περιοχές που βρίσκονται στα διοικητικά όρια των οικισμών "
        "Αγοράς και Πηγαδιών Μεγάλου Αλεξάνδρου της δημοτικής κοινότητας Δοξάτου."
    )[:3] == ["Αγοράς", "Πηγαδιών Μεγάλου Αλεξάνδρου", "Δοξάτου"]
    assert parse_commune_list("στα διοικητικά όρια των Δ.Δ. Πύλης, Σκούρτων")[:2] == ["Πύλης", "Σκούρτων"]
    # a unit name after the phrase is not a list: prose, dropped as before
    assert parse_commune_list(
        "περιλαμβάνει την περιοχή στα διοικητικά όρια της Περιφερειακής Ενότητας (πρώην Νομός) Ευβοίας"
    ) == []
    # ΠΟΠ Ρομπόλα's "Βλαχάτων" is GISCO's "Βλαχάτων Εικοσιμίας"
    assert _normalise_commune("Βλαχάτων") == "βλαχάτων εικοσιμίασ"


def test_aegean_sea_pgi_spans_both_aegean_nuts_regions():
    """Its spec cites GR42 and GR41; the name match kept only the south."""
    from _lib.gr.nuts import override_ids
    from _lib.gr.region import region_for_nuts_ids

    assert override_ids("aegeo-pelagos") == ["EL41", "EL42"]
    assert region_for_nuts_ids(["EL41", "EL42"]) == "Νησιά Αιγαίου"


def test_stage04_summary_skips_the_2024_template_country_section():
    from _lib.summaries import derive_summary

    rec = {"country": "gr", "sections": {"1": "«Μακεδονία»", "3": "Ελλάδα"},
           "section_titles": {"1": "Ονομασία(ες)",
                              "3": "Χώρα στην οποία ανήκει η οριοθετημένη γεωγραφική περιοχή"}}
    assert derive_summary(rec) == "«Μακεδονία»"
    rec["section_titles"]["3"] = "Κατηγορίες αμπελοοινικών προϊόντων"
    assert derive_summary(rec) == "«Μακεδονία» Ελλάδα"
