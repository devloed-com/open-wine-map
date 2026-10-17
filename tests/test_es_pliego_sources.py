"""Regression tests for the Spanish source chain behind a visitor flag on
Norte de Almería (2026-10-05): the stage-01 manifest had lost 147 of 149
entries to a scoped --refresh, so 183 cards linked no pliego; five pliegos'
link sections were never routed ("VINCULACIÓN …", a parent holding only a
page number, sub-sections without their parent heading); and 20 records
fell back to the region "España".
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.es.region import CCAA_OVERRIDES, derive_ccaa  # noqa: E402

fetch = importlib.import_module("es.01_fetch_pliegos")
extract = importlib.import_module("es.02_extract_pliegos")


# --- stage 01: manifest entries rebuilt from the cache -------------------


def test_url_oj_key_forms():
    assert fetch._url_oj_key("https://eur-lex.europa.eu/eli/C/2026/565/oj/spa") == (2026, 565)
    assert fetch._url_oj_key(
        "https://eur-lex.europa.eu/legal-content/ES/TXT/HTML/?uri=OJ:C_202300287") == (2023, 287)
    assert fetch._url_oj_key(
        "https://eur-lex.europa.eu/legal-content/ES/TXT/HTML/"
        "?uri=uriserv%3AOJ.C_.2020.217.01.0021.01.SPA&toc=OJ%3AC%3A2020%3A217%3ATOC"
    ) == (2020, 217, 21)
    assert fetch._url_oj_key("https://www.mapa.gob.es/x/norte_de_almeria.pdf") is None


def test_page_oj_key_forms():
    assert fetch._page_oj_key(
        '<meta about="http://data.europa.eu/eli/C/2026/565/oj" typeof="eli:LegalResource"/>'
    ) == (2026, 565)
    assert fetch._page_oj_key("<title>C_2020217ES.01002101.xml</title>") == (2020, 217, 21)
    assert fetch._page_oj_key("<title>C_202300287ES.000101.fmx.xml</title>") == (2023, 287)


def _wine(uri: str) -> dict:
    return {"slug": "x", "giIdentifier": "EUGI1",
            "publications": [{"uri": uri, "text": "Official Journal C"}]}


def test_reconstruct_pdf_takes_the_override(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    os.utime(pdf, (1778439686, 1778439686))
    url = "https://www.mapa.gob.es/x/norte_de_almeria_2014_27_06.pdf"
    entry = fetch.reconstruct_entry(_wine("http://data.europa.eu/eli/C/2026/1/oj"),
                                    {"url": url}, pdf)
    assert entry["source_url"] == entry["final_url"] == url
    assert entry["format"] == "pdf" and entry["from_override"] and entry["reconstructed"]
    assert entry["fetched_at"] == "2026-05-10T19:01:26+00:00"


def test_reconstruct_html_checks_the_publication(tmp_path):
    page = tmp_path / "x.html"
    page.write_text("<title>C_2020217ES.01002101.xml</title>", encoding="utf-8")
    same = ("https://eur-lex.europa.eu/legal-content/EN/TXT/"
            "?uri=uriserv:OJ.C_.2020.217.01.0021.01.ENG&toc=OJ:C:2020:217:TOC")
    entry = fetch.reconstruct_entry(_wine(same), None, page)
    assert entry["source_url"].startswith("https://eur-lex.europa.eu/legal-content/ES/TXT/HTML/")
    assert entry["source_url"].endswith("01.SPA&toc=OJ:C:2020:217:TOC")
    other = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=uriserv:OJ.C_.2024.101.01.0003.01.ENG"
    assert fetch.reconstruct_entry(_wine(other), None, page) is None


# --- stage 02: routing of the link section -------------------------------


def test_vinculacion_parent_with_only_a_page_number_takes_its_children():
    titles = {"F": "VARIEDADES DE UVA DE LAS QUE PROCEDEN LOS VINOS",
              "G": "VINCULACIÓN CON EL MEDIO GEOGRÁFICO",
              "G.1": "Características de la zona geográfica",
              "G.2": "Información detallada sobre la calidad",
              "H": "REQUISITOS APLICABLES"}
    sections = {"F": "Airen", "G": "-3-", "G.1": "Factores naturales: altiplanicies.",
                "G.2": "Marcada acidez.", "H": "Etiquetado."}
    routed = extract.route_sections(sections, titles)
    assert routed["link_to_terroir"] == "Factores naturales: altiplanicies.\nMarcada acidez."


def test_link_parent_with_a_body_keeps_its_children():
    titles = {"G": "VINCULACIÓN CON EL MEDIO GEOGRÁFICO",
              "G.1": "Factores humanos", "G.2": "Factores naturales"}
    sections = {"G": "La reputación de los vinos.", "G.1": "Tradición.", "G.2": "Albariza."}
    routed = extract.route_sections(sections, titles)
    assert routed["link_to_terroir"] == "La reputación de los vinos.\nTradición.\nAlbariza."


def test_link_children_without_their_parent_heading():
    titles = {"6": "Variedades de uvas de las que proceden los vinos",
              "7.1": "Información detallada de la zona geográfica (factores naturales y humanos)",
              "7.2": "Información sobre la calidad o las características del vino",
              "7.3": "Relación entre las características de la zona geográfica y la calidad",
              "9.1": "Autoridad competente"}
    sections = {"6": "Cencibel", "7.1": "Terreno.", "7.2": "Calidad.", "7.3": "Relación.",
                "9.1": "Dirección General."}
    routed = extract.route_sections(sections, titles)
    assert routed["link_to_terroir"] == "Terreno.\nCalidad.\nRelación."


def test_other_roles_do_not_take_children():
    titles = {"B": "DESCRIPCIÓN DE LOS VINOS", "B.1": "Principales características analíticas"}
    sections = {"B": "Vinos tranquilos.", "B.1": "Grado 13."}
    assert extract.route_sections(sections, titles)["description"] == "Vinos tranquilos."


# --- region -----------------------------------------------------------------


def test_ccaa_name_with_a_conjunction():
    rec = {"slug": "t", "geo_area_brief":
           "la totalidad de los municipios de la Comunidad Autónoma de Castilla y León."}
    assert derive_ccaa(rec) == "Castilla y León"


def test_bracketed_province_after_a_municipio():
    rec = {"slug": "t", "geo_area_brief":
           "los términos municipales de Anchuras (Ciudad Real) y Sevilleja de la Jara (Toledo)."}
    assert derive_ccaa(rec) == "Castilla-La Mancha"


def test_province_followed_by_a_word():
    rec = {"slug": "t", "geo_area_brief":
           "los terrenos ubicados en la provincia de Castellón comprendidos en las unidades"}
    assert derive_ccaa(rec) == "Comunidad Valenciana"


def test_area_text_decides_over_the_link_text():
    rec = {"slug": "t",
           "geo_area_brief": "el término municipal de Villabáñez (Valladolid)",
           "link_to_terroir": "villa del Partido de Portillo de la Provincia de Madrid."}
    assert derive_ccaa(rec) == "Castilla y León"


def test_link_text_when_the_area_names_no_province():
    rec = {"slug": "t",
           "geo_area_brief": "los términos municipales siguientes: Chirivel, María.",
           "link_to_terroir": "en la zona más septentrional de la provincia de Almería"}
    assert derive_ccaa(rec) == "Andalucía"


def test_municipio_only_pliegos_are_pinned():
    for slug, ccaa in {"somontano": "Aragón", "terra-alta": "Cataluña",
                       "pago-de-otazu": "Navarra", "desierto-de-almeria": "Andalucía"}.items():
        assert CCAA_OVERRIDES[slug] == ccaa
