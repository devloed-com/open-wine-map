"""Fixture-based regression tests for the United Kingdom (GB) parsers.

One parser module, `scripts/_lib/gb/spec.py`, covering three document
layouts — the UK register is the only corpus where a single country ships
three unrelated templates:

  - **defra-pfn-2011** — the December-2011 DEFRA specifications
    (English/Welsh PDO + their Regional PGIs). A header block, then one
    `PART n: <CATEGORY>` per grapevine category, each with an upper-case
    `SPECIFICATION` subsection run. Two seams matter here:
      * The still roster is semicolon-separated and **wraps across PDF
        lines**, so a run of roster lines must be rejoined with a SPACE
        ("… Black Hamburg; Blau\\nPortugueser …" is one variety, not two).
      * The sparkling roster is bulleted one-per-line with NO separators
        (pdftotext renders the Wingdings bullet as U+F0B7), so that run
        must instead be rejoined with a SEPARATOR — the opposite rule.
        Getting this backwards merges six varieties into one string.
      Plus the two PART rosters must not bleed into each other
      ("Zweigeltrebe" + "Acolon" -> "Zweigeltrebe Acolon").

  - **uk-gi-single-document** — Sussex, the only post-Brexit UK-scheme
    registration. Numbered EU-style outline; `9. Link` is an empty header
    whose content lives entirely in 9.1 / 9.3, so routing must gather
    children. Its variety rosters sit in a section that also carries
    record-keeping and yield-dispensation PROSE, which must not reach the
    grape matcher.

  - **defra-pfn-application** — Darnibole, on the 2017 EU application
    form. It has NO link section, so `link_to_terroir` must fall back to
    `7 b) Definition of the demarcated area` (where the slate subsoil and
    the slope actually are), and its single variety is stated as a
    proportion ("100% Bacchus").

Two documented source typos are repaired structurally rather than through
`GRAPE_ALIAS`, because they split one name into two before any alias
could apply: Sussex's "Pinot Noir, Pinot Noir, Précoce" and the DEFRA
rosters' missing semicolon between Gamay and Garanoir.

Also pins `scripts/_lib/gb/darnibole.py` — the boundary reconstructed
from the OS/RPA parcel references on the specification's own plan.

Real cached documents live under raw/gb/specs/ (gitignored); the fixtures
here are short, redacted excerpts.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.gb import darnibole  # noqa: E402
from _lib.gb.region import derive_region  # noqa: E402
from _lib.gb.spec import detect_template, grape_candidates, parse_spec  # noqa: E402

# ─────────────────────────────────────────────── defra-pfn-2011 (English) ──


def test_defra_2011_template_and_header(fixture_text):
    parsed = parse_spec(fixture_text("gb_defra_pfn_2011_english.txt"))
    assert parsed["template"] == "defra-pfn-2011"
    assert parsed["protected_name"] == "ENGLISH"
    assert parsed["demarcation"] == "ENGLAND"
    # GENERAL PROVISIONS carries no wine and must be dropped.
    assert parsed["part_titles"] == ["STILL WINE", "QUALITY SPARKLING WINE"]


def test_defra_2011_roles(fixture_text):
    roles = parse_spec(fixture_text("gb_defra_pfn_2011_english.txt"))["roles"]
    assert roles["geo_area"] == "ENGLAND"
    # The link narrative is the pre-SPECIFICATION prose of each wine part.
    assert "49.9 degrees north" in roles["link_to_terroir"]
    assert "backbone of fine sparkling wines" in roles["link_to_terroir"]
    # …and must NOT swallow the regulatory subsections that follow it.
    assert "tartaric acid" not in roles["link_to_terroir"]
    assert "Still Wine: 80 hl/ha" in roles["yields"]


def test_defra_2011_line_wrapped_names_survive(fixture_text):
    """A roster wrapped by the PDF layout must rejoin with a space."""
    names = grape_candidates(
        parse_spec(fixture_text("gb_defra_pfn_2011_english.txt"))["roles"]["grape_varieties"]
    )
    assert "Blau Portugueser" in names
    assert "Madeleine Angevine" in names
    assert "Marechal Foch" in names
    assert "Blau" not in names and "Portugueser" not in names
    assert "Angevine" not in names


def test_defra_2011_bulleted_roster_splits_per_line(fixture_text):
    """The sparkling roster has no separators — one variety per bullet."""
    names = grape_candidates(
        parse_spec(fixture_text("gb_defra_pfn_2011_english.txt"))["roles"]["grape_varieties"]
    )
    for expected in ("Chardonnay", "Pinot Noir", "Pinot Noir Précoce",
                     "Pinot Meunier", "Pinot Blanc", "Pinot Gris"):
        assert expected in names, expected
    # The bullet glyph itself must never survive into a candidate.
    assert not any("\uf0b7" in n for n in names)


def test_defra_2011_parts_do_not_bleed_together(fixture_text):
    """The last name of PART 1's roster must not glue to PART 2's first."""
    names = grape_candidates(
        parse_spec(fixture_text("gb_defra_pfn_2011_english.txt"))["roles"]["grape_varieties"]
    )
    assert "Zweigeltrebe" in names
    assert not any(n.startswith("Zweigeltrebe ") for n in names)


def test_defra_2011_source_typo_and_synonym_tail(fixture_text):
    names = grape_candidates(
        parse_spec(fixture_text("gb_defra_pfn_2011_english.txt"))["roles"]["grape_varieties"]
    )
    # Missing semicolon in the source: alphabetical order (Gamaret, Gamay,
    # Garanoir, Gewurztraminer) proves these are two entries.
    assert "Gamay" in names and "Garanoir" in names
    assert "Gamay Garanoir" not in names
    # Parenthesised synonym tails are stripped; the head name is the one
    # the regulator authorises.
    assert "Rulander" in names
    assert not any(n.startswith("Rulander (") for n in names)


# ────────────────────────────────────────── uk-gi-single-document (Sussex) ──


def test_sussex_template_and_link_gathers_children(fixture_text):
    parsed = parse_spec(fixture_text("gb_uk_single_document_sussex.txt"))
    assert parsed["template"] == "uk-gi-single-document"
    assert parsed["demarcation"] == "East and West Sussex"
    link = parsed["roles"]["link_to_terroir"]
    # `9. Link` is an empty header — 9.1 and 9.3 are its content.
    assert "chalk of the South Downs" in link
    assert "longer growing season" in link


def test_sussex_prose_never_reaches_the_matcher(fixture_text):
    names = grape_candidates(
        parse_spec(fixture_text("gb_uk_single_document_sussex.txt"))["roles"]["grape_varieties"]
    )
    joined = " | ".join(names)
    for prose in ("vineyard owner", "exceptional circumstances", "tonnes per hectare",
                  "jeopardised", "Scheme Manager"):
        assert prose not in joined, prose


def test_sussex_source_typos_repaired(fixture_text):
    names = grape_candidates(
        parse_spec(fixture_text("gb_uk_single_document_sussex.txt"))["roles"]["grape_varieties"]
    )
    # "… Pinot Noir, Pinot Noir, Précoce, Regent …" — a stray comma splits
    # one name in two; no alias could repair it after the split.
    assert "Pinot Noir Précoce" in names
    assert "Précoce" not in names
    # Hyphenation across a line break.
    assert "Müller-Thurgau" in names
    assert "Müller- Thurgau" not in names
    assert "Regent" in names


# ──────────────────────────────────── defra-pfn-application (Darnibole) ──


def test_darnibole_template_and_terroir_fallback(fixture_text):
    parsed = parse_spec(fixture_text("gb_defra_application_darnibole.txt"))
    assert parsed["template"] == "defra-pfn-application"
    # No link section exists, so the demarcated-area definition stands in.
    link = parsed["roles"]["link_to_terroir"]
    assert "ancient slate" in link
    assert link == parsed["roles"]["geo_area"]


def test_darnibole_proportion_prefix_stripped(fixture_text):
    names = grape_candidates(
        parse_spec(fixture_text("gb_defra_application_darnibole.txt"))["roles"]["grape_varieties"]
    )
    assert names == ["Bacchus"]


# ───────────────────────────────────────────────── darnibole geometry ──


def test_darnibole_hull_matches_the_declared_area():
    """The hull of the seven demarcated parcel centroids should land close
    to the specification's declared "whole 5 hectare area"."""
    hull = darnibole.boundary_bng()
    assert len(darnibole.DEMARCATED_PARCELS) == 7
    hectares = hull.area / 1e4
    assert 5.0 <= hectares <= 8.0, hectares
    minx, miny, maxx, maxy = hull.bounds
    # OS 1 km square SX 03 67, on the south-facing slope above the Camel.
    assert 203000 <= minx and maxx <= 204000
    assert 67000 <= miny and maxy <= 68000


def test_darnibole_parcels_are_not_the_excluded_ones():
    """Parcels drawn on the plan but outside the red line stay out."""
    assert not set(darnibole.DEMARCATED_PARCELS) & set(darnibole.EXCLUDED_PARCELS)


# ──────────────────────────────────────────────────────── region facet ──


def test_region_by_file_number_and_demarcation_fallback():
    assert derive_region({"file_number": "PDO-GB-A1585"}) == "England"
    assert derive_region({"file_number": "PGI-GB-A1590"}) == "Wales"
    assert derive_region({"file_number": "PDO-GB-02365"}) == "England"   # Sussex
    assert derive_region({"file_number": "PDO-GB-N1636"}) == "England"   # Darnibole
    # A GI registered after this table was written falls back to the
    # specification's own DEMARCATION field.
    assert derive_region({"file_number": "PDO-GB-9999",
                          "demarcation": "WALES"}) == "Wales"
    assert derive_region({"file_number": "PDO-GB-9999"}) == "United Kingdom"


def test_demarcation_survives_an_empty_area_section():
    """An explicit "Demarcation:" line must win even when no area section
    parses — the region facet falls back to it, so losing it would drop a
    future GI to "United Kingdom"."""
    from _lib.gb.spec import parse_numbered_spec

    parsed = parse_numbered_spec(
        "Product specification for Testshire\n"
        "Demarcation: Testshire\n"
        "3. Details of protection\n"
        "3.1 Name of product to be registered\n"
        "Testshire\n",
        "uk-gi-single-document",
    )
    assert parsed["roles"]["geo_area"] == ""
    assert parsed["demarcation"] == "Testshire"


def test_detect_template_is_stable_across_all_three(fixture_text):
    assert detect_template(fixture_text("gb_defra_pfn_2011_english.txt")) == "defra-pfn-2011"
    assert detect_template(
        fixture_text("gb_defra_application_darnibole.txt")) == "defra-pfn-application"
    assert detect_template(
        fixture_text("gb_uk_single_document_sussex.txt")) == "uk-gi-single-document"
