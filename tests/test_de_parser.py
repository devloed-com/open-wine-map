"""Fixture-based regression + behaviour tests for the Germany (DE) parsers.

Two parser surfaces, each a documented seam (see the DE section of
CLAUDE.md and the module docstrings):

  - scripts/de/02_extract_pliegos.py + scripts/_lib/de/einziges_dokument.py
    — the EU-OJ "EINZIGES DOKUMENT" HTML driver: slice from the
    `<p class="ti-grseq-1">EINZIGES DOKUMENT</p>` anchor, find numbered
    `ti-grseq-1` section headers, route by German title keyword, and
    parse the section-7/8 variety list whose lines are
    `Canonical Name — Synonym, Synonym` (canonical kept, synonyms dropped).
    The geo_area role carries a title BLOCKLIST so section 3 "Art der
    geografischen Angabe" (which contains "geografisch") does not shadow
    the real abgegrenztes Gebiet.

  - scripts/_lib/de/produktspezifikation.py — the BLE Produktspezifikation
    PDF parser with FOUR template branches the BLE drafted across agency
    eras (the highest-value target — a tweak for one template has
    historically broken another):
      A  numbered "8 Zugelassene Keltertraubensorten" + §3.2 per-variety
         Mindestmostgewicht (de-facto principal). Mosel, Pfalz, Nahe, …
         (tolerates the Saale-Unstrut "Kellertraubensorten" PDF typo).
      B  un-numbered "Zugelassene Keltertraubensorten:" + bullet
         "• Weißwein" / "• Rot- und Roséwein". Ahr, Sachsen.
      C  "7. Rebsorten" (NOT §8) + "• Rebsorten für Weißwein" bullets
         and inline "insbes. {variety} mit rd. X %" / §5.1 named-
         Mostgewicht principals. Rheingau, Hessische Bergstraße.
      D  Baden multi-Bereich §3.2.X tiered Mostgewicht rows, with a flat
         §8 the Template-A parser harvests for the full authorised set.
    Stage 02f lists every § 8 variety alike (`section-8-flat-no-split`,
    2026-11-17): no specification draws a principal / accessory line. The
    names § 3.2 singles out are still parsed, as reference data.

Fixtures are short redacted excerpts of public, licence-clear regulator
documents (BLE Produktspezifikationen = Amtliches Werk §5 UrhG; EU-OJ
documents) under tests/fixtures/de_*.{txt,html}. The HTML fixture is a
`# synthetic` faithful reconstruction of the real OJ markup (the real
page is 45 KB; the marker is in an HTML comment on line 1).

Assertions are on STRUCTURE (routed roles, variety NAME/slug sets, the
template letter, the principal/accessory split + its role_split_method
tag), not full-output snapshots. Where a test pins ACTUAL behaviour that
diverges from the docstring ideal (the `\\btrocken\\b` inflection gap;
the trailing `;` on a §8 name) the divergence is called out inline.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.de import produktspezifikation as ps  # noqa: E402
from _lib.de.einziges_dokument import (  # noqa: E402
    _GEO_AREA_TITLE_BLOCKLIST,
    SECTION_ROLE_KEYWORDS,
)
from _lib.grape_entity import match_variety  # noqa: E402

# 02_extract_pliegos starts with a digit, so import it by module path.
extract = importlib.import_module("de.02_extract_pliegos")


# ==========================================================================
# Einziges Dokument HTML driver — anchor slice + section routing
# ==========================================================================

def _route_html(html: str) -> tuple[dict, dict, dict]:
    """Slice → extract numbered sections → route, the way build_record
    drives them. Returns (sections, titles, routed)."""
    doc = extract.slice_einziges_dokument(html)
    assert doc is not None, "EINZIGES DOKUMENT anchor must be found"
    sections, titles = extract.extract_sections(doc)
    routed = extract.route_sections(sections, titles)
    return sections, titles, routed


def test_anchor_slice_drops_preamble(fixture_text):
    html = fixture_text("de_einziges_dokument_wurzburger_stein_berg.html")
    doc = extract.slice_einziges_dokument(html)
    # The "Veröffentlichung eines Antrags" preamble before the anchor is gone.
    assert "Veröffentlichung eines Antrags" not in doc
    # The slice begins at the EINZIGES DOKUMENT anchor paragraph.
    assert doc.lstrip().startswith("<p")
    assert "EINZIGES DOKUMENT" in doc[:80]


def test_section_routing_wurzburger(fixture_text):
    _sections, _titles, routed = _route_html(
        fixture_text("de_einziges_dokument_wurzburger_stein_berg.html")
    )
    # The semantic roles downstream consumers depend on.
    for role in ("name", "geo_area", "grape_varieties", "link_to_terroir"):
        assert role in routed, role
    # Section 7 body (abgegrenztes Gebiet) lands in geo_area.
    assert "Einzellage Würzburger Stein" in routed["geo_area"]
    # Section 8 body (Keltertraubensorten) lands in grape_varieties.
    assert "Weißer Riesling" in routed["grape_varieties"]
    # Section 9 body lands in link_to_terroir.
    assert "Muschelkalkboden" in routed["link_to_terroir"]


def test_section_keys_are_number_prefixed(fixture_text):
    """SECTION_NUM_RE: a ti-grseq-1 header registers only when it carries a
    leading "N." number — the bare "EINZIGES DOKUMENT" anchor paragraph
    must NOT register as a numbered section."""
    html = fixture_text("de_einziges_dokument_wurzburger_stein_berg.html")
    doc = extract.slice_einziges_dokument(html)
    sections, titles = extract.extract_sections(doc)
    assert set(sections) == set(titles)
    for num in sections:
        assert num[0].isdigit(), f"section key {num!r} should be number-prefixed"
    # The anchor heading is never a section title.
    assert "EINZIGES DOKUMENT" not in titles.values()


def test_section_role_keyword_table_shape():
    """The role table maps the German title keywords downstream routing
    depends on. The geo_area family must include the precise "abgegrenztes
    geografisches gebiet" form (section 7), the grape family the
    "keltertraubensorte" form, and the link family the "zusammenhang"
    form. A dropped keyword silently empties a semantic role for the whole
    DE corpus."""
    geo = SECTION_ROLE_KEYWORDS["geo_area"]
    assert "abgegrenztes geografisches gebiet" in geo
    grapes = SECTION_ROLE_KEYWORDS["grape_varieties"]
    assert any("keltertraubensorte" in kw for kw in grapes)
    link = SECTION_ROLE_KEYWORDS["link_to_terroir"]
    assert any("zusammenhang" in kw for kw in link)


def test_regression_geo_area_blocklist_skips_art_der_angabe(fixture_text):
    """Section 3 "Art der geografischen Angabe" contains the substring
    "geografische" — the same keyword that routes the real abgegrenztes
    Gebiet — but its body is just the "g.U." category. The geo_area
    blocklist must keep geo_area on section 7, NOT the section-3 decoy.
    A missing blocklist entry re-opens the regression."""
    # The blocklist table must carry the decoy title.
    assert "art der geografischen angabe" in _GEO_AREA_TITLE_BLOCKLIST
    _sections, titles, routed = _route_html(
        fixture_text("de_einziges_dokument_wurzburger_stein_berg.html")
    )
    # Sanity: the decoy section is present and IS what the blocklist guards.
    assert titles["3"] == "Art der geografischen Angabe"
    geo = routed["geo_area"]
    assert "g.U." not in geo
    assert geo.strip() != "g.U. — geschützte Ursprungsbezeichnung"
    assert "Einzellage Würzburger Stein" in geo


# ==========================================================================
# Einziges Dokument — section-7 "Canonical — Synonym" variety split
# ==========================================================================

def test_grape_parsing_em_dash_synonym_split(fixture_text):
    """`Weißer Riesling — Riesling, Riesling renano, …` → the canonical
    name before the ` — ` separator resolves; the synonym blob is dropped.
    The display name is the segment BEFORE the dash."""
    _sections, _titles, routed = _route_html(
        fixture_text("de_einziges_dokument_wurzburger_stein_berg.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    slugs = set(grapes["principal"])
    assert {"riesling", "pinot-blanc", "sylvaner"} == slugs
    by_slug = {d["slug"]: d for d in grapes["details"]}
    # Display name is the canonical head (synonyms after the em-dash dropped).
    assert by_slug["riesling"]["name"] == "Weißer Riesling"
    assert "Rheinriesling" not in by_slug["riesling"]["name"]
    assert by_slug["pinot-blanc"]["name"] == "Weißer Burgunder"
    assert by_slug["sylvaner"]["name"] == "Grüner Silvaner"


def test_grape_parsing_no_role_split_all_principal(fixture_text):
    """The German Einziges Dokument section 7 is a flat list — no
    principal/accessory split. Every match defaults to principal."""
    _sections, _titles, routed = _route_html(
        fixture_text("de_einziges_dokument_wurzburger_stein_berg.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    assert grapes["accessory"] == []
    assert set(grapes["principal"]) == {d["slug"] for d in grapes["details"]}
    for d in grapes["details"]:
        assert d["role"] == "principal"


def test_style_detection_white_only(fixture_text):
    """parse_styles scans the Beschreibung/Kategorie/Weiter sections for
    colour keywords + style markers. The section-5 body is white-only
    ("Weißweine … trockene Weißweine"), so the detected style set is
    {blanc}.

    ACTUAL-behaviour pin: the inflected "trockene" does NOT add `dry` —
    the STYLE_MARKERS pattern is `\\btrocken\\b`, whose trailing word
    boundary fails before the "-e" suffix. A bare "trocken" would add it.
    The test pins {blanc} so a future widening of the marker to inflected
    forms is a conscious change, not an accident."""
    sections, titles, _routed = _route_html(
        fixture_text("de_einziges_dokument_wurzburger_stein_berg.html")
    )
    styles = extract.parse_styles(sections, titles)
    assert styles == ["blanc"]


def test_wine_type_sub_section_titles_state_the_types():
    """Württemberg's single document (C/2025/5177) numbers one sub-section
    of the description per wine type and names it in the title; the bodies
    carry no product line. Until 2026-11-17 the card of a mostly red region
    showed White alone. The title is read; the body under it is not."""
    titles = {
        "3": "Kategorien von Weinbauerzeugnissen",
        "4": "Beschreibung des Weins / der Weine",
        "4.1": "Wein, weiß", "4.2": "Wein, rot", "4.3": "Wein, rosé", "4.4": "Weißherbst",
        "4.6": "Wein, Schillerwein", "4.7": "Wein, Rotling",
        "4.9": "Prädikatswein, Beerenauslese und Trockenbeerenauslese",
        "4.10": "Prädikatswein Eiswein",
        "4.12": "Qualitätsschaumwein, rot", "4.16": "Perlwein, rosé", "4.19": "Likörwein, rot",
        "5": "Weinbereitungsverfahren", "5.1": "Spezifische önologische Verfahren",
        "8": "Beschreibung des zusammenhangs bzw. der zusammenhänge",
    }
    sections = {num: "" for num in titles}
    sections["4.2"] = "KURZE TEXTBESCHREIBUNG\nAussehen: Sortenbedingt von hellrot bis schwarz"
    sections["5.1"] = "Für Strohwein gilt geltendes Recht."      # not a description sub-section
    assert extract.wine_type_titles(titles) == [
        "Wein, weiß", "Wein, rot", "Wein, rosé", "Weißherbst", "Wein, Schillerwein",
        "Wein, Rotling", "Prädikatswein, Beerenauslese und Trockenbeerenauslese",
        "Prädikatswein Eiswein", "Qualitätsschaumwein, rot", "Perlwein, rosé", "Likörwein, rot"]
    styles = extract.parse_styles(sections, titles)
    # ("Qualitätsschaumwein" is no hit of the `\\bschaumwein\\b` marker; the
    # record's Sparkling comes from its categories section.)
    assert {"blanc", "noir", "rose", "semi-sparkling", "vin-de-liqueur",
            "grains-nobles", "vendanges-tardives"} <= set(styles)
    assert "vin-de-paille" not in styles
    # Schillerwein and Rotling are categories of their own, not a rosé.
    assert extract.parse_styles({k: "" for k in ("4", "4.6", "4.7")},
                                {"4": titles["4"], "4.6": titles["4.6"], "4.7": titles["4.7"]}) == []


# ==========================================================================
# BLE Produktspezifikation — Template A (Mosel)
# ==========================================================================

def test_ble_template_a_detected_mosel(fixture_text):
    text = fixture_text("de_ble_templateA_mosel.txt")
    assert ps._detect_template(text) == "A"


def test_ble_template_a_section_3_2_principal_mosel(fixture_text):
    """§3.2 names individual varieties with their own Mostgewicht
    threshold → de-facto principal. "alle übrigen Rebsorten" rows carry a
    threshold too but must be EXCLUDED from the principal set."""
    text = fixture_text("de_ble_templateA_mosel.txt")
    principal = ps.parse_section_3_2_principal_names(text)
    assert principal == ["Elbling", "Riesling", "Müller Thurgau", "Dornfelder"]
    # The all-rest accessory bucket never leaks in as a principal.
    assert not any("übrigen" in n for n in principal)
    assert not any(n.lower().startswith("alle") for n in principal)


def test_ble_template_a_section_8_white_red_split_mosel(fixture_text):
    """§8 Zugelassene Keltertraubensorten splits on the "Weiße Rebsorten:"
    / "Rote Rebsorten:" subheaders, and stops at the §9 Zusammenhang
    header (the red list must not run past §8)."""
    text = fixture_text("de_ble_templateA_mosel.txt")
    section_8 = ps.parse_section_8_authorised(text)
    assert "Riesling" in section_8["white"]
    assert "Weißer Burgunder" in section_8["white"]
    assert "Dornfelder" in section_8["red"]
    assert "Tempranillo" in section_8["red"]
    # No white name leaked into red and vice versa.
    assert "Dornfelder" not in section_8["white"]
    assert "Riesling" not in section_8["red"]
    # §8 stopped at §9 — no Zusammenhang prose harvested as a variety.
    for name in (*section_8["white"], *section_8["red"]):
        assert "Angaben" not in name and "Zusammenhang" not in name


def test_ble_template_a_lists_every_variety_alike(fixture_text):
    """No BLE specification draws a principal / accessory line, so stage 02f
    lists every authorised variety alike (2026-11-17). Until then the names
    § 3.2 gives a must weight of their own were principal and the rest
    accessory — Mosel's card had four principals and Spätburgunder among the
    accessories."""
    text = fixture_text("de_ble_templateA_mosel.txt")
    role_split_method, principal_slugs, accessory_slugs = _role_split(text)
    assert role_split_method == "section-8-flat-no-split"
    assert {"elbling", "riesling", "muller-thurgau", "dornfelder", "scheurebe"} <= principal_slugs
    assert not accessory_slugs


def test_regression_ble_kellertraubensorten_typo_tolerated():
    """Saale-Unstrut's PDF has a "Kellertraubensorten" typo for the §8
    header. _SECTION_8_RE must accept both the correct "Kelter-" and the
    typo "Keller-" spelling, or that Anbaugebiet silently loses its §8."""
    assert ps._SECTION_8_RE.search("8 Zugelassene Keltertraubensorten")
    assert ps._SECTION_8_RE.search("8 Zugelassene Kellertraubensorten")


# ==========================================================================
# BLE Produktspezifikation — Template B (Ahr)
# ==========================================================================

def test_ble_template_b_detected_ahr(fixture_text):
    text = fixture_text("de_ble_templateB_ahr.txt")
    assert ps._detect_template(text) == "B"


def test_ble_template_b_bullet_colour_split_ahr(fixture_text):
    """Template B has no numbered §8 — the variety lists hang off the
    un-numbered "Zugelassene Keltertraubensorten:" anchor under bullet
    "• Weißwein" / "• Rot- und Roséwein" colour headers."""
    text = fixture_text("de_ble_templateB_ahr.txt")
    section_8 = ps.parse_section_8_authorised(text)
    assert "Riesling" in section_8["white"]
    assert "Weißer Burgunder" in section_8["white"][-1]  # trailing ';' pinned below
    assert "Dornfelder" in section_8["red"]
    assert "St. Laurent" in section_8["red"]
    # The Zusammenhang prose after the red list is not a variety.
    for name in (*section_8["white"], *section_8["red"]):
        assert "Gebiet" not in name


def test_ble_template_b_no_section_3_2_principal_ahr(fixture_text):
    """Ahr's §5.1 is flat-by-colour — no §3.2 per-variety Mostgewicht, so
    no principal split is recoverable. parse_section_3_2_principal_names
    returns []."""
    text = fixture_text("de_ble_templateB_ahr.txt")
    assert ps.parse_section_3_2_principal_names(text) == []


def test_ble_template_b_role_split_method_flat_no_split_ahr(fixture_text):
    """With no §3.2 principal, stage 02f tags `section-8-flat-no-split`:
    every §8 variety is principal, accessory is empty."""
    text = fixture_text("de_ble_templateB_ahr.txt")
    role_split_method, principal_slugs, accessory_slugs = _role_split(text)
    assert role_split_method == "section-8-flat-no-split"
    assert accessory_slugs == set()
    # Both colour buckets fold into principal.
    assert "riesling" in principal_slugs            # white
    assert "dornfelder" in principal_slugs          # red


def test_regression_ble_template_b_name_keeps_trailing_semicolon(fixture_text):
    """ACTUAL-behaviour pin: pdftotext glues the colour-block terminator
    ';' onto the last name ("Weißer Burgunder;"). _parse_comma_enum does
    NOT strip a trailing ';', so the raw §8 name carries it. The downstream
    grape lexicon still resolves it (lexicon-side cleanup), so this is
    harmless — but the test pins it so a future cleanup is a conscious
    choice and the slug assertion above ('riesling' principal) is the
    behaviour that actually matters."""
    text = fixture_text("de_ble_templateB_ahr.txt")
    white = ps.parse_section_8_authorised(text)["white"]
    assert white[-1] == "Weißer Burgunder;"
    # Despite the semicolon, the lexicon resolves it to pinot-blanc.
    m = match_variety(white[-1])
    assert m is not None and m.slug == "pinot-blanc"


# ==========================================================================
# BLE Produktspezifikation — Template C (Rheingau)
# ==========================================================================

def test_ble_template_c_detected_rheingau(fixture_text):
    text = fixture_text("de_ble_templateC_rheingau.txt")
    assert ps._detect_template(text) == "C"


def test_ble_template_c_section_7_bullet_colour_split_rheingau(fixture_text):
    """Template C lists varieties under "7. Rebsorten" (NOT §8) with
    "• Rebsorten für Weißwein" / "• Rebsorten für Rot- und Roséwein"
    bullets. The "insbes. … klassifizierte Rebsorten:" preamble before
    each comma list must be stripped so it doesn't pollute the names."""
    text = fixture_text("de_ble_templateC_rheingau.txt")
    section_8 = ps.parse_section_8_authorised(text)
    assert "Weißer Riesling" in section_8["white"]
    assert "Chardonnay" in section_8["white"]
    assert "Merlot" in section_8["red"]
    assert "Blauer Spätburgunder" in section_8["red"]
    # The "insbes." / "klassifizierte Rebsorten" preamble words are gone.
    for name in (*section_8["white"], *section_8["red"]):
        assert "insbes" not in name.lower()
        assert "klassifizierte" not in name.lower()
        assert "%" not in name


def test_ble_template_c_principal_two_signals_rheingau(fixture_text):
    """Template C principals come from TWO signals at once:
      - the inline "insbes. Weißer Riesling mit rd. 80 %" (white)
      - the §5.1 named-Mostgewicht row "Spätburgunder Rotwein 8,4 66°" (red)
    Both must be recovered."""
    text = fixture_text("de_ble_templateC_rheingau.txt")
    principal = ps.parse_section_3_2_principal_names(text)
    assert "Weißer Riesling" in principal   # insbes. inline
    assert "Spätburgunder" in principal     # §5.1 named-Mostgewicht row


def test_ble_template_c_lists_every_variety_alike_rheingau(fixture_text):
    text = fixture_text("de_ble_templateC_rheingau.txt")
    role_split_method, principal_slugs, accessory_slugs = _role_split(text)
    assert role_split_method == "section-8-flat-no-split"
    assert {"riesling", "pinot-noir", "chardonnay"} <= principal_slugs
    assert not accessory_slugs


# ==========================================================================
# BLE Produktspezifikation — Template D (Baden multi-Bereich)
# ==========================================================================

def test_ble_template_d_detected_baden(fixture_text):
    """A "3.2.X. Bereich:" header short-circuits detection to Template D
    regardless of the other templates' marker presence."""
    text = fixture_text("de_ble_templateD_baden.txt")
    assert ps._detect_template(text) == "D"


def test_ble_template_d_singles_out_no_variety_baden(fixture_text):
    """Baden's § 3.2 tiers some fifty-five varieties over two Bereich groups
    and six quality levels and puts Spätburgunder, a third of its vineyard,
    under "alle übrigen Rebsorten": no row singles out a lead variety, so the
    table makes no role split (2026-11-17 — the lowest-tier reading had made
    principals of Tempranillo and Trollinger, and of Merzling and Baron on
    the full PDF)."""
    text = fixture_text("de_ble_templateD_baden.txt")
    assert ps.parse_section_3_2_principal_names(text) == []
    assert ps.principal_names_with_basis(text) == []


def test_ble_template_d_section_8_falls_back_to_flat_list_baden(fixture_text):
    """Baden embeds BOTH the multi-Bereich §3.2 tiers (Template D, an
    incomplete list) AND a flat §8 (Template A shape, the full authorised
    set). parse_section_8_authorised must return the comprehensive flat §8,
    not the partial §3.2 Bereich rows."""
    text = fixture_text("de_ble_templateD_baden.txt")
    section_8 = ps.parse_section_8_authorised(text)
    # Varieties only present in the flat §8 (not in the §3.2 Bereich rows).
    assert "Weißburgunder" in section_8["white"]
    assert "Dornfelder" in section_8["red"]
    assert "Spätburgunder" in section_8["red"]
    # The §3.2 leitsorten are in §8 too.
    assert "Gutedel" in section_8["white"]
    assert "Tempranillo" in section_8["red"]


def test_ble_template_d_role_split_method_flat_baden(fixture_text):
    text = fixture_text("de_ble_templateD_baden.txt")
    role_split_method, principal_slugs, accessory_slugs = _role_split(text)
    assert role_split_method == "section-8-flat-no-split"
    # every authorised variety is listed, none demoted: Spätburgunder too
    assert {"chasselas", "schiava-grossa", "pinot-blanc", "pinot-noir"} <= principal_slugs
    assert not accessory_slugs


def test_ble_principal_basis_names_the_signal(fixture_text):
    """The parser still reports which varieties a specification singles out
    and how (reference data in the sidecar, `raw_section_3_2_principal`); the
    card reads no role from it."""
    mosel = dict(ps.principal_names_with_basis(fixture_text("de_ble_templateA_mosel.txt")))
    assert mosel and set(mosel.values()) == {ps.BASIS_MUST_WEIGHT}
    rheingau = dict(ps.principal_names_with_basis(fixture_text("de_ble_templateC_rheingau.txt")))
    assert rheingau.get("Weißer Riesling") == ps.BASIS_PLANTINGS


# ==========================================================================
# Terroir (§8/§9 Zusammenhang) extraction
# ==========================================================================

def test_terroir_text_extracted_for_numbered_zusammenhang_mosel(fixture_text):
    """The numbered "9 Angaben, aus denen sich der Zusammenhang …" header
    bounds the §8 variety list AND anchors the terroir block. For Mosel
    (Template A) the header is present, so extract_terroir_text returns a
    non-empty block starting at that header."""
    text = fixture_text("de_ble_templateA_mosel.txt")
    terroir = ps.extract_terroir_text(text)
    assert terroir.startswith("9")
    assert "Zusammenhang" in terroir


def test_terroir_text_empty_when_no_numbered_header_ahr(fixture_text):
    """ACTUAL-behaviour pin: Ahr's terroir is introduced by the
    un-numbered "Zusammenhang mit dem geografischen Gebiet:" line — which
    bounds §8 but is NOT the numbered "8./9. Angaben …" anchor
    extract_terroir_text looks for. So extract_terroir_text returns "" on
    the Template-B fixture; Ahr's real terroir is recovered via a separate
    path. The test pins the gap so it's a conscious limitation."""
    text = fixture_text("de_ble_templateB_ahr.txt")
    assert ps.extract_terroir_text(text) == ""


# ==========================================================================
# Shared helper — reproduce stage 02f's role split from a parsed PDF text
# ==========================================================================

def _role_split(text: str) -> tuple[str, set[str], set[str]]:
    """Mirror scripts/de/02f_extract_produktspezifikation.py:_build_record
    over already-text-extracted Produktspezifikation content. Returns
    (role_split_method, principal_slugs, accessory_slugs): every § 8 variety
    is listed alike, the names § 3.2 singles out first."""
    names = [*ps.parse_section_3_2_principal_names(text)]
    section_8 = ps.parse_section_8_authorised(text)
    names += [*section_8["white"], *section_8["red"]]
    principal_slugs: set[str] = set()
    for name in names:
        m = match_variety(name)
        if m is not None:
            principal_slugs.add(m.slug)
    role_split_method = "section-8-flat-no-split"
    accessory_slugs: set[str] = set()
    return role_split_method, principal_slugs, accessory_slugs


# ==========================================================================
# Landwein commune-list geometry (scripts/_lib/de/geometry.py)
# ==========================================================================

def test_de_norm_strips_bavarian_gisco_suffixes():
    """GISCO LAU spells Bavarian towns "Röttingen, St" / "Rothenburg ob der
    Tauber, GKSt" / "Zell a.Main, M" (Stadt / Große Kreisstadt / Markt),
    the way Brandenburg's carry ", Stadt". The suffix must go so the
    Produktspezifikation's bare name matches; a name merely ENDING in
    "-stadt" is not a suffix."""
    from _lib.de.geometry import _de_norm

    assert _de_norm("Röttingen, St") == _de_norm("Röttingen") == "rottingen"
    assert _de_norm("Rothenburg ob der Tauber, GKSt") == _de_norm("Rothenburg ob der Tauber")
    assert _de_norm("Zell a.Main, M") == "zell a.main"
    assert _de_norm("Bad Mergentheim, Stadt") == "bad mergentheim"
    assert _de_norm("Ingolstadt") == "ingolstadt"


def test_landwein_area_kreise_all_have_an_ags():
    """Every Kreis a DE_LANDWEIN_AREA entry names must be in _DE_KREIS_AGS —
    otherwise _load_communes never loads it and the Gemeinde silently
    lands in `unmatched`."""
    from _lib.de.geometry import _DE_KREIS_AGS, DE_LANDWEIN_AREA, _de_norm

    for file_number, area in DE_LANDWEIN_AREA.items():
        for name in (*area.get("landkreise", []), *area.get("kreisfreie", []),
                     *(g["kreis"] for g in area.get("gemeinden", []))):
            assert _de_norm(name) in _DE_KREIS_AGS, (file_number, name)


def test_regression_taubertaler_landwein_is_a_commune_union_not_wurttemberg():
    """Regression (geometry-outlier audit 2026-09): PGI-DE-A1307 sat in
    DE_PGI_MEMBER_PDOS as the whole Württemberg Anbaugebiet, so it drew
    Württemberg's detached Lake-Constance part. Its Produktspezifikation
    §4 names 13 Main-Tauber-Kreis Gemeinden + 5 Bavarian places, so it
    resolves by GISCO commune union like Brandenburger Landwein."""
    from pathlib import Path

    from _lib.de.geometry import (
        _DE_KREIS_AGS,
        DE_LANDWEIN_AREA,
        DE_PGI_MEMBER_PDOS,
        DEPolygonIndex,
        _de_norm,
    )
    from shapely.geometry import box

    assert "PGI-DE-A1307" not in DE_PGI_MEMBER_PDOS
    idx = DEPolygonIndex(figshare_gpkg=Path("/nonexistent.gpkg"))
    bodensee = box(9.3, 47.6, 9.6, 47.8)
    idx._pdo_polygons["PDO-DE-A1276"] = box(9.0, 48.7, 9.6, 49.4).union(bodensee)
    gemeinden = DE_LANDWEIN_AREA["PGI-DE-A1307"]["gemeinden"]
    for i, g in enumerate(gemeinden):
        kreis = _DE_KREIS_AGS[_de_norm(g["kreis"])]
        idx._commune_by_kreis_name[(kreis, _de_norm(g["name"]))] = box(
            9.6 + i * 0.02, 49.5, 9.61 + i * 0.02, 49.51
        )
    geom, source, stats = idx.resolve("PGI-DE-A1307")
    assert source == "gisco-commune-union"
    assert stats["gemeinden"] == len(gemeinden) == 18
    assert stats["unmatched"] == 0
    assert not geom.intersects(bodensee)


def test_regensburger_landwein_is_a_disclosed_reading_of_its_own_text():
    """Decision of 2026-11-24. PGI-DE-A1296 was drawn as Franken, 150 km off.
    Its specification lists no Gemeinde (nor did Bavarian law ever: the
    Untergebiet Donau is one sentence since 1983), so the six north-bank
    communes from Regensburg to Wörth are a reading — every sentence read is
    in the cached PDF, the card says it is a reading, and the wine is no
    longer a union of any Anbaugebiet."""
    import re
    import subprocess
    from pathlib import Path

    from _lib.de.geometry import (
        _DE_KREIS_AGS,
        DE_LANDWEIN_AREA,
        DE_PGI_MEMBER_PDOS,
        DEPolygonIndex,
        _de_norm,
    )
    from shapely.geometry import box

    fn = "PGI-DE-A1296"
    assert fn not in DE_PGI_MEMBER_PDOS
    area = DE_LANDWEIN_AREA[fn]
    assert not area.get("landkreise") and not area.get("kreisfreie")
    names = [g["name"] for g in area["gemeinden"]]
    assert names == ["Regensburg", "Tegernheim", "Donaustauf", "Bach a.d.Donau",
                     "Wiesent", "Wörth a.d.Donau"]
    reading = area["reading"]
    assert set(reading["disclose"]) == {"en", "fr", "es", "nl"}
    assert all(s.strip() for s in reading["disclose"].values())

    # resolves as a commune union whatever the Franken polygon is
    idx = DEPolygonIndex(figshare_gpkg=Path("/nonexistent.gpkg"))
    franken = box(9.0, 49.5, 10.8, 50.5)
    idx._pdo_polygons["PDO-DE-A1267"] = franken
    for i, g in enumerate(area["gemeinden"]):
        kreis = _DE_KREIS_AGS[_de_norm(g["kreis"])]
        idx._commune_by_kreis_name[(kreis, _de_norm(g["name"]))] = box(
            12.0 + i * 0.1, 48.95, 12.1 + i * 0.1, 49.05)
    geom, source, stats = idx.resolve(fn)
    assert source == "gisco-commune-union"
    assert stats["gemeinden"] == 6 and stats["unmatched"] == 0
    assert not geom.intersects(franken)
    assert stats["reading"]["units"] == [
        "Regensburg", "Tegernheim", "Donaustauf", "Bach a.d. Donau", "Wiesent",
        "Wörth a.d. Donau"]
    assert stats["reading"]["disclose"] is reading["disclose"]
    # an entry that lists its communes carries no reading
    assert "reading" not in DE_LANDWEIN_AREA["PGI-DE-A1280"]

    # every sentence the reading rests on is in the specification as cached
    pdf = (Path(__file__).resolve().parent.parent
           / "raw/de/produktspezifikationen/regensburger-landwein.pdf")
    if pdf.exists():
        text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                              capture_output=True, text=True, check=True).stdout
        flat = re.sub(r"\s+", " ", re.sub(r"-\n\s*", "", text))
        for quote in reading["evidence"]:
            assert re.sub(r"\s+", " ", quote) in flat, quote
        # and § 3 still lists nothing: the frame is followed by the sentence
        frame = flat.index("der folgenden Gemeinden, wenn ihre Eignung")
        assert "Das Landweingebiet Regensburg umfasst" in flat[frame:frame + 260]

    # the six are real communes of the city and the Landkreis in GISCO
    gisco = next((Path(__file__).resolve().parent.parent / "raw/es/gisco").glob(
        "LAU_RG_01M_2024_3035*.zip"), None)
    if gisco is not None:
        real = DEPolygonIndex(figshare_gpkg=Path("/nonexistent.gpkg"), gisco_lau_zip=gisco)
        geom, source, stats = real.resolve(fn)
        assert source == "gisco-commune-union" and stats["unmatched"] == 0, stats
        assert stats["gemeinden"] == 6
        assert geom.geom_type == "Polygon"          # one contiguous row along the river
        lon0, lat0, lon1, lat1 = geom.bounds
        assert 11.9 < lon0 < lon1 < 12.6 and 48.9 < lat0 < lat1 < 49.15


def test_landwein_region_facet_follows_the_anbaugebiet_or_bundesland_rule():
    """A Landwein coextensive with one Anbaugebiet keeps that name; one that
    straddles several takes its Bundesland. Taubertäler Landwein spans
    Württemberg's Kocher-Jagst-Tauber, Baden's Tauberfranken and five
    Bavarian communes (BLE spec §1: "Baden-Württemberg und Bayern") and was
    filed under Württemberg; Schwäbischer Landwein, whose only union member
    is the Württemberg PDO (BLE spec §4: Kreßbronn, Ravensburg, Taldorf),
    was filed under Baden (2026-09-24)."""
    from _lib.de.region import REGIONS, region_for_file_number

    assert "Baden-Württemberg" in REGIONS
    assert region_for_file_number("PGI-DE-A1307") == "Baden-Württemberg"
    assert region_for_file_number("PGI-DE-A1305") == "Württemberg"
    assert region_for_file_number("PGI-DE-A1284") == "Württemberg"   # Landwein Neckar, coextensive
    assert region_for_file_number("PGI-DE-A1279") == "Baden"         # Badischer Landwein, coextensive


# ---------------------------------------------------------------- 2016 decision layout (2026-11-07)
# Bürgstadter Berg (OJ C 384/2016, CELEX 32016D1018(01)) is the one DE record
# published as a Commission decision: the anchor is a `doc-ti` title after
# "ANHANG", and § 7 is headed "Wichtigste Keltertrauben". It had been a stub
# since May (`no-einziges-dokument-anchor`), its card inheriting Franken's.

DECISION_HTML = """<p class="doc-ti" id="d1e32-5-1">ANHANG</p>
<p class="doc-ti">EINZIGES DOKUMENT</p>
<p class="ti-grseq-1" id="d1e41-5-1">1.\xa0\xa0\xa0<span class="bold">Einzutragende(r) Name(n)</span></p>
<p class="normal">Bürgstadter Berg</p>
<p class="ti-grseq-1">7.\xa0\xa0\xa0<span class="bold">Wichtigste Keltertrauben</span></p>
<p class="normal">Blauer Zweigelt</p>
<p class="normal">Weißer Riesling</p>
"""


def test_decision_layout_anchor_and_grape_heading():
    from _lib.de.einziges_dokument import DOC_ANCHOR_RE, SECTION_ROLE_KEYWORDS

    assert DOC_ANCHOR_RE.search(DECISION_HTML) is not None
    assert "wichtigste keltertrauben" in SECTION_ROLE_KEYWORDS["grape_varieties"]
