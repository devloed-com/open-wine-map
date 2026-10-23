"""The product categories a record declares, classified still / sparkling /
other: the EU single document's "categories of grapevine products" list
(Reg. 1308/2013 Annex VII Part II — "1. Vin", "5. Vino spumante di
qualità", "4. Mousserende wijn") and, for France, INAO's SIQO `categorie`
("Vin tranquille", "Vin mousseux «Crémant»").

A grape-colour fallback reads this to tell a sparkling-only appellation —
Crémant d'Alsace, Franciacorta, Vlaamse mousserende kwaliteitswijn, whose
colours its text names or not at all — from one whose still wines its text
simply names in no colour word (Dealu Mare: "1. Vin, 5. Vin spumant de
calitate, 8. Vin petiant"). Before 2026-10-23 the stage-04 floor guessed
from the record's styles alone, so Franciacorta carried White and Red and
Dealu Mare, which declares still wine, lost its Red.
"""

from __future__ import annotations

import re

# The section that lists the categories: its title opens on the word
# (after an optional number), or — Hungarian — ends on it. Per-type
# sections ("Colli Berici spumante - Categoria «Vino spumante di qualità»",
# "WIJNCATEGORIE 1 Wijn, Wijntype: …") are not lists and are not read.
_TITLE_RE = re.compile(
    r"^\W*(?:\d{1,2}\s*[.)]?\s*)?(?:cat[eé]gor|kategor|катег|κατηγορ)"
    r"|term[ée]kek\s+kateg[óo]ri[áa]i\s*$",
    re.IGNORECASE,
)

_SPARKLING_RE = re.compile(
    r"mousser|mousseux|moussend|spumant|espumos|espumant|sparkling|schaumwein|\bsekt\b"
    r"|pezsg|pene[čc]|penin|pjenu[šs]|[šs]umiv|пенлив|искрящ|αφρώδ"
    r"|perlwein|parelwijn|frizzant|petiant|perlant|p[ée]tillant|gy[öo]ngy[öo]z[őo]"
    r"|biser|perliv|перлен|aguja|frisante",
    re.IGNORECASE,
)

# The categories that are neither the wine itself nor sparkling: liqueur
# wine, wine of raisined or overripe grapes, grape must, new wine, vinegar,
# a spirit — and SIQO's sweet / oxidative categories.
_OTHER_RE = re.compile(
    r"licor|liquor|liqueur|lik[öőoée]r|likeur|ликьор|λικέρ|lichior"
    r"|\buv[ae]s?\b|grapes|druiven|trauben|raisin|appassit|pasific|sobremadur|sobreamadur"
    r"|overrip|overrijp|surm[ûu]ri|eingetrockn|túlérett|prosu[šs]|presu[šs]|λιαστ|υπερώριμ"
    r"|prezret|hrozienk|stafid|сушен|mosto|\bmust\b|\bmost\b|μούστ|мъст|aguardent|bagaceir|vinagre|vinegar"
    r"|aceto|essig|nuevo|nuovo|\bnovo\b|grains\s+nobles|vendanges|paille|\bjaune\b"
    r"|doux\s+naturel|tri[ée]es|eaux?-de-vie|cidre|poir[ée]|spiritu|whisk|rhum",
    re.IGNORECASE,
)
# The category "wine" itself (EU category 1) opens on the wine word of its
# language — "Vin", "Vinho branco, tinto, e rosado ou rosé", SIQO's "Vin
# tranquille" — once its number and any "(1)" reference are cut.
_STILL_RE = re.compile(
    r"^(?:vin|vinho|wine|wijn|wein|bor|v[íi]no|вино|ο[ίι]νος)\b",
    re.IGNORECASE,
)

_ITEM_NUMBER_RE = re.compile(r"^\s*\(?\d{1,2}(?:\s*[.)])?\s*")
_ITEM_REF_RE = re.compile(r"[\s–-]*\(\s*\d{1,2}\s*\)\s*$")


def classify(item: str) -> str:
    """'sparkling' (sparkling or semi-sparkling, aerated or not), 'still'
    (the category wine) or 'other' (liqueur, raisined, overripe, must, …)."""
    text = _ITEM_REF_RE.sub("", _ITEM_NUMBER_RE.sub("", item)).strip(" .:;–-\t\xa0«»\"")
    if _SPARKLING_RE.search(text):
        return "sparkling"
    if _OTHER_RE.search(text):
        return "other"
    if _STILL_RE.match(text):
        return "still"
    return "other"


def _items(body: str) -> list[str]:
    out = []
    for line in re.split(r"[\n;]", body or ""):
        text = _ITEM_NUMBER_RE.sub("", line).strip(" .:;–-\t\xa0")
        if 2 <= len(text) <= 90:
            out.append(line)
    return out


def _category_bodies(record: dict) -> list[str]:
    """The category list's body: the section titled as one, PT's
    `sections["category"]`, the GR / CY national specs' `category` role."""
    bodies: list[str] = []
    titles = record.get("section_titles")
    sections = record.get("sections")
    if isinstance(titles, dict) and isinstance(sections, dict):
        bodies += [sections.get(key) or "" for key, title in titles.items()
                   if isinstance(title, str) and len(title) < 140 and _TITLE_RE.search(title)]
    for holder in (sections, record.get("section_roles")):
        if isinstance(holder, dict) and isinstance(holder.get("category"), str):
            bodies.append(holder["category"])
    return bodies


def declared_kinds(record: dict) -> set[str] | None:
    """The kinds of the categories the record declares, or None when it
    carries no category list (a national spec, a MASAF disciplinare)."""
    if record.get("country") == "fr":
        cats = [c for c in record.get("categories") or [] if isinstance(c, str) and c.strip()]
        return {classify(c) for c in cats} or None
    kinds = {classify(item) for body in _category_bodies(record) for item in _items(body)}
    return kinds or None


def sparkling_only(record: dict) -> bool:
    kinds = declared_kinds(record)
    return bool(kinds) and kinds <= {"sparkling"}


def declares_still(record: dict) -> bool:
    return "still" in (declared_kinds(record) or ())
