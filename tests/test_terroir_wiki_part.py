"""A `both` fact whose bullet carries a term only its Wikipedia quote
grounds is marked `wiki_part`, and the card shows the Wikipedia marker on it
(card validator on Manchuela and Somontano, 2026-10-30)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.terroir_wiki_part import (  # noqa: E402
    has_wiki_only_part,
    mark_wiki_parts,
    wiki_only_terms,
)

MANCHUELA_LIEN = ("Clima continental, con ausencia casi total de lluvias entre los meses de "
                  "mayo y septiembre, y suelos arcillosos de base calcárea.")


def _flag(bullet: str, regulator: str, wiki_quote: str) -> bool:
    return has_wiki_only_part(wiki_only_terms(bullet, regulator, wiki_quote))


def test_a_figure_only_wikipedia_gives():
    bullet = ("El clima continental registra una temperatura media anual de 13 °C y "
              "precipitaciones en torno a 600 l/m², con ausencia casi total de lluvias entre mayo y septiembre.")
    wq = "el clima es continental con una temperatura media de 13° anualmente, las precipitaciones rondan los 600 l/m²"
    terms = wiki_only_terms(bullet, MANCHUELA_LIEN, wq)
    assert "13" in terms["numbers"] and "2" not in terms["numbers"]
    assert has_wiki_only_part(terms)


def test_a_clause_only_wikipedia_states():
    bullet = ("El asentamiento de itálicos en el Somontano importó técnicas vitivinícolas avanzadas, "
              "y fueron los romanos quienes consolidaron el cultivo de la vid.")
    lien = "El asentamiento de itálicos en el Somontano importó técnicas vitivinícolas avanzadas."
    wq = "Fueron los romanos quienes consolidaron el cultivo de la vid."
    assert _flag(bullet, lien, wq)


def test_a_unit_word_or_one_inflection_is_not_a_part():
    lien = "La zona se encuentra entre los 350 y los 1000 m sobre el nivel del mar."
    assert not _flag("Altura entre los 350 y los 1000 metros sobre el nivel del mar.", lien,
                     "La altitud oscila entre los 350 metros y los 1000 metros.")
    assert not _flag("Suelos de pizarras llamadas llicorella.", "Suelos de pizarras denominadas llicorella.",
                     "suelos pizarrosos llamados llicorelles")


def test_a_proper_noun_only_wikipedia_names():
    lien = "El vino se elabora con tempranillo y otras variedades."
    assert _flag("El vino ensambla tempranillo con Petit Verdot.", lien,
                 "proporciones variables de los varietales Syrah y Petit Verdot")


def test_a_claim_the_regulator_states_elsewhere_is_not_a_part():
    regulator = "Art. 3. La zona comprende tutto il territorio amministrativo dei comuni di Brindisi e Mesagne."
    assert not _flag("La zona comprende tutto il territorio amministrativo dei comuni di Brindisi e Mesagne.",
                     regulator, "comprende tutto il territorio amministrativo dei comuni di Brindisi e Mesagne")


def test_mark_wiki_parts_sets_both_facts_only():
    facts = [
        {"provenance": "both", "bullet": "Media de 13 °C.", "wiki_quote": "media de 13 °C"},
        {"provenance": "both", "bullet": "Suelos arcillosos.", "wiki_quote": "suelos arcillosos"},
        {"provenance": "cahier", "bullet": "x", "wiki_part": True},
    ]
    assert mark_wiki_parts(facts, "Suelos arcillosos.") == 3
    assert facts[0]["wiki_part"] is True and facts[1]["wiki_part"] is False
    assert "wiki_part" not in facts[2]
    assert mark_wiki_parts(facts, "Suelos arcillosos.") == 0


def test_a_german_bullet_needs_a_number_or_two_stems_not_one_capitalised_noun():
    lien = "Die Weingärten liegen auf Löss und Kalk."
    bullet = "Die Weingärten liegen im Flusstal auf Löss und Kalk."
    wq = "die Weingärten im Flusstal"
    assert _flag(bullet, lien, wq)  # read as a Romance bullet, "Flusstal" is a proper noun
    facts = [{"provenance": "both", "bullet": bullet, "wiki_quote": wq}]
    mark_wiki_parts(facts, lien, source_lang="de")
    assert facts[0]["wiki_part"] is False
    facts = [{"provenance": "both", "bullet": "Rund 80 Prozent der Flächen tragen Weißwein.",
              "wiki_quote": "auf rund 80 Prozent der Flächen"}]
    mark_wiki_parts(facts, "Es wird hauptsächlich Weißwein produziert.", source_lang="de")
    assert facts[0]["wiki_part"] is True
