"""A sottozona's own rules from its MASAF annex (masaf.annex_* + stage 04).

Excerpts follow the consolidated disciplinari of Friuli Colli Orientali,
Trentino, Barbera d'Asti, Riviera del Garda Classico and Riviera Ligure di
Ponente as MASAF publishes them.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.augment.it import _sottozona_annex  # noqa: E402
from _lib.grape_entity import match_variety  # noqa: E402
from _lib.it.documento_unico import scan_styles  # noqa: E402
from _lib.it.masaf import annex_grapes, annex_sottozona_names  # noqa: E402

_spec = importlib.util.spec_from_file_location("it_02f", ROOT / "scripts/it/02f_extract_masaf.py")
it_02f = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(it_02f)


def slugs(grapes: dict | None) -> list[str]:
    return [d["slug"] for d in (grapes or {}).get("details", [])]


def test_names_follow_the_last_sottozona_word():
    assert annex_sottozona_names(
        "ALLEGATO 2 “ABRUZZO” SOTTOZONA “TERRE AQUILANE” O “TERRE DE L’AQUILA”"
    ) == ["TERRE AQUILANE", "TERRE DE L’AQUILA"]
    assert annex_sottozona_names(
        "ALLEGATO 1 SOTTOZONE “MONTEBALDO”, “LA ROCCA”, “SOMMACAMPAGNA”"
    ) == ["MONTEBALDO", "LA ROCCA", "SOMMACAMPAGNA"]
    assert annex_sottozona_names("ALLEGATO A “Terre di Cosenza” sottozona Colline del Crati") == [
        "Colline del Crati"
    ]
    # the previous annex's labelling rule sits above the heading
    assert annex_sottozona_names(
        "sottozona “Tinella” è consentito esclusivamente l’uso del tappo di sughero. "
        "SOTTOZONA \"COLLI ASTIANI” o “ASTIANO”"
    ) == ["COLLI ASTIANI", "ASTIANO"]
    assert annex_sottozona_names("TITOLO II “TRENTINO SUPERIORE”") == []


def test_single_variety_annexes():
    pignolo = (
        "1. La denominazione di origine controllata «Friuli» Colli Orientali accompagnata dalla "
        "qualificazione\n«Pignolo di Rosazzo» e' riservata ai vini ottenuti da uve del vitigno "
        "Pignolo prodotte nella zona\nindicata all'art. 3 del presente allegato;\n"
    )
    assert slugs(annex_grapes(match_variety, pignolo, "", "Friuli Colli Orientali",
                              ["PIGNOLO DI ROSAZZO"])) == ["pignolo"]
    isera = (
        "Base ampelografica\n\nLa denominazione di origine controllata “Trentino“ Marzemino "
        "accompagnata dalla menzione\n“Superiore” e con la specificazione della sottozona "
        "“Isera” o “d’Isera”, è riservata al vino ottenuto\ndall’uva Marzemino gentile prodotta "
        "in vigneti ubicati nella zona delimitata nel successivo articolo 3.\n"
    )
    assert slugs(annex_grapes(match_variety, isera, "", "Trentino", ["ISERA", "D’ISERA"])) == [
        "marzemino"
    ]


def test_the_sottozona_name_is_not_a_grape():
    tinella = (
        "Base ampelografica\n\nIl vino a D.O.C.G. “Barbera d'Asti” superiore “Tinella” deve essere "
        "ottenuto dal vitigno Barbera\nnella misura minima dell'90%, altri vitigni a bacca nera "
        "non aromatici, idonei alla coltivazione nella\nregione Piemonte: massimo 10%.\n"
    )
    assert slugs(annex_grapes(match_variety, tinella, "", "Barbera d'Asti", ["TINELLA"])) == [
        "barbera"
    ]


def test_a_minimum_share_closes_the_name():
    valtenesi = (
        "Base ampelografica\n        1. I vini con la specificazione « Valtènesi » nelle tipologie "
        "rosso e chiaretto devono essere\nottenuti dalle uve provenienti in ambito aziendale dai "
        "vigneti aventi la seguente composizione\nvarietale: Groppello (nei biotipi Gentile e "
        "Mocasina, S. Stefano) per un minimo del 30%. Possono\nconcorrere alla produzione di detto "
        "vino anche le uve provenienti dai vitigni Marzemino, Barbera,\nSangiovese da soli o "
        "congiuntamente, fino ad un massimo del 70%.\n"
    )
    got = slugs(annex_grapes(match_variety, valtenesi, "", "Riviera del Garda Classico",
                             ["VALTENESI"]))
    assert got[0] == "groppello"
    assert {"marzemino", "barbera", "sangiovese"} <= set(got)


def test_an_annex_without_a_variety_article_keeps_the_parent_roster():
    zone = (
        "Zona di produzione\n\nLa zona di produzione delle uve destinate alla produzione dei vini "
        "a Denominazione di Origine\nControllata “Riviera Ligure di Ponente” - “Riviera dei Fiori” "
        "comprende l’intero territorio\namministrativo della Provincia di Imperia.\n"
    )
    assert annex_grapes(match_variety, zone, "", "Riviera ligure di Ponente",
                        ["RIVIERA DEI FIORI"]) is None


def test_chiaretto_is_rose():
    assert "rose" in scan_styles("« Valtènesi » rosso anche Riserva; « Valtènesi» Chiaretto.")


def test_styles_come_from_the_organoleptic_article_found_by_its_opening():
    annex = {
        "title": "ALLEGATO SOTTOZONA PIGNOLO DI ROSAZZO",
        "articles": {
            1: "1. La denominazione … «Pignolo di Rosazzo» … immesso al consumo.",
            2: "1. … riservata ai vini ottenuti da uve del vitigno Pignolo prodotte nella zona",
            6: (
                "I vini «Friuli» Colli Orientali «Pignolo di Rosazzo» all'atto dell'immissione al "
                "consumo, devono\nrispondere alle seguenti caratteristiche:\n\ncolore: rosso "
                "rubino o granato se invecchiato;\nsapore: asciutto, elegante;\n"
            ),
        },
    }
    entry = it_02f._annex_entry({"slug": "friuli-colli-orientali",
                                 "name": "Friuli Colli Orientali"}, annex, "")
    assert slugs(entry["grapes"]) == ["pignolo"]
    assert entry["styles"] == ["dry", "noir"]
    annex["articles"].pop(6)
    assert "styles" not in it_02f._annex_entry({"slug": "x", "name": "Friuli Colli Orientali"},
                                               annex, "")


def test_stage04_binds_a_sottozona_to_its_annex_by_any_alias():
    annexes = [
        {"title": "SOTTOZONA “TINELLA”", "sottozone": ["TINELLA"], "grapes": {"details": []}},
        {"title": "… SOTTOZONA \"COLLI ASTIANI” o “ASTIANO”", "sottozone": ["COLLI ASTIANI", "ASTIANO"],
         "grapes": {"details": []}},
    ]
    assert _sottozona_annex("Colli Astiani” o “Astiano", annexes) is annexes[1]
    assert _sottozona_annex("Tinella", annexes) is annexes[0]
    assert _sottozona_annex("Nizza", annexes) is None
    valt = [{"title": "Allegato 1 SOTTOZONA «VALTENESI»", "sottozone": ["VALTENESI"],
             "grapes": {"details": []}}]
    assert _sottozona_annex("Valtènesi", valt) is valt[0]
