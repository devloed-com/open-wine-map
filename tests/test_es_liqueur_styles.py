"""The ES style reader after the Manzanilla question of 2026-11-13: a liqueur
wine is fortified, sweet only where its text says so, and a generoso is
oxidative only through the types whose ageing is (amontillado, oloroso, palo
cortado) — Manzanilla's single document reads "Seco … azúcar inferior a 4
g/L" and "crianza biológica", and its card showed Sweet and Oxidative."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("es02", ROOT / "scripts" / "es" / "02_extract_pliegos.py")
es02 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(es02)

DESCR = "Descripción del (de los) vino(s)"
CATS = "Categorías de productos vitivinícolas"


def _styles(sections: dict[str, str], titles: dict[str, str]) -> set[str]:
    return set(es02.parse_styles_es(sections, titles))


def test_manzanilla_is_neither_sweet_nor_oxidative():
    sections = {
        "1": "«Manzanilla-Sanlúcar de Barrameda / Manzanilla de Sanlúcar / Manzanilla»",
        "5": "1.\nVino\n3.\nVino de licor",
        "6": ("Producto vitivinícola\nVinos de licor\nCaracterísticas organolépticas\n"
              "Aroma\nDeberá presentar al menos dos de los siguientes aromas propios de la "
              "crianza biológica: flores blancas, frutos secos o levadura.\n"
              "Sabor\nSeco y de sensación salina en boca.\n"
              "Contenido en azúcar inferior a 4 g/L expresado en glucosa y fructosa.\n"),
        "8": "—\nPALOMINO\n—\nPALOMINO FINO — LISTÁN BLANCO",
        "10": "… lo que permite la elaboración de vinos generosos con niveles de vejez elevada.",
    }
    titles = {
        "1": "Nombre(s)", "5": CATS, "6": "Descripción del vino o vinos",
        "8": "Indicación de la variedad o variedades de uva de las que procede el vino o vinos",
        "10": "Vínculo con la zona geográfica",
    }
    found = _styles(sections, titles)
    assert {"fortified", "vin-de-liqueur", "generoso", "manzanilla"} <= found
    assert not {"sweet", "oxidative", "fino"} & found


def test_a_dry_liqueur_wine_is_not_sweet():
    rueda = {"3": "Vino\nVino de licor\nVino espumoso de calidad",
             "4": ("4.   VINO DE LICOR — Dorado\nBREVE DESCRIPCIÓN TEXTUAL\n"
                   "Fase gustativa: Equilibrio en boca, glicérico y postgusto con recuerdos de "
                   "aromas terciarios (frutos secos).\n"
                   "5.   VINO DE LICOR Pálido\nFase gustativa: Equilibrio en boca, glicérico.\n")}
    found = _styles(rueda, {"3": CATS, "4": DESCR})
    assert {"fortified", "vin-de-liqueur"} <= found
    assert "sweet" not in found


def test_the_liqueur_block_states_its_sweetness():
    valencia = {"4": ("3.    Vino tinto\nEn boca seco, con taninos dulces y maduros.\n"
                      "4.    Vino de licor blanco, rosado y tinto\nBREVE DESCRIPCIÓN TEXTUAL\n"
                      "Nariz de buena intensidad, especialmente cuando proceda de la uva Moscatel. "
                      "En boca dulce y golosa, equilibrada y de potente postgusto.\n")}
    assert "sweet" in _styles(valencia, {"4": DESCR})
    jumilla = {"4": ("9.    Vinos de Licor (Tinto Monastrell)\nBREVE DESCRIPCIÓN TEXTUAL\n"
                     "Fase Olfativa: Fruta Negra. Fruta desecada. Fase Gustativa: El dulzor "
                     "predomina sobre la acidez. Tánicos.\n")}
    assert "sweet" in _styles(jumilla, {"4": DESCR})
    valdejalon = {"B": ("Vinos tintos: Color rojo cereza. En boca son secos y estructurados.\n"
                        "Vinos de licor: Color ámbar de intensidad variable y aspecto denso. En nariz se\n"
                        "apreciarán claramente las notas aromáticas primarias. En boca será dulce, y untuoso\n")}
    assert "sweet" in _styles(valdejalon, {"B": "DESCRIPCION DE LOS VINOS"})


def test_a_section_titled_for_the_liqueur_wine_states_it():
    navarra = {"3": "Vino\nVino de licor",
               "8.2": ("Vinos elaborados fundamentalmente a partir de las variedades Moscatel de Grano "
                       "Menudo y Garnacha, caracterizados por un elevado contenido en azúcar, redondez "
                       "y untuosidad.")}
    assert "sweet" in _styles(navarra, {"3": CATS, "8.2": "Vino de licor"})
    # grapes rich in sugar are not a sweet wine (Costers del Segre, Utiel-Requena)
    costers = {"3": "Vino\nVino de licor",
               "8.3": ("Las elevadas temperaturas diurnas permiten retrasar la cosecha y obtener uvas "
                       "muy ricas en azúcares. Existe la tradición de elaborar vinos de licor con "
                       "cosechas tardías.")}
    found = _styles(costers, {"3": CATS, "8.3": "Vino de licor"})
    assert "vin-de-liqueur" in found and "sweet" not in found


def test_a_type_header_that_says_dulce_is_sweet():
    montilla = {"4": ("3.    Vinos generosos (categoría 1)\nFino: de color amarillo pajizo.\n"
                      "6.    Vinos de licor dulces (categoría 3)\n"
                      "Contenido en azúcares (g de glucosa + fructosa/L) ≥272\n")}
    found = _styles(montilla, {"4": DESCR})
    assert {"sweet", "fino", "generoso", "vin-de-liqueur"} <= found
    jucar = {"4": "1.    Vino Blanco y Rosado, seco\n2.    Vino Blanco y Rosado, dulce\n"}
    assert "sweet" in _styles(jucar, {"4": DESCR})


def test_tannins_and_fruit_are_not_a_sweet_wine():
    text = {"4": ("5.   Vino de licor\nBREVE DESCRIPCIÓN TEXTUAL\n"
                  "En boca cálido, con taninos dulces y recuerdos de fruta dulce; sin dulzor marcado "
                  "en nariz. Untuoso y persistente.\n")}
    assert "sweet" not in _styles(text, {"4": DESCR})


def test_oxidative_comes_with_the_oxidative_types_only():
    jerez = {"4": ("Vinos generosos\nFino: vino de color amarillo pajizo, crianza bajo velo de flor.\n"
                   "Oloroso: vino de color ámbar a caoba.\n")}
    found = _styles(jerez, {"4": DESCR})
    assert {"generoso", "fino", "oloroso", "oxidative"} <= found
    lebrija = {"B": ("c) Vino generoso: vino de licor elaborado bajo velo de flor, proceso biológico.\n"
                     "d) Vino generoso de licor: Es el vino de licor obtenido a partir de vino generoso.\n")}
    found = _styles(lebrija, {"B": "DESCRIPCIÓN DE LOS VINOS"})
    assert {"generoso", "fortified", "vin-de-liqueur"} <= found
    assert "oxidative" not in found
