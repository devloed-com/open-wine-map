"""Fixture-based regression tests for the Croatia (HR) parsers.

Two target parsers, each its own documented seam:

  - scripts/hr/02_extract_pliegos.py + scripts/_lib/hr/jedinstveni_dokument.py
    — the EUR-Lex "JEDINSTVENI DOKUMENT" HTML driver. Slice from the
    JEDINSTVENI-DOKUMENT anchor, find numbered `(oj-)ti-grseq-1` section
    headers, route by Croatian title keyword (Naziv… / Razgraničeno
    zemljopisno područje / Glavne sorte vinove loze / Opis povezanosti),
    parse the em-dash `Name – Synonym` grape lines, and detect colour
    styles. The geo_area blocklist keeps section 2 ("Vrsta oznake
    zemljopisnog podrijetla", which also carries "zemljopisnog") from
    shadowing the real area in section 6.

  - scripts/_lib/hr/specifikacija.py — the MPS national-spec parser (the
    bulk of HR — 16 grandfathered PDOs). Lettered a)–h) outline slicer
    (`_lettered_sections`), the `\\x0c` form-feed → newline normalisation,
    the FORWARD-ONLY letter guard (a backward cross-reference like
    "…prema točki e) …" inside section c) must NOT register as a heading),
    the grape colour markers `Bijele sorte:`→blanc / `Crne sorte:`→noir,
    the trailing-colour-adjective fallback (`Chardonnay crni`→chardonnay),
    and the `.docx` keyword-title slicer fallback (`_keyword_sections`)
    when Word auto-numbering strips the a–j prefixes.

Real cached docs live under raw/hr/{oj-pages,specifikacije-extracted}/
(gitignored). The HTML fixture is a redacted minimal excerpt of the
public EU-OJ Ponikve document; the specifikacija fixtures are `# synthetic`
text mirrors of the lettered-PDF and docx shapes (the `.doc → text`
conversion needs the antiword Docker image, deliberately not run here),
cross-checked against raw/hr/specifikacije-extracted/*.json so the asserted
slugs match what parse_specifikacija actually produces.

Assertions are on STRUCTURE (routed roles, lettered-section bodies, colour
split + trailing-adjective fallback, form-feed handling, forward-only guard),
not on full-output snapshots. Where a test pins ACTUAL parser behaviour, it
is called out inline.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.grape_entity import set_pliego_context  # noqa: E402
from _lib.hr import specifikacija as spec  # noqa: E402
from _lib.hr.jedinstveni_dokument import (  # noqa: E402
    _GEO_AREA_TITLE_BLOCKLIST,
    SECTION_ROLE_KEYWORDS,
)

# 02_extract_pliegos starts with a digit, so import it by module path.
extract = importlib.import_module("hr.02_extract_pliegos")

# Grape matching consults a per-pliego context (for the unknowns queue).
set_pliego_context("hr-test")


def _route_html(html: str) -> tuple[dict, dict, dict]:
    """Slice → extract numbered sections → route, the way build_record drives
    them. Returns (sections, titles, routed)."""
    doc = extract.slice_jedinstveni_dokument(html)
    assert doc is not None, "JEDINSTVENI-DOKUMENT anchor must be found"
    sections, titles = extract.extract_sections(doc)
    routed = extract.route_sections(sections, titles)
    return sections, titles, routed


# ==========================================================================
# JEDINSTVENI DOKUMENT — HTML driver: anchor + section routing
# ==========================================================================

def test_anchor_slice_drops_preamble(fixture_text):
    html = fixture_text("hr_jedinstveni_dokument_ponikve.html")
    doc = extract.slice_jedinstveni_dokument(html)
    assert doc is not None
    # The "PROIZVODA" doc-title line before the anchor is dropped; the slice
    # begins at the JEDINSTVENI DOKUMENT header tag itself.
    assert "oj-doc-ti" not in doc
    assert "JEDINSTVENI" in doc.lstrip()[:60]


def test_section_routing_ponikve(fixture_text):
    _sections, _titles, routed = _route_html(
        fixture_text("hr_jedinstveni_dokument_ponikve.html")
    )
    # The four semantic roles the downstream consumers depend on.
    for role in ("name", "geo_area", "grape_varieties", "link_to_terroir"):
        assert role in routed, role
    # Section 1 body → name.
    assert routed["name"] == "Ponikve"
    # Section 6 body (area) lands in geo_area, NOT terroir prose.
    assert "vinogradarski položaj Ponikve" in routed["geo_area"]
    # Section 7 body lands in grape_varieties.
    assert "Maraština" in routed["grape_varieties"]
    # Section 8 body lands in link_to_terroir.
    assert "sredozemna klima" in routed["link_to_terroir"]


def test_section_keys_are_number_prefixed(fixture_text):
    """Only the numbered top-level headers register as sections; the bare
    decoy lines below the anchor ("„PONIKVE”", the file-number "PDO-HR-…")
    carry no leading "N." and must NOT become sections."""
    html = fixture_text("hr_jedinstveni_dokument_ponikve.html")
    doc = extract.slice_jedinstveni_dokument(html)
    sections, titles = extract.extract_sections(doc)
    assert set(sections) == set(titles)
    assert set(sections) == {"1", "2", "3", "4", "5", "6", "7", "8", "9"}
    for num in sections:
        assert num[0].isdigit(), f"section key {num!r} should be number-prefixed"


# ==========================================================================
# JEDINSTVENI DOKUMENT — grape parsing (em-dash synonym split + colour)
# ==========================================================================

def test_grape_parsing_em_dash_synonym_split(fixture_text):
    """`Maraština – Rukatac, Maraškin, …` → the canonical name before the
    ` – ` em-dash separator resolves; the synonym blob is only a fallback.
    Display name is the segment BEFORE the dash (synonyms dropped)."""
    _sections, _titles, routed = _route_html(
        fixture_text("hr_jedinstveni_dokument_ponikve.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    assert grapes["principal"] == ["marastina", "plavac-mali", "posip"]
    by_slug = {d["slug"]: d for d in grapes["details"]}
    # Display name is the head segment; synonyms after the em-dash are dropped.
    assert by_slug["marastina"]["name"] == "Maraština"
    assert "Rukatac" not in by_slug["marastina"]["name"]
    # "Plavac mali crni – …" keeps the trailing colour word on the head name
    # but still resolves to the plavac-mali slug (noir).
    assert by_slug["plavac-mali"]["name"] == "Plavac mali crni"
    assert by_slug["plavac-mali"]["colour"] == "noir"
    assert by_slug["marastina"]["colour"] == "blanc"
    assert by_slug["posip"]["colour"] == "blanc"
    # No principal/accessory split in the HR single document → all principal.
    assert grapes["accessory"] == []


def test_styles_colour_detection(fixture_text):
    """parse_styles scans the description ("Opis vina") + category bodies for
    Croatian colour adjectives: bijela vina → blanc, crna vina → noir,
    ružičasta vina → rose."""
    sections, titles, _routed = _route_html(
        fixture_text("hr_jedinstveni_dokument_ponikve.html")
    )
    styles = extract.parse_styles(sections, titles)
    assert "blanc" in styles
    assert "noir" in styles
    assert "rose" in styles


# ==========================================================================
# Regression: the "Vrsta oznake zemljopisnog podrijetla" geo_area decoy
# ==========================================================================

def test_geo_area_blocklist_table_present():
    # Section 2's title carries "zemljopisnog" but its body is just the
    # ZOI/ZOZP label — the blocklist must disqualify it from geo_area, or it
    # would shadow the real area in section 6.
    assert "vrsta oznake zemljopisnog podrijetla" in _GEO_AREA_TITLE_BLOCKLIST


def test_regression_section2_zemljopisnog_decoy_not_routed_to_geo_area(fixture_text):
    """Section 2 ("Vrsta oznake zemljopisnog podrijetla") contains the
    keyword "zemljopisnog" that the geo_area keyword scan matches, but its
    body is "ZOI – zaštićena oznaka izvornosti", not an area. The blocklist
    must keep geo_area on section 6 (the real area)."""
    _sections, _titles, routed = _route_html(
        fixture_text("hr_jedinstveni_dokument_ponikve.html")
    )
    geo = routed["geo_area"]
    assert "zaštićena oznaka izvornosti" not in geo.split(".")[0]
    # The real area (section 6) is what landed.
    assert "vinogradarski položaj Ponikve" in geo


def test_geo_area_keyword_ordering_most_specific_first():
    """The geo_area keyword list is ordered most-specific-first so the full
    "razgraničeno zemljopisno područje" wins over the bare
    "zemljopisno područje" fragment."""
    geo_keywords = SECTION_ROLE_KEYWORDS["geo_area"]
    assert geo_keywords[0] == "razgraničeno zemljopisno područje"


# ==========================================================================
# specifikacija.py — lettered a)–h) outline (Dingač-shape PDF)
# ==========================================================================

def _dingac_text(fixture_text) -> str:
    """Load the synthetic lettered fixture (drop the `#` header lines) and
    inject a real form-feed before the g) header to exercise the
    \\x0c → newline fold."""
    raw = fixture_text("hr_specifikacija_dingac.txt")
    body = "".join(line for line in raw.splitlines(keepends=True)
                   if not line.startswith("#"))
    return body.replace("\ng)", "\x0cg)", 1)


def test_lettered_section_split(fixture_text):
    text = _dingac_text(fixture_text)
    sections = spec._lettered_sections(text)
    # All eight lettered sections a)–h) carve out.
    assert set(sections) == set("abcdefgh")
    # f) (grape varieties) holds the colour-marker block.
    assert "Bijele sorte:" in sections["f"]
    assert "Crne sorte:" in sections["f"]


def test_lettered_role_routing(fixture_text):
    text = _dingac_text(fixture_text)
    sections = spec._lettered_sections(text)
    routed = spec._route_sections(sections)
    for role in ("name", "description", "geo_area", "grape_varieties",
                 "link_to_terroir"):
        assert role in routed, role
    assert "Dingač" in routed["name"]
    assert "poluotoka" in routed["geo_area"]
    # g) terroir text routes to link_to_terroir.
    assert "insolaciju" in routed["link_to_terroir"]


def test_regression_formfeed_fold_before_g_section(fixture_text):
    """A `\\x0c` form-feed page break right before the g) header must be
    folded to a newline so the `^`-anchored g) letter is still matched and
    section f) doesn't swallow g)'s terroir body."""
    text = _dingac_text(fixture_text)
    assert "\x0cg)" in text  # the test injected a real form-feed
    sections = spec._lettered_sections(text)
    # g) carved out as its own section despite the form-feed.
    assert "g" in sections
    assert "insolaciju" in sections["g"]
    # f) (grapes) did not absorb g)'s terroir prose.
    assert "insolaciju" not in sections["f"]


def test_regression_forward_only_letter_guard(fixture_text):
    """Section c) contains a backward cross-reference "…prema točki e)
    Maksimalni urod…". The forward-only guard (an anchor whose letter does
    not advance past the last accepted one is a reference, not a heading)
    must keep that inline "e)" out of the section map — section e) stays the
    real "Maksimalni urod po ha" heading."""
    text = _dingac_text(fixture_text)
    sections = spec._lettered_sections(text)
    # The cross-reference text survives inside section c)'s body.
    assert "prema točki e)" in sections["c"]
    # Section e) is the real heading body, not the c) cross-reference fragment.
    assert "Najveći dozvoljeni urod" in sections["e"]


def test_specifikacija_colour_markers_white_vs_red(fixture_text):
    """`Bijele sorte:` → blanc, `Crne sorte:` → noir. Each variety carries
    the colour of its marker bucket (the matcher's own colour wins when it
    has one, but the bucket is the fallback)."""
    text = _dingac_text(fixture_text)
    frag = spec.parse_specifikacija(text, "dingac")
    by_slug = {d["slug"]: d for d in frag["grapes"]["details"]}
    for slug in ("chardonnay", "marastina", "posip", "debit", "riesling"):
        assert by_slug[slug]["colour"] == "blanc", slug
    for slug in ("plavac-mali", "babic", "plavina", "merlot", "croatina",
                 "syrah"):
        assert by_slug[slug]["colour"] == "noir", slug
    # No principal/accessory split — every variety is principal.
    assert frag["grapes"]["accessory"] == []
    assert set(frag["grapes"]["principal"]) == set(by_slug)


def test_regression_trailing_colour_adjective_fallback(fixture_text):
    """`Chardonnay crni` / `Riesling žuti` carry a trailing Croatian colour
    adjective that makes the bare matcher reject the adjective-bearing form.
    The `_COLOUR_ADJ_RE` fallback in `_add` retries without the trailing
    adjective so both still resolve. (Verified: match_variety('Chardonnay
    crni') / ('Riesling žuti') return None, while the stripped forms match.)
    `Croatina crna` is the documented marker case — it resolves to
    `croatina`."""
    text = _dingac_text(fixture_text)
    frag = spec.parse_specifikacija(text, "dingac")
    slugs = set(frag["grapes"]["principal"])
    # These two only resolve via the trailing-adjective retry.
    assert "chardonnay" in slugs
    assert "riesling" in slugs
    # The Croatina crna marker case.
    assert "croatina" in slugs


def test_specifikacija_record_fragment_shape(fixture_text):
    text = _dingac_text(fixture_text)
    frag = spec.parse_specifikacija(text, "dingac")
    # Lettered docs (≥ 5 sections) carry the v1 template tag.
    assert frag["parser_template"] == "mps-specifikacija-v1"
    assert frag["n_sections"] == 8
    # Styles: white + red grapes → blanc + rouge colour-derived styles.
    assert "blanc" in frag["styles"]
    assert "rouge" in frag["styles"]
    # Terroir text from g) is preserved.
    assert "insolaciju" in frag["link_to_terroir"]
    # geo area brief from d) is preserved.
    assert "poluotoka" in frag["geo_area_brief"]


# ==========================================================================
# specifikacija.py — .docx keyword-title fallback (no a)–j) prefixes)
# ==========================================================================

def _primorska_text(fixture_text) -> str:
    raw = fixture_text("hr_specifikacija_primorska_docx.txt")
    return "".join(line for line in raw.splitlines(keepends=True)
                   if not line.startswith("#"))


def test_docx_lettered_slicer_finds_no_sections(fixture_text):
    """Word auto-numbering strips the a)–j) prefixes, so the lettered slicer
    finds < 5 sections → parse_specifikacija falls through to the keyword
    slicer."""
    text = _primorska_text(fixture_text)
    assert len(spec._lettered_sections(text)) < 5


def test_regression_docx_keyword_section_fallback(fixture_text):
    """`_keyword_sections` anchors on the role-keyword heading lines
    themselves (no letters) and slices each body to the next heading, so the
    grape roster + terroir text are still recovered for the docx."""
    text = _primorska_text(fixture_text)
    routed = spec._keyword_sections(text)
    for role in ("name", "description", "geo_area", "grape_varieties",
                 "link_to_terroir"):
        assert role in routed, role
    assert "Maraština" in routed["grape_varieties"]
    assert "Sredozemna" in routed["link_to_terroir"]
    assert "priobalno" in routed["geo_area"]


def test_docx_parser_template_and_grapes(fixture_text):
    text = _primorska_text(fixture_text)
    frag = spec.parse_specifikacija(text, "primorska-hrvatska")
    # The docx path is tagged distinctly from the lettered v1 path.
    assert frag["parser_template"] == "mps-specifikacija-docx"
    slugs = set(frag["grapes"]["principal"])
    assert {"marastina", "posip", "debit"} <= slugs  # whites
    assert {"plavac-mali", "babic", "plavina"} <= slugs  # reds
    by_slug = {d["slug"]: d for d in frag["grapes"]["details"]}
    assert by_slug["marastina"]["colour"] == "blanc"
    assert by_slug["plavac-mali"]["colour"] == "noir"
