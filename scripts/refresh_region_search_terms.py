#!/usr/bin/env python3
"""Refresh the region search-term table from Wikidata (CC0).

The map's search box matches the region facet on its native label only
(Μακεδονία, Piemonte, Bayern, Cataluña …), so "Macedonia", "Piedmont",
"Bavaria" or "Catalonia" find nothing. The displayed label stays the
regulator's native form; this table adds extra *search* forms per facet
label — the Wikidata item's en / fr / es / nl labels plus a bounded set of
proper-name aliases — each entry citing the item URL. Nothing is written
from memory: every form comes from the Wikidata API at run time, and the
curator input is the pin table below (facet label → Wikidata item).

    .venv/bin/python scripts/refresh_region_search_terms.py           # rewrite the JSON
    .venv/bin/python scripts/refresh_region_search_terms.py --check   # drift detector
    .venv/bin/python scripts/refresh_region_search_terms.py --verbose # show labels + aliases

Rules applied to every form (see `build_forms`):
  * the four labels are always candidates, ahead of any alias (a trailing
    "(…)" disambiguator is stripped: "Douro (DOC)" → "Douro");
  * an alias is a candidate only when it is a proper-name variant of at most
    three words carrying none of the generic words in `GENERIC_WORDS`, no
    descriptive compound ("Moezelwijn"), at least four letters, no digit,
    comma or period, and no code-like token ("BY", "BaWü");
  * a form whose normalised key equals or is contained in the native label,
    or carries it as whole words ("Lake Balaton"), is dropped — the native
    label already matches; a form that only embeds it inside a longer word
    ("Moselle" for Mosel, "Ribatejo" for Tejo) is a different query and stays;
  * a form equal to another region's native label, or to another country's
    form for a different item, is dropped from every entry involved and
    reported (`COLLISION`) rather than silently kept on one side.

A pin whose item no longer carries the facet label (or an obvious variant of
it) in the native language fails the run — fix the pin, never the JSON.
Writes scripts/_lib/region_search_terms.json (sorted keys, indent 1, UTF-8).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "scripts" / "_lib" / "region_search_terms.json"

API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "open-wine-map/1.0 (mailto:winemap@devloed.com)"
REQUEST_PAUSE_S = 0.3
FORM_LANGS = ("en", "fr", "es", "nl")
LICENSE = "Wikidata, CC0 1.0 — https://creativecommons.org/publicdomain/zero/1.0/"
GENERATED_BY = "scripts/refresh_region_search_terms.py"
MAX_ALIAS_WORDS = 3
MIN_ALIAS_LETTERS = 4

# Words that mark an alias as a descriptive phrase rather than a proper-name
# variant ("Free State of Bavaria", "Région wallonne", "provincie Limburg").
# The brief's list, plus the fr / es / nl equivalents and the wine-scheme
# words the wine-region items carry. Compared on normalised tokens.
GENERIC_WORDS = frozenset(
    """
    state free region province land autonomous community island islands republic
    county district kingdom principality prefecture departement comunidad provincia
    regione bundesland freistaat gewest provincie area zone
    etat libre ile iles isla islas eiland eilanden republique republica republiek
    comte condado graafschap royaume reino koninkrijk principaute principado prinsdom
    vrijstaat gemeenschap communaute comunitat autonome autonoma regio deelstaat
    estado staat country pays canton kanton nation periphery periferia peripherie
    distrito isle isles peninsula peninsule schiereiland
    vorstendom grootvorstendom duchy hertogdom ducado duche groothertogdom
    historique historical historic historica historisch
    wine wines vin vins vino vini vinho vinhos wijn wijnen wein weine vignoble vignobles
    weinbaugebiet weinanbaugebiet anbaugebiet weinbauregion weinregion vinohradnicka
    oblast borvidek borregio dezela vinorodna vinicola viticole wijnstreek wijngebied
    regiao demarcada regiune podgoria vinogradarska regija
    doc vr pdo pgi aop dop igp
    """.split()
)

# Curated pins — the curator input. facet label -> (country or countries,
# native language of the facet label, Wikidata item or None, note). The note
# explains a non-obvious choice, or — for a null pin — why no item is pinned.
# The native-language label of the pinned item must equal the facet label or
# be an obvious variant of it (`label_check`); a mismatch fails the run.
PINS: dict[str, tuple[str | list[str], str, str | None, str]] = {
    # Greece — the traditional geographic divisions, not the 13 administrative
    # regions (Crete the island, Thrace / Macedonia / Epirus the Greek regions,
    # not the wider historical regions shared with neighbours).
    "Νησιά Αιγαίου": ("gr", "el", "Q19543318", "Greek geographic division; Q878481 spans Turkey"),
    "Κρήτη": ("gr", "el", "Q34374", "the island; Q1267522 is the administrative region"),
    "Θράκη": ("gr", "el", "Q1192701", "Thrace (Greece); Q41741 is the wider historical region"),
    "Μακεδονία": ("gr", "el", "Q81734", "Macedonia (Greece); not North Macedonia / the kingdom"),
    "Ήπειρος": ("gr", "el", "Q19543299", "Epirus, Greek geographic region; Q565751 spans Albania"),
    "Στερεά Ελλάδα": ("gr", "el", "Q190600", "traditional region; Q199580 is the admin region"),
    "Θεσσαλία": ("gr", "el", "Q166919", ""),
    "Πελοπόννησος": ("gr", "el", "Q78967", "peninsula / geographic region, en label 'Peloponnese'"),
    "Ιόνια Νησιά": ("gr", "el", "Q170295", "island group; Q1147674 is the administrative region"),
    # Cyprus — the four districts (the PGI areas), not the towns.
    "Πάφος": ("cy", "el", "Q59133", "Paphos District — labelled in the genitive (Επαρχία Πάφου)"),
    "Λεμεσός": ("cy", "el", "Q59150", "Limassol District"),
    "Λάρνακα": ("cy", "el", "Q59153", "Larnaca District"),
    "Λευκωσία": ("cy", "el", "Q59147", "Nicosia District"),
    # Bulgaria — the 5 wine regions carry the names of physical regions.
    "Тракийска низина": ("bg", "bg", "Q1091567", "Upper Thracian Plain; alias Тракийската низина"),
    "Черноморски район": ("bg", "bg", None, "no item for the wine region; Q1142729 is the coast"),
    "Дунавска равнина": ("bg", "bg", "Q1241026", ""),
    "Долината на Струма": ("bg", "bg", None, "no item for the wine region; Q204127 is the river"),
    "Розова долина": ("bg", "bg", "Q768480", ""),
    # Italy — the 20 regioni + the country.
    "Toscana": ("it", "it", "Q1273", ""),
    "Piemonte": ("it", "it", "Q1216", ""),
    "Veneto": ("it", "it", "Q1243", ""),
    "Lombardia": ("it", "it", "Q1210", ""),
    "Emilia-Romagna": ("it", "it", "Q1263", ""),
    "Puglia": ("it", "it", "Q1447", ""),
    "Sardegna": ("it", "it", "Q1462", ""),
    "Campania": ("it", "it", "Q1438", ""),
    "Lazio": ("it", "it", "Q1282", ""),
    "Sicilia": ("it", "it", "Q1460", ""),
    "Calabria": ("it", "it", "Q1458", ""),
    "Umbria": ("it", "it", "Q1280", ""),
    "Marche": ("it", "it", "Q1279", ""),
    "Liguria": ("it", "it", "Q1256", ""),
    "Friuli-Venezia Giulia": ("it", "it", "Q1250", ""),
    "Abruzzo": ("it", "it", "Q1284", ""),
    "Trentino-Alto Adige": ("it", "it", "Q1237", ""),
    "Basilicata": ("it", "it", "Q1452", ""),
    "Molise": ("it", "it", "Q1443", ""),
    "Italia": ("it", "it", "Q38", ""),
    "Valle d'Aosta": ("it", "it", "Q1222", "the regione; Q140130978 is the wine area"),
    # Germany — Anbaugebiet facets pin the wine region item, Bundesland facets
    # (Landwein PGIs) the federal state.
    "Rheinland-Pfalz": ("de", "de", "Q1200", ""),
    "Mosel": ("de", "de", "Q672776", "wine region, not the river Q1667"),
    "Baden": ("de", "de", "Q647902", "wine region, not the historical territory Q6877935"),
    "Bayern": ("de", "de", "Q980", ""),
    "Franken": ("de", "de", "Q153250", "wine region, not the cultural region Q150907"),
    "Württemberg": ("de", "de", "Q166387", "wine region, not the historical state Q159626"),
    "Nahe": ("de", "de", "Q315052", "wine region, not the river Q168696"),
    "Hessen": ("de", "de", "Q1199", ""),
    "Sachsen": ("de", "de", "Q467095", "wine region (Anbaugebiet); the Bundesland is Q1202"),
    "Ahr": ("de", "de", "Q402640", "wine region, not the river Q153394"),
    "Brandenburg": ("de", "de", "Q1208", ""),
    "Hessische Bergstraße": ("de", "de", "Q323855", ""),
    "Saarland": ("de", "de", "Q1201", ""),
    "Sachsen-Anhalt": ("de", "de", "Q1206", ""),
    "Mittelrhein": ("de", "de", "Q464929", "wine region, not the landscape Q571607"),
    "Pfalz": ("de", "de", "Q185439", "wine region, not the historical region Q326359"),
    "Rheingau": ("de", "de", "Q387316", "wine region, not the landscape Q212376"),
    "Rheinhessen": ("de", "de", "Q567327", "wine region, not the region Q707297"),
    "Saale-Unstrut": ("de", "de", "Q683582", ""),
    "Baden-Württemberg": ("de", "de", "Q985", ""),
    # Spain — the autonomous communities + the country.
    "Galicia": ("es", "es", "Q3908", ""),
    "Castilla-La Mancha": ("es", "es", "Q5748", ""),
    "Comunidad Valenciana": ("es", "es", "Q5720", ""),
    "España": ("es", "es", "Q29", ""),
    "Andalucía": ("es", "es", "Q5783", ""),
    "Castilla y León": ("es", "es", "Q5739", "the community; Q5049887 is the Vino de la Tierra"),
    "Cataluña": ("es", "es", "Q5705", ""),
    "Canarias": ("es", "es", "Q5813", ""),
    "Aragón": ("es", "es", "Q4040", ""),
    "Baleares": ("es", "es", "Q107356467", "the community; Q5765 is the archipelago"),
    "Madrid": ("es", "es", "Q5756", "Community of Madrid, not the city Q2807"),
    "Navarra": ("es", "es", "Q4018", ""),
    "Murcia": ("es", "es", "Q5772", "Region of Murcia, not the city Q12225"),
    "La Rioja": ("es", "es", "Q5727", ""),
    "País Vasco": ("es", "es", "Q3995", "the community; Q47588 is the cultural region"),
    "Cantabria": ("es", "es", "Q3946", ""),
    "Asturias": ("es", "es", "Q3934", ""),
    "Extremadura": ("es", "es", "Q5777", "the community; Q5422290 is the Vino de la Tierra"),
    # Portugal — IVV wine regions; the DOC / VR item where one exists under
    # the facet name, else the traditional region the wine region is named for.
    "Minho": ("pt", "pt", "Q374743", "Minho (VR); the former province is Q512317"),
    "Alentejo": ("pt", "pt", "Q20963720", "the geographic region; Q2832668 is the DOC"),
    "Lisboa": ("pt", "pt", "Q207199", "Lisbon District, whose name the VR carries (the VR item "
               "Q3242467 has no Lisbon / Lisbonne / Lissabon label); not the city Q597"),
    "Douro/Porto": ("pt", "pt", "Q1094448", "Douro (DOC); the facet label folds Porto in"),
    "Tejo": ("pt", "pt", "Q140562000", "Do Tejo (DOC), ex-Ribatejo; not the river Q14294"),
    "Algarve": ("pt", "pt", "Q15782399", "the traditional province"),
    "Trás-os-Montes": ("pt", "pt", "Q3541228", "the DOC; the former province is Q2179774"),
    "Açores": ("pt", "pt", "Q25263", ""),
    "Beira Interior": ("pt", "pt", "Q2894017", "Beira Interior (DOC)"),
    "Dão": ("pt", "pt", "Q1269612", "Dão (DOC)"),
    "Madeira": ("pt", "pt", "Q26253", ""),
    "Setúbal": ("pt", "pt", "Q3518577", "Península de Setúbal (VR); not the city / district"),
    "Bairrada": ("pt", "pt", "Q9643639", ""),
    # Austria — the Bundesländer + the country.
    "Niederösterreich": ("at", "de", "Q42497", ""),
    "Burgenland": ("at", "de", "Q43210", ""),
    "Steiermark": ("at", "de", "Q41358", ""),
    "Österreich": ("at", "de", "Q40", ""),
    "Wien": ("at", "de", "Q1741", ""),
    "Kärnten": ("at", "de", "Q37985", ""),
    "Oberösterreich": ("at", "de", "Q41967", ""),
    "Salzburg": ("at", "de", "Q43325", "the Bundesland, not the city Q34713"),
    "Tirol": ("at", "de", "Q42880", "the Bundesland, not the historical region Q153809"),
    "Vorarlberg": ("at", "de", "Q38981", ""),
    # Switzerland — the six Swiss Wine regions: cantons, the Three-Lakes
    # region and German-speaking Switzerland.
    "Genève": ("ch", "fr", "Q11917", "the canton, not the city Q71"),
    "Deutschschweiz": ("ch", "de", "Q689055", ""),
    "Valais": ("ch", "fr", "Q834", ""),
    "Vaud": ("ch", "fr", "Q12771", ""),
    "Trois-Lacs": ("ch", "fr", "Q693912", "Three-Lakes Region (Drei-Seen-Land)"),
    "Ticino": ("ch", "it", "Q12724", "the canton, not the river Q14366"),
    # Hungary — borrégiók; only some have a Wikidata item.
    "Balaton": ("hu", "hu", "Q6383", "the lake; Q4049117 is labelled Balatoni (adjective)"),
    "Felső-Pannon": ("hu", "hu", None, "no item for the Felső-Pannon borrégió"),
    "Duna": ("hu", "hu", "Q1508457", "Duna wine region; the river is Q1653"),
    "Felső-Magyarország": ("hu", "hu", None, "no item; Q999030 is historical Upper Hungary (SK)"),
    "Pannon": ("hu", "hu", "Q4052414", "Pannon wine region; not Roman Pannonia Q170062"),
    "Tokaj": (["hu", "sk"], "hu", "Q828125", "one label, two facets; the Slovak Tokaj is Q1950186"),
    "Zemplén": ("hu", "hu", None, "no item; Q897633 is the Zempléni-hegység range"),
    # Romania — regiuni viticole = the historical regions.
    "Moldova": ("ro", "ro", "Q209754", "Western Moldavia, not the country Q217"),
    "Transilvania": ("ro", "ro", "Q39473", ""),
    "Oltenia": ("ro", "ro", "Q208629", ""),
    "Dobrogea": ("ro", "ro", "Q182660", "Dobruja; Q2673270 is Northern Dobruja"),
    "Crișana și Maramureș": ("ro", "ro", None, "Crișana Q268034 + Maramureș Q10975458; no item"),
    "Banat": ("ro", "ro", "Q170143", ""),
    "Muntenia": ("ro", "ro", "Q207388", ""),
    "Terasele Dunării": ("ro", "ro", None, "no item for the Danube Terraces wine region"),
    # Czechia / Slovakia / Slovenia / Croatia
    "Morava": ("cz", "cs", "Q43266", "Moravia, not the river Q179251"),
    "Čechy": ("cz", "cs", "Q39193", ""),
    "Malokarpatská": ("sk", "sk", "Q1887684", "Malokarpatská vinohradnícka oblasť"),
    "Južnoslovenská": ("sk", "sk", "Q13421176", "Južnoslovenská vinohradnícka oblasť"),
    "Nitrianska": ("sk", "sk", "Q12772543", "Nitrianska vinohradnícka oblasť"),
    "Slovensko": ("sk", "sk", "Q214", ""),
    "Stredoslovenská": ("sk", "sk", "Q12776835", "Stredoslovenská vinohradnícka oblasť"),
    "Východoslovenská": ("sk", "sk", "Q16520436", "Východoslovenská vinohradnícka oblasť"),
    "Posavje": ("si", "sl", "Q19937666", "vinorodna dežela; Q218276 is the Lower Sava valley"),
    "Primorska": ("si", "sl", "Q19937667", "vinorodna dežela; Q125323 is the Slovenian Littoral"),
    "Podravje": ("si", "sl", "Q12805797", "vinorodna dežela; Q856328 is the statistical region"),
    "Primorska Hrvatska": ("hr", "hr", None, "no item; Q1789654 (Croatian Littoral) is narrower"),
    "Zapadna kontinentalna Hrvatska": ("hr", "hr", None, "no item; Q16951229 = continental HR"),
    "Istočna kontinentalna Hrvatska": ("hr", "hr", None, "no item; Q16951229 = continental HR"),
    # Netherlands — the 12 provincies.
    "Gelderland": ("nl", "nl", "Q775", ""),
    "Limburg": ("nl", "nl", "Q1093", "the Dutch province, not the Belgian one Q1095"),
    "Overijssel": ("nl", "nl", "Q773", ""),
    "Drenthe": ("nl", "nl", "Q772", ""),
    "Flevoland": ("nl", "nl", "Q707", ""),
    "Friesland": ("nl", "nl", "Q770", ""),
    "Groningen": ("nl", "nl", "Q752", "the province, not the city Q749"),
    "Noord-Brabant": ("nl", "nl", "Q1101", ""),
    "Noord-Holland": ("nl", "nl", "Q701", ""),
    "Utrecht": ("nl", "nl", "Q776", "the province, not the city Q803"),
    "Zeeland": ("nl", "nl", "Q705", ""),
    "Zuid-Holland": ("nl", "nl", "Q694", ""),
    # Belgium / Luxembourg / Malta / United Kingdom
    "Vlaanderen": ("be", "nl", "Q9337", "Flemish Region; Q234 is the ethnic territory"),
    "Wallonie": ("be", "fr", "Q231", "Walloon Region; Q83078 is the ethnic territory"),
    "Moselle Luxembourgeoise": ("lu", "fr", None, "no item; Q14211572 is en-only, Q1759014 = wine"),
    "Gozo": ("mt", "en", "Q170488", ""),
    "Malta": ("mt", "en", "Q193896", "the island (Malta PDO), not the country Q233"),
    "Maltese Islands": ("mt", "en", "Q3803158", ""),
    "England": ("gb", "en", "Q21", ""),
    "Wales": ("gb", "en", "Q25", ""),
}


def normalize_key(text: str) -> str:
    """NFD, strip combining marks, lower-case, punctuation → space, collapse
    (mirrors `searchNormalize` in app.js / `search_key` in _lib/romanise.py)."""
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    folded = stripped.lower()
    spaced = "".join(ch if ch.isalnum() else " " for ch in folded)
    return " ".join(spaced.split())


def strip_qualifier(label: str) -> str:
    """Drop a trailing parenthesised disambiguator: 'Dão (DOC)' → 'Dão'."""
    return re.sub(r"\s*\([^()]*\)\s*$", "", label).strip()


# A label that describes the entity rather than naming it — "Vignoble de
# Franconie", "Canton of Geneva", "district de Paphos", "Posavska wine
# region" — ships as the bare name: the descriptor is what a query like
# "vignoble" or "district" would otherwise match on five regions at once.
_DESCRIPTOR_PREFIX_RE = re.compile(
    r"^(?:vignobles? (?:de la |de l'|du |des |de )|vins? (?:de la |du |des |de )"
    r"|canton (?:of |de |du |de la |d')|cant[oó]n (?:de |del )|cantone (?:di |del )"
    r"|district (?:of |de |du )|distrito de |region (?:of )|r[ée]gion (?:de |du |de la )"
    r"|regi[oó]n (?:de |del |)|weinbaugebiet |weinregion |wijnstreek |wijngebied "
    r"|pays (?:de |du |des |d'|)|[iî]les? (?:de |d'|)|islas? (?:de |)|isole |eilanden )",
    re.IGNORECASE,
)
_DESCRIPTOR_SUFFIX_RE = re.compile(
    r"\s+(?:wine region|wine-growing region|district|borr[ée]gi[oó]|borvid[ée]k"
    r"|vinohradn[ií]cka oblas[tť]|r[ée]gion viticole|regi[oó]n vin[ií]cola"
    r"|region|community|country|islands?|gewest|eilanden|gemeenschap)$",
    re.IGNORECASE,
)


def strip_descriptor(label: str) -> str:
    """The bare name of a descriptive label ('Vignoble de Franconie' →
    'Franconie', 'Paphos District' → 'Paphos'); unchanged when the label is
    only a descriptor."""
    out = _DESCRIPTOR_SUFFIX_RE.sub("", _DESCRIPTOR_PREFIX_RE.sub("", strip_qualifier(label)))
    out = out.strip(" -")
    return out if out else strip_qualifier(label)


# Wikidata strings that are not names anyone types for a wine region: the
# register's own typos, descriptive nicknames and 1938–45 administrative
# names. Kept out of the table; the item stays the source of the rest.
EXCLUDED_FORMS = frozenset({
    # Wikidata's own typos
    "Centrall Griekenland", "Baden Württenberg", "Baden Wurttenberg", "Deutsche Schweitz",
    "Dodbrudja", "Allentajo", "Voralberg", "Macédoine Egéénne", "Pélopponèse", "Pelloponèse",
    "Peleponesos",
    # demonyms and adjectives, not names
    "Azoriana", "Azoriano", "Cretense", "Kretenzer", "Tesalio", "Tesaliano", "Munteniana",
    "Bohémiens", "Moraves", "Peloponesios", "Peloponesia", "Peloponesíacas", "Peloponesiaco",
    "Peloponesíaca", "Peloponenses", "Peloponesiacos", "Peloponesio", "Peloponense",
    "Peloponesias",
    # descriptive nicknames, 1938–45 names, names in other languages
    "The Mountain", "La Montaña", "Santander", "Niederdonau", "Oberdonau", "Kirid", "Ländle",
    "Hassia", "Hassen",
    # the Azores' historical Dutch name ("Vlaamse Eilanden"): a Dutch visitor
    # typing "vlaams" wants Flanders, not the Azores
    "Vlaamse",
})


# A token ending in one of these is a descriptive compound, not a name
# ("Moezelwijn", "Moezelgebied", "Salzburgerland", "Guelderland").
_COMPOUND_SUFFIXES = (
    "wijn", "wijnen", "wein", "weine", "gebied", "land", "landen", "region", "regio",
)
# Leading articles ignored when two forms are compared ("the Marches" ~ "Marches").
_ARTICLES = frozenset("the la le les l las los el il lo de het der die das den i gli".split())


def is_proper_name_alias(alias: str) -> bool:
    """A proper-name variant: at most three words, no generic or wine-scheme
    word, no descriptive compound, at least four letters, no digit, no
    comma or period (a "Sardinia, Italy" / "Ang." alias is not a name), and
    no code-like token ("BY", "CH-GE", "BaWü")."""
    words = alias.split()
    if not words or len(words) > MAX_ALIAS_WORDS:
        return False
    if any(ch.isdigit() or ch in ",." for ch in alias):
        return False
    letters = [ch for ch in alias if ch.isalpha()]
    if len(letters) < MIN_ALIAS_LETTERS or all(ch.isupper() for ch in letters):
        return False
    for tok in re.split(r"[\s\-–/]+", alias):
        if tok.isupper() and len(tok) <= 3:
            return False
        if any(a.islower() and b.isupper() for a, b in zip(tok, tok[1:])):
            return False
    tokens = normalize_key(alias).split()
    if any(tok in GENERIC_WORDS for tok in tokens):
        return False
    return not any(
        tok.endswith(suf) and len(tok) > len(suf) + 2
        for tok in tokens
        for suf in _COMPOUND_SUFFIXES
    )


def _dedupe_key(text: str) -> str:
    tokens = normalize_key(text).split()
    if len(tokens) > 1 and tokens[0] in _ARTICLES:
        tokens = tokens[1:]
    return " ".join(tokens)


# Inflection folds applied token-wise before comparing a facet label with an
# item label: the Cypriot districts are labelled with the genitive (Επαρχία
# Πάφου ← Πάφος), the Bulgarian plains carry an alias in the definite form
# (Тракийската низина ← Тракийска низина).
_SUFFIX_FOLDS: dict[str, tuple[tuple[str, str], ...]] = {
    "el": (("ου", "ος"), ("ας", "α"), ("ης", "η")),
    "bg": (
        ("ият", ""), ("ата", "а"), ("ото", "о"), ("ите", "и"), ("ът", ""), ("ят", ""), ("та", ""),
    ),
}


def _fold_tokens(tokens: list[str], lang: str) -> list[str]:
    out = []
    for tok in tokens:
        for suffix, repl in _SUFFIX_FOLDS.get(lang, ()):
            if tok.endswith(suffix) and len(tok) > len(suffix) + 2:
                tok = tok[: -len(suffix)] + repl
                break
        out.append(tok)
    return out


def _contains_run(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return bool(needle) and any(
        haystack[i : i + n] == needle for i in range(len(haystack) - n + 1)
    )


def _native_label_check(
    native: str, item_label: str | None, aliases: list[str], lang: str
) -> str:
    """'exact' / 'variant: <surface>' / 'none' for the item's native-language
    label. A variant is: the label up to case, diacritics, punctuation or a
    trailing qualifier; a native-language alias equal to the facet label; the
    facet label as a whole-token run inside the label or an alias (Comunidad
    de Madrid, Vinorodna dežela Posavje, Tokaj-Hegyalja); one part of a
    composite facet label (Douro/Porto); or the same after the inflection
    folds of `_SUFFIX_FOLDS`."""
    if not item_label:
        return "none"
    if item_label.strip().lower() == native.strip().lower():
        return "exact"
    n_tokens = normalize_key(native).split()
    n_folded = _fold_tokens(n_tokens, lang)
    parts = [normalize_key(p) for p in native.split("/")] if "/" in native else []
    for surface in [item_label, *aliases]:
        s_tokens = normalize_key(strip_qualifier(surface)).split()
        s_folded = _fold_tokens(s_tokens, lang)
        if (
            s_tokens == n_tokens
            or _contains_run(s_tokens, n_tokens)
            or _contains_run(s_folded, n_folded)
            or " ".join(s_tokens) in parts
        ):
            return f"variant: {surface}"
    return "none"


def build_forms(
    native: str, labels: dict[str, str], aliases: dict[str, list[str]]
) -> tuple[list[str], list[str]]:
    """(forms, labels): the en / fr / es / nl labels, then the proper-name
    aliases in the same language order, deduped by normalised key (leading
    article ignored), minus anything the native label already matches — and
    the subset of them that are item labels, which a suggestion row may echo.
    A label still carrying a generic word after the descriptor strip is a
    description, not a name, and is dropped like an alias would be."""
    n_key = normalize_key(native)
    n_tokens = n_key.split()
    label_forms = [
        f
        for f in (strip_descriptor(labels[lang]) for lang in FORM_LANGS if labels.get(lang))
        if not any(tok in GENERIC_WORDS for tok in normalize_key(f).split())
    ]
    label_keys = {normalize_key(f) for f in label_forms}
    alias_forms = [
        a
        for lang in FORM_LANGS
        for a in (strip_descriptor(x) for x in aliases.get(lang, []))
        if is_proper_name_alias(a)
    ]
    seen: set[str] = set()
    forms: list[str] = []
    for cand in label_forms + alias_forms:
        key = normalize_key(cand)
        if not key or key == n_key or key in n_key or key in _excluded_keys():
            continue
        # A form that carries the native label as whole words ("Lake Balaton",
        # "Mosel-Saar-Ruwer") adds nothing the native label does not match; one
        # that embeds it inside a longer word ("Moselle", "Ribatejo") is a
        # different query and stays.
        if n_key in key and _contains_run(key.split(), n_tokens):
            continue
        dk = _dedupe_key(cand)
        if dk in seen:
            continue
        seen.add(dk)
        forms.append(cand)
    return forms, [f for f in forms if normalize_key(f) in label_keys]


def _excluded_keys() -> frozenset[str]:
    return frozenset(normalize_key(f) for f in EXCLUDED_FORMS)


# Forms that are a real name of one region but a historical or foreign name
# of another: dropped on that entry only, so the collision guard does not
# take the genuine form away from the region it belongs to ("Flemish Islands"
# is the Azores' old name; "Flemish" must stay on Vlaanderen).
EXCLUDED_BY_REGION: dict[str, frozenset[str]] = {
    "Açores": frozenset({"Flemish", "Vlaamse"}),
}


def fetch_entities(qids: list[str], languages: list[str]) -> dict[str, dict]:
    import requests

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    out: dict[str, dict] = {}
    for i in range(0, len(qids), 50):
        chunk = qids[i : i + 50]
        resp = session.get(
            API,
            params={
                "action": "wbgetentities",
                "ids": "|".join(chunk),
                "props": "labels|aliases",
                "languages": "|".join(languages),
                "format": "json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
        if "error" in payload:
            sys.exit(f"wikidata error: {payload['error']}")
        out.update(payload.get("entities", {}))
        time.sleep(REQUEST_PAUSE_S)
    return out


def _entity_labels(entity: dict) -> tuple[dict[str, str], dict[str, list[str]]]:
    labels = {lang: v["value"] for lang, v in (entity.get("labels") or {}).items()}
    aliases = {
        lang: [a["value"] for a in vals] for lang, vals in (entity.get("aliases") or {}).items()
    }
    return labels, aliases


def build_table(fetched_at: str, verbose: bool = False) -> tuple[dict, list[str]]:
    """Fetch every pinned item and assemble the JSON table. Returns
    (table, problems); problems are pins whose native label no longer
    matches — the caller fails the run on them."""
    qids = sorted({qid for _, _, qid, _ in PINS.values() if qid})
    languages = sorted(set(FORM_LANGS) | {lang for _, lang, _, _ in PINS.values()})
    entities = fetch_entities(qids, languages)
    problems: list[str] = []
    entries: dict[str, dict] = {}
    for native, (country, lang, qid, note) in PINS.items():
        entry: dict = {"country": country, "qid": qid, "fetched_at": fetched_at}
        if qid is None:
            entry.update({"label_check": "none", "forms": [], "reason": note or "no item pinned"})
            entries[native] = entry
            continue
        entity = entities.get(qid)
        if not entity or "missing" in entity:
            problems.append(f"{native}: {qid} not found on Wikidata")
            continue
        labels, aliases = _entity_labels(entity)
        check = _native_label_check(native, labels.get(lang), aliases.get(lang, []), lang)
        if check == "none":
            problems.append(
                f"{native}: {qid} {lang} label {labels.get(lang)!r} does not match "
                f"(aliases {aliases.get(lang, [])})"
            )
        entry["source"] = f"https://www.wikidata.org/wiki/{qid}"
        entry["label_check"] = check
        entry["forms"], entry["labels"] = build_forms(native, labels, aliases)
        rejected = {normalize_key(f) for f in EXCLUDED_BY_REGION.get(native, ())}
        if rejected:
            entry["forms"] = [f for f in entry["forms"] if normalize_key(f) not in rejected]
            entry["labels"] = [f for f in entry["labels"] if normalize_key(f) not in rejected]
        if note:
            entry["note"] = note
        if verbose:
            print(
                f"  {native} [{qid}] {lang}={labels.get(lang)!r} aliases={aliases.get(lang, [])} "
                f"| en={labels.get('en')!r} fr={labels.get('fr')!r} es={labels.get('es')!r} "
                f"nl={labels.get('nl')!r} | alias en={aliases.get('en', [])} "
                f"fr={aliases.get('fr', [])} es={aliases.get('es', [])} nl={aliases.get('nl', [])}",
                file=sys.stderr,
            )
        entries[native] = entry
    problems.extend(_apply_collision_guard(entries))
    for native, entry in entries.items():
        if entry["qid"] and not entry["forms"]:
            entry["forms_empty_reason"] = (
                "every en/fr/es/nl label of the item is the native label "
                "or carries it as whole words"
            )
    table = {"__license__": LICENSE, "__generated_by__": GENERATED_BY}
    table.update(entries)
    return table, problems


def _countries(entry: dict) -> tuple[str, ...]:
    c = entry["country"]
    return tuple(c) if isinstance(c, list) else (c,)


def _apply_collision_guard(entries: dict[str, dict]) -> list[str]:
    """Drop a form that equals another region's native label, or another
    country's form for a different item; report each drop."""
    native_keys = {normalize_key(n): n for n in entries}
    owners: dict[str, list[tuple[str, tuple[str, ...], str | None]]] = {}
    for native, entry in entries.items():
        for form in entry["forms"]:
            owners.setdefault(normalize_key(form), []).append(
                (native, _countries(entry), entry["qid"])
            )
    reports: list[str] = []
    for native, entry in entries.items():
        kept = []
        for form in entry["forms"]:
            key = normalize_key(form)
            if key in native_keys and native_keys[key] != native:
                reports.append(
                    f"COLLISION {native!r}: form {form!r} equals the native label of "
                    f"{native_keys[key]!r} — dropped"
                )
                continue
            clash = [
                o
                for o in owners.get(key, [])
                if o[0] != native
                and o[2] != entry["qid"]
                and not set(o[1]) & set(_countries(entry))
            ]
            if clash:
                reports.append(
                    f"COLLISION {native!r}: form {form!r} also a form of "
                    f"{', '.join(repr(o[0]) for o in clash)} "
                    "(different item, other country) — dropped"
                )
                continue
            kept.append(form)
        entry["forms"] = kept
        entry["labels"] = [f for f in entry.get("labels", []) if f in kept]
    return reports


def read_table(path: Path = OUT_PATH) -> dict[str, dict]:
    """The on-disk table without the `__` metadata keys."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("__")}


def dumps(table: dict) -> str:
    return json.dumps(table, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def _comparable(table: dict) -> dict:
    return {
        k: ({kk: vv for kk, vv in v.items() if kk != "fetched_at"} if isinstance(v, dict) else v)
        for k, v in table.items()
    }


def print_review(table: dict) -> None:
    rows = [(k, v) for k, v in table.items() if not k.startswith("__")]
    width = max(len(k) for k, _ in rows)
    print(f"{'label':<{width}} | {'qid':<10} | {'label_check':<34} | forms")
    print(f"{'-' * width}-+-{'-' * 10}-+-{'-' * 34}-+------")
    for native, entry in rows:
        forms = ", ".join(entry["forms"]) if entry["forms"] else "—"
        qid = entry["qid"] or "null"
        print(f"{native:<{width}} | {qid:<10} | {entry['label_check']:<34} | {forms}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="re-fetch and fail if the JSON drifted")
    ap.add_argument("--verbose", action="store_true", help="print labels and aliases per item")
    args = ap.parse_args(argv)

    table, problems = build_table(date.today().isoformat(), verbose=args.verbose)
    print_review(table)
    for line in problems:
        print(line, file=sys.stderr)
    if any(not p.startswith("COLLISION") for p in problems):
        print("pin problems — fix PINS before writing", file=sys.stderr)
        return 2
    if args.check:
        if not OUT_PATH.exists():
            print(f"{OUT_PATH} missing", file=sys.stderr)
            return 1
        on_disk = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        if _comparable(on_disk) != _comparable(table):
            changed = sorted(
                k for k in set(on_disk) | set(table)
                if _comparable(on_disk).get(k) != _comparable(table).get(k)
            )
            print(f"DRIFT: {len(changed)} entries differ: {changed}", file=sys.stderr)
            return 1
        print("no drift", file=sys.stderr)
        return 0
    OUT_PATH.write_text(dumps(table), encoding="utf-8")
    n = sum(1 for k in table if not k.startswith("__"))
    n_null = sum(1 for k, v in table.items() if not k.startswith("__") and v["qid"] is None)
    print(
        f"wrote {OUT_PATH.relative_to(ROOT)}: {n} labels, {n_null} without an item",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
