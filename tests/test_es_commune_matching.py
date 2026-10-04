"""Behaviour tests for the ES commune-list → GISCO municipio chain
(`scripts/_lib/es/commune_list.py`, `scripts/_lib/es/subzona.py`,
`scripts/_lib/es/geometry.py`).

Each case is a defect found by the geometry-outlier audit of 2026-09-24,
pinned with the record's own delimitation text: a parish or village name
that bound to a same-first-word municipio in another province (Salinillas
de Buradón → Salinillas de Bureba, Alcocer de Planes → Guadalajara's
Alcocer, San Pedro de Muro → San Sadurniño, Vélez Banco → Vélez de
Benaudalla, Abegondo's parish Leiro → Ourense's Leiro), plus the keep-cases
the fix must not break (Elvillar / Bilar, Lapuebla de Labarca, Albelda de
Iregua).

The geometry index is built from a handful of synthetic municipios: the
rules under test are name normalisation, province context and the
fallback guards, none of which need real polygons.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.es import commune_list, geometry  # noqa: E402
from _lib.es.commune_list import (  # noqa: E402
    parse_commune_list,
    parse_parroquia_inclusions,
    parse_whole_commune_prefix,
)
from _lib.es.geometry import ESPolygonIndex, _normalise_commune_name  # noqa: E402
from _lib.es.subzona import (  # noqa: E402
    _is_commune_token,
    _split_inline_communes,
    extract_subzonas,
)

# --------------------------------------------------------------------------
# geometry.py — normalisation
# --------------------------------------------------------------------------

def test_hyphen_is_a_word_separator():
    assert _normalise_commune_name("Vélez-Rubio") == _normalise_commune_name("Vélez Rubio")
    assert _normalise_commune_name("Oyón-Oion").split(" ", 1)[0] == "oyon"


def test_bilingual_gisco_name_keeps_first_form_exactly():
    assert _normalise_commune_name("Labastida / Bastida") == "labastida"
    assert _normalise_commune_name("Yécora / Iekora") == "yecora"
    assert _normalise_commune_name("Elvillar / Bilar") == "elvillar"


# --------------------------------------------------------------------------
# geometry.py — union_communes province context
# --------------------------------------------------------------------------

_MUNIS = [
    # (INE, GISCO LAU_NAME) — INE's first two digits are the province.
    ("01011", "Baños de Ebro / Mañueta"),
    ("01019", "Kripan"),
    ("01022", "Elciego"),
    ("01023", "Elvillar / Bilar"),
    ("01028", "Labastida / Bastida"),
    ("01031", "Laguardia"),
    ("01033", "Lapuebla de Labarca"),
    ("01034", "Leza"),
    ("01041", "Navaridas"),
    ("01043", "Oyón-Oion"),
    ("01052", "Samaniego"),
    ("09334", "Salinillas de Bureba"),
    ("03003", "Agres"),
    ("03007", "Alcosser"),
    ("03056", "Cocentaina"),
    ("03133", "Torrevieja"),
    ("19009", "Alcocer"),
    ("04037", "Chirivel"),
    ("04063", "María"),
    ("04098", "Vélez-Blanco"),
    ("04099", "Vélez-Rubio"),
    ("18184", "Vélez de Benaudalla"),
    ("29094", "Vélez-Málaga"),
    ("15011", "Boiro"),
    ("15071", "Porto do Son"),
    ("15076", "San Sadurniño"),
    ("36044", "Pontecesures"),
    ("22009", "Albelda"),
    ("26005", "Albelda de Iregua"),
    ("26018", "Alfaro"),
    ("26036", "Calahorra"),
    ("31008", "Andosilla"),
    ("03107", "Polop"),
    ("03117", "Sanet y Negrals"),
    ("03119", "Sant Joan d'Alacant"),
    ("18050", "Cogollos de la Vega"),
    ("18051", "Cogollos de Guadix"),
    ("18101", "Huétor Vega"),
    ("22903", "San Miguel del Cinca"),
    ("22032", "Alcolea de Cinca"),
    ("02033", "Fuente-Álamo"),
    ("30016", "Cartagena"),
    ("30021", "Fuente Álamo de Murcia"),
    ("30037", "Torre-Pacheco"),
    ("19095", "Cogolludo"),
    ("19248", "San Andrés del Congosto"),
    ("19249", "San Andrés del Rey"),
    ("28107", "Patones"),
    ("28129", "San Agustín del Guadalix"),
    ("27031", "Monforte de Lemos"),
    ("27047", "Pobra do Brollón, A"),
    ("27050", "Quiroga"),
    ("27052", "Ribas de Sil"),
    ("32044", "Manzaneda"),
    ("32063", "Pobra de Trives, A"),
    ("32070", "San Xoán de Río"),
    ("25158", "Palau d'Anglesola, El"),
    ("25216", "Talarn"),
    ("25227", "Tremp"),
    ("25902", "Sant Martí de Riucorb"),
    ("42165", "San Esteban de Gormaz"),
    ("47114", "Peñafiel"),
    ("47130", "Quintanilla de Trigueros"),
    ("05260", "Villanueva del Campillo"),
    ("05241", "Tiemblo, El"),
    ("47218", "Villanueva de Duero"),
    ("24074", "Fuentes de Carbajal"),
    ("24089", "León"),
    ("41069", "Palacios y Villafranca, Los"),
    ("41095", "Utrera"),
    ("31254", "Villafranca"),
    ("25040", "Alcarràs"),
    ("25912", "Gimenells i el Pla de la Font"),
    ("09421", "Vid y Barrios, La"),
    ("09457", "Zuzones"),
    ("18054", "Cortes y Graena"),
    ("31078", "Cortes"),
    ("18089", "Guadix"),
]


def _index() -> ESPolygonIndex:
    idx = ESPolygonIndex(Path("/nonexistent.gpkg"), Path("/nonexistent.zip"))
    for i, (ine, name) in enumerate(_MUNIS):
        # Disjoint unit squares so the union's area counts the municipios.
        idx._add_municipio(box(i * 2, 0, i * 2 + 1, 1), ine, name)
    return idx


def _ines(idx: ESPolygonIndex, names: list[str]) -> set[str]:
    geom, _stats = idx.union_communes(names)
    if geom is None:
        return set()
    return {
        ine for ine, cand in idx._munis_by_ine.items()
        if geom.intersection(cand.geom).area > 0.5
    }


def test_rioja_alavesa_village_does_not_bind_outside_the_exact_provinces():
    # Salinillas de Buradón is a village of Labastida (Álava); the only
    # same-first-word GISCO row is in Burgos. The exact matches pin the
    # list to province 01, so the fallback is refused — and it must not
    # widen the province set either.
    idx = _index()
    got = _ines(idx, ["Elciego", "Laguardia", "Leza", "Navaridas", "Samaniego",
                      "Salinillas de Buradón"])
    assert "09334" not in got
    assert got == {"01022", "01031", "01034", "01041", "01052"}


def test_rioja_alavesa_bilingual_and_abbreviated_names_match():
    idx = _index()
    got = _ines(idx, ["Elciego", "Laguardia", "Elvillar de Álava", "Lapuebla de La barca",
                      "Labastida", "Yécora", "Oyón", "Baños de Ebro"])
    # Keep-cases the reviewer flagged: Elvillar / Bilar and Lapuebla de
    # Labarca are legitimately listed and stay bound.
    assert {"01023", "01033", "01028", "01011"} <= got
    # The pliego's bare "Oyón" reaches GISCO's "Oyón-Oion" through the
    # first-word fallback, accepted because it sits in province 01.
    assert "01043" in got


def test_alcocer_de_planes_does_not_become_guadalajara_alcocer():
    idx = _index()
    got = _ines(idx, ["Agres", "Cocentaina", "Alcocer de Planes"])
    assert "19009" not in got
    assert got == {"03003", "03056"}


def test_velez_typo_resolves_inside_almeria_and_hyphenated_name_matches_exactly():
    # The pliego writes "Vélez Banco" (Vélez-Blanco) and "Vélez Rubio".
    idx = _index()
    got = _ines(idx, ["Chirivel", "María", "Vélez Banco", "Vélez Rubio"])
    assert got == {"04037", "04063", "04098", "04099"}
    assert "18184" not in got


def test_generic_first_word_never_binds_a_parish():
    # San Pedro de Muro is a parish of Porto do Son; "san" proves nothing.
    idx = _index()
    got = _ines(idx, ["Boiro", "Pontecesures", "San Pedro de Muro"])
    assert "15076" not in got
    assert got == {"15011", "36044"}


def test_multi_word_fallback_needs_the_second_word():
    # Even inside the expected province, a fallback must match past the
    # first word: "Vélez Banco" reaches Vélez-Blanco through "velez b",
    # never Vélez-Rubio through the bare "velez ".
    idx = _index()
    got = _ines(idx, ["Chirivel", "Vélez Banco"])
    assert got == {"04037", "04098"}


def test_abbreviated_albelda_prefers_la_rioja_extension():
    # Rioja Oriental lists "Albelda" among La Rioja communes; Huesca's
    # bare-named Albelda is the only exact hit, but no other listed
    # commune supports Huesca while La Rioja carries several — the
    # abbreviation case the module docstring describes.
    idx = _index()
    got = _ines(idx, ["Alfaro", "Calahorra", "Andosilla", "Albelda"])
    assert "26005" in got
    assert "22009" not in got


def test_pliego_longer_form_and_particle_variants_still_bind():
    # The reverse of abbreviation: the pliego writes "Polop de la Marina"
    # for GISCO's "Polop", "Cogollos Vega" for "Cogollos de la Vega", "San
    # Miguel de Cinca" for "San Miguel del Cinca", the Catalan "i" and the
    # curly apostrophe. All are listed municipios of the same province.
    idx = _index()
    got = _ines(idx, ["Agres", "Cocentaina", "Polop de La Marina", "Sanet i Negrals",
                      "Sant Joan d\u2019Alacant"])
    assert {"03107", "03117", "03119"} <= got
    got = _ines(idx, ["Huétor Vega", "Cogollos Vega"])
    assert got == {"18101", "18050"}
    got = _ines(idx, ["Alcolea de Cinca", "San Miguel de Cinca"])
    assert got == {"22032", "22903"}


def test_generic_headed_abbreviation_binds_only_when_unique():
    idx = _index()
    # Two Guadalajara San Andrés extend "San Andrés": no evidence, no bind.
    assert _ines(idx, ["Cogolludo", "San Andrés"]) == {"19095"}
    # One Madrid extension of "San Agustín de Guadalix" (particle variant).
    assert _ines(idx, ["Patones", "San Agustín de Guadalix"]) == {"28107", "28129"}


def test_hyphenated_exact_hit_yields_to_the_in_province_extension():
    # Campo de Cartagena's "Fuente Álamo" now matches Albacete's
    # "Fuente-Álamo" exactly (hyphen folded); Murcia carries the other
    # votes, so Fuente Álamo de Murcia wins.
    idx = _index()
    got = _ines(idx, ["Cartagena", "Torre Pacheco", "Fuente Álamo"])
    assert got == {"30016", "30037", "30021"}


def test_exact_single_hit_stays_without_province_evidence():
    # With nothing else on the list, the exact hit is the only evidence.
    idx = _index()
    assert _ines(idx, ["Albelda"]) == {"22009"}


def test_a_shared_particle_is_not_evidence_and_equal_names_outrank_it():
    # Ribeira Sacra's Quiroga-Bibei subzona: "A Pobra de Brollón" is GISCO's
    # "Pobra do Brollón, A" (Lugo). Pobra de Trives (Ourense) shares the
    # longer prefix "pobra de " — a particle, not the place.
    idx = _index()
    got = _ines(idx, ["Monforte de Lemos", "A Pobra de Brollón", "Quiroga", "Ribas de Sil",
                      "Manzaneda", "San Xoán de Río"])
    assert "27047" in got
    assert "32063" not in got
    # Costers del Segre's Pallars subzona lists two villages that are not
    # municipios; "palau d'" / "sant marti de" must not bind them to Palau
    # d'Anglesola and Sant Martí de Riucorb, 50 km south.
    got = _ines(idx, ["Tremp", "Talarn", "Palau de Noguera", "Sant Martí de Barcedana"])
    assert got == {"25227", "25216"}


def test_the_next_word_must_be_a_spelling_not_just_an_initial():
    idx = _index()
    # Quintanilla de Tres Barrios is a village of San Esteban de Gormaz;
    # "tres" / "trigueros" share a letter, not a name.
    got = _ines(idx, ["San Esteban de Gormaz", "Peñafiel", "Quintanilla de Tres Barrios"])
    assert got == {"42165", "47114"}
    # A particle variant beats a longer shared prefix: Villanueva del Duero
    # is Villanueva de Duero, not Ávila's Villanueva del Campillo.
    got = _ines(idx, ["Peñafiel", "El Tiemblo", "Villanueva del Duero"])
    assert got == {"47114", "05241", "47218"}
    # A spelling variant of the next word still binds.
    assert _ines(idx, ["León", "Fuentes de Carvajal"]) == {"24089", "24074"}


# --------------------------------------------------------------------------
# commune_list.py — parish enumerations
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


def test_lowercase_asi_como_ends_the_list():
    assert parse_commune_list(_BARBANZA) == [
        "Boiro", "Catoira", "Dodro", "A Pobra do Caramiñal", "Pontecesures",
        "Rianxo", "Ribeira", "Valga",
    ]


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


def test_parish_enumerations_are_stripped_with_their_municipio():
    # "así\ncomo" breaks across a line, so the enumeration strip — not the
    # end marker — is what keeps Abegondo's parishes (Leiro, Cabanas) out.
    assert parse_commune_list(_BETANZOS) == ["Bergondo", "Betanzos", "Coirós", "Miño", "Paderne"]


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


def test_repeated_de_and_province_tail_are_not_part_of_the_name():
    text = ("que engloba los\ntérminos municipales de Villaviciosa de Córdoba y de "
            "Espiel en la provincia de\nCórdoba.")
    assert parse_commune_list(text) == ["Villaviciosa de Córdoba", "Espiel"]


def test_parcel_sentence_after_the_list_is_cut():
    text = ("ubicada en los términos municipales de Anchuras (Ciudad Real) y Sevilleja "
            "de la Jara (Toledo). Las parcelas afectadas son las siguientes:\n—\n"
            "En el Término municipal de Anchuras:\n—\nPolígono 5, parcelas: 319;")
    assert parse_commune_list(text) == ["Anchuras", "Sevilleja de la Jara"]


_SIERRAS_DE_MALAGA = (
    "La zona de producción de los vinos amparados por las Denominaciones de Origen «Sierras "
    "de Málaga» está constituida por los términos municipales de: Málaga, Alameda, Alcaucín, "
    "La Viñuela y Yunquera, pertenecientes a la provincia de Málaga, así como los términos "
    "municipales de Benamejí y Palenciana pertenecientes a la provincia de Córdoba.\n"
    "Subzona: Unidad geográfica menor que la zona de producción, que constituye un medio "
    "geográfico homogéneo.\nDentro de la zona de producción se distingue la subzona "
    "«Serranía de Ronda», comarca natural a la que pertenecen los términos municipales de "
    "Algatocín, Alpandeire y Ronda."
)

_MALAGA = (
    "está constituida por los terrenos ubicados en los términos municipales de:\n\n"
    "Málaga, Alameda, Alcaucín, Villanueva del Trabuco y La Viñuela pertenecientes a la "
    "provincia de\nMálaga, así como los municipios de Benamejí y Palenciana pertenecientes a "
    "la provincia\nde Córdoba\n\nAsímismo dentro de la zona de producción se distinguen las "
    "siguientes Áreas:\n\n- «Axarquía», a la que pertenecen los términos municipales de "
    "Alcaucín y Comares."
)


def test_asi_como_los_terminos_municipales_continues_the_list_to_its_sentence_end():
    # The mid-sentence "así como los términos municipales de" adds whole
    # municipios (the two Córdoba ones); only "así como las parroquias"
    # (Barbanza, Betanzos above) ends the list. The list stops with the
    # sentence, before the subzona paragraph.
    assert parse_commune_list(_SIERRAS_DE_MALAGA) == [
        "Málaga", "Alameda", "Alcaucín", "La Viñuela", "Yunquera", "Benamejí", "Palenciana",
    ]
    assert parse_commune_list(_MALAGA) == [
        "Málaga", "Alameda", "Alcaucín", "Villanueva del Trabuco", "La Viñuela", "Benamejí",
        "Palenciana",
    ]
    assert parse_commune_list(_BARBANZA)[-1] == "Valga"


def test_municipio_with_parishes_lines_keep_only_the_municipio():
    assert parse_commune_list(_VALLE_DEL_MINO) == [
        "Amoeiro", "Barbadás", "O Pereiro de Aguiar", "A Peroxa", "Quintela de Leirado",
    ]


# --------------------------------------------------------------------------
# subzona.py — the last subzona's commune capture
# --------------------------------------------------------------------------

_ALICANTE_TAIL = (
    "Subzona de L'Alcoià: Alcoy, Banyeres de Mariola, Benifallim y Penàguila.\n"
    "Subzona de El Comtat: Alfafara, Alcolecha, Agres, Benimarfull y Cocentaina. "
    "Viñedos ubicados dentro de la demarcación del «Parque Natural de las Lagunas "
    "de la Mata y Torrevieja».\n"
)


def test_last_subzona_stops_at_the_sentence_boundary():
    subs = {s["slug"]: s["communes"] for s in extract_subzonas(_ALICANTE_TAIL, "Alicante")}
    assert subs["el-comtat"] == ["Alfafara", "Alcolecha", "Agres", "Benimarfull", "Cocentaina"]
    assert subs["l-alcoia"] == ["Alcoy", "Banyeres de Mariola", "Benifallim", "Penàguila"]


def test_medio_vinalopo_marker_cut_is_unchanged():
    assert _split_inline_communes("Aspe, Hondón de las Nieves y Novelda. Así como los polígonos 3 y 4") == [
        "Aspe", "Hondón de las Nieves", "Novelda",
    ]


def test_quoted_or_sentence_tokens_are_not_communes():
    assert not _is_commune_token("Torrevieja»")
    assert not _is_commune_token("«Parque Natural")
    assert not _is_commune_token("Cocentaina. Viñedos ubicados")
    assert _is_commune_token("Cocentaina")


# --------------------------------------------------------------------------
# commune_list.py — parish inclusions (the enumerations stripped above are
# read back per holder for the IET parroquia layer; the detailed suite is
# tests/test_es_parroquias.py)
# --------------------------------------------------------------------------

def _inclusions(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for e in parse_parroquia_inclusions(text):
        out.setdefault(e["municipio"], []).extend(e["parroquias"] or ["<whole>"] * bool(e.get("whole")))
    return out


def test_parish_inclusions_parishes_first_and_singular_form():
    # "las parroquias de A, B y C del término municipal de X" / "la
    # parroquia de A, del término municipal de X".
    got = _inclusions(_BARBANZA)
    assert got["Padrón"] == ["Iria Flavia", "Padrón"]
    assert got["Rois"] == ["Seira"]
    assert got["Porto do Son"][-2:] == ["San Pedro de Muro", "Xuño"]
    # … and the whole-municipio list is what it was.
    assert parse_commune_list(_BARBANZA) == [
        "Boiro", "Catoira", "Dodro", "A Pobra do Caramiñal", "Pontecesures",
        "Rianxo", "Ribeira", "Valga",
    ]


def test_parish_inclusions_en_el_termino_and_y_de_las_chaining():
    got = _inclusions(_BETANZOS)
    assert got["Sada"] == ["Osedo", "Soñeiro"]
    assert got["Oza dos Ríos"] == ["Bandoxa", "Cis", "Cuíña", "Mondoi", "Oza", "Porzomillos",
                                   "Reboredo", "Salto", "Vivente"]
    assert len(got["Abegondo"]) == 14
    assert parse_commune_list(_BETANZOS) == ["Bergondo", "Betanzos", "Coirós", "Miño", "Paderne"]


def test_parish_inclusions_line_form():
    got = _inclusions(_VALLE_DEL_MINO)
    assert got["Amoeiro"] == ["Parada de Amoeiro", "Trasalba"]
    assert got["Barbadás"][-2:] == ["Sobrado do Bispo", "A Valenzá"]
    assert got["Quintela de Leirado"] == ["Quintela de Leirado"]
    assert parse_commune_list(_VALLE_DEL_MINO) == [
        "Amoeiro", "Barbadás", "O Pereiro de Aguiar", "A Peroxa", "Quintela de Leirado",
    ]


def test_parish_inclusions_ayuntamiento_concello_and_holder_first_forms():
    text = (
        "las parroquias de Gondulfes y Servoi del ayuntamiento de Castrelo do Val; "
        "la parroquia de Queirugás del concello de Verín; del ayuntamiento de Laza, "
        "las parroquias de Matamá y Retorta; y la totalidad del municipio de Negueira de Muñiz."
    )
    assert _inclusions(text) == {
        "Castrelo do Val": ["Gondulfes", "Servoi"],
        "Verín": ["Queirugás"],
        "Laza": ["Matamá", "Retorta"],
        "Negueira de Muñiz": ["<whole>"],
    }
    # No whole-municipio list in that sentence, as before.
    assert parse_commune_list(text) == []


# --------------------------------------------------------------------------
# subzona.py — a lower-case article opens a name (es-A, 2026-09-24)
# --------------------------------------------------------------------------

_RIBEIRA_SACRA = (
    "Subzona de Chantada: Carballedo, Chantada, Taboada, Portomarín y A Peroxa.\n—\n"
    "Subzona de Quiroga-Bibei: Monforte de Lemos, A Pobra de Brollón, Quiroga, "
    "Ribas de Sil, a Pobra de Trives, Manzaneda y San Xoán de Río.\n—\n"
    "Subzona de Ribeiras do Miño: Paradela, O Saviñao, Pantón, Sober y Monforte de Lemos."
)


def test_lower_case_article_opens_a_commune_name():
    # The pliego forgot the capital on "a Pobra de Trives"; the name is real.
    subs = {s["slug"]: s["communes"] for s in extract_subzonas(_RIBEIRA_SACRA, "Ribeira Sacra")}
    assert subs["quiroga-bibei"] == [
        "Monforte de Lemos", "A Pobra de Brollón", "Quiroga", "Ribas de Sil",
        "a Pobra de Trives", "Manzaneda", "San Xoán de Río",
    ]
    for tok in ("a Pobra de Trives", "o Rosal", "els Omellons", "les Borges Blanques",
                "l'Alcora", "sa Pobla", "es Castell", "el Vilosell", "la Pobla de Segur"):
        assert _is_commune_token(tok), tok
    # Prose that opens with the same articles keeps being rejected.
    for tok in ("los agregados de Cellers", "la parte norte del municipio", "el resto",
                "las pedanías de Tremp denominadas Gurb", "a partir de", "el término municipal",
                "la totalidad", "su agregado Escaladei", "os"):
        assert not _is_commune_token(tok), tok


def test_lower_case_article_name_binds_through_the_resolver():
    idx = _index()
    got = _ines(idx, ["Monforte de Lemos", "A Pobra de Brollón", "Quiroga", "Ribas de Sil",
                      "a Pobra de Trives", "Manzaneda", "San Xoán de Río"])
    assert "32063" in got


# --------------------------------------------------------------------------
# commune_list.py / subzona.py — compound municipio names stay whole (es-B)
# --------------------------------------------------------------------------

_LOS_PALACIOS = (
    "Delimitación del Área geográfica: comprende superficies incluidas en los términos\n"
    "municipales de Los Palacios y Villafranca, Utrera, Dos Hermanas y Alcalá de Guadaira,\n"
    "de la provincia de Sevilla, quedando definida por los siguientes límites:\n\n"
    "- Al Norte: El canal principal del Bajo Guadalquivir desde la salida del canal primario"
)

_SEGRIA = (
    "Unidad geográfica menor Segrià: Compuesta por las siguientes localidades:\n—\n"
    "Alcarràs\n—\nAlfarràs\n—\nAlmacelles\n—\nAlmenar\n—\nGimenells y Pla de la Font\n—\n"
    "Lleida\n—\nTorrefarrera\n"
)


def test_compound_municipio_is_not_split_on_the_conjunction():
    # Los Palacios: the " y " split gave a bare "Villafranca", which the
    # resolver bound to Navarra's Villafranca, 580 km from Sevilla.
    assert parse_commune_list(_LOS_PALACIOS) == [
        "Los Palacios y Villafranca", "Utrera", "Dos Hermanas", "Alcalá de Guadaira",
    ]
    assert parse_whole_commune_prefix(_LOS_PALACIOS)[0] == "Los Palacios y Villafranca"
    idx = _index()
    got = _ines(idx, parse_commune_list(_LOS_PALACIOS))
    assert "41069" in got and "31254" not in got


def test_compound_name_in_a_subzona_block_and_the_pliego_particle_variant():
    # Costers del Segre writes "Gimenells y Pla de la Font" for GISCO's
    # "Gimenells i el Pla de la Font": one municipio, kept whole and bound.
    subs = {s["slug"]: s["communes"] for s in extract_subzonas(_SEGRIA, "Costers del Segre")}
    assert subs["segria"] == [
        "Alcarràs", "Alfarràs", "Almacelles", "Almenar", "Gimenells y Pla de la Font",
        "Lleida", "Torrefarrera",
    ]
    assert _split_inline_communes("Cortes y Graena, Guadix y Purullena") == [
        "Cortes y Graena", "Guadix", "Purullena",
    ]
    idx = _index()
    assert _ines(idx, ["Alcarràs", "Gimenells y Pla de la Font"]) == {"25040", "25912"}
    # Altiplano de Sierra Nevada: "Cortes y Graena" is Granada's, not Navarra's Cortes.
    assert _ines(idx, ["Guadix", "Cortes y Graena"]) == {"18089", "18054"}


def test_compound_name_survives_a_split_inside_its_parenthesis():
    # Ribera del Duero: "LA VID Y BARRIOS (GUMA y ZUZONES)" was cut at the
    # " y " inside the parenthesis into "…(GUMA" and "ZUZONES)".
    got = parse_whole_commune_prefix(
        "los términos municipales de LA VID Y BARRIOS (GUMA y ZUZONES), ZUZONES, PEÑARANDA DE DUERO"
    )
    assert got == ["LA VID Y BARRIOS (GUMA y ZUZONES)", "ZUZONES", "PEÑARANDA DE DUERO"]


def test_two_real_municipios_side_by_side_are_never_fused():
    from _lib.es.commune_list import merge_compound_municipios

    # "Blecua y Torres" exists; "Blecua" next to "Torres de Alcanadre" is two places.
    assert merge_compound_municipios(["Blecua", "Torres de Alcanadre"], ["", ", "]) == [
        "Blecua", "Torres de Alcanadre",
    ]
    # A semicolon or a line break is a hard boundary.
    assert merge_compound_municipios(["Los Palacios", "Villafranca"], ["", "; "]) == [
        "Los Palacios", "Villafranca",
    ]
    assert merge_compound_municipios(["Los Palacios", "Villafranca"], ["", "\n"]) == [
        "Los Palacios", "Villafranca",
    ]
    # Three pieces across a comma and a conjunction (Empordà's list).
    assert merge_compound_municipios(
        ["Cruïlles", "Monells", "Sant Sadurní de l'Heura", "Forallac"], ["", ", ", " i ", ", "],
    ) == ["Cruïlles, Monells i Sant Sadurní de l'Heura", "Forallac"]


def test_compound_table_matches_the_gisco_layer():
    doc = json.loads(commune_list._COMPOUND_MUNICIPIOS_PATH.read_text(encoding="utf-8"))
    assert "LAU_RG_01M_2024_3035" in doc["_source"]
    rows = [(m["gisco_id"], m["name"]) for m in doc["municipios"]]
    assert rows == sorted(rows) and len(set(rows)) == len(rows)
    assert all(re.search(r"\s(?:y|i|e)\s", name) for _gid, name in rows)
    lau = Path(__file__).resolve().parents[1] / "raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip"
    if not lau.exists():
        pytest.skip("GISCO LAU zip not fetched")
    import geopandas as gpd

    gdf = gpd.read_file(lau, where="CNTR_CODE='ES'")
    expected = sorted(
        (gid, name) for gid, name in zip(gdf["GISCO_ID"], gdf["LAU_NAME"])
        if re.search(r"\s(?:y|i|e)\s", name)
    )
    assert rows == expected


# --------------------------------------------------------------------------
# geometry.py — former municipios bind to the one that absorbed them (es-C)
# --------------------------------------------------------------------------

_PALLARS_MUNIS = [
    ("25234", "Tremp"),
    ("25215", "Talarn"),
    ("25161", "Conca de Dalt"),
    ("25904", "Castell de Mur"),
    ("25098", "Gavet de la Conca"),
    ("25115", "Isona i Conca Dellà"),
    ("25158", "Palau d'Anglesola, El"),
    ("25902", "Sant Martí de Riucorb"),
    ("41095", "Utrera"),
]

# The Costers del Segre "Unidad geográfica menor Pallars" names, as the
# pliego spells them (curly apostrophes included).
_PALLARS_LIST = [
    "Tremp", "Palau de Noguera", "Puigcercós", "Suterranya", "Vilamitjana", "Conca de Dalt",
    "Guàrdia de Tremp", "Sant Martí de Barcedana", "Sant Miquel de la Vall",
    "Figuerola d’Orcau", "Orcau-Basturs", "Sant Romà d’Abella", "Talarn",
]


def _pallars_index(munis=_PALLARS_MUNIS) -> ESPolygonIndex:
    idx = ESPolygonIndex(Path("/nonexistent.gpkg"), Path("/nonexistent.zip"))
    for i, (ine, name) in enumerate(munis):
        idx._add_municipio(box(i * 2, 0, i * 2 + 1, 1), ine, name)
    return idx


def test_former_municipios_bind_to_the_municipio_that_absorbed_them():
    idx = _pallars_index()
    geom, stats = idx.union_communes(_PALLARS_LIST)
    assert stats == {"matched": 13, "unmatched": 0, "ambiguous_resolved": 0, "merged": 10}
    assert idx.n_merged_resolved == 10
    assert _ines(idx, _PALLARS_LIST) == {"25234", "25215", "25161", "25904", "25098", "25115"}


def test_merger_is_a_last_resort_inside_the_expected_provinces():
    idx = _pallars_index()
    # A Sevilla list has no business binding a Pallars village.
    geom, stats = idx.union_communes(["Utrera", "Palau de Noguera"])
    assert stats["merged"] == 0 and stats["unmatched"] == 1
    assert _ines(idx, ["Utrera", "Palau de Noguera"]) == {"41095"}
    # An exact name is never overridden by the table.
    assert _ines(idx, ["Tremp"]) == {"25234"}


def test_stale_merger_pin_is_refused_and_reported(capsys):
    # The pinned INE now carries another name: the pin is stale, not a bind.
    idx = _pallars_index([("25234", "Ponts"), ("25215", "Talarn")])
    assert _ines(idx, ["Talarn", "Palau de Noguera"]) == {"25215"}
    assert "[STALE] municipio_mergers.json" in capsys.readouterr().err


def test_merger_table_is_sourced_and_points_at_current_gisco_municipios():
    doc = json.loads(geometry._MUNICIPIO_MERGERS_PATH.read_text(encoding="utf-8"))
    mergers = doc["mergers"]
    for former, e in mergers.items():
        assert e["source_url"].startswith("https://"), former
        assert e["quote"].strip() and e["current"] and re.fullmatch(r"\d{5}", e["ine"]), former
        assert e["current"].casefold() != former.casefold(), former
    lau = Path(__file__).resolve().parents[1] / "raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip"
    if not lau.exists():
        pytest.skip("GISCO LAU zip not fetched")
    import geopandas as gpd

    gdf = gpd.read_file(lau, where="CNTR_CODE='ES'")
    by_id = dict(zip(gdf["GISCO_ID"], gdf["LAU_NAME"]))
    for former, e in mergers.items():
        assert _normalise_commune_name(by_id[f"ES_{e['ine']}"]) == _normalise_commune_name(
            e["current"]
        ), former


# --------------------------------------------------------------------------
# 2026-09-25 — the latent gaps of the 2026-09-24 review, now guarded
# --------------------------------------------------------------------------


def test_bare_article_piece_is_never_fused_into_a_compound():
    from _lib.es.commune_list import merge_compound_municipios

    # Les (Val d'Aran) is the one municipio whose whole name is an article;
    # the normaliser strips a trailing article the way GISCO writes "Borges
    # del Camp, Les", so "Vielha e Mijaran, Les" used to fold to the compound.
    assert merge_compound_municipios(
        ["Vielha", "Mijaran", "Les", "Bossòst"], ["", " e ", ", ", " y "],
    ) == ["Vielha e Mijaran", "Les", "Bossòst"]
    assert merge_compound_municipios(
        ["Vielha e Mijaran", "Les", "Bossòst"], ["", ", ", " y "],
    ) == ["Vielha e Mijaran", "Les", "Bossòst"]
    # A compound whose piece carries an article inside a real name still fuses.
    assert merge_compound_municipios(["Gimenells", "el Pla de la Font"], ["", " i "]) == [
        "Gimenells i el Pla de la Font",
    ]


def test_castilian_plural_articles_open_a_commune_name():
    for tok in ("los Villares", "las Pedrosas", "los Corrales"):
        assert _is_commune_token(tok), tok
    for tok in ("los agregados de Cellers", "las pedanías de Tremp", "los", "las"):
        assert not _is_commune_token(tok), tok


_CINCO_VILLAS_MUNIS = [
    ("22001", "Agüero"), ("22039", "Ayerbe"), ("22149", "Loarre"), ("22156", "Loscorrales"),
    ("50095", "Ejea de los Caballeros"), ("50252", "Tauste"), ("50297", "Zuera"),
    ("41037", "Corrales, Los"),
]


def test_exact_hit_outside_every_established_province_is_reread_with_its_spaces_closed():
    # Ribera del Gállego-Cinco Villas writes "Los Corrales" (Huesca); GISCO
    # spells it "Loscorrales", and the article-stripped key "corrales" was an
    # exact hit on Sevilla's "Corrales, Los", 636 km away.
    idx = ESPolygonIndex(Path("/nonexistent.gpkg"), Path("/nonexistent.zip"))
    for i, (ine, name) in enumerate(_CINCO_VILLAS_MUNIS):
        idx._add_municipio(box(i * 2, 0, i * 2 + 1, 1), ine, name)
    got = _ines(idx, ["Agüero", "Ayerbe", "Loarre", "Los Corrales", "Ejea de los Caballeros",
                      "Tauste", "Zuera"])
    assert "22156" in got and "41037" not in got
    # With no other province established the exact hit stands (a Sevilla list).
    got = _ines(idx, ["Los Corrales"])
    assert got == {"41037"}


_TORIL_MUNIS = [
    ("10190", "Toril"), ("10037", "Cáceres"), ("10148", "Plasencia"),
    ("02047", "Masegoso"), ("02003", "Albacete"), ("02037", "Hellín"),
    ("44231", "Toril y Masegoso"), ("44216", "Teruel"), ("44013", "Alcañiz"),
]


def test_compound_of_two_established_provinces_is_split_into_its_pieces():
    # "Toril y Masegoso" is one Teruel municipio; "Toril" (Cáceres) and
    # "Masegoso" (Albacete) side by side in a list of those provinces are two,
    # and the compound merge upstream cannot know the provinces.
    idx = ESPolygonIndex(Path("/nonexistent.gpkg"), Path("/nonexistent.zip"))
    for i, (ine, name) in enumerate(_TORIL_MUNIS):
        idx._add_municipio(box(i * 2, 0, i * 2 + 1, 1), ine, name)
    got = _ines(idx, ["Cáceres", "Plasencia", "Toril y Masegoso", "Albacete", "Hellín"])
    assert got == {"10037", "10148", "10190", "02003", "02037", "02047"}
    # In a Teruel list the compound is the Teruel municipio.
    got = _ines(idx, ["Teruel", "Alcañiz", "Toril y Masegoso"])
    assert got == {"44216", "44013", "44231"}
