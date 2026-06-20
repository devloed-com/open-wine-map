"""Regression tests for the Italy (IT) regional wine-zone matcher.

Focus: the Umbria CKAN `ckan_shapefiles` source in
scripts/_lib/it/zone_sources.py and its name-matching helpers in
scripts/_lib/it/zones.py. The Umbria shapefiles carry the appellation in a
`ZONE` field with a dotted tier prefix ("D.O.C. e D.O.C.G. Montefalco"),
sometimes an "X o Y" alternate name, and a combined DOC+DOCG dataset that
covers the DOCG too — so the stripped+normalised name must resolve to the
right eAmbrosia wine slug. These are the exact `ZONE` strings observed in the
live dati.regione.umbria.it catalog (2026-06).

Pure-function tests — no network, no shapefile read.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.it.zone_sources import ZONE_SOURCES  # noqa: E402
from _lib.it.zones import _name_variants, _norm, _strip_tier  # noqa: E402

UMBRIA = ZONE_SOURCES["umbria"]


def test_umbria_source_is_active_ckan():
    assert UMBRIA["status"] == "active"
    assert UMBRIA["fetch_type"] == "ckan_shapefiles"
    assert UMBRIA["name_field"] == "ZONE"
    # Shapefiles ship without a .prj, so a CRS must be declared.
    assert UMBRIA["crs"] == "EPSG:3004"


def test_strip_tier_handles_dotted_prefixes():
    strip = lambda z: _strip_tier(z, UMBRIA)  # noqa: E731
    # Plain DOC / IGT, including the dataset's irregular "D.O.C ." spacing.
    assert strip("D.O.C . Orvieto Classico") == "Orvieto Classico"
    assert strip("D.O.C.  Amelia") == "Amelia"
    assert strip("I.G.T. Umbria") == "Umbria"
    # Combined "D.O.C. e D.O.C.G." with and without a space before the name.
    assert strip("D.O.C. e D.O.C.G. Montefalco") == "Montefalco"
    assert strip("D.O.C. e D.O.C.G.Torgiano") == "Torgiano"
    # Undotted "DOC ".
    assert strip("DOC Rosso Orvietano o Orvietano Rosso") == "Rosso Orvietano o Orvietano Rosso"


def test_strip_tier_never_bites_into_a_real_name():
    # Every Umbria appellation name begins with a non-D/I letter, so the
    # anchored tier regex must leave names that merely contain D/I/O/G/C/T
    # intact (no prefix to strip means the input is returned unchanged).
    assert _strip_tier("Colli del Trasimeno", UMBRIA) == "Colli del Trasimeno"
    assert _strip_tier("Todi", UMBRIA) == "Todi"


def test_alt_name_split_recovers_both_halves():
    # "Rosso Orvietano o Orvietano Rosso" — the Italian " o " separates two
    # spellings; both are indexed so the eAmbrosia "Rosso Orvietano" resolves.
    variants = _name_variants("Rosso Orvietano o Orvietano Rosso", UMBRIA)
    assert "Rosso Orvietano" in variants
    assert "Orvietano Rosso" in variants
    assert _norm("Rosso Orvietano") in {_norm(v) for v in variants}


def test_combined_docg_alias_covers_the_docg():
    # The single "Montefalco" / "Torgiano" polygon (DOC + DOCG share the
    # delimited area) must also resolve the DOCG sub-name.
    assert "Montefalco Sagrantino" in _name_variants("Montefalco", UMBRIA)
    assert "Torgiano Rosso Riserva" in _name_variants("Torgiano", UMBRIA)
    # A name with no curated extra is returned as-is.
    assert _name_variants("Amelia", UMBRIA) == ["Amelia"]


def test_stripped_names_normalise_to_eambrosia_slugs():
    # End-to-end: the ZONE string, once stripped + variant-expanded + normed,
    # must equal the eAmbrosia wine's normalised name for the four cases that
    # needed special handling.
    def norms(zone: str) -> set[str]:
        return {_norm(v) for v in _name_variants(_strip_tier(zone, UMBRIA), UMBRIA)}

    assert _norm("Rosso Orvietano") in norms("DOC Rosso Orvietano o Orvietano Rosso")
    assert _norm("Montefalco Sagrantino") in norms("D.O.C. e D.O.C.G. Montefalco")
    assert _norm("Torgiano Rosso Riserva") in norms("D.O.C. e D.O.C.G.Torgiano")
    assert _norm("Orvieto") in norms("D.O.C . Orvieto")
