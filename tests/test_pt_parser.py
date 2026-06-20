"""Fixture-based regression tests for the Portugal (PT) parsers.

Three parser modules, each a documented seam in the IVV-caderno pipeline
(see the PT section of CLAUDE.md and the module docstrings):

  - scripts/_lib/pt/caderno_sections.py — keyword-anchor section finder.
      PT cadernos come in three structural variants and the parser must
      carve the same semantic roles (`area` / `grapes` / `link` / `yields`
      …) out of all of them WITHOUT knowing which variant it is reading:
        Variant A — "Roman + Arabic" with a "V. DOCUMENTO ÚNICO" wrapper
                    (Douro, Porto, Alentejo). Repeating roles → last-write
                    wins (the numbered interior copy, not the Roman
                    preamble).
        Variant B — Arabic-only / documento-único-first (Vinho Verde).
        Variant C — Arabic-short / older format (Dão), with mixed-case
                    headers and the "Meio Geográfico" link variant.
      Anchors require a numeric prefix ("5. ÁREA…") so in-prose mentions
      don't become false section boundaries.

  - scripts/_lib/pt/subregiao.py — sub-região (DGC analogue) detection.
      Pattern A: "Sub-região [de|do|da] NAME" line headers + a body
        (Vinho Verde lists them in the grapes section, one casta table
        each).
      Pattern B: Douro-style "NAME: no distrito de X …" colon prefix,
        gated behind a "três áreas geográficas" / "sub-regiões" preamble
        so captions don't false-fire.
      extract_subregioes tries A on (area + grapes), then B on area,
      and returns whichever fires with ≥ 2 matches (else parent-only).

  - scripts/_lib/pt/commune_list.py — "Área Delimitada" concelho/distrito
      parsing. Handles the enumerated "os municípios de X, Y e Z" list,
      the "Todos os municípios dos distritos de …" distrito-all form, the
      "abrange todo o distrito de X" whole-distrito form, the bare
      "Distrito de X." sentence, and the "Arquipélago dos Açores" macro
      token.

Real cached docs live under raw/pt/ivv/cadernos/*.pdf (gitignored). The
fixtures here are short redacted excerpts under tests/fixtures/, with
expected output cross-checked against raw/pt/cadernos-extracted/*.json.

Assertions are on STRUCTURE (carved role keys, sub-região names + pattern
tag, concelho / distrito / macro sets), not full-output snapshots. Where a
test pins ACTUAL parser behaviour that diverges from the docstring's ideal
(the distrito name leaking into the concelho list; the Pattern A header
form vs. the section-1 bullet list), the divergence is called out inline.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.pt.caderno_sections import extract_sections  # noqa: E402
from _lib.pt.commune_list import parse_commune_list  # noqa: E402
from _lib.pt.subregiao import (  # noqa: E402
    detect_pattern_a,
    detect_pattern_b,
    extract_subregioes,
    slugify,
)


def _names(records: list[dict]) -> list[str]:
    return [r["name"] for r in records]


def _slugs(records: list[dict]) -> list[str]:
    return [r["slug"] for r in records]


def _patterns(records: list[dict]) -> set[str]:
    return {r["source_pattern"] for r in records}


# ==========================================================================
# caderno_sections — keyword-anchor section routing across variants
# ==========================================================================

def test_caderno_variant_b_roles_routed(fixture_text):
    """Variant B (Vinho Verde, Arabic-only). The three roles the downstream
    consumers depend on land in the right bodies."""
    sec = extract_sections(fixture_text("pt_caderno_variantB_vinho-verde.txt"))
    assert {"area", "grapes", "link"} <= set(sec)
    # "5. ZONA GEOGRÁFICA DEMARCADA" body → area (commune list prose),
    # NOT the link narrative.
    assert sec["area"].startswith("A área geográfica de produção da DO")
    assert "Todos os municípios dos distritos de Braga" in sec["area"]
    # "6. PRINCIPAL(IS) CASTA(S) DE UVA" body → grapes.
    assert "As castas utilizadas na produção" in sec["grapes"]
    assert "Alvarinho" in sec["grapes"]
    # "7. RELAÇÃO COM A ZONA GEOGRÁFICA" body → link (terroir prose).
    assert sec["link"].startswith("Elementos relativos à área geográfica")
    assert "clima atlântico" in sec["link"]
    # Section boundaries are clean: the grape names did not bleed into area,
    # and the area commune prose did not bleed into grapes.
    assert "Alvarinho" not in sec["area"]
    assert "Todos os municípios" not in sec["grapes"]


def test_caderno_variant_c_roles_routed(fixture_text):
    """Variant C (Dão, Arabic-short older format). Exercises the
    "Delimitação da Área Geográfica" area-header variant, the "Relação com
    o Meio Geográfico" link variant, and a distinct `yields` role from
    "Rendimentos Máximos por Hectare"."""
    sec = extract_sections(fixture_text("pt_caderno_variantC_dao.txt"))
    assert {"area", "grapes", "link", "yields"} <= set(sec)
    # "4. Delimitação da Área Geográfica" → area.
    assert sec["area"].startswith("A área da Região Demarcada do Dão")
    assert "os municípios de Arganil" in sec["area"]
    # "5. Rendimentos Máximos por Hectare" → yields, carved out as its own
    # body (not glued onto the area commune list).
    assert "Rendimento máximo por hectare" in sec["yields"]
    assert "Arganil" not in sec["yields"]
    # "6. Castas Utilizadas:" → grapes.
    assert "Castas tintas" in sec["grapes"]
    assert "Touriga-Nacional" in sec["grapes"]
    # "7. Relação com o Meio Geográfico" → link (the "Meio Geográfico"
    # variant, not "Área/Zona Geográfica").
    assert "Factores Naturais" in sec["link"]
    assert "graníticos" in sec["link"]


def test_caderno_variant_a_last_write_wins(fixture_text):
    """Variant A (Douro) wraps numbered interior sections inside
    "V. DOCUMENTO ÚNICO". For a role that appears both in the Roman
    preamble and the numbered interior, the LAST (interior, content-rich)
    copy must win — the parser's last-write-wins rule."""
    sec = extract_sections(fixture_text("pt_caderno_variantA_douro.txt"))
    assert {"area", "grapes", "link"} <= set(sec)
    # "5. ÁREA DELIMITADA" interior body → area (the Pattern-B sub-region
    # colon-prefix prose).
    assert "três áreas geográficas mais restritas" in sec["area"]
    assert "Baixo Corgo: no distrito de Vila Real" in sec["area"]
    # "6. UVAS DE VINHO" → grapes; "7. RELAÇÃO COM A ÁREA GEOGRÁFICA" → link.
    assert "Inventário das principais castas" in sec["grapes"]
    assert sec["link"].startswith("Elementos relativos à área geográfica")
    assert "bacia hidrográfica do Douro" in sec["link"]


def test_caderno_anchor_requires_numeric_prefix():
    """A bare in-prose mention ("a área delimitada da DOP é …") without a
    "N." numeric prefix must NOT become a section boundary — otherwise the
    real section bodies would be sheared at the false anchor."""
    text = (
        "1. NOME E TIPO\n"
        "O nome a registar é Exemplo. A área delimitada da DOP é pequena "
        "e a sua zona geográfica demarcada está bem definida.\n"
        "5. ÁREA DELIMITADA\n"
        "Os municípios de Arganil e Tábua.\n"
    )
    sec = extract_sections(text)
    # Only the numbered "5. ÁREA DELIMITADA" anchored the area; the in-prose
    # "área delimitada" mention in section 1's body did not split it.
    assert "Os municípios de Arganil e Tábua" in sec["area"]
    assert "O nome a registar" not in sec["area"]


def test_caderno_no_anchors_returns_empty():
    # Defensive: a document with no recognisable section header yields {}.
    assert extract_sections("Texto livre sem cabeçalhos numerados.") == {}


# ==========================================================================
# subregiao — Pattern A ("Sub-região NAME" headers, Vinho Verde)
# ==========================================================================

def test_subregiao_pattern_a_vinho_verde_nine(fixture_text):
    text = fixture_text("pt_subregiao_patternA_vinho-verde.txt")
    out = detect_pattern_a(text)
    # All 9 Vinho Verde sub-regiões, article ("de/do/da") stripped from the
    # captured name.
    assert _names(out) == [
        "Amarante",
        "Ave",
        "Baião",
        "Basto",
        "Cávado",
        "Lima",
        "Monção e Melgaço",
        "Paiva",
        "Sousa",
    ]
    assert _patterns(out) == {"A"}
    # Multi-word names survive ("de Monção e Melgaço" → "Monção e Melgaço").
    assert "Monção e Melgaço" in _names(out)


def test_subregiao_pattern_a_slug_diacritic_fold(fixture_text):
    text = fixture_text("pt_subregiao_patternA_vinho-verde.txt")
    out = detect_pattern_a(text)
    slugs = _slugs(out)
    # Slug folds diacritics + spaces.
    assert "cavado" in slugs
    assert "moncao-e-melgaco" in slugs
    assert slugify("Cávado") == "cavado"
    assert slugify("Monção e Melgaço") == "moncao-e-melgaco"


def test_subregiao_pattern_a_captures_casta_body(fixture_text):
    """Each "Sub-região NAME" header carries the casta-list lines beneath it
    as its body, up to the next header. The body is what stage 02 stores as
    the sub-region's geo_area_brief / inherited grape context."""
    text = fixture_text("pt_subregiao_patternA_vinho-verde.txt")
    out = detect_pattern_a(text)
    amarante = next(r for r in out if r["name"] == "Amarante")
    assert "Amaral" in amarante["body"]
    assert "Vinhão; Sousão" in amarante["body"]
    # The body stops before the next header — Ave's castas don't leak in.
    assert "Padeiro" not in amarante["body"]


def test_subregiao_pattern_a_ignores_section1_bullet_list():
    """The section-1 NOME block lists the sub-regiões as a guillemet bullet
    list ("- «Amarante»;"), NOT as "Sub-região NAME" headers. Pattern A is
    deliberately keyed on the header form, so the bullet list must NOT fire
    — that is why stage 02 routes Pattern A over the grapes section, not
    the name block."""
    bullets = "Sub-regiões:\n- «Amarante»;\n- «Ave»;\n- «Baião»;\n- «Sousa»."
    assert detect_pattern_a(bullets) == []


# ==========================================================================
# subregiao — Pattern B (Douro colon prefix, preamble-gated)
# ==========================================================================

def test_subregiao_pattern_b_douro_three(fixture_text):
    """End-to-end via the variant-A Douro caderno fixture: the area section
    carries the "três áreas geográficas" preamble + the three colon-prefix
    items, so extract_subregioes returns the 3 sub-regiões tagged B."""
    sec = extract_sections(fixture_text("pt_caderno_variantA_douro.txt"))
    out = extract_subregioes(sec.get("area", ""), sec.get("grapes", ""))
    assert _names(out) == ["Baixo Corgo", "Cima Corgo", "Douro Superior"]
    assert _patterns(out) == {"B"}
    assert "douro-superior" in _slugs(out)


def test_subregiao_pattern_b_requires_preamble():
    """Pattern B is conservative: the colon-prefix items alone are NOT
    enough — a "três áreas geográficas" / "sub-regiões" preamble must
    appear, otherwise a stray "Name: no distrito …" caption would
    false-fire."""
    items = (
        "Baixo Corgo: no distrito de Vila Real abrange os concelhos de "
        "Mesão Frio e Peso da Régua.\n"
        "Cima Corgo: no distrito de Vila Real abrange as freguesias de "
        "Alijó e Amieiro.\n"
        "Douro Superior: no distrito de Bragança abrange a freguesia de "
        "Vilarelhos.\n"
    )
    # No preamble → no detection.
    assert detect_pattern_b(items) == []
    # Same items WITH the preamble → 3 detected.
    with_preamble = "agrupadas em três áreas geográficas mais restritas:\n" + items
    assert _names(detect_pattern_b(with_preamble)) == [
        "Baixo Corgo",
        "Cima Corgo",
        "Douro Superior",
    ]


def test_subregiao_extract_threshold_two():
    """extract_subregioes returns the empty list (parent-only DOP) when a
    pattern yields fewer than 2 matches — a single "Sub-região NAME" header
    is not enough to model a sub-denominated wine."""
    one_header = "Sub-região de Amarante\nAmaral\nAzal\nLoureiro\n"
    assert extract_subregioes("", one_header) == []


def test_subregiao_extract_empty_inputs():
    assert extract_subregioes("", "") == []


# ==========================================================================
# commune_list — Área Delimitada concelho / distrito / macro parsing
# ==========================================================================

def test_commune_list_enumerated_municipios(fixture_text):
    """Variant-C Dão area: "os municípios de Arganil, Oliveira do Hospital e
    Tábua" → the concelho names, list separators (comma + final " e ")
    split, articles stripped."""
    sec = extract_sections(fixture_text("pt_caderno_variantC_dao.txt"))
    cl = parse_commune_list(sec["area"])
    concelhos = cl["concelhos"]
    assert "Arganil" in concelhos
    assert "Oliveira do Hospital" in concelhos
    assert "Tábua" in concelhos
    assert "Seia" in concelhos
    assert "Tondela" in concelhos
    # Multi-word concelho survived the " e " split (it is one item, not two).
    assert "Oliveira do Hospital" in concelhos
    # No distrito names leaked into the concelho list for the Dão "Do
    # distrito de X, os municípios de …" form.
    for d in ("Coimbra", "Guarda", "Viseu"):
        assert d not in concelhos
    # Dão enumerates municípios, so distritos stays empty.
    assert cl["distritos"] == []


def test_commune_list_distrito_all_form(fixture_text):
    """Variant-B Vinho Verde area: "Todos os municípios dos distritos de
    Braga e de Viana do Castelo" → both distritos, expanded by the caller."""
    sec = extract_sections(fixture_text("pt_caderno_variantB_vinho-verde.txt"))
    cl = parse_commune_list(sec["area"])
    assert "Braga" in cl["distritos"]
    assert "Viana do Castelo" in cl["distritos"]
    # The enumerated municípios in the b)/c)/d)/e) clauses are also captured.
    for c in ("Arouca", "Amarante", "Baião", "Mondim de Basto", "Cinfães"):
        assert c in cl["concelhos"]


def test_commune_list_distrito_name_leaks_into_concelhos(fixture_text):
    """ACTUAL behaviour pin (divergence from the ideal): the
    "distritos de Braga e de Viana do Castelo" phrase is also matched by the
    município regex, and the " e " split surfaces "Viana do Castelo" as a
    concelho candidate. It is harmless downstream (a same-named município
    does exist and resolves), but the leak is real — pinned so a future
    tightening of the município regex is a conscious choice."""
    sec = extract_sections(fixture_text("pt_caderno_variantB_vinho-verde.txt"))
    cl = parse_commune_list(sec["area"])
    assert "Viana do Castelo" in cl["concelhos"]


def test_commune_list_pattern_samples(fixture_text):
    """The focused pattern fixture exercises every area-section shape in one
    pass: enumerated municípios, distrito-all, whole-distrito, bare
    "Distrito de X.", and the Açores archipelago macro token."""
    cl = parse_commune_list(fixture_text("pt_area_concelho_patterns.txt"))
    # Enumerated município list.
    assert {"Arganil", "Oliveira do Hospital", "Tábua"} <= set(cl["concelhos"])
    # "Todos os municípios dos distritos de Braga e de Viana do Castelo".
    assert "Braga" in cl["distritos"]
    # "abrange todo o distrito de Faro" — whole-distrito.
    assert "Faro" in cl["distritos"]
    # Bare "Distrito de Setúbal." standalone sentence.
    assert "Setúbal" in cl["distritos"]
    # "Arquipélago dos Açores" → macro token (caller expands to the ilhas).
    assert cl["macro_regions"] == ["acores"]


def test_commune_list_macro_archipelago_only():
    # An archipelago-only area section emits the macro token and no concelhos.
    text = 'A IG "Açores" abrange todas as ilhas do Arquipélago dos Açores.'
    cl = parse_commune_list(text)
    assert cl["macro_regions"] == ["acores"]
    assert cl["concelhos"] == []
    cl_m = parse_commune_list("A área abrange a Região Autónoma da Madeira.")
    assert cl_m["macro_regions"] == ["madeira"]


def test_commune_list_empty_input():
    cl = parse_commune_list("")
    assert cl == {
        "concelhos": [],
        "distritos": [],
        "macro_regions": [],
        "raw_hits": 0,
    }


def test_commune_list_rejects_boundary_prose():
    """Alentejo-style boundary prose ("Estremoz até à ribeira da Fonte Boa")
    is full of noise words; a município captured with such a tail must be
    rejected by the _NOISE_WORDS filter, not admitted with a long noise
    string."""
    text = (
        "os municípios de Estremoz até à ribeira da Fonte Boa onde prossegue "
        "pela estrada até ao limite do concelho."
    )
    cl = parse_commune_list(text)
    # The single captured token carries noise words ("até", "ribeira",
    # "estrada", "limite") → discarded; nothing survives.
    for c in cl["concelhos"]:
        assert "ribeira" not in c.lower()
        assert "estrada" not in c.lower()
