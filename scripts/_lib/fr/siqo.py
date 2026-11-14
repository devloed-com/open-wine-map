"""The INAO SIQO referentiel as the FR pipeline reads it: the data.gouv.fr
CSV plus the checked-in supplement rows.

The CSV (`raw/inao/siqo-referentiel.csv`) is INAO's export of its product
catalogue. It is labelled weekly on data.gouv.fr but republished about once
a year (the 2025-12-31 extraction was still the live resource on
2026-10-01), so between two exports it misses what INAO itself already
publishes: a new appellation (Montpeyroux, arrêté du 11 août 2026) has no
row, and a denomination INAO retires keeps its row. Every FR stage that
reads the referentiel — 01 (manifest), 01d (register bind), 02 (records and
denominations), the coverage audit — therefore reads it through
`siqo_rows()`, which appends the rows of `siqo_supplements.json`.

Two kinds of supplement row, both in the CSV's own column set so no reader
has to know they are supplements:

- `added` — a GI INAO has recognised that the export does not carry yet.
  Its `id_appellation` / `id_denomination_geo` are provisional strings
  (`p<idproduit>`, the INAO product id, which is public and stable) until
  the export publishes INAO's numbers; `idproduit` is the real one, so
  stage 01 walks the real product page.
- `retained` — a row the export dropped but the corpus keeps: a record is
  never removed because a CSV export stopped listing it. The decision that
  retires or re-labels it lives in a registry with a cited public act
  (`cancelled_gis.json`, `promoted_gis.json`); the row here only keeps the
  record in the build. Stage 02's full run refuses to drop a previously
  emitted denomination unless told so (`--allow-drop`), which is where a
  curator learns a row went missing.

A supplement row whose `id_appellation` or `idproduit` collides with a CSV
row that names another appellation is a mistake and raises.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SIQO_CSV = ROOT / "raw" / "inao" / "siqo-referentiel.csv"
SUPPLEMENTS_PATH = Path(__file__).with_name("siqo_supplements.json")

# The signs a corpus row carries. "IG" is the EU sign of a spirit-drink GI
# (Reg. (EU) 2019/787): INAO signs 29 of its spirits AOC as well, and those
# were in the corpus from the start; the 34 appellations whose only sign is
# IG (Fine Bordeaux, Marc de Champagne, Ratafia champenois, the rums, the
# Alsace fruit spirits, cassis, génépi, absinthe, genièvre, Whisky d'Alsace)
# joined on 2026-11-12 with the other countries' spirit drinks.
CORPUS_SIGNS = {"AOC", "AOP", "IGP", "IG"}
WINE_SIGNS = CORPUS_SIGNS  # the name the stages imported before the widening

# SIQO `categorie` → (product_class, drink_category); see
# `_lib/product_class.py`. Every categorie beginning with "Vin" is a wine.
CATEGORIE_CLASS: dict[str, tuple[str, str]] = {
    "Cidre": ("cider", "cider"),
    "Poiré": ("cider", "cider"),
    "Eaux-de-vie de vin": ("spirit", "wine-spirit"),
    "Eaux-de-vie de marc de raisin": ("spirit", "grape-marc"),
    "Eaux-de-vie de fruits": ("spirit", "fruit-spirit"),
    "Eaux-de-vie de cidre et de poiré": ("spirit", "cider-spirit"),
    "Rhum": ("spirit", "rum"),
    "Whisky ou Whiskey": ("spirit", "whisky"),
    "Liqueur": ("spirit", "liqueur"),
    "Crème de cassis": ("spirit", "liqueur"),
    "Boissons aromatisées baies de genévrier": ("spirit", "juniper"),
    "Autres boissons spiritueuses": ("spirit", "other-spirit"),
}

# Where the export's `categorie` and the EU register disagree about a spirit,
# the register's Annex I category is the legal one. id_appellation → category
# slug, each with the register entry it was read from.
CATEGORY_PINS: dict[str, tuple[str, str]] = {
    # SIQO files Genièvre Flandre-Artois under "Eaux-de-vie de fruits"; the
    # register: "19. Juniper-flavoured spirit drink" (PGI-FR-02028).
    "1030": ("juniper", "EU GI register PGI-FR-02028, category 19"),
    # SIQO files Absinthe de Pontarlier under "Liqueur"; the register:
    # "45. Spirit drinks" (PGI-FR-01870).
    "746": ("other-spirit", "EU GI register PGI-FR-01870, category 45"),
}


def classify_categorie(categorie: str, id_appellation: str = "") -> tuple[str, str]:
    """(product_class, drink_category) for a SIQO categorie; ("wine", "") for
    a wine and ("", "") for a categorie the table does not know (the caller
    decides: an empty categorie on a stub says nothing)."""
    cat = (categorie or "").strip()
    if cat.startswith("Vin"):
        return "wine", ""
    known = CATEGORIE_CLASS.get(cat)
    if known is None:
        return "", ""
    pin = CATEGORY_PINS.get(str(id_appellation or "").strip())
    if pin and known[0] == "spirit":
        return "spirit", pin[0]
    return known

SIQO_COLUMNS = (
    "signe_fr", "signe_ue", "id_categorie_produit", "categorie", "id_type_produit",
    "classe_ue", "secteur", "id_appellation", "appellation", "id_denomination_geo",
    "denomination", "produit", "idproduit", "pro_etat", "lib_etat", "cvi_douane",
    "reference_produit", "comite_national", "comite_regional", "site_inao",
    "delegation_territoriale_inao", "date_extraction",
)
SUPPLEMENT_STATUSES = {"added", "retained"}
NAME_OVERRIDE_KEYS = ("appellation", "_reason", "_source", "_verified")


def load_supplements(path: Path = SUPPLEMENTS_PATH) -> list[dict]:
    """The supplement rows, validated: every SIQO column present, a known
    `_status`, a `_source` and a `_verified` date."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("rows") or []
    for i, row in enumerate(rows):
        missing = [c for c in SIQO_COLUMNS if c not in row]
        if missing:
            raise ValueError(f"{path.name} row {i}: missing SIQO column(s) {missing}")
        if row.get("_status") not in SUPPLEMENT_STATUSES:
            raise ValueError(f"{path.name} row {i}: _status must be one of {sorted(SUPPLEMENT_STATUSES)}")
        for key in ("_source", "_verified"):
            if not row.get(key):
                raise ValueError(f"{path.name} row {i}: `{key}` is required")
    return rows


def load_name_overrides(path: Path = SUPPLEMENTS_PATH) -> dict[str, dict]:
    """`name_overrides` of the supplements file: id_appellation → the name
    the record carries in place of the export's `appellation` column, with
    the reason, the public source and a verification date. For a GI whose
    registered name is longer than the export's catalogue label — the
    export's own `produit` column, the INAO product page, the EU register
    and the cahier all say "Marc d'Alsace Gewurztraminer" where the
    `appellation` column says "Marc d'Alsace"."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    overrides = data.get("name_overrides") or {}
    for id_app, spec in overrides.items():
        missing = [k for k in NAME_OVERRIDE_KEYS if not spec.get(k)]
        if missing:
            raise ValueError(f"{path.name} name_overrides[{id_app}]: missing {missing}")
    return overrides


def apply_name_overrides(rows: list[dict], overrides: dict[str, dict]) -> list[str]:
    """Rename the rows in place; returns the ids whose export row already
    carries the pinned name, or has no row (a STALE pin)."""
    stale: list[str] = []
    for id_app, spec in overrides.items():
        new = spec["appellation"].strip()
        hit = False
        for row in rows:
            if row["id_appellation"].strip() != id_app:
                continue
            old = row["appellation"].strip()
            if old == new:
                stale.append(id_app)
                break
            hit = True
            if row["denomination"].strip() == old:
                row["denomination"] = new
            row["appellation"] = new
        if not hit and id_app not in stale:
            stale.append(id_app)
    return stale


def _check_collisions(csv_rows: list[dict], supplements: list[dict], path: Path) -> None:
    by_app = {r["id_appellation"].strip(): r["appellation"].strip() for r in csv_rows}
    by_prod = {r["idproduit"].strip(): r["appellation"].strip() for r in csv_rows}
    for s in supplements:
        app = s["appellation"].strip()
        other = by_app.get(s["id_appellation"].strip())
        if other and other != app:
            raise ValueError(
                f"{path.name}: id_appellation {s['id_appellation']} is {other!r} in the CSV, "
                f"not {app!r}"
            )
        other = by_prod.get(s["idproduit"].strip())
        if other and other != app and s.get("_status") == "added":
            raise ValueError(
                f"{path.name}: idproduit {s['idproduit']} is {other!r} in the CSV, not {app!r}"
            )


def siqo_rows(csv_path: Path = SIQO_CSV, supplements_path: Path = SUPPLEMENTS_PATH) -> list[dict]:
    """Every row of the referentiel: the CSV's, then the supplements'. A
    `retained` supplement row is skipped when the CSV carries the same
    `idproduit` again (the export caught up), so nothing is doubled."""
    rows: list[dict] = []
    if csv_path.exists():
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    supplements = load_supplements(supplements_path)
    if supplements:
        _check_collisions(rows, supplements, supplements_path)
        csv_products = {r["idproduit"].strip() for r in rows}
        for s in supplements:
            if s.get("_status") == "retained" and s["idproduit"].strip() in csv_products:
                continue
            rows.append({c: str(s.get(c, "") or "") for c in SIQO_COLUMNS})
    overrides = load_name_overrides(supplements_path)
    if overrides:
        for id_app in apply_name_overrides(rows, overrides):
            print(
                f"[siqo] STALE name override {id_app}: the referentiel row already reads "
                f"{overrides[id_app]['appellation']!r} or is gone — drop the pin",
                file=sys.stderr,
            )
    return rows


# A GI of several member states is one record, owned by the first country of
# its EU file number (the Maasvallei rule). INAO's referentiel lists the ones
# France shares; one that another state filed is built by the drinks pipeline
# (scripts/drinks/), with France among its `country_aliases`, and is no record
# of the French stages. id_appellation → the register entry that says so.
DRINKS_PIPELINE_IDS: dict[str, str] = {
    # Genièvre / Jenever / Genever — Belgium, the Netherlands, France, Germany
    "1157": "EU GI register PGI-BE+NL+FR+DE-01962: filed by Belgium, the first country of the file number",
}


def is_corpus_row(row: dict) -> bool:
    """The filter every FR stage applies: VITICOLE sector (INAO files wines,
    ciders and spirit drinks under it), an AOC / AOP / IGP / IG sign, état
    Publié — and not a multi-country GI another state filed
    (`DRINKS_PIPELINE_IDS`)."""
    if row["secteur"].strip() != "VITICOLE":
        return False
    if (row.get("id_appellation") or "").strip() in DRINKS_PIPELINE_IDS:
        return False
    if row["lib_etat"].strip() != "Publié":
        return False
    sign = row["signe_fr"].strip() or row["signe_ue"].strip()
    return sign in CORPUS_SIGNS


is_wine_row = is_corpus_row  # the name before the corpus held IG-only spirits
