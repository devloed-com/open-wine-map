"""Sub-regiões a caderno names but does not delimit, drawn from the national
act that does.

Vinho Verde's caderno (PDO-PT-A1545-AM01) lists nine sub-regiões, gives each
a grape table and requires a sub-região wine to come from grapes "produzidas
e vinificadas exclusivamente na respetiva sub-região" — but its area section
delimits the DO only. The sub-regiões are delimited by Portaria n.º
668/2010, Artigo 3.º and Anexo I ("Área geográfica de produção com indicação
de sub-região"), as republished by Portaria n.º 152/2015: by município, and
by freguesia where a município is shared (Cinfães, Vizela, Valongo,
Resende).

`subregiao_areas.json` (checked in) holds the act's table as printed — a row
without freguesias is "(*) Todo o concelho", a name the print splits or
misspells keeps the printed form beside it (`printed_as`) — and the acts read
for their effect on it (`reviewed_acts`). Stage 04 draws each sub-região
through the same freguesia resolver as a caderno's own units
(`freguesias.resolve_area_units`) and the card cites the act;
`tests/test_pt_subregiao_areas.py` checks every name against the PDF stage 00
fetched into raw/pt/dre/.

A caderno whose legal reference ("Referência jurídica", section 9.8 b) cites
an act no entry has reviewed makes the entry STALE: stage 04 says so on its
`[pt-geom]` line and the test fails, because that act may have changed the
table.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from pyproj import Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform

from .area_units import Item, Piece

TABLE_PATH = Path(__file__).resolve().parent / "subregiao_areas.json"
_TO_3035 = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True).transform

# An act citation — "Portaria n.º 668/2010", "Declaração de Retificação n.
# º27/2015", "Portarias n.os 949/2010 e 216/2014", "Portaria nº 333/2016",
# "Decreto-Lei 61/2020" — and the numbers a list adds to it ("…, 216/2014 e
# n.º 152/2015"), each read as the act type before it.
_ACT_KIND = (r"Portarias?|Declara[çc](?:[ãa]o|[õo]es)\s+de\s+Retifica[çc][ãa]o|Avisos?|"
             r"Decretos?(?:\s*-\s*|\s+)Leis?|Decretos?\s+Regulamentares?|"
             r"Despachos?(?:\s+Normativos?)?|Leis?")
_ACT_NO = r"(?:n\s*\.?\s*(?:[ºo°]s?|os)\s*)?(\d+(?:-[A-Z])?)\s*/\s*(\d{4}|\d{2})(?!\d)"
_ACT_RE = re.compile(rf"\b({_ACT_KIND})\s+{_ACT_NO}", re.IGNORECASE)
_ACT_MORE_RE = re.compile(rf"\s*(?:,|\be\b)\s*{_ACT_NO}", re.IGNORECASE)
_SINGULAR = (("declaracoes", "declaracao"), ("decretos", "decreto"), ("regulamentares",
             "regulamentar"), ("despachos", "despacho"), ("normativos", "normativo"),
             ("portarias", "portaria"), ("avisos", "aviso"), ("leis", "lei"))
_LEGAL_REF_RE = re.compile(r"Refer[êe]ncia\s+jur[íi]dica\s*:", re.IGNORECASE)
# the next lettered heading of 9.8 ("c) Outros documentos:", "d) Mapas …") —
# a capital after the letter, so a wrapped "alínea\nc) do artigo" is no end
_LEGAL_REF_END_RE = re.compile(r"\n\s*[c-z]\)\s+[A-ZÀ-Ú]|Outros\s+documentos|Mapas\s+da\s+área")


def load_table(path: Path = TABLE_PATH) -> dict:
    """{parent slug: entry}, without the `_doc` key."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def entry_for(table: dict, slug: str) -> tuple[dict, dict] | None:
    """(parent entry, sub-região entry) for a sub-região slug."""
    for entry in table.values():
        sub = (entry.get("subregioes") or {}).get(slug)
        if sub is not None:
            return entry, sub
    return None


def pieces_for(sub: dict) -> list[Piece]:
    """The resolver's pieces for one sub-região: a whole município, or the
    freguesias the act lists in it."""
    out: list[Piece] = []
    for row in sub.get("rows") or []:
        fregs = row.get("freguesias") or []
        if fregs:
            out.append(Piece(kind="freguesias", name=row["concelho"],
                             items=[Item(n) for n in fregs], subregion=sub.get("name", "")))
        else:
            out.append(Piece(kind="concelho", name=row["concelho"],
                             subregion=sub.get("name", "")))
    return out


def area_km2(geom: BaseGeometry) -> float:
    """Equal-area (EPSG:3035) area of a WGS84 geometry, in km²."""
    return shp_transform(_TO_3035, geom).area / 1e6


def outside_km2(geom: BaseGeometry, parent: BaseGeometry) -> float:
    """km² of `geom` outside `parent`: the act's sub-região should lie inside
    the appellation the caderno delimits."""
    return area_km2(geom.difference(parent))


def act_key(kind: str, number: str, year: str) -> str:
    """'Declaração de Retificação n.º 27/2015' → 'declaracao de retificacao 27/2015';
    a plural type, a "Decreto Lei" without its hyphen and a two-digit year
    ("n.os 263/99") read as the one act."""
    k = unicodedata.normalize("NFKD", kind).encode("ascii", "ignore").decode().lower()
    k = re.sub(r"\s*-\s*", "-", re.sub(r"\s+", " ", k)).strip()
    for plural, singular in _SINGULAR:
        k = re.sub(rf"\b{plural}\b", singular, k)
    k = re.sub(r"^decreto[- ]lei$", "decreto-lei", k)
    if len(year) == 2:
        year = ("19" if int(year) >= 50 else "20") + year
    return f"{k} {number.upper()}/{year}"


def cited_acts(text: str) -> list[str]:
    """Every national act a text cites, as `act_key`s, in order."""
    # a word hyphenated over a line break ("Retifica-\nção") read whole
    text = re.sub(r"(?<=[a-zà-ÿ])-\s*\n\s*(?=[a-zà-ÿ])", "", text or "")
    out: list[str] = []
    for m in _ACT_RE.finditer(text):
        kind = m.group(1)
        found = [act_key(kind, m.group(2), m.group(3))]
        end = m.end()
        while more := _ACT_MORE_RE.match(text, end):
            found.append(act_key(kind, more.group(1), more.group(2)))
            end = more.end()
        for k in found:
            if k not in out:
                out.append(k)
    return out


def legal_reference(record: dict) -> str | None:
    """The caderno's "Referência jurídica" (section 9.8 b): the national acts
    that approved the specification."""
    text = "\n".join(v for v in (record.get("sections") or {}).values() if isinstance(v, str))
    m = _LEGAL_REF_RE.search(text)
    if not m:
        return None
    rest = text[m.end():m.end() + 2000]
    end = _LEGAL_REF_END_RE.search(rest)
    return rest[:end.start()] if end else rest


def unreviewed_acts(record: dict, entry: dict) -> list[str] | None:
    """Acts the parent caderno's legal reference cites that the entry has not
    reviewed — or None when the caderno carries no legal reference."""
    ref = legal_reference(record)
    if ref is None:
        return None
    reviewed = {k for a in entry.get("reviewed_acts") or [] for k in cited_acts(a.get("act", ""))}
    return [k for k in cited_acts(ref) if k not in reviewed]
