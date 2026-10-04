"""Regression + behaviour tests for the FR cahier des charges parser
(`scripts/02_extract_cahiers.py`).

Covers the pure text helpers (slug / normalize_name / candidate_keys /
parse_communes) and the section-slicer `extract_sections`, including the two
latent regex bugs fixed in commit f1ad98c that silently dropped section X
("Lien au terroir"):

  1. CHAPITRE_RE was case-insensitive, so a line-wrapped body reference like
     "...visé au\nchapitre II du présent cahier..." matched and truncated the
     body early, losing sections VIII–XII. The fix made it case-sensitive.
  2. SECTION_HDR_RE's leading-whitespace class lacked \x0c, so a Roman-numeral
     heading landing right after a pdftotext page break (\x0c) failed to match.
     The fix added \x0c to the class.

These use small synthetic segments rather than raw fixtures — the behaviours
under test are about regex routing, which is exercised precisely by minimal
crafted input.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import importlib

# 02_extract_cahiers starts with a digit, so it can't be imported by name.
extract = importlib.import_module("02_extract_cahiers")


# --------------------------------------------------------------------------
# Pure text helpers
# --------------------------------------------------------------------------

def test_slug_basic_and_diacritics():
    assert extract.slug("Côte de Nuits-Villages") == "cote-de-nuits-villages"
    assert extract.slug("Châteauneuf-du-Pape") == "chateauneuf-du-pape"
    assert extract.slug("  Édge   Cäse!! ") == "edge-case"


def test_normalize_name_strips_punctuation_and_case():
    # Same loose key regardless of spacing / hyphen / diacritics / case.
    assert extract.normalize_name("Saint-Émilion") == extract.normalize_name("saint emilion")
    assert extract.normalize_name("Côtes du Rhône") == "cotesdurhone"


def test_candidate_keys_splits_aliases():
    # "ou" / "et" / comma aliases each yield a match key, full form first.
    keys = extract.candidate_keys("Cidre de Normandie ou Cidre normand")
    assert keys[0] == extract.normalize_name("Cidre de Normandie ou Cidre normand")
    assert extract.normalize_name("Cidre normand") in keys
    assert extract.normalize_name("Cidre de Normandie") in keys


def test_candidate_keys_comma_and_et_list():
    keys = extract.candidate_keys("Côtes de Bourg, Bourg et Bourgeais")
    assert extract.normalize_name("Côtes de Bourg") in keys
    assert extract.normalize_name("Bourg") in keys
    assert extract.normalize_name("Bourgeais") in keys


# --------------------------------------------------------------------------
# parse_communes
# --------------------------------------------------------------------------

def test_parse_communes_top_level_separators():
    out = extract.parse_communes("Commune A, Commune B et Commune C")
    assert out == ["Commune A", "Commune B", "Commune C"]


def test_parse_communes_keeps_parenthetical_commas_attached():
    field = (
        "Le Controis-en-Sologne (pour le territoire des communes déléguées de "
        "Feings, Fougères-sur-Bièvre et Ouchamps), Cheverny"
    )
    out = extract.parse_communes(field)
    assert len(out) == 2
    assert out[0].startswith("Le Controis-en-Sologne (")
    assert out[0].endswith(")")
    assert out[1] == "Cheverny"


def test_parse_communes_reglues_soft_wrapped_hyphen():
    # pdftotext leaves "Saint-\n Claude" -> "Saint- Claude"; must re-glue.
    out = extract.parse_communes("Saint- Claude-de-Diray, Candé-sur-Beuvron")
    assert out == ["Saint-Claude-de-Diray", "Candé-sur-Beuvron"]


# --------------------------------------------------------------------------
# extract_sections — section slicing + the f1ad98c regressions
# --------------------------------------------------------------------------

def _wrap(body: str) -> str:
    """Wrap section body text in the CHAPITRE Ier envelope extract_sections
    expects, plus a CHAPITRE II so the slicer keeps only chapter I."""
    return (
        "CHAPITRE Ier\n"
        + body
        + "\nCHAPITRE II - OBLIGATIONS DÉCLARATIVES\n"
        "Some declaration boilerplate that must be excluded.\n"
    )


def test_extract_sections_basic_routing():
    seg = _wrap(
        "I. - Nom de l'appellation\n"
        "Coulée de Serrant.\n"
        "IV. - Aire géographique\n"
        "La récolte des raisins est assurée sur la commune de Savennières.\n"
        "X. - Lien au terroir\n"
        "Le vignoble s'étend sur des coteaux schisteux.\n"
    )
    bodies, titles = extract.extract_sections(seg)
    assert set(bodies) >= {"I", "IV", "X"}
    assert "schisteux" in bodies["X"]
    assert "Lien au terroir" in titles["X"]
    # CHAPITRE II content must be excluded.
    assert "declaration boilerplate" not in bodies["X"]


def test_extract_sections_header_after_page_break():
    # Regression 2: a \x0c page break immediately before the X heading must
    # NOT prevent the heading from matching.
    seg = _wrap(
        "IX. - Mesures transitoires\n"
        "Néant.\n"
        "\x0cX. - Lien au terroir\n"
        "Les sols argilo-calcaires confèrent au vin sa minéralité.\n"
    )
    bodies, _titles = extract.extract_sections(seg)
    assert "X" in bodies, "section X heading after \\x0c page break was dropped"
    assert "minéralité" in bodies["X"]


def test_extract_sections_lowercase_chapitre_in_body_does_not_truncate():
    # Regression 1: a line-wrapped lowercase "chapitre" reference inside a
    # section body must not be treated as a CHAPITRE boundary and truncate the
    # remaining sections.
    seg = _wrap(
        "IV. - Aire géographique\n"
        "La récolte est assurée dans l'aire définie au\n"
        "chapitre II du présent cahier des charges.\n"
        "X. - Lien au terroir\n"
        "Terroir de coteaux exposés au sud.\n"
    )
    bodies, _titles = extract.extract_sections(seg)
    assert "X" in bodies, "lowercase body 'chapitre' truncated the segment early"
    assert "coteaux exposés au sud" in bodies["X"]


# ----- extract_aire: section IV sub-block headers + sentence-form aires -----
#
# Pouilly-Loché's 2024 PNOCDC writes "1 - Aire géographique" (no degree
# sign) and defines the aire as a sentence ("… sur le territoire de la
# commune de Mâcon du département de Saône-et-Loire") instead of a
# "Département de X :" list. Before the fix the block split missed, the
# whole section was scanned, and the aire de proximité immédiate list
# (366 Burgundy communes) was recorded as the aire géographique — which
# drew the AOC across all of Burgundy in the simple-mode map.


def test_extract_aire_degree_less_header_keeps_proximity_out_of_aire():
    iv = (
        "1 - Aire géographique\n\n"
        "La récolte des raisins, la vinification, l’élaboration et l’élevage des vins "
        "d’appellation d’origine\ncontrôlée « Pouilly-Loché » sont assurés sur le territoire "
        "de la commune de Mâcon du département de\nSaône-et-Loire.\n\n"
        "2 - Aire parcellaire délimitée\n\n"
        "Les vins sont issus exclusivement de vignes situées dans l’aire parcellaire.\n\n"
        "3 - Aire de proximité immédiate\n\n"
        "L’aire de proximité immédiate est constituée par le territoire des communes suivantes :\n"
        "- Département de la Côte-d’Or : Agencourt, Aloxe-Corton\n"
        "- Département du Rhône : Anse, Belleville\n"
    )
    aire = extract.extract_aire(iv)
    assert aire["aire_geographique"] == {"Saône-et-Loire": ["Mâcon"]}
    assert aire["aire_proximite_immediate"] == {
        "Côte-d’Or": ["Agencourt", "Aloxe-Corton"],
        "Rhône": ["Anse", "Belleville"],
    }


def test_extract_aire_sentence_form_multi_commune_two_departements():
    iv = (
        "1° - Aire géographique\n\n"
        "La récolte est assurée sur le territoire des communes de Chablis,\nPoinchy et Fyé "
        "du département de l’Yonne et des communes de Dijon du département de la Côte-d’Or.\n\n"
        "2° - Aire parcellaire délimitée\n\nx\n"
    )
    aire = extract.extract_aire(iv)
    assert aire["aire_geographique"] == {
        "Yonne": ["Chablis", "Poinchy", "Fyé"],
        "Côte-d’Or": ["Dijon"],
    }
    assert aire["aire_proximite_immediate"] == {}


def test_extract_aire_classic_degree_header_unchanged():
    iv = (
        "1° - Aire géographique\n\n- Département de la Marne : Reims, Épernay\n\n"
        "2° - Aire parcellaire délimitée\n\nx\n\n"
        "3° - Aire de proximité immédiate\n\n- Département de l’Aube : Troyes\n"
    )
    aire = extract.extract_aire(iv)
    assert aire["aire_geographique"] == {"Marne": ["Reims", "Épernay"]}
    assert aire["aire_proximite_immediate"] == {"Aube": ["Troyes"]}


def test_extract_aire_list_form_wins_over_sentence_form_in_same_block():
    # A block that carries a "Département de X :" list must not ALSO pick up
    # a stray sentence mention — the sentence fallback only runs when the
    # list form found nothing.
    iv = (
        "1° - Aire géographique\n\n"
        "Les vins proviennent des communes de Nuits du département de la Côte-d’Or.\n"
        "- Département de la Côte-d’Or : Nuits-Saint-Georges, Premeaux-Prissey\n\n"
        "2° - Aire parcellaire délimitée\n\nx\n"
    )
    aire = extract.extract_aire(iv)
    assert aire["aire_geographique"] == {"Côte-d’Or": ["Nuits-Saint-Georges", "Premeaux-Prissey"]}


def test_aire_block_header_requires_a_marker():
    # "3 communes …" starts with a digit but carries no ° / dash / paren, so
    # it must not open a sub-block and split a commune list in two.
    import re

    pat = re.compile(extract._AIRE_BLOCK_HEADER_PATTERN, re.MULTILINE)
    assert pat.search("1° - Aire géographique")
    assert pat.search("1°- Aire parcellaire délimitée")
    assert pat.search("1 - Aire géographique")
    assert pat.search("2 – Aire parcellaire délimitée")
    assert pat.search("1) Aire géographique")
    assert not pat.search("3 communes du département")
    assert not pat.search("12 - Aire géographique")


def test_extract_aire_sentence_form_drops_lowercase_asides():
    iv = (
        "1° Aire géographique :\n\nLa récolte des raisins est assurée sur le territoire de\n"
        "la commune de Barsac, sur la base du code officiel géographique en date du 1er janvier 2025, "
        "dans le\ndépartement de la Gironde.\n\n2° Aire parcellaire délimitée :\n\nx\n"
    )
    assert extract.extract_aire(iv)["aire_geographique"] == {"Gironde": ["Barsac"]}
    iv2 = (
        "1°- Aire géographique\n\nLes vins sont assurés sur le territoire de\nla commune de Loupiac, "
        "située dans le département de la Gironde.\n\n2°- Aire parcellaire délimitée\n\nx\n"
    )
    assert extract.extract_aire(iv2)["aire_geographique"] == {"Gironde": ["Loupiac"]}


# --------------------------------------------------------------------------
# Homologation date — the header forms INAO actually prints (2026-10-04)
# --------------------------------------------------------------------------

def test_homologation_date_reads_the_article_less_and_typo_forms():
    assert extract.homologation_date(
        "Cahier des charges de l'AOC « X »\nhomologué par arrêté du 29 décembre 2025, publié au JORF\n"
    ) == "2025-12-29"
    # INAO's own typo on the Montpeyroux cahier of 2026.
    assert extract.homologation_date(
        "« MONTPEYROUX »\nHomologué pa l’arrêté du 11 août 2026, publié au JORF du 15 août 2026\n"
    ) == "2026-08-11"
    assert extract.homologation_date(
        "homologué par l’arrêté du 1er septembre 2025, publié au JORF du 5 septembre 2025"
    ) == "2025-09-01"
    assert extract.homologation_date(
        "homologué par le décret n° 2011-1684 du 28 novembre 2011, JORF du 30 novembre 2011"
    ) == "2011-11-28"
    assert extract.homologation_date("CHAPITRE Ier\nI. - Nom de l'appellation\n") is None


def test_homologation_date_falls_back_to_the_cover_line_before_the_segment():
    before = (
        "Publié au BO du MASA du jeudi 18 septembre 2025\n"
        "Cahier des charges de l’appellation d’origine contrôlée « CHABLIS »\n"
        "homologué par l’arrêté du 10 septembre 2025 publié au JORF du 12 septembre 2025.\n"
    )
    segment = "CAHIER DES CHARGES DE L’APPELLATION D’ORIGINE CONTRÔLÉE « CHABLIS »\nCHAPITRE Ier\n"
    assert extract.homologation_date(segment) is None
    assert extract.homologation_date(segment, before) == "2025-09-10"
    text = before + segment
    assert extract._text_before(text, segment) == before
    assert extract._text_before(text, text) == ""


def test_parse_appellation_header_accepts_arrete_without_article():
    hdr = extract.parse_appellation_header(
        "Homologué pa l’arrêté du 11 août 2026, publié au JORF du 15 août 2026\nCHAPITRE Ier\n"
    )
    assert hdr["homologation_type"] == "arrêté"
    assert hdr["homologation_date"] == "11 août 2026"
    assert hdr["jorf_date"] == "15 août 2026"


# --------------------------------------------------------------------------
# Unnumbered headings — the 2024 Saumur layout
# --------------------------------------------------------------------------

_UNNUMBERED = """CAHIER DES CHARGES DE L’APPELLATION D’ORIGINE CONTRÔLÉE « SAUMUR »
                        CHAPITRE Ier
                        Nom de l’appellation
Seuls peuvent prétendre à l’appellation « Saumur » les vins ci-après.
            Dénominations géographiques et mentions complémentaires
1°- Le nom peut être complété par « Val de Loire ».
                      Couleurs et types de produit
1°- L’appellation est réservée aux vins tranquilles blancs, rosés et rouges.
        Aires et zones dans lesquelles différentes opérations sont réalisées
1°- Aire géographique
Département de la Vienne : Berrie, Saix.
                            Encépagement
1°- Encépagement
- cépages principaux : chenin B, cabernet franc N.
                        Conduite du vignoble
1°- Modes de conduite
                   Lien avec la zone géographique
1°- Informations sur la zone géographique
Le vignoble s’étend sur les coteaux du Thouet.
                       Mesures transitoires
Néant.
                        CHAPITRE II
                        I. - Obligations déclaratives
"""


def test_unnumbered_titles_are_numbered_by_canonical_position():
    bodies, titles = extract.extract_unnumbered_sections(_UNNUMBERED)
    assert list(bodies) == ["I", "II", "III", "IV", "V", "VI", "X", "XI"]
    assert titles["X"] == "Lien avec la zone géographique"
    assert "coteaux du Thouet" in bodies["X"]
    assert "cabernet franc" in bodies["V"]
    # the "1°- Encépagement" sub-block line is not a heading
    assert bodies["V"].lstrip().startswith("1°- Encépagement")
    # CHAPITRE II is cut off
    assert "Obligations" not in bodies["XI"]


def test_extract_one_reads_the_unnumbered_layout_and_leaves_the_roman_one_alone():
    rec = extract.extract_one("Saumur", _UNNUMBERED)
    assert rec is not None and rec["kind"] == "AOC"
    assert "coteaux du Thouet" in rec["lien_au_terroir"]
    assert rec["aire"]["aire_geographique"] == {"Vienne": ["Berrie", "Saix"]}
    roman = _UNNUMBERED.replace("                        Nom de l’appellation", "I. - Nom de l’appellation") \
        .replace("            Dénominations géographiques et mentions complémentaires", "II. - Dénominations géographiques et mentions complémentaires") \
        .replace("                      Couleurs et types de produit", "III. - Couleurs et types de produit") \
        .replace("        Aires et zones dans lesquelles différentes opérations sont réalisées", "IV. - Aires et zones dans lesquelles différentes opérations sont réalisées") \
        .replace("                            Encépagement", "V. - Encépagement") \
        .replace("                        Conduite du vignoble", "VI. - Conduite du vignoble") \
        .replace("                   Lien avec la zone géographique", "X. - Lien avec la zone géographique") \
        .replace("                       Mesures transitoires", "XI. - Mesures transitoires")
    bodies, _ = extract.extract_sections(roman)
    assert len(bodies) == 8
    assert extract.extract_one("Saumur", roman)["sections"].keys() == bodies.keys()


# --------------------------------------------------------------------------
# 2026-10-04: table label column, proximity sentence, whole département,
# page-break lists, the 2026 eau-de-vie template
# --------------------------------------------------------------------------

_TABLE_IV = """1°- Aire géographique

Toutes les étapes de la production ont lieu dans les aires géographiques dont le périmètre englobe le territoire
des communes suivantes, sur la base du code officiel géographique de 2023 :

COULEUR DES VINS,
TYPE DE VIN,
DENOMINATION                                                  COMMUNES
GEOGRAPHIQUE
COMPLEMENTAIRE
Publié au BO du MASA le 25 janvier 2024



                               Département des Deux-Sèvres : Saint-Martin-de-Mâcon, Tourtenay
                           Département de Maine-et-Loire : Artannes-sur-Thouet, Brossay,
                           Doué-en-Anjou (pour le seul territoire des communes déléguées de Doué-la-
Vins tranquilles blancs et Fontaine, Forges, Meigné et Les Verchers-sur-Layon), Épieds, Fontevraud-
rosés                      l'Abbaye, Montreuil-Bellay, Saumur
                               Département de la Vienne : Berrie, Saix

                               Département des Deux-Sèvres : Saint-Martin-de-Mâcon, Tourtenay
                               Département de Maine-et-Loire : Artannes-sur-Thouet, Brossay, Épieds,
Vins tranquilles rouges
                               Fontevraud-l'Abbaye, Montreuil-Bellay, Saumur
                               Département de la Vienne : Berrie, Saix

Dénomination                   Département de Maine-et-Loire : Brossay, Épieds
géographique
complémentaire
« Puy-Notre-Dame »             Département de la Vienne : Berrie, Saix

3°- Aire de proximité immédiate

L’aire de proximité immédiate, définie par dérogation pour la vinification, est constituée par le territoire
des communes suivantes :

COULEUR DES VINS,
TYPE DE VIN,
DENOMINATION                                                    COMMUNES
GEOGRAPHIQUE
COMPLEMENTAIRE

                                 Département d’Indre-et-Loire : Saint-Nicolas-de-Bourgueil
Vins tranquilles blancs et
rosés                            Département de la Loire-Atlantique : Ancenis-Saint-Géréon
"""


def test_table_label_column_is_cut_and_rows_deduplicated():
    aire = extract.extract_aire(_TABLE_IV)
    geo = aire["aire_geographique"]
    assert geo["Deux-Sèvres"] == ["Saint-Martin-de-Mâcon", "Tourtenay"]
    assert geo["Maine-et-Loire"] == [
        "Artannes-sur-Thouet", "Brossay",
        "Doué-en-Anjou (pour le seul territoire des communes déléguées de Doué-la-Fontaine, "
        "Forges, Meigné et Les Verchers-sur-Layon)",
        "Épieds", "Fontevraud-l'Abbaye", "Montreuil-Bellay", "Saumur",
    ]
    assert geo["Vienne"] == ["Berrie", "Saix"]
    prox = aire["aire_proximite_immediate"]
    assert prox == {"Indre-et-Loire": ["Saint-Nicolas-de-Bourgueil"],
                    "Loire-Atlantique": ["Ancenis-Saint-Géréon"]}
    flat = " ".join(c for d in (geo, prox) for cs in d.values() for c in cs)
    assert "Vins" not in flat and "rosés" not in flat and "Dénomination" not in flat


def test_dgc_table_without_blank_rows_keeps_only_the_commune_column():
    text = """c) - Pour les dénominations géographiques complémentaires suivantes :

     DÉNOMINATIONS GÉOGRAPHIQUES
                                                                     LISTE DES COMMUNES
          COMPLEMENTAIRES
 Dénomination géographique complémentaire
                                                         Département de l’Hérault : Cabrières.
 « Cabrières »
 Dénomination géographique complémentaire                Département de l’Hérault : Castelnau-le-Lez,
 « La Méjanelle »                                        Mauguio, Montpellier et Saint-Aunès.
 Dénomination géographique complémentaire
 « Pézenas » :
 - Aire géographique de production telle
 qu’approuvée par l’Institut national de l’origine et    Département de l’Hérault : Adissan, Aspiran,
 de la qualité lors de la séance du comité national      Caux.
"""
    out = extract.strip_table_label_column(text)
    assert "Dénomination" not in out and "Pézenas" not in out and "qu’approuvée" not in out
    geo = extract.extract_aire("COULEUR DES VINS\nCOMMUNES\n" + text)["aire_geographique"]
    assert geo == {"Hérault": ["Cabrières", "Castelnau-le-Lez", "Mauguio", "Montpellier", "Saint-Aunès",
                               "Adissan", "Aspiran", "Caux"]}


def test_plain_layout_is_left_alone_by_the_table_strip():
    text = "Département du Rhône : Anse, Lachassagne,\nMarcy.\n\n    centred note\n"
    assert extract.strip_table_label_column(text) == text


_IGP_4 = """La récolte des raisins, la vinification et l’élaboration des vins bénéficiant de l’indication
géographique protégée « Côtes du Lot » sont réalisées dans le département du Lot.

La récolte des raisins destinés à l’élaboration des vins bénéficiant de l’indication géographique
protégée « Côtes du Lot » complétée du nom de l’unité géographique « Rocamadour » est
réalisée sur le territoire de la commune de Rocamadour dans le département du Lot.

La zone de proximité immédiate définie par dérogation pour la vinification et l’élaboration des
vins bénéficiant de l’indication géographique protégée « Côtes du Lot » est constituée par les
cantons limitrophes de la zone géographique suivants :
- dans le département du Lot-et-Garonne : Fumel et Tournon-d'-Agenais ;
- dans le département du Tarn-et-Garonne : Lauzerte, Molières, Montaigu-de-Quercy et
   Montpezat-de-Quercy.
"""


def test_proximity_sentence_is_the_proximity_zone_and_the_departement_is_the_aire():
    aire = extract.extract_aire(_IGP_4)
    assert aire["aire_geographique"] == {}
    assert aire["aire_departements"] == ["Lot"]
    assert aire["aire_proximite_immediate"] == {
        "Lot-et-Garonne": ["Fumel", "Tournon-d'-Agenais"],
        "Tarn-et-Garonne": ["Lauzerte", "Molières", "Montaigu-de-Quercy", "Montpezat-de-Quercy"],
    }


def test_whole_departements_read_the_regulators_phrasings():
    w = extract.whole_departements
    assert w("La récolte des raisins, la vinification et l’élaboration des vins sont réalisées dans les "
             "départements du Doubs, de la Haute-Saône, du Territoire de Belfort,\net du Jura, à l’exception "
             "des communes de Arbois, Arlay.") == ["Doubs", "Haute-Saône", "Territoire de Belfort", "Jura"]
    assert w("La production des raisins, la vinification et l’élaboration des vins sont réalisées dans le "
             "département du Gard.") == ["Gard"]
    assert w("La récolte des raisins … sont réalisées sur la totalité du territoire du département de la "
             "Drôme correspondant aux communes suivantes :") == ["Drôme"]
    assert w("La récolte des raisins … sont réalisées dans les départements des Alpes de Haute Provence,\n"
             "Hautes-Alpes, Var, Haute-Corse ainsi que sur le territoire des communes suivantes :") == [
        "Alpes-de-Haute-Provence", "Hautes-Alpes", "Var", "Haute-Corse"]
    assert w("- l’ensemble des communes des départements de l’Aude, de l’Hérault, du Gard et des Pyrénées-\n"
             "Orientales ;") == ["Aude", "Hérault", "Gard", "Pyrénées-Orientales"]
    assert w("La récolte … sont réalisées dans le département de Lot-et-Garonne à l’exclusion des communes "
             "de Bourlens, Courbiac.") == ["Lot-et-Garonne"]
    # a storage rule or a commune list is not the aire
    assert w("Le stockage et la distillation des marcs doivent être réalisés dans les départements du "
             "Haut-Rhin et du Bas-Rhin.") == []
    assert w("La récolte des raisins est assurée sur le territoire des communes suivantes du département "
             "de la Gironde : Pauillac.") == []


def test_list_after_a_blank_line_and_a_count_token_are_read():
    text = ("Département de l’Ardèche : 96 communes\n\nAlboussière, Andance, Annonay.\n\n"
            "Département de la Meuse :\n\nBilly-sous-les-Côtes, Buxerulles, Creuë.\n")
    geo = extract.extract_aire(text)["aire_geographique"]
    assert geo == {"Ardèche": ["Alboussière", "Andance", "Annonay"],
                   "Meuse": ["Billy-sous-les-Côtes", "Buxerulles", "Creuë"]}
    prose = "Département de la Meuse :\n\nLa zone est définie par le présent cahier, sans liste.\n"
    assert extract.extract_aire(prose)["aire_geographique"] == {}


def test_bo_page_header_inside_a_list_does_not_cut_it():
    text = ("Département du Haut-Rhin :\nAmmerschwihr, Houssen,\n\x0cPublié au BO Agri du MAASA le 10 "
            "septembre 2026\n\nHunawihr, Zimmerbach.\n")
    assert extract.extract_aire(text)["aire_geographique"] == {
        "Haut-Rhin": ["Ammerschwihr", "Houssen", "Hunawihr", "Zimmerbach"]}


_EDV_2026 = """Cahier des charges de l’appellation d’origine contrôlée « Marc d’Alsace » suivie de la dénomination
« Gewurztraminer » homologué par arrêté du 2 septembre 2026, publié au JORF du 5 septembre 2026

Chapitre Ier : Conditions de production et lien à l’origine

1. - Nom de l’appellation

Seules peuvent prétendre à l’appellation d’origine contrôlée « Marc d’Alsace » les eaux-de-vie.

2. - Description de la boisson spiritueuse

Eau-de-vie de marc de raisin, Annexe I, point 6 du Règlement (UE) 2019/787.

2.1° Caractéristiques physiques

Les eaux-de-vie ne présentent aucune coloration.

3. - Définition de la zone géographique concernée

3.1° Aire géographique :

Les marcs proviennent de raisins récoltés et vinifiés sur les communes suivantes :

Département du Haut-Rhin :
Ammerschwihr, Beblenheim.

Département du Bas-Rhin :
Albé, Andlau.

4. - Description de la méthode d’obtention

4.1° Matière première

Le raisin mis en œuvre provient du cépage gewurztraminer Rs.

4.2° Distillation

Les alambics de type « Holstein » sont autorisés.

5. - Lien à l’origine géographique

5.1° Spécificité de l’aire géographique

1. Description des facteurs du lien au terroir

a) Facteurs naturels
Cette aire bénéficie d’un climat de type semi-continental.

2. Eléments historiques concernant les facteurs du lien au terroir

L’introduction du cépage remonte à la fin du XIXème siècle.

6. - Règles de présentation et d’étiquetage

Le nom de cépage doit être inscrit sur les étiquettes.

Chapitre II : Obligations déclaratives et tenue de registres

1. Obligations déclaratives

Déclaration d’ouverture des travaux de distillation.

Chapitre III

1. - Principaux point à contrôler et méthodes d’évaluation

               A. - RÈGLES STRUCTURELLES

 Aire de stockage                     Contrôle sur site

                 B. - RÈGLES ANNUELLES

                      Période de repos                Examen documentaire

                       C. – PRODUIT

        Caractéristiques analytiques du produit fini                          Examen analytique
"""


def test_2026_eau_de_vie_template_is_read_as_a_spirit_with_aire_lien_and_grape():
    rec = extract.extract_one("Marc d'Alsace Gewurztraminer", _EDV_2026)
    assert rec["kind"] == "EDV"
    assert list(rec["sections"]) == ["1", "2", "3", "4", "5", "6"]
    assert rec["section_titles"]["5"] == "Lien à l’origine géographique"
    assert "semi-continental" in rec["lien_au_terroir"] and "XIXème" in rec["lien_au_terroir"]
    assert "étiquettes" not in rec["lien_au_terroir"]
    assert rec["aire"]["aire_geographique"] == {"Haut-Rhin": ["Ammerschwihr", "Beblenheim"],
                                                "Bas-Rhin": ["Albé", "Andlau"]}
    enc = rec["section_roles"]["encepagement"]
    assert "gewurztraminer Rs" in enc and "Holstein" not in enc
    grapes = extract.parse_grapes(enc)
    assert [t["slug"] for t in grapes["all"]] == ["gewurztraminer"]
    assert extract.is_grape_spirit("Eaux-de-vie de marc de raisin")
    assert not extract.is_grape_spirit("Eaux-de-vie de cidre")
