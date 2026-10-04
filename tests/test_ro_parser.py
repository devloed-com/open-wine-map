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
    judeţ names + terroir prose. (commit c4bb2f9 — density fallback.) Since
    2026-09-24 it returns (name, [județe]) pairs, scoped to the county
    header each name sits under."""
    html = fixture_text("ro_document_unic_dragasani.html")
    doc = extract.slice_document_unic(html)
    sections, _titles = extract.extract_sections(doc)
    out = extract._harvest_communes_fallback(sections, _titles)
    low = {c.lower() for c, _judete in out}
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


def test_commune_split_si_conjunction_both_diacritic_forms():
    """_COMMUNE_SPLIT_RE splits on the conjunction in its comma-below "și"
    (U+0219), legacy cedilla "şi" (U+015F) and bare "si" forms. The cedilla
    form used to be a documented gap ("comma is the dominant separator, so
    harmless"); the 2026-09-24 recall diagnosis found it gluing chunks in
    8 records ("satele Blăjani şi Soreşti", "Drăguşeni şi Urleşti"), so
    the gap was closed deliberately."""
    for conj in ("și", "şi", "si"):
        out = [c.lower() for c in commune.parse_commune_list(
            f"comuna Prundeni {conj} comuna Babeni")]
        assert "prundeni" in out and "babeni" in out, conj


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


# ---------------------------------------------------------------------------
# Județ harvesting + the județ-masked commune union (2026-09-23).
#
# Romanian commune names repeat heavily across counties — Izvoarele is 5
# communes, Fântânele 7, Ștefan cel Mare 6 — and the union took every
# homonym. 11 of the 13 RO commune-union records were inflated, several to
# the full width of the country: Colinele Dobrogei, on the Black Sea, ran
# from 21.35°E to 29.02°E.
# ---------------------------------------------------------------------------

def test_parse_judet_list_reads_both_marker_spellings():
    """The EU document writes `judeţul X`; the ONVPV caiet abbreviates it
    to `jud. X` inline per locality."""
    from _lib.ro.commune import parse_judet_list

    assert parse_judet_list("în judeţul Constanţa şi judeţul Tulcea") == [
        "constanta", "tulcea",
    ]
    assert parse_judet_list("1.Blaj – jud. Alba: - localităţile componente") == ["alba"]


def test_parse_judet_list_ignores_communes():
    from _lib.ro.commune import parse_judet_list

    assert parse_judet_list("comuna Izvoarele, satul Fântânele") == []


def _ro_index_with(lau, judete):
    from pathlib import Path

    from _lib.ro.geometry import ROPolygonIndex

    idx = ROPolygonIndex(figshare_gpkg=Path("/nonexistent.gpkg"))
    idx._lau_by_name = lau
    idx._judet_by_name = judete
    return idx


def test_commune_union_keeps_only_the_in_judet_homonym():
    from _lib.ro.commune import _normalise_commune
    from shapely.geometry import box

    idx = _ro_index_with(
        {_normalise_commune("Izvoarele"): [box(28.0, 44.0, 28.1, 44.1),
                                           box(24.0, 46.0, 24.1, 46.1)]},
        {"constanta": box(27.5, 43.5, 29.0, 44.8)},
    )
    geom, stats = idx.commune_union(["Izvoarele"], ["constanta"])
    assert stats["matched"] == 1
    assert geom.bounds[0] > 27  # the Transylvanian homonym is gone


def test_commune_union_drops_a_commune_outside_every_declared_judet():
    """The commune parser also scrapes place names out of surrounding
    prose; those land far outside the area (Abrud and Hațeg, ~400 km west
    of Dobrogea)."""
    from _lib.ro.commune import _normalise_commune
    from shapely.geometry import box

    idx = _ro_index_with(
        {_normalise_commune("Abrud"): [box(23.0, 46.2, 23.1, 46.3)]},
        {"constanta": box(27.5, 43.5, 29.0, 44.8)},
    )
    geom, stats = idx.commune_union(["Abrud"], ["constanta"])
    assert geom is None
    assert stats["names_outside_judet"] == ["Abrud"]


def test_commune_union_without_judete_skips_ambiguous_names():
    """No declared județ to disambiguate with — the name contributes
    nothing rather than every homonym."""
    from _lib.ro.commune import _normalise_commune
    from shapely.geometry import box

    idx = _ro_index_with(
        {_normalise_commune("Izvoarele"): [box(28.0, 44.0, 28.1, 44.1),
                                           box(24.0, 46.0, 24.1, 46.1)],
         _normalise_commune("Ostrov"): [box(27.9, 44.1, 28.0, 44.2)]},
        {},
    )
    geom, stats = idx.commune_union(["Izvoarele", "Ostrov"], [])
    assert stats["matched"] == 1
    assert stats["names_ambiguous"] == ["Izvoarele (2)"]
    assert geom.bounds[0] > 27


def test_judet_source_text_reads_section_titles():
    """Dealurile Moldovei's PDF→HTML conversion mangles the numbering, so
    its six county sub-headers become top-level section titles and the
    area body comes out empty. The counties must still be found."""
    from _lib.ro.commune import judet_source_text, parse_judet_list

    record = {
        "geo_area_brief": "",
        "section_roles": {"geo_area": ""},
        "section_titles": {"1": "6 Judeţul Iaşi", "1.1": "Judeţul Galaţi",
                           "1.2": "Judeţul Vaslui", "7": "Soiul principal"},
    }
    assert parse_judet_list(judet_source_text(record)) == ["iasi", "galati", "vaslui"]


# ---------------------------------------------------------------------------
# Recall fixes from the 2026-09-24 diagnosis (13 commune-union records,
# 559 → 719 matched communes). Each test pins one rule; the risks the
# diagnosis named for each rule are pinned as the negative cases.
# ---------------------------------------------------------------------------

def _names(text):
    return [c.lower() for c in commune.parse_commune_list(text)]


def test_abbreviated_and_bare_tier_words_are_stripped():
    """The Oltenia document writes `Com. X` / `Com X` / `Loc. X`; the
    caiete write `localităţile X` and the typo `Locatitatea X`. Olteniei
    went 20 → 119 matched on this and the tail rule together."""
    out = _names("Com. Iancu Jianu, Com Devesel, Loc. Piatra-Olt, "
                 "localităţile Buziaş, Locatitatea Corabia, cartierele Bucium")
    for want in ("iancu jianu", "devesel", "piatra-olt", "buziaş", "corabia", "bucium"):
        assert want in out, want


def test_bare_tier_word_still_needs_whitespace():
    """`Satu Nou` / `Comana` / `Comăneşti` are commune names, not a tier
    word plus a name. `Satu Mare` is BOTH a county and its seat: bare it
    is the county header (rejected), with `municipiul` it is the seat."""
    out = _names("comuna Satu Nou, Satu Mare, municipiul Satu Mare, Comana, Comăneşti")
    assert "satu nou" in out and "satu mare" in out
    assert out.count("satu mare") == 1
    assert "comana" in out and "comăneşti" in out


def test_glued_tier_word_is_repaired():
    """The PDF→text step loses the space: `ComunaDimitrie Cantemir`,
    `sateleTârzii`."""
    out = _names("ComunaDimitrie Cantemir, sateleTârzii, Municipiul Iaşi")
    assert "dimitrie cantemir" in out


def test_leading_cu_before_a_tier_word():
    assert "lugoj" in _names("Timişoara, cu oraşul Lugoj, cu localităţile Buziaş")


def test_descriptor_tail_singular_sat_and_bare_satele():
    out = _names("Com. Leu - sat Leu, Comuna Probota satele Probota, Perieni, "
                 "Comuna Prăjeşti satul Prăjeşt")
    assert "leu" in out and "probota" in out and "prăjeşti" in out
    # the narrow "- sat " form must not cut a hyphenated village name
    assert "domnești-sat" in _names("comuna Domnești-Sat")


def test_descriptor_tail_never_fires_at_chunk_start():
    """`localităţile componente Mediaş` / `cu localitatea Jamu Mare` used to
    be emptied by an unanchored tail cut; they are the commune itself."""
    out = _names("localităţile componente Mediaş, cu localitatea Jamu Mare")
    assert "mediaş" in out and "jamu mare" in out


def test_town_cu_tail_only_after_a_town_prefix():
    """`oraşul Urlaţi cu Arioneştii Noi` → Urlaţi. But `Malu cu Flori` is
    a commune whose name contains ` cu `, and `malu` is a different GISCO
    key — an unconditional cut would swap one commune for another."""
    assert "urlaţi" in _names("oraşul Urlaţi cu Arioneştii Noi")
    assert "malu cu flori" in _names("comuna Malu cu Flori")
    assert "malu cu flori" in _names("Malu cu Flori")


def test_commune_dash_tail_only_after_a_commune_prefix():
    assert "lungeşti" in _names("Com. Lungeşti - Lungeşti")
    # a hyphenated village listed on its own keeps its dash
    assert "stăneşti – lunca" in _names("Stăneşti – Lunca") or "stăneşti - lunca" in _names("Stăneşti – Lunca")


def test_county_seat_and_numeric_commune_survive_with_a_prefix():
    """`Iaşi` alone is a county header; `Municipiul Iaşi` is the county
    seat. `23 August` is a commune; a bare digit-first chunk is a list
    number. `Ip` is the shortest GISCO key."""
    out = _names("Judeţul Iaşi: Municipiul Iaşi, Municipiul Vaslui, "
                 "Comuna 23 August, comuna Ip, 3. Bistriţa")
    assert "iaşi" in out and "vaslui" in out and "23 august" in out and "ip" in out
    assert "3" not in out and "bistriţa" not in [n for n in out if n.startswith("3")]


def test_bare_county_name_is_still_rejected():
    out = _names("Judeţul Tulcea: Tulcea, comuna Somova")
    assert "tulcea" not in out and "somova" in out


def test_page_footer_and_heading_words_are_not_communes():
    out = _names("Localități din judeţul Buzău: comuna Năeni, Page 3 of 13, "
                 "Localitatea, centrele, Pagina 2 din 9")
    assert "năeni" in out
    for bad in ("localități din", "localitatea", "centrele", "page", "pagina"):
        assert bad not in out, bad


def test_typographic_dashes_fold_to_hyphen():
    n = commune._normalise_commune
    assert n("Bereşti—Meria") == n("Bereşti-Meria") == "beresti meria"


def test_spelling_aliases_map_only_the_spec_side():
    from _lib.ro.commune import _SPELLING_ALIASES
    n = commune._normalise_commune
    assert _SPELLING_ALIASES[n("Isacea")] == n("Isaccea")
    assert _SPELLING_ALIASES[n("Năieni")] == n("Năeni")
    # the normaliser itself is unchanged — the alias is applied in the resolver
    assert n("Isacea") == "isacea"


def test_scoped_parse_tags_each_name_with_its_section_county():
    """Griviţa is a commune in both Galaţi and Vaslui, and Dealurile Moldovei
    lists it under each county header. Record-wide that is an ambiguity;
    section-scoped it is two matches."""
    text = ("Judeţul Galaţi: Comuna Griviţa, satele Griviţa, Călmăţui; "
            "Comuna Iveşti. Judeţul Vaslui: Comuna Griviţa, Comuna Costeşti.")
    pairs = commune.parse_commune_list_scoped(text)
    by = {}
    for name, judete in pairs:
        by.setdefault(name.lower(), []).append(tuple(judete))
    assert by["griviţa"] == [("galati",), ("vaslui",)]
    assert by["iveşti"] == [("galati",)]
    assert by["costeşti"] == [("vaslui",)]


def test_scoped_parse_names_before_any_header_carry_no_county():
    pairs = commune.parse_commune_list_scoped("comuna Prundeni, oraşul Băbeni")
    assert [j for _n, j in pairs] == [[], []]


def test_scoped_union_masks_each_name_to_its_own_county():
    from pathlib import Path

    from _lib.ro.geometry import ROPolygonIndex
    from shapely.geometry import box

    idx = ROPolygonIndex(figshare_gpkg=Path("/nonexistent.gpkg"))
    n = commune._normalise_commune
    galati, vaslui = box(27.5, 45.5, 28.2, 46.2), box(27.2, 46.2, 28.2, 46.9)
    idx._judet_by_name = {"galati": galati, "vaslui": vaslui}
    idx._lau_by_name = {n("Griviţa"): [box(27.8, 45.8, 27.9, 45.9), box(27.6, 46.5, 27.7, 46.6)]}
    geom, st = idx.commune_union(
        ["Griviţa"], ["galati", "vaslui"],
        scoped=[("Griviţa", ["galati"]), ("Griviţa", ["vaslui"])],
    )
    assert st["matched"] == 2 and st["n_ambiguous"] == 0
    assert geom.bounds[1] < 46 < geom.bounds[3]
    # record-wide alone cannot tell them apart
    _g, st2 = idx.commune_union(["Griviţa"], ["galati", "vaslui"])
    assert st2["n_ambiguous"] == 1


def test_fallback_scopes_names_to_a_county_titled_section(fixture_text):
    """Dealurile Moldovei: section 6 is empty and its county lists arrived
    as pseudo-sections titled `6 Judeţul Iaşi`, `Judeţul Galaţi`, … The
    fallback must accept those on the title alone and tag every name."""
    sections = {"1": "Comuna Deleni, satele Deleni, Poiana; Comuna Cotnari.",
                "1.1": "Comuna Griviţa, Comuna Iveşti.",
                "8": "Legătura cu aria geografică: Podgoria Cotnari este …"}
    titles = {"1": "6 Judeţul Iaşi", "1.1": "Judeţul Galaţi", "8": "Descrierea legăturii"}
    out = extract._harvest_communes_fallback(sections, titles)
    by = {name.lower(): judete for name, judete in out}
    assert by["deleni"] == ["iasi"] and by["cotnari"] == ["iasi"]
    assert by["griviţa"] == ["galati"] and by["iveşti"] == ["galati"]


# ---------------------------------------------------------------------------
# Review 2026-09-24 (ro-1 … ro-6): county-header harvesting, the undashed
# "localităţile componente" tail, dashed commune names, missing masks.
# ---------------------------------------------------------------------------

def _keys(text):
    return [commune._normalise_commune(c) for c in commune.parse_commune_list(text)]


def test_tier_prefixed_commune_after_a_header_is_not_a_second_county():
    """Călăraşi and Satu Mare are communes as well as counties. Read as a
    second county, "comuna Călăraşi" widened the mask to Călăraşi county and
    made the Dolj commune itself ambiguous."""
    assert commune.parse_commune_list_scoped(
        "Judeţul Dolj, comuna Călăraşi, comuna Sadova"
    ) == [("Călăraşi", ["dolj"]), ("Sadova", ["dolj"])]
    assert commune.parse_judet_list(
        "Judeţul Suceava, comuna Satu Mare, comuna Dărmăneşti"
    ) == ["suceava"]
    # a real county list is still read whole
    assert commune.parse_judet_list("în judeţele Iaşi, Vaslui şi Galaţi") == [
        "iasi", "vaslui", "galati",
    ]


def test_second_header_on_the_same_line_opens_its_own_section():
    text = "Judeţul Galaţi, Tecuci, Iveşti, Judeţul Vaslui, Griviţa, Iveşti"
    assert commune.parse_commune_list_scoped(text) == [
        ("Tecuci", ["galati"]), ("Iveşti", ["galati"]),
        ("Griviţa", ["vaslui"]), ("Iveşti", ["vaslui"]),
    ]
    # a marker that continues the county list is not a section of its own
    assert commune.parse_commune_list_scoped(
        "în judeţul Constanţa şi judeţul Tulcea: comuna Ostrov"
    ) == [("Ostrov", ["constanta", "tulcea"])]


def test_same_line_headers_resolve_each_homonym_in_its_own_county():
    """End to end: the Galaţi and Vaslui Iveşti are both kept, the Vaslui
    Griviţa too — merged under one scope they were all dropped as ambiguous."""
    from shapely.geometry import box

    n = commune._normalise_commune
    galati, vaslui = box(27.5, 45.5, 28.2, 46.2), box(27.2, 46.2, 28.2, 46.9)
    idx = _ro_index_with(
        {n("Tecuci"): [box(27.55, 45.8, 27.6, 45.85)],
         n("Iveşti"): [box(27.5, 45.6, 27.6, 45.7), box(27.5, 46.3, 27.6, 46.4)],
         n("Griviţa"): [box(27.8, 45.8, 27.9, 45.9), box(27.6, 46.5, 27.7, 46.6)]},
        {"galati": galati, "vaslui": vaslui},
    )
    text = "Judeţul Galaţi, Tecuci, Iveşti, Judeţul Vaslui, Griviţa, Iveşti"
    _geom, st = idx.commune_union(
        commune.parse_commune_list(text), commune.parse_judet_list(text),
        scoped=commune.parse_commune_list_scoped(text),
    )
    assert st["n_ambiguous"] == 0 and st["matched"] == 4


def test_header_with_descriptor_tail_or_genitive_opens_a_section():
    text = ("Judeţul Galaţi: Comuna Iveşti, Comuna Griviţa.\n"
            "Judeţul Vaslui – zona Huşi: Comuna Iveşti, Comuna Duda-Epureni")
    assert commune.parse_commune_list_scoped(text) == [
        ("Iveşti", ["galati"]), ("Griviţa", ["galati"]),
        ("Iveşti", ["vaslui"]), ("Duda-Epureni", ["vaslui"]),
    ]
    genitive = ("Judeţul Galaţi: Comuna Iveşti.\n"
                "Localităţile judeţului Vaslui: Comuna Iveşti")
    assert commune.parse_commune_list_scoped(genitive) == [
        ("Iveşti", ["galati"]), ("Iveşti", ["vaslui"]),
    ]
    # Sâmbureşti's caiet: the county was never harvested
    assert commune.parse_judet_list(
        "se întinde pe teritoriul judeţului Olt pe raza localitaţilor:"
    ) == ["olt"]


def test_undashed_localitati_componente_tail_is_cut():
    assert _keys("Municipiul Târnăveni localităţile componente Târnăveni, Botorca") == [
        "tarnaveni", "botorca",
    ]
    assert _keys("Municipiul Aiud localităţi componente Aiud") == ["aiud"]


def test_dash_in_a_commune_name_survives_a_descriptor_tail():
    """A "- satul …" / "cu satele …" descriptor marks where the village
    list starts, so the dash before it belongs to the name: Albeşti-
    Paleologu (Prahova), Bereşti-Meria (Galaţi). "albesti" and "beresti"
    are other GISCO keys."""
    assert _keys("Com. Albești - Paleologu - satul Albești - Paleologu") == [
        "albesti paleologu",
    ]
    assert _keys("Comuna Bereşti – Meria cu satele Slivna") == ["beresti meria"]
    # with no descriptor the dash still starts the village list
    assert _keys("Com. Lungeşti - Lungeşti") == ["lungesti"]


def test_missing_county_masks_are_reported(tmp_path, capsys):
    """Stage 04 reads the RO county masks from the GR stage's NUTS-3 file;
    without it the unions run unmasked, which must not be silent."""
    import json

    from _lib.ro.geometry import N_JUDETE, ROPolygonIndex

    idx = ROPolygonIndex(figshare_gpkg=tmp_path / "none.gpkg",
                         nuts3_geojson=tmp_path / "missing.geojson")
    assert idx.n_judete == 0
    assert "UNMASKED" in capsys.readouterr().err

    one = {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "properties": {"CNTR_CODE": "RO", "NUTS_NAME": "Constanța"},
        "geometry": {"type": "Polygon", "coordinates": [[[28, 44], [29, 44], [29, 45], [28, 44]]]},
    }]}
    path = tmp_path / "nuts3.geojson"
    path.write_text(json.dumps(one), encoding="utf-8")
    idx = ROPolygonIndex(figshare_gpkg=tmp_path / "none.gpkg", nuts3_geojson=path)
    assert idx.n_judete == 1
    assert f"1 of {N_JUDETE}" in capsys.readouterr().err


def test_a_county_header_that_runs_on_into_prose_does_not_swallow_the_next_marker():
    """'în judeţul Iaşi pe raza comunei Bohotin judeţul Vaslui, comuna Griviţa':
    the Iaşi header ends after 'Iaşi', so 'judeţul Vaslui' opens its own
    section and Griviţa is scoped to Vaslui (review 2026-09-24, ro-2)."""
    from _lib.ro.commune import parse_commune_list_scoped, parse_judet_list

    text = "în judeţul Iaşi pe raza comunei Bohotin judeţul Vaslui, comuna Griviţa"
    assert parse_judet_list(text) == ["iasi", "vaslui"]
    scoped = dict(parse_commune_list_scoped(text))
    assert scoped["Griviţa"] == ["vaslui"]


def test_a_repeated_head_after_the_dash_is_the_seat_village_even_with_a_descriptor():
    """'Com. Lungeşti - Lungeşti - satele …' names the commune Lungeşti; only a
    dash-joined name whose second half differs ('Albeşti - Paleologu') keeps
    the dash when a village descriptor follows (review 2026-09-24, ro-6)."""
    from _lib.ro.commune import parse_commune_list_scoped

    names = [n for n, _ in parse_commune_list_scoped(
        "Com. Lungeşti - Lungeşti - satele Fumureni, "
        "Com. Albeşti - Paleologu - satul Albeşti - Paleologu, "
        "Comuna Mihai Viteazu - Mihai Viteazu cu satele Cernavodă"
    )]
    assert names == ["Lungeşti", "Albeşti - Paleologu", "Mihai Viteazu"]
