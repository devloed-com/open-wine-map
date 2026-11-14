"""The seat of a commune nouvelle: a commune of today the aire holds in part.

A commune nouvelle keeps the INSEE code of its seat. A row INAO wrote for
« Putanges-Pont-Écrepin » (61339) therefore reads today as Putanges-le-Lac,
nine former communes, and IGN's polygon under that code is all of them.

The delimitation does not move with a merger, and INAO says so in the cahiers
themselves. 268 of the 500 French cahiers of the build date their commune list
— "sur la base du code officiel géographique de l'année 2020" — and the
Official Journal notice of each such redraft gives the reason: the reference
to the code "permet de référencer l'aire géographique par rapport à la version en
vigueur en 2019 du code officiel géographique, édité par l'INSEE et de
sécuriser juridiquement la délimitation de l'aire géographique. Le périmètre
de l'aire géographique reste strictement identique", "afin que celle-ci ne
soit pas impactée ultérieurement par des fusions ou scissions de communes ou
de parties de communes, ou des changements de nom" (Marsannay,
PDO-FR-A0175-AM01, OJ C 89 of 16.3.2021, p. 11, items 1 and 3). Where a commune
nouvelle is only partly inside, the redrafted list says which part: "Tuffalun
(pour le seul territoire de la commune déléguée d'Ambillou-Château)" — 521
such restrictions in the build's cahiers. A list that was never redrafted
still names the commune of its day (Calvados, décret of 2015: « Putanges-
Pont-Écrepin »).

So the cahier's wording decides, on positive evidence only (`narrowed_seats`):

- it names the commune of today and **restricts** it to former communes — the
  former communes the restriction names are drawn, each by its own outline;
- it names the seat **by its former name** and nowhere the commune of today —
  the seat's former outline is drawn, and with it any other former commune of
  the same commune the text names;
- it names the commune of today **without restriction** — the whole commune,
  as before;
- the commune **kept its name** through the merger (Montsûrs, La Gacilly), so
  the name cannot tell: the date does. A list dated before the merger — its
  code officiel géographique year, else the cahier's homologation — names the
  commune of that day: the seat's former outline (a décret of February 2015
  cannot name the Montsûrs of 2019). Dated on or after it, the whole commune;
- anything else (the text names neither, or lists no commune) — the whole
  commune, as before.

A seat is narrowed only when every part has an outline of its own
(geo.api.gouv.fr's communes déléguées, the layer of `former_communes.py`) and
no former commune the rows carry would lose its ground; otherwise the commune
stays whole. With the layer missing nothing is narrowed.
"""
from __future__ import annotations

import re
import unicodedata

_PROXIMITY_RE = re.compile(r"(?i)proximit[ée]\s+imm[ée]diate")
# page furniture inside a list: the page number, the BO running header
_FURNITURE_RE = re.compile(
    r"(?m)^[ \t\x0c]*(?:\d{1,3}(?:[ \t]*/[ \t]*\d{1,3})?|Publie a[ui] BO[^\n]*)[ \t]*$"
)
_PAREN_RE = re.compile(r"\s*\(([^)]{0,600})\)")
_PAREN_RESTRICTION_RE = re.compile(
    r"(?i)territoire|anciennes?\s+communes?|communes?\s+deleguees?|communes?\s+associees?"
)
_BARE_RESTRICTION_RE = re.compile(
    r"(?i)\s*,?\s*(pour\s+l[ea]s?\s+seule?s?\s+(?:territoires?|part(?:ie)?s?)\b[^.;()]{0,400})"
)
_COG_RE = re.compile(r"(?i)code\s+officiel\s+g[ée]ographique[^.:\n]{0,60}?((?:19|20)\d\d)")
_DEPT_HEAD_RE = re.compile(
    r"(?i)departements?\s+(?:du\s+|de\s+la\s+|de\s+l'\s*|des\s+|de\s+|d'\s*)"
    r"([A-Z][\w'-]*(?:[ \t-]+[A-Z][\w'-]*)*)"
)


def flat(s: str) -> str:
    """Accents and ligatures folded, one apostrophe: the form names are matched in."""
    s = s.replace("œ", "oe").replace("Œ", "Oe").replace("æ", "ae").replace("’", "'")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def name_pattern(name: str) -> re.Pattern:
    """A commune name as a whole item of flattened text, hyphens and spaces alike."""
    body = re.escape(flat(name))
    body = body.replace(r"\-", r"[-\s]+").replace(r"\ ", r"[-\s]+").replace(r"\'", r"['\s]*")
    return re.compile(r"(?<![\w-])" + body + r"(?![\w-])", re.IGNORECASE)


def zone_text(record: dict) -> str:
    """The record's delimitation text up to the proximity zone, flattened."""
    raw = (record.get("section_roles") or {}).get("aire") or ""
    if not isinstance(raw, str) or not raw:
        raw = (record.get("sections") or {}).get("IV") or ""
    if not isinstance(raw, str):
        return ""
    zone = flat(_PROXIMITY_RE.split(raw)[0])
    return _FURNITURE_RE.sub("", zone).replace("\x0c", "")


def cog_year(record: dict) -> str | None:
    """The year of the code officiel géographique the cahier dates its list to."""
    for body in (record.get("sections") or {}).values():
        if isinstance(body, str):
            m = _COG_RE.search(body.replace("\n", " "))
            if m:
                return m.group(1)
    return None


def reference_date(record: dict) -> str | None:
    """The day the cahier's commune list is dated to (ISO): 1 January of its
    code officiel géographique year, else the homologation of the cahier."""
    year = cog_year(record)
    if year:
        return f"{year}-01-01"
    return (record.get("source") or {}).get("homologated_at") or None


def _restriction_after(zone: str, end: int) -> tuple[str, int] | None:
    """The clause that restricts the name ending at `end`, and where it ends."""
    m = _PAREN_RE.match(zone, end)
    if m and _PAREN_RESTRICTION_RE.search(m.group(1)):
        return m.group(1), m.end()
    m = _BARE_RESTRICTION_RE.match(zone, end)
    if m:
        return m.group(1), m.end()
    return None


def _named(zone: str, name: str, code: str) -> re.Match | None:
    """The first mention of `name` that stands under no heading of another
    département than the code's: « Conteville » in the Eure's list is not
    Conteville (Calvados), a former commune of Valambray."""
    from _lib.geom_chain import dept_code_for  # lazy: geom_chain imports this module

    for m in name_pattern(name).finditer(zone):
        heads = list(_DEPT_HEAD_RE.finditer(zone, 0, m.start()))
        dept = dept_code_for(heads[-1].group(1).strip()) if heads else None
        if dept is None or code.startswith(dept) or (dept == "20" and code[:2] in ("2A", "2B")):
            return m
    return None


def _same(a: str, b: str) -> bool:
    key = lambda s: re.sub(r"[^a-z0-9]", "", flat(s).lower())  # noqa: E731
    return key(a) == key(b)


def narrowed_seats(
    record: dict, codes: set[str], names: dict[str, str], former,
) -> dict[str, dict]:
    """`codes`: the aire's commune codes; `names`: code → name of the communes
    of today; `former`: `former_communes.load(...)`. Returns, per commune of
    today the cahier holds only in part, `{"parts": [codes], "names": [...],
    "geoms": [...], "why": "restricted" | "old-name" | "dated", "evidence": str}`
    — the former communes to draw in its place."""
    out: dict[str, dict] = {}
    if not former or not getattr(former, "seats", None):
        return out
    zone = None
    for code in sorted(codes):
        if code not in names:
            continue
        others = former.predecessors.get(code, set()) - {code}
        absent = others - codes
        if not absent:
            continue
        if zone is None:
            zone = zone_text(record)
        if not zone:
            return out
        today, seat = names[code], former.seat_names.get(code) or ""
        clauses: list[tuple[str, int, int]] = []
        occurrences = list(name_pattern(today).finditer(zone))
        for m in occurrences:
            hit = _restriction_after(zone, m.end())
            if hit:
                clauses.append((hit[0], m.end(), hit[1]))
        free = [
            m for m in occurrences
            if not any(m.end() == start or start <= m.start() < end for _c, start, end in clauses)
        ]
        label = {code: seat, **{p: former.name(p) for p in others}}
        dated = None
        if free:
            # named without restriction: the whole commune — unless it kept
            # its name and the list is older than the merger
            joined = [former.merged_on[p] for p in absent if p in former.geoms and p in former.merged_on]
            ref = reference_date(record)
            if not (seat and _same(seat, today) and ref and joined and ref < min(joined)):
                continue
            dated = (ref, min(joined))
        if dated:
            parts = {code} | {p for p in absent if _named(zone, label[p], p)}
            why = "dated"
            evidence = f"list dated {dated[0]}, merger of {dated[1]}"
        elif clauses:
            text = " ".join(c for c, _s, _e in clauses)
            parts = {p for p, n in label.items() if n and name_pattern(n).search(text)}
            why, evidence = "restricted", f"{today} ({re.sub(r'\\s+', ' ', clauses[0][0]).strip()})"
        elif seat and not _same(seat, today) and (m := _named(zone, seat, code)):
            parts = {code} | {p for p in absent if _named(zone, label[p], p)}
            why = "old-name"
            evidence = re.sub(r"\s+", " ", zone[max(0, m.start() - 40): m.end() + 40]).strip()
        else:
            continue
        if not parts or not (absent - parts):
            continue  # nothing recognised, or every former commune is named
        # every former commune of the aire must keep its ground: the parts by
        # their outlines, the rows' own former communes by theirs
        geoms = [former.seats.get(p) if p == code else former.geoms.get(p) for p in sorted(parts)]
        if any(g is None for g in geoms) or any(p not in former.geoms for p in others & codes):
            continue
        out[code] = {
            "parts": sorted(parts), "names": [label[p] for p in sorted(parts)],
            "geoms": geoms, "why": why, "evidence": evidence, "today": today,
        }
    return out
