"""Former French communes: what a pre-merger INSEE code is drawn as.

INAO's aires-communes rows keep the commune code of the day each row was
written. A commune merged since is no longer in IGN's commune layer, and until
2026-11-13 its code was simply skipped. INAO usually writes the commune of
today beside its former communes, so most skipped codes cost nothing; the
ground was lost where the rows carry the former communes alone (with them
drawn, Eau-de-vie de cidre du Maine gained 23 % of area, Cidre Cotentin 8 %,
Domfront 6 %, Calvados 3 %). Three public facts settle most of them
(`resolve`):

- **its own outline** — the merger kept the former commune as a commune
  déléguée or associée, and geo.api.gouv.fr (IGN AdminExpress) still serves
  its outline under its code, or under the code a change of département gave
  it on the way (Le Fresne-sur-Loire 44060 → 49382, Freigné 49144 → 44225):
  drawn exactly;
- **its commune of today is in the aire** — INSEE's movements table gives the
  commune the code ended in; when the aire's rows carry that commune it is
  drawn whole already and the former commune lies inside it: nothing to add;
- **a new code for the same ground** — a commune of today whose every former
  commune is in the aire's rows (a change of code, a commune nouvelle under a
  new code): drawn whole.

What is left — a former commune fused without trace into a commune the aire
does not list — has no outline of its own in any public layer. It is not
drawn and is named on the card; drawing the commune of today would draw
ground the delimitation never held.

The mirror case — a row that bears the code of a commune of today because the
commune it was written for became the seat of a commune nouvelle — is
`seat_communes.py`: the cahier's wording decides whether the commune of today
or only its seat is in the aire.

One class is never drawn and never named (`Resolution.elsewhere`): a code
whose ground **left its département before any cahier in force was written**.
INAO's commune table still holds Chassieu, Meyzieu and 22 more communes under
the `38…` codes they lost when they passed from Isère to the Rhône in 1967,
six communes of the Ain likewise, and Frettes (Haute-Marne until 1974, a part
of Champlitte in Haute-Saône since); its rows for IGP Isère, IGP Coteaux de
l'Ain, IGP Haute-Marne and Génépi des Alpes carry them, and each of those
cahiers delimits "le département de …". The cahier wins: ground outside the
département it names is not in the aire. The class holds only where the aire
has no commune of today in the département the ground went to: Antorpe left
the Jura for the Doubs in 1974, and IGP Franche-Comté spans both, so its code
is resolved like any other. So is a commune that crossed a département border
after the cahiers (Pont-Farcy, 2018).

INAO's table also keeps communes INSEE calls "périmées" (its `Actual` = 3):
- one **suppressed and shared out** between its neighbours (INSEE event 30:
  Creusy, 1965, between Chevilly and Sougy) is covered when the aire lists
  every commune that took a part of it;
- a Corsican commune merged before 1976 stands in INSEE's table under its
  `20…` code and in INAO's rows under the `2A…` / `2B…` code it never bore:
  read through the `20…` one;
- one that ceased **before 1943**, where INSEE's table begins (Lompnes,
  Palalda), is pinned to the commune that took it in
  `former_commune_pins.json`, each pin with its source.

Sources: `raw/ign/communes-associees-deleguees.geojson` and
`raw/insee/v_mvt_commune.csv`, both fetched by stage 00 (Licence Ouverte 2.0).
With either file missing the module resolves nothing and every caller draws
exactly what it drew before.
"""
from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
FORMER_GEOJSON = ROOT / "raw" / "ign" / "communes-associees-deleguees.geojson"
MOVEMENTS_CSV = ROOT / "raw" / "insee" / "v_mvt_commune.csv"
PINS_JSON = Path(__file__).resolve().parent / "former_commune_pins.json"

# INSEE's event codes that end a commune's code in another commune's:
# 31 fusion simple, 32 commune nouvelle, 33 fusion-association, 41 change of
# code with a change of département, 50 change of code with the chef-lieu.
_SUCCESSION_MODS = {"31", "32", "33", "41", "50"}
# … of which the mergers: the commune a merger ends in holds its own former
# ground too, whether or not the table gives it a row of its own (it does for
# all but one of 2,081)
_MERGER_MODS = {"31", "32", "33"}
# … and the changes of code of one and the same commune
_RECODE_MODS = {"41", "50"}
# … and the suppression of a commune whose ground its neighbours share
_SPLIT_MOD = "30"
_MAX_CHAIN = 8
# No cahier des charges in force is older: the AOC cahiers were rewritten
# from 2009 on, the IGP wine cahiers date from 2011, the spirit drinks' from
# 2009 onwards. A commune that left its département before that day cannot be
# ground a cahier means by "le département de …".
OLDEST_CAHIER = "2009-01-01"


@dataclass
class FormerCommunes:
    """`geoms` / `names` / `holder`: former communes with an outline of their
    own and the commune that holds each, minus the codes the commune layer
    carries (a seat's code is its commune's).
    `successor`: former code → the code of the commune that holds it today.
    `predecessors`: commune of today → every former code that ended in it,
    itself included when it was one of the merged communes.
    `left_departement`: former code → the day its ground passed to another
    département (ISO date), for the codes it happened to.
    `split`: a suppressed commune → the communes of today that share its
    ground.
    `seats` / `seat_names`: the outline and the former name of the seat of a
    commune nouvelle — the commune déléguée that bears its commune's code
    (Putanges-Pont-Écrepin under 61339, the code of Putanges-le-Lac). Read by
    `seat_communes.py`, never by `resolve`.
    `merged_on`: former code → the day it merged into another commune (ISO
    date; its last merger)."""
    geoms: dict[str, dict] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    holder: dict[str, str] = field(default_factory=dict)
    seats: dict[str, dict] = field(default_factory=dict)
    seat_names: dict[str, str] = field(default_factory=dict)
    merged_on: dict[str, str] = field(default_factory=dict)
    successor: dict[str, str] = field(default_factory=dict)
    predecessors: dict[str, set[str]] = field(default_factory=dict)
    left_departement: dict[str, str] = field(default_factory=dict)
    split: dict[str, set[str]] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.geoms or self.successor)

    def name(self, code: str) -> str:
        return self.names.get(code) or code

    def commune_of_today(self, code: str) -> str:
        """The commune that holds a former code today (INSEE's table, else the
        layer's `chefLieu`), or the code itself."""
        return self.successor.get(code) or self.holder.get(code) or code


@dataclass
class Resolution:
    """What `resolve` makes of the codes the commune layer lacks."""
    outlines: dict[str, dict] = field(default_factory=dict)    # code → its own outline
    whole: dict[str, list[str]] = field(default_factory=dict)  # commune of today → former codes
    covered: list[str] = field(default_factory=list)           # inside a commune the aire draws
    undrawn: list[str] = field(default_factory=list)           # no outline anywhere
    elsewhere: list[str] = field(default_factory=list)         # left its département before the cahiers


def _dept(code: str) -> str:
    """The département of a code; Corsica's two are one (the split of 1976
    moved no ground)."""
    return "20" if code[:2] in ("2A", "2B") else code[:2]


def load_pins(path: Path = PINS_JSON) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}


def _read_movements(
    path: Path, current: set[str], pins: dict[str, dict] | None = None,
) -> tuple[dict[str, str], dict[str, set[str]], dict[str, str], dict[str, str], dict[str, str],
           dict[str, set[str]], dict[str, str]]:
    """(successor, predecessors, names, recoded, left_departement, split, merged_on)."""
    events: dict[str, list[tuple[str, str]]] = {}
    shared: dict[str, set[str]] = {}
    merger_ends: set[str] = set()
    names: dict[str, str] = {}
    recoded: dict[str, str] = {}
    merged_on: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["TYPECOM_AV"] != "COM" or row["TYPECOM_AP"] != "COM":
                continue
            if row["MOD"] == _SPLIT_MOD and row["COM_AV"] != row["COM_AP"]:
                shared.setdefault(row["COM_AV"], set()).add(row["COM_AP"])
                names.setdefault(row["COM_AV"], row["LIBELLE_AV"])
                continue
            if row["MOD"] not in _SUCCESSION_MODS:
                continue
            before, after = row["COM_AV"], row["COM_AP"]
            names.setdefault(before, row["LIBELLE_AV"])
            if row["MOD"] in _MERGER_MODS:
                merger_ends.add(after)
            if before != after:
                events.setdefault(before, []).append((row["DATE_EFF"], after))
                if row["MOD"] in _RECODE_MODS:
                    recoded[before] = after
                else:
                    merged_on[before] = max(merged_on.get(before, ""), row["DATE_EFF"])

    def end_of(code: str) -> str | None:
        for _ in range(_MAX_CHAIN):
            if code in current:
                return code
            later = sorted(events.get(code, ()))
            if not later:
                return None
            code = later[-1][1]
        return None

    def left(code: str) -> str | None:
        for _ in range(_MAX_CHAIN):
            later = sorted(events.get(code, ()))
            if not later or code in current:
                return None
            date, after = later[-1]
            if _dept(after) != _dept(code):
                return date
            code = after
        return None

    successor: dict[str, str] = {}
    left_departement: dict[str, str] = {}
    for code in events:
        if code in current:
            continue
        end = end_of(code)
        if end is not None:
            successor[code] = end
        date = left(code)
        if date:
            left_departement[code] = date
    predecessors: dict[str, set[str]] = {}
    for code, end in successor.items():
        predecessors.setdefault(end, set()).add(code)
    for end, group in predecessors.items():
        if end in merger_ends:
            group.add(end)
    # a Corsican commune merged before 1976: INAO writes the 2A / 2B code it
    # would bear, INSEE's table knows it as 20…
    for code, end in list(successor.items()):
        if code[:2] == "20" and end[:2] in ("2A", "2B"):
            alias = end[:2] + code[2:]
            if alias not in current and alias not in successor:
                successor[alias] = end
                if code in names:
                    names.setdefault(alias, names[code])
    # ceased before 1943: the pinned commune, followed to the commune of today
    for code, pin in (pins or {}).items():
        if code in current or code in successor:
            continue
        end = end_of(pin["today"])
        if end is not None:
            successor[code] = end
            names.setdefault(code, pin.get("name") or code)
            # a merger: the commune that took it holds other ground too
            predecessors.setdefault(end, set()).update({code, end})
    # suppressed and shared out: every commune of today that took a part
    split: dict[str, set[str]] = {}
    for code, takers in shared.items():
        if code in current or code in successor:
            continue
        ends = {end_of(t) for t in takers}
        if None not in ends:
            split[code] = ends
    return successor, predecessors, names, recoded, left_departement, split, merged_on


def former_names(current: set[str] | dict, movements_path: Path = MOVEMENTS_CSV) -> list[tuple[str, str]]:
    """(code, former name) of the communes of today that changed name (INSEE
    MOD 10): a cahier older than the change still writes « Céreste » for
    Céreste-en-Luberon, « Clara » for Clara-Villerach, « Roquestéron-Grasse »
    for La Roque-en-Provence."""
    if not movements_path.exists():
        return []
    out: list[tuple[str, str]] = []
    with movements_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if (row["MOD"] == "10" and row["TYPECOM_AV"] == "COM" and row["TYPECOM_AP"] == "COM"
                    and row["COM_AV"] == row["COM_AP"] and row["COM_AV"] in current
                    and row["LIBELLE_AV"] != row["LIBELLE_AP"]):
                out.append((row["COM_AV"], row["LIBELLE_AV"]))
    return out


def load(
    current: set[str] | dict,
    former_path: Path = FORMER_GEOJSON,
    movements_path: Path = MOVEMENTS_CSV,
    *,
    pins_path: Path = PINS_JSON,
    log: bool = True,
) -> FormerCommunes:
    """`current`: the codes of the commune layer (a set, or the insee index)."""
    current = set(current)
    out = FormerCommunes()
    if former_path.exists():
        for feat in json.loads(former_path.read_text(encoding="utf-8"))["features"]:
            props = feat["properties"]
            code = props["code"]
            if not feat.get("geometry"):
                continue
            if code in current:
                out.seats[code] = feat["geometry"]
                out.seat_names[code] = props.get("nom") or code
                continue
            out.geoms[code] = feat["geometry"]
            out.names[code] = props.get("nom") or code
            if props.get("chefLieu"):
                out.holder[code] = props["chefLieu"]
    if movements_path.exists():
        (out.successor, out.predecessors, names, recoded, out.left_departement,
         out.split, out.merged_on) = _read_movements(movements_path, current, load_pins(pins_path))
        for code, name in names.items():
            out.names.setdefault(code, name)
        # a commune that changed code before it merged keeps its outline
        # under the later code: the earlier one is drawn from it
        for code in recoded:
            later = code
            for _ in range(_MAX_CHAIN):
                later = recoded.get(later)
                if later is None or later in current:
                    break
                if later in out.geoms and code not in out.geoms:
                    out.geoms[code] = out.geoms[later]
                    if later in out.holder:
                        out.holder.setdefault(code, out.holder[later])
                    break
    if log:
        print(
            f"[load] former communes: {len(out.geoms)} outline(s), "
            f"{len(out.successor)} successor(s)"
            + ("" if out else " — layer files missing, nothing resolved"),
            file=sys.stderr,
        )
    return out


def resolve(codes: set[str], current: set[str] | dict, former: FormerCommunes | None) -> Resolution:
    """Sort the codes of `codes` that `current` lacks into the classes of the
    module docstring. `codes` is the whole aire: a successor counts as drawn
    only when the aire's own rows carry it."""
    res = Resolution()
    missing = sorted(c for c in codes if c not in current)
    if not former:
        res.undrawn = missing
        return res
    # the départements the aire holds communes of today in: a code that left
    # the Jura for the Doubs in 1974 (Antorpe, now in Saint-Vit) is still
    # inside IGP Franche-Comté, which spans both
    depts = {_dept(c) for c in codes if c in current}
    for code in missing:
        if (former.left_departement.get(code, OLDEST_CAHIER) < OLDEST_CAHIER
                and _dept(former.commune_of_today(code)) not in depts):
            res.elsewhere.append(code)
            continue
        if code in former.geoms:
            res.outlines[code] = former.geoms[code]
            continue
        end = former.successor.get(code)
        if end is None:
            parts = former.split.get(code)
            (res.covered if parts and parts <= codes else res.undrawn).append(code)
        elif end in codes:
            res.covered.append(code)
        elif former.predecessors.get(end, set()) <= codes:
            res.whole.setdefault(end, []).append(code)
        else:
            res.undrawn.append(code)
    return res
