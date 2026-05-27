"""Village-level INSEE overrides for DGCs whose territory is enumerated
in the cahier prose rather than published as a parcellaire row or an
aires-CSV entry.

The poster child is Champagne: INAO publishes one row in the aires CSV
("Champagne") covering all ~320 communes of the appellation, and the
parcellaire shapefile carries no Champagne entries at all (the cahier
defers parcel delimitation to the 1919 law). The grand cru / premier cru
DGCs (id_denomination_geo 56 and 57) inherit no specific geometry and
without an override fall back to the entire Champagne polygon — which is
wrong: the cahier's section II restricts those mentions to a named list
of villages.

Two layers feed `DGC_VILLAGE_INSEE`:

1. **Hand-curated** (this file): Champagne grand cru / premier cru, plus
   any other case where commune mergers, typos, or missing aires-CSV
   coverage need the explicit comments below. Recent Marne mergers:

     Aÿ + Bisseuil + Mareuil-sur-Aÿ  → 51030  Aÿ-Champagne (2016)
     Louvois + Tauxières-Mutry       → 51564  Val de Livre (2016)
     Vertus + Voipreux + Gionges     → 51612  Blancs-Coteaux (2019)
     Coligny                          → 51158  Val-des-Marais (2016)
     Villeneuve-Renneville            → 51627  Villeneuve-Renneville-Chevigny
     Vaudemanges (cahier spelling)    → 51599  Vaudemange
     Oger + Le Mesnil-sur-Oger        → 51367  Le Mesnil-sur-Oger (2025)

   Premier cru is the SUPERSET of grand cru villages (17) + 41 PC-only.

2. **Extracted from parent cahier** (`dgc_village_overrides.json`): IGP
   umbrellas like Aude, Pays d'Hérault, Isère, Coteaux de l'Ain,
   Vaucluse — the parent cahier's section IV enumerates per-DGC commune
   lists in tabular or bullet form, and `scripts/extract_dgc_overrides.py`
   parses them into the JSON sidecar. Re-run that script when the
   underlying cahiers change.

Cases this file deliberately does *not* override (commune-level resolution
can't improve on the parent):
  - Chablis premier cru lieux-dits (~25 missing parcellaire rows) and
    Givry premier cru Le Vernoy: each is a sub-parcel within the parent
    commune. Resolved at sub-commune precision in stage 04 via the
    cadastre lieu-dit step (see `_lib/lieu_dit.py`); the few that still
    fail the fuzzy match (Beauroy, Vaulorent, Côte de Fontenay, Mélinots,
    Côte des Prés-Girots) can be pinned in
    `cadastre_lieu_dit_overrides.json` rather than here.
  - Saint-Véran complété par une dénomination de climat: a usage-mention
    DGC, same commune set as Saint-Véran parent.
"""

from __future__ import annotations

import json
from pathlib import Path

# Champagne grand cru: 17 villages where the appellation may carry
# "grand cru" (and a fortiori "premier cru").
_CHAMPAGNE_GRAND_CRU_INSEE: set[str] = {
    "51007",  # Ambonnay
    "51029",  # Avize
    "51030",  # Aÿ-Champagne (formerly Aÿ)
    "51044",  # Beaumont-sur-Vesle
    "51079",  # Bouzy
    "51153",  # Chouilly
    "51196",  # Cramant
    "51564",  # Val de Livre (formerly Louvois)
    "51338",  # Mailly-Champagne
    "51367",  # Le Mesnil-sur-Oger (now also covers former Oger)
    "51413",  # Oiry
    "51450",  # Puisieulx
    "51536",  # Sillery
    "51576",  # Tours-sur-Marne
    "51613",  # Verzenay
    "51614",  # Verzy
}

# Champagne premier cru-only: the 41 additional villages where the
# appellation may carry "premier cru" only.
_CHAMPAGNE_PREMIER_CRU_EXTRA_INSEE: set[str] = {
    "51028",  # Avenay-Val-d'Or
    "51049",  # Bergères-lès-Vertus
    "51058",  # Bezannes
    "51061",  # Billy-le-Grand
    "51030",  # Aÿ-Champagne (formerly Bisseuil; also formerly Mareuil-sur-Aÿ)
    "51112",  # Chamery
    "51119",  # Champillon
    "51152",  # Chigny-les-Roses
    "51158",  # Val-des-Marais (formerly Coligny)
    "51172",  # Cormontreuil
    "51177",  # Coulommes-la-Montagne
    "51200",  # Cuis
    "51202",  # Cumières
    "51210",  # Dizy
    "51225",  # Écueil
    "51239",  # Étréchy
    "51281",  # Grauves
    "51287",  # Hautvillers
    "51310",  # Jouy-lès-Reims
    "51333",  # Ludes
    "51365",  # Les Mesneux
    "51375",  # Montbré
    "51392",  # Mutigny
    "51422",  # Pargny-lès-Reims
    "51431",  # Pierry
    "51461",  # Rilly-la-Montagne
    "51471",  # Sacy
    "51532",  # Sermiers
    "51562",  # Taissy
    "51564",  # Val de Livre (formerly Tauxières-Mutry)
    "51580",  # Trépail
    "51584",  # Trois-Puits
    "51599",  # Vaudemange
    "51612",  # Blancs-Coteaux (formerly Vertus and Voipreux)
    "51622",  # Ville-Dommange
    "51627",  # Villeneuve-Renneville-Chevigny
    "51629",  # Villers-Allerand
    "51631",  # Villers-aux-Nœuds
    "51636",  # Villers-Marmery
    "51657",  # Vrigny
}


# Pineau des Charentes Île de Ré (id_denom=2953) — 10 communes per
# cahier section IV. INSEE codes verified against IGN AdminExpress.
_PINEAU_ILE_DE_RE_INSEE: set[str] = {
    "17019",  # Ars-en-Ré
    "17051",  # Le Bois-Plage-en-Ré
    "17121",  # La Couarde-sur-Mer
    "17161",  # La Flotte
    "17207",  # Loix
    "17286",  # Les Portes-en-Ré
    "17297",  # Rivedoux-Plage
    "17318",  # Saint-Clément-des-Baleines
    "17360",  # Sainte-Marie-de-Ré
    "17369",  # Saint-Martin-de-Ré
}

# Pays des Bouches-du-Rhône Terre de Camargue (id_denom=2453) —
# 2 communes per cahier section 4 (Arles + Saintes-Maries-de-la-Mer).
# The cahier excludes specific cadastral parcels within Saintes-Maries,
# which we can't represent at commune resolution; the polygon will be
# slightly inflated for that DGC, but vastly more accurate than falling
# back to the entire Bouches-du-Rhône IGP.
_BOUCHES_DU_RHONE_CAMARGUE_INSEE: set[str] = {
    "13004",  # Arles
    "13096",  # Saintes-Maries-de-la-Mer
}


# Pineau des Charentes Île d'Oléron (id_denom=2952) — 8 communes per
# cahier section IV. INSEE codes verified against IGN AdminExpress.
_PINEAU_ILE_D_OLERON_INSEE: set[str] = {
    "17093",  # Le Château-d'Oléron
    "17140",  # Dolus-d'Oléron
    "17323",  # Saint-Denis-d'Oléron
    "17337",  # Saint-Georges-d'Oléron
    "17385",  # Saint-Pierre-d'Oléron
    "17411",  # Saint-Trojan-les-Bains
    "17485",  # Le Grand-Village-Plage
    "17486",  # La Brée-les-Bains
}


def _load_extracted() -> dict[str, frozenset[str]]:
    """Load JSON-sidecar overrides extracted from parent IGP cahiers."""
    path = Path(__file__).resolve().parent / "dgc_village_overrides.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: frozenset(v) for k, v in raw.items()}


# Keyed by id_denomination_geo (string) — the canonical DGC identifier.
# Hand-curated entries first; the extracted JSON sidecar fills in IGP
# umbrella sub-zones (Aude, Pays d'Hérault, Isère, Coteaux de l'Ain,
# Vaucluse, …). Hand-curated entries take priority on key collision.
DGC_VILLAGE_INSEE: dict[str, frozenset[str]] = {
    **_load_extracted(),
    "56": frozenset(_CHAMPAGNE_GRAND_CRU_INSEE),
    "57": frozenset(_CHAMPAGNE_GRAND_CRU_INSEE | _CHAMPAGNE_PREMIER_CRU_EXTRA_INSEE),
    "2453": frozenset(_BOUCHES_DU_RHONE_CAMARGUE_INSEE),
    "2952": frozenset(_PINEAU_ILE_D_OLERON_INSEE),
    "2953": frozenset(_PINEAU_ILE_DE_RE_INSEE),
}
