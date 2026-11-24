"""Does a French cahier set a parcel area of its own?

The card of a record drawn as a commune union says what the polygon is
(`geom_approx_aires_union*`); this module tells the three cases apart that the
first cut of 2026-11-23 — any «aire parcellaire délimitée» in the text — had
lumped together (second look of the same day):

- **own**: the record's parcel area, approved by INAO's committee, its plans
  deposited at the town halls — «l'aire parcellaire délimitée est celle
  approuvée …» (Champagne and the spirits made from its grapes), «2°- Aire
  parcellaire délimitée — Les vins sont issus exclusivement des vignes situées
  dans l'aire parcellaire de production telle qu'approuvée …» (Cassis, Bellet,
  Rosé des Riceys);
- not a parcel *identification* — «parcelles ayant fait l'objet d'une procédure
  d'identification» (Corrèze, Duché d'Uzès), «parcelles identifiées selon des
  critères» (Armagnac) —, which delimits nothing;
- not the parcel areas of other appellations — a marc's «aires parcellaires …
  définies dans les cahiers des charges des appellations …» (Marc du Jura, Marc
  d'Alsace Gewurztraminer), Fine Bordeaux's vines «exclues de l'aire délimitée
  parcellaire» of the Bordeaux AOC; INAO publishes those.

`PUBLISHED_APART` names the records whose own parcel area INAO publishes in a
resource of its own, outside the parcellaire shapefile the build reads: their
card says what is drawn and nothing about the parcels, until the build draws
them (CURATOR_TODO).
"""
from __future__ import annotations

import re

_AREA_RE = re.compile(
    r"\baires?\s+(?:parcellaires?\s+(?:d[ée]limit[ée]es?|de\s+production)"
    r"|d[ée]limit[ée]es?\s+parcellaires?)\b",
    re.IGNORECASE,
)
_APPROVED_RE = re.compile(
    r"\bapprouv[ée]e?s?\b|documents\s+graphiques|plans\s+sont\s+d[ée]pos[ée]s",
    re.IGNORECASE,
)
_NOT_OWN_RE = re.compile(
    r"identifi|cahiers?\s+des\s+charges\s+des\s+appellations|exclues?\s+de\s+l.aire",
    re.IGNORECASE,
)
_BEFORE = 100
_AFTER = 700

PUBLISHED_APART: dict[str, dict[str, str]] = {
    "rhum-de-la-martinique": {
        "resource": (
            "https://static.data.gouv.fr/resources/delimitation-parcellaire-des-aoc-"
            "viticoles-de-linao/20201204-162040/2020-11-25-rhum-de-martinique.zip"
        ),
        "reason": (
            "INAO's dataset «Délimitation parcellaire des AOC viticoles» carries the "
            "rum's parcel area (28 commune shapefiles, approved 3 September 2020) as a "
            "resource of its own, beside the parcellaire shapefile"
        ),
        "verified": "2026-11-23",
    },
}


def sets_own_parcel_area(sections: dict | None) -> bool:
    """True when a section states the record's own approved parcel area."""
    for body in (sections or {}).values():
        if not isinstance(body, str):
            continue
        for m in _AREA_RE.finditer(body):
            ahead = body[m.start(): m.end() + _AFTER]
            around = body[max(0, m.start() - _BEFORE): m.end() + _AFTER]
            if _APPROVED_RE.search(ahead) and not _NOT_OWN_RE.search(around):
                return True
    return False


def parcel_area_note(slug: str, sections: dict | None) -> str | None:
    """`unpublished` / `apart` for a record drawn as a commune union, else None."""
    if not sets_own_parcel_area(sections):
        return None
    return "apart" if slug in PUBLISHED_APART else "unpublished"
