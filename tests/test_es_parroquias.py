"""Behaviour tests for the Galician parroquia step
(`scripts/_lib/es/parroquia.py`, `parse_parroquia_inclusions` in
`scripts/_lib/es/commune_list.py`, `apply_es_parroquias` in
`scripts/_lib/geom_chain.py`, the panel attribution in
`scripts/_lib/content_block.py`).

Pinned with the nine Galician records' own delimitation sentences and
the IET layer's own spellings ("Iria Flavia (Santa María)", "O Porto do
Son", "Fumaces e A Trepa (Santa María)"). The polygon index is synthetic:
disjoint unit squares, so an area counts the parishes drawn.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib import geom_chain  # noqa: E402
from _lib.content_block import RenderCtx, render_content_block  # noqa: E402
from _lib.es.commune_list import parse_commune_list, parse_parroquia_inclusions  # noqa: E402
from _lib.es.geometry import ESPolygonIndex  # noqa: E402
from _lib.es.parroquia import ESParroquiaIndex, normalise_parroquia_name  # noqa: E402
from _lib.geom_chain import (  # noqa: E402
    ES_PARROQUIA_ONLY_SOURCE,
    ES_PARROQUIA_PROVENANCE,
    apply_es_parroquias,
)
from _lib.map_template import build_labels  # noqa: E402

# --------------------------------------------------------------------------
# parser — the phrasings the nine records use
# --------------------------------------------------------------------------

_BARBANZA = (
    "Los términos municipales de Boiro, Catoira, Dodro, A Pobra do Caramiñal, "
    "Pontecesures, Rianxo, Ribeira y Valga, así como las parroquias de Camboño, "
    "Fruíme y Tállara del término municipal de Lousame; las parroquias de Iria "
    "Flavia y Padrón, del término municipal de Padrón; las parroquias de Baroña, "
    "Caamaño, Queiruga, Ribasieira, San Pedro de Muro y Xuño, del término "
    "municipal de Porto do Son; y la parroquia de Seira, del término municipal "
    "de Rois.\nLa mayor parte de esta zona geográfica se encuentra en la "
    "provincia de A Coruña."
)

_BETANZOS = (
    "constituida por los terrenos aptos para la producción de uva de\n"
    "los términos municipales de Bergondo, Betanzos, Coirós, Miño y Paderne, así\n"
    "como de las parroquias de Abegondo, Cabanas, Cerneda, Cos, Cullergondo,\n"
    "Leiro, Limiñón, Mabegondo, Meangos, Montouto, Presedo, Sarandóns,\n"
    "Vilacoba y Viós en el término municipal de Abegondo; de las parroquias de\n"
    "Bandoxa, Cis, Cuíña, Mondoi, Oza, Porzomillos, Reboredo, Salto y Vivente del\n"
    "término municipal de Oza dos Ríos y de las parroquias de Osedo y Soñeiro del\n"
    "término municipal de Sada.\n\n"
    "Todos los términos municipales mencionados se encuentran en la provincia de\n"
    "A Coruña, en la Comunidad Autónoma de Galicia."
)

_VALLE_DEL_MINO = (
    "constituida por los terrenos aptos para la producción de\n"
    "uva pertenecientes a los términos municipales y parroquias siguientes:\n\n"
    "    - Amoeiro: las parroquias de Parada de Amoeiro y Trasalba.\n\n"
    "    - Barbadás: las parroquias de Barbadás, Bentraces, Loiro, Piñor, Sobrado do\n"
    "    Bispo y A Valenzá.\n\n"
    "    - O Pereiro de Aguiar: las parroquias de Calvelle, A Lamela, Melias, Sabadelle,\n"
    "    San Xoán de Moreiras, Tibiás y Vilariño.\n"
    "Pliego de Condiciones IGP Valle del Miño - Ourense/Val de Miño - Ourense\n"
    "                                                          3\n"
    "    - A Peroxa: las parroquias de Gueral, A Peroxa y Vilarrubín.\n\n"
    "    - Quintela de Leirado: la parroquia de Quintela de Leirado.\n\n"
    "Todos los términos municipales mencionados se encuentran en la provincia de\n"
    "Ourense, en la Comunidad Autónoma de Galicia."
)

_MONTERREI = (
    "El territorio delimitado está dividido en dos subzonas:\n—\n"
    "Subzona valle de Monterrei: las parroquias de Castrelo do Val, Pepín y Nocedo do "
    "Val del ayuntamiento de Castrelo do Val; las parroquias de Albarellos, Infesta, "
    "Mon-terrei y Vilaza del ayuntamiento de Monterrei; las parroquias de Oímbra, "
    "Rabal, y San Cibrao del ayuntamiento de Oímbra y las parroquias de Abedes, "
    "Cabreiroá, Tama-guelos, Tintores, Verín y Vilamaior do Val del ayuntamiento de "
    "Verín.\n—\n"
    "Subzona ladera de Monterrei: comprende el ayuntamiento de Vilardevós, las "
    "parro-quias de Gondulfes y Servoi del ayuntamiento de Castrelo do Val; las "
    "parroquias de As Chas, Bousés, Videferre y A Granxa del ayuntamiento de Oímbra; "
    "la parroquia de Queirugás del ayuntamiento de Verín; del ayuntamiento de Riós, "
    "las parroquias de Castrelo de Abaixo, Castrelo de Cima, Fuma-ces e A Trepa, Progo "
    "y Riós; del ayuntamiento de Cualedro, las parroquias de San Millao, Montes, "
    "Rebordondo y A Xironda; y del ayuntamiento de Laza, las parroquias de Matamá y "
    "Retorta."
)

_RIBEIRO = (
    "está constituida por los terrenos que se encuentran en los términos municipales "
    "y lugares siguientes: ayuntamientos de Ribadavia, Arnoia, Castrelo de Miño, "
    "Carballeda de Avia, Leiro, Cenlle, Beade, Punxín y Cortegada; las parroquias de "
    "Banga, Cabanelas y O Barón, en el ayuntamiento de O Carballiño; las parroquias de "
    "Pazos de Arenteiro, Albarellos, Laxas, Cameixa y Moldes en el ayuntamiento de "
    "Boborás; los lugares de Santa Cruz de Arrabaldo y Untes en el ayuntamiento de "
    "Ourense, y del ayuntamiento de Toén los lugares de Puga, A Eirexa de Puga, O "
    "Olivar, el pueblo de Feá y Celeirón y la parroquia de Alongos; y el pueblo de A "
    "Touza del ayuntamiento de San Amaro.\nTodos estos términos municipales están en "
    "la provincia de Ourense, en la Comunidad Autónoma de Galicia."
)

_TERRAS_DO_NAVIA = (
    "constituida por los terrenos aptos para la producción de uva, de las parroquias "
    "de Cereixido, Lamas de Moreira, Monteseiro, San Martiño de Suarna, Vilabol de "
    "Suarna y Vilar da Cuiña en el municipio de A Fonsagrada; de las parroquias de A "
    "Pobra de Navia, Barcia, Castañedo, Muñís, Mosteiro y A Ribeira en el municipio de "
    "Navia de Suarna; y la totalidad del municipio de Negueira de Muñiz. Todo el "
    "territorio se encuentra en la provincia de Lugo, Comunidad Autónoma de Galicia.\n"
    "Las parroquias son entidades locales territoriales reconocidas en el ordenamiento "
    "jurídico de la Comunidad Autónoma de Galicia."
)


def _by_muni(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for e in parse_parroquia_inclusions(text):
        out.setdefault(e["municipio"], []).extend(e["parroquias"])
    return out


def test_parishes_first_with_holder_last():
    # "las parroquias de A, B y C del término municipal de X" and the
    # singular "la parroquia de A, del término municipal de X".
    assert _by_muni(_BARBANZA) == {
        "Lousame": ["Camboño", "Fruíme", "Tállara"],
        "Padrón": ["Iria Flavia", "Padrón"],
        "Porto do Son": ["Baroña", "Caamaño", "Queiruga", "Ribasieira", "San Pedro de Muro",
                         "Xuño"],
        "Rois": ["Seira"],
    }


def test_chained_enumerations_bind_each_to_its_own_holder():
    # "… en el término municipal de Abegondo; de las parroquias de … del
    # término municipal de Oza dos Ríos y de las parroquias de Osedo y
    # Soñeiro del término municipal de Sada" — three holders, no leak.
    got = _by_muni(_BETANZOS)
    assert set(got) == {"Abegondo", "Oza dos Ríos", "Sada"}
    assert got["Sada"] == ["Osedo", "Soñeiro"]
    assert got["Oza dos Ríos"][0] == "Bandoxa" and got["Oza dos Ríos"][-1] == "Vivente"
    assert "Vilacoba" in got["Abegondo"] and "Viós" in got["Abegondo"]


def test_line_form_keeps_wrapped_names_and_skips_the_page_footer():
    got = _by_muni(_VALLE_DEL_MINO)
    assert got == {
        "Amoeiro": ["Parada de Amoeiro", "Trasalba"],
        "Barbadás": ["Barbadás", "Bentraces", "Loiro", "Piñor", "Sobrado do Bispo",
                     "A Valenzá"],
        "O Pereiro de Aguiar": ["Calvelle", "A Lamela", "Melias", "Sabadelle",
                                "San Xoán de Moreiras", "Tibiás", "Vilariño"],
        "A Peroxa": ["Gueral", "A Peroxa", "Vilarrubín"],
        "Quintela de Leirado": ["Quintela de Leirado"],
    }


def test_monterrei_forms_holder_first_oxford_comma_whole_municipio_and_galician_e():
    got = parse_parroquia_inclusions(_MONTERREI)
    by = {}
    for e in got:
        by.setdefault(e["municipio"], []).append(e)
    # ", y San Cibrao" (Oxford comma) is a third parish, not dropped.
    assert by["Oímbra"][0]["parroquias"] == ["Oímbra", "Rabal", "San Cibrao"]
    # "del ayuntamiento de Riós, las parroquias de …" — holder first; the
    # Galician " e " stays inside the parish name.
    assert by["Riós"][0]["parroquias"] == [
        "Castrelo de Abaixo", "Castrelo de Cima", "Fuma-ces e A Trepa", "Progo", "Riós",
    ]
    assert by["Laza"][0]["parroquias"] == ["Matamá", "Retorta"]
    # "comprende el ayuntamiento de Vilardevós" is a whole-municipio inclusion.
    assert by["Vilardevós"] == [{"municipio": "Vilardevós", "parroquias": [], "whole": True}]
    # The hyphenated "parro-quias" still anchors the Castrelo do Val clause.
    assert [e["parroquias"] for e in by["Castrelo do Val"]] == [
        ["Castrelo do Val", "Pepín", "Nocedo do Val"], ["Gondulfes", "Servoi"],
    ]
    # Every enumeration of the two subzonas is accounted for: 4 in the
    # valle, 6 plus the whole Vilardevós in the ladera.
    assert len(got) == 11


def test_holder_first_gap_may_not_cross_another_holder():
    # Alongos belongs to Toén, not to Ourense named just before; the lugares
    # and pueblos in between are villages and are not parishes.
    assert _by_muni(_RIBEIRO) == {
        "O Carballiño": ["Banga", "Cabanelas", "O Barón"],
        "Boborás": ["Pazos de Arenteiro", "Albarellos", "Laxas", "Cameixa", "Moldes"],
        "Toén": ["Alongos"],
    }


def test_totalidad_del_municipio_is_a_whole_inclusion():
    got = parse_parroquia_inclusions(_TERRAS_DO_NAVIA)
    assert got[-1] == {"municipio": "Negueira de Muñiz", "parroquias": [], "whole": True}
    assert got[0]["municipio"] == "A Fonsagrada" and len(got[0]["parroquias"]) == 6
    assert got[1]["municipio"] == "Navia de Suarna" and got[1]["parroquias"][0] == "A Pobra de Navia"


def test_no_parish_enumeration_means_no_inclusions():
    assert parse_parroquia_inclusions("") == []
    # Cangas's terroir prose mentions "parroquias como Entreviñas" — no list.
    assert parse_parroquia_inclusions(
        "así pueblos como La Viña, parroquias como Entreviñas, barrios como Viña Grandiella"
    ) == []


def test_whole_municipio_parsing_is_unchanged():
    # The keep-cases: the whole-municipio parser still strips the parish
    # enumerations with their holders.
    assert parse_commune_list(_BARBANZA) == [
        "Boiro", "Catoira", "Dodro", "A Pobra do Caramiñal", "Pontecesures",
        "Rianxo", "Ribeira", "Valga",
    ]
    assert parse_commune_list(_BETANZOS) == ["Bergondo", "Betanzos", "Coirós", "Miño", "Paderne"]
    assert parse_commune_list(_VALLE_DEL_MINO) == [
        "Amoeiro", "Barbadás", "O Pereiro de Aguiar", "A Peroxa", "Quintela de Leirado",
    ]


# --------------------------------------------------------------------------
# index — matching against the layer's own spellings
# --------------------------------------------------------------------------

_PARROQUIAS = [
    # (INE, CONCELLO, PARROQUIA) as the IET layer writes them.
    ("15065", "Padrón", "Carcacía (San Pedro)"),
    ("15065", "Padrón", "Iria Flavia (Santa María)"),
    ("15065", "Padrón", "Padrón (Santiago)"),
    ("15071", "O Porto do Son", "Baroña (San Pedro)"),
    ("15071", "O Porto do Son", "San Pedro de Muro (San Pedro)"),
    ("15071", "O Porto do Son", "Xuño (Santa Mariña)"),
    ("15074", "Rois", "Seira (San Lourenzo)"),
    ("15075", "Sada", "Osedo (San Xián)"),
    ("32091", "Vilardevós", "Vilardevós (San Miguel)"),
    ("15001", "Abegondo", "Sarandós (Santa María)"),
    ("15001", "Abegondo", "Vilacova (San Tomé)"),
    ("15902", "Oza Cesuras", "Bandoxa (San Martiño)"),
    ("32085", "Verín", "Ábedes (Santa María)"),
    ("32085", "Verín", "A Rasela (Santa María)"),
    ("32085", "Verín", "Tamaguelos (Santa María)"),
    ("32071", "Riós", "Fumaces e A Trepa (Santa María)"),
    ("32071", "Riós", "O Riós (Santa María)"),
    ("32050", "Monterrei", "San Cristovo (San Cristovo)"),
    ("32054", "Ourense", "Ourense"),
    ("32020", "Cartelle", "San Tomé das Olas (San Tomé)"),
]


def _parroquia_index(tmp_path: Path | None = None, overrides: dict | None = None):
    ov = tmp_path / "overrides.json" if tmp_path is not None else Path("/nonexistent.json")
    if overrides is not None:
        ov.write_text(json.dumps(overrides, ensure_ascii=False), encoding="utf-8")
    idx = ESParroquiaIndex(zip_path=Path("/nonexistent.zip"), overrides_path=ov)
    for i, (ine, concello, name) in enumerate(_PARROQUIAS):
        idx._add(ine, name, concello, box(i * 2, 10, i * 2 + 1, 11))
    return idx


def test_normalisation_drops_the_saint_suffix_and_the_article():
    assert normalise_parroquia_name("Iria Flavia (Santa María)") == "iria flavia"
    assert normalise_parroquia_name("A Rasela (Santa María)") == "rasela"
    assert normalise_parroquia_name("Ábedes (Santa María)") == "abedes"


def test_exact_matches_and_reports_the_unmatched():
    idx = _parroquia_index()
    geom, st = idx.union_parroquias("15065", ["Iria Flavia", "Padrón", "Herbón"])
    assert st == {"matched": ["Iria Flavia", "Padrón"], "unmatched": ["Herbón"]}
    assert geom.area == 2
    # Never across municipios: Seira is a parish of Rois, not of Padrón.
    assert idx.union_parroquias("15065", ["Seira"])[1]["unmatched"] == ["Seira"]


def test_hyphenation_artefact_article_and_galician_e_reach_the_layer():
    idx = _parroquia_index()
    _geom, st = idx.union_parroquias(
        "32085", ["Tama-guelos", "Abedes", "A Rasela"],
    )
    assert st["matched"] == ["Tamaguelos", "Ábedes", "A Rasela"]
    _geom, st = idx.union_parroquias("32071", ["Fuma-ces e A Trepa", "Riós"])
    assert st["matched"] == ["Fumaces e A Trepa", "O Riós"]


def test_saint_prefix_is_tolerated_only_when_the_pliego_writes_it():
    idx = _parroquia_index()
    # The pliego's "San Pedro de Muro" is the layer's exact name.
    assert idx.union_parroquias("15071", ["San Pedro de Muro"])[1]["matched"] == ["San Pedro de Muro"]
    # A bare "Cristovo" for the layer's "San Cristovo" is not tolerated.
    assert idx.union_parroquias("32050", ["Cristovo"])[1]["unmatched"] == ["Cristovo"]
    # A pliego "San Tomé" for the layer's "San Tomé das Olas" needs a pin.
    assert idx.union_parroquias("32020", ["San Tomé"])[1]["unmatched"] == ["San Tomé"]


def test_curator_pin_binds_the_pliego_spelling_and_a_stale_pin_is_ignored(tmp_path):
    idx = _parroquia_index(tmp_path, {
        "betanzos": {
            "_note": "Sarandóns / Sarandós; Vilacoba / Vilacova",
            "_municipios": {"Oza dos Ríos": "15902"},
            "15001": {"Sarandóns": "Sarandós", "Vilacoba": "Vilacova", "Nowhere": "Absent"},
        },
    })
    _geom, st = idx.union_parroquias("15001", ["Sarandóns", "Vilacoba", "Nowhere"], slug="betanzos")
    assert st == {"matched": ["Sarandós", "Vilacova"], "unmatched": ["Nowhere"]}
    # The pin is per record: another slug does not inherit it.
    assert idx.union_parroquias("15001", ["Sarandóns"], slug="other")[1]["unmatched"] == ["Sarandóns"]
    assert idx.municipio_override("betanzos", "Oza dos Ríos") == "15902"
    assert idx.municipio_override("other", "Oza dos Ríos") is None
    assert idx.ine_for_concello("Porto do Son") == "15071"


# --------------------------------------------------------------------------
# resolver — apply_es_parroquias on a synthetic GISCO index
# --------------------------------------------------------------------------

_MUNIS = [
    ("15011", "Boiro"), ("15065", "Padrón"), ("15071", "Porto do Son"), ("15074", "Rois"),
    ("15075", "Sada"), ("31212", "Sada"), ("15001", "Abegondo"), ("15902", "Oza-Cesuras"),
    ("27035", "Negueira de Muñiz"), ("32085", "Verín"), ("32091", "Vilardevós"),
    ("32071", "Riós"), ("32075", "San Cibrao das Viñas"),
]


def _gisco_index() -> ESPolygonIndex:
    idx = ESPolygonIndex(Path("/nonexistent.gpkg"), Path("/nonexistent.zip"))
    for i, (ine, name) in enumerate(_MUNIS):
        idx._add_municipio(box(i * 2, 0, i * 2 + 1, 1), ine, name)
    return idx


def _muni_geom(gisco: ESPolygonIndex, ine: str):
    return gisco._munis_by_ine[ine].geom


def test_parishes_join_a_commune_list_union_and_the_holder_stays_out():
    gisco = _gisco_index()
    parr = _parroquia_index()
    ES_PARROQUIA_PROVENANCE.clear()
    record = {"country": "es", "slug": "barbanza-e-iria", "geo_area_brief": _BARBANZA}
    base = _muni_geom(gisco, "15011")
    geom, source, stats = apply_es_parroquias(
        record, gisco, base, "gisco-commune-list", {"matched": 1, "unmatched": 0}, index=parr,
    )
    assert source == "gisco-commune-list"
    # Boiro + Iria Flavia + Padrón + Baroña + San Pedro de Muro + Xuño + Seira.
    assert geom.area == 7
    # Porto do Son's three other parishes are not in the fixture; Lousame is
    # not a municipio of it at all.
    assert stats["matched"] == 1 and stats["parroquias"] == {"matched": 6, "unmatched": 3}
    prov = ES_PARROQUIA_PROVENANCE["barbanza-e-iria"]
    assert prov["matched"][:2] == ["Padrón: Iria Flavia", "Padrón: Padrón"]
    assert prov["unmatched"] == ["Porto do Son: Caamaño", "Porto do Son: Queiruga",
                                 "Porto do Son: Ribasieira"]
    assert prov["municipios_unmatched"] == ["Lousame"]
    assert geom.intersection(_muni_geom(gisco, "15065")).area == 0


def test_holder_named_whole_by_a_curator_pin_is_replaced_by_its_parishes():
    # Terras do Navia: the research pin unions three whole municipios; the
    # pliego keeps one whole and limits the other two to parishes.
    gisco = _gisco_index()
    parr = _parroquia_index()
    text = (
        "de las parroquias de Iria Flavia y Padrón en el municipio de Padrón; y la "
        "totalidad del municipio de Negueira de Muñiz."
    )
    record = {"country": "es", "slug": "t", "geo_area_brief": text}
    base = _muni_geom(gisco, "15065").union(_muni_geom(gisco, "27035"))
    geom, source, stats = apply_es_parroquias(
        record, gisco, base, "geometry-research-municipios", {"matched": 2, "unmatched": 0},
        index=parr,
    )
    assert source == "geometry-research-municipios"
    assert geom.intersection(_muni_geom(gisco, "15065")).area == 0
    assert geom.intersection(_muni_geom(gisco, "27035")).area == 1
    assert geom.area == 3 and stats["matched"] == 1


def test_a_record_without_a_polygon_becomes_a_parish_union():
    gisco = _gisco_index()
    parr = _parroquia_index()
    record = {"country": "es", "slug": "s", "geo_area_brief": _BARBANZA}
    geom, source, stats = apply_es_parroquias(
        record, gisco, None, "none", {"matched": 0, "unmatched": 0}, index=parr,
    )
    assert source == ES_PARROQUIA_ONLY_SOURCE and geom.area == 6
    assert stats["matched"] == 0


def test_a_parish_delimited_subzona_reads_its_own_block_of_the_parent_text():
    gisco = _gisco_index()
    parr = _parroquia_index()
    record = {
        "country": "es", "slug": "monterrei-ladera-de-monterrei", "name": "Ladera de Monterrei",
        "is_sub_denomination": True, "parent_slug": "monterrei",
        "geo_area_brief": "Servoi del ayuntamiento de Castrelo do Val; las parroquias de As Chas",
        "sections": {"6": _MONTERREI}, "section_roles": {"geo_area": "6"},
    }
    # The comma-split subzona_communes bound San Cibrao das Viñas whole; that
    # union is replaced, not refined.
    stray = _muni_geom(gisco, "32075")
    geom, source, stats = apply_es_parroquias(
        record, gisco, stray, "gisco-commune-union-subzona", {"matched": 1, "unmatched": 18},
        index=parr,
    )
    assert source == ES_PARROQUIA_ONLY_SOURCE
    assert geom.intersection(stray).area == 0
    # Vilardevós whole + Fumaces e A Trepa + O Riós (the valle's Verín
    # parishes belong to the other block and are not drawn).
    assert geom.intersection(_muni_geom(gisco, "32091")).area == 1
    assert geom.area == 3
    assert ES_PARROQUIA_PROVENANCE[record["slug"]]["whole_municipios"] == ["Vilardevós"]
    assert "Verín: Ábedes" not in ES_PARROQUIA_PROVENANCE[record["slug"]]["matched"]


def test_ambiguous_municipio_is_kept_only_inside_galicia_and_never_guessed():
    gisco = _gisco_index()
    parr = _parroquia_index()
    assert geom_chain._es_municipio_ine(gisco, parr, "x", "Sada") == "15075"
    # An exact GISCO hit outside the layer, and a first-word fallback, resolve
    # to nothing.
    assert geom_chain._es_municipio_ine(gisco, parr, "x", "Oza dos Ríos") is None
    assert geom_chain._es_municipio_ine(gisco, parr, "x", "San Cibrao del ayuntamiento") is None


def test_zone_sources_and_other_countries_are_left_alone(capsys):
    gisco = _gisco_index()
    parr = _parroquia_index()
    ES_PARROQUIA_PROVENANCE.clear()
    base = _muni_geom(gisco, "15011")
    for source in ("mapa-zone", "figshare-pdo", "sigpac-hybrid-pliego"):
        record = {"country": "es", "slug": "z", "geo_area_brief": _BARBANZA}
        assert apply_es_parroquias(record, gisco, base, source, {}, index=parr) == (base, source, {})
    # The MAPA zone is Boiro whole, which the text lists plainly, not as a
    # parish holder: the zone is kept and the card gets no parishes line.
    assert "z" not in ES_PARROQUIA_PROVENANCE
    assert "MAPA zone kept — municipio(s) unresolved: Lousame" in capsys.readouterr().err
    record = {"country": "fr", "slug": "f", "geo_area_brief": _BARBANZA}
    assert apply_es_parroquias(record, gisco, base, "gisco-commune-list", {}, index=parr)[1] == "gisco-commune-list"
    assert apply_es_parroquias(record, gisco, base, "gisco-commune-list", {}, index=parr)[0] is base


_PADRON_AND_VILARDEVOS = (
    "de las parroquias de Iria Flavia y Padrón en el municipio de Padrón; y la "
    "totalidad del municipio de Vilardevós."
)


def _zone_case(text: str, zone, capsys):
    gisco = _gisco_index()
    parr = _parroquia_index()
    ES_PARROQUIA_PROVENANCE.clear()
    record = {"country": "es", "slug": "z", "geo_area_brief": text}
    got = apply_es_parroquias(
        record, gisco, zone, "mapa-zone", {"matched": 1, "unmatched": 0}, index=parr,
    )
    return gisco, got, capsys.readouterr().err


def test_a_whole_municipio_mapa_zone_is_redrawn_from_the_parishes_its_pliego_names(capsys):
    # Monterrei: the MAPA zone is whole municipios; the pliego names two
    # parishes of one and the other whole. A neighbour grazed by the zone's
    # digitisation (2 % of Boiro) is neither covered nor partial.
    gisco = _gisco_index()
    zone = _muni_geom(gisco, "15065").union(_muni_geom(gisco, "32091")).union(box(0.98, 0, 1, 1))
    gisco, (geom, source, stats), err = _zone_case(_PADRON_AND_VILARDEVOS, zone, capsys)
    assert source == ES_PARROQUIA_ONLY_SOURCE
    # Padrón is replaced by its two parishes; Vilardevós comes whole from GISCO.
    assert geom.intersection(_muni_geom(gisco, "15065")).area == 0
    assert geom.intersection(_muni_geom(gisco, "32091")).area == 1
    assert geom.intersection(_muni_geom(gisco, "15011")).area == 0
    assert geom.area == 3
    assert stats == {"matched": 1, "unmatched": 0, "parroquias": {"matched": 2, "unmatched": 0}}
    prov = ES_PARROQUIA_PROVENANCE["z"]
    assert prov["zone_superseded"] == "mapa-zone"
    assert prov["matched"] == ["Padrón: Iria Flavia", "Padrón: Padrón"]
    assert prov["whole_municipios"] == ["Vilardevós"]
    assert "mapa-zone drawn at whole-municipio resolution (2 municipios) redrawn" in err


def test_a_mapa_zone_is_kept_when_the_parishes_do_not_restate_it(capsys):
    gisco = _gisco_index()
    padron, negueira = _muni_geom(gisco, "15065"), _muni_geom(gisco, "32091")
    whole = padron.union(negueira)
    cases = [
        # A municipio covered in part: the zone is a real delimitation.
        (_PADRON_AND_VILARDEVOS, padron.union(box(20, 0, 20.5, 1)),
         "covers Vilardevós in part"),
        # A municipio of the zone the text does not name.
        (_PADRON_AND_VILARDEVOS, whole.union(_muni_geom(gisco, "15011")),
         "the text does not name: Boiro"),
        # A unit below the parish (Ribeiro's lugares): parishes alone would
        # under-draw the holder.
        (_PADRON_AND_VILARDEVOS + " Y el lugar de Herbón del municipio de Padrón.", whole,
         "a unit below the parish ('lugar')"),
        # A parish the layer lacks.
        ("de las parroquias de Iria Flavia y Herbón en el municipio de Padrón; y la "
         "totalidad del municipio de Vilardevós.", whole,
         "parish(es) unmatched: Padrón: Herbón"),
    ]
    for text, zone, reason in cases:
        _gisco, got, err = _zone_case(text, zone, capsys)
        assert got == (zone, "mapa-zone", {"matched": 1, "unmatched": 0}), reason
        assert "z" not in ES_PARROQUIA_PROVENANCE, reason
        assert "MAPA zone kept — " in err and reason in err, (reason, err)


def test_municipios_covered_tells_whole_from_partial_from_grazed():
    gisco = _gisco_index()
    zone = _muni_geom(gisco, "15065").union(box(20, 0, 20.5, 1)).union(box(0.98, 0, 1, 1))
    assert gisco.municipios_covered(zone) == (["15065"], ["32091"])
    assert gisco.municipio_name("32091") == "Vilardevós"
    assert gisco.municipio_name("00000") is None


def test_missing_layer_leaves_the_geometry_untouched():
    gisco = _gisco_index()
    absent = ESParroquiaIndex(zip_path=Path("/nonexistent.zip"), overrides_path=Path("/none.json"))
    base = _muni_geom(gisco, "15011")
    record = {"country": "es", "slug": "b", "geo_area_brief": _BARBANZA}
    assert apply_es_parroquias(record, gisco, base, "gisco-commune-list", {"matched": 1}, index=absent)[0] is base


# --------------------------------------------------------------------------
# panel — the IET attribution on every record that draws parishes
# --------------------------------------------------------------------------

def _ctx() -> RenderCtx:
    return RenderCtx(
        locale="fr", labels=build_labels(lambda s: s), region_labels={},
        country_labels={"es": "Espagne"}, country_flag_emoji={"es": "🇪🇸"},
        grapes_info={}, styles_info={}, style_labels={},
        github_new_issue_url="https://github.com/x/y/issues/new",
    )


def test_ssr_card_shows_the_parishes_with_the_iet_attribution_and_licence():
    sources = {
        "country": "es",
        "parroquias_url": "https://abertos.xunta.gal/x",
        "parroquias_licence_url": "https://mapas.xunta.gal/es/aviso-legal",
        "parroquias_licence": "CC BY 4.0",
        "parroquias_attribution": "© Xunta de Galicia – IET, Mapa de Parroquias",
        "parroquias_matched": ["Padrón: Iria Flavia", "Padrón: Padrón"],
        "parroquias_unmatched": [],
    }
    rec = {"name": "Barbanza e Iria", "kind": "IGP", "country": "es", "region": "Galicia",
           "geom_source": "gisco-commune-list", "communes_matched": 8, "sources": sources}
    out = render_content_block(rec, "barbanza-e-iria", _ctx())
    assert "Padrón: Iria Flavia; Padrón: Padrón" in out
    assert "© Xunta de Galicia – IET, Mapa de Parroquias · CC BY 4.0" in out
    assert 'href="https://mapas.xunta.gal/es/aviso-legal"' in out
    assert "Mapa de Parroquias de Galicia (IET, Xunta de Galicia)" in out
    # The commune-union line is still there: the parishes complete it.
    assert "unités administratives" in out
    # Without parishes nothing of it is rendered.
    rec["sources"] = {"country": "es"}
    out = render_content_block(rec, "barbanza-e-iria", _ctx())
    assert "Parroquias" not in out


# --------------------------------------------------------------------------
# stage 00 — the manifest dates the layer from the zip it fetched
# --------------------------------------------------------------------------

def _parroquias_zip(path: Path, shp_date: tuple[int, ...]) -> Path:
    import zipfile

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("Parroquias.shp", date_time=shp_date), b"shp")
        linea = zipfile.ZipInfo("Parroquias_linea.shp", date_time=(2026, 2, 11, 9, 7, 50))
        zf.writestr(linea, b"x")
    return path


def test_dataset_date_comes_from_the_zips_parroquias_shp_entry(tmp_path):
    from _lib.es.parroquia import parroquias_dataset

    got = parroquias_dataset(_parroquias_zip(tmp_path / "Parroquias.zip", (2027, 3, 5, 10, 0, 0)))
    assert got["dataset_date"] == "2027-03-05"
    assert "2027-03-05" in got["dataset"] and "2026-06-01" not in got["dataset"]


def test_stage00_records_the_fetched_zips_date_in_the_manifest(tmp_path, monkeypatch):
    import importlib.util
    import shutil

    path = Path(__file__).resolve().parents[1] / "scripts" / "es" / "00_fetch_data.py"
    spec = importlib.util.spec_from_file_location("es_00_fetch_data_parroquias", path)
    stage00 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage00)
    served = _parroquias_zip(tmp_path / "served.zip", (2027, 3, 5, 10, 0, 0))
    out = tmp_path / "raw" / "Parroquias.zip"
    manifest = tmp_path / "raw" / "manifest.json"

    def fake_curl(cmd, **kwargs):
        shutil.copyfile(served, cmd[cmd.index("-o") + 1])

    monkeypatch.setattr(stage00, "ROOT", tmp_path)
    monkeypatch.setattr(stage00, "PARROQUIAS_ZIP", out)
    monkeypatch.setattr(stage00, "PARROQUIAS_MANIFEST", manifest)
    monkeypatch.setattr(stage00.subprocess, "run", fake_curl)
    stage00.fetch_xunta_parroquias()
    written = json.loads(manifest.read_text(encoding="utf-8"))
    assert written["dataset_date"] == "2027-03-05"
    assert "shapefile dated 2027-03-05" in written["dataset"]
