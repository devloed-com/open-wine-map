"""The units a German delimitation names, outside the two layouts that have
their own module (Baden-Württemberg's numbered Gemarkungen, `gemarkung.py`;
the Bavarian Regierungsbezirk lists, `gemeinde_list.py`).

Four ways a text names its area, each read by its own words:

  numbered     "Bacharach (Bacharach (3503), Steeg (3502)), Bad Ems (0950)" —
               the Rheinland-Pfalz regions print each Gemarkung's land-register
               number, nested under its Gemeinde where the Gemeinde has several
               (Mittelrhein, Mosel, Nahe, Pfalz and their Landweine);
  city         "der Stadt Königswinter mit den Gemarkungen Oberdollendorf,
               Niederdollendorf und Königswinter" (Mittelrhein in
               Nordrhein-Westfalen);
  by Kreis     "der Gemarkungen Bad Kösen, … und Zscheiplitz im Landkreis
               Burgenlandkreis, Quedlinburg und Westerhausen im Landkreis Harz
               … des Landes Sachsen-Anhalt" (Saale-Unstrut), with "Weimar
               Ortsteil Schöndorf" and "die kreisfreien Städte Jena und
               Erfurt" in the same sentence;
  Gemeinden    "der Städte und Gemeinden Eltville am Rhein, … und der
               Landeshauptstadt Wiesbaden des Bundeslandes Hessen" (Rheingau,
               Hessische Bergstraße, Ahr, Rheinhessen, the Saarland).

`parse(text)` returns the units in text order; `resolve(units, …)` binds
each to a Gemarkung of its Land's open layer (`katasterbezirk.py`) or to a
GISCO commune, never by guessing: a number is drawn only when the printed
name agrees with the layer's name for it, a name only when it names one
unit inside the Land and — where the text gives one — the Kreis or Gemeinde.

Bétard 2022 drew these regions as whole municipalities: Bonn, Königswinter
and Bad Honnef for the five Gemarkungen Mittelrhein names there, and no
part of Frankfurt am Main, which the Rheingau's § 3 lists (feedback triage
2026-11-24).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .gemarkung import name_agreement
from .katasterbezirk import norm_name

# Land names as the texts write them → (layer code, AGS prefix).
LANDS: dict[str, tuple[str, str]] = {
    "rheinland pfalz": ("rp", "07"),
    "nordrhein westfalen": ("nw", "05"),
    "sachsen anhalt": ("st", "15"),
    "thuringen": ("th", "16"),
    "brandenburg": ("bb", "12"),
    "hessen": ("he", "06"),
    "saarland": ("sl", "10"),
    "saarlandes": ("sl", "10"),
    "baden wurttemberg": ("bw", "08"),
    "bayern": ("by", "09"),
    "sachsen": ("sn", "14"),
}
AGS2 = {code: ags for code, ags in LANDS.values()}
# The Länder whose layer is keyed by the number a text prints.
NUMBERED_LANDS = ("rp",)

# A sentence that is no longer the list: the map reference, the rule on
# where the wine may be made.
_TAIL = re.compile(
    r"Die\s+genaue\s+Abgrenzung|Die\s+Abgrenzungskarten|Die\s+Herstellung\s+von|"
    r"darf\s+in\s+einem\s+anderen\s+Gebiet|muss\s+im\s+Anbaugebiet")
_LAND_RE = re.compile(
    r"Rheinland[-–\s]+Pfalz|Nordrhein[-–\s]+Westfalen|Sachsen[-–\s]+Anhalt|Th[üu]ringen|"
    r"Brandenburg|Hessen|Saarland(?:es)?|Baden[-–\s]+W[üu]rttemberg|Bayern|Sachsen")
# "Land Rheinland-Pfalz" / "Im Bundesland Sachsen" / "Rheinland-Pfalz" alone on
# its line: the Land of the lines below.
_LAND_HEAD = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?(?:Im\s+)?(?:(?:Bundes)?[Ll]and\s+)?(" + _LAND_RE.pattern + r")\s*:?\s*$")
_NUMBER_GROUP = re.compile(r"\(\s*(\d{3,5}(?:\s*,\s*\d{3,5})*)\s*\)")
_KREIS_GLOSS = re.compile(r"\(\s*(?:Land)?[Kk]reis\s+([^()]+?)\s*\)")
_CITY = re.compile(
    r"(?:der\s+)?Stadt\s+(?P<holder>[A-ZÄÖÜ][\wäöüß.\- ]*?(?:\s*\([^()]*\))?)\s+mit\s+de[rn]\s+"
    r"Gemarkung(?:en)?\s+(?P<names>.+?)(?=,\s+der\s+Stadt\s|\s+und\s+der\s+Stadt\s|$)", re.DOTALL)
_BY_KREIS = re.compile(
    r"(?P<names>.+?)\s+im\s+(?:(?:Land)?[Kk]reis\s+|(?=[A-ZÄÖÜ][\w\-]*-Kreis\b|Regionalverband\s))(?P<kreis>.+?)"
    r"(?=,|\s+sowie\s|\s+des\s+(?:Bundes)?[Ll]andes\s|\s+und\s+die\s|$)", re.DOTALL)
_HOLDER_TAIL = re.compile(
    r"\s+der\s+(?:Stadt|Gemeinde)\s+(?P<holder>[A-ZÄÖÜ][\wäöüß.\- ]*?(?:\s*\([^()]*\))?)\s*$")
_ORTSTEIL = re.compile(r"^(?P<holder>[A-ZÄÖÜ][\wäöüß.\- ]*?)\s+Ortsteil\s+(?P<name>.+)$")
_KREISFREI = re.compile(r"(?:und\s+)?die\s+kreisfreien\s+St[äa]dte\s+(?P<names>.+)$", re.DOTALL)
_GEMEINDEN = re.compile(
    r"(?:Rebfl[äa]chen|Fl[äa]chen)\s+(?:der|folgender)\s+(?:folgenden\s+)?"
    r"(?:St[äa]dte\s+und\s+)?Gemeinden\s+(?!und\s+deren|\()(?P<names>.+)$", re.DOTALL)
_GEMARKUNGEN = re.compile(r"(?:Rebfl[äa]chen\s+(?:der|in\s+den)|in\s+den)\s+Gemarkungen\s+(?P<rest>.+)$",
                          re.DOTALL)
# Words that end a Gemeinde list: the Land, a verb, a second clause.
_GEMEINDEN_END = re.compile(
    r"\s+des\s+(?:Bundes)?[Ll]andes\s.*$|\s+des\s+Saarlandes.*$|\s+im\s+(?:Bundes)?[Ll]and\s.*$|"
    r"\s+stammen\b.*$", re.DOTALL)
# "…, die Flächen der Städte und Gemeinden X, Y im Landkreis Z" repeated per Kreis (the Saarland)
_REPEATED_LEAD = re.compile(
    r"(?:sowie\s+)?die\s+(?:Rebfl[äa]chen|Fl[äa]chen)\s+der\s+(?:St[äa]dte\s+und\s+)?Gemeinden\s+")
_TITLE = re.compile(r"^(?:der\s+)?(?:Landeshauptstadt|Stadt|Gemeinde|Kreisstadt)\s+")


@dataclass(frozen=True)
class Unit:
    kind: str            # numbered | gemarkung | ortsteil | gemeinde
    name: str            # as printed
    land: str = ""       # layer code ('' when the text names no Land)
    number: int | None = None
    holder: str = ""     # the Gemeinde / Stadt the unit is printed under
    kreis: str = ""      # the Kreis the text files it under, as printed
    gloss: str = ""      # a bracket after the name ("Honnef (Rhöndorf)")


def _land_code(name: str) -> str:
    return LANDS.get(norm_name(name), ("", ""))[0]


def _split_depth0(text: str, seps: str = ",") -> list[str]:
    """Split on separators outside brackets."""
    out, depth, cur = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch in seps and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [p.strip() for p in out if p.strip()]


def _names(block: str) -> list[str]:
    """The names of a comma / "und" / "sowie" list, a bracket kept with its
    name; "Tümplingund Wichmar" (Saale-Unstrut's single document lost the
    space) is two names."""
    block = re.sub(r"(?<=[a-zäöüß])und\s+(?=[A-ZÄÖÜ])", " und ", block)
    out: list[str] = []
    for part in _split_depth0(block, ","):
        for piece in re.split(r"\s+(?:und|sowie)\s+", part):
            piece = re.sub(r"^(?:der|die|den|dem)\s+(?=[A-ZÄÖÜ])", "", piece.strip(" .;:"))
            if piece and piece[0].isupper():
                out.append(piece)
    return out


def _bare(name: str) -> tuple[str, str]:
    """(name without its trailing bracket, the bracket's text). A bracket
    that is part of the name — "Werder (Havel)", "Wallhausen (Helme)" — is
    resolved by the caller, which tries both forms."""
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", name)
    return (m.group(1).strip(), m.group(2).strip()) if m else (name.strip(), "")


_AREA_HEAD = re.compile(
    r"^[ \t]*(\d)\.?[ \t]+(?:Abgrenzung\s+des\s+(?:geogra\w+\s+)?Gebiete?s|Gebietsabgrenzung)[^\n]*$",
    re.MULTILINE)


def area_section(spec_text: str) -> str:
    """The "Abgrenzung des Gebiet(e)s" section of a BLE Produktspezifikation
    (`pdftotext -layout`), whatever its number (3 in the older template, 4 in
    the newer), up to the next top-level heading; '' when the specification
    has none under that title."""
    m = _AREA_HEAD.search(spec_text or "")
    if not m:
        return ""
    # the next top-level heading: a higher number (Landwein Rhein runs from 3
    # to 5), never a list line that opens on a digit ("3 Mittelhainger (5490)"
    # inside the Pfalz's section 4)
    n = int(m.group(1))
    higher = "".join(str(d) for d in range(n + 1, min(n + 3, 9) + 1))
    nxt = re.compile(rf"^[ \t]*[{higher}]\.?[ \t]+[A-ZÄÖÜ]", re.MULTILINE)
    end = nxt.search(spec_text, m.end())
    return spec_text[m.end():end.start() if end else len(spec_text)].strip("\n")


# ───────────────────────────────────────────────────── numbered lists ──

def _numbered_items(body: str, land: str) -> list[Unit]:
    """One numbered list: "Name (dddd)", "Name (d1, d2)", "Name (Landkreis X)
    (dddd)", "Gemeinde (Gemarkung (dddd), Gemarkung (dddd))"."""
    out: list[Unit] = []
    for item in _split_depth0(re.sub(r"\s+und\s+(?=[A-ZÄÖÜ0-9][^()]*\()", ", ", body), ","):
        item = item.strip(" .;")
        if not _NUMBER_GROUP.search(item):
            continue
        kreis = ""
        km = _KREIS_GLOSS.search(item)
        if km:
            kreis = km.group(1).strip()
        last = None
        depth = 0
        # the last top-level bracket of the item
        for i, ch in enumerate(item):
            if ch == "(":
                if depth == 0:
                    last = i
                depth += 1
            elif ch == ")":
                depth -= 1
        if last is None:
            continue
        head = _KREIS_GLOSS.sub("", item[:last]).strip(" ,")
        inner = item[last + 1:item.rfind(")")]
        direct = re.fullmatch(r"\s*(\d{3,5}(?:\s*,\s*\d{3,5})*)\s*", inner)
        if direct:
            for n in re.findall(r"\d{3,5}", direct.group(1)):
                out.append(Unit("numbered", head, land, int(n), kreis=kreis))
            continue
        for sub in _split_depth0(inner, ","):
            sm = _NUMBER_GROUP.search(sub)
            if not sm:
                continue
            name = sub[:sm.start()].strip(" ,")
            for n in re.findall(r"\d{3,5}", sm.group(1)):
                out.append(Unit("numbered", name, land, int(n), holder=head, kreis=kreis))
    return out


_NUMBERED_LEAD = re.compile(
    r"^.*?(?:Gemeinde/Ortsteile|Ortsteilen?|Gemeinden)\b(?:\s+stammen)?\s*:?\s*(?=[A-ZÄÖÜ])", re.DOTALL)


# ───────────────────────────────────────────────────────── parse ──

_PAGE_FURNITURE = re.compile(r"^\s*(?:-\s*\d+\s*-|Seite\s+\d+(?:\s+von\s+\d+)?|\d+(?:\s*/\s*\d+)?|Stand:.*)\s*$",
                             re.IGNORECASE)


def _paragraphs(text: str) -> list[str]:
    """A PDF's hard-wrapped lines joined into paragraphs (a word broken at a
    line end closed: "Ge-⏎meinden"; a compound keeps its hyphen: "Dahme-⏎
    Spreewald"); a Land header and a blank line end a paragraph. An EU
    document's one-line paragraphs pass through unchanged in substance."""
    out: list[str] = []
    cur: list[str] = []

    def flush() -> None:
        if cur:
            joined = "\n".join(cur)
            joined = re.sub(r"(?<=[a-zäöüß])-\n(?=[a-zäöüß])", "", joined)
            joined = re.sub(r"-\n(?=[A-ZÄÖÜ])", "-", joined)
            joined = re.sub(r"\s+", " ", joined).strip()
            out.append(re.sub(r"(?<=\w)\s+\.(?=\s|$)", ".", joined))
            cur.clear()

    for line in (text or "").splitlines():
        if _PAGE_FURNITURE.match(line):
            continue
        line = line.strip()
        if not line:
            if cur and cur[-1].rstrip().endswith((".", ":")):
                flush()
        elif _LAND_HEAD.match(line):
            flush()
            out.append(line)
        else:
            cur.append(line)
    flush()
    return out


def _sentences(text: str) -> list[tuple[str, str]]:
    """(sentence, Land code in force) — a Land header line sets the Land of
    the lines below; a sentence naming one Land is that Land's."""
    out: list[tuple[str, str]] = []
    current = ""
    for line in _paragraphs(text):
        head = _LAND_HEAD.match(line)
        if head:
            current = _land_code(head.group(1))
            continue
        # a header run into its paragraph: "Land Rheinland-Pfalz Zur geschützten …"
        lead = re.match(r"^(?:Im\s+)?(?:(?:Bundes)?[Ll]and\s+)?(" + _LAND_RE.pattern + r")\s+(?=(?:Zur?|Die|Das)\s)", line)
        if lead:
            current = _land_code(lead.group(1))
            line = line[lead.end():]
        # sentence ends: a full stop after a closing bracket or a word of
        # three letters or more ("St. Goar", "a. Stein" and "b. A." stay whole)
        for sent in re.split(r"(?<=[\)\w]{3})\.\s+(?=[A-ZÄÖÜ„])", line):
            sent = sent.strip()
            if not sent:
                continue
            named = {_land_code(m.group(0)) for m in _LAND_RE.finditer(sent)} - {""}
            land = current
            if len(named) == 1:
                land = next(iter(named))
                current = land
            out.append((sent, land))
    return out


def parse(text: str) -> list[Unit]:
    """The units of a delimitation text, in text order."""
    units: list[Unit] = []
    for sent, land in _sentences(text):
        if _TAIL.search(sent):
            # the closing sentences name no unit; a list never follows them
            head = _TAIL.split(sent)[0]
            if len(_NUMBER_GROUP.findall(head)) < 1 and "Gemarkung" not in head:
                continue
            sent = head
        sent = re.sub(r"\s+stammen\s*$", "", sent.rstrip(" ."))
        if len(_NUMBER_GROUP.findall(sent)) >= 1 and not re.search(r"\(0\d{4}\b", sent):
            body = _NUMBERED_LEAD.sub("", sent, count=1)
            body = re.sub(r"\s+stammen\s*$", "", body)
            got = _numbered_items(body, land)
            if got:
                units += got
                continue
        cities = list(_CITY.finditer(sent))
        if cities:
            for m in cities:
                holder = _bare(m.group("holder"))[0]
                for n in _names(m.group("names")):
                    name, gloss = _bare(n)
                    units.append(Unit("gemarkung", name, land, holder=holder, gloss=gloss))
            continue
        gm = _GEMARKUNGEN.search(sent)
        if gm:
            units += _by_kreis(gm.group("rest"), land)
            continue
        ge = _GEMEINDEN.search(sent)
        if ge:
            body = _REPEATED_LEAD.sub(", ", _GEMEINDEN_END.sub("", ge.group("names")))
            body = re.sub(r"\s*,\s*,\s*", ", ", body)
            groups = list(_BY_KREIS.finditer(body))
            if groups and all(g.group("kreis") for g in groups):
                pos = 0
                for g in groups:
                    for n in _names(g.group("names").lstrip(", ")):
                        units.append(Unit("gemeinde", _TITLE.sub("", n), land, kreis=_kreis(g.group("kreis"))))
                    pos = g.end()
                rest = body[pos:]
            else:
                rest = body
            for n in _names(rest):
                km = _KREIS_GLOSS.search(n)
                kreis = _kreis(km.group(1)) if km else ""
                n = _KREIS_GLOSS.sub("", n).strip()
                units.append(Unit("gemeinde", _TITLE.sub("", n), land, kreis=kreis))
    return units


def _kreis(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip(" .,;")


def _by_kreis(rest: str, land: str) -> list[Unit]:
    """"A, B und C im Landkreis X, D und E im Landkreis Y sowie … des Landes
    Z", then whatever follows the last group: "Weimar Ortsteil Schöndorf",
    "die kreisfreien Städte Jena und Erfurt"."""
    units: list[Unit] = []
    rest = re.sub(r"\s+des\s+(?:Bundes)?[Ll]andes\s.*$", "", rest, flags=re.DOTALL)
    pos = 0
    for g in _BY_KREIS.finditer(rest):
        names = g.group("names").lstrip(", ")
        names = re.sub(r"^\s*sowie\s+", "", names)
        holder = ""
        hm = _HOLDER_TAIL.search(names)
        if hm:
            holder = _bare(hm.group("holder"))[0] if not _is_name_bracket(hm.group("holder")) else hm.group("holder")
            names = names[:hm.start()]
        for n in _names(names):
            units.append(Unit("gemarkung", n, land, holder=holder, kreis=_kreis(g.group("kreis"))))
        pos = g.end()
    tail = rest[pos:].lstrip(" ,")
    kf = _KREISFREI.search(tail)
    if kf:
        for n in _names(kf.group("names")):
            units.append(Unit("gemeinde", n, land))
        tail = tail[:kf.start()]
    for n in _names(tail):
        om = _ORTSTEIL.match(n)
        if om:
            units.append(Unit("ortsteil", om.group("name").strip(), land, holder=om.group("holder").strip()))
        elif pos == 0:
            # a Gemarkung list with no Kreis at all
            units.append(Unit("gemarkung", n, land))
    return units


def _is_name_bracket(name: str) -> bool:
    """"Werder (Havel)": the bracket is part of the town's name."""
    return bool(re.search(r"\((?:Havel|Saale|Unstrut|Helme|Mosel|Pfalz|Rhein|Main|Elbe|Oder)\)\s*$", name))


# ─────────────────────────────────────────────────────── resolve ──

# Kreis names the texts print → the 5-digit key. Checked against the Gemeinde
# keys of the Länder's own layers (tests/test_de_area_units.py): every
# Gemarkung a text files under a Kreis lies in a Gemeinde of that key.
KREIS_AGS: dict[str, str] = {
    norm_name(k): v for k, v in {
        "Burgenlandkreis": "15084", "Harz": "15085", "Mansfeld-Südharz": "15087",
        "Saalekreis": "15088", "Salzlandkreis": "15089",
        "Weimarer Land": "16071", "Saale-Holzland-Kreis": "16074",
        "Saalfeld-Rudolstadt": "16073", "Sömmerda": "16068",
        "Unstrut-Hainich-Kreis": "16064",
        "Potsdam-Mittelmark": "12069",
        "Ahrweiler": "07131", "Bad Kreuznach": "07133", "Birkenfeld": "07134",
        "Cochem-Zell": "07135", "Mayen-Koblenz": "07137", "Neuwied": "07138",
        "Rhein-Hunsrück-Kreis": "07140", "Rhein-Lahn-Kreis": "07141",
        "Bernkastel-Wittlich": "07231", "Trier-Saarburg": "07235",
        "Alzey-Worms": "07331", "Bad Dürkheim": "07332", "Donnersbergkreis": "07333",
        "Germersheim": "07334", "Kusel": "07336", "Südliche Weinstraße": "07337",
        "Mainz-Bingen": "07339",
        "Regionalverband Saarbrücken": "10041", "Merzig-Wadern": "10042",
        "Neunkirchen": "10043", "Saarlouis": "10044", "Saar-Pfalz-Kreis": "10045",
        "Saarpfalz-Kreis": "10045", "St. Wendel": "10046",
    }.items()
}

PINS_PATH = Path(__file__).with_name("area_unit_pins.json")


def load_pins(path: Path = PINS_PATH) -> dict[str, dict[str, dict]]:
    """{file_number: {unit label: {units: [{land, schluessel} | {gemeinde}],
    reason, source, verified}}} — a name the text prints that no layer
    carries as such (a former Gemeinde whose Gemarkungen kept their own
    names, a Kreis the text misplaces), bound to what it names. `same_as`
    hands a record the pins of another whose list it shares."""
    if not path.exists():
        return {}
    data = {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items()
            if not k.startswith("__")}
    return {fn: dict(data.get(v["same_as"], {})) if isinstance(v, dict) and v.get("same_as") else v
            for fn, v in data.items()}

NAME_MATCH_MIN = 0.8


@dataclass
class Bound:
    unit: Unit
    how: str                      # gemarkung | gemeinde | gemeinde-for-part
    label: str                    # the layer's name for what is drawn
    geometry: object = None
    lau_id: str = ""              # GISCO_ID of the commune it lies in / is
    land: str = ""
    number: int | None = None     # a Gemarkung's register number
    gemeinde: str = ""            # the Gemeinde a Gemarkung lies in


@dataclass
class Resolved:
    bound: list[Bound] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    disagree: list[str] = field(default_factory=list)

    @property
    def share(self) -> float:
        total = len(self.bound) + len(self.unmatched)
        return len(self.bound) / total if total else 0.0


class CommuneRows:
    """GISCO LAU rows of Germany: (GISCO_ID "DE_<AGS8>", LAU_NAME, geometry)."""

    def __init__(self, rows: list[tuple[str, str, object]]) -> None:
        self.rows = rows
        self._by: dict[tuple[str, str], list[tuple[str, str, object]]] = {}
        for gid, name, geom in rows:
            for key in _commune_keys(name):
                self._by.setdefault((gid[3:5], key), []).append((gid, name, geom))
        self._by_id = {gid: (gid, name, geom) for gid, name, geom in rows}

    def find(self, ags2: str, name: str, kreis: str = "") -> list[tuple[str, str, object]]:
        hits = self._by.get((ags2, norm_name(name)), [])
        if not hits:
            bare, gloss = _bare(name)
            hits = self._by.get((ags2, norm_name(bare)), [])
            if not hits and gloss:
                # "Mülheim (Mosel)" is GISCO's "Mülheim an der Mosel"
                head, tail = norm_name(bare) + " ", " " + norm_name(gloss)
                hits = [h for (a, key), rows in self._by.items() if a == ags2
                        and key.startswith(head) and key.endswith(tail) for h in rows]
        if kreis:
            hits = [h for h in hits if h[0][3:8] == kreis]
        seen, out = set(), []
        for h in hits:
            if h[0] not in seen:
                seen.add(h[0])
                out.append(h)
        if len(out) > 1:
            # the key folds umlauts and brackets: "Bärweiler" is not Barweiler,
            # "Sankt Katharinen" not "Sankt Katharinen (Landkreis Neuwied)"
            exact = [h for h in out if _strip_title(h[1]).casefold() == name.strip().casefold()]
            if len(exact) == 1:
                return exact
        return out

    def by_ags(self, ags: str):
        return self._by_id.get("DE_" + ags)


def _commune_keys(lau_name: str) -> set[str]:
    """The keys a GISCO name answers to: whole, without its municipal title
    after the comma ("Eltville am Rhein, Stadt"), and without a bracket
    ("Lorch (Rheingau)" is the text's "Lorch")."""
    base = _strip_title(lau_name)
    keys = {norm_name(base), norm_name(_bare(base)[0]), norm_name(base.split("/")[0])}
    return {k for k in keys if k}


_MUNICIPAL_TITLE = re.compile(r",\s*(?:[\w\-. ]*[Ss]tadt|Kurort|Marktflecken|Flecken|St|M|GKSt)\.?\s*$")


def _strip_title(lau_name: str) -> str:
    """GISCO's name without its municipal titles ("Sankt Goarshausen,
    Loreleystadt, Stadt" carries two)."""
    base = lau_name or ""
    while _MUNICIPAL_TITLE.search(base):
        base = _MUNICIPAL_TITLE.sub("", base)
    return base.strip()


def _name_forms(name: str) -> list[str]:
    """The forms a printed name is looked up by: whole, without its bracket,
    and the part before a slash ("Freyburg/Unstrut", "Perl/Nennig")."""
    forms = [name, _bare(name)[0], name.split("/")[0].strip(),
             re.sub(r"(?<=[a-zäöüß])(?=[A-ZÄÖÜ])", "-", name)]
    return list(dict.fromkeys(f for f in forms if f))


def _vote_land(units: list[Unit], communes: CommuneRows) -> str:
    """The Land of a Gemeinde list that names none (Rheinhessen's): the one
    most of its names are communes of."""
    votes: dict[str, int] = {}
    for u in units:
        seen = set()
        for form in _name_forms(u.name):
            for code, ags2 in AGS2.items():
                if code not in seen and communes.find(ags2, form):
                    seen.add(code)
        for code in seen:
            votes[code] = votes.get(code, 0) + 1
    if not votes:
        return ""
    best = max(votes, key=votes.get)
    return best if votes[best] >= 0.8 * len(units) else ""


def resolve(units: list[Unit], gemarkungen, communes: CommuneRows,
            pins: dict[str, dict] | None = None) -> Resolved:
    """Bind every unit. `gemarkungen` is a `katasterbezirk.Gemarkungen`;
    `pins` the record's entries of area_unit_pins.json."""
    out = Resolved()
    pins = pins or {}
    lands_on_disk = gemarkungen.lands if gemarkungen is not None else set()
    # the register a list without a Land prints its numbers from: the one
    # most of its names agree with
    guess_numbered = ""
    unlabelled = [u for u in units if u.kind == "numbered" and not u.land]
    if unlabelled:
        best = 0
        for code in NUMBERED_LANDS:
            if code not in lands_on_disk:
                continue
            n = sum(1 for u in unlabelled if _number_row(gemarkungen, code, u) is not None)
            if n > best:
                best, guess_numbered = n, code
    plain = [u for u in units if u.kind == "gemeinde" and not u.land]
    guess_named = _vote_land(plain, communes) if plain else ""
    for u in units:
        land = u.land or (guess_numbered if u.kind == "numbered" else guess_named)
        label = _label(u)
        pin = pins.get(label)
        if pin is not None:
            got = _pinned(u, pin, gemarkungen, communes)
            if got:
                out.bound += got
            else:
                out.unmatched.append(label + " (stale pin)")
            continue
        ags2 = AGS2.get(land, "")
        if u.kind == "numbered":
            if land not in lands_on_disk:
                # a Land whose layer is not read: the Gemeinde the unit names
                hits = []
                for form in _name_forms(u.name):
                    hits = communes.find(ags2, form) if ags2 else []
                    if hits:
                        break
                if len(hits) == 1:
                    out.bound.append(Bound(u, "gemeinde-for-part", hits[0][1].split(",")[0],
                                           hits[0][2], hits[0][0], land))
                else:
                    out.unmatched.append(label)
                continue
            row = gemarkungen.by_number(land, u.number)
            if row is None:
                out.unmatched.append(label)
                continue
            if _number_row(gemarkungen, land, u) is None:
                out.disagree.append(f"{label}: {row['name']}, {row['gemeinde']}")
                out.unmatched.append(label)
                continue
            out.bound.append(Bound(u, "gemarkung", row["name"], row["geometry"],
                                   "DE_" + row["ags"] if row["ags"] else "", land))
            continue
        kreis = KREIS_AGS.get(norm_name(u.kreis), "") if u.kreis else ""
        if u.kind in ("gemarkung", "ortsteil"):
            rows = []
            if land in lands_on_disk:
                for form in _name_forms(u.name):
                    rows = gemarkungen.by_name(land, form, kreis=kreis, gemeinde=u.holder)
                    if rows:
                        break
            if len(rows) == 1:
                row = rows[0]
                out.bound.append(Bound(u, "gemarkung", row["name"], row["geometry"],
                                       "DE_" + row["ags"] if row["ags"] else "", land))
                continue
            if not rows and u.holder and ags2:
                # no Gemarkung of that name in the town: the town, whole
                hits = communes.find(ags2, u.holder, kreis)
                if len(hits) == 1:
                    out.bound.append(Bound(u, "gemeinde-for-part", hits[0][1].split(",")[0],
                                           hits[0][2], hits[0][0], land))
                    continue
            out.unmatched.append(label + (f" ({len(rows)} of that name)" if len(rows) > 1 else ""))
            continue
        # a Gemeinde that prints its own districts in a bracket — "Alzey (Alzey,
        # Dautenheim, Heimersheim, Weinheim)", "Bingen am Rhein (mit Ausnahme
        # Bingerbrück)" — is those Gemarkungen, where the Land's layer is read
        # and every name is one of that Gemeinde's
        if land in lands_on_disk:
            rows = _bracket_gemarkungen(u, land, kreis, gemarkungen)
            if rows:
                out.bound += [Bound(u, "gemarkung", r["name"], r["geometry"],
                                    "DE_" + r["ags"] if r["ags"] else "", land) for r in rows]
                continue
        # a Gemeinde
        hits = []
        for form in _name_forms(u.name):
            hits = communes.find(ags2, form, kreis) if ags2 else []
            if hits:
                break
        if len(hits) > 1 and not kreis:
            bracket = KREIS_AGS.get(norm_name(_bare(u.name)[1]), "")
            if bracket:
                hits = [h for h in hits if h[0][3:8] == bracket]
        if len(hits) == 1:
            out.bound.append(Bound(u, "gemeinde", hits[0][1].split(",")[0], hits[0][2], hits[0][0], land))
        else:
            out.unmatched.append(label + (f" ({len(hits)} of that name)" if len(hits) > 1 else ""))
    return out


_EXCEPT = re.compile(r"^mit\s+Ausnahme\s+(?:von\s+)?", re.IGNORECASE)


def _bracket_gemarkungen(u: Unit, land: str, kreis: str, gemarkungen) -> list[dict]:
    """The Gemarkungen a Gemeinde's bracket names (or, after "mit Ausnahme",
    all of the Gemeinde's but those); [] when the bracket is no such list or
    a name in it is not a Gemarkung of that Gemeinde — the Gemeinde is then
    drawn whole. A name is matched inside the Gemeinde only, so a spelling
    the register writes otherwise ("Groß-Winternheim" / Großwinternheim,
    "Rheindürckheim" / Rheindürkheim) is safe to read by likeness."""
    bare, gloss = _bare(u.name)
    if not gloss or _is_name_bracket(u.name) or norm_name(gloss) in KREIS_AGS:
        return []
    pool = [r for r in gemarkungen.of_gemeinde(land, bare) if not kreis or r["ags"].startswith(kreis)]
    if len({r["ags"] for r in pool}) != 1:
        return []
    excepted = bool(_EXCEPT.match(gloss))
    parts = [p.strip() for p in re.split(r",|\s+und\s+", _EXCEPT.sub("", gloss)) if p.strip()]
    if not parts or any(not p[0].isupper() for p in parts):
        return []
    found: list[dict] = []
    for part in parts:
        hits = [r for r in pool if norm_name(r["name"]) == norm_name(part)]
        if not hits:
            scored = sorted(((name_agreement(part, r["name"]), r) for r in pool),
                            key=lambda x: -x[0])
            if scored and scored[0][0] >= 0.9 and (len(scored) == 1 or scored[1][0] < 0.9):
                hits = [scored[0][1]]
        if len(hits) != 1:
            return []
        found.append(hits[0])
    if excepted:
        gone = {r["schluessel"] for r in found}
        return [r for r in pool if r["schluessel"] not in gone]
    return found


def _pinned(u: Unit, pin: dict, gemarkungen, communes: CommuneRows) -> list[Bound]:
    """The units a pin binds a printed name to; [] when one of them is gone
    from its layer (the pin is stale)."""
    out: list[Bound] = []
    for target in pin.get("units") or []:
        if target.get("gemeinde"):
            hit = communes.by_ags(target["gemeinde"].removeprefix("DE_"))
            if hit is None:
                return []
            out.append(Bound(u, "gemeinde-for-part" if pin.get("partial") else "gemeinde",
                             hit[1].split(",")[0], hit[2], hit[0], u.land))
            continue
        row = (gemarkungen.by_number(target["land"], int(str(target["schluessel"])[-4:]))
               if gemarkungen is not None else None)
        if row is None or row["schluessel"] != str(target["schluessel"]):
            return []
        out.append(Bound(u, "gemarkung", row["name"], row["geometry"],
                         "DE_" + row["ags"] if row["ags"] else "", target["land"],
                         number=row["number"], gemeinde=row["gemeinde"]))
    return out


def pin_text(label: str, bound: list[Bound]) -> str:
    """What the card prints for a unit read through a pin: "Breitscheid
    (0261) → 3501 Breitscheid" (a number read as another), "Stedten → Stedten
    (Seegebiet Mansfelder Land)" (the same name, placed), "Kromsdorf →
    Großkromsdorf, Kleinkromsdorf", "Oberperl (3560) → Perl"."""
    parts = []
    for b in bound:
        if b.how != "gemarkung":
            parts.append(b.label)
        elif b.unit.kind == "numbered" and b.number is not None:
            parts.append(f"{b.number:04d} {b.label}")
        elif norm_name(b.label) == norm_name(_bare(b.unit.name)[0]) and b.gemeinde:
            parts.append(f"{b.label} ({_strip_title(b.gemeinde)})")
        else:
            parts.append(b.label)
    return f"{label} → {', '.join(parts)}"


def _number_row(gemarkungen, land: str, u: Unit):
    row = gemarkungen.by_number(land, u.number)
    if row is None:
        return None
    # the Kreis the text glosses the name with must be the row's: Mittelrhein
    # prints "Breitscheid (Landkreis Mainz-Bingen) (0261)", and 0261 is the
    # Breitscheid of the Landkreis Neuwied
    kreis = KREIS_AGS.get(norm_name(u.kreis), "") if u.kreis else ""
    if kreis and row["ags"] and not row["ags"].startswith(kreis):
        return None
    printed = [u.name, _bare(u.name)[0], re.sub(r"^[^/]*/", "", u.name)]
    if any(name_agreement(p, row["name"], row["gemeinde"]) >= NAME_MATCH_MIN for p in printed if p):
        return row
    if u.holder and name_agreement(u.holder, row["gemeinde"]) >= NAME_MATCH_MIN \
            and name_agreement(_bare(u.name)[0], row["name"]) >= 0.6:
        return row
    return None


def _label(u: Unit) -> str:
    if u.kind == "numbered":
        return f"{u.name} ({u.number:04d})"
    if u.kind == "ortsteil":
        return f"{u.holder} Ortsteil {u.name}"
    return u.name + (f" ({u.gloss})" if u.gloss else "")


# ───────────────────────────────────────────────────────── load ──

# A record is read through this module when its text names at least this
# many units (a two-commune sentence in a Landwein's prose is not a list).
MIN_UNITS = 4


def load_areas(extracted_dir: Path, sidecar_dir: Path | None = None) -> dict[str, dict]:
    """{file_number: {units, source_kind, slug}} for the DE parent records
    whose delimitation this module reads: the EU single document's area
    section, else § 3 / § 4 of the BLE Produktspezifikation (the stage-02f
    sidecar's `area_text`)."""
    out: dict[str, dict] = {}
    for path in sorted(Path(extracted_dir).glob("*.json")):
        if path.name.startswith("_"):
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        fn = rec.get("file_number") or ""
        if not fn or rec.get("is_sub_denomination"):
            continue
        units = parse((rec.get("section_roles") or {}).get("geo_area") or "")
        kind = "eu-single-document"
        if len(units) < MIN_UNITS and sidecar_dir is not None:
            side = Path(sidecar_dir) / f"{rec.get('slug')}.json"
            if side.exists():
                units = parse(json.loads(side.read_text(encoding="utf-8")).get("area_text") or "")
                kind = "ble-produktspezifikation"
        if len(units) >= MIN_UNITS:
            out[fn] = {"units": units, "source_kind": kind, "slug": rec.get("slug") or ""}
    return out
