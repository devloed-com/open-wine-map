"""A sub-denomination's own roster outside France and Italy.

Excerpts follow the documents in force: the IVV caderno of DO Vinho Verde
(section 6 sub-região tables), the Valais OVV (art. 88), the Ticino
regolamento (art. 20, 23) and the national pliego of DO Vinos de Madrid.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from _lib.augment.es import _apply_subzona_principals
from _lib.ch.reglement import colour_blocks, grand_cru_block, list_varieties
from _lib.grape_entity import match_variety

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("pt_02", ROOT / "scripts/pt/02_extract_cadernos.py")
pt_02 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pt_02)

VINHO_VERDE_GRAPES = """Alvarinho
Amaral
Arinto; Pedernã
Avesso
Azal
Loureiro
Vinhão; Sousão

Os vinhos e produtos vitivinícolas com indicação de sub-região devem ser exclusivamente obtidos
a partir das castas enumeradas nos quadros seguintes para a respetiva sub-região.

Sub-região de Baião
Alvarelhão Brancelho
Amaral
Arinto Pedernã
Avesso
 Azal
Borraçal
Vinhão Sousão

Sub-região de Monção e Melgaço
Alvarelhão; Brancelho
Alvarinho
Borraçal
Loureiro
Pedral
 Trajadura; Treixadura
 Vinhão; Sousão
"""


def test_a_sub_regiao_reads_its_own_table():
    melgaco = pt_02.subregion_grapes(VINHO_VERDE_GRAPES, "Monção e Melgaço")["principal"]
    assert "albarino" in melgaco and "avesso" not in melgaco and "azal" not in melgaco
    assert pt_02.subregion_grapes(VINHO_VERDE_GRAPES, "Lima") is None


def test_a_lost_synonym_semicolon_is_restored():
    baiao = pt_02.subregion_grapes(VINHO_VERDE_GRAPES, "Baião")["principal"]
    assert {"alvarelhao", "arinto", "vinhao"} <= set(baiao)
    assert "alvarelhao-branco" not in baiao and "albarino" not in baiao


def test_the_parent_stops_at_the_first_sub_regiao():
    parent = pt_02.parse_grape_list(VINHO_VERDE_GRAPES)["principal"]
    assert "pedral" not in parent and "albarino" in parent


VS_ART_88 = """Art. 88       Cépages
1
  L’appellation Grand Cru est réservée aux cépages suivants :4
a) Cépages blancs: 4,5
Chasselas (Fendant), Sylvaner (Rhin ou gros Rhin), Arvine (Petite
Arvine), Marsanne blanche (Ermitage), Roussanne, Savagnin blanc (Païen ou
Heida), Pinot gris (Malvoisie);4
b) Cépages rouges:4
Pinot noir, Gamay, Syrah.4
2
  Abrogé.
Art. 89 1     Périmètres de production
  Les cépages doivent être cultivés dans les secteurs d'encépagement pour
"""


def test_valais_grand_cru_list():
    got = {v["slug"] for v in list_varieties(grand_cru_block(VS_ART_88), match_variety)}
    assert got == {"chasselas", "sylvaner", "arvine", "marsanne", "roussanne", "savagnin",
                   "pinot-gris", "pinot-noir", "gamay", "syrah"}


TI_ART_23 = """Vitigni
      Art. 23 Sono vini DOC solo quelli prodotti con uve dei seguenti vitigni:
      a) per le uve rosse: la Bondola, il Cabernet Franc, il Merlot, il Petit Verdot, il
           Pinot Nero e la Syrah;
      b) per le uve bianche: lo Chardonnay, lo Chasselas, il Müller
           Thurgau, il Sauvignon Grigio, il Semillon e
           il Viognier.

1   Cpv. introdotto dal R 11.7.2017; in vigore dal 14.7.2017 - BU 2017, 213.
"""


def test_ticino_lists_by_grape_colour():
    blocks = colour_blocks(TI_ART_23)
    red = {v["slug"] for v in list_varieties(blocks["red"], match_variety)}
    white = {v["slug"] for v in list_varieties(blocks["white"], match_variety)}
    assert red == {"bondola", "cabernet-franc", "merlot", "petit-verdot", "pinot-noir", "syrah"}
    assert white == {"chardonnay", "chasselas", "muller-thurgau", "sauvignon-gris", "semillon",
                     "viognier"}
    assert colour_blocks("Vitigni ammessi: Merlot, Chasselas.") == {}


MADRID_SECTION = """  Tintas: Tinto Fino (Tempranillo), Garnacha Tinta, Merlot, Syrah.

  Principales Subzona de Arganda

          -    Blancas: Malvar.
          -    Tintas: Tinto Fino (Tempranillo).

Principales Subzona de San Martin de Valdeiglesias

       - Blancas: Albillo Real.
       - Tintas: Garnacha Tinta.
"""


def _record(name):
    roster = ["malvar", "albillo-real", "airen", "tempranillo", "grenache", "merlot", "syrah"]
    return {"name": name, "is_sub_denomination": True,
            "grapes": {"principal": roster, "accessory": [],
                       "details": [{"slug": s, "name": s, "role": "principal"} for s in roster]}}


def test_madrid_subzona_principals_leave_the_rest_accessory():
    arganda = _record("Arganda")
    _apply_subzona_principals(arganda, {"section_text": MADRID_SECTION})
    assert arganda["grapes"]["principal"] == ["malvar", "tempranillo"]
    assert "albillo-real" in arganda["grapes"]["accessory"]
    san_martin = _record("San Martin de Valdeiglesias")
    _apply_subzona_principals(san_martin, {"section_text": MADRID_SECTION})
    assert san_martin["grapes"]["principal"] == ["albillo-real", "grenache"]
    other = _record("El Molar")
    _apply_subzona_principals(other, {"section_text": MADRID_SECTION})
    assert len(other["grapes"]["principal"]) == 7
