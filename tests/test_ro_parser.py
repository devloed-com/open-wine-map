"""Regression + behaviour tests for the Romania (RO) parsers.

Three target modules, each a seam that has regressed historically (see
commit c4bb2f9 "Romania: complete coverage" and the RO section of CLAUDE.md):

  - scripts/ro/02_extract_pliegos.py — the EU-OJ DOCUMENT UNIC HTML driver
    (slice from the DOCUMENT-UNIC anchor, find numbered ti-grseq-1 section
    headers, route by Romanian title keyword, parse grapes/communes).
  - scripts/_lib/ro/document_unic.py — the Romanian keyword/role tables +
    the geo_area title blocklist (the "Țara căreia → România" decoy).
  - scripts/_lib/ro/caiet.py — the ONVPV caiet de sarcini PDF parser
    (Roman-numeral outline, "Soiurile albe:" / "Soiuri roşii:" colour split,
    form-feed folding, line-wise colour-segment join).
  - scripts/_lib/ro/commune.py — Romanian commune-list parsing (municipal
    tier prefixes, judeţ headers, "cu satele/localităţile componente" tails,
    parenthetical sub-village groups).

Real cached docs live under raw/ro/{oj-pages,national-specs}/ (gitignored).
The fixtures here are short redacted excerpts under tests/fixtures/.

Assertions are on STRUCTURE (routed roles, slug sets, commune membership,
colour split), not on full-output snapshots. Where a test pins ACTUAL parser
behaviour that diverges from the docstring's ideal (the cedilla-"şi" split
gap), the divergence is called out inline.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.ro import caiet, commune  # noqa: E402
from _lib.ro.document_unic import (  # noqa: E402
    _GEO_AREA_TITLE_BLOCKLIST,
    SECTION_ROLE_KEYWORDS,
)

# 02_extract_pliegos starts with a digit, so import it by module path.
extract = importlib.import_module("ro.02_extract_pliegos")


# ==========================================================================
# DOCUMENT UNIC HTML driver — section routing
# ==========================================================================

def _route_html(html: str) -> tuple[dict, dict, dict]:
    """Slice → extract numbered sections → route. Returns (sections, titles,
    routed) the way build_record drives them."""
    doc = extract.slice_document_unic(html)
    assert doc is not None, "DOCUMENT-UNIC anchor must be found"
    sections, titles = extract.extract_sections(doc)
    routed = extract.route_sections(sections, titles)
    return sections, titles, routed


def test_anchor_slice_drops_preamble(fixture_text):
    html = fixture_text("ro_document_unic_dragasani.html")
    doc = extract.slice_document_unic(html)
    # The COMUNICAREA… modification preamble before DOCUMENT UNIC is dropped.
    assert "COMUNICAREA UNEI MODIFICĂRI" not in doc
    assert doc.lstrip().startswith("<p")


def test_section_routing_dragasani(fixture_text):
    _sections, _titles, routed = _route_html(
        fixture_text("ro_document_unic_dragasani.html")
    )
    # The four semantic roles the downstream consumers depend on.
    assert "geo_area" in routed
    assert "grape_varieties" in routed
    assert "link_to_terroir" in routed
    # Section 6 body lands in geo_area (commune list), NOT terroir prose.
    assert "Judeţul Vâlcea" in routed["geo_area"]
    assert "Municipiul Drăgăşani" in routed["geo_area"]
    # Section 7 body lands in grape_varieties.
    assert "Cabernet Sauvignon" in routed["grape_varieties"]
    # Section 8 body lands in link_to_terroir.
    assert "Subcarpaţii Getici" in routed["link_to_terroir"]


def test_uppercase_titles_are_not_sections(fixture_text):
    """The SECTION_NUM_RE guard: a ti-grseq-1 header without a leading "N."
    number ("DOCUMENT UNIC", "DESCRIERE TEXTUALĂ CONCISĂ", "Vinurile
    albe/roze") must NOT register as a numbered section — otherwise the
    uppercase decoy bodies would shadow the real numbered sections."""
    html = fixture_text("ro_document_unic_dragasani.html")
    doc = extract.slice_document_unic(html)
    sections, titles = extract.extract_sections(doc)
    # Section keys are the numeric prefixes only.
    assert set(sections) == set(titles)
    for num in sections:
        assert num[0].isdigit(), f"section key {num!r} should be number-prefixed"
    # No section title is an all-caps decoy heading.
    assert "DOCUMENT UNIC" not in titles.values()
    assert "DESCRIERE TEXTUALĂ CONCISĂ" not in titles.values()


def test_grape_parsing_em_dash_synonym_split(fixture_text):
    """`Fetească regală B - Konigliche Madchentraube, …` → canonical name
    before the ` - ` synonym separator resolves; the synonym blob is only a
    fallback. The colour-letter suffix (B/N/G) is kept on the display name."""
    _sections, _titles, routed = _route_html(
        fixture_text("ro_document_unic_dragasani.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    slugs = set(grapes["principal"])
    assert {"cabernet-sauvignon", "chardonnay", "merlot", "sauvignon"} <= slugs
    assert "feteasca-neagra" in slugs and "feteasca-regala" in slugs
    # Display name is the segment BEFORE " - " (synonyms dropped), colour kept.
    by_slug = {d["slug"]: d for d in grapes["details"]}
    assert by_slug["feteasca-regala"]["name"] == "Fetească regală B"
    assert "Konigliche" not in by_slug["feteasca-regala"]["name"]
    assert by_slug["feteasca-regala"]["colour"] == "blanc"
    assert by_slug["cabernet-sauvignon"]["colour"] == "noir"
    # No principal/accessory split in RO DOCUMENT UNIC → all principal.
    assert grapes["accessory"] == []


def test_grape_parsing_bullet_prefixed_and_colour_letters(fixture_text):
    """Newer-template section 8 uses a leading "- " bullet plus a colour
    letter (B / N / G / Rs). The bullet must be stripped and Traminer Roz Rs
    must resolve (the colour-letter regex accepts the two-letter Rs/Rg code)."""
    _sections, _titles, routed = _route_html(
        fixture_text("ro_document_unic_2024_terasele-dunarii.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    slugs = set(grapes["principal"])
    assert {"aligote", "babeasca-neagra", "cabernet-sauvignon",
            "chardonnay", "feteasca-alba", "merlot", "sauvignon"} <= slugs
    # "Traminer Roz Rs - …Gewürztraminer" → the Gewürztraminer slug.
    assert "gewurztraminer" in slugs
    # "Pinot Gris G" → pinot-gris.
    assert "pinot-gris" in slugs


# ==========================================================================
# Regression: the "Țara căreia → România" decoy (geo_area blocklist)
# ==========================================================================

def test_geo_area_blocklist_table_present():
    # The blocklist must carry both diacritic and ASCII-folded forms of the
    # decoy title — a missing entry re-opens the regression.
    assert "țara căreia îi aparține" in _GEO_AREA_TITLE_BLOCKLIST
    assert "tara careia ii apartine" in _GEO_AREA_TITLE_BLOCKLIST


def test_regression_tara_careia_romania_decoy_not_routed_to_geo_area(fixture_text):
    """Reg. 2024/1143 template: section 3 is titled "Țara căreia îi aparține
    aria geografică delimitată" and its body is the single word "România".
    Its title carries "geografică" so it would otherwise shadow the real
    area in section 9. The blocklist must keep geo_area on section 9
    (commune list), NOT the România decoy. (commit c4bb2f9)"""
    _sections, _titles, routed = _route_html(
        fixture_text("ro_document_unic_2024_terasele-dunarii.html")
    )
    geo = routed.get("geo_area", "")
    assert geo.strip() != "România"
    # The real area (section 9 commune list) is what landed.
    assert "judeţul Teleorman" in geo
    assert "Zimnicea" in geo


def test_regression_2024_template_area_section_9_routed(fixture_text):
    """The newer "Descrierea concisă a arealului geografic delimitat" title
    (section 9) must route to geo_area. It is listed most-specific-first in
    the keyword table so it wins over the bare "aria geografică" decoy."""
    geo_keywords = SECTION_ROLE_KEYWORDS["geo_area"]
    assert geo_keywords[0] == "descrierea concisă a arealului geografic delimitat"
    _sections, _titles, routed = _route_html(
        fixture_text("ro_document_unic_2024_terasele-dunarii.html")
    )
    assert "judeţul Giurgiu" in routed["geo_area"]


# ==========================================================================
# Regression: descriptor-tail commune stripping + density fallback
# ==========================================================================

def test_regression_commune_descriptor_tail_stripped(fixture_text):
    """The "X cu satele/localităţile componente Y, Z" and
    "Municipiul X - localităţi componente …" descriptor tails must be
    dropped so the bare head commune name matches the GISCO key.
    (commit c4bb2f9 — commune.py descriptor-tail strip.)"""
    _sections, _titles, routed = _route_html(
        fixture_text("ro_document_unic_2024_terasele-dunarii.html")
    )
    communes = commune.parse_commune_list(routed["geo_area"])
    low = [c.lower() for c in communes]
    # "municipiul Zimnicea cu localităţile componente." → "Zimnicea".
    assert any(c == "zimnicea" for c in low)
    # "comuna Daia cu satele Daia, …" → head "Daia" kept.
    assert any(c == "daia" for c in low)
    # The descriptor words themselves must NOT leak in as commune candidates.
    assert not any("componente" in c for c in low)
    assert not any(c.startswith("satele") or c.startswith("satul") for c in low)


def test_regression_density_fallback_when_geo_area_thin(fixture_text):
    """When geo_area routing yields < 2 communes (mangled section numbering),
    build_record falls back to scanning every section body for commune-dense
    ones. _harvest_communes_fallback must recover the list and reject the
    judeţ names + terroir prose. (commit c4bb2f9 — density fallback.)"""
    html = fixture_text("ro_document_unic_dragasani.html")
    doc = extract.slice_document_unic(html)
    sections, _titles = extract.extract_sections(doc)
    out = extract._harvest_communes_fallback(sections)
    low = {c.lower() for c in out}
    # The grape section + terroir section are not commune-dense → ignored;
    # the section-6 area body is recovered.
    assert "drăgăşani" in low
    # Judeţ name "Vâlcea" must not survive as a commune.
    assert "vâlcea" not in low and "valcea" not in low
    # Grape names from section 7 must not leak in.
    assert "chardonnay" not in low and "merlot" not in low


# ==========================================================================
# commune.py — unit behaviours
# ==========================================================================

def test_commune_tier_prefix_and_judet_header():
    text = (
        "Judeţul Vâlcea: comuna Prundeni, oraşul Băbeni, "
        "municipiul Drăgăşani, satul Zlătărei."
    )
    out = [c.lower() for c in commune.parse_commune_list(text)]
    # Tier prefixes (comuna/oraşul/municipiul/satul) are stripped.
    assert "prundeni" in out
    assert "băbeni" in out
    assert "drăgăşani" in out
    assert "zlătărei" in out
    # The judeţ name itself is a section marker, never a commune.
    assert "vâlcea" not in out and "valcea" not in out


def test_commune_split_si_conjunction_modern_diacritic_only():
    """Quirk: _COMMUNE_SPLIT_RE splits on the conjunction only in its
    comma-below "și" (U+0219) or bare "si" forms — NOT the legacy cedilla
    "şi" (U+015F). Comma is the dominant real-world separator, so this gap
    is harmless in practice, but the test pins the asymmetry so a future
    edit to the split regex is a conscious choice, not an accident."""
    # Comma-below "și" splits cleanly.
    out_modern = [c.lower() for c in commune.parse_commune_list(
        "comuna Prundeni și comuna Babeni")]
    assert "prundeni" in out_modern and "babeni" in out_modern
    # Cedilla "şi" (U+015F) does NOT split — the two glue into one chunk.
    out_cedilla = [c.lower() for c in commune.parse_commune_list(
        "comuna Prundeni şi comuna Babeni")]
    assert "babeni" not in out_cedilla


def test_commune_parenthetical_subvillage_group_dropped():
    # "(satele X, Y şi Z)" enumerate hamlets and must be dropped whole,
    # leaving the head commune name un-fragmented.
    text = "comuna Daia (satele Daia, Dăiţa şi Plopşoru), comuna Greaca."
    out = [c.lower() for c in commune.parse_commune_list(text)]
    assert "daia" in out
    assert "greaca" in out
    assert not any(c in ("dăiţa", "plopşoru") for c in out)


def test_commune_satul_belongs_rewrite_keeps_commune():
    # "satul X aparţinând comunei Y" → the salient unit is Y (the commune).
    text = "satul Mărtineşti aparţinând comunei Cetăţeni, comuna Văleni."
    out = [c.lower() for c in commune.parse_commune_list(text)]
    assert "cetăţeni" in out
    assert "văleni" in out
    assert "mărtineşti" not in out


# ==========================================================================
# caiet.py — ONVPV caiet de sarcini PDF parser
# ==========================================================================

def _iana_caiet_text(fixture_text) -> str:
    """Load the redacted iana caiet excerpt and inject a real form-feed
    before the III. header to exercise the \\x0c → newline fold."""
    raw = fixture_text("ro_caiet_iana.txt")
    return raw.replace("\n   III.", "\x0c   III.", 1)


def test_caiet_section_split_roman_numerals(fixture_text):
    text = _iana_caiet_text(fixture_text)
    bodies, titles = caiet.split_sections(text)
    # I Definiţie → summary, II Legătura → terroir, III Delimitarea → area,
    # IV Soiurile → grapes.
    assert set(bodies) >= {"summary", "link_to_terroir", "geo_area", "grape_varieties"}
    assert "DEFINIŢIE" in titles["summary"]
    assert "SOIURILE DE STRUGURI" in titles["grape_varieties"]


def test_caiet_formfeed_fold_does_not_swallow_next_section(fixture_text):
    """A form-feed page break right before the "III." header must be folded
    to a newline so section II doesn't swallow section III's body."""
    text = _iana_caiet_text(fixture_text)
    bodies, _titles = caiet.split_sections(text)
    # geo_area (section III) was carved out as its own body, not glued to II.
    assert "Judeţul Vaslui" in bodies["geo_area"]
    assert "Judeţul Vaslui" not in bodies["link_to_terroir"]


def test_caiet_colour_split_white_vs_red(fixture_text):
    """"- soiuri albe:" → blanc, "- soiuri roşii/roze:" → noir. Each variety
    carries the colour of its header bucket.

    The red header "soiuri roşii/roze:" carries a "/roze" second-colour
    suffix; _COLOUR_HEADER_RE now consumes it (and the trailing colon), so
    the first red variety — Cabernet Sauvignon — resolves instead of being
    glued to a leftover "roze: " prefix. The bucket colour is the FIRST
    captured colour (roşii → noir)."""
    text = _iana_caiet_text(fixture_text)
    bodies, _titles = caiet.split_sections(text)
    grapes = caiet.parse_grapes(bodies["grape_varieties"])
    by_slug = {d["slug"]: d for d in grapes["details"]}
    # Whites
    for slug in ("aligote", "feteasca-regala", "welschriesling",
                 "feteasca-alba", "sauvignon", "muscat-ottonel"):
        assert by_slug[slug]["colour"] == "blanc", slug
    # Reds — Cabernet Sauvignon (the first, formerly eaten by "/roze") now
    # resolves alongside the rest of the red list.
    for slug in ("cabernet-sauvignon", "merlot", "pinot-noir",
                 "feteasca-neagra", "babeasca-neagra", "busuioaca-de-bohotin"):
        assert by_slug[slug]["colour"] == "noir", slug
    # No principal/accessory split — all principal.
    assert grapes["accessory"] == []
    assert set(grapes["principal"]) == set(by_slug)


def test_regression_caiet_wrapped_variety_name_not_sheared(fixture_text):
    """The red list wraps mid-list across a "Page 3 of 10" furniture line:
        - soiuri roşii/roze: …, Băbească neagră,
        Page 3 of 10
        Busuioacă de Bohotin.
    The line-wise colour-segment join (not per-physical-line split) must keep
    "Busuioacă de Bohotin" as one token. (commit c4bb2f9 — line-wise join.)"""
    text = _iana_caiet_text(fixture_text)
    bodies, _titles = caiet.split_sections(text)
    grapes = caiet.parse_grapes(bodies["grape_varieties"])
    slugs = set(grapes["principal"])
    # The wrapped tail variety resolves — would be lost if sheared.
    assert "busuioaca-de-bohotin" in slugs
    by_slug = {d["slug"]: d for d in grapes["details"]}
    assert by_slug["busuioaca-de-bohotin"]["colour"] == "noir"


def test_caiet_parse_caiet_record_fragment(fixture_text):
    """End-to-end: parse_caiet returns the merge-able record fragment with
    grapes, communes, styles, link_to_terroir, and the parser template tag."""
    text = _iana_caiet_text(fixture_text)
    frag = caiet.parse_caiet(text, "iana")
    assert frag["parser_template"] == "onvpv-caiet-de-sarcini-v1"
    assert frag["n_grapes"] == 12
    assert "blanc" in frag["styles"] and "rouge" in frag["styles"]
    # Communes from section III resolve (head names, satul-tails dropped).
    low = {c.lower() for c in frag["geo_communes"]}
    assert "perieni" in low and "ciocani" in low and "pogana" in low
    # Terroir text is the II. Legătura body.
    assert "temperat continental" in frag["link_to_terroir"]
