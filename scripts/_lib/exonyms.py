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
    r"appellation|denominazione|denominación|Vino de la Tierra|Anbaugebiet)\b|\bd\.o\.c\.", re.I)
# A grape or institution built on the place name.
_NAME_CONTEXT = re.compile(r"\b(Melon|Junta|Generalitat|Lezíria|Ribatejo|Consorzio|Consejo)\b", re.I)
# The form inside a longer proper name, kept verbatim in every locale: a
# comune ("Magliano in Toscana"), a title ("Bacco in Toscana", Redi's
# dithyramb), a district name ("Alto Piemonte"); and a quoted name
# («Argille Varicolori»). 2026-10-25: each was flagged as an untranslated
# place on the caches re-translated in phases D–G. A German or Austrian town
# named by its river likewise ("Ludwigshafen am Rhein", "Mautern an der
# Donau", 2026-11-13: the drink records' municipality lists).
_IN_PROPER_NAME = re.compile(
    r"[A-ZÀ-Ý][\w'’-]+\s+(?:in|di|del|della|de|du|des|am|an der|ob der|bei)\s+$"
    r"|\b(?:Alto|Basso|Medio|Haut|Bas)[-\s]+$")
_QUOTE_OPEN = "«“\"„"
_QUOTE_CLOSE = "»”\"“"


def _in_quotes(text: str, start: int, end: int) -> bool:
    """True when [start, end) sits between an opening and a closing quote on
    the same stretch of text (no sentence end in between)."""
    before, after = text[:start], text[end:]
    o = max(before.rfind(q) for q in _QUOTE_OPEN)
    if o < 0 or any(before.rfind(q) > o for q in _QUOTE_CLOSE if q not in _QUOTE_OPEN):
        return False
    c = min((after.find(q) for q in _QUOTE_CLOSE if after.find(q) >= 0), default=-1)
    return c >= 0 and ". " not in before[o:] and ". " not in after[:c]


def _pattern(form: str) -> re.Pattern:
    return re.compile(r"(?<![\w-])" + re.escape(form) + r"(?![\w-])")


_PATTERNS = {form: _pattern(form) for form in EXONYMS}


def _fold_name(text: str) -> str:
    """Lower case and one apostrophe, character for character — the offsets
    of the folded text are the offsets of `text` (`str.casefold` turns "ß"
    into two letters)."""
    return "".join(c.lower() if len(c.lower()) == 1 else c for c in text.replace("’", "'"))


def _inside_name(bullet: str, start: int, end: int, names) -> bool:
    """True when [start, end) lies inside an occurrence of one of `names`
    longer than the form itself ("Sardegna" in "Cannonau di Sardegna")."""
    # the name as a translation writes it: either apostrophe, any case
    # (the record is « Kirsch d’Alsace », the Spanish bullet "el Kirsch
    # d'Alsace"; "de marc d'Alsace Gewurztraminer" opens lower-case)
    folded = _fold_name(bullet)
    for name in names:
        if len(name) <= end - start:
            continue
        for m in re.finditer(re.escape(_fold_name(name)), folded):
            if m.start() <= start and end <= m.end():
                return True
    return False


def exonym_hits(bullet: str, lang: str, *, gi_forms: frozenset[str] = frozenset(),
                own_names=()) -> list[str]:
    """Source forms in `bullet` that should read as their `lang` exonym.
    `gi_forms`: the forms that also occur in an appellation name of the
    corpus — flagged only in a place-like context. `own_names`: the
    bullet's own appellation names; a form inside one of them is the label
    ("the production zone of Cannonau di Sardegna"), while a record named
    after the region alone ("Upper Kärnten") is still read as a place."""
    out: list[str] = []
    for form, targets in EXONYMS.items():
        if lang not in targets:
            continue
        # the source form is already the target's ("mar Egeo" in Spanish,
        # "Karpaten" in Dutch)
        if _PATTERNS[form].search(targets[lang]):
            continue
        for m in _PATTERNS[form].finditer(bullet or ""):
            ctx = bullet[max(0, m.start() - 45): m.end() + 45]
            if form in gi_forms and (_GI_MARKER.search(ctx) or _NAME_CONTEXT.search(ctx)):
                continue
            if form not in gi_forms and _NAME_CONTEXT.search(ctx):
                continue
            if _inside_name(bullet, m.start(), m.end(), own_names) \
                    or _IN_PROPER_NAME.search(bullet[max(0, m.start() - 40): m.start()]) \
                    or _in_quotes(bullet, m.start(), m.end()):
                continue
            out.append(form)
            break
    return out


def gi_forms_from_names(names) -> frozenset[str]:
    """The exonym source forms that occur as a whole word in any GI name."""
    blob = " ".join(names)
    return frozenset(form for form in EXONYMS if _PATTERNS[form].search(blob))
