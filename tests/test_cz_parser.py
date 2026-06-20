"""Fixture-based regression tests for the Czech Republic (CZ) parsers.

CZ is the worst single-document corpus: all 13 EU-OJ wines ship as
content-stubs (no fetchable JEDNOTNÝ DOKUMENT), so the data — and the
parser regression surface — lives in the NATIONAL-SPEC layer, not in the
EU-OJ HTML driver. Three target modules:

  - scripts/_lib/cz/national_spec.py — the two Czech wine-law decrees.
      `parse_varieties`     → Vyhláška 88/2017 Sb. Příloha 2: 3 Roman-
        numeral colour blocks (I. white / II. red / III. zemské-víno),
        each a flat `<num>. Name <Abbr>` table. The block-terminator
        slicing (cut BEFORE the next "II."/"III."/"IV." marker) keeps
        the marker from leaking into the prior block's last entry and
        keeps the IV. abbreviations table out of the variety roster.
      `parse_commune_tree`  → Vyhláška 254/2010 Sb. Příloha: a 3-column
        rowspan table (Vinařská obec / Katastrální území / Název viniční
        trati) walked by a rowspan-tracking state machine that yields
        the column-0 obec name exactly once per obec regardless of how
        many KÚ / trať rows it spans, switching the active macro-region
        on the "A. … ČECHY" / "B. … MORAVA" headers.

  - scripts/_lib/cz/chzo_spec.py — the SZPI CHZO (PGI) product-spec
    parser (`szpi-chzo-specifikace-v1`) over `pdftotext -layout`:
      Section 1 (Popis vinařského regionu) → region_terroir_text
        (sliced from the "1 …" header to the next top-level "3 …",
        so section 3 Enologické postupy does NOT bleed in).
      Section 2 (Druhy výrobků) → style roster (still colours +
        Likérové→vin-de-liqueur / Šumivé→sparkling / Perlivé→
        semi-sparkling).

  - scripts/_lib/cz/jednotny_dokument.py — Czech keyword/role tables for
    the (never-yet-exercised) EU-OJ JEDNOTNÝ DOKUMENT. A small unit test
    of the role tables + a synthetic single document driven through the
    cz/02_extract_pliegos extractor, since no real CZ document fires it.

Real cached docs live under raw/cz/national-specs/ (gitignored — the
decree HTMLs + the SZPI PDFs). Fixtures here are short redacted excerpts;
the JEDNOTNÝ DOKUMENT fixture is `# synthetic` (no real doc exists).

Assertions are on STRUCTURE (per-colour slug sets, the rowspan state
machine's obec membership per podoblast, CHZO terroir-text presence +
style roster, JD role routing), not full-output snapshots. The
`name`-vs-lexicon-slug distinction is pinned explicitly: parse_varieties
emits its own NFKD slug (`frankovka`), while stage-04's augmenter resolves
the `name` through match_variety to the canonical lexicon slug
(`blaufrankisch`) — both layers are exercised.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.cz import chzo_spec, national_spec  # noqa: E402
from _lib.cz.jednotny_dokument import (  # noqa: E402
    _GEO_AREA_TITLE_BLOCKLIST,
    SECTION_ROLE_KEYWORDS,
)
from _lib.grape_entity import match_variety  # noqa: E402

# cz/02_extract_pliegos starts with a digit → import by module path.
extract = importlib.import_module("cz.02_extract_pliegos")


# ==========================================================================
# national_spec.parse_varieties — Vyhláška 88/2017 Sb. variety table
# ==========================================================================

def _varieties(fixture_text) -> dict:
    return national_spec.parse_varieties(
        fixture_text("cz_vyhlaska88_varieties.html")
    )


def _by_colour(out: dict, colour: str) -> list[dict]:
    return [v for v in out["varieties"] if v["colour"] == colour]


def test_varieties_three_colour_blocks_counted(fixture_text):
    out = _varieties(fixture_text)
    # The redacted fixture keeps 7 white / 6 red / 3 zemské rows; the
    # block counters reflect the colour split, not one flat list.
    assert out["n_white"] == 7
    assert out["n_red"] == 6
    assert out["n_zemske"] == 3
    assert len(out["varieties"]) == 16
    # The Příloha č. 2 anchor is recorded so the panel cites the decree.
    assert out["source_anchor"] == "Příloha č. 2 k vyhlášce č. 88/2017 Sb."


def test_varieties_per_block_slug_sets(fixture_text):
    out = _varieties(fixture_text)
    # parse_varieties emits its OWN NFKD-ASCII slug (`_slug`), not the
    # grape-lexicon slug — pin the structure per colour block.
    white = {v["slug"] for v in _by_colour(out, "blanc")}
    red = {v["slug"] for v in _by_colour(out, "noir")}
    zemske = {v["slug"] for v in _by_colour(out, "zemske")}
    assert white == {
        "aurelius", "chardonnay", "muller-thurgau", "rulandske-sede",
        "ryzlink-rynsky", "sauvignon", "veltlinske-zelene",
    }
    assert red == {
        "andre", "cabernet-sauvignon", "frankovka", "merlot",
        "modry-portugal", "svatovavrinecke",
    }
    assert zemske == {"bily-portugal", "modry-janek", "tramin-zluty"}
    # Every variety carries its block colour.
    for v in _by_colour(out, "blanc"):
        assert v["colour"] == "blanc"
    for v in _by_colour(out, "noir"):
        assert v["colour"] == "noir"


def test_varieties_name_resolves_to_lexicon_slug(fixture_text):
    """The augmenter (scripts/_lib/augment/cz.py) feeds the parser's
    `name` — NOT its `slug` — through match_variety to get the canonical
    grape-lexicon slug. The parser's own slug and the lexicon slug
    diverge for renamed natives, so pin the lexicon mapping on the
    load-bearing ones."""
    out = _varieties(fixture_text)
    by_name = {v["name"]: v for v in out["varieties"]}
    # Parser NFKD slug vs lexicon slug diverge here:
    assert by_name["Frankovka"]["slug"] == "frankovka"
    assert match_variety("Frankovka").slug == "blaufrankisch"
    assert match_variety("Svatovavřinecké").slug == "sankt-laurent"
    assert match_variety("Modrý Portugal").slug == "blauer-portugieser"
    assert match_variety("Ryzlink rýnský").slug == "riesling"
    assert match_variety("Veltlínské zelené").slug == "gruner-veltliner"


def test_varieties_preserves_source_typo_muller_thurgau(fixture_text):
    """The decree mis-types "Müller Thurgau" with U+0170 Ű
    ("Műller Thurgau"). The parser preserves the source spelling
    verbatim (never silently corrects it), and the lexicon still folds
    both spellings to muller-thurgau."""
    out = _varieties(fixture_text)
    mt = next(v for v in out["varieties"] if "ller Thurgau" in v["name"])
    assert mt["name"] == "Műller Thurgau"  # source typo kept
    assert mt["slug"] == "muller-thurgau"
    assert match_variety(mt["name"]).slug == "muller-thurgau"


def test_varieties_multi_abbreviation_kept_off_name(fixture_text):
    """A comma-separated abbreviation ("RŠ, RS") must be stripped off the
    name entirely — the trailing-abbreviation regex consumes both
    alternates so the name is the bare "Rulandské šedé"."""
    out = _varieties(fixture_text)
    rs = next(v for v in out["varieties"] if v["name"].startswith("Rulandské šedé"))
    assert rs["name"] == "Rulandské šedé"
    assert "RŠ" not in rs["name"] and "RS" not in rs["name"]


def test_regression_block_terminator_no_marker_leak(fixture_text):
    """The Roman-numeral block headers (II./III./IV.) are part of the
    literal terminator, so block slicing cuts BEFORE the marker. The
    last white variety must be clean "Veltlínské zelené" (not glued to a
    trailing "II"), and the last red "Svatovavřinecké" (not "… III")."""
    out = _varieties(fixture_text)
    names = {v["name"] for v in out["varieties"]}
    assert "Veltlínské zelené" in names
    assert "Svatovavřinecké" in names
    for n in names:
        assert not n.endswith(" II") and not n.endswith(" III")


def test_regression_abbreviation_table_not_parsed_as_varieties(fixture_text):
    """The III. (zemské) block ends at the IV. abbreviations table
    ("Seznam zkratek pro některé tradiční výrazy"), which is a
    traditional-term list, NOT a variety list. Its rows
    ("Jakostní víno", "Pozdní sběr") must never enter the roster."""
    out = _varieties(fixture_text)
    names = {v["name"] for v in out["varieties"]}
    assert "Jakostní víno" not in names
    assert "Pozdní sběr" not in names
    # And the Příloha č. 3 wine-defects appendix below it is sliced off too.
    assert not any("chorob" in n.lower() for n in names)


# ==========================================================================
# national_spec.parse_commune_tree — Vyhláška 254/2010 Sb. rowspan table
# ==========================================================================

def _commune_tree(fixture_text) -> dict:
    return national_spec.parse_commune_tree(
        fixture_text("cz_vyhlaska254_commune_tree.html")
    )


def test_commune_tree_podoblast_keys_and_anchor(fixture_text):
    out = _commune_tree(fixture_text)
    # One entry per podoblast heading the rowspan walker saw a table for.
    assert set(out["podoblasti"]) == {"melnicka", "litomericka", "mikulovska"}
    assert out["source_anchor"] == "Příloha k vyhlášce č. 254/2010 Sb."


def test_commune_tree_macro_region_switch(fixture_text):
    """The active macro-region flips on the "A. … ČECHY" / "B. … MORAVA"
    headers. The two Bohemian podoblasti carry Čechy; the Moravian one
    carries Morava — proving the state machine switched mid-document."""
    out = _commune_tree(fixture_text)
    assert out["podoblasti"]["melnicka"]["macro_region"] == "Čechy"
    assert out["podoblasti"]["litomericka"]["macro_region"] == "Čechy"
    assert out["podoblasti"]["mikulovska"]["macro_region"] == "Morava"


def test_commune_tree_rowspan_yields_obec_once(fixture_text):
    """The core of the rowspan state machine: an obec cell with
    rowspan="3" spans 3 physical <tr> rows (one per KÚ / trať), but the
    walker must yield the column-0 obec name exactly ONCE — never once
    per spanned row, and never the column-1 KÚ name."""
    out = _commune_tree(fixture_text)
    mel = out["podoblasti"]["melnicka"]
    # "Benátky nad Jizerou" spans 3 rows, "Cítov" spans 2 — each once.
    assert mel["communes"] == ["Benátky nad Jizerou", "Cítov", "Kuks"]
    # The KÚ-column cells ("Nové Benátky", "Obodř", "Cítov") and the
    # trať-column cells ("Pod zámkem", …) must NOT appear as obce.
    assert "Nové Benátky" not in mel["communes"]
    assert "Obodř" not in mel["communes"]
    assert "Pod zámkem" not in mel["communes"]


def test_commune_tree_obec_name_strips_leading_ordinal(fixture_text):
    """The obec cell carries a "1. Benátky nad Jizerou" ordinal prefix;
    _LEADING_ORDINAL_RE strips it so the bare obec name remains (and a
    multi-word name like "Benátky nad Jizerou" stays intact)."""
    out = _commune_tree(fixture_text)
    for pod in out["podoblasti"].values():
        for obec in pod["communes"]:
            assert not obec[:3].strip().rstrip(".").isdigit()
    assert "Benátky nad Jizerou" in out["podoblasti"]["melnicka"]["communes"]


def test_commune_tree_second_podoblast_communes(fixture_text):
    out = _commune_tree(fixture_text)
    lit = out["podoblasti"]["litomericka"]
    # Bělušice spans 3 rows (3 traťs), Most one — each once.
    assert lit["communes"] == ["Bělušice", "Most"]
    mik = out["podoblasti"]["mikulovska"]
    assert mik["communes"] == ["Bavory", "Březí"]


# ==========================================================================
# chzo_spec.parse_chzo_spec — SZPI CHZO product spec
# ==========================================================================

def _chzo(fixture_text) -> dict:
    return chzo_spec.parse_chzo_spec(
        fixture_text("cz_chzo_moravske_layout.txt"), "moravske"
    )


def test_chzo_region_and_pgi_file_number(fixture_text):
    out = _chzo(fixture_text)
    assert out["region"] == "Morava"
    assert out["pgi_file_number"] == "PGI-CZ-A0902"
    assert out["source_anchor"] == "1 Popis vinařského regionu"


def test_chzo_terroir_text_is_section_1_body(fixture_text):
    """Section-1 terroir text spans the region intro + 1.1 climate + 1.2
    geology/soils. It is the regulator-grounded terroir source for every
    CZ wine in the region (tier-agnostic), so its presence is the gating
    assertion for CZ terroir-fact extraction."""
    out = _chzo(fixture_text)
    terroir = out["region_terroir_text"]
    assert terroir.startswith("1 Popis vinařského regionu")
    # 1.1 + 1.2 subsection content is included.
    assert "HUGLIN" in terroir
    assert "vápenci" in terroir
    assert "Chardonnay" in terroir


def test_regression_chzo_section_1_stops_before_section_3(fixture_text):
    """_slice_top_section cuts section 1 at the next top-level header
    (sub=None). Section 2 (Druhy výrobků) sits between, then section 3
    (Základní enologické postupy). The terroir slice must NOT swallow
    section 2 or 3 — pin that the enology prose stays out."""
    out = _chzo(fixture_text)
    terroir = out["region_terroir_text"]
    assert "Enologické postupy" not in terroir
    assert "Likérové víno" not in terroir  # section 2 stays out of terroir


def test_chzo_style_roster(fixture_text):
    """Section 2 yields the style roster: still colours (white/red/rose
    from the 2.1 subsection headers) + the three special wine types."""
    out = _chzo(fixture_text)
    styles = set(out["styles"])
    # Still-wine colours.
    assert {"white", "rose", "red"} <= styles
    # Likérové → vin-de-liqueur, Šumivé → sparkling, Perlivé → semi-sparkling.
    assert "vin-de-liqueur" in styles
    assert "sparkling" in styles
    assert "semi-sparkling" in styles
    # The list is sorted + deduped.
    assert out["styles"] == sorted(set(out["styles"]))


def test_chzo_unknown_slug_yields_empty_region(fixture_text):
    # A slug not in CHZO_REGION / CHZO_PGI_FILE_NUMBER yields empty
    # region + pgi but still parses the section bodies.
    out = chzo_spec.parse_chzo_spec(
        fixture_text("cz_chzo_moravske_layout.txt"), "bogus"
    )
    assert out["region"] == ""
    assert out["pgi_file_number"] == ""
    # Styles still resolve (they come from the text, not the slug map).
    assert "sparkling" in out["styles"]


# ==========================================================================
# jednotny_dokument — role tables + synthetic single-document routing
# ==========================================================================

def test_jd_role_keyword_tables_cover_the_four_core_roles():
    """The four semantic roles every downstream consumer reads must be
    present with their canonical Czech section titles first."""
    assert SECTION_ROLE_KEYWORDS["name"][0] == "název"
    assert SECTION_ROLE_KEYWORDS["geo_area"][0] == "vymezená zeměpisná oblast"
    assert SECTION_ROLE_KEYWORDS["grape_varieties"][0] == "hlavní moštové odrůdy"
    assert SECTION_ROLE_KEYWORDS["link_to_terroir"][0] == "popis souvislostí"


def test_jd_geo_area_blocklist_excludes_category_titles():
    """"Druh zeměpisného označení" and "Kategorie výrobků z révy vinné"
    both contain "zeměpis"/"výrobk" tokens that could lure the geo_area
    matcher; the blocklist keeps them off the geo_area role."""
    assert "druh zeměpisného označení" in _GEO_AREA_TITLE_BLOCKLIST
    assert "kategorie výrobků z révy vinné" in _GEO_AREA_TITLE_BLOCKLIST


def _route_jd(html: str) -> tuple[dict, dict, dict]:
    doc = extract.slice_jednotny_dokument(html)
    assert doc is not None, "JEDNOTNÝ DOKUMENT anchor must be found"
    sections, titles = extract.extract_sections(doc)
    routed = extract.route_sections(sections, titles)
    return sections, titles, routed


def test_jd_synthetic_anchor_and_section_routing(fixture_text):
    """Synthetic single document driven through the cz/02 extractor: the
    anchor regex finds JEDNOTNÝ DOKUMENT, the numbered ti-grseq-1 headers
    parse, and the Czech keyword tables route each body to its role."""
    html = fixture_text("cz_jednotny_dokument_synthetic.html")
    _sections, _titles, routed = _route_jd(html)
    # The four core roles all routed.
    assert {"name", "geo_area", "grape_varieties", "link_to_terroir"} <= set(routed)
    # Section 6 body → geo_area (the area sentence, not the category).
    assert "podoblast mělnická" in routed["geo_area"]
    # Section 8 body → link_to_terroir (the terroir prose).
    assert "spraše" in routed["link_to_terroir"]


def test_jd_synthetic_preamble_dropped(fixture_text):
    # slice_jednotny_dokument starts AT the anchor → the modification
    # preamble before "JEDNOTNÝ DOKUMENT" is dropped.
    html = fixture_text("cz_jednotny_dokument_synthetic.html")
    doc = extract.slice_jednotny_dokument(html)
    assert "KOMUNIKACE O ZMĚNĚ" not in doc


def test_jd_synthetic_grape_section_resolves_lexicon_slugs(fixture_text):
    """The grape section is `Name - synonym` per line; the canonical
    Czech name (before " - ") resolves via the shared lexicon. No
    principal/accessory split in the CZ single document → all principal."""
    html = fixture_text("cz_jednotny_dokument_synthetic.html")
    _sections, _titles, routed = _route_jd(html)
    grapes = extract.parse_grapes(routed["grape_varieties"])
    slugs = set(grapes["principal"])
    assert {"riesling", "sankt-laurent", "pinot-noir"} <= slugs
    assert grapes["accessory"] == []
