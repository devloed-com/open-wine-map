"""Geographic exonyms the translation layer must use.

The 02e rule keeps names verbatim, but a mountain range, river, sea or
region *used as a place* takes the target language's established name
(Vosges → Vogezen, Rhin → Rijn, Appennino → Apennines; English wine
writing keeps Mosel and Tejo for the regions, so those carry no English
form) — found by Boris
on the Dutch Alsace pages, 2026-09-11. `EXONYMS` maps each source form
to its target form per locale; `exonym_hits` flags a translated bullet
that still carries the source form.

Many region names double as appellation names (Toscana IGT, Bourgogne,
Wien DAC, Steiermark); those are correct verbatim as labels and wrong as
places, and only the model can tell. The detector therefore treats the
two classes differently: a form that never appears in a GI name is
flagged on any whole-word occurrence; a form that does is flagged only
when no appellation marker sits next to it and it is not part of a grape
or institution name (Melon de Bourgogne, Junta de Andalucía). The
detector scopes a re-translation; it never rewrites anything.
"""

from __future__ import annotations

import re

EXONYMS: dict[str, dict[str, str]] = {
    "Vosges": {"nl": "Vogezen", "es": "Vosgos"},
    "Rhin": {"nl": "Rijn", "en": "Rhine", "es": "Rin"},
    "Rhein": {"nl": "Rijn", "en": "Rhine", "es": "Rin", "fr": "Rhin"},
    "Pyrénées": {"nl": "Pyreneeën", "en": "Pyrenees", "es": "Pirineos"},
    "Pirineos": {"nl": "Pyreneeën", "en": "Pyrenees", "fr": "Pyrénées"},
    "Méditerranée": {"nl": "Middellandse Zee", "en": "Mediterranean", "es": "Mediterráneo"},
    "Mediterraneo": {"nl": "Middellandse Zee", "en": "Mediterranean", "fr": "Méditerranée", "es": "Mediterráneo"},
    "Atlantique": {"nl": "Atlantische Oceaan", "en": "Atlantic", "es": "Atlántico"},
    "Atlantico": {"nl": "Atlantische Oceaan", "en": "Atlantic", "fr": "Atlantique"},
    "Adriatico": {"nl": "Adriatische Zee", "en": "Adriatic", "fr": "Adriatique", "es": "Adriático"},
    "Tirreno": {"nl": "Tyrreense Zee", "en": "Tyrrhenian", "fr": "Tyrrhénienne", "es": "Tirreno"},
    "Appennino": {"nl": "Apennijnen", "en": "Apennines", "fr": "Apennins", "es": "Apeninos"},
    "Appennini": {"nl": "Apennijnen", "en": "Apennines", "fr": "Apennins", "es": "Apeninos"},
    "Massif Central": {"nl": "Centraal Massief", "es": "Macizo Central"},
    "Alpes": {"nl": "Alpen", "en": "Alps"},
    "Alpi": {"nl": "Alpen", "en": "Alps", "fr": "Alpes", "es": "Alpes"},
    "Alpen": {"en": "Alps", "fr": "Alpes", "es": "Alpes"},
    "Dolomiti": {"nl": "Dolomieten", "en": "Dolomites", "fr": "Dolomites", "es": "Dolomitas"},
    "Donau": {"en": "Danube", "es": "Danubio", "fr": "Danube"},
    "Danube": {"nl": "Donau", "es": "Danubio"},
    "Danube Plain": {"nl": "Donauvlakte", "en": "Danubian Plain", "es": "Llanura del Danubio", "fr": "plaine du Danube"},
    "Garonne": {"es": "Garona"},
    "Loire": {"es": "Loira"},
    "Rhône": {"es": "Ródano"},
    "Tejo": {"fr": "Tage", "es": "Tajo"},
    "Lisboa": {"en": "Lisbon", "fr": "Lisbonne", "nl": "Lissabon"},
    "Bayern": {"en": "Bavaria", "es": "Baviera", "fr": "Bavière", "nl": "Beieren"},
    "Toscana": {"nl": "Toscane", "en": "Tuscany", "fr": "Toscane"},
    "Piemonte": {"nl": "Piëmont", "en": "Piedmont", "fr": "Piémont", "es": "Piamonte"},
    "Sicilia": {"nl": "Sicilië", "en": "Sicily", "fr": "Sicile"},
    "Sardegna": {"nl": "Sardinië", "en": "Sardinia", "fr": "Sardaigne", "es": "Cerdeña"},
    "Lombardia": {"nl": "Lombardije", "en": "Lombardy", "fr": "Lombardie", "es": "Lombardía"},
    "Steiermark": {"nl": "Stiermarken", "en": "Styria", "fr": "Styrie", "es": "Estiria"},
    "Wien": {"nl": "Wenen", "en": "Vienna", "fr": "Vienne", "es": "Viena"},
    "Sachsen": {"nl": "Saksen", "en": "Saxony", "fr": "Saxe", "es": "Sajonia"},
    "Kärnten": {"nl": "Karinthië", "en": "Carinthia", "fr": "Carinthie", "es": "Carintia"},
    "Andalucía": {"nl": "Andalusië", "en": "Andalusia", "fr": "Andalousie"},
    "Cataluña": {"nl": "Catalonië", "en": "Catalonia", "fr": "Catalogne"},
    "Catalunya": {"nl": "Catalonië", "en": "Catalonia", "fr": "Catalogne", "es": "Cataluña"},
    "Castilla": {"nl": "Castilië", "en": "Castile", "fr": "Castille"},
    "Bourgogne": {"nl": "Bourgondië", "en": "Burgundy", "es": "Borgoña"},
    "Alsace": {"nl": "Elzas", "es": "Alsacia"},
    "Moselle": {"nl": "Moezel", "es": "Mosela"},
    "Mosel": {"nl": "Moezel", "fr": "Moselle", "es": "Mosela"},
    "Rodopi": {"en": "Rhodopes", "fr": "Rhodopes", "nl": "Rhodopen", "es": "Ródope"},
    "Rodopite": {"en": "Rhodopes", "fr": "Rhodopes", "nl": "Rhodopen", "es": "Ródope"},
    "Родопи": {"en": "Rhodopes", "fr": "Rhodopes", "nl": "Rhodopen", "es": "Ródope"},
    "Родопите": {"en": "Rhodopes", "fr": "Rhodopes", "nl": "Rhodopen", "es": "Ródope"},
    "Balkan Mountains": {"nl": "Balkangebergte", "fr": "Grand Balkan", "es": "Gran Balcán"},
    "Nördliche Kalkalpen": {"en": "Northern Limestone Alps", "nl": "Noordelijke Kalkalpen", "fr": "Alpes calcaires septentrionales", "es": "Alpes Calcáreos del Norte"},
    "Schwarzwald": {"en": "Black Forest", "nl": "Zwarte Woud", "fr": "Forêt-Noire", "es": "Selva Negra"},
    "Bodensee": {"en": "Lake Constance", "nl": "Bodenmeer", "fr": "lac de Constance", "es": "lago de Constanza"},
    "Neusiedler See": {"en": "Lake Neusiedl", "nl": "Neusiedler See", "fr": "lac de Neusiedl", "es": "lago Neusiedl"},
    "Karpaty": {"en": "Carpathians", "nl": "Karpaten", "fr": "Carpates", "es": "Cárpatos"},
    "Karpaten": {"en": "Carpathians", "nl": "Karpaten", "fr": "Carpates", "es": "Cárpatos"},
    "Carpați": {"en": "Carpathians", "nl": "Karpaten", "fr": "Carpates", "es": "Cárpatos"},
    "Kárpátok": {"en": "Carpathians", "nl": "Karpaten", "fr": "Carpates", "es": "Cárpatos"},
    "Dunărea": {"en": "Danube", "nl": "Donau", "fr": "Danube", "es": "Danubio"},
    "Дунав": {"en": "Danube", "nl": "Donau", "fr": "Danube", "es": "Danubio"},
    "Duna": {"en": "Danube", "nl": "Donau", "fr": "Danube", "es": "Danubio"},
    "Peloponnisos": {"en": "Peloponnese", "nl": "Peloponnesos", "fr": "Péloponnèse", "es": "Peloponeso"},
    "Πελοπόννησος": {"en": "Peloponnese", "nl": "Peloponnesos", "fr": "Péloponnèse", "es": "Peloponeso"},
    "Kriti": {"en": "Crete", "nl": "Kreta", "fr": "Crète", "es": "Creta"},
    "Κρήτη": {"en": "Crete", "nl": "Kreta", "fr": "Crète", "es": "Creta"},
    "Makedonia": {"en": "Macedonia", "nl": "Macedonië", "fr": "Macédoine", "es": "Macedonia"},
    "Thessalia": {"en": "Thessaly", "nl": "Thessalië", "fr": "Thessalie", "es": "Tesalia"},
    "Ipiros": {"en": "Epirus", "nl": "Epirus", "fr": "Épire", "es": "Epiro"},
    "Egeo": {"en": "Aegean", "nl": "Egeïsche Zee", "fr": "mer Égée", "es": "Egeo"},
    "Aigaio": {"en": "Aegean", "nl": "Egeïsche Zee", "fr": "mer Égée", "es": "Egeo"},
    "Jadran": {"en": "Adriatic", "nl": "Adriatische Zee", "fr": "Adriatique", "es": "Adriático"},
    "Sredozemlje": {"en": "Mediterranean", "nl": "Middellandse Zee", "fr": "Méditerranée", "es": "Mediterráneo"},
    "Mediterrâneo": {"en": "Mediterranean", "nl": "Middellandse Zee", "fr": "Méditerranée", "es": "Mediterráneo"},
    "Atlântico": {"en": "Atlantic", "nl": "Atlantische Oceaan", "fr": "Atlantique", "es": "Atlántico"},
}

# An appellation label next to the name: the form is the registered name, not a place.
_GI_MARKER = re.compile(
    r"\b(DOC|DOCG|IGT|IGP|DOP|AOC|AOP|PDO|PGI|DAC|g\.U\.|g\.g\.A\.|Landwein|grand cru|premier cru|"
    r"appellation|denominazione|denominación|Vino de la Tierra|Anbaugebiet)\b", re.I)
# A grape or institution built on the place name.
_NAME_CONTEXT = re.compile(r"\b(Melon|Junta|Generalitat|Lezíria|Ribatejo|Consorzio|Consejo)\b", re.I)


def _pattern(form: str) -> re.Pattern:
    return re.compile(r"(?<![\w-])" + re.escape(form) + r"(?![\w-])")


_PATTERNS = {form: _pattern(form) for form in EXONYMS}


def exonym_hits(bullet: str, lang: str, *, gi_forms: frozenset[str] = frozenset()) -> list[str]:
    """Source forms in `bullet` that should read as their `lang` exonym.
    `gi_forms`: the forms that also occur in an appellation name of the
    corpus — flagged only in a place-like context."""
    out: list[str] = []
    for form, targets in EXONYMS.items():
        if lang not in targets:
            continue
        for m in _PATTERNS[form].finditer(bullet or ""):
            ctx = bullet[max(0, m.start() - 45): m.end() + 45]
            if form in gi_forms and (_GI_MARKER.search(ctx) or _NAME_CONTEXT.search(ctx)):
                continue
            if form not in gi_forms and _NAME_CONTEXT.search(ctx):
                continue
            out.append(form)
            break
    return out


def gi_forms_from_names(names) -> frozenset[str]:
    """The exonym source forms that occur as a whole word in any GI name."""
    blob = " ".join(names)
    return frozenset(form for form in EXONYMS if _PATTERNS[form].search(blob))
