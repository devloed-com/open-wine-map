"""Regression tests for the style fixes of 2026-10-23 (validator findings,
phase C): the declared product categories behind the grape-colour fallbacks
(a sparkling-only appellation gets no colour from its grapes), sweet and
dessert wine words read as Sweet rather than Late Harvest, ice wine as
Icewine, rosé read from the text in the UK and Maltese specifications, and
the category / colour readers added for PT, SI, SK, ES, GR, CY and HU."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib import wine_categories as wc  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
be02 = importlib.import_module("be.02_extract_pliegos")


# ---- declared categories ----------------------------------------------------

def test_category_items_are_classified_in_every_corpus_language():
    assert wc.classify("1. Vin") == "still"
    assert wc.classify("Vinho branco, tinto, e rosado ou rosé") == "still"
    assert wc.classify("Vino (1)") == "still"
    assert wc.classify("4. Vin mousseux") == "sparkling"
    assert wc.classify("5.\nVino spumante di qualità") == "sparkling"
    assert wc.classify("Szén-dioxid hozzáadásával készült gyöngyözőbor") == "sparkling"
    assert wc.classify("Vinho licoroso") == "other"
    assert wc.classify("Víno z prezretého hrozna") == "other"
    assert wc.classify("Οίνος λικέρ") == "other"


def test_a_sparkling_only_list_and_one_that_declares_still_wine():
    vlaamse = {"country": "be", "section_titles": {"3": "Categorieën van wijnbouwproducten"},
               "sections": {"3": "1. mousserende kwaliteitswijn"}}
    dealu_mare = {"country": "ro", "section_titles": {"3": "Categorii de produse vitivinicole"},
                  "sections": {"3": "1.\nVin\n5.\nVin spumant de calitate\n8.\nVin petiant"}}
    assert wc.sparkling_only(vlaamse)
    assert not wc.declares_still(vlaamse)
    assert wc.declares_still(dealu_mare)
    assert not wc.sparkling_only(dealu_mare)
    # a per-type section is not the list ("WIJNCATEGORIE 1 Wijn, Wijntype: …")
    per_type = {"country": "nl", "section_titles": {"9": "WIJNCATEGORIE 5: mousserende kwaliteitswijn"},
                "sections": {"9": "mousserende kwaliteitswijn"}}
    assert wc.declared_kinds(per_type) is None
    # the French title carries an accent
    fr = {"country": "be", "section_titles": {"2": "CATÉGORIES DE PRODUITS DE LA VIGNE"},
          "sections": {"2": "4. Vin mousseux"}}
    assert wc.sparkling_only(fr)


def test_siqo_categories_decide_for_france():
    assert wc.sparkling_only({"country": "fr", "categories": ['Vin mousseux "Crémant"']})
    assert wc.declares_still({"country": "fr", "categories": ["Vin tranquille", "Vin mousseux"]})
    assert wc.declared_kinds({"country": "fr", "categories": []}) is None


def test_the_stage04_floor_reads_the_declared_categories():
    # stage 04 is not imported here (it loads the corpus caches); its wiring is
    # linted instead, as test_region_scan_wiring does
    src = (ROOT / "scripts" / "04_build_maps.py").read_text(encoding="utf-8")
    assert "and not sparkling_only(record):" in src
    assert "declares_still=declares_still(record)" in src
    assert 'frozenset(_taxonomy_descendants("sparkling"))' in src
    assert "and not declares_still and existing_styles" in src
    audit = (ROOT / "scripts" / "audit_styles.py").read_text(encoding="utf-8")
    assert 'SPARKLING_FAMILY = descendants("sparkling")' in audit


def test_be_sparkling_only_pdo_takes_no_colour_from_its_grapes():
    sections = {"3": "1. mousserende kwaliteitswijn", "4": "Fijne mousse, frisse zuren"}
    titles = {"3": "Categorieën van wijnbouwproducten", "4": "Beschrijving van de wijn(en)"}
    grapes = [{"slug": "pinot-noir", "colour": "noir"}, {"slug": "chardonnay", "colour": "blanc"}]
    assert be02.parse_styles(sections, titles, "nl", grape_details=grapes) == ["sparkling-quality"]
    still = {"3": "1.\nWijn", "4": "Fijne mousse"}
    assert be02.parse_styles(still, titles, "nl", grape_details=grapes) == ["blanc", "noir"]


# ---- sweet, dessert and ice wine are not a late harvest ----------------------

def test_sweet_and_dessert_wine_words_are_the_sweet_style():
    from _lib.bg.edinen_dokument import STYLE_MARKERS as BG
    from _lib.gr.eniaio_engrafo import STYLE_MARKERS as GR
    from _lib.hr.jedinstveni_dokument import STYLE_MARKERS as HR
    from _lib.hu.egyseges_dokumentum import STYLE_MARKERS as HU
    from _lib.ro.document_unic import STYLE_MARKERS as RO

    def styles(markers, text):
        return {slug for pat, slug in markers if pat.search(text)}

    bg = styles(BG, "— за полусладки вина — до 45 g/l; — за сладки вина — над 45 g/l")
    assert bg == {"sweet", "semi-sweet"}
    assert styles(GR, "γλυκύς οίνος") == {"sweet"}
    assert styles(HR, "desertno vino") == {"sweet"}
    assert styles(HU, "csemegebor") == {"sweet"}
    assert styles(RO, "vin de desert") == {"sweet"}
    for markers, ice in ((BG, "ледено вино"), (HR, "ledeno vino"), (HU, "jégbor"),
                         (RO, "vin de gheață")):
        assert styles(markers, ice) == {"icewine"}


def test_hr_spec_dried_berries_are_noble_rot_and_dried_grapes_a_raisin_wine():
    from _lib.hr.specifikacija import _parse_styles
    continental = "„Izborna berba prosušenih bobica“: vino proizvedeno od izabranih prosušenih bobica"
    assert _parse_styles(continental, {}) == ["grains-nobles"]
    coastal = "Desertna vina dobivena su posebnim načinom prerade prezrelog ili prosušenog grožđa."
    assert _parse_styles(coastal, {}) == ["raisin-wine", "sweet", "vendanges-tardives"]


# ---- rosé from the text in the UK and Maltese specifications -----------------

def test_gb_reads_its_colours_from_the_analytical_limits():
    gb02 = importlib.import_module("gb.02_extract_specs")
    parsed = {"part_titles": ["STILL WINE"], "roles": {
        "description": "Still Wine English Wine is made from grapes grown close to the limit",
        "analytical": "5. Volatile Acidity: 1.08mg per litre in white and rosé wines\n"
                      "1.2mg per litre in red wine"}}
    assert gb02.parse_styles(parsed, [], "English") == ["red", "rose", "white"]
    # a red grape is a red wine at most, never a rosé
    bare = {"part_titles": [], "roles": {"description": "a dry still Cornish wine"}}
    assert gb02.parse_styles(bare, [{"colour": "noir"}], "Darnibole") == ["red"]


def test_mt_rose_only_from_the_register_single_document():
    mt02 = importlib.import_module("mt.02_extract_pliegos")
    sections = {"3": "1.\nWine\n4.\nSparkling wine\n15.\nWine from raisined grapes",
                "5.1": "DOK ‘Riżerva’ white wines … DOK ‘Riżerva’ red wines must"}
    titles = {"3": "Categories of grapevine products", "5.1": "Specific oenological practices"}
    noir = [{"colour": "noir"}]
    assert "rose" not in mt02.parse_styles(sections, titles, grape_details=noir)
    fiche = "Red, white and rosé wines are produced … - Sweet wines: minimum total"
    styles = mt02.parse_styles(sections, titles, grape_details=noir, extra_text=fiche)
    assert {"red", "white", "rose", "sweet", "sparkling", "raisin-wine"} <= set(styles)


# ---- GR / CY: one guarded colour matcher, lists of colours -------------------

def test_greek_colour_lists_share_one_wine_word():
    from _lib.gr.eniaio_engrafo import colour_styles
    larnaka = "τίτλος 11% vol. για ερυθρούς και 10% vol. για λευκούς και ερυθρωπούς οίνους."
    assert colour_styles(larnaka) == {"noir", "blanc", "rose"}
    # an aged red's hue, a place name, a hue list: no wine colour
    assert colour_styles("καταλήγοντας σε ερυθρές και καφέ αποχρώσεις") == set()
    assert colour_styles("ο νομός Λευκάδας και η Λευκωσία") == set()
    assert colour_styles("παρατηρούνται ερυθρωπές και έπειτα ιώδεις αποχρώσεις") == set()


# ---- category and colour readers: PT, SI, SK, ES -----------------------------

def test_pt_reads_the_category_list_and_the_masculine_colours():
    pt02 = importlib.import_module("pt.02_extract_cadernos")
    sections = {
        "category": "1. Vinho\n3. Vinho licoroso\n4.Vinho espumante de qualidade",
        "description": "Vinho tinto e rosado – mínimo de 12% vol.;\nVinho branco - mínimo de 11,5 %",
        "practices": "o vinho espumante … fermentação clássica em garrafa",
    }
    assert pt02.parse_styles(sections) == [
        "methode-traditionnelle", "red", "rose", "sparkling", "sparkling-quality",
        "vin-de-liqueur", "white"]
    # the grapes' "uvas tintas" are not a red wine
    assert pt02.parse_styles({"description": "a partir de uvas tintas e brancas"}) == []


def test_si_fiche_styles_read_the_inflected_description():
    from _lib.si.specifikacija import fiche_styles
    description = (
        "Sladkorja prosti ekstrakt mora znašati najmanj 17 g/l za bela in rose vina ter "
        "20 g/l za rdeča vina. Za bela vina vinorodnega okoliša Bela krajina je značilna "
        "sadnost. Posebnost je tudi obsežna pridelava vin posebnih kakovosti, od pozne "
        "trgatve do suhega jagodnega izbora in ledenega vina.")
    assert fiche_styles("1. Vino\n4. Peneče vino", description) == [
        "blanc", "grains-nobles", "icewine", "rose", "rouge", "sparkling", "vendanges-tardives"]
    # the region's name is no white wine
    assert fiche_styles("1. Vino", "Vina Bela krajina so sveža.") == []


def test_sk_spec_reads_the_farba_line_not_a_grape_name():
    from _lib.sk.specifikacija import _text_colours
    text = ("Farba: biela, ružová a červená zodpovedajúca označeniu a ročníku. "
            "najviac 150 mg/l pre červené a 200 mg/l pre biele a ružové vína")
    assert _text_colours(text) == {"blanc", "rose", "rouge"}
    assert _text_colours("Veltlínske červené skoré, Tramín červený; Farba: zlatožltá") == set()


def test_es_reads_a_lettered_wine_type_list():
    es02 = importlib.import_module("es.02_extract_pliegos")
    sections = {"2": "a. Vino Blanco\n    b. Vino Rosado\n    i. Vino Malvasía dulce\n"
                     "    j. Vino espumoso\n    k. Vino de aguja\n    l. Vino de licor\n"}
    titles = {"2": "Descripción del vino"}
    styles = set(es02.parse_styles_es(sections, titles))
    assert {"sparkling", "semi-sparkling", "vin-de-liqueur", "sweet", "white", "rose"} <= styles


def test_es_reads_a_type_list_numbered_under_its_letter():
    es02 = importlib.import_module("es.02_extract_pliegos")
    sections = {"2": "a.1. Vinos blancos, rosados y tintos:\n  a.1.1. Grado alcohólico\n"
                     "a.2. Vinos espumosos de calidad\n  - Grado alcohólico\n"
                     "a.3. Vinos de licor\n"}
    titles = {"2": "DESCRIPCIÓN DEL VINO."}
    styles = set(es02.parse_styles_es(sections, titles))
    assert {"sparkling", "sparkling-quality", "vin-de-liqueur", "fortified"} <= styles


def test_a_white_fermented_on_its_skins_is_read_in_es_hu_de():
    es02 = importlib.import_module("es.02_extract_pliegos")
    titles = {"6": "Descripción del vino o vinos"}
    for body in ("Vino naranja: gama desde el amarillo hasta el naranja.",
                 "Blanco Brisado: Fase visual: tonalidades del amarillo al anaranjado.",
                 "BRISADO: Con tonalidades que pueden ir del amarillo al anaranjado."):
        assert "skin-contact-white" in es02.parse_styles_es({"6": body}, titles)
    huelva = "Vinos generosos. El Vino Naranja del Condado de Huelva se elabora con cáscaras."
    assert "skin-contact-white" not in es02.parse_styles_es({"6": huelva}, titles)
    from _lib.hu import termekleiras
    hu = termekleiras.parse_styles({"description": "Bortípusok: 1. Fehér 2. Narancsbor 3. Rozé"}, {})
    assert "skin-contact-white" in hu
    de02 = importlib.import_module("de.02_extract_pliegos")
    de = de02.parse_styles({"4": "Insbesondere maischevergorene Weißweine können auch orangefarben erscheinen."},
                           {"4": "Beschreibung des Weins"})
    assert "skin-contact-white" in de


def test_es_sweetness_levels_listed_as_types():
    es02 = importlib.import_module("es.02_extract_pliegos")
    descr = {"6": "Descripción del vino o vinos"}
    s = set(es02.parse_styles_es({"6": "Producto vitivinícola Vinos Semisecos, Semidulces y Dulces, "
                                       "blancos, rosados y tintos"}, descr))
    assert {"semi-sweet", "sweet"} <= s and "semi-dry" not in s
    s = set(es02.parse_styles_es({"5": "Vinos blancos, rosados, y tintos jóvenes, semisecos, semidulces y, dulces."},
                                 {"5": "Prácticas vitivinícolas"}))
    assert {"semi-sweet", "sweet"} <= s
    assert "sweet" not in es02.parse_styles_es(
        {"6": "En boca, sabor dulce y taninos dulces, vinos secos."}, descr)
    link = {"8": "Vínculo con la zona geográfica"}
    assert "sweet" not in es02.parse_styles_es(
        {"8": "Los vinos de la IGP Castilla pueden ser secos, semisecos, semidulces y dulces, "
              "los vinos Rosalejo sólo son secos."}, link)
    assert "sweet" not in es02.parse_styles_es(
        {"8": "", "8.3": "Los vinos de la IGP Castilla pueden ser secos, semisecos, semidulces y dulces."},
        {"8": "Descripción del (de los) vínculo(s)", "8.3": "Relación entre las características de la zona"})


def test_ro_reads_the_description_sub_sections_and_article_forms():
    ro02 = importlib.import_module("ro.02_extract_pliegos")
    sections = {"4": "", "4.1": "Vinurile albe au o culoare galben-pai.",
                "4.3": "Vinurile roșii prezintă nuanțe de roșu rubiniu.",
                "8.2": "Vinurile roze au prospețime."}
    titles = {"4": "Descrierea vinului (vinurilor)", "4.1": "Caracteristici analitice",
              "4.3": "Caracteristici fizico-chimice", "8.2": "Detalii privind produsul"}
    # the link (8.2) is not the description
    assert ro02.parse_styles(sections, titles) == ["blanc", "noir"]


# ---- sweetness levels listed as wine types: GR, HU ---------------------------

def test_gr_wine_type_headers_declare_sweet_and_semi_sweet_types():
    from _lib.gr.specifikacija import parse_styles
    zakynthos = {"description": "Οίνος λευκός ξηρός, ημίξηρος, ημίγλυκος, γλυκός Αναλυτικά"}
    assert {"semi-sweet", "sweet"} <= set(parse_styles(zakynthos))
    karditsa = {"description": "Οίνος Ερυθρός ξηρός, ημίξηρος και ημίγλυκος Αναλυτικά"}
    styles = set(parse_styles(karditsa))
    assert "semi-sweet" in styles
    assert "sweet" not in styles
    # a sweet taste in a tasting note is no type
    assert "sweet" not in parse_styles({"description": "Μακρά γλυκιά επίγευση. Στόμα γλυκό."})


def test_hu_sweetness_lists_declare_the_types():
    from _lib.hu.egyseges_dokumentum import sweetness_styles
    assert sweetness_styles("száraz, félédes vagy édes, lágy karakterű") == {"semi-sweet", "sweet"}
    assert sweetness_styles("Száraz, félszáraz, félédes és édes kategóriában") == {
        "semi-sweet", "sweet"}
    assert sweetness_styles("száraz vagy félédes borok") == {"semi-sweet"}
    # a sweetish taste, sweet spices, sweetening: no type
    assert sweetness_styles("édeskés ízérzet, édes fűszerek, musttal történő édesítés") == set()


# ---- a (semi-)sparkling type in any inflection, beside a wine word: GR, CY ----

def test_gr_sparkling_types_in_any_inflection_beside_a_wine_word():
    from _lib.gr.eniaio_engrafo import sparkling_type_styles
    from _lib.gr.specifikacija import parse_styles
    # Arkadia's winemaking section, Ήπειρος's type headers
    assert sparkling_type_styles(
        "Οινοποίηση λευκών και ερυθρωπών ημιαφρωδών οίνων") == {"semi-sparkling"}
    assert sparkling_type_styles("Δ. ΟΙΝΟΣ ΗΜΙΑΦΡΩΔΗΣ 1. Οίνος λευκός ημιαφρώδης ξηρός") == {
        "semi-sparkling"}
    assert sparkling_type_styles("παραγωγής αφρώδους οίνου") == {"sparkling"}
    # a mention with no wine word beside it is no type (Λήμνος)
    assert sparkling_type_styles(
        "ξηρά, αρωματικά λευκά, ενώ δεν λείπουν και δείγματα αφρωδών. Τα ηφαιστειογενή") == set()
    assert "semi-sparkling" in parse_styles(
        {"viticultural_practices": "Η παραγωγή των ημιαφρωδών οίνων ακολουθεί την τεχνική"})


# ---- FR: a "Types de produit" section is the colour section -----------------

def test_fr_types_de_produit_section_routes_as_couleur():
    fr02 = importlib.import_module("02_extract_cahiers")
    bodies = {
        "I": "Seuls peuvent prétendre à l'appellation d'origine contrôlée « Crémant d'Alsace »",
        "II": "L'appellation d'origine contrôlée « Crémant d'Alsace » est réservée aux vins "
              "mousseux blancs\nou rosés.",
        "III": "1°- Aire géographique\n\na) - La récolte des raisins … Colmar, Rouffach",
    }
    titles = {"I": "Nom de l'appellation", "II": "Types de produit",
              "III": "Aires et zones dans lesquelles différentes opérations sont réalisées"}
    routed = fr02.route_sections(bodies, titles)
    assert routed["couleur"] == bodies["II"]
    from _lib.grape_lexicon import parse_styles
    assert {"white", "rose"} <= set(parse_styles(routed["couleur"]))


# ---- IT: the type titles a description is sliced into -----------------------

def test_it_reads_type_titles_and_accented_rose():
    it02 = importlib.import_module("it.02_extract_pliegos")
    sections = {"4": "Franciacorta: spuma fine; colore giallo paglierino.",
                "7": "spuma fine e persistente …",
                "9": "… 7. Varietà di uve da vino Chardonnay B. Pinot bianco B. Pinot nero N."}
    titles = {"4": "Descrizione dei vini:", "7": "Franciacorta Rosé",
              "9": "Franciacorta Rosé Riserva"}
    styles = it02.parse_styles(sections, titles)
    # the description's colour field gives the white, the type titles the rosé
    assert {"blanc", "rose"} <= set(styles)
    # the body of a type section is not read: its "Pinot nero N." gives no red
    assert "noir" not in styles
    from _lib.it.documento_unico import scan_styles
    assert "rose" in scan_styles("Abruzzo spumante rosè metodo classico")


# ---- IT: the head word of the organoleptic colour field ---------------------

def test_it_colour_field_head_word_states_the_colour():
    from _lib.it.documento_unico import scan_styles

    def colours(text):
        return {c for c in scan_styles(text) if c in ("blanc", "noir", "rose")}

    # Franciacorta's base wine, Offida Pecorino: a yellow wine is a white wine
    assert colours("colore: dal giallo paglierino più o meno intenso, fino al giallo dorato") == {
        "blanc"}
    assert colours("Colore: giallo paglierino") == {"blanc"}
    assert colours("colore: dal rubino al granato") == {"noir"}
    # never a reflection, never a pink head (the Vin Santo Occhio di Pernice)
    assert colours("colore: colore rosa intenso con lievi riflessi gialli") == set()
    assert colours("colore: dal rosa all'ambrato") == set()
    assert colours("profumo di frutta a polpa gialla") == set()


def test_es_sweetness_labelling_terms_are_not_wine_types():
    es02 = importlib.import_module("es.02_extract_pliegos")
    descr = {"6": "Descripción del vino o vinos"}
    # Bailén restates the EU sugar-term rule for labelling
    bailen = ("Según el contenido de azúcar, en los vinos con IGP “Bailén” podrán emplearse las "
              "indicaciones seco, semiseco, semidulce y dulce, atendiendo a los siguientes rangos: Secos: …")
    assert not {"sweet", "semi-sweet"} & set(es02.parse_styles_es({"6": bailen}, descr))
    # Castilla y León: a footnote on the analytical table
    cyl = ("Azúcares (g/l) 4 (máx.) 4 (máx.)\n"
           "(*) Según la legislación vigente se podrán denominar: secos, semisecos, semidulces y dulces.")
    assert not {"sweet", "semi-sweet"} & set(es02.parse_styles_es({"6": cyl}, descr))
    # Málaga classes its own wines by their sugar
    malaga = ("Vinos de licor o encabezados, que son aquellos en cuya elaboración se ha adicionado alcohol "
              "vínico, y que en función del contenido final en azúcares pueden denominarse: secos o semisecos, "
              "dulces o semidulces; y entre los que se encuentran los vinos dulces naturales.")
    assert {"sweet", "semi-sweet"} <= set(es02.parse_styles_es({"6": malaga}, descr))
    # a labelling word in the previous sentence does not reach the list (Almansa)
    almansa = ("Los límites establecidos en la legislación aplicable de la UE. "
               "Producto vitivinícola Vinos Semisecos, Semidulces y Dulces, blancos, rosados y tintos")
    assert {"sweet", "semi-sweet"} <= set(es02.parse_styles_es({"6": almansa}, descr))
    # a list in a section title is read on the title alone, and "con mención
    # Roble" before it is a wine type, not a labelling-term rule (Méntrida)
    mentrida = {"2": "Vino Blanco, Vino Blanco con mención Roble, Vino Blanco envejecido en tonel, "
                     "Semisecos, Semidulces y Dulces", "3": "Vino rosado seco, semisecos, semidulces y dulces"}
    assert {"sweet", "semi-sweet"} <= set(es02.parse_styles_es({"2": "x", "3": "y"}, mentrida))
    # Bailén's heading states the types the body's labelling sentence does not
    assert {"sweet", "semi-sweet"} <= set(es02.parse_styles_es(
        {"B.1": bailen, "C.3": "…"}, {"B.1": "Principales características analíticas",
                                     "C.3": "Vinos semisecos, semidulces y dulces"}))
