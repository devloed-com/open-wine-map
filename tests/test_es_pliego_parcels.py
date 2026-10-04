"""Behaviour tests for the ES SIGPAC polígono-inclusion chain
(`scripts/_lib/es/pliego_parcels.py`, `scripts/_lib/es/sigpac.py`, the
whole-commune prefix of `scripts/_lib/es/commune_list.py`).

Pinned with the pliegos' own delimitation sentences: Sierra Sur de Jaén
("polígonos catastrales actuales del 1 al 12 y del 18 al 29, inclusive
estos" in brackets after the municipio), Rueda (bracketed comma list),
Campo de Borja (the municipio named AFTER its list), and the Priorat /
Montsant forms the resolver already served — those sets must not move.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.content_block import RenderCtx, render_content_block  # noqa: E402
from _lib.es.commune_list import parse_whole_commune_prefix  # noqa: E402
from _lib.es.pliego_parcels import _parse_number_list, parse_polygon_inclusions  # noqa: E402
from _lib.es.sigpac import (  # noqa: E402
    SIGPAC_INCLUSION_SEMANTICS,
    SIGPAC_SOURCES,
    SigpacIndex,
    _fega_frame_as_catalan,
    inclusion_semantics,
)
from _lib.geom_chain import ES_SIGPAC_PROVENANCE, _resolve_es_sigpac  # noqa: E402
from _lib.map_template import build_labels  # noqa: E402

SIERRA_SUR = (
    "La zona delimitada de la IGP la los términos municipales de Alcalá la Real ,Castillo de\n"
    "Locubín, Frailes, Fuensanta de Martos, Los Villares y Valdepeñas de Jaén, así como las\n"
    "zonas de sierra pertenecientes a los términos municipales de Alcaudete (polígonos\n"
    "catastrales actuales del 1 al 12 y del 18 al 29, inclusive estos) y Martos (polígonos\n"
    "catastrales actuales del 33 al 42, ambos incluidos).\n\n"
    "Únicamente podrá utilizarse la mención Vino de la Tierra de la “Sierra Sur de Jaén” en\n"
    "los vinos obtenidos íntegramente de uvas producidas dentro del territorio delimitado."
)

RUEDA_FRAGMENT = (
    "Provincia de Ávila: Blasconuño de Matacabras, Madrigal de las Altas Torres, Órbita "
    "(polígonos catastrales 1, 2, 4 y\xa05) y Palacios de Goda (polígonos catastrales 14, 17, "
    "18, 19 y\xa020). Provincia de Segovia: Aldeanueva del Codonal, Aldehuela del Codonal"
)

CAMPO_DE_BORJA_FRAGMENT = (
    "Pozuelo de Aragón, Tabuenca, y Vera de Moncayo, así como en los polígonos catastrales "
    "número 4, 5, 6, 7, 8, 9, 10 y\xa011 del término municipal de Mallén, y en los polígonos "
    "catastrales número 1, 2, 3, 4, 5, 6, 7,8, 9, 10, 11, 12, 13, 14 y\xa019 del término "
    "municipal de Fréscano."
)

PRIORAT_FRAGMENT = (
    "La Vilella Alta, La Vilella Baixa, la parte norte del municipio de Falset comprendida "
    "por los polígonos números 1, 4, 5, 6, 7, 21 y 25 enteros; y por las parcelas 38, 39, 40 "
    "del polígono n o . 2; por las parcelas 1, 2, 3 del polígono 3 y la parte este del "
    "municipio del Molar comprendida por los polígonos n o . 5, 6 y 7 enteros"
)

MONTSANT_FRAGMENT = (
    "Y, en parte, los términos municipales siguientes:\nFalset:\n"
    "Los polígonos números 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 23, 26, 27, 28, 29, 30 y 31;\n"
    "Polígono 2 parcelas de la 1 a la 37, de la 41 a la 70.\n"
    "El Molar:\nPolígonos 1, 2, 3, del 11 al 16.\n"
    "Polígono 4 parcelas de la 1 a la 7, parte oeste de la parcela 8 (0,5515 ha).\n"
)


def _by_muni(text: str) -> dict[str, set[int]]:
    return {i.municipio_norm: set(i.polygon_numbers) for i in parse_polygon_inclusions(text)}


# --------------------------------------------------------------------------
# pliego_parcels.py — number lists
# --------------------------------------------------------------------------

def test_closed_ranges_with_trailing_qualifier():
    assert _parse_number_list("del 33 al 42") == set(range(33, 43))
    assert _parse_number_list("del 1 al 12 y del 18 al 29") == set(range(1, 13)) | set(range(18, 30))
    assert _parse_number_list("1, 2, 4 y\xa05") == {1, 2, 4, 5}


# --------------------------------------------------------------------------
# pliego_parcels.py — anchors
# --------------------------------------------------------------------------

def test_sierra_sur_bracketed_catastrales_actuales_ranges():
    got = _by_muni(SIERRA_SUR)
    assert got == {
        "alcaudete": set(range(1, 13)) | set(range(18, 30)),
        "martos": set(range(33, 43)),
    }
    # The bracket anchor keeps the municipio's own name, not the accented
    # tail of "términos municipales de …" nor the preceding list item.
    assert {i.municipio for i in parse_polygon_inclusions(SIERRA_SUR)} == {"Alcaudete", "Martos"}


def test_rueda_bracketed_comma_lists():
    assert _by_muni(RUEDA_FRAGMENT) == {
        "orbita": {1, 2, 4, 5},
        "palacios de goda": {14, 17, 18, 19, 20},
    }


def test_campo_de_borja_list_binds_to_the_municipio_named_after_it():
    assert _by_muni(CAMPO_DE_BORJA_FRAGMENT) == {
        "mallen": {4, 5, 6, 7, 8, 9, 10, 11},
        "frescano": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 19},
    }


def test_priorat_and_montsant_forms_unchanged():
    assert _by_muni(PRIORAT_FRAGMENT) == {"falset": {1, 4, 5, 6, 7, 21, 25}, "molar": {5, 6, 7}}
    assert _by_muni(MONTSANT_FRAGMENT) == {
        "falset": {8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 23, 26, 27, 28, 29, 30, 31},
        "molar": {1, 2, 3, 11, 12, 13, 14, 15, 16},
    }


def test_singular_polígono_parcela_references_do_not_fire():
    assert parse_polygon_inclusions(
        "Del municipio de Cabra del Camp el polígono\xa01, parcelas 13, 15, 18, 28 y\xa077."
    ) == []


# --------------------------------------------------------------------------
# commune_list.py — whole-commune prefix in front of the partial tail
# --------------------------------------------------------------------------

def test_whole_commune_prefix_stops_at_asi_como_and_joins_wrapped_names():
    assert parse_whole_commune_prefix(SIERRA_SUR) == [
        "Alcalá la Real", "Castillo de Locubín", "Frailes",
        "Fuensanta de Martos", "Los Villares", "Valdepeñas de Jaén",
    ]


def test_whole_commune_prefix_priorat_unchanged():
    text = (
        "Bellmunt del Priorat, Gratallops, El Lloar, La Morera de Montsant y su agregado "
        "Escaladei, Poboleda, Porrera, Torroja del Priorat, La Vilella Alta, La Vilella "
        "Baixa, " + PRIORAT_FRAGMENT
    )
    assert parse_whole_commune_prefix(text) == [
        "Bellmunt del Priorat", "Gratallops", "El Lloar", "La Morera de Montsant",
        "Poboleda", "Porrera", "Torroja del Priorat", "La Vilella Alta", "La Vilella Baixa",
    ]


# --------------------------------------------------------------------------
# sigpac.py — one loader for the Catalan and the FEGA schema
# --------------------------------------------------------------------------

def _catalan_gpkg(path: Path) -> Path:
    gdf = gpd.GeoDataFrame(
        {
            "ID_MUN": ["43054", "43054", "43054", "43090"],
            "MUNICIPI": ["Falset", "Falset", "Falset", "el Molar"],
            "ID_COM": ["29"] * 4,
            "POL": [1, 1, 2, 5],
            "US": ["VI", "OV", "VI", "VI"],
        },
        geometry=[box(0.80, 41.14, 0.81, 41.15), box(0.81, 41.14, 0.82, 41.15),
                  box(0.82, 41.14, 0.83, 41.15), box(0.72, 41.16, 0.73, 41.17)],
        crs="EPSG:4326",
    )
    gdf.to_file(path, layer="SIGPAC_29_Priorat", driver="GPKG")
    return path


def _fega_gpkg(path: Path) -> Path:
    gdf = gpd.GeoDataFrame(
        {
            "provincia": [23, 23, 23, 23, 23, 23],
            "municipio": [60, 60, 60, 3, 5, 5],
            "poligono": [36, 36, 40, 5, 7, 8],
            "parcela": [1, 2, 1, 1, 1, 1],
            "recinto": [1, 1, 1, 1, 1, 1],
            "uso_sigpac": ["VI", "OV", "VI", "VI", "OV", "PR"],
            "municipio_nombre": ["Martos", "Martos", "Martos", "Alcaudete", "Andújar", "Andújar"],
        },
        geometry=[box(-3.98, 37.70, -3.97, 37.71), box(-3.97, 37.70, -3.96, 37.71),
                  box(-3.96, 37.70, -3.95, 37.71), box(-4.10, 37.58, -4.09, 37.59),
                  box(-4.05, 38.02, -4.04, 38.03), box(-4.04, 38.02, -4.03, 38.03)],
        crs="EPSG:4258",
    )
    gdf.to_file(path, layer="recinto", driver="GPKG")
    return path


def test_sigpac_index_reads_both_schemas(tmp_path):
    idx = SigpacIndex([_catalan_gpkg(tmp_path / "SIGPAC_29_Priorat.gpkg"),
                       _fega_gpkg(tmp_path / "SIGPAC_FEGA_23_JAEN.gpkg")])
    assert idx.n_comarques == 2
    assert idx.n_municipios == 4
    # Catalan path: name (article-stripped) and INE both resolve; OV excluded.
    falset = idx.polygons_in_municipi("Falset", [1, 2])
    assert falset is not None and abs(falset.area - 2 * 0.0001) < 1e-9
    assert idx.polygons_in_municipi("43090", [5]).equals(idx.polygons_in_municipi("El Molar", [5]))
    # FEGA path: INE = provincia*1000 + municipio, name from municipio_nombre.
    martos = idx.polygons_in_municipi("martos", [36, 40, 41])
    assert martos is not None and abs(martos.area - 2 * 0.0001) < 1e-9
    assert idx.polygons_in_municipi("23060", [36]).equals(idx.polygons_in_municipi("Martos", [36]))
    assert idx.polygons_in_municipi("Alcaudete", [1, 2, 3]) is None  # no VI in those polígonos
    assert idx.municipi_vineyards("Alcaudete").bounds == (-4.10, 37.58, -4.09, 37.59)
    # A municipio in neither file stays unresolved.
    assert idx.polygons_in_municipi("Garcia", [7]) is None


def _avila_fega_frame() -> gpd.GeoDataFrame:
    # Province 05 (Ávila): Rueda's Órbita, INE 05176.
    return gpd.GeoDataFrame(
        {
            "provincia": [5, 5], "municipio": [176, 176], "poligono": [1, 2],
            "parcela": [1, 1], "recinto": [1, 1], "uso_sigpac": ["VI", "TA"],
        },
        geometry=[box(-4.80, 41.00, -4.79, 41.01), box(-4.79, 41.00, -4.78, 41.01)],
        crs="EPSG:4258",
    )


def test_fega_ine_keeps_the_leading_zero_of_provinces_01_to_09(tmp_path):
    assert list(_fega_frame_as_catalan(_avila_fega_frame())["ID_MUN"]) == ["05176", "05176"]
    path = tmp_path / "SIGPAC_FEGA_05_AVILA.gpkg"
    _avila_fega_frame().assign(municipio_nombre="Órbita").to_file(
        path, layer="recinto", driver="GPKG",
    )
    idx = SigpacIndex([path])
    assert idx.polygons_in_municipi("05176", [1]) is not None
    assert idx.polygons_in_municipi("Órbita", [1]) is not None
    assert idx.polygon_footprints_in_municipi("05176", [1, 2])[1] == {1, 2}


def _load_stage00():
    path = Path(__file__).resolve().parents[1] / "scripts" / "es" / "00_fetch_data.py"
    spec = importlib.util.spec_from_file_location("es_00_fetch_data", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_stage00_fega_extract_names_a_province_05_municipio(tmp_path, monkeypatch, capsys):
    stage00 = _load_stage00()
    monkeypatch.setattr(stage00, "ROOT", tmp_path)
    monkeypatch.setattr(stage00, "SIGPAC_OUT_DIR", tmp_path)
    full = tmp_path / "05_AVILA.gpkg"
    _avila_fega_frame().to_file(full, layer="recinto", driver="GPKG")
    zip_path = tmp_path / "05_AVILA.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(full, "05_AVILA.gpkg")
    extract = tmp_path / "SIGPAC_FEGA_05_AVILA.gpkg"
    stage00._write_sigpac_fega_extract(
        pr="05", zip_path=zip_path, entry={"inner_gpkg": "05_AVILA.gpkg", "layer": "recinto"},
        municipios={"05176": "Órbita"}, extract_path=extract, zipfile_mod=zipfile,
    )
    assert list(gpd.read_file(extract)["municipio_nombre"]) == ["Órbita", "Órbita"]
    assert "WARNING" not in capsys.readouterr().err


def test_stage00_catalan_fetch_keeps_the_fega_cache_state(tmp_path, monkeypatch):
    # fetch_sigpac_comarques runs first in main(); rewriting the shared
    # manifest whole dropped `fega_provincias`, so the FEGA extract cache
    # never hit and every run re-extracted the 0.9 GB Jaén file.
    stage00 = _load_stage00()
    manifest = tmp_path / "manifest.json"
    for name, value in (("ROOT", tmp_path), ("SIGPAC_OUT_DIR", tmp_path),
                        ("SIGPAC_MANIFEST_PATH", manifest), ("SIGPAC_COMARCA_CODIS", ("29",)),
                        ("SIGPAC_FEGA_PROVINCIAS", ("23",))):
        monkeypatch.setattr(stage00, name, value)
    urls = tmp_path / "catalonia.json"
    urls.write_text(json.dumps({"29": {
        "url_2025_gpkg": "https://example.invalid/29.zip", "filename": "29.zip",
        "comarca": "Priorat",
    }}), encoding="utf-8")
    fega_urls = tmp_path / "fega.json"
    fega_urls.write_text(json.dumps({
        "_meta": {"license_url": "u", "license_quote": "q"},
        "23": {"filename": "23.zip", "url": "https://example.invalid/23.zip",
               "provincia": "Jaén", "campaign": "2026", "validity_date": "2025-12-15",
               "extract_gpkg": "SIGPAC_FEGA_23_JAEN.gpkg", "municipios": {"23060": "Martos"}},
    }), encoding="utf-8")
    monkeypatch.setattr(stage00, "SIGPAC_URLS_JSON", urls)
    monkeypatch.setattr(stage00, "SIGPAC_FEGA_URLS_JSON", fega_urls)
    with zipfile.ZipFile(tmp_path / "29.zip", "w") as zf:
        zf.writestr("SIGPAC_29_Priorat.gpkg", b"")
    (tmp_path / "SIGPAC_FEGA_23_JAEN.gpkg").write_bytes(b"")
    manifest.write_text(json.dumps({"fega_provincias": {"23": {
        "zip_sha256": "abc", "municipios": {"23060": "Martos"},
    }}}), encoding="utf-8")
    monkeypatch.setattr(stage00, "_fetch_binary_with_manifest", lambda **kw: None)
    monkeypatch.setattr(stage00, "_stream_binary_with_manifest", lambda **kw: "abc")
    extracted: list[str] = []
    monkeypatch.setattr(stage00, "_write_sigpac_fega_extract",
                        lambda **kw: extracted.append(kw["pr"]))

    stage00.fetch_sigpac_comarques()
    kept = json.loads(manifest.read_text(encoding="utf-8"))
    assert kept["fega_provincias"]["23"]["zip_sha256"] == "abc"
    assert kept["comarques"]["29"]["gpkg"] == "SIGPAC_29_Priorat.gpkg"
    stage00.fetch_sigpac_fega_provincias()
    assert extracted == []
    assert set(json.loads(manifest.read_text(encoding="utf-8"))) >= {"comarques", "fega_provincias"}


# --------------------------------------------------------------------------
# sigpac.py — the polígono footprint (any land use) next to the vineyard reading
# --------------------------------------------------------------------------

def test_footprint_takes_every_recinto_of_a_poligono_and_the_vineyard_reading_is_unchanged(tmp_path):
    idx = SigpacIndex([_catalan_gpkg(tmp_path / "SIGPAC_29_Priorat.gpkg"),
                       _fega_gpkg(tmp_path / "SIGPAC_FEGA_23_JAEN.gpkg")])
    # Catalan file: polígono 1 is a VI + an OV recinto — the footprint has
    # both, the vineyard reading only the VI one; found reports the polígonos
    # present, not those listed.
    fp, found = idx.polygon_footprints_in_municipi("Falset", [1, 2, 9])
    assert found == {1, 2} and abs(fp.area - 3 * 0.0001) < 1e-9
    assert abs(idx.polygons_in_municipi("Falset", [1, 2, 9]).area - 2 * 0.0001) < 1e-9
    assert idx.vineyard_polygons_present("Falset", [1, 2, 9]) == {1, 2}
    assert idx.polygon_footprints_in_municipi("43090", [5])[0].equals(
        idx.polygon_footprints_in_municipi("El Molar", [5])[0]
    )
    # FEGA file: a municipio without a single vineyard is absent from the
    # vineyard index and still resolves as a footprint.
    assert idx.polygons_in_municipi("Andújar", [7, 8]) is None
    assert idx.n_municipios == 4
    fp, found = idx.polygon_footprints_in_municipi("andujar", [7, 8, 9])
    assert found == {7, 8} and abs(fp.area - 2 * 0.0001) < 1e-9
    assert idx.polygon_footprints_in_municipi("23005", [7])[0].bounds == (-4.05, 38.02, -4.04, 38.03)
    assert idx.municipio_publication("Andújar") == "fega"
    assert idx.municipio_publication("Falset") == "catalunya"
    # Nothing listed, nothing loaded, nothing there: no geometry.
    assert idx.polygon_footprints_in_municipi("Falset", []) == (None, set())
    assert idx.polygon_footprints_in_municipi("Garcia", [7]) == (None, set())
    assert idx.polygon_footprints_in_municipi("Martos", [1]) == (None, set())


def test_inclusion_semantics_default_footprint_and_nothing_pinned():
    """Every record reads its polígonos as footprints — Priorat and Montsant
    included since 2026-09-24. The table stays so a future pin needs a
    reason the pliego's wording supports; today it must be empty."""
    for slug in ("sierra-sur-de-jaen", "priorat", "montsant", "a-new-record"):
        assert inclusion_semantics(slug) == "footprint"
    assert SIGPAC_INCLUSION_SEMANTICS == {}
    for src in SIGPAC_SOURCES.values():
        assert src["attribution"] and src["url"]
    assert SIGPAC_SOURCES["fega"]["licence"] == "CC BY 4.0"


class _NoCommunes:
    def union_communes(self, names):
        return None, {"matched": 0, "unmatched": len(list(names))}


def test_resolver_reads_the_pin_and_records_the_provenance(tmp_path, monkeypatch):
    idx = SigpacIndex([_catalan_gpkg(tmp_path / "SIGPAC_29_Priorat.gpkg"),
                       _fega_gpkg(tmp_path / "SIGPAC_FEGA_23_JAEN.gpkg")])
    ES_SIGPAC_PROVENANCE.clear()
    # Default reading: Martos's polígonos 33–42 taken whole (VI + OV) plus
    # Alcaudete's polígono 5; the listed count is kept beside the count found.
    rec = {"slug": "sierra-sur-de-jaen", "geo_area_brief": SIERRA_SUR}
    g = _resolve_es_sigpac(rec, idx, _NoCommunes())
    assert abs(g.area - 4 * 0.0001) < 1e-9
    prov = ES_SIGPAC_PROVENANCE["sierra-sur-de-jaen"]
    assert prov["semantics"] == "footprint"
    assert prov["municipios"] == [
        {"name": "Alcaudete", "listed": 24, "found": 1},
        {"name": "Martos", "listed": 10, "found": 2},
    ]
    assert prov["whole"] == parse_whole_commune_prefix(SIERRA_SUR) and prov["whole_matched"] == 0
    assert prov["sources"] == [SIGPAC_SOURCES["fega"]]
    # Unpinned, Priorat reads its polígonos as footprints like every record
    # (decision 2026-09-24): every recinto of the listed polígonos, the
    # non-vineyard one included — three in this fixture against the two
    # vineyard parcels the pinned reading below keeps.
    rec = {"slug": "priorat", "geo_area_brief": PRIORAT_FRAGMENT}
    g = _resolve_es_sigpac(rec, idx, _NoCommunes())
    assert abs(g.area - 3 * 0.0001) < 1e-9
    assert ES_SIGPAC_PROVENANCE["priorat"]["semantics"] == "footprint"
    # A pin to the vineyard reading still works: Falset's polígonos 1, 4, …
    # as vineyard parcels only.
    monkeypatch.setitem(SIGPAC_INCLUSION_SEMANTICS, "priorat", "vineyard")
    g = _resolve_es_sigpac(rec, idx, _NoCommunes())
    assert abs(g.area - 2 * 0.0001) < 1e-9
    prov = ES_SIGPAC_PROVENANCE["priorat"]
    assert prov["semantics"] == "vineyard"
    assert prov["municipios"] == [
        {"name": "Falset", "listed": 7, "found": 1},
        {"name": "Molar", "listed": 3, "found": 1},
    ]
    assert prov["sources"] == [SIGPAC_SOURCES["catalunya"]]
    # No polígono resolves → no geometry, and no provenance claimed.
    ES_SIGPAC_PROVENANCE.clear()
    rec = {"slug": "elsewhere", "geo_area_brief": RUEDA_FRAGMENT}
    assert _resolve_es_sigpac(rec, idx, _NoCommunes()) is None
    assert "elsewhere" not in ES_SIGPAC_PROVENANCE


# --------------------------------------------------------------------------
# panel — the SSR card says which reading drew the polígonos
# --------------------------------------------------------------------------

def _ctx() -> RenderCtx:
    return RenderCtx(
        locale="fr", labels=build_labels(lambda s: s), region_labels={},
        country_labels={"es": "Espagne"}, country_flag_emoji={"es": "🇪🇸"},
        grapes_info={}, styles_info={}, style_labels={},
        github_new_issue_url="https://github.com/x/y/issues/new",
    )


def test_ssr_card_discloses_the_sigpac_reading_with_the_publisher_and_licence():
    sources = {
        "country": "es",
        "sigpac_semantics": "footprint",
        "sigpac_municipios": [{"name": "Alcaudete", "listed": 24, "found": 24},
                              {"name": "Martos", "listed": 10, "found": 9}],
        "sigpac_whole": ["Alcalá la Real", "Frailes"],
        "sigpac_sources": [SIGPAC_SOURCES["fega"]],
    }
    rec = {"name": "Sierra Sur de Jaén", "kind": "IGP", "country": "es", "region": "Andalucía",
           "geom_source": "sigpac-hybrid-pliego", "communes_matched": -1, "sources": sources}
    out = render_content_block(rec, "sierra-sur-de-jaen", _ctx())
    assert "les 34 polígonos cadastraux SIGPAC" in out
    assert "dans Alcaudete (24), Martos (9/10), chacun dessiné en entier" in out
    assert "© FEGA / MAPA, SIGPAC · CC BY 4.0</a>" in out
    assert 'href="https://creativecommons.org/licenses/by/4.0/deed.es"' in out
    assert "les communes Alcalá la Real, Frailes." in out
    # The vineyard reading names the land use, and a source without a
    # recorded licence is linked to its portal with the attribution alone.
    sources.update({"sigpac_semantics": "vineyard", "sigpac_sources": [SIGPAC_SOURCES["catalunya"]],
                    "sigpac_whole": []})
    out = render_content_block(rec, "sierra-sur-de-jaen", _ctx())
    assert "parcelles de vigne (SIGPAC, usage VI) situées dans les 34 polígonos" in out
    assert 'href="https://analisi.transparenciacatalunya.cat/"' in out
    assert "© Generalitat de Catalunya / DARP, SIGPAC</a>" in out
    assert "S'y ajoutent" not in out and "S&#x27;y ajoutent" not in out
    # Another geometry source with the same sources block says nothing.
    rec["geom_source"] = "mapa-zone"
    assert "SIGPAC" not in render_content_block(rec, "sierra-sur-de-jaen", _ctx())
