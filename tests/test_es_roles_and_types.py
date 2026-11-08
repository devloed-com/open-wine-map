"""The ES reader after the Bullas flag of 2026-11-08: the singular "principal"
role header, the "secundarias" list, the sentence that names the principal
varieties after the roster, the « … » name wrapped over a line break, the
wine types a national pliego states once with the word "vino", and the
template-title slicer of the EUR-Lex single document."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("es02", ROOT / "scripts" / "es" / "02_extract_pliegos.py")
es02 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(es02)


def _roles(text: str) -> dict[str, str]:
    g = es02.parse_grapes(text)
    return {d["name"]: d["role"] for d in g["details"]}


def test_the_singular_principal_header_flips_the_role_back():
    # Valtiendas: read after "- Variedades autorizadas: Albillo Mayor." the
    # line kept the accessory role, "principales?" never matching "principal".
    text = (
        "      a) Variedades de uva blanca:\n\n"
        "             - Variedades autorizadas: Albillo Mayor.\n\n"
        "      b) Variedades de uva tinta:\n\n"
        "             - Variedad principal: Tempranillo.\n"
        "             - Variedades autorizadas: Garnacha Tinta, Cabernet-Sauvignon,\n"
        "                 Merlot y Syrah.\n"
    )
    roles = _roles(text)
    assert roles["tempranillo"] == "principal"
    assert roles["albillo mayor"] == "accessory"
    assert roles["garnacha tinta"] == "accessory"
    assert roles["merlot"] == "accessory"


def test_secundarias_is_the_accessory_list():
    text = (
        "      a) Variedades de uva blanca:\n"
        "          Variedades principales: Albillo Mayor, Albillo Real, Viura (sin.\n"
        "            Macabeo) y Verdejo.\n"
        "          Variedades secundarias: Rojal (sin.: Malvasía Riojana, Alarije),\n"
        "            Albarín Blanco, Chardonnay.\n"
        "      b) Variedades de uva tinta:\n"
        "          Variedades principales: Garnacha Tinta, Mencía.\n"
        "          Variedades secundarias: Cabernet\n"
        "            Sauvignon, Merlot.\n"
    )
    roles = _roles(text)
    assert {n for n, r in roles.items() if r == "principal"} == {
        "albillo mayor", "albillo real", "viura", "verdejo", "garnacha tinta", "mencía"}
    assert roles["chardonnay"] == "accessory"
    assert roles["merlot"] == "accessory"
    assert roles["albarín blanco"] == "accessory"


def test_a_sentence_after_the_roster_names_the_principal_varieties():
    bullas = (
        "La elaboración de los vinos protegidos se realiza exclusivamente con uvas de las siguientes\n"
        "variedades:\n\n"
        "Tintas: Monastrell, Tempranillo, Cabernet Sauvignon, Syrah, Merlot, Garnacha Tinta, Garnacha\n"
        "Tintorera y Petit Verdot.\n\n\n"
        "Blancas: Macabeo, Airen, Chardonnay, Malvasía, Moscatel de Alejandría, Moscatel de Grano\n"
        "Menudo y Sauvignon Blanc.\n\n"
        "De estas variedades se considera como principal la Monastrell en tintas y la Macabeo entre las\n"
        "blancas.\n"
    )
    roles = _roles(bullas)
    assert {n for n, r in roles.items() if r == "principal"} == {"monastrell", "macabeo"}
    assert roles["tempranillo"] == "accessory"
    assert roles["sauvignon blanc"] == "accessory"


def test_the_sentence_inside_a_colour_group_and_the_longer_name_first():
    lebrija = (
        "a) Variedades blancas: Moscatel de Alejandría, Palomino, Palomino Fino y Sauvignon Blanc. De ellas son\n"
        "consideradas principales Palomino y Palomino Fino.\n"
        "b) Variedades tintas: Cabernet Sauvignon, Syrah, Tempranillo, Merlot, Petit Verdot y Tintilla de Rota.\n"
    )
    roles = _roles(lebrija)
    assert {n for n, r in roles.items() if r == "principal"} == {"palomino", "palomino fino"}
    assert roles["moscatel de alejandría"] == "accessory"
    assert roles["tintilla de rota"] == "accessory"


def test_the_list_form_and_the_plural_family_word():
    mino = (
        "Son aptas para la producción de vino acogido a la indicación geográfica protegida\n"
        "Valle del Miño-Ourense las uvas de las variedades siguientes:\n\n"
        "- Blancas: Treixadura, Torrontés, Godello, Albariño, Loureira y Palomino.\n\n"
        "- Tintas: Mencía, Brancellao, Mouratón, Sousón y Garnacha tintorera.\n\n"
        "Los vinos deberán ser elaborados con un mínimo del 60 % de uva de las siguientes\n"
        "variedades consideradas como principales:\n\n"
        "- Blancas: Treixadura, Torrontés, Godello, Albariño y Loureira.\n\n"
        "- Tintas: Mencía, Brancellao, Mouratón y Sousón.\n"
    )
    roles = _roles(mino)
    assert {n for n, r in roles.items() if r == "accessory"} == {"palomino", "garnacha tintorera"}
    malaga = (
        "La elaboración de los vinos protegidos se realizará con uvas de las variedades «Pero\n"
        "Ximén» (Pedro Ximénez), «Moscatel de Málaga» (Moscatel de Alejandría), «Moscatel\n"
        "Morisco» (Moscatel de grano menudo), Lairén, Doradilla y Rome, de las que se consideran\n"
        "preferentes «Pero Ximén» y las «Moscateles».\n"
    )
    roles = _roles(malaga)
    # the « name wrapped over the line break is one variety, Pedro Ximénez
    assert "ximén" not in roles
    assert roles["pero ximén"] == "principal"
    assert roles["moscatel de málaga"] == "principal"
    assert roles["moscatel morisco"] == "principal"
    assert {n for n, r in roles.items() if r == "accessory"} == {"lairén", "doradilla", "rome"}


def test_an_explicit_accessory_list_leaves_the_sentence_alone():
    text = (
        "- Variedades principales: Verdejo y Malvasía Castellana.\n"
        "- Variedades autorizadas: Garnacha Tinta y Cabernet Sauvignon.\n"
        "Se considera como principal la Verdejo.\n"
    )
    roles = _roles(text)
    assert roles["malvasía castellana"] == "principal"
    assert roles["garnacha tinta"] == "accessory"


def _styles(sections: dict[str, str], titles: dict[str, str]) -> set[str]:
    return set(es02.parse_styles_es(sections, titles))


def test_the_type_list_sentence_states_the_types_once():
    bullas = {"2": (
        "a) Características analíticas.\n\n"
        "     Los tipos de los vinos amparados por esta Denominación de Origen Protegida, dispuestos para el\n"
        "     consumo, son los siguientes: blancos, rosados, tintos, de licor y espumosos y en función del\n"
        "     contenido en azúcar, se clasifican en secos, dulces, semisecos y semidulces.\n"
    )}
    found = _styles(bullas, {"2": "DESCRIPCIÓN DE LOS VINOS"})
    assert {"red", "rose", "white", "vin-de-liqueur", "sparkling", "sweet"} <= found
    murcia = {"2": (
        "  Los tipos de los vinos amparados por esta Indicación Geográfica Protegida, dispuestos para el\n"
        "  consumo, son los siguientes: blancos, rosados y tintos; de licor; de uva sobremadura y de aguja.\n"
    )}
    found = _styles(murcia, {"2": "DESCRIPCIÓN DE LOS VINOS"})
    assert {"vin-de-liqueur", "uvas-sobremaduradas", "semi-sparkling"} <= found


def test_bulleted_and_numbered_type_lines():
    hierro = {"2": (
        "    - Vino blanco\n    - Vino rosado\n    - Vino tinto\n"
        "    - Vino de licor\n    - Vino dulce clásico\n    - Vino espumoso\n\n"
        "a) Características analíticas:\n1. Grado alcohólico volumétrico adquirido mínimo:\n"
    )}
    found = _styles(hierro, {"2": "Descripción del vino"})
    assert {"vin-de-liqueur", "sparkling", "sweet"} <= found
    castello = {"2": "Los vinos amparados por la IGP Castelló son los siguientes:\n"
                     "      Vino\n      Vino de uva sobremadurada\n"
                     "      Vino espumoso de calidad\n      Vino de aguja\n"}
    found = _styles(castello, {"2": "Descripción del vino"})
    assert {"sparkling-quality", "semi-sparkling", "uvas-sobremaduradas"} <= found
    # the single document's per-type headers, now lines of its description
    valencia = {"4": "1. Vino blanco\nFase visual …\n4. Vino de licor blanco, rosado y tinto\n…\n"
                     "5. Vino espumoso aromático de calidad blanco\n…\n6. Vino de aguja blanco, rosado y tinto\n"}
    found = _styles(valencia, {"4": "Descripción del (de los) vino(s)"})
    assert {"vin-de-liqueur", "sparkling-quality", "semi-sparkling", "white", "red", "rose"} <= found


def test_the_eu_category_cited_by_number_and_the_category_list():
    cyl = {"2": (
        "Los vinos amparados por la I.G.P. «CASTILLA Y LEÓN» pertenecen a la categoría\n"
        "         1 “Vino”, a la categoría 3 “Vino de licor”, a la categoría 5 “Vino espumoso de\n"
        "         calidad”, a la categoría 8 “Vino de aguja” y a la categoría 16 “Vino de uvas\n"
        "         sobremaduradas” de acuerdo con el Reglamento.\n"
    )}
    found = _styles(cyl, {"2": "DESCRIPCIÓN DEL VINO"})
    assert {"vin-de-liqueur", "sparkling-quality", "semi-sparkling", "uvas-sobremaduradas"} <= found
    tharsys = {"2": "Los vinos serán de la categoría 1: tintos, rosados y blancos y de la categoría 5:\n"
                    "    espumosos de calidad: rosados y blancos, del Anexo VII Parte II del Reglamento\n"}
    assert {"sparkling", "sparkling-quality"} <= _styles(tharsys, {"2": "DESCRIPCIÓN DE LOS VINOS"})
    malaga = {"B": "- Categorías de productos vitícolas: vino, vino de licor, vino de uvas sobremaduradas y\n"
                   "  vino de uvas pasificadas.\n"}
    assert {"vin-de-liqueur", "uvas-sobremaduradas", "uvas-pasificadas"} <= _styles(
        malaga, {"B": "DESCRIPCIÓN DE LOS VINOS"})


def test_a_type_stated_as_a_heading_in_capitals():
    link = {"8": "Todos estos factores favorecen la obtención de vinos complejos.\n"
                 "VINO DE LICOR\nLas características edafoclimáticas son ideales.\n"
                 "VINO DE ESPUMOSO DE CALIDAD\nDe los viñedos orientados al norte …\n"}
    found = _styles(link, {"8": "Descripción del (de los) vínculo(s)"})
    assert {"vin-de-liqueur", "sparkling-quality"} <= found
    # prose is not a heading
    prose = {"8": "Las características edafoclimáticas son ideales para elaborar vinos de licor.\n"}
    assert "vin-de-liqueur" not in _styles(prose, {"8": "Descripción del (de los) vínculo(s)"})


def _h(num: str, title: str) -> str:
    return f'<p class="ti-grseq-1"><span class="bold">{num}. {title}</span></p>'


def test_the_slicer_keeps_the_templates_titles_and_leaves_the_nested_headers_in_the_body():
    html = (
        _h("1", "Nombre(s)") + "<p>«Valencia»</p>"
        + _h("2", "Tipo de indicación geográfica") + "<p>DOP</p>"
        + _h("3", "Categorías de productos vitivinícolas")
        + "<p>1. Vino</p><p>3. Vino de licor</p><p>6. Vino espumoso aromático de calidad</p>"
        + _h("3.1", "Código de nomenclatura combinada") + "<p>2204</p>"
        + _h("4", "Descripción del (de los) vino(s)")
        + _h("1", "Vino blanco") + "<p>Fase visual</p>"
        + _h("4", "Vino de licor blanco, rosado y tinto") + "<p>Color ámbar</p>"
        + _h("5", "Vino espumoso aromático de calidad blanco") + "<p>Burbuja fina</p>"
        + _h("5", "Prácticas vitivinícolas")
        + _h("5.1", "Prácticas enológicas específicas") + "<p>—</p>"
        + _h("6", "Zona geográfica delimitada") + "<p>Provincia de Valencia</p>"
        + _h("7", "Variedad(es) de uva de vinificación") + "<p>MACABEO</p>"
        + _h("8", "Descripción del (de los) vínculo(s)") + "<p>El clima</p>"
        + _h("9", "Condiciones complementarias esenciales") + "<p>Envasado</p>"
    )
    sections, titles = es02.extract_sections(html)
    assert titles["4"] == "Descripción del (de los) vino(s)"
    assert titles["5"] == "Prácticas vitivinícolas"
    assert titles["6"] == "Zona geográfica delimitada"
    assert "Vino espumoso aromático de calidad blanco" in sections["4"]
    assert "Vino de licor blanco" in sections["4"]
    assert "6. Vino espumoso aromático de calidad" in sections["3"]
    assert sections["7"].strip() == "MACABEO"
    found = _styles(sections, titles)
    assert {"vin-de-liqueur", "sparkling-quality", "white", "red", "rose"} <= found
    routed = es02.route_sections(sections, titles)
    assert routed["grape_varieties"].strip() == "MACABEO"
    assert routed["description"].startswith("1. Vino blanco")


def test_a_document_without_the_templates_titles_is_read_as_before():
    html = _h("1", "Práctica de cultivo") + "<p>a</p>" + _h("2", "Restricción") + "<p>b</p>" + _h("3", "Rendimiento") + "<p>c</p>"
    sections, titles = es02.extract_sections(html)
    assert set(titles) == {"1", "2", "3"}
