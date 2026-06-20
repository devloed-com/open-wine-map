"""Wikidata QID resolution helpers (used by stage 02i).

Two resolution paths for mapping an EU wine geographical indication to a
Wikidata QID — the highest-value `sameAs` / entity-reconciliation target for
the per-appellation JSON-LD:

1. **P9854 "eAmbrosia ID"** — Wikidata stores the `EUGI…` identifier on the
   item, so a single SPARQL query yields the whole `{EUGI… → QID}` table; we
   join locally on each record's `id_eambrosia`. Authoritative.
2. **Wikipedia sitelink** — for records with a validated Wikipedia article but
   no `id_eambrosia` (notably FR, which is INAO-sourced), resolve the article
   title → QID via the MediaWiki `pageprops.wikibase_item` API. Every language
   Wikipedia links to one Wikidata item, so any one locale's title resolves it.

The module splits PURE parsing/normalisation (unit-tested offline) from the
thin `requests`-backed fetchers, so a network outage degrades to "no Wikidata
QID" rather than a crash.
"""

from __future__ import annotations

import re

SPARQL_URL = "https://query.wikidata.org/sparql"
# Wikidata property P9854 = "eAmbrosia ID" (stores the EUGI… identifier).
P9854_SPARQL = "SELECT ?item ?e WHERE { ?item wdt:P9854 ?e }"

UA = (
    "open-wine-map/0.0.1 (+https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)

_QID_RE = re.compile(r"^Q[1-9][0-9]*$")


def normalize_qid(value: str | None) -> str:
    """Coerce `Q123`, `q123`, or a full entity URL/URI to a canonical `Q123`;
    return "" for anything that isn't a well-formed item id."""
    if not value:
        return ""
    v = value.strip()
    if "/" in v:  # http://www.wikidata.org/entity/Q123
        v = v.rstrip("/").rsplit("/", 1)[-1]
    v = v.upper()
    return v if _QID_RE.match(v) else ""


def wikidata_url(qid: str) -> str:
    """Public Wikidata item URL for a (already-validated) QID, else ""."""
    q = normalize_qid(qid)
    return f"https://www.wikidata.org/wiki/{q}" if q else ""


def parse_sparql_p9854(payload: dict) -> dict[str, str]:
    """`{EUGI… : QID}` from a SPARQL-JSON result of `P9854_SPARQL`.

    A handful of items may carry the same eAmbrosia id (re-registrations); the
    first binding wins and the rest are ignored — the join is best-effort."""
    out: dict[str, str] = {}
    for b in (((payload or {}).get("results") or {}).get("bindings")) or []:
        eid = ((b.get("e") or {}).get("value") or "").strip()
        qid = normalize_qid((b.get("item") or {}).get("value"))
        if eid and qid and eid not in out:
            out[eid] = qid
    return out


def parse_pageprops(payload: dict) -> dict[str, str]:
    """`{final_article_title : QID}` from a MediaWiki `prop=pageprops`
    response (formatversion=2). Titles here are the API's *resolved* titles
    (post normalisation/redirect); pair with `title_resolution_map` to look up
    by the title that was requested."""
    out: dict[str, str] = {}
    for pg in (((payload or {}).get("query") or {}).get("pages")) or []:
        title = pg.get("title")
        qid = normalize_qid((pg.get("pageprops") or {}).get("wikibase_item"))
        if title and qid:
            out[title] = qid
    return out


def title_resolution_map(payload: dict) -> dict[str, str]:
    """`{requested_or_intermediate_title : next_title}` merging the response's
    `normalized` and `redirects` hops, so a requested title can be chased to
    the title key used in `parse_pageprops`."""
    q = (payload or {}).get("query") or {}
    out: dict[str, str] = {}
    for hop in (q.get("normalized") or []) + (q.get("redirects") or []):
        frm, to = hop.get("from"), hop.get("to")
        if frm and to:
            out[frm] = to
    return out


def resolve_title_qid(
    requested_title: str, pageprops: dict[str, str], resolution: dict[str, str]
) -> str:
    """QID for a requested title, following up to two normalise/redirect hops."""
    t = requested_title
    seen = {t}
    for _ in range(3):
        if t in pageprops:
            return pageprops[t]
        nxt = resolution.get(t)
        if not nxt or nxt in seen:
            break
        seen.add(nxt)
        t = nxt
    return pageprops.get(t, "")


def title_from_page(page_title: str | None, page_url: str | None) -> str:
    """The article title to query the MediaWiki API with: prefer the cached
    `page_title`, else derive it from the `page_url`'s last path segment
    (underscores → spaces, percent-decoded)."""
    if page_title and page_title.strip():
        return page_title.strip()
    if not page_url:
        return ""
    from urllib.parse import unquote

    seg = page_url.rstrip("/").rsplit("/", 1)[-1]
    return unquote(seg).replace("_", " ").strip()


# ---- thin network layer (delegates parsing to the pure functions above) ----


def fetch_p9854_table(session) -> dict[str, str]:
    """Run the P9854 SPARQL query; return `{EUGI… : QID}`. Raises on transport
    errors so the caller can decide whether a cached table is usable."""
    r = session.get(
        SPARQL_URL,
        params={"query": P9854_SPARQL, "format": "json"},
        headers={"User-Agent": UA, "Accept": "application/sparql-results+json"},
        timeout=120,
    )
    r.raise_for_status()
    return parse_sparql_p9854(r.json())


def fetch_titles_qids(session, lang: str, titles: list[str]) -> dict[str, str]:
    """Resolve a batch of ≤50 article titles on `<lang>.wikipedia.org` to
    `{requested_title : QID}` (only titles that resolved are present)."""
    if not titles:
        return {}
    r = session.get(
        f"https://{lang}.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "prop": "pageprops",
            "ppprop": "wikibase_item",
            "redirects": 1,
            "titles": "|".join(titles[:50]),
            "format": "json",
            "formatversion": 2,
        },
        headers={"User-Agent": UA},
        timeout=60,
    )
    r.raise_for_status()
    payload = r.json()
    pageprops = parse_pageprops(payload)
    resolution = title_resolution_map(payload)
    out: dict[str, str] = {}
    for t in titles:
        qid = resolve_title_qid(t, pageprops, resolution)
        if qid:
            out[t] = qid
    return out
