"""Two naming axes for an appellation: the legal scheme and the traditional term.

`eu_scheme` is derived from fields already on the record — the SIQO `signe_ue`
for France, the eAmbrosia kind elsewhere, the GOV.UK register for the UK; Swiss
records sit outside the EU scheme. `national_term` is the EU-registered
traditional term (Reg. (EU) 1308/2013 Art. 112(a); Reg. (EC) 607/2009 Annex
XII) a member state attaches to the GI as a whole — DOCG / DOC / IGT,
DOCa / DOQ / DO / Vino de Pago, AOC, DAC, Landwein … — read from a public
roster (MASAF elenco, MAPA listado, SIQO `signe_fr`) or from the checked-in
ruling table `traditional_terms.json`. Lot-level quality grades
(Qualitätswein, Prädikatswein, kakovostno …) and mere translations of
PDO / PGI (OEM, ZOP, ΠΟΠ, BOB …) are never terms. The stored `kind` token is
untouched: it stays the map's paint / filter key.

Rendering is `TERM (SCHEME)` with the scheme word in the UI locale — "DOQ
(PDO)", "DOCG (AOP)" — term-only when there is no scheme (Swiss AOC) and
scheme-only when the country has no term. `classification_label` is the
single composer; stage 04 runs it once per locale so the JS app and the SSR
card read the same precomputed string.
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Callable

from _lib.grape_lexicon import slugify

TERMS_PATH = Path(__file__).with_name("traditional_terms.json")

SCHEMES: tuple[str, ...] = ("pdo", "pgi", "spirit-gi", "uk-pdo", "uk-pgi", "none")

_SCHEME_LABEL_KEY = {
    "pdo": "scheme_pdo",
    "uk-pdo": "scheme_pdo",
    "pgi": "scheme_pgi",
    "uk-pgi": "scheme_pgi",
    "spirit-gi": "scheme_spirit_gi",
    "none": "",
}

_KIND_SCHEME = {"AOC": "pdo", "AOP": "pdo", "DOP": "pdo", "IGP": "pgi", "EDV": "spirit-gi"}

TermResolver = Callable[[dict, str], str]


@lru_cache(maxsize=1)
def load_terms_table() -> dict:
    return load_terms_table_from(TERMS_PATH)


def load_terms_table_from(path: Path) -> dict:
    if not path.exists():
        print(f"[gi_terms] {path.name} missing — no traditional terms", file=sys.stderr)
        return {}
    with path.open(encoding="utf-8") as fh:
        table = json.load(fh)
    for key, entry in (table.get("terms") or {}).items():
        scheme = entry.get("scheme")
        if scheme not in SCHEMES:
            raise ValueError(f"traditional_terms.json: term {key!r} has unknown scheme {scheme!r}")
    _reject_scheme_abbreviations(table)
    return table


# Local abbreviations of PDO / PGI are the scheme, not a traditional term; one
# landing in a term slot would render "OEM (PDO)" — the very conflation this
# layer exists to end — so the table refuses to load.
_SCHEME_ABBREVIATIONS = frozenset({
    "pdo", "pgi", "aop", "igp", "dop", "bob", "bga", "g.u.", "g.g.a.", "gu", "gga",
    "oem", "ofj", "zop", "zgo", "zoi", "zozp", "chop", "chzo", "znp", "zgu", "pop", "pge",
    "ποπ", "πγε", "знп", "згу",
})


def _reject_scheme_abbreviations(table: dict) -> None:
    def _check(term: str, where: str) -> None:
        if term and term.casefold().replace(" ", "") in _SCHEME_ABBREVIATIONS:
            raise ValueError(f"traditional_terms.json: {where} uses the scheme abbreviation {term!r}")
    for cc, by_kind in (table.get("constants") or {}).items():
        for kind, term in by_kind.items():
            _check(term, f"constants[{cc}][{kind}]")
    for cc, pins in (table.get("pins") or {}).items():
        for key, pin in pins.items():
            _check(pin.get("term") or "", f"pins[{cc}][{key}]")
    for key in (table.get("terms") or {}):
        _check(key.partition(":")[2], f"terms[{key}]")


def _pin_for(record: dict, table: dict) -> dict | None:
    pins = (table.get("pins") or {}).get(record.get("country") or "", {})
    if not pins:
        return None
    for key in (record.get("slug") or "", record.get("file_number") or ""):
        if key and key in pins:
            return pins[key]
    return None


def derive_eu_scheme(record: dict, mvt_kind: str) -> str:
    country = record.get("country") or "fr"
    pin = _pin_for(record, load_terms_table())
    if pin and pin.get("scheme"):
        return pin["scheme"]
    if country == "ch":
        return "none"
    if country == "fr":
        sue = (record.get("signe_ue") or "").strip().upper()
        if sue == "AOP":
            return "pdo"
        if sue == "IGP":
            return "pgi"
        if sue == "IG":
            return "spirit-gi"
        return _KIND_SCHEME.get(mvt_kind, "pdo")
    base = _KIND_SCHEME.get(mvt_kind, "pdo")
    if country == "gb":
        return "uk-" + base
    return base


def resolve_national_term(
    record: dict,
    mvt_kind: str,
    *,
    it_term_for: TermResolver | None = None,
    es_term_for: TermResolver | None = None,
) -> str:
    table = load_terms_table()
    pin = _pin_for(record, table)
    if pin is not None and "term" in pin:
        return pin["term"] or ""
    country = record.get("country") or "fr"
    if country == "it" and it_term_for is not None:
        return it_term_for(record, mvt_kind) or ""
    if country == "es" and es_term_for is not None:
        return es_term_for(record, mvt_kind) or ""
    return (table.get("constants") or {}).get(country, {}).get(mvt_kind, "") or ""


def term_key(country: str, term: str) -> str:
    return f"{country}:{slugify(term)}" if term else ""


def class_key(eu_scheme: str, country: str, term: str) -> str:
    parts = [eu_scheme]
    tk = term_key(country, term)
    if tk:
        parts.append(tk)
    return ";" + ";".join(parts) + ";"


def scheme_label(eu_scheme: str, labels: dict) -> str:
    key = _SCHEME_LABEL_KEY.get(eu_scheme, "")
    return labels.get(key, "") if key else ""


def classification_label(term: str, eu_scheme: str, labels: dict) -> str:
    scheme = scheme_label(eu_scheme, labels)
    if term and scheme and term.casefold() != scheme.casefold():
        return f"{term} ({scheme})"
    return term or scheme


def _localised(block: dict | None, locale: str) -> str:
    if not block:
        return ""
    return block.get(locale) or block.get("en") or ""


def build_terms_info(locale: str) -> dict[str, dict]:
    """Tooltip payload keyed exactly like the tokens in `class_key`: scheme ids
    and `<cc>:<term-slug>`. Each entry: label, full, note, sources[, castilian_form]."""
    table = load_terms_table()
    out: dict[str, dict] = {}
    for scheme, entry in (table.get("schemes") or {}).items():
        out[scheme] = {
            "full": _localised(entry.get("full"), locale),
            "note": _localised(entry.get("note"), locale),
            "sources": entry.get("sources") or [],
        }
    for key, entry in (table.get("terms") or {}).items():
        country, _, term = key.partition(":")
        info = {
            "term": term,
            "full": entry.get("full") or "",
            "scheme": entry.get("scheme") or "",
            "note": _localised(entry.get("note"), locale),
            "sources": entry.get("sources") or [],
        }
        if entry.get("castilian_form"):
            info["castilian_form"] = entry["castilian_form"]
        out[term_key(country, term)] = info
    return out


SCHEME_ORDER: tuple[str, ...] = ("pdo", "pgi", "spirit-gi", "uk-pdo", "uk-pgi", "none")


def build_term_tree(counts: dict[str, int]) -> tuple[list[dict], dict[str, list[str]]]:
    """Two-level facet tree from `class_key` → count: scheme rows (depth 0), then
    their term rows (depth 1) by count. Same row shape as the classification
    tree (`{slug, parent, depth, count}`); `descendants` includes self, which is
    what `expandTree` in app.js relies on to widen a scheme pick to its terms."""
    scheme_totals: dict[str, int] = {}
    by_scheme: dict[str, dict[str, int]] = {}
    for ck, n in counts.items():
        toks = [t for t in ck.strip(";").split(";") if t]
        if not toks:
            continue
        scheme = toks[0]
        scheme_totals[scheme] = scheme_totals.get(scheme, 0) + n
        if len(toks) > 1:
            terms = by_scheme.setdefault(scheme, {})
            terms[toks[1]] = terms.get(toks[1], 0) + n
    tree: list[dict] = []
    descendants: dict[str, list[str]] = {}
    ordered = sorted(
        scheme_totals,
        key=lambda s: (SCHEME_ORDER.index(s) if s in SCHEME_ORDER else len(SCHEME_ORDER), s),
    )
    for scheme in ordered:
        tree.append({"slug": scheme, "parent": None, "depth": 0, "count": scheme_totals[scheme]})
        kids = sorted((by_scheme.get(scheme) or {}).items(), key=lambda kv: (-kv[1], kv[0]))
        descendants[scheme] = [scheme] + [k for k, _ in kids]
        for k, n in kids:
            tree.append({"slug": k, "parent": scheme, "depth": 1, "count": n})
            descendants[k] = [k]
    return tree, descendants
