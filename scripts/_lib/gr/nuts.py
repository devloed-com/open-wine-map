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
# misses. NUTS-2 ids (EL30, EL52, EL53) come from the LEVL_2 layer;
# NUTS-3 ids from LEVL_3. Each mapping is the unit the spec delimits:
#   - the Attica retsina/town cluster → EL30 Αττική (the specs are
#     region-wide for these small PGIs; town-level precision isn't in the
#     spec and would be a guess);
#   - Cyclades / Dodecanese → their NUTS-3 unit (labelled by island list);
#   - Μακεδονία → Drama + Kavala/Thasos (NUTS-3) with Central and West
#     Macedonia (NUTS-2), the thirteen units its single document lists;
#   - Θράκη → Evros + Xanthi + Rodopi, the three Thracian units.
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
    # Its EU single document (OJ C/2026/2625, section 9) lists thirteen
    # regional units: Γρεβενών, Δράμας, Θεσσαλονίκης, Ημαθίας, Καβάλας,
    # Φλώρινας, Καστοριάς, Κοζάνης, Πέλλας, Σερρών, Πιερίας, Χαλκιδικής and
    # (named communities only) Κιλκίς — geographic Macedonia, not Thrace, so
    # EL51 "Ανατολική Μακεδονία, Θράκη" would draw Evros, Xanthi and Rodopi
    # too. EL515 also carries Thasos and EL523 all of Kilkis; the altitude
    # bands the document sets per unit are not drawn.
    # Fallback for a build without the LAU layer; the prefix pin above is
    # what draws the record (EL515 carries Thasos and EL523 all of Kilkis).
    "makedonia": ["EL514", "EL515", "EL52", "EL53"],
    # "a. Περιοχή NUTS GR42 Νότιο Αιγαίο GR41 Βόρειο Αιγαίο" — the name resolver
    # kept one of the two units and drew half the PGI.
    "aegeo-pelagos": ["EL41", "EL42"],
    # "περιλαμβάνει όλες τις περιοχές της Θράκης" — the spec cites the NUTS
    # unit GR11 "Ανατολική Μακεδονία, Θράκη", which would add Drama and
    # Kavala; the text delimits Thrace, i.e. its three regional units.
    "thraki": ["EL511", "EL512", "EL513"],
}

# NOTE: `epanomi` carries no pin either (removed 2026-09-24): its single
# document names "το Δημοτικό Διαμέρισμα Επανομής του Δήμου Θερμαϊκού", one
# GISCO community (79.5 km²), and a pin to EL522 drew all of Θεσσαλονίκη
# (3,689 km²) over it once pins were checked before the commune list.
# NOTE: `ayio-oros` deliberately carries no pin. The spec names its two
# units outright ("τη διοικητική περιοχή του Αγίου Όρους και το όμορο
# δημοτικό διαμέρισμα Ουρανούπολης"), both of which are GISCO LAU
# communities (EL_99010000, 335.9 km²; EL_13020105, 21.7 km²), so the
# commune-list step resolves it at community precision. A coarse
# Χαλκιδική pin here would mask a future parser regression instead of
# letting it surface as stub-no-geometry.


# Curated slug → [GISCO_ID prefix] for PGIs whose text delimits a whole
# municipality or island that no NUTS unit matches and no community list
# names. Greek LAU ids are hierarchical (EL_ + 2 prefecture + 2 municipality
# + 2 municipal unit + 2 community), so a 7-character prefix is a
# Kallikratis δήμος; `GRPolygonIndex.prefix_union` unions its communities.
# Verified against the LAU names under each prefix, 2026-09-24.
_GR_PGI_PREFIX: dict[str, list[str]] = {
    # "την χερσόνησο της Σιθωνίας" — Δήμος Σιθωνίας (Νικήτη, Νέος Μαρμαράς,
    # Συκιά, Σάρτη …), not all of Chalkidiki.
    "sithonia": ["EL_1305"],
    # "περιοχές της νήσου Κω" — Δήμος Κω (Κως, Πυλί, Αντιμάχεια, Κέφαλος …),
    # not the whole Dodecanese NUTS unit.
    "kos": ["EL_6401"],
    # "αμπελώνων που βρίσκονται στη Λέσβο" — the island is the two δήμοι
    # Μυτιλήνης and Δυτικής Λέσβου; the NUTS unit adds Lemnos and Agios
    # Efstratios.
    "lesvos": ["EL_5301", "EL_5302"],
    # "τις Κοινότητες Τρικώμου, Κοσματίου και στην ευρύτερη περιοχή του Ν.
    # Γρεβενών": the whole prefecture (EL_15), not the NUTS-3 unit EL531
    # that also holds Κοζάνη.
    "grevena": ["EL_15"],
    # A whole prefecture or island named by a spec whose NUTS-3 unit pairs
    # it with a neighbour (screened 2026-09-24, every finding refuted twice;
    # each prefix's rows and seat checked against GISCO): the prefecture
    # prefix, not the pair. Altitude bands stay undrawn.
    "argolida": ["EL_41"],   # "στο Νομό Αργολίδας" — EL651 adds Αρκαδία (EL_40)
    "arkadia": ["EL_40"],    # "του Νομού Αρκαδίας" — EL651 adds Αργολίδα (EL_41)
    "karditsa": ["EL_23"],   # "του νομού Καρδίτσας" — EL611 adds Τρίκαλα (EL_26)
    "kozani": ["EL_14"],     # "του Νομού Κοζάνης" — EL531 adds Γρεβενά (EL_15)
    "lakonia": ["EL_43"],    # "του νομού Λακωνίας" — EL653 adds Μεσσηνία (EL_44)
    "messinia": ["EL_44"],   # "του Νομού Μεσσηνίας" — EL653 adds Λακωνία (EL_43)
    "thasos": ["EL_0401"],   # "στη Νήσο Θάσο" — Δήμος Θάσου; EL515 adds Καβάλα (EL_05)
    "ikaria": ["EL_5401"],   # "της νήσου Ικαρίας" — Δήμος Ικαρίας; EL412 adds Σάμος + Φούρνοι
    # "το σύνολο της νήσου Εύβοιας": the island — every Euboean unit of the
    # prefecture EL_29 except Σκύρος (EL_2908) and the two mainland units
    # of Δήμος Χαλκιδέων, Ανθηδόνος (EL_290102) and Αυλίδος (EL_290103),
    # which lie on the Boeotian shore (moved from Επαρχία Θηβών in 1974).
    "retsina-evias": [
        "EL_290101", "EL_290104", "EL_290105",
        "EL_2902", "EL_2903", "EL_2904", "EL_2905", "EL_2906", "EL_2907",
    ],
    # Its EU single document (OJ C/2026/2625, section 9) lists twelve whole
    # regional units — Γρεβενών EL_15, Δράμας EL_02, Θεσσαλονίκης EL_07,
    # Ημαθίας EL_08, Καβάλας EL_05 (not Thasos EL_04, a separate unit),
    # Φλώρινας EL_17, Καστοριάς EL_16, Κοζάνης EL_14, Πέλλας EL_10, Σερρών
    # EL_12, Πιερίας EL_11, Χαλκιδικής EL_13 — and, of Κιλκίς, ten named
    # communities of Δήμος Παιονίας (units Γουμένισσας without Καστανερή,
    # Ευρωπού's Ευρωπός / Πολύπετρο / Τούμπα, and Γοργόπη). The altitude
    # bands the document sets per unit are not drawn. Review 2026-09-24.
    "makedonia": [
        "EL_02", "EL_05", "EL_07", "EL_08", "EL_10", "EL_11", "EL_12", "EL_13",
        "EL_14", "EL_15", "EL_16", "EL_17",
        "EL_09020301", "EL_09020302", "EL_09020303", "EL_09020305", "EL_09020306",
        "EL_09020307", "EL_09020401", "EL_09020404", "EL_09020405", "EL_09020202",
    ],
}


def prefix_ids(slug: str) -> list[str] | None:
    return _GR_PGI_PREFIX.get(slug)


def override_ids(slug: str) -> list[str] | None:
    return _GR_PGI_NUTS.get(slug)
