"""Resolve a PT area section, read by `area_units.parse_area_units`, to
DGT CAOP 2025 freguesia polygons.

CAOP 2025 carries the freguesias as they stand after the 2013 reform
(Lei n.º 11-A/2013) and the 2025 de-aggregation: 636 of the 3,049 mainland
units are a "União das freguesias de A, B e C", and some unions carry a
plain name ("Viseu", "São Gonçalo de Lagos", "Coutos de Viseu"). The
cadernos mostly name the freguesias of before 2013, so a name is matched,
inside its município only, against every name a unit answers to:

  1. its CAOP name and short designation, each of its former freguesias
     (the union's parts — "Travassô e Óis da Ribeira" → Travassô, Óis da
     Ribeira; "Lamego (Almacave e Sé)" → Almacave, Sé, "Lamego (Sé)"),
     and every run of consecutive parts ("Oeiras e São Julião da Barra");
  2. the same with the connectors dropped ("Vilar da Maçada" / "Vilar de
     Maçada"), and with the spaces dropped ("Riba Tua" / "Ribatua");
  3. a whole-word prefix or suffix of one unit's name ("Santa Catarina" →
     Santa Catarina da Fonte do Bispo, "Santa Maria de Almacave" →
     Almacave, "Santana da Carnota" → Carnota);
  4. a typo inside the município (rapidfuzz ratio ≥ 88, the runner-up
     ≥ 8 behind: "Boa Adeia", "Vil de Soito", "Santa Eugédia");
  5. the checked-in `freguesia_overrides.json`: a renamed union whose
     name carries no parts (Viseu = Coração de Jesus + Santa Maria de
     Viseu + São José), or a spelling the steps above cannot reach — each
     with its reason and public source.

A name that matches none of them is reported, never guessed.

What is drawn:
  - a município the text includes whole → its CAOP município polygon,
    minus the freguesias an exclusion of the same clause names;
  - a município restricted to freguesias → those units;
  - a freguesia the text includes only in part (or under an altitude
    limit) → the unit whole, listed in ``partial``;
  - a former freguesia whose union holds parishes the text does not name
    → the union whole, listed in ``proxied``;
  - an exclusion that names only some parts of a union keeps the union
    (drawn whole, listed in ``partial``).
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pyproj import Transformer
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform
from shapely.ops import unary_union

from .area_units import Item, Piece

if TYPE_CHECKING:
    from .geometry import PTPolygonIndex, _Concelho

OVERRIDES_PATH = Path(__file__).resolve().parent / "freguesia_overrides.json"

_FUZZY_MIN = 88
_FUZZY_GAP = 8
# Parts of an archipelago token drawn "islands only" (Madeira + Porto
# Santo) farther than this off the islands' main landmasses are dropped:
# the Desertas start ~11 km off Ponta de São Lourenço, the Selvagens lie
# ~280 km south; every coastal islet of the two islands is within 3 km.
ISLAND_KEEP_M = 10_000
_TO_3035 = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
_CONNECTORS = frozenset({"de", "do", "da", "dos", "das", "e", "d"})
_UNIAO_PREFIX = re.compile(
    r"^(?:Uni[ãa]o\s+d[ae]s?\s+freguesias\s+(?:de|da|do|das|dos)\s+|Freguesia\s+de\s+)",
    re.IGNORECASE,
)
_PAREN_FORM = re.compile(r"^(?P<pre>[^()]+?)\s*\((?P<inner>.+)\)\s*$")
_ABBREV = ((re.compile(r"\bd\.\s*"), "dona "), (re.compile(r"\bsta\.\s*"), "santa "),
           (re.compile(r"\bsto\.\s*"), "santo "), (re.compile(r"\bs\.\s*"), "sao "))


def fkey(s: str) -> str:
    """Accent- and case-folded key with punctuation dropped."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    for rx, repl in _ABBREV:
        s = rx.sub(repl, s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def floose(s: str) -> str:
    return " ".join(w for w in fkey(s).split() if w not in _CONNECTORS)


def fnospace(s: str) -> str:
    return floose(s).replace(" ", "")


def split_parts(s: str) -> list[str]:
    """Split a union's name on ", ", " e " and " - " outside parentheses."""
    out, depth, start = [], 0, 0
    for m in re.finditer(r"\(|\)|,\s*|\s+e\s+|\s+-\s+", s):
        tok = m.group(0)
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
        elif depth == 0:
            out.append(s[start:m.start()])
            start = m.end()
    out.append(s[start:])
    return [p.strip() for p in out if p.strip()]


@dataclass
class Freguesia:
    code: str
    name: str  # CAOP `freguesia`
    short: str  # CAOP `designacao_simplificada`
    concelho: str
    distrito: str
    geom: BaseGeometry
    parts: list[str] = field(default_factory=list)  # former freguesias, when a union
    # fkey(name variant) → fkeys of the parts that variant stands for
    keys: dict[str, frozenset[str]] = field(default_factory=dict)
    source: str = ""  # "override" when a pin added the parts

    @property
    def is_union(self) -> bool:
        return len(self.parts) > 1


def unit_keys(name: str, short: str) -> tuple[list[str], dict[str, frozenset[str]]]:
    """The former freguesias of a CAOP unit and every name it answers to,
    each mapped to the parts it stands for."""
    core = _UNIAO_PREFIX.sub("", (short or name).strip())
    keys: dict[str, frozenset[str]] = {}
    m = _PAREN_FORM.match(core)
    if m and not re.search(r"\)\s*\S", core):
        pre = m.group("pre").strip()
        parts = split_parts(_UNIAO_PREFIX.sub("", m.group("inner").strip()))
        prefixed = {p: f"{pre} ({p})" for p in parts}
    else:
        pre, parts, prefixed = "", split_parts(core), {}
    # a part that is itself "Celorico (São Pedro e Santa Maria)"
    expanded: list[str] = []
    for p in parts:
        mm = _PAREN_FORM.match(p)
        if mm:
            sub = split_parts(mm.group("inner"))
            expanded.extend(f"{mm.group('pre').strip()} ({x})" for x in sub)
        else:
            expanded.append(p)
    parts = expanded if len(expanded) >= len(parts) else parts
    all_parts = frozenset(fkey(p) for p in parts)
    for variant in (name, short, core):
        if variant:
            keys[fkey(_UNIAO_PREFIX.sub("", variant))] = all_parts
            keys[fkey(variant)] = all_parts
    if pre:
        keys.setdefault(fkey(pre), all_parts)
    for p in parts:
        keys[fkey(p)] = frozenset({fkey(p)})
        mm = _PAREN_FORM.match(p)
        if mm:
            keys.setdefault(fkey(mm.group("inner")), frozenset({fkey(p)}))
        for piece in p.split("/"):
            keys.setdefault(fkey(piece), frozenset({fkey(p)}))
        if p in prefixed:
            keys[fkey(prefixed[p])] = frozenset({fkey(p)})
            # CAOP's "Vizela (São Paio)" is the act's "São Paio de Vizela",
            # "Caldas de Vizela (São Miguel)" its "São Miguel das Caldas de
            # Vizela" (the loose key drops the connector)
            keys.setdefault(fkey(f"{p} de {pre}"), frozenset({fkey(p)}))
    for i in range(len(parts)):
        for j in range(i + 2, len(parts) + 1):
            run = parts[i:j]
            covered = frozenset(fkey(p) for p in run)
            keys.setdefault(fkey(" e ".join(run)), covered)
            keys.setdefault(fkey(", ".join(run[:-1]) + " e " + run[-1]), covered)
    keys.pop("", None)
    return (parts if len(parts) > 1 else []), keys


def union_label(f: Freguesia) -> str:
    """A union as the card names it: its CAOP name when that lists the
    former freguesias ("União das freguesias de Travassô e Óis da
    Ribeira"), else the name and its pinned former freguesias ("Armamar
    (Armamar, Coura, Tões)")."""
    if f.source != "override":
        return f.name
    parts = [(_PAREN_FORM.match(p).group("inner") if _PAREN_FORM.match(p) else p)
             for p in f.parts]
    return f"{f.name} ({', '.join(parts)})"


@dataclass
class Match:
    freg: Freguesia
    how: str
    named: frozenset[str]


def union_parts(g: _Gazetteer, name: str) -> list[str]:
    """The former freguesias of a name written "União das freguesias de A e
    B" when no unit of the município carries that union's name any more —
    CAOP 2025 has re-created some (Valongo's Campo e Sobrado is Campo and
    Sobrado again) — else []. Read whole, such a name would match one of its
    parts by suffix and lose the others."""
    if not _UNIAO_PREFIX.match(name) or g.match(name, strict=True) is not None:
        return []
    return split_parts(_UNIAO_PREFIX.sub("", name))


class _Gazetteer:
    """Name lookup over one município's freguesias."""

    def __init__(self, fregs: list[Freguesia]) -> None:
        self.fregs = fregs
        self.by_key: dict[str, list[tuple[Freguesia, frozenset[str]]]] = {}
        self.by_loose: dict[str, list[tuple[Freguesia, frozenset[str]]]] = {}
        self.by_nospace: dict[str, list[tuple[Freguesia, frozenset[str]]]] = {}
        for f in fregs:
            for k, named in f.keys.items():
                self.by_key.setdefault(k, []).append((f, named))
                self.by_loose.setdefault(floose(k), []).append((f, named))
                self.by_nospace.setdefault(fnospace(k), []).append((f, named))

    @staticmethod
    def _unique(hits: list[tuple[Freguesia, frozenset[str]]] | None) -> tuple | None:
        if not hits:
            return None
        codes = {f.code for f, _ in hits}
        if len(codes) != 1:
            return None
        named = frozenset().union(*(n for _, n in hits))
        return hits[0][0], named

    def match(self, name: str, *, strict: bool = False) -> Match | None:
        """The unit `name` stands for. `strict`: the whole name only — no
        prefix / suffix, typo or fuzzy reading."""
        k = fkey(name)
        if not k:
            return None
        for how, table, key in (("exact", self.by_key, k), ("loose", self.by_loose, floose(name)),
                                ("nospace", self.by_nospace, fnospace(name))):
            hit = self._unique(table.get(key))
            if hit:
                return Match(hit[0], how, hit[1])
        if strict:
            return None
        words = k.split()
        cand: dict[str, tuple[Freguesia, frozenset[str]]] = {}
        for key, hits in self.by_key.items():
            kw = key.split()
            if len(key) < 4 or kw == words:
                continue
            # "Santa Catarina" → Santa Catarina da Fonte do Bispo; "Santa
            # Maria do Castelo" → Santa Maria; "Santa Maria de Almacave" →
            # Almacave; "Rua" → Vila da Rua
            if kw[:len(words)] == words or words[:len(kw)] == kw or words[-len(kw):] == kw \
                    or (len(k) >= 3 and kw[-len(words):] == words):
                for f, named in hits:
                    cand.setdefault(f.code, (f, named))
        if len(cand) == 1:
            f, named = next(iter(cand.values()))
            return Match(f, "affix", named)
        if len(k) >= 5:
            # one letter off: "Frechos" / Frechas, "Argeriz" / Algeriz
            typo: dict[str, tuple[Freguesia, frozenset[str]]] = {}
            for key, hits in self.by_key.items():
                if len(key) >= 5 and Levenshtein.distance(k, key, score_cutoff=1) <= 1:
                    for f, named in hits:
                        typo.setdefault(f.code, (f, named))
            if len(typo) == 1:
                f, named = next(iter(typo.values()))
                return Match(f, "typo", named)
        scored: dict[str, tuple[float, Freguesia, frozenset[str]]] = {}
        for key, hits in self.by_key.items():
            r = fuzz.ratio(k, key)
            for f, named in hits:
                if f.code not in scored or r > scored[f.code][0]:
                    scored[f.code] = (r, f, named)
        ranked = sorted(scored.values(), key=lambda t: -t[0])
        if ranked and ranked[0][0] >= _FUZZY_MIN and (
                len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= _FUZZY_GAP):
            return Match(ranked[0][1], "fuzzy", ranked[0][2])
        return None


def load_overrides(path: Path = OVERRIDES_PATH) -> dict:
    if not path.exists():
        return {"unions": [], "names": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("unions", [])
    data.setdefault("names", [])
    return data


def apply_overrides(index: PTPolygonIndex, overrides: dict) -> list[str]:
    """Add the pinned former freguesias and spellings to the gazetteer.
    Returns STALE warnings for pins whose unit CAOP no longer carries."""
    stale: list[str] = []
    for pin in overrides.get("unions", []):
        f = index.find_freguesia(pin["concelho"], pin["caop"])
        if f is None:
            stale.append(f"union pin {pin['concelho']} / {pin['caop']}: no such CAOP unit")
            continue
        if f.is_union:
            stale.append(f"union pin {pin['concelho']} / {pin['caop']}: CAOP already names "
                         f"its parts ({', '.join(f.parts)})")
            continue
        f.parts = list(pin["former"])
        f.source = "override"
        all_parts = frozenset(fkey(p) for p in f.parts)
        for k in list(f.keys):
            f.keys[k] = all_parts
        for p in f.parts:
            f.keys[fkey(p)] = frozenset({fkey(p)})
            # the act writes "Viseu (São José)": the caderno, "São José"
            m = _PAREN_FORM.match(p)
            if m:
                f.keys.setdefault(fkey(m.group("inner")), frozenset({fkey(p)}))
    for pin in overrides.get("names", []):
        f = index.find_freguesia(pin["concelho"], pin["caop"])
        if f is None:
            stale.append(f"name pin {pin['concelho']} / {pin['name']} → {pin['caop']}: "
                         f"no such CAOP unit")
            continue
        target = pin.get("part") or pin["caop"]
        f.keys[fkey(pin["name"])] = frozenset({fkey(target)}) if f.is_union else \
            frozenset(fkey(p) for p in f.parts) or frozenset({fkey(target)})
    index.reset_gazetteers()
    return stale


# ------------------------------------------------------------ resolve --


@dataclass
class AreaResolution:
    geom: BaseGeometry | None = None
    source: str = ""  # caop-freguesia-union | caop-concelho-union
    concelhos_whole: list[str] = field(default_factory=list)
    freguesias: list[str] = field(default_factory=list)  # CAOP names drawn on their own
    partial: list[str] = field(default_factory=list)
    proxied: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    exclusions_unresolved: list[str] = field(default_factory=list)
    n_units: int = 0
    log: list[str] = field(default_factory=list)
    # how each statement of the text was drawn — the audit's evidence
    trace: list[dict] = field(default_factory=list)


@dataclass
class _Drawn:
    freg: Freguesia
    full: bool = False  # included by a whole-unit statement
    via_concelho: bool = False  # included because its município is whole
    whole_via_concelho: bool = False  # … by a município / distrito named whole
    named: set[str] = field(default_factory=set)
    written: list[str] = field(default_factory=list)  # the text's names for it
    # the text's name → included only in part wherever it is named
    name_part: dict[str, bool] = field(default_factory=dict)


def _choose(cands: list[tuple[int, _Concelho]], items: list[Item], expected: set[str],
            gaz) -> _Concelho | None:
    """The município a name stands for: the candidate in which most of the
    clause's freguesias resolve, then an exact name before a shortened one
    ("Paredes" is Paredes, not Paredes de Coura), then the distrito the
    record's unambiguous municípios lie in."""
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0][1]
    scored = []
    for rank, c in cands:
        g = gaz(c)
        n = sum(1 for it in items if g.match(it.name))
        scored.append((-n, rank, c.distrito not in expected, c))
    scored.sort(key=lambda t: t[:3])
    if scored[0][:3] == scored[1][:3]:
        return None
    return scored[0][3]


def _islands_only(geom: BaseGeometry, islands: list[BaseGeometry]) -> BaseGeometry:
    """Drop the parts of `geom` lying more than ISLAND_KEEP_M off the main
    landmass of every island in `islands`."""
    mains = []
    for g in islands:
        parts = list(getattr(g, "geoms", [g]))
        if parts:
            mains.append(shp_transform(_TO_3035.transform, max(parts, key=lambda q: q.area)))
    keep = [q for q in getattr(geom, "geoms", [geom])
            if any(shp_transform(_TO_3035.transform, q).distance(m) <= ISLAND_KEEP_M
                   for m in mains)]
    return unary_union(keep) if keep else geom


def resolve_area_units(index: PTPolygonIndex, parsed: dict, slug: str = "") -> AreaResolution:
    res = AreaResolution()
    pieces: list[Piece] = parsed.get("pieces") or []
    drawn: dict[str, _Drawn] = {}
    whole_concelhos: dict[int, _Concelho] = {}
    part_concelhos: set[str] = set()  # municípios included whole but only in part
    island_anchors: list[str] = []  # distrito_ilha whose main landmass bounds the drawing

    def add(f: Freguesia, *, full: bool, via_concelho: bool = False,
            named: frozenset[str] = frozenset(), written: str = "") -> _Drawn:
        d = drawn.get(f.code)
        if d is None:
            d = drawn[f.code] = _Drawn(f)
        d.full = d.full or full
        d.via_concelho = d.via_concelho or via_concelho
        d.whole_via_concelho = d.whole_via_concelho or (via_concelho and full)
        d.named |= set(named)
        if written:
            if written not in d.written:
                d.written.append(written)
            d.name_part[written] = d.name_part.get(written, True) and not full
        return d

    # municípios named without ambiguity anchor the distrito context
    expected: set[str] = set()
    for p in pieces:
        if p.kind in ("concelho", "freguesias") and p.name:
            cands = index.concelho_candidates(p.name)
            if len(cands) == 1:
                expected.add(cands[0].distrito)
        elif p.kind == "distrito":
            expected.add(p.name)

    def resolve_concelho(name: str, items: list[Item]) -> _Concelho | None:
        cands = index.concelho_candidates_ranked(name)
        chosen = _choose(cands, items, expected, index.gazetteer)
        if chosen is None and cands:
            res.log.append(f"ambiguous município '{name}': "
                           f"{', '.join(c.name + ' (' + c.distrito + ')' for _, c in cands)}")
        return chosen

    def exclude(c: _Concelho, it: Item, codes: set[str]) -> None:
        g = index.gazetteer(c)
        # a União written by name that CAOP no longer carries as such: its
        # former freguesias, the parishes each names gathered per unit so a
        # union whose every part is excluded goes as a whole
        hits: dict[str, tuple[Freguesia, set[str], str]] = {}
        for name in union_parts(g, it.name) or [it.name]:
            m = g.match(name)
            if m is None:
                res.exclusions_unresolved.append(f"{name} ({c.name})")
                continue
            hits.setdefault(m.freg.code, (m.freg, set(), m.how))[1].update(m.named)
        for f, named, how in hits.values():
            res.trace.append({"exclude": it.name, "from": c.name, "caop": f.name, "how": how,
                              "part": bool(it.part)})
            if it.part or (f.is_union and not {fkey(p) for p in f.parts} <= named):
                # part of a freguesia, or some parishes of a union, are carved
                # out: the unit stays, included in part
                add(f, full=False, via_concelho=True)
            codes.discard(f.code)

    for p in pieces:
        if p.kind == "macro":
            res.trace.append({"macro": p.name})
            if p.name in index.macro_islands_only:
                island_anchors.extend(index.macro_distritos(p.name))
            for ilha in index.macro_distritos(p.name):
                for c in index.concelhos_in_distrito(ilha):
                    whole_concelhos[id(c)] = c
                    for f in c.freguesias:
                        add(f, full=True, via_concelho=True)
            continue
        if p.kind == "distrito":
            excl_conc = {fkey(n) for n in p.excluded_concelhos}
            concelhos = index.concelhos_in_distrito(p.name)
            res.trace.append({"distrito": p.name, "excluded_concelhos": list(p.excluded_concelhos),
                              "excluded_freguesias": [f"{a} ({b})" for a, b in
                                                      p.excluded_freguesias],
                              "n_concelhos": len(concelhos)})
            if not concelhos:
                res.unmatched.append(f"distrito {p.name}")
                continue
            for c in concelhos:
                if fkey(c.name) in excl_conc:
                    continue
                codes = {f.code for f in c.freguesias}
                for fname, cname in p.excluded_freguesias:
                    if fkey(cname) == fkey(c.name) or floose(cname) == floose(c.name):
                        exclude(c, Item(fname, role="exclude"), codes)
                for f in c.freguesias:
                    if f.code in codes:
                        add(f, full=not p.part, via_concelho=True)
                if codes == {f.code for f in c.freguesias}:
                    whole_concelhos[id(c)] = c
            continue
        if p.kind == "concelho":
            c = resolve_concelho(p.name, p.items)
            if c is None:
                res.unmatched.append(p.name)
                continue
            res.trace.append({"concelho": p.name, "caop": f"{c.name} ({c.distrito})",
                              "part": bool(p.part)})
            codes = {f.code for f in c.freguesias}
            for it in p.items:
                if it.role == "exclude":
                    exclude(c, it, codes)
            for f in c.freguesias:
                if f.code in codes:
                    add(f, full=not p.part, via_concelho=True)
            if p.part:
                part_concelhos.add(c.name)
                res.partial.append(c.name)
            if codes == {f.code for f in c.freguesias} and not p.part:
                whole_concelhos[id(c)] = c
            continue
        # freguesias
        localities = [it for it in p.items if it.role == "locality"]
        includes = [it for it in p.items if it.role not in ("exclude", "locality")]
        if p.name:
            c = resolve_concelho(p.name, includes)
            cands = [c] if c else []
        else:
            # no container written: the municípios the record names elsewhere
            seen = {id(x): x for x in whole_concelhos.values()}
            for q in pieces:
                if q.kind in ("concelho", "freguesias") and q.name and q is not p:
                    for x in index.concelho_candidates(q.name):
                        seen[id(x)] = x
            cands = [(0, x) for x in seen.values()]
            c = _choose(cands, includes, expected, index.gazetteer) if cands else None
        if c is None:
            for it in includes:
                if it.role == "include":
                    res.unmatched.append(f"{it.name} ({p.name})" if p.name else it.name)
            continue
        g = index.gazetteer(c)
        anchor: Freguesia | None = None
        tail_open = False
        tail_id = 0
        waiting: list[Item] = []  # includes that matched nothing, before a tail
        expanded: list[Item] = []
        for it in includes:
            if it.role != "union_tail":
                parts = union_parts(g, it.name)
                if parts:
                    expanded.extend(Item(n, part=it.part, role=it.role) for n in parts)
                    continue
            # "Gouviães e Ucanha", kept whole by the parser as one former
            # parish, may now be two units: try the parts when the whole fails
            if it.role != "union_tail" and " e " in it.name and g.match(it.name) is None:
                expanded.extend(Item(n, part=it.part, role=it.role)
                                for n in split_parts(it.name))
            else:
                expanded.append(it)
        for it in expanded:
            m = g.match(it.name)
            if it.role == "union_tail" and it.tail != tail_id:
                tail_id, tail_open = it.tail, False
            if it.role == "union_tail" and not tail_open:
                if m is not None and anchor is not None and m.freg.code == anchor.code:
                    continue  # a part of the union the text took a parish out of
                if m is not None and waiting and (it.holder or anchor is None):
                    # "Coura e Tões da freguesia de Armamar", "X da União de
                    # Freguesias de …": the text binds the names before the
                    # tail to the unit the tail names
                    for w in waiting:
                        add(m.freg, full=not w.part, named=frozenset({fkey(w.name)}),
                            written=w.name)
                        res.trace.append({"freguesia": w.name, "in": f"{c.name} ({c.distrito})",
                                          "caop": m.freg.name, "how": "held-by-text",
                                          "part": bool(w.part)})
                        res.log.append(f"'{w.name}' bound to {m.freg.name} by the text")
                    waiting.clear()
                    anchor = m.freg
                    continue
                if m is not None and anchor is None:
                    continue
                tail_open = True  # the union's names are over: back to the list
            if m is None:
                waiting.append(it)
                continue
            add(m.freg, full=not it.part, named=m.named, written=it.name)
            res.trace.append({"freguesia": it.name, "in": f"{c.name} ({c.distrito})",
                              "caop": m.freg.name, "how": m.how, "part": bool(it.part)})
            if m.how not in ("exact", "loose", "nospace"):
                res.log.append(f"{m.how}: '{it.name}' → {m.freg.name} ({c.name})")
            anchor = m.freg
        for w in waiting:
            res.unmatched.append(f"{w.name} ({c.name})")
        for loc in localities:
            # a "lugar" that is a freguesia of the município today (Porto
            # Salvo, a lugar of Oeiras e São Julião da Barra in Carcavelos'
            # text): drawn whole, in part; any other lugar draws nothing
            m = g.match(loc.name)
            if m is None or m.how not in ("exact", "loose", "nospace") or m.freg.code in {
                    d.freg.code for d in drawn.values()}:
                continue
            add(m.freg, full=False, named=m.named, written=loc.name)
            res.trace.append({"lugar": loc.name, "in": f"{c.name} ({c.distrito})",
                              "caop": m.freg.name, "how": m.how, "part": True})

    # disclosures: a unit drawn whole that the text includes only in part,
    # and a union drawn for the former freguesias the text names in it
    partial_by_concelho: dict[str, list[str]] = {}
    for d in drawn.values():
        f = d.freg
        if d.whole_via_concelho or f.concelho in part_concelhos:
            continue
        # per name: a parish included only in part stays partial even when
        # its União is drawn whole for a sister parish (Douro's "Nossa
        # Senhora da Conceição (parte)" beside São Dinis and São Pedro)
        part_names = [w for w, part in d.name_part.items() if part]
        if not d.written and not d.full:
            part_names = [f.short]  # a part of it carved out by an exclusion
        if part_names:
            names = partial_by_concelho.setdefault(f.concelho, [])
            names.extend(n for n in part_names if n not in names)
        if f.is_union and not d.via_concelho and not {fkey(x) for x in f.parts} <= d.named:
            res.proxied.append(f"{', '.join(d.written) or f.short} → {union_label(f)}")
    res.partial.extend(f"{', '.join(names)} ({c})" for c, names in partial_by_concelho.items())
    if not drawn:
        return res

    # geometry: a município entirely drawn uses its own polygon
    by_concelho: dict[str, list[Freguesia]] = {}
    for d in drawn.values():
        by_concelho.setdefault(f"{d.freg.concelho}|{d.freg.distrito}", []).append(d.freg)
    geoms: list[BaseGeometry] = []
    any_partial_concelho = False
    for key, fregs in by_concelho.items():
        c = index.concelho_by_key(key)
        if c is not None and len(fregs) == len(c.freguesias):
            geoms.append(c.geom)
            res.concelhos_whole.append(c.name)
        else:
            any_partial_concelho = True
            geoms.extend(f.geom for f in fregs)
            res.freguesias.extend(f.name for f in fregs)
    res.geom = unary_union(geoms)
    if island_anchors:
        res.geom = _islands_only(res.geom, [
            unary_union([c.geom for c in index.concelhos_in_distrito(d)])
            for d in island_anchors])
    res.n_units = len(drawn)
    res.source = "caop-freguesia-union" if any_partial_concelho else "caop-concelho-union"
    if res.log:
        for line in res.log:
            print(f"  [pt-geom] {slug}: {line}", file=sys.stderr)
    return res
