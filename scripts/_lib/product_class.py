"""What a record is: a wine, a spirit drink, an aromatised wine or a cider.

The corpus began as wine GIs; since 2026-11 it also holds the spirit-drink
GIs (Reg. (EU) 2019/787), the aromatised wine GIs (Reg. (EU) 251/2014, in
the register's class 2.21 since 2021; the two Glühwein and Samoborski bermet
sit in its residual class 2.22 "Other alcoholic beverages") and the cider /
perry GIs (agricultural-product PDO / PGIs). There is no single legal term
for the three together; the UI calls them "spirits and other alcoholic
drinks" and shows them behind one legend pill.

Every extracted record carries `product_class` and `drink_category`; a
record without the field is a wine, so the wine pipelines are untouched. An
FR record written before the field existed is classed from its SIQO
`categorie` (`fr.siqo.classify_categorie`).

`drink_category` is the facet beneath the umbrella: a slug of the spirit
category of Annex I of Reg. 2019/787 (grouped where the annex splits what a
reader takes for one drink: the four aniseed categories, liqueur and its
named members), or the class itself for an aromatised wine or a cider. The
slugs are leaves of the `drinks` bucket of `style_taxonomy.py`, and a drink
record's `styles` is its category, so the style facet, the pills and the
MCP facets need nothing of their own.
"""
from __future__ import annotations

import re

PRODUCT_CLASSES: tuple[str, ...] = ("wine", "spirit", "aromatised-wine", "cider")

DRINK_CATEGORIES: tuple[str, ...] = (
    "wine-spirit", "brandy", "grape-marc", "fruit-spirit", "cider-spirit", "rum",
    "whisky", "grain-spirit", "juniper", "aniseed", "liqueur", "bitter",
    "other-spirit", "aromatised-wine", "cider",
)

# Annex I of Reg. (EU) 2019/787, by category number as the EU register prints
# it in `productCategory` ("4. Wine spirit", "15. Vodka, 31. Flavoured vodka").
# A number not listed is `other-spirit`: vodka, gentian, caraway, akvavit and
# the register's own residual "45. Spirit drinks".
_ANNEX_CATEGORY: dict[int, str] = {
    1: "rum",
    2: "whisky",
    3: "grain-spirit",
    4: "wine-spirit",
    5: "brandy",
    6: "grape-marc",
    7: "fruit-spirit",       # fruit marc spirit
    8: "fruit-spirit",       # raisin spirit
    9: "fruit-spirit",
    10: "cider-spirit",
    16: "fruit-spirit",      # spirit obtained by maceration and distillation
    17: "fruit-spirit",      # Geist
    19: "juniper",
    20: "juniper",           # gin
    21: "juniper",
    22: "juniper",
    25: "aniseed",
    26: "aniseed",           # pastis
    27: "aniseed",
    28: "aniseed",           # anis
    29: "aniseed",           # distilled anis
    30: "bitter",
    32: "liqueur",           # sloe-aromatised spirit drink or pacharán
    33: "liqueur",
    34: "liqueur",           # crème de …
    35: "liqueur",           # sloe gin
    36: "liqueur",           # sambuca
    37: "liqueur",           # maraschino
    38: "liqueur",           # nocino
    39: "liqueur",           # egg liqueur
    40: "liqueur",
    41: "aniseed",           # mistrà
}

_CATEGORY_NUMBER_RE = re.compile(r"^\s*(\d{1,2})\s*\.")


def spirit_category(register_category: str) -> str:
    """The `drink_category` of a spirit from the register's `productCategory`
    string; the first category named decides ("15. Vodka, 31. Flavoured
    vodka")."""
    m = _CATEGORY_NUMBER_RE.match(register_category or "")
    if not m:
        return "other-spirit"
    return _ANNEX_CATEGORY.get(int(m.group(1)), "other-spirit")


def classify_register_row(row: dict, cider_file_numbers: frozenset[str] | set[str] = frozenset()) -> tuple[str, str]:
    """(product_class, drink_category) of a register listing row
    (`eambrosia_register.load_gi_rows`); ("", "") for a row that is no drink
    of the corpus (a wine, a food). The ciders are Food-class GIs in class
    1.8, told apart only by the checked-in file-number list."""
    qpt = (row.get("qualityProductType") or "").strip()
    cat = (row.get("productCategory") or "").strip()
    if qpt == "Spirit drink":
        return "spirit", spirit_category(cat)
    if cat.startswith(("Class 2.21", "Class 2.22")):
        return "aromatised-wine", "aromatised-wine"
    if (row.get("fileName") or "") in cider_file_numbers:
        return "cider", "cider"
    return "", ""


def product_class(record: dict) -> str:
    """The record's class; "wine" when the record says nothing. An FR record
    of before the field takes it from its SIQO categorie."""
    pc = (record.get("product_class") or "").strip()
    if pc in PRODUCT_CLASSES:
        return pc
    if (record.get("country") or "fr") == "fr":
        return _fr_class(record)[0]
    return "wine"


def drink_category(record: dict) -> str:
    """The record's drink category slug; "" for a wine."""
    if product_class(record) == "wine":
        return ""
    dc = (record.get("drink_category") or "").strip()
    if dc in DRINK_CATEGORIES:
        return dc
    if (record.get("country") or "fr") == "fr":
        return _fr_class(record)[1]
    return "other-spirit" if product_class(record) == "spirit" else product_class(record)


def is_wine(record: dict) -> bool:
    return product_class(record) == "wine"


def _fr_class(record: dict) -> tuple[str, str]:
    from _lib.fr.siqo import classify_categorie

    categorie = (record.get("categorie") or "").strip()
    categories = record.get("categories") or []
    # A record extracted via the manual-override / mirror path carries an
    # empty manifest `categorie` while the SIQO-derived `categories` list is
    # populated (Côte roannaise, Muscat du Cap Corse).
    if not categorie and categories:
        categorie = categories[0]
    pc, dc = classify_categorie(categorie, id_appellation=str(record.get("id_appellation") or ""))
    if pc:
        return pc, dc
    # A categorie the table does not know. An eau-de-vie cahier layout is a
    # spirit whatever the export says; anything else with a categorie is a
    # non-wine drink of no known category (the stage-04 rule of before the
    # class model: only a "Vin…" categorie is a wine), and a record with no
    # categorie at all says nothing and stays a wine.
    if (record.get("kind") or "") == "EDV":
        return "spirit", "other-spirit"
    if categorie:
        return "spirit", "other-spirit"
    return "wine", ""
