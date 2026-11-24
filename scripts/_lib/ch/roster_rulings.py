"""Rosters a cantonal ordinance leaves to another act.

A Swiss wine ordinance often names no variety and says who does: an office's
ruling (Schwyz, Zürich), the government's own ordinance or decision (both
Appenzells, Glarus), a department's directives (Jura). The act sits on the
same law portal, one number on — RSJU 916.141 → 916.141.1, GS 916.610 →
916.611, bGS 920.16 → 920.161, GS IX D/621/1 → 621/2 — and until 2026-11-17
none was read: seven cantonal cards showed no grape, and five of them were
pinned "the regulator names no variety" (visitor flags on Schwyz and Jura;
Jura's roster was found only because Boris asked whether it might sit in an
unexpected place).


The Schwyz Verordnung über den Weinbau (SRSZ 312.711) names the canton's two
AOCs and gives the Amt für Landwirtschaft the power to set their requirements
(§ 1 Abs. 2 Bst. i, § 7); the office's Allgemeinverfügungen of 28 July 2025 —
one for «AOC Schwyz», one for «AOC Zürichsee» — carry the roster as an annex,
"Verzeichnis der zugelassenen Rebsorten". Zürich has no wine ordinance since
2018: the Amt für Landschaft und Natur's ruling of 26 June 2020 says
"Zugelassen sind die Traubensorten gemäss Anhang 2" and publishes that annex
as a document of its own. Until 2026-11-17 the three cards showed no grape
(visitor flag on Schwyz, 2026-11-11).

The Schwyz annexes are scans and Zürich's is a short text PDF; each list is
kept in `roster_rulings.json` with the ruling, the clause that makes it the
roster and the sha256 of the PDF stage 01 fetches;
`tests/test_ch_roster_rulings.py` checks every list against the cached PDF.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TABLE = Path(__file__).with_name("roster_rulings.json")
RULINGS_DIR = Path(__file__).resolve().parents[3] / "raw" / "ch" / "rulings"


def load(path: Path = TABLE) -> dict[str, dict]:
    """{slug: entry}, `varieties` resolved through `same_annex_as`."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {k: dict(v) for k, v in data.items() if not k.startswith("__")}
    for entry in out.values():
        ref = entry.get("same_annex_as")
        if ref and "varieties" not in entry:
            entry["varieties"] = list(out[ref]["varieties"])
    return out


def varieties(entry: dict, match_fn) -> list[dict]:
    """The lexicon's reading of a transcribed list, one variety per entry —
    the roster-table reader's cell rule (a bracketed gloss dropped, a
    "Cornalin / Landroter" cell tried name by name, a breeder code skipped,
    an exact or near-exact match only). A misprint is read through the
    entry's `read_as` (Glarus prints «Läon Millot»)."""
    from _lib.ch.reglement import table_varieties

    return table_varieties("\n".join(n for names in _readings(entry) for n in names), match_fn)


def _readings(entry: dict) -> list[list[str]]:
    """Per printed entry, the name(s) it is read as: itself, its `read_as`
    reading, or several where one entry names two varieties ("Elbling (rot
    und weiss)")."""
    read_as = entry.get("read_as") or {}
    out = []
    for printed in entry.get("varieties") or []:
        reading = read_as.get(printed, printed)
        out.append(list(reading) if isinstance(reading, list) else [reading])
    return out


_GLOSS = re.compile(r"\([^)]*\)")


def _is_breeder_code(name: str) -> bool:
    """"CAL 1-28", "VB 91-26-26", "Lac 1/02-05-35": a selection number, no
    variety name — a digit and no word of four letters beyond a station's
    acronym ("IRAC 2060"; "Seibel 9110" and "VB Jura 25" are names). A code
    the lexicon resolves is not counted here (`coverage` tries it first)."""
    bare = _GLOSS.sub(" ", name)
    words = [w for w in re.findall(r"[^\W\d_]{4,}", bare) if not w.isupper()]
    return bool(re.search(r"\d", bare)) and not words


def coverage(entry: dict, match_fn) -> dict:
    """What the card shows of the list: `entries` printed, `varieties` shown
    (two entries can be one variety — "Heida" and "Savagnin blanc"), `codes`
    left out as breeder codes, `unknown` names the grape lexicon does not
    hold. The card prints it wherever something is left out."""
    from _lib.ch.reglement import table_varieties

    slugs: set[str] = set()
    codes, unknown = 0, []
    for printed, names in zip(entry.get("varieties") or [], _readings(entry)):
        # a code VIVC files under a named variety is that variety («VB
        # 91-26-29» is Satin noir): tried before it counts as a code
        hits = table_varieties("\n".join(names), match_fn)
        if hits:
            slugs |= {h["slug"] for h in hits}
        elif all(_is_breeder_code(n) for n in names):
            codes += 1
        else:
            unknown.append(printed)
    return {"entries": len(entry.get("varieties") or []), "varieties": len(slugs),
            "codes": codes, "unknown": len(unknown), "unknown_names": unknown}


_STYLE_SLUG = {"blanc": "white", "noir": "red", "rose": "rose"}


def styles(entry: dict) -> dict[str, dict]:
    """{style: {clause, quote}} — the wine types the act's own clauses name
    (`wine_types`): "Auch Schaum-, Perl- und Likörweine können die
    kontrollierte Ursprungsbezeichnung «AOC Schwyz» tragen" (Ziff. 2.2), the
    Réserve rule's "Rotweine" and "Weissweine", "Spätlese", "Beerenauslese"
    (Ziff. 2.9), "Roséwein … mit Weisswein verschnitten" (Ziff. 2.10). Until
    2026-11-17 no reader read them and the Schwyz, Zürichsee and Zürich cards
    showed the berry-colour floor with "the regulator's text names no
    colour"."""
    from _lib.de.ble_styles import clause_styles

    out: dict[str, dict] = {}
    for item in (entry.get("wine_types") or {}).get("clauses") or []:
        for style in clause_styles(item["quote"]):
            out.setdefault(_STYLE_SLUG.get(style, style),
                           {"clause": item["clause"], "quote": item["quote"]})
    return out


def types_source(entry: dict) -> dict | None:
    """The record's source for wine types stated in a PDF other than the
    roster's (Zürich: the ruling itself, its Anhang 2 being published
    apart)."""
    doc = (entry.get("wine_types") or {}).get("document")
    if not doc:
        return None
    return {"kind": "cantonal-ruling", "url": doc["url"], "label": doc["label"],
            "sha256": doc.get("sha256", ""), "format": "pdf",
            "license": "Official act of a cantonal authority"}


def source(entry: dict) -> dict:
    """The record's `cantonal-reglement-roster` source for a roster act."""
    return {
        "kind": "cantonal-reglement-roster",
        "url": entry.get("page_url") or entry["url"],
        "label": f"{entry['ruling']}, {entry['annex']}",
        "applied_by": entry["clause"],
        "sha256": entry.get("sha256", ""),
        "format": "pdf",
        "license": "Official act of a cantonal authority",
    }
