"""The seat of a commune nouvelle is drawn as the cahier names it
(scripts/_lib/fr/seat_communes.py): its former outline where the text names the
former commune or restricts the commune of today, the whole commune otherwise."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.fr import former_communes as FC  # noqa: E402
from _lib.fr import seat_communes as SC  # noqa: E402
from _lib.geom_chain import union_from_insee  # noqa: E402


def _square(x: float, y: float, size: float = 1.0) -> dict:
    return {"type": "Polygon", "coordinates": [[
        [x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]]}


# Putanges-le-Lac (61339) = Putanges-Pont-Écrepin (the seat) + Chênedouit (61106,
# its own outline) + La Forêt-Auvray (61174, its own outline)
NAMES = {"61339": "Putanges-le-Lac", "61001": "Alençon"}
INSEE = {"61339": _square(0, 0, 3), "61001": _square(10, 0)}


def _former() -> FC.FormerCommunes:
    return FC.FormerCommunes(
        geoms={"61106": _square(1, 0), "61174": _square(2, 0)},
        names={"61106": "Chênedouit", "61174": "La Forêt-Auvray"},
        successor={"61106": "61339", "61174": "61339"},
        predecessors={"61339": {"61339", "61106", "61174"}},
        seats={"61339": _square(0, 0)},
        seat_names={"61339": "Putanges-Pont-Écrepin"},
    )


def _record(zone: str) -> dict:
    return {"slug": "x", "section_roles": {"aire": zone}}


def _seats(zone: str, codes=frozenset({"61339", "61001"})) -> dict:
    return SC.narrowed_seats(_record(zone), set(codes), NAMES, _former())


def test_old_name_narrows_to_the_seat():
    seats = _seats("Département de l'Orne : Alençon, Putanges-Pont-Écrepin, Rabodanges.")
    assert seats["61339"]["parts"] == ["61339"]
    assert seats["61339"]["why"] == "old-name"
    geom, stats = union_from_insee({"61339", "61001"}, INSEE, _former(), seats)
    assert round(geom.area, 6) == 2.0          # Alençon + the seat's square, not the 9 of the commune
    assert stats["seats_narrowed"] == ["Putanges-le-Lac → Putanges-Pont-Écrepin"]
    assert stats["matched"] == 2


def test_another_former_commune_the_text_names_is_drawn_too():
    seats = _seats("Département de l'Orne : Chênedouit, Putanges-Pont-Écrepin.")
    assert seats["61339"]["parts"] == ["61106", "61339"]


def test_every_former_commune_named_is_the_whole_commune():
    assert _seats("Orne : Chênedouit, La Forêt-Auvray, Putanges-Pont-Écrepin.") == {}


def test_commune_of_today_unrestricted_stays_whole():
    assert _seats("Département de l'Orne : Alençon, Putanges-le-Lac, Rabodanges.") == {}
    # both names: the list of today wins
    assert _seats("Orne : Putanges-le-Lac. Anciennement : Putanges-Pont-Écrepin.") == {}


def test_restriction_names_the_parts():
    seats = _seats("Orne : Putanges-le-Lac (pour le seul territoire des communes déléguées "
                   "de Chênedouit et Putanges-Pont-Écrepin), Rabodanges.")
    assert seats["61339"]["parts"] == ["61106", "61339"]
    assert seats["61339"]["why"] == "restricted"
    # a restriction that leaves the seat out draws the named former commune alone
    seats = _seats("Orne : Putanges-le-Lac pour le seul territoire de la commune déléguée de "
                   "Chênedouit, Rabodanges.")
    assert seats["61339"]["parts"] == ["61106"]
    geom, _ = union_from_insee({"61339"}, INSEE, _former(), seats)
    assert geom.bounds == (1.0, 0.0, 2.0, 1.0)


def test_restriction_to_the_old_commune():
    seats = _seats("Orne : Putanges-le-Lac (pour le seul territoire de l'ancienne commune de "
                   "Putanges-Pont-Écrepin).")
    assert seats["61339"]["parts"] == ["61339"]


def test_same_name_before_and_after_is_not_decided_by_name():
    former = _former()
    former.seat_names["61339"] = "Putanges-le-Lac"
    zone = "Orne : Alençon, Putanges-le-Lac."
    assert SC.narrowed_seats(_record(zone), {"61339"}, NAMES, former) == {}
    # … but an explicit restriction is
    zone = "Orne : Putanges-le-Lac (pour le seul territoire de la commune déléguée de Putanges-le-Lac)."
    assert SC.narrowed_seats(_record(zone), {"61339"}, NAMES, former)["61339"]["parts"] == ["61339"]


def test_same_name_is_decided_by_the_date_of_the_list():
    former = _former()
    former.seat_names["61339"] = "Putanges-le-Lac"
    former.merged_on = {"61106": "2016-01-01", "61174": "2016-01-01"}
    zone = "Orne : Alençon, Putanges-le-Lac."
    older = {"section_roles": {"aire": zone}, "source": {"homologated_at": "2015-02-13"}}
    assert SC.narrowed_seats(older, {"61339"}, NAMES, former)["61339"]["why"] == "dated"
    newer = {"section_roles": {"aire": zone}, "source": {"homologated_at": "2021-12-17"}}
    assert SC.narrowed_seats(newer, {"61339"}, NAMES, former) == {}
    # the code officiel géographique year is the list's date; 1 January of the merger year holds the merger
    cog = lambda y: {"section_roles": {"aire": zone}, "source": {"homologated_at": "2024-01-01"},  # noqa: E731
                     "sections": {"IV": f"sur la base du code officiel géographique de l'année {y} : …"}}
    assert SC.narrowed_seats(cog(2015), {"61339"}, NAMES, former)["61339"]["parts"] == ["61339"]
    assert SC.narrowed_seats(cog(2016), {"61339"}, NAMES, former) == {}
    # a different name of today, named without restriction, is the commune of today whatever the date
    assert SC.narrowed_seats(older, {"61339"}, NAMES, _former()) == {}


def test_rows_that_carry_every_former_commune_are_left_alone():
    assert _seats("Orne : Putanges-Pont-Écrepin.", {"61339", "61106", "61174"}) == {}


def test_a_former_commune_of_the_rows_without_outline_keeps_the_commune_whole():
    former = _former()
    del former.geoms["61174"]
    zone = "Orne : Putanges-Pont-Écrepin."
    # 61174 is in the rows and has no outline: the commune of today is its only drawing
    assert SC.narrowed_seats(_record(zone), {"61339", "61174"}, NAMES, former) == {}
    # absent from the rows, it is simply not part of the aire
    assert SC.narrowed_seats(_record(zone), {"61339"}, NAMES, former)["61339"]["parts"] == ["61339"]


def test_no_seat_outline_no_narrowing():
    former = _former()
    former.seats.clear()
    assert SC.narrowed_seats(_record("Orne : Putanges-Pont-Écrepin."), {"61339"}, NAMES, former) == {}
    assert SC.narrowed_seats(_record("Orne : Putanges-Pont-Écrepin."), {"61339"}, NAMES, None) == {}


def test_homonym_under_another_departement_is_not_the_seat():
    zone = ("Département du Calvados : Putanges-Pont-Écrepin, Vire. "
            "Département de l'Orne : Alençon, Rabodanges.")
    assert _seats(zone) == {}


def test_proximity_zone_is_not_the_aire():
    zone = ("Orne : Alençon. Aire de proximité immédiate : Putanges-Pont-Écrepin.")
    assert _seats(zone) == {}


def test_union_without_seats_is_unchanged():
    geom, stats = union_from_insee({"61339", "61001"}, INSEE, _former())
    assert round(geom.area, 6) == 10.0
    assert "seats_narrowed" not in stats


def test_cog_year():
    rec = {"sections": {"IV": "… sur la base du code officiel géographique de l’année 2020 : Bandol."}}
    assert SC.cog_year(rec) == "2020"
    assert SC.cog_year({"sections": {"IV": "Bandol."}}) is None


def test_layer_loads_the_seat_outlines():
    if not (FC.FORMER_GEOJSON.exists() and FC.MOVEMENTS_CSV.exists()):
        return
    import json
    current = {f["properties"]["code"] for f in json.loads(
        (ROOT / "raw/ign/communes.geojson").read_text(encoding="utf-8"))["features"]}
    former = FC.load(current, log=False)
    assert former.seat_names.get("61339") == "Putanges-Pont-Écrepin"
    assert "61339" in former.seats and "61339" not in former.geoms
