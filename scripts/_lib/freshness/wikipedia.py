"""Reference tier — the Wikipedia pages stage 02b cached (per-appellation
pages and the grape / style extracts), against the live revision id
(MediaWiki API, 50 titles per request per language). Informational: a
newer revision changes a tooltip or a salience hint, never a regulator
fact; the recipe is the 02b refresh of that slug."""
from __future__ import annotations

import json
from urllib.parse import quote

from . import CURRENT, GONE, NEWER, ROOT, UNREACHABLE, Http, Probe

API = "https://{lang}.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=ids&format=json&formatversion=2&titles={titles}"


def cached_pages(kind: str, lang: str, slugs: set[str] | None) -> list[tuple[str, str, str, str]]:
    """(slug, title, revision, page_url) of the cached entries of one kind."""
    out = []
    d = ROOT / "raw" / "wikipedia" / kind / lang
    if not d.exists():
        return out
    for p in sorted(d.glob("*.json")):
        if p.name.startswith("manifest") or (slugs is not None and p.stem not in slugs):
            continue
        try:
            e = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        title = e.get("page_title") or e.get("wikipedia_title") or e.get("title")
        rev = str(e.get("revision") or e.get("revision_id") or "")
        if title and rev and e.get("status", "ok") != "missing":
            out.append((p.stem, title, rev, e.get("page_url") or ""))
    return out


def probe(http: Http, *, kind: str, lang: str, slugs: set[str] | None = None) -> list[Probe]:
    pages = cached_pages(kind, lang, slugs)
    out: list[Probe] = []
    for i in range(0, len(pages), 50):
        chunk = pages[i:i + 50]
        url = API.format(lang=lang, titles=quote("|".join(t for _, t, _, _ in chunk), safe=""))
        data = http.get_json(url)
        if isinstance(data, str):
            out += [Probe(tier="reference", source_key=f"wikipedia/{kind}", url=pu or url, verdict=UNREACHABLE, held=rev, method="api", reason=data)
                    for _, _, rev, pu in chunk]
            continue
        live: dict[str, str] = {}
        missing: set[str] = set()
        for pg in (data.get("query") or {}).get("pages") or []:
            t = pg.get("title")
            if pg.get("missing"):
                missing.add(t)
                continue
            revs = pg.get("revisions") or []
            if revs:
                live[t] = str(revs[0].get("revid"))
        norm = {n.get("from"): n.get("to") for n in (data.get("query") or {}).get("normalized") or []}
        for slug, title, rev, pu in chunk:
            t = norm.get(title, title)
            lr = live.get(t)
            base = dict(tier="reference", source_key=f"wikipedia/{kind}", url=pu or f"https://{lang}.wikipedia.org/wiki/{quote(title)}",
                        held=rev, method="api", recipe=f"scripts/02b_fetch_{'aoc' if kind == 'aocs' else kind.rstrip('s')}_lexicon.py --lang {lang} --only {slug}")
            if t in missing:
                out.append(Probe(**base, verdict=GONE, reason="the article no longer exists under this title"))
            elif lr is None:
                out.append(Probe(**base, verdict=UNREACHABLE, reason="not in the API answer"))
            elif lr != rev:
                out.append(Probe(**base, verdict=NEWER, upstream=lr, reason="a newer revision of the article"))
            else:
                out.append(Probe(**base, verdict=CURRENT, upstream=lr))
    return out
