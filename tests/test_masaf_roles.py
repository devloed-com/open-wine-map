"""MASAF Article 2 rules of 2026-10-22 (the Romagna Oriolo annex).

1. The clause names the role: a variety named after a clause's *concorrere*
   marker or its "complementari / accessori:" label is an accessory, one
   named after "principali:" or before any marker is principal; a roster
   phrased wholly as "possono concorrere" stays principal.
2. A bare family word the disciplinare writes short ("Trebbiano" for the
   "Trebbiano Romagnolo" its article 2 names) is pinned per record in
   grape_context_overrides.json — never folded by rule.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.grape_entity import match_variety, set_pliego_context  # noqa: E402
from _lib.grape_lexicon import DEFAULT_COLOUR, GRAPE_ALIAS  # noqa: E402
from _lib.it.masaf import (  # noqa: E402
    CONTEXT_OVERRIDES_PATH,
    clause_roles,
    context_pins,
    exclusion_drops,
    parse_grapes_with,
)

ORIOLO = """Base ampelografica

2.1. La denominazione di origine controllata “Romagna” Sangiovese Oriolo, anche riserva, è
riservata ai vini derivanti dalle uve prodotte dai vigneti aventi, nell’ambito aziendale, la seguente
composizione ampelografica:

Sangiovese (anche riserva):
- Sangiovese: minimo il 95%;
- possono concorrere altri vitigni a bacca nera, idonei alla coltivazione per la regione Emilia
Romagna, fino ad un massimo del 5%.

2.2. La denominazione di origine controllata “Romagna” Bianco Oriolo è riservata ai vini derivanti
dalle uve prodotte dai vigneti aventi, nell’ambito aziendale, la seguente composizione ampelografica:
- Trebbiano: minimo 70%;
- può concorrere alla produzione di detto vino il vitigno Albana fino ad un massimo del 30 % da solo
o congiuntamente ad altri vitigni a bacca bianca idonei alla coltivazione nella Regione Emilia
Romagna fino ad un massimo del 5%.

2.3. La denominazione di origine controllata “Romagna” Centesimino Oriolo, anche Riserva, Passito
e spumante rosato o rosè, è riservata ai vini derivanti dalle uve prodotte dai vigneti aventi,
nell’ambito aziendale, la seguente composizione ampelografica:
Centesimino (anche Riserva, Passito e spumante rosato o rosé):
- Centesimino: minimo il 95%;
- possono concorrere altri vitigni a bacca nera, idonei alla coltivazione per la regione Emilia-
Romagna, fino ad un massimo del 5%.
"""


def _roles(body: str, name: str = "Romagna", context: str | None = None) -> dict[str, str]:
    set_pliego_context(context)
    try:
        out = parse_grapes_with(match_variety, body, wine_name=name)
    finally:
        set_pliego_context(None)
    return {d["slug"]: d["role"] for d in out["details"]}


def test_oriolo_albana_is_the_accessory_of_the_bianco():
    roles = _roles(ORIOLO)
    assert roles["sangiovese"] == "principal"
    assert roles["centesimino"] == "principal"
    assert roles["ugni-blanc"] == "principal"            # the bare alias, without a context
    assert roles["albana"] == "accessory"
    assert "nebbiolo" not in roles                        # "spumante rosato o rosè" is a wine type


def test_oriolo_reads_its_parent_pin_for_the_bare_trebbiano():
    roles = _roles(ORIOLO, context="romagna")
    assert "ugni-blanc" not in roles
    assert roles["trebbiano-romagnolo"] == "principal"


def test_mixed_clauses_split_the_roster():
    body = ("Il vino è ottenuto dalle uve del vitigno Nebbiolo per almeno l'85%; possono concorrere "
            "alla produzione i vitigni Barbera, Freisa e Dolcetto fino ad un massimo del 15%.")
    assert _roles(body, "Langhe") == {"nebbiolo": "principal", "barbera": "accessory",
                                      "freisa": "accessory", "dolcetto": "accessory"}


def test_an_adverb_or_deve_before_concorrere_still_marks_the_accessory():
    body = ("- Sangiovese dal 90% fino al 100%.\nPossono inoltre concorrere alla produzione di detto "
            "vino le uve dei vitigni Colorino, Canaiolo, Ciliegiolo, insieme o disgiuntamente nella "
            "misura massima del 10%.")
    roles = _roles(body, "Chianti Classico")
    assert roles["sangiovese"] == "principal"
    complement = {m.slug for m in (match_variety(n) for n in ("Colorino", "Canaiolo", "Ciliegiolo")) if m}
    assert complement and all(roles[slug] == "accessory" for slug in complement), (complement, roles)
    body = ("Il vino rosé deve essere ottenuto dal vitigno Glera per un minimo del 85%; deve "
            "concorrere, in ambito aziendale per un minimo del 10%, il vitigno Pinot nero.")
    assert _roles(body, "Prosecco") == {"glera": "principal", "pinot-noir": "accessory"}


def test_a_list_on_its_own_lines_belongs_to_the_clause_that_opened_it():
    body = ("I vini devono essere ottenuti dal vitigno Glera; possono concorrere, da soli o "
            "congiuntamente fino ad un massimo del 15%, i seguenti vitigni:\nVerdiso, Perera, "
            "Chardonnay, Pinot bianco e Pinot grigio.")
    roles = _roles(body, "Prosecco")
    assert roles["glera"] == "principal"
    assert {roles[s] for s in ("verdiso", "perera", "chardonnay", "pinot-blanc", "pinot-gris")} == {"accessory"}


def test_role_lists_are_read():
    body = "Vitigni principali: Bosco e/o Albarola;\nvitigni complementari: Vermentino."
    assert _roles(body, "Cinque Terre") == {"bosco": "principal", "albarola": "principal",
                                            "vermentino": "accessory"}


def test_a_roster_phrased_as_concorrere_keeps_every_variety_principal():
    body = ("Alla produzione del vino possono concorrere, da soli o congiuntamente, i seguenti "
            "vitigni: Barbera, Dolcetto, Freisa.")
    assert set(_roles(body, "Piemonte").values()) == {"principal"}
    assert clause_roles(body, ["Barbera", "Dolcetto", "Freisa"]) == {}


def test_da_sole_o_congiuntamente_binds_no_grape():
    for word in ("sole", "soli", "sola"):
        assert match_variety(word) is None, word


def test_context_pin_table_is_sound():
    raw = json.loads(CONTEXT_OVERRIDES_PATH.read_text(encoding="utf-8"))
    pins = context_pins()
    assert pins
    assert set(pins) == {k for k in raw if not k.startswith("_")}
    for record, table in pins.items():
        assert (ROOT / "raw/it/masaf-disciplinari-extracted" / f"{record}.json").exists(), record
        for surface, pin in table.items():
            assert surface == surface.lower().strip(), (record, surface)
            assert pin["slug"] in DEFAULT_COLOUR or pin["slug"] in GRAPE_ALIAS, (record, surface)
            for field in ("reason", "source", "verified"):
                assert pin.get(field), (record, surface, field)


def test_a_variety_named_only_in_an_exclusion_is_not_in_the_roster():
    body = ("“Montecucco” Rosso: Sangiovese, almeno 60%. Possono concorrere alla produzione di detto "
            "vino, le uve a bacca rossa di altri vitigni idonei alla coltivazione nell’ambito della "
            "Regione Toscana, fino ad un massimo del 40% con l’esclusione della Malvasia Nera, "
            "Malvasia Nera di Brindisi e Aleatico.")
    roles = _roles(body, "Montecucco")
    assert roles == {"sangiovese": "principal"}


def test_a_labelling_sentence_and_a_concession_are_not_exclusions():
    label = ("L'indicazione geografica tipica \"Nurra\", con la specificazione di uno dei vitigni idonei "
             "alla coltivazione nella regione Sardegna con l'esclusione dei vitigni Cannonau, Monica e "
             "Vermentino è riservata ai vini ottenuti per almeno l'85% dal corrispondente vitigno.")
    assert exclusion_drops(label, ["Cannonau", "Monica", "Vermentino"]) == set()
    concession = ("Possono concorrere altri vitigni a bacca bianca idonei alla coltivazione nella Regione "
                  "Piemonte, con l’esclusione del Moscato Bianco per il quale è consentita la presenza "
                  "fino al 3%.")
    assert exclusion_drops(concession, ["Moscato Bianco"]) == set()
    exception = "Vitigni non aromatici, ad eccezione del Sangiovese che potrà essere aggiunto sino al 50%."
    assert exclusion_drops(exception, ["Sangiovese"]) == set()


def test_an_exclusion_in_one_type_does_not_drop_a_variety_another_type_is_made_of():
    body = ("«Friuli Isonzo» bianco: uve dei vitigni a bacca bianca idonei, esclusa la varietà «Moscato "
            "giallo»; «Friuli Isonzo» Moscato giallo: Moscato giallo minimo 85%.")
    assert exclusion_drops(body, ["Moscato giallo"]) == set()
    assert match_variety("giallo") is None


def test_vitigno_scan_drops_a_conjunction_the_terminator_left_on_the_name():
    """"dal vitigno Brachetto e per il restante 3%" read "Brachetto e" (and Asti's
    "Moscato bianco e"), a spelling the card's umlaut fold then hid behind
    "Brachetto" — found by the bracket-fold sweep of 2026-10-23."""
    from _lib.it.masaf import _scan_vitigno_phrases

    body = ("I vini devono essere ottenuti da uve provenienti da vigneti composti per non meno "
            "del 97% dal vitigno Brachetto e per il restante 3% provenienti da vitigni idonei.")
    assert _scan_vitigno_phrases(body) == ["Brachetto"]
    assert _scan_vitigno_phrases("ottenuti dal vitigno Moscato bianco e per il restante 15% da") == [
        "Moscato bianco"]
    # a conjunction between two names still splits them
    assert _scan_vitigno_phrases("dai vitigni Barbera e Freisa, con") == ["Barbera", "Freisa"]
