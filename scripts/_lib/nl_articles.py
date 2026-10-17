"""Dutch article agreement (de / het) in machine-translated bullets.

Every word of "Het wijngaard profiteert van …" is spelled right, so a
spelling dictionary passes it; the defect is the article. 23 NL terroir
bullets rendered FR "le vignoble" that way (2026-10-09, Kirchberg de Barr),
next to "het gemeente", "de landschap", "de perceel". The 02e back-check
graded them `ok`: the meaning survives. This module is the deterministic
detector: a table of nouns whose gender is unambiguous in the wine corpus,
read only right after a definite article or demonstrative (with at most one
inflected adjective between), so it says nothing it cannot be sure of.

Not flagged on purpose: a noun followed by a hyphen or soft hyphen (the
first half of a compound — "het heuvel- en voetheuvelgebied", "de
klimaat- en bodemkenmerken"), a capitalised noun (a name), "die" / "dat"
(also a relative pronoun and a conjunction), and nouns that take either
article or collide with a common verb form (leem, kalksteen, leisteen,
teelt, meer).
"""

from __future__ import annotations

import re

DE_NOUNS = frozenset({
    "aanplant", "appellatie", "berg", "bodem", "denominatie", "druif", "druivensoort", "gemeente",
    "gisting", "grond", "helling", "heuvel", "hoogte", "klei", "kust", "ligging", "ondergrond",
    "opbrengst", "oriëntatie", "provincie", "regio", "rijping", "rivier", "streek", "temperatuur",
    "vallei", "vinificatie", "wijnbouw", "wijnbouwer", "wijngaard", "wijnstok", "wijnstreek", "zone",
})

HET_NOUNS = frozenset({
    "areaal", "basalt", "bekken", "bos", "dal", "departement", "dorp", "druivenras", "gebied",
    "gesteente", "graniet", "grind", "klimaat", "landschap", "massief", "mesoklimaat",
    "microklimaat", "perceel", "plateau", "productiegebied", "ras", "reliëf", "stroomgebied",
    "terras", "terroir", "wijnbouwgebied", "wijngebied", "zand",
})

# Words that fill the adjective slot without being an adjective: a second
# article ("het de gemeente" — "it is the municipality"), a classifier noun
# ("dit type bodem", "het type wijnbouw"), a numeral ("de drie bekkens").
_NOT_ADJECTIVES = frozenset({"de", "deze", "die", "mate", "soort", "type", "twee", "drie"})

_DE_ARTICLES = {"de": "het", "deze": "dit"}
_HET_ARTICLES = {"het": "de", "dit": "deze"}

_PHRASE = re.compile(
    r"(?<![\w'’\-])(?P<art>[Dd]e|[Dd]eze|[Hh]et|[Dd]it)\s+"
    r"(?:(?P<adj>[a-zà-ÿ]+e)\s+)?"
    r"(?P<noun>[a-zà-ÿ]+)(?![\w\-­])"
)


def _wrong(article: str, noun: str) -> bool:
    a = article.lower()
    return (a in _HET_ARTICLES and noun in DE_NOUNS) or (a in _DE_ARTICLES and noun in HET_NOUNS)


def article_hits(text: str) -> list[str]:
    """The article + noun phrases of `text` whose article does not agree
    with the noun ("Het wijngaard", "de perceel"), in order."""
    hits: list[str] = []
    for m in _PHRASE.finditer(text or ""):
        art, adj, noun = m.group("art"), m.group("adj"), m.group("noun")
        if adj in _NOT_ADJECTIVES:
            continue
        if _wrong(art, noun):
            hits.append(m.group(0))
        elif adj and _wrong(art, adj):
            hits.append(f"{art} {adj}")
    return hits
