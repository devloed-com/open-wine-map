"""FR appellation → wine-region bucket for the map facet, the underlay and
every place the page names its region (title, description, meta line,
JSON-LD containedInPlace).

INAO's comité régional is an administrative grouping, not a wine region:
BOURGOGNE bundles Burgundy, Beaujolais, Jura, Savoie and Bugey; SUD-OUEST
holds every Bordeaux AOC beside Bergerac and Duras (Pauillac was titled
"South-West, France" until 2026-09-26); LANGUEDOC-ROUSSILLON, PROVENCE-CORSE
and ALSACE ET EST each pair two regions; VIN DOUX NATURELS and EAUX-DE-VIE
DE CIDRE are product groupings that span three regions apiece; and every IGP
carries no comité at all. The raw `comite_regional` value on each record
stays untouched (regulator data, preserved in the cahier-extracted JSON);
this helper is only consumed by stage 04 when emitting the `region`
property.

Resolution, in order:

1. BOURGOGNE — split by slug rule (Jura / Savoie / Bugey / Beaujolais /
   Burgundy), as before.
2. A comité that names one wine region passes through, renamed where the
   comité's own name is not the region's (TOULOUSE-PYRENEES → SUD-OUEST).
3. A comité that spans several regions, or no comité, is placed by the
   dominant département of the appellation's INAO aire (the aires-communes
   CSV, the same public table the polygon is drawn from) through
   `_DEPARTEMENT_BUCKET`; the cider comité reads the same table with its own
   Maine bucket, because Mayenne and Sarthe are Loire for wine and Maine for
   cider.
4. `_SLUG_BUCKET` pins the residue: a record whose aire the CSV does not
   carry under its SIQO name, and the few whose dominant département would
   mislead. Each pin says why.

DGCs ride their parent's bucket via `parent_slug`; the caller passes the
parent's départements for them.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

_JURA_SLUGS: frozenset[str] = frozenset({
    "arbois",
    "arbois-pupillin",
    "chateau-chalon",
    "cotes-du-jura",
    "cremant-du-jura",
    "l-etoile",
    "macvin-du-jura",
    "marc-du-jura",
})

_BEAUJOLAIS_CRU_SLUGS: frozenset[str] = frozenset({
    "brouilly",
    "chenas",
    "chiroubles",
    "cote-de-brouilly",
    "fleurie",
    "julienas",
    "morgon",
    "moulin-a-vent",
    "regnie",
    "saint-amour",
})

_SAVOIE_EXTRA_SLUGS: frozenset[str] = frozenset({
    "seyssel",
    "cremant-de-savoie",
    "marc-de-savoie",
    "mousseux-de-savoie",
})

_SAVOIE_PREFIXES: tuple[str, ...] = (
    "vin-de-savoie",
    "roussette-de-savoie",
)

_BUGEY_PREFIXES: tuple[str, ...] = (
    "bugey",
    "roussette-du-bugey",
)

# Two BOURGOGNE-bassin appellations lie outside Burgundy proper: Côtes du
# Forez sits in the upper Loire beside Côte roannaise and Côtes d'Auvergne
# (which INAO itself files under VAL DE LOIRE), and Coteaux du Lyonnais
# continues the Beaujolais granite south of Lyon.
_LOIRE_SLUGS: frozenset[str] = frozenset({
    "cotes-du-forez",
})

_LYONNAIS_SLUGS: frozenset[str] = frozenset({
    "coteaux-du-lyonnais",
})

# Comités that name exactly one wine region, under the region's own name.
_COMITE_BUCKET: dict[str, str] = {
    "VAL DE LOIRE": "VAL DE LOIRE",
    "VALLEE DU RHÔNE": "VALLEE DU RHÔNE",
    "CHAMPAGNE": "CHAMPAGNE",
    "ARMAGNAC": "ARMAGNAC",
    "RHUM": "RHUM",
    # INAO's second south-western comité (Cahors, Madiran, Gaillac, Jurançon,
    # the Aveyron AOCs): one wine region with SUD-OUEST in every reference.
    "TOULOUSE-PYRENEES": "SUD-OUEST",
}

# Comités that span two or more wine regions: the département decides.
_SPLIT_COMITES: frozenset[str] = frozenset({
    # INAO files Whisky breton under the Cognac comité; the Charentes
    # départements keep Cognac and Pineau where they are.
    "COGNAC",
    "SUD-OUEST",
    "LANGUEDOC-ROUSSILLON",
    "PROVENCE-CORSE",
    "ALSACE ET EST",
    "VIN DOUX NATURELS",
    "EAUX-DE-VIE DE CIDRE",
})

# INAO's upper-case ASCII département spelling (the aires-communes CSV
# `Département` column) → wine-region bucket. Only départements a record
# reaches through steps 2–3 matter; the ambiguous ones (Rhône holds both
# Beaujolais and the northern Rhône, Loire both Forez and Saint-Joseph,
# Saône-et-Loire both the Mâconnais and Saint-Amour) are never consulted for
# a record whose comité already names the region, so their entry is the
# default for a comité-less IGP.
_DEPARTEMENT_BUCKET: dict[str, str] = {
    "GIRONDE": "BORDEAUX",
    "DORDOGNE": "SUD-OUEST",
    "LOT-ET-GARONNE": "SUD-OUEST",
    "LOT": "SUD-OUEST",
    "TARN": "SUD-OUEST",
    "TARN-ET-GARONNE": "SUD-OUEST",
    "GERS": "SUD-OUEST",
    "LANDES": "SUD-OUEST",
    "PYRENEES-ATLANTIQUES": "SUD-OUEST",
    "HAUTES-PYRENEES": "SUD-OUEST",
    "AVEYRON": "SUD-OUEST",
    "HAUTE-GARONNE": "SUD-OUEST",
    "ARIEGE": "SUD-OUEST",
    "CORREZE": "SUD-OUEST",
    "HAUTE-VIENNE": "SUD-OUEST",
    "CANTAL": "SUD-OUEST",
    "PYRENEES-ORIENTALES": "ROUSSILLON",
    "AUDE": "LANGUEDOC",
    "HERAULT": "LANGUEDOC",
    "GARD": "LANGUEDOC",
    "LOZERE": "LANGUEDOC",
    "VAUCLUSE": "VALLEE DU RHÔNE",
    "DROME": "VALLEE DU RHÔNE",
    "ARDECHE": "VALLEE DU RHÔNE",
    "RHONE": "VALLEE DU RHÔNE",
    "VAR": "PROVENCE",
    "BOUCHES-DU-RHONE": "PROVENCE",
    "ALPES-MARITIMES": "PROVENCE",
    "ALPES-DE-HAUTE-PROVENCE": "PROVENCE",
    "HAUTES-ALPES": "PROVENCE",
    "CORSE-DU-SUD": "CORSE",
    "HAUTE-CORSE": "CORSE",
    "BAS-RHIN": "ALSACE",
    "HAUT-RHIN": "ALSACE",
    "MOSELLE": "LORRAINE",
    "MEURTHE-ET-MOSELLE": "LORRAINE",
    "MEUSE": "LORRAINE",
    "VOSGES": "LORRAINE",
    "MARNE": "CHAMPAGNE",
    "AUBE": "CHAMPAGNE",
    "AISNE": "CHAMPAGNE",
    "HAUTE-MARNE": "CHAMPAGNE",
    "ARDENNES": "CHAMPAGNE",
    "SEINE-ET-MARNE": "ILE-DE-FRANCE",
    "PARIS": "ILE-DE-FRANCE",
    "YVELINES": "ILE-DE-FRANCE",
    "ESSONNE": "ILE-DE-FRANCE",
    "HAUTS-DE-SEINE": "ILE-DE-FRANCE",
    "SEINE-SAINT-DENIS": "ILE-DE-FRANCE",
    "VAL-DE-MARNE": "ILE-DE-FRANCE",
    "VAL-D'OISE": "ILE-DE-FRANCE",
    "SAVOIE": "SAVOIE",
    "HAUTE-SAVOIE": "SAVOIE",
    "ISERE": "SAVOIE",
    "AIN": "BUGEY",
    "JURA": "JURA",
    "DOUBS": "JURA",
    "HAUTE-SAONE": "JURA",
    "TERRITOIRE DE BELFORT": "JURA",
    "COTE-D'OR": "BOURGOGNE",
    "SAONE-ET-LOIRE": "BOURGOGNE",
    "YONNE": "BOURGOGNE",
    "NIEVRE": "VAL DE LOIRE",
    "CHER": "VAL DE LOIRE",
    "INDRE": "VAL DE LOIRE",
    "INDRE-ET-LOIRE": "VAL DE LOIRE",
    "LOIR-ET-CHER": "VAL DE LOIRE",
    "LOIRET": "VAL DE LOIRE",
    "MAINE-ET-LOIRE": "VAL DE LOIRE",
    "LOIRE-ATLANTIQUE": "VAL DE LOIRE",
    "VENDEE": "VAL DE LOIRE",
    "VIENNE": "VAL DE LOIRE",
    "DEUX-SEVRES": "VAL DE LOIRE",
    "SARTHE": "VAL DE LOIRE",
    "MAYENNE": "VAL DE LOIRE",
    "ALLIER": "VAL DE LOIRE",
    "PUY-DE-DOME": "VAL DE LOIRE",
    "HAUTE-LOIRE": "VAL DE LOIRE",
    "LOIRE": "VAL DE LOIRE",
    "EURE-ET-LOIR": "VAL DE LOIRE",
    "CHARENTE": "COGNAC",
    "CHARENTE-MARITIME": "COGNAC",
    "CALVADOS": "NORMANDIE",
    "MANCHE": "NORMANDIE",
    "ORNE": "NORMANDIE",
    "EURE": "NORMANDIE",
    "SEINE-MARITIME": "NORMANDIE",
    "FINISTERE": "BRETAGNE",
    "COTES-D'ARMOR": "BRETAGNE",
    "ILLE-ET-VILAINE": "BRETAGNE",
    "MORBIHAN": "BRETAGNE",
    "MARTINIQUE": "RHUM",
    "GUADELOUPE": "RHUM",
    "GUYANE": "RHUM",
    "LA REUNION": "RHUM",
}

# The cider comité's aire runs from the Cotentin to the Sarthe; Maine is a
# cider region of its own (Pommeau du Maine) where the same départements
# are Loire for wine.
_CIDRE_DEPARTEMENT_BUCKET: dict[str, str] = {
    "MAYENNE": "MAINE",
    "SARTHE": "MAINE",
}

# Records the département rule cannot place: their SIQO name binds to no
# aires-CSV row (so no département profile), or the dominant département
# would put them in the wrong region. Keyed by the parent slug.
_SLUG_BUCKET: dict[str, str] = {
    # Nièvre is Loire for Pouilly-Fumé and Côtes de la Charité; the Tannay
    # vineyard on the Yonne is the old Burgundy vignoble of the Nivernais.
    "coteaux-de-tannay": "BOURGOGNE",
    # Whole-region IGPs whose dominant département is a technicality
    # (Méditerranée is not pinned: its Drôme majority places it and its two
    # Drôme DGCs in the Rhône valley, where the same-named DGCs of IGP Drôme
    # already are).
    "ile-de-france": "ILE-DE-FRANCE",
    "val-de-loire": "VAL DE LOIRE",
    "pays-d-oc": "LANGUEDOC",
    "comtes-rhodaniens": "VALLEE DU RHÔNE",
    "collines-rhodaniennes": "VALLEE DU RHÔNE",
    "atlantique": "BORDEAUX",
    "comte-tolosan": "SUD-OUEST",
    "cotes-de-gascogne": "SUD-OUEST",
    "franche-comte": "JURA",
    "vin-des-allobroges": "SAVOIE",
    "lorraine": "LORRAINE",
    "ile-de-beaute": "CORSE",
    "cidre-de-bretagne-ou-cidre-breton": "BRETAGNE",
    "cidre-de-normandie-ou-cidre-normand": "NORMANDIE",
    # Marc d'Alsace Gewurztraminer: a spirit AOC with no comité on the SIQO
    # manifest row and no aires-CSV row of its own.
    "marc-d-alsace-gewurztraminer": "ALSACE",
    # Montpeyroux (AOC since the arrêté du 11 août 2026, Hérault): the split
    # LANGUEDOC-ROUSSILLON comité and no aires-CSV row yet — the 2025-10-09
    # CSV predates the appellation.
    "montpeyroux": "LANGUEDOC",
    # Names the aires CSV carries under another spelling than SIQO's, or
    # under two ("Alsace" and "Vin d'Alsace" are both rows, so the register
    # alias step declines).
    "cotes-du-lot": "SUD-OUEST",
    "alsace-ou-vin-d-alsace": "ALSACE",
    # INAO files Pierrevert under the Rhône comité; every commune of its aire
    # is in Alpes-de-Haute-Provence and the references list it with Provence.
    "pierrevert": "PROVENCE",
    # IGP Coteaux de l'Ain covers the whole département: Bugey for want of a
    # better name (Pays de Gex, Revermont and Val de Saône are DGCs of it).
    "coteaux-de-l-ain": "BUGEY",
}


# Départements of the BOURGOGNE comité that are Burgundy (or a Beaujolais
# cru's Rhône): a BOURGOGNE record whose aire lies elsewhere and matches no
# slug rule (Kirsch de Fougerolles, Haute-Saône) is placed by département.
_BOURGOGNE_DEPARTEMENTS: frozenset[str] = frozenset({
    "COTE-D'OR", "SAONE-ET-LOIRE", "YONNE", "NIEVRE", "RHONE",
})


def _bourgogne_bucket(target: str) -> str:
    if target in _LOIRE_SLUGS:
        return "VAL DE LOIRE"
    if target in _LYONNAIS_SLUGS:
        return "BEAUJOLAIS"
    if target in _JURA_SLUGS:
        return "JURA"
    if target.startswith(_BUGEY_PREFIXES):
        return "BUGEY"
    if target.startswith(_SAVOIE_PREFIXES) or target in _SAVOIE_EXTRA_SLUGS:
        return "SAVOIE"
    if target.startswith("beaujolais") or target in _BEAUJOLAIS_CRU_SLUGS:
        return "BEAUJOLAIS"
    return "BOURGOGNE"


def dominant_departement(departements: Counter | dict[str, int] | None) -> str:
    """The département with the most commune rows, INAO spelling; '' when
    the profile is empty."""
    if not departements:
        return ""
    return max(departements, key=lambda d: (departements[d], d)).upper()


def derive_wine_region(
    record: dict[str, Any], departements: Counter | dict[str, int] | None = None
) -> str:
    """Return the wine-region bucket for an FR record (see the module doc).

    `departements` is the record's aire département profile from
    `aires.lookup_departements` (the parent's, for a DGC). Without it the
    split comités fall back to their comité name and a comité-less record
    to '' — the pre-2026-09-26 behaviour, kept so a caller without the CSV
    still gets the regulator's grouping rather than a guess.
    """
    bassin = record.get("comite_regional") or ""
    slug = record.get("slug") or ""
    target = record.get("parent_slug") or slug
    dept = dominant_departement(departements)
    if bassin == "BOURGOGNE":
        bucket = _bourgogne_bucket(target)
        if bucket == "BOURGOGNE" and dept and dept not in _BOURGOGNE_DEPARTEMENTS:
            return _DEPARTEMENT_BUCKET.get(dept, bucket)
        return bucket
    if slug in _SLUG_BUCKET:
        return _SLUG_BUCKET[slug]
    if target in _SLUG_BUCKET:
        return _SLUG_BUCKET[target]
    if bassin in _COMITE_BUCKET:
        return _COMITE_BUCKET[bassin]
    if bassin and bassin not in _SPLIT_COMITES:
        return bassin
    if bassin == "EAUX-DE-VIE DE CIDRE" and dept in _CIDRE_DEPARTEMENT_BUCKET:
        return _CIDRE_DEPARTEMENT_BUCKET[dept]
    if dept in _DEPARTEMENT_BUCKET:
        return _DEPARTEMENT_BUCKET[dept]
    return bassin


FR_WINE_REGIONS: tuple[str, ...] = (
    "BOURGOGNE", "BEAUJOLAIS", "JURA", "SAVOIE", "BUGEY", "ALSACE", "LORRAINE",
    "CHAMPAGNE", "ILE-DE-FRANCE", "VAL DE LOIRE", "BORDEAUX", "SUD-OUEST",
    "VALLEE DU RHÔNE", "LANGUEDOC", "ROUSSILLON", "PROVENCE", "CORSE",
    "NORMANDIE", "BRETAGNE", "MAINE", "COGNAC", "ARMAGNAC", "RHUM",
)
