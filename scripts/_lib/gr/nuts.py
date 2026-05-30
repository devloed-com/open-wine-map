"""NUTS-region resolution for Greek PGIs (ΠΓΕ).

The 114 GR PGIs are NOT in Bétard (PDO-only), and their national-spec
"Οριοθετημένη περιοχή" section does NOT enumerate δήμοι — it delimits the
area by reference to the founding ministerial decrees plus a **NUTS code +
regional-unit / region name** (`GR232  Αχαΐα`, `GR30  Αττική`). So the
honest geometry for a GR PGI is the Eurostat GISCO NUTS polygon for that
regional unit (NUTS-3) or region (NUTS-2) — which is exactly what the spec
legally delimits.

This module supplies the country-knowledge layer (no geo deps): a
spec-name extractor + the comma/slash-token name→id matching rule +
a curated `slug → [NUTS_ID]` override for the residual PGIs whose spec
names a unit the NUTS layer labels by island-list (Cyclades, Dodecanese),
whose appellation is an Attica town (the retsina cluster → whole Αττική),
or which span several regions (Μακεδονία). `GRPolygonIndex` in
`geometry.py` owns the polygons and does the union.
"""

from __future__ import annotations

import re

from .eniaio_engrafo import greek_norm

# The spec's "Οριοθετημένη περιοχή" cites the NUTS unit as
# `<GR|EL><digits>  <Greek name>` — capture the trailing name.
_SPEC_NUTS_RE = re.compile(r"\b(?:GR|EL)\d{2,3}\b[ \t]+([Α-ΩΆΈΉΊΌΎΏΪΫA-Z][\wΆ-ώ.\- ]{2,40})")

# Tokens to drop when splitting a NUTS_NAME into matchable units.
_NUTS_NAME_SPLIT_RE = re.compile(r"[,/–-]")


def spec_nuts_name(geo_area_brief: str) -> str:
    """Extract the regional-unit / region name the spec cites, or ''."""
    m = _SPEC_NUTS_RE.search(geo_area_brief or "")
    return m.group(1).strip() if m else ""


def name_tokens(nuts_name: str) -> list[str]:
    """Normalised matchable tokens for a NUTS_NAME (handles the
    island-list NUTS-3 labels, e.g. 'Θάσος, Καβάλα' → ['θασοσ','καβαλα'])."""
    out = []
    for tok in _NUTS_NAME_SPLIT_RE.split(nuts_name or ""):
        k = greek_norm(tok).strip()
        if len(k) >= 4:
            out.append(k)
    return out


# Curated slug → [NUTS_ID] for the residual PGIs that strict name-match
# misses. NUTS-2 ids (EL30, EL42, EL51/52/53) come from the LEVL_2 layer;
# NUTS-3 ids from LEVL_3. Each mapping is the unit the spec delimits:
#   - the Attica retsina/town cluster → EL30 Αττική (the specs are
#     region-wide for these small PGIs; town-level precision isn't in the
#     spec and would be a guess);
#   - Cyclades / Dodecanese → their NUTS-3 unit (labelled by island list);
#   - Μακεδονία → the three Macedonian NUTS-2 regions unioned.
_GR_PGI_NUTS: dict[str, list[str]] = {
    # whole Αττική (NUTS-2 EL30)
    "attiki": ["EL30"],
    "anavyssos": ["EL30"],
    "gerania": ["EL30"],
    "ilion": ["EL30"],
    "markopoulo": ["EL30"],
    "pallini": ["EL30"],
    "spata": ["EL30"],
    "playies-pentelikou": ["EL30"],
    "retsina-attikis": ["EL30"],
    "retsina-koropiou": ["EL30"],
    "retsina-markopoulou-attikis": ["EL30"],
    "retsina-megaron": ["EL30"],
    "retsina-mesogion-attikis": ["EL30"],
    "retsina-pallinis": ["EL30"],
    "retsina-peanias": ["EL30"],
    "retsina-pikermiou": ["EL30"],
    "retsina-spaton": ["EL30"],
    # regional units the spec names but the NUTS-3 label lists by island
    "dodekanisos": ["EL421"],
    "kos": ["EL421"],
    "kiklades": ["EL422"],
    "thapsana": ["EL422"],
    # named regional units (appellation is a town, not the unit name)
    "epanomi": ["EL522"],          # Θεσσαλονίκη
    "nea-mesimvria": ["EL522"],    # Θεσσαλονίκη
    "siatista": ["EL531"],         # Κοζάνη
    "tyrnavos": ["EL612"],         # Λάρισα
    "korinthos": ["EL652"],        # Κορινθία
    "karystos": ["EL642"],         # Εύβοια
    "retsina-halkidas-evias": ["EL642"],   # Εύβοια
    "opountia-lokridas": ["EL644"],        # Φθιώτιδα
    "playies-knimidas": ["EL644"],         # Φθιώτιδα
    "retsina-of-viotia": ["EL641"],        # Βοιωτία
    "halikouna": ["EL622"],        # Κέρκυρα
    "playies-paikou": ["EL524", "EL523"],  # Πέλλα + Κιλκίς (Paiko spans both)
    # interregional umbrella
    "makedonia": ["EL51", "EL52", "EL53"],
}


def override_ids(slug: str) -> list[str] | None:
    return _GR_PGI_NUTS.get(slug)
