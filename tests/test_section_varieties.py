"""§4 / §5 varieties outside the §7 roster (scripts/_lib/section_varieties.py).

Piemonte's §4 names Sauvignon as a varietal type, Eger's §5 names Turán and
Cabernet dorsa in production rules, Prosecco's §5 allows Chardonnay and the
Pinots up to 15 % — none in §7. A bare family word (Lambrusco, Albillo,
Moscato) never binds, nor a roster member again, nor the appellation's name.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.section_varieties import (  # noqa: E402
    FAMILY_WORDS,
    add_section_varieties,
    section_varieties,
)

PIEMONTE = {
    "description": "Categoria Vino (1) -Bianchi: Piemonte bianco, con specificazione di vitigno "
                   "Cortese, Chardonnay, Sauvignon, con due vitigni. Sono vini dal colore giallo "
                   "paglierino, più delicato nel caso del Cortese.",
}
EGER = {
    "viticultural_practices": "a bort legalább 6 hónapig fahordóban kell érlelni, kivéve: Blauburger, "
                              "Kadarka, Kékoportó, Turán fajták borait; 10,60 %vol (17 °MM): Alibernet, "
                              "Cabernet dorsa, Cabernet franc, Kékfrankos.",
}
PROSECCO = {
    "viticultural_practices": "è consentita l’aggiunta di prodotti ottenuti dalla vinificazione di uve "
                              "Chardonnay, Pinot bianco, Pinot grigio e Pinot nero (vinificato in bianco), "
                              "in quantità non superiore al 15 %",
}


def _slugs(roles, have, name=""):
    return [d["slug"] for d in section_varieties(roles, set(have), name)]


def test_piemonte_sauvignon_is_a_type_the_roster_lacks():
    found = section_varieties(PIEMONTE, {"cortese", "chardonnay"}, "Piemonte")
    assert [d["slug"] for d in found] == ["sauvignon"]
    assert found[0]["role"] == "accessory"
    assert found[0]["source"] == "section-4-type"
    assert found[0]["name"] == "Sauvignon"


def test_eger_rules_name_turan_and_cabernet_dorsa():
    have = {"blauburger", "kadarka", "blauer-portugieser", "alibernet", "cabernet-franc", "blaufrankisch"}
    found = section_varieties(EGER, have, "Eger")
    assert {d["slug"] for d in found} == {"turan", "cabernet-dorsa"}
    assert {d["source"] for d in found} == {"section-5-rule"}
    assert {d["name"] for d in found} == {"Turán", "Cabernet dorsa"}


def test_prosecco_blending_varieties():
    assert set(_slugs(PROSECCO, {"glera"}, "Prosecco")) == {"chardonnay", "pinot-blanc", "pinot-gris", "pinot-noir"}


def test_bare_family_words_never_bind():
    roles = {"description": "Vini ottenuti da uve Lambrusco; aromi di Moscato; uva Albillo."}
    assert _slugs(roles, set()) == []
    assert {"lambrusco", "moscato", "albillo"} <= FAMILY_WORDS
    # The family words the lexicon folds onto one member (Canaiolo → canaiolo
    # nero, Malvasia nera → di Brindisi) are not read from prose either.
    roles = {"description": "Maremma Toscana Canaiolo; Val d'Arno di Sopra Malvasia nera e Refosco."}
    assert _slugs(roles, set()) == []


def test_roster_members_and_the_appellation_name_are_skipped():
    roles = {"description": "Il Barbera d'Asti è ottenuto da uve Barbera; Freisa d'Asti idem."}
    assert _slugs(roles, {"barbera"}, "Barbera d'Asti") == ["freisa"]
    assert _slugs(roles, {"barbera", "freisa"}, "Barbera d'Asti") == []


def test_add_section_varieties_appends_accessories_in_place():
    grapes = {"principal": ["cortese", "chardonnay"], "accessory": [], "details": []}
    assert add_section_varieties(grapes, PIEMONTE, "Piemonte") == ["sauvignon"]
    assert grapes["accessory"] == ["sauvignon"]
    assert grapes["details"][-1]["source"] == "section-4-type"
    assert add_section_varieties(grapes, PIEMONTE, "Piemonte") == []


def test_prose_words_and_lowercase_prose_never_bind():
    roles = {"description": "Su conducción deberá ser la óptima; envejecimiento a sol y serena; "
                            "aromas de melón; frutti di bosco; vitigni a bacca bianca; halvány rubin, "
                            "lilás árnyalatokkal; el color de la cariñena con la riqueza de la garnacha."}
    assert _slugs(roles, set()) == []


def test_a_variety_word_admits_a_lowercase_name():
    roles = {"description": "Rancio: elaborado a partir de las variedades garnacha blanca y macabeo. "
                            "El 100% de la uva blanca ha de ser de la variedad forastera."}
    assert _slugs(roles, set()) == ["grenache-blanc", "macabeu", "forastera"]


def test_a_toponym_and_a_family_word_are_skipped():
    roles = {"description": "la Subzona de El Molar entre el Sistema Central y el río; "
                            "variedades Zalema, Palomino Fino, Listán del Condado y Garrido Fino; "
                            "«Riviera del Garda Classico» Groppello; Venezia Raboso."}
    assert _slugs(roles, {"zalema", "palomino-fino", "garrido-fino"}) == []


def test_an_apostrophe_name_keeps_its_case():
    roles = {"description": "«Sicilia» Nero d'Avola: colore rosso rubino."}
    found = section_varieties(roles, set(), "Sicilia")
    assert [(d["slug"], d["name"]) for d in found] == [("nero-davola", "Nero d'Avola")]
