"""Darnibole PDO — an approximate boundary derived from the regulator's plan.

`PDO-GB-N1636` Darnibole is a single-vineyard PDO at Camel Valley,
Nanstallon (Cornwall). Its product specification defines the demarcated
area **narratively** — "bordered to the West by a marked soil change to
alluvial sand (the old River Camel river bed) … The disused railway (now
the Camel Trail) demarcates the Southern boundary" — with no coordinates,
and no public polygon of it exists anywhere.

What the specification *does* carry is a **"Plan of demarcated area"**
(page 5 of `protected-food-name-darnibole-wine.pdf`): an OS-based Rural
Payments Agency land-parcel map with the PDO boundary drawn in red over
numbered field parcels, each labelled "Vines planted" / "Not yet planted".

Those parcel numbers are not arbitrary ids. Under the OS / RPA
convention a field parcel is identified by the **four-figure National
Grid reference of its centroid within its 1 km grid square** — two
digits of easting then two of northing, each in units of 10 m. So
parcel `7985` sits at 790 m E, 850 m N inside its square.

That makes the plan georeferenceable, and this module reconstructs an
approximate boundary from it: the convex hull of the centroids of the
seven parcels the red line encloses.

**Anchoring the square** (SX 03 67 → BNG easting base 203000, northing
base 67000) was verified three ways:

  1. *Internal consistency.* Decoded north→south and west→east order
     reproduces the plan's layout exactly, including the 1 km grid line
     visible on the plan between parcels 5107/8101 (N 68xxx) and 5095
     (N 67950).
  2. *Terrain.* An elevation transect north from the block (EU-DEM 25 m)
     puts the valley floor at 11–14 m over N 67300–67400 and climbs
     steadily to 96 m by N 68100. The seven parcels sit at 47–80 m on a
     ~13 % south-facing slope immediately above the old river bed —
     precisely the specification's "steep south facing slope", bounded
     south by the River Camel's old bed and north by land "above the
     optimum thermal band".
  3. *Address.* The ONS centroid of Camel Valley's postcode (PL30 5LG)
     is E 203164 N 67751 — on the same slope, ~330 m west of the block.

**Accuracy.** The hull spans E 203490–203890 / N 67680–67950 and
measures **6.1 ha** against the specification's declared "whole 5
hectare area" — so it is the right size in the right place, but it is a
reconstruction, not an official boundary: it interpolates between parcel
centroids rather than tracing the red line itself, so its edges fall
inside the true boundary by up to roughly half a field. Records built
from it carry `geom_approximate: True` and `geom_source:
"pdo-plan-parcel-hull-approx"` so the map panel can disclose it.

Source: Product specification for Darnibole (PDO), DEFRA / GOV.UK,
Open Government Licence v3.0.
"""

from __future__ import annotations

from shapely.geometry import MultiPoint
from shapely.geometry.base import BaseGeometry

# BNG easting/northing base of OS 1 km square SX 03 67.
_SQUARE_E0 = 203000
_SQUARE_N0 = 67000

# The parcels enclosed by the red demarcation line on the plan, keyed by
# the RPA parcel number printed on it → (easting, northing) within the
# square in units of 10 m, plus the plan's own planting label.
DEMARCATED_PARCELS: dict[str, tuple[int, int, str]] = {
    "5095": (50, 95, "not yet planted"),
    "7985": (79, 85, "vines planted"),
    "4976": (49, 76, "vines planted"),
    "7873": (78, 73, "vines planted"),
    "6372": (63, 72, "vines planted"),
    "7270": (72, 70, "vines planted"),
    "8968": (89, 68, "vines planted"),
}

# Parcels drawn on the plan but OUTSIDE the red line, kept for
# provenance: 5317 / 5107 / 6921 / 8101 lie north of it, 6661 and 8748
# (the older, hatched Camel Valley rows) south of it.
EXCLUDED_PARCELS: tuple[str, ...] = ("5317", "5107", "6921", "8101", "6661", "8748")

GEOM_SOURCE = "pdo-plan-parcel-hull-approx"
SOURCE_LABEL = (
    "Approximate — reconstructed from the parcel references on the "
    "PDO specification's plan of the demarcated area"
)
SOURCE_URL = (
    "https://assets.publishing.service.gov.uk/media/5fd36a7ad3bf7f3061e108aa/"
    "protected-food-name-darnibole-wine.pdf"
)


def parcel_points_bng() -> list[tuple[int, int]]:
    """The seven demarcated parcel centroids in EPSG:27700."""
    return [
        (_SQUARE_E0 + e * 10, _SQUARE_N0 + n * 10)
        for e, n, _label in DEMARCATED_PARCELS.values()
    ]


def boundary_bng() -> BaseGeometry:
    """Approximate Darnibole boundary in EPSG:27700 (British National Grid)."""
    return MultiPoint(parcel_points_bng()).convex_hull
