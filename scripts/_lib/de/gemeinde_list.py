"""Bavarian Gemeinde lists — the layout Franken and Landwein Main are delimited in.

Franken's EU single document (C/2025/6794, section 9) and the single
document and BLE Produktspezifikation of Landwein Main (§ 4) list "die
Rebflächen folgender Städte, Gemeinden und deren Ortsteile" by
Regierungsbezirk and Kreis:

    Regierungsbezirk Unterfranken:
    Kreisfreie Städte: Aschaffenburg, Schweinfurt, Würzburg
    Landkreis Aschaffenburg: Alzenau in Unterfranken, Großostheim, Hösbach

Bétard 2022 drew Franken before the amendment PDO-DE-A1267-AM01 (8 October
2025) removed fifteen Gemeinden and added three (feedback triage
2026-11-24), and Landwein Main — whose own list is not Franken's — was drawn
as Franken's polygon. The listed Gemeinden are drawn instead, from GISCO LAU
2024: the same commune resolution Bétard had, from the text in force.

  parse_lists(text)          the (Regierungsbezirk, Kreis, names) lists;
  resolve(lists, rows)       each name to one GISCO commune, scoped to its
                             Regierungsbezirk and Kreis;
  load_areas(extracted_dir)  the DE parent records whose area text is such
                             a list.

A name is bound only inside its Regierungsbezirk (the AGS digit after "09")
and, for a Landkreis, inside the Kreis most of the group's names fall in; a
name that matches nothing there, or several communes, is reported and not
drawn — never guessed.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Bavarian Regierungsbezirke and their AGS digit (09 + digit + Kreis).
RB_DIGIT = {
    "oberbayern": "1", "niederbayern": "2", "oberpfalz": "3", "oberfranken": "4",
    "mittelfranken": "5", "unterfranken": "6", "schwaben": "7",
}

_RB_HEAD = re.compile(
    r"Regierungsbezirk\s+(Oberbayern|Niederbayern|Oberpfalz|Oberfranken|Mittelfranken|"
    r"Unterfranken|Schwaben)\s*:",
)
_KREIS_HEAD = re.compile(
    r"(?P<kf>Kreisfreie\s+St[äa]dte?)\s*:|Landkreis\s+(?P<lk>[^:—\n]+):",
)
_LIST_END = re.compile(r"Die\s+genaue\s+Abgrenzung")

# Words a Bavarian place name carries in one source and abbreviates or drops
# in another ("Sand am Main" / GISCO "Sand a.Main", "Alzenau in Unterfranken"
# / "Alzenau, St", "Neustadt a. d. Aisch" / "Neustadt a.d.Aisch, St").
_PARTICLES = {
    "a", "am", "an", "d", "der", "die", "dem", "den", "i", "im", "in", "b", "bei",
    "ob", "o", "u", "bay", "bayern", "ufr", "unterfranken", "mfr", "ofr", "opf",
}
# GISCO's municipal titles after the comma: Stadt, Markt, Große Kreisstadt …
_TITLE = re.compile(r",\s*(?:St|M|GKSt|Stadt|Markt|Gr\.?\s*Kreisstadt)\.?\s*$")

# A list is read as this layout only with a Regierungsbezirk header and at
# least this many names (the Rhineland lists name no Regierungsbezirk).
MIN_NAMES = 10


@dataclass
class KreisList:
    rb: str                 # Regierungsbezirk as printed
    rb_digit: str
    kreisfrei: bool
    kreis: str              # the Landkreis name ('' for kreisfreie Städte)
    names: list[str] = field(default_factory=list)


def name_key(name: str) -> str:
    """Comparison key: municipal title dropped, ß / umlauts / accents folded,
    punctuation to spaces, the particles above removed."""
    s = _TITLE.sub("", (name or "").strip())
    s = s.replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    words = re.sub(r"[^a-z0-9]+", " ", s).split()
    return " ".join(w for w in words if w not in _PARTICLES)


def _clean_list(block: str) -> list[str]:
    block = re.sub(r"(\w)-\s*\n\s*([a-zäöüß])", r"\1\2", block)
    block = block.replace("—", " ")
    block = re.sub(r"\s+", " ", block)
    out = []
    for part in re.split(r",|\s+und\s+", block):
        part = part.strip(" .;")
        if part and part[0].isupper():
            out.append(part)
    return out


def parse_lists(text: str) -> list[KreisList]:
    """Every "Kreisfreie Stadt / Städte:" and "Landkreis X:" list of a text,
    each under the Regierungsbezirk header before it. [] when the text has no
    Regierungsbezirk header."""
    text = text or ""
    rbs = list(_RB_HEAD.finditer(text))
    if not rbs:
        return []
    # The closing "Die genaue Abgrenzung ergibt sich aus den Karten …" ends
    # the last list; Franken's BLE § 4 also prints it before the first one.
    end = _LIST_END.search(text, rbs[-1].end())
    if end:
        text = text[:end.start()]
    out: list[KreisList] = []
    for i, rb in enumerate(rbs):
        block = text[rb.end():rbs[i + 1].start() if i + 1 < len(rbs) else len(text)]
        heads = list(_KREIS_HEAD.finditer(block))
        for j, h in enumerate(heads):
            body = block[h.end():heads[j + 1].start() if j + 1 < len(heads) else len(block)]
            out.append(KreisList(
                rb=rb.group(1), rb_digit=RB_DIGIT[rb.group(1).lower()],
                kreisfrei=bool(h.group("kf")),
                kreis=re.sub(r"\s+", " ", (h.group("lk") or "")).strip(),
                names=_clean_list(body),
            ))
    return out


def n_names(lists: list[KreisList]) -> int:
    return sum(len(k.names) for k in lists)


@dataclass
class Resolved:
    # (name as printed, GISCO_ID, LAU name)
    drawn: list[tuple[str, str, str]] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)

    @property
    def share(self) -> float:
        total = len(self.drawn) + len(self.unmatched)
        return len(self.drawn) / total if total else 0.0


def _candidates(key: str, rows: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
    """(GISCO_ID, LAU name) of the rows whose key is `key`; else the one row
    whose key extends it or that it extends by whole words; else the one row
    within a ratio of 92."""
    exact = [(gid, name) for gid, name, k in rows if k == key]
    if exact:
        return exact
    ext = [(gid, name) for gid, name, k in rows
           if k.startswith(key + " ") or key.startswith(k + " ")]
    if len(ext) == 1:
        return ext
    from rapidfuzz import fuzz
    near = [(gid, name) for gid, name, k in rows if fuzz.ratio(key, k) >= 92]
    return near if len(near) == 1 else []


def resolve(lists: list[KreisList], rows: list[tuple[str, str]]) -> Resolved:
    """Bind each listed name to one GISCO commune. `rows` are the Bavarian
    LAU rows as (GISCO_ID "DE_09…", LAU_NAME)."""
    keyed = [(gid, name, name_key(name)) for gid, name in rows]
    out = Resolved()
    for kl in lists:
        # AGS: 09 + Regierungsbezirk + Kreis; kreisfreie Städte are Kreis 6x,
        # Landkreise 7x / 8x.
        scope = [r for r in keyed if r[0][5:6] == kl.rb_digit
                 and ((r[0][6:7] == "6") == kl.kreisfrei)]
        found = {n: _candidates(name_key(n), scope) for n in kl.names}
        kreis = ""
        if not kl.kreisfrei:
            votes: dict[str, int] = {}
            for cands in found.values():
                if len(cands) == 1:
                    votes[cands[0][0][3:8]] = votes.get(cands[0][0][3:8], 0) + 1
            if votes:
                kreis = max(votes, key=votes.get)
        for n, cands in found.items():
            if kreis:
                cands = [c for c in cands if c[0][3:8] == kreis]
            if len(cands) == 1:
                out.drawn.append((n, cands[0][0], cands[0][1]))
            else:
                out.unmatched.append(n)
    return out


def load_areas(extracted_dir: Path, sidecar_dir: Path | None = None) -> dict[str, dict]:
    """{file_number: {lists, source_kind, slug}} for the DE parent records
    whose delimitation is a Bavarian Regierungsbezirk / Kreis list of at
    least MIN_NAMES names: the EU single document's area section
    (`section_roles.geo_area`, Franken), else § 4 of the BLE
    Produktspezifikation (the stage-02f sidecar's `area_text`, Landwein Main,
    whose single document prints the same names as one alphabetical run)."""
    out: dict[str, dict] = {}
    for path in sorted(Path(extracted_dir).glob("*.json")):
        if path.name.startswith("_"):
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        fn = rec.get("file_number") or ""
        if not fn or rec.get("is_sub_denomination"):
            continue
        lists = parse_lists((rec.get("section_roles") or {}).get("geo_area") or "")
        kind = "eu-single-document"
        if n_names(lists) < MIN_NAMES and sidecar_dir is not None:
            side = Path(sidecar_dir) / f"{rec.get('slug')}.json"
            if side.exists():
                lists = parse_lists(json.loads(side.read_text(encoding="utf-8")).get("area_text") or "")
                kind = "ble-produktspezifikation"
        if n_names(lists) >= MIN_NAMES:
            out[fn] = {"lists": lists, "source_kind": kind, "slug": rec.get("slug") or ""}
    return out
