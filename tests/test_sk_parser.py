"""Fixture-based regression tests for the Slovakia (SK) parsers.

Two parser surfaces, each with its own documented seam:

  - scripts/_lib/sk/jednotny_dokument.py (+ the HTML driver in
    scripts/sk/02_extract_pliegos.py) — the EU-OJ "JEDNOTNÝ DOKUMENT"
    template. Section-keyword role routing has to handle BOTH title
    variants the corpus actually ships:
      * geo_area: "Vymedzená zemepisná oblasť" (newer) AND the older,
        shorter "Vymedzená oblasť".
      * link_to_terroir: "Opis súvislostí" (newer) AND the older
        "Údaje potvrdzujúce spojitosť".
    Regression (commit b869b1b): the Tokaj document gives each wine TYPE
    its own numbered ti-grseq-1 section (Tokajský výber, ľadové víno,
    slamové víno, Likérové víno, Sekt …) instead of one "Opis vín"
    section, so style detection has to scan the section TITLES + per-type
    "STRUČNÝ SLOVNÝ OPIS" bodies, not just an "opis vín" title.

  - scripts/_lib/sk/specifikacija.py — the ÚPV SR national spec, two
    templates:
      * upv-sr-specifikacia-v1: lettered a–i outline. The critical seam is
        section f), a two-column Odroda (canonical, LEFT) / Synonymum
        (foreign synonyms, RIGHT) table grouped under MUŠTOVÉ BIELE
        (→blanc) / MUŠTOVÉ MODRÉ (→noir). The parser must take ONLY the
        left Odroda column (the ≥2-space gutter), so the Pesecká leánka ↔
        Feteasca regala synonym confusion never reaches the matcher.
      * upv-sr-prihlaska-v1: the older numbered 03.N template with a FLAT
        inline §03.5 variety list (OCR-scanned, noisy).

Real cached docs live under raw/sk/{oj-pages,national-specs}/ (gitignored).
The fixtures here are short, redacted excerpts under tests/fixtures/.

Assertions are on STRUCTURE (routed roles for both title variants, the
left-Odroda-column-only grape set + colour split, the right-column synonym
NOT leaking, the Tokaj predikát style set), not on full-output snapshots.
Where a test pins ACTUAL parser behaviour that diverges from the module
docstring's ideal (the §f geo/link bodies still carrying their wrapped
title prefix because they have no early colon; the glued-bucket white block
never receiving a bucket colour fallback), the divergence is called out
inline.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.sk import specifikacija  # noqa: E402
from _lib.sk.jednotny_dokument import (  # noqa: E402
    SECTION_ROLE_KEYWORDS,
)

# 02_extract_pliegos starts with a digit, so import it by module path.
extract = importlib.import_module("sk.02_extract_pliegos")


# ==========================================================================
# JEDNOTNÝ DOKUMENT HTML driver — section routing helper
# ==========================================================================

def _route_html(html: str) -> tuple[dict, dict, dict]:
    """Slice → extract numbered sections → route, the way build_record
    drives them. Returns (sections, titles, routed)."""
    doc = extract.slice_jednotny_dokument(html)
    assert doc is not None, "JEDNOTNÝ DOKUMENT anchor must be found"
    sections, titles = extract.extract_sections(doc)
    routed = extract.route_sections(sections, titles)
    return sections, titles, routed


# ==========================================================================
# Section routing — the NEWER template variant
# ==========================================================================

def test_routing_new_template_titles(fixture_text):
    """The newer template: geo titled "Vymedzená zemepisná oblasť", link
    titled "Opis súvislostí". Both must route to the right semantic role."""
    sections, titles, routed = _route_html(
        fixture_text("sk_jednotny_dokument_new_stredoslovenska.html")
    )
    # Title variants present in the doc.
    assert "Vymedzená zemepisná oblasť" in titles.values()
    assert "Opis súvislostí" in titles.values()
    # The four roles downstream consumers depend on.
    for role in ("name", "geo_area", "grape_varieties", "link_to_terroir"):
        assert role in routed, role
    # Section 6 body (commune list) lands in geo_area, not terroir prose.
    assert "katastrálnych území" in routed["geo_area"]
    assert "Abovce" in routed["geo_area"]
    # Section 8 body lands in link_to_terroir.
    assert "južnej hranice" in routed["link_to_terroir"]
    # The category section 2 ("Druh zemepisného označenia") body is CHZO,
    # and it must NOT have shadowed the real area despite carrying
    # "zemepisného" — the geo_area blocklist keeps it out.
    assert routed["geo_area"].strip() != "CHZO – chránené zemepisné označenie"


# ==========================================================================
# Section routing — the OLDER template variant (the same roles, other titles)
# ==========================================================================

def test_routing_old_template_titles(fixture_text):
    """The older template (Skalický rubín): geo titled the shorter
    "Vymedzená oblasť", link titled "Údaje potvrdzujúce spojitosť". Both
    must route to the SAME semantic roles as the newer titles, so
    downstream consumers stay template-agnostic."""
    sections, titles, routed = _route_html(
        fixture_text("sk_jednotny_dokument_old_skalicky-rubin.html")
    )
    # The older, shorter title variants are what this doc carries.
    assert "Vymedzená oblasť" in titles.values()
    assert "Vymedzená zemepisná oblasť" not in titles.values()
    assert "Údaje potvrdzujúce spojitosť" in titles.values()
    assert "Opis súvislostí" not in titles.values()
    # …yet they route to the identical roles.
    for role in ("name", "geo_area", "grape_varieties", "link_to_terroir"):
        assert role in routed, role
    assert "katastrálneho územia mesta Skalica" in routed["geo_area"]
    assert "Bielych Karpát" in routed["link_to_terroir"]
    # Section 7 (the grape list) lands in grape_varieties, not geo/terroir.
    assert "Svätovavrinecké" in routed["grape_varieties"]


def test_both_title_variants_are_wired_in_keyword_table():
    """Pin that BOTH the newer and older title forms live in the keyword
    table — a future trim of either re-opens the routing regression."""
    geo = SECTION_ROLE_KEYWORDS["geo_area"]
    assert "vymedzená zemepisná oblasť" in geo  # newer
    assert "vymedzená oblasť" in geo  # older
    link = SECTION_ROLE_KEYWORDS["link_to_terroir"]
    assert "opis súvislostí" in link  # newer
    assert "údaje potvrdzujúce spojitosť" in link  # older


# ==========================================================================
# Grape parsing — flat list + the `Name - synonym` split
# ==========================================================================

def test_grape_parsing_flat_red_list(fixture_text):
    """Skalický rubín section 7 is a flat 3-variety red list (one per
    line). All resolve to principal (no role split in the SK single
    document); each carries the noir colour from the lexicon."""
    _sections, _titles, routed = _route_html(
        fixture_text("sk_jednotny_dokument_old_skalicky-rubin.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    assert set(grapes["principal"]) == {
        "sankt-laurent", "blaufrankisch", "blauer-portugieser"
    }
    # No principal/accessory split — everything is principal.
    assert grapes["accessory"] == []
    by_slug = {d["slug"]: d for d in grapes["details"]}
    # The canonical Slovak names are kept as the display name.
    assert by_slug["sankt-laurent"]["name"] == "Svätovavrinecké"
    assert by_slug["blaufrankisch"]["name"] == "Frankovka modrá"
    for d in grapes["details"]:
        assert d["role"] == "principal"


def test_grape_parsing_name_synonym_em_dash_split(fixture_text):
    """The Tokaj grape section uses the `Name - synonym` form
    (`Kövérszőlő - Tučné hrozno`, `Zéta - Zeta`). The canonical name
    before the ` - ` separator resolves; the synonym blob is a fallback."""
    _sections, _titles, routed = _route_html(
        fixture_text("sk_jednotny_dokument_tokaj_predikat.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    slugs = set(grapes["principal"])
    # Furmint / Kabar / Lipovina / Muškát žltý plus the hyphen-synonym rows.
    assert {"furmint", "kabar", "harslevelu"} <= slugs
    assert "koverszolo" in slugs  # from "Kövérszőlő - Tučné hrozno"
    assert "zeta" in slugs  # from "Zéta - Zeta"
    # The display name is the segment BEFORE " - " (synonym dropped).
    by_slug = {d["slug"]: d for d in grapes["details"]}
    assert by_slug["koverszolo"]["name"] == "Kövérszőlő"
    assert "Tučné" not in by_slug["koverszolo"]["name"]


# ==========================================================================
# Style detection — colour keyword + the Tokaj predikát ladder regression
# ==========================================================================

def test_styles_colour_keyword_from_description(fixture_text):
    """A clean "Opis vína" section body carrying a colour phrase yields the
    colour style. Skalický rubín's description ("Červené víno") → noir."""
    sections, titles, routed = _route_html(
        fixture_text("sk_jednotny_dokument_old_skalicky-rubin.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    styles = extract.parse_styles(sections, titles, grapes)
    # Red wine → noir; the red grapes also carry noir, reinforcing it.
    assert "noir" in styles
    # No sparkling / sweet markers in this plain red doc.
    assert "sparkling" not in styles
    assert "grains-nobles" not in styles


def test_regression_tokaj_predikat_ladder_styles(fixture_text):
    """Regression (commit b869b1b): the Tokaj doc has NO single "Opis vín"
    section — each wine TYPE is its own numbered ti-grseq-1 section
    (Tokajský výber, bobuľový výber, ľadové víno, slamové víno, Likérové
    víno, Sekt). parse_styles must scan the section TITLES + per-type
    bodies, so the full predikát ladder is detected. Before the fix this
    document rendered with zero styles."""
    sections, titles, routed = _route_html(
        fixture_text("sk_jednotny_dokument_tokaj_predikat.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    styles = set(extract.parse_styles(sections, titles, grapes))
    # The botrytis / late-harvest / straw / ice / sparkling / liqueur tags
    # are recovered from the per-wine-type section titles.
    assert "grains-nobles" in styles  # bobuľový výber (botrytis)
    assert "vendanges-tardives" in styles  # ľadové víno
    assert "vin-de-paille" in styles  # slamové víno
    assert "vin-de-liqueur" in styles  # Likérové víno
    assert "sparkling" in styles  # Sekt V. O.
    # The white predikát grapes give the base colour style.
    assert "blanc" in styles
    # Sanity: the fix turned a zero-style document into a rich one.
    assert len(styles) >= 5


# ==========================================================================
# specifikacija.py — §f two-column Odroda/Synonymum table (left column only)
# ==========================================================================

def _nitrianska(fixture_text) -> dict:
    text = fixture_text("sk_specifikacija_nitrianska_two_column.txt")
    return specifikacija.parse_specifikacija(text, "nitrianska")


def test_specifikacija_template_and_routing(fixture_text):
    out = _nitrianska(fixture_text)
    assert out["parser_template"] == "upv-sr-specifikacia-v1"
    # The lettered b/d/f/g sections routed to their roles.
    roles = out["section_roles"]
    assert roles["grape_varieties"]  # f)
    assert "katastrálne územia" in roles["geo_area"]  # d)
    # g) terroir narrative landed in link_to_terroir.
    assert "Vinohrady" in out["link_to_terroir"]


def test_specifikacija_left_odroda_column_only(fixture_text):
    """The §f grape set is built from the LEFT (Odroda) column only. Every
    canonical Slovak name resolves; the right-column synonyms do not become
    separate varieties."""
    out = _nitrianska(fixture_text)
    by_slug = {d["slug"]: d for d in out["grapes"]["details"]}
    slugs = set(by_slug)
    # Canonical left-column names, white block.
    assert {"aurelius", "bouvier", "devin", "chardonnay", "irsai-oliver",
            "muscat-ottonel", "muller-thurgau", "welschriesling", "pinot-gris",
            "sauvignon", "gewurztraminer"} <= slugs
    # Canonical left-column names, red block.
    assert {"alibernet", "blaufrankisch", "blauer-portugieser", "nitranka",
            "rudava", "pinot-noir", "sankt-laurent", "zweigelt"} <= slugs
    # The display name is always the left (Odroda) cell, never a synonym.
    assert by_slug["feteasca-regala"]["name"] == "Feteasca regala"
    assert by_slug["welschriesling"]["name"] == "Rizling vlašský"
    assert by_slug["sankt-laurent"]["name"] == "Svätovavrinecké"


def test_regression_synonym_column_not_leaked(fixture_text):
    """The CRITICAL seam: the "Feteasca regala" row carries "Pesecká
    leánka" in the right (Synonymum) column, and "Dievčie hrozno" carries
    "Leányka" / "Feteasca alba". Read as bare names those synonyms resolve
    to feteasca-ALBA — the WRONG variety for the Feteasca-regala row. The
    parser takes only the left column, so:
      * feteasca-regala comes from its own left cell "Feteasca regala",
      * feteasca-alba comes from its own left cell "Dievčie hrozno",
    and NEITHER comes from a leaked synonym."""
    out = _nitrianska(fixture_text)
    by_slug = {d["slug"]: d for d in out["grapes"]["details"]}
    # Both varieties present, each pinned to its own left-column name.
    assert by_slug["feteasca-regala"]["name"] == "Feteasca regala"
    assert by_slug["feteasca-alba"]["name"] == "Dievčie hrozno"
    # No detail's display name is a right-column synonym string.
    names = {d["name"] for d in out["grapes"]["details"]}
    for synonym in ("Pesecká leánka", "Pesecké dievčie hrozno", "Leányka",
                    "Welschriesling", "Pinot gris", "Gewürtztraminer",
                    "Olasz rizling"):
        assert synonym not in names, synonym
    # A wrapped synonym-continuation line ("vlašský" alone, the wrap of the
    # Rizling vlašský synonym blob) must not have become a variety either.
    assert all(d["name"] != "vlašský" for d in out["grapes"]["details"])


def test_specifikacija_colour_bucket_split(fixture_text):
    """MUŠTOVÉ BIELE → white block, MUŠTOVÉ MODRÉ → red block. When the
    lexicon assigns no colour, a variety in the standalone-labelled red
    block inherits the noir bucket hint.

    ACTUAL-behaviour pin: the WHITE bucket label is GLUED to the first
    variety ("MUŠTOVÉ Aurelius", " BIELE   Bouvierovo hrozno") rather than
    sitting on its own line, so it is never a dedicated bucket-label line
    and the white block gets NO bucket colour fallback — lexicon-empty
    whites keep colour "". Only the standalone "MUŠTOVÉ" / "MODRÉ" label
    lines flip the hint, so the bucket fallback fires for the red block."""
    out = _nitrianska(fixture_text)
    by_slug = {d["slug"]: d for d in out["grapes"]["details"]}
    # Red block, lexicon gives these no colour → noir bucket fallback.
    for slug in ("alibernet", "nitranka", "rudava"):
        assert by_slug[slug]["colour"] == "noir", slug
    # Lexicon-coloured reds.
    assert by_slug["blauer-portugieser"]["colour"] == "noir"
    assert by_slug["sankt-laurent"]["colour"] == "noir"
    # White block: lexicon colours where known…
    assert by_slug["welschriesling"]["colour"] == "blanc"
    assert by_slug["chardonnay"]["colour"] == "blanc"
    # …and the documented quirk — a lexicon-empty white (Sauvignon) does
    # NOT inherit a bucket colour because the white label was glued, so its
    # colour stays "".
    assert by_slug["sauvignon"]["colour"] == ""


def test_specifikacija_styles_from_description(fixture_text):
    """Section b) "Opis vína" drives style detection: "Biele, ružové a
    červené" → base colours, "sekty" → sparkling, "likérové vína" →
    vin-de-liqueur."""
    out = _nitrianska(fixture_text)
    styles = set(out["styles"])
    assert "vin-de-liqueur" in styles
    # blanc + rouge come from the grape-colour fallback (white + red blocks).
    assert "blanc" in styles
    assert "rouge" in styles


# ==========================================================================
# specifikacija.py — the older numbered 03.N prihláška template
# ==========================================================================

def test_prihlaska_template_detected_and_flat_list(fixture_text):
    """The 1996 Karpatská perla prihláška has no lettered a–i sections and
    a flat §03.5 inline variety list, so parse_specifikacija falls through
    to the upv-sr-prihlaska-v1 branch."""
    text = fixture_text("sk_specifikacija_karpatska_prihlaska.txt")
    out = specifikacija.parse_specifikacija(text, "karpatska-perla")
    assert out["parser_template"] == "upv-sr-prihlaska-v1"
    # The full flat roster (31 varieties in the real doc) resolves.
    assert len(out["grapes"]["principal"]) == 31
    assert out["grapes"]["accessory"] == []


def test_prihlaska_ocr_noisy_names_recovered(fixture_text):
    """The OCR scan mangles several names — "C hardonnay", "Mu ~kát
    Ottonel", "MUller Thurgau" — but the fuzzy matcher + targeted repairs
    recover the canonical slug."""
    text = fixture_text("sk_specifikacija_karpatska_prihlaska.txt")
    out = specifikacija.parse_specifikacija(text, "karpatska-perla")
    slugs = set(out["grapes"]["principal"])
    assert "chardonnay" in slugs  # "C hardonnay"
    assert "muscat-ottonel" in slugs  # "Mu ~kát Ottonel"
    assert "muller-thurgau" in slugs  # "MUller Thurgau"
    # The flat list carries both Feteasca regala and Dievčie hrozno, so
    # both feteasca slugs are present (no two-column gutter here).
    assert "feteasca-regala" in slugs
    assert "feteasca-alba" in slugs
