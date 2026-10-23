"""EU tier — the eAmbrosia register, diffed against every country's cached
index (the register-drift method of docs/register-drift-2026-09-20.md,
step 1, as a probe).

One GET of the public list (~4,000 GIs, 6.6 MB, cached for the day) gives
per GI: `modificationDate`, `publications`, `removedFlag`, `status`,
`amendmentsInProgressFlag`. Per country the probe reports:

  NEW            a registered wine GI of the country the index lacks
  GONE           an indexed GI the live register no longer lists, or lists
                 `removedFlag` — a cancellation to confirm on EUR-Lex
  NEWER-UPSTREAM the GI was modified after we fetched its document, or
                 carries a publication the cached entry does not
  IN-OPPOSITION  `amendmentsInProgressFlag`
  CURRENT        otherwise

The register is the EU's own record of the member state's act and lags the
national arrêté (3 of 22 newer FR arrêtés showed on 2026-09-20): a CURRENT
here is necessary, not sufficient, for France — the INAO probe decides.
"""
from __future__ import annotations

import json

from . import (
    COVERED,
    CURRENT,
    GONE,
    IN_OPPOSITION,
    NEWER,
    ROOT,
    UNREACHABLE,
    Http,
    Probe,
    parse_iso,
)

LIST_URL = "https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications"
# Countries whose spine is not eAmbrosia (FR: INAO; CH: OFAG; GB: GOV.UK) — their
# EU-register rows are a secondary signal, matched by file number where known.
NON_EAMBROSIA_SPINES = {"fr", "ch", "gb"}
CC_TO_LIVE = {"gr": "GR", "gb": "GB"}
# a cross-border GI is one record, on one side (CLAUDE.md: Maasvallei Limburg ships on BE)
CROSS_BORDER_OWNER = {"PDO-BE+NL-02172": "be"}

RECIPE = ("scripts/{cc}/01_fetch_pliegos.py --only {slug} --refresh (01b_solve_waf.py if the page is "
          "WAF-blocked) → 02_extract_pliegos.py --only {slug} → 04_build_maps.py")


def live_rows(http: Http) -> list[dict] | str:
    data = http.get_json(LIST_URL)
    if isinstance(data, str):
        return data
    rows = data if isinstance(data, list) else (data.get("content") or [])
    return [r for r in rows if isinstance(r, dict)]


def wine_rows_by_country(rows: list[dict]) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for r in rows:
        if (r.get("productType") or "") != "WINE":
            continue
        fn = r.get("fileNumber") or ""
        for c in r.get("countries") or []:
            out.setdefault(c.upper(), {})[fn] = r
    return out


def country_index(cc: str) -> tuple[list[dict], str]:
    """(rows, fetched_at of the index file) from raw/<cc>/eambrosia/index.json."""
    p = ROOT / "raw" / cc / "eambrosia" / "index.json"
    if not p.exists():
        return [], ""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return [], ""
    rows = d if isinstance(d, list) else (d.get("wines") or d.get("rows") or list(d.values()))
    rows = [r for r in rows if isinstance(r, dict) and r.get("fileNumber")]
    gen = ""
    mp = p.with_name("manifest.json")
    if mp.exists():
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
            gen = m.get("generated_at") or m.get("fetched_at") or ""
        except ValueError:
            gen = ""
    return rows, gen


def document_fetched_at(cc: str) -> dict[str, str]:
    """slug → fetched_at of the single document we hold (oj-pages manifest)."""
    out: dict[str, str] = {}
    mp = ROOT / "raw" / cc / "oj-pages" / "manifest.json"
    if not mp.exists():
        return out
    try:
        m = json.loads(mp.read_text(encoding="utf-8"))
    except ValueError:
        return out
    for slug, e in (m.get("by_slug") or {}).items():
        if isinstance(e, dict) and e.get("fetched_at"):
            out[slug] = e["fetched_at"]
    return out


def probe_country(cc: str, live_by_cc: dict[str, dict[str, dict]], *, index_fetched_at: str = "") -> list[Probe]:
    """Per-GI probes for one country from the cached live listing."""
    live = live_by_cc.get(CC_TO_LIVE.get(cc, cc.upper()), {})
    rows, gen = country_index(cc)
    fetched = document_fetched_at(cc)
    out: list[Probe] = []
    seen: set[str] = set()
    for r in rows:
        fn = r["fileNumber"]
        seen.add(fn)
        slug = r.get("slug") or fn
        lrow = live.get(fn)
        held_mod = r.get("modification_date") or r.get("modificationDate") or ""
        held_pubs = {p.get("text") or p.get("uri") for p in (r.get("publications") or []) if isinstance(p, dict)}
        doc_at = fetched.get(slug) or gen or index_fetched_at
        base = dict(tier="eu", source_key=f"eambrosia {fn} {r.get('name') or slug}",
                    url=f"https://ec.europa.eu/geographical-indications-register/#/detail/{r.get('giIdentifier') or ''}",
                    held=held_mod[:10], method="api", recipe=RECIPE.format(cc=cc, slug=slug))
        if lrow is None:
            out.append(Probe(**base, verdict=GONE, reason=f"{fn} is not in the live register any more (a renumbering or a cancellation — check EUR-Lex)"))
            continue
        live_mod = lrow.get("modificationDate") or ""
        live_pubs = {p.get("text") or p.get("uri") for p in (lrow.get("publications") or []) if isinstance(p, dict)}
        new_pubs = sorted(p for p in live_pubs - held_pubs if p)
        if lrow.get("removedFlag") or (lrow.get("status") or "").lower() not in ("registered", ""):
            out.append(Probe(**base, verdict=GONE, upstream=lrow.get("status") or "removed",
                             reason=f"live status {lrow.get('status')!r}, removedFlag={lrow.get('removedFlag')} — confirm the cancellation regulation on EUR-Lex and add the GI to scripts/_lib/cancelled_gis.json"))
            continue
        lm, da = parse_iso(live_mod), parse_iso(doc_at)
        if new_pubs:
            out.append(Probe(**base, verdict=NEWER, upstream=live_mod[:10],
                             upstream_url=next((p.get("uri") for p in lrow.get("publications") or [] if (p.get("text") or p.get("uri")) in new_pubs), ""),
                             reason="new publication(s) in the register: " + "; ".join(new_pubs)[:300]))
        elif lm and da and lm > da:
            out.append(Probe(**base, verdict=NEWER, upstream=live_mod[:10],
                             reason=f"modified {live_mod[:10]} after our document fetch {doc_at[:10]} (no new publication listed — a date-only change, often a register attachment)"))
        elif lrow.get("amendmentsInProgressFlag"):
            out.append(Probe(**base, verdict=IN_OPPOSITION, upstream=live_mod[:10],
                             reason="amendmentsInProgressFlag — an amendment is being examined; a new publication will follow"))
        else:
            out.append(Probe(**base, verdict=CURRENT, upstream=live_mod[:10]))
    if cc not in NON_EAMBROSIA_SPINES:
        indexed_names = {_norm(r.get("name") or "") for r in rows}
        for fn, lrow in live.items():
            if fn in seen or (lrow.get("status") or "").lower() != "registered" or lrow.get("removedFlag"):
                continue
            names = lrow.get("protectedNames") or []
            key = f"eambrosia {fn} {', '.join(names)}"
            url = f"https://ec.europa.eu/geographical-indications-register/#/detail/{lrow.get('giIdentifier') or ''}"
            if fn in CROSS_BORDER_OWNER and CROSS_BORDER_OWNER[fn] != cc:
                out.append(Probe(tier="eu", source_key=key, url=url, verdict=CURRENT, method="api",
                                 reason=f"cross-border GI emitted once, on the {CROSS_BORDER_OWNER[fn].upper()} side"))
                continue
            if any(_norm(n) in indexed_names for n in names):
                out.append(Probe(tier="eu", source_key=key, url=url, verdict=CURRENT, method="api",
                                 upstream=(lrow.get("euProtectionDate") or "")[:10],
                                 reason="a duplicate administrative registration of a name already in the index (stage 00 keeps one row per wine)"))
                continue
            out.append(Probe(tier="eu", source_key=key, url=url, verdict=NEWER, held="",
                             upstream=(lrow.get("euProtectionDate") or "")[:10], method="api",
                             reason=f"NEW registered {lrow.get('giType')} not in raw/{cc}/eambrosia/index.json: {', '.join(names)} ({fn})",
                             recipe=f"scripts/{cc}/00_fetch_data.py → 01 → 02 → region / geometry entries → 04"))
    return out


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().casefold()
    return " ".join(s.replace("-", " ").split())


def eurlex_covered(url: str, cc: str, slug: str) -> Probe:
    return Probe(tier="eu", source_key="eur_lex_url", url=url, verdict=COVERED, method="-",
                 reason="EUR-Lex answers non-browser clients with a WAF challenge; the EU tier is checked through the eAmbrosia register row of this GI")


def unreachable(reason: str) -> Probe:
    return Probe(tier="eu", source_key="eambrosia", url=LIST_URL, verdict=UNREACHABLE, method="api", reason=reason)
