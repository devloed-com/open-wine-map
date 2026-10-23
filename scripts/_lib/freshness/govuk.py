"""National tier, United Kingdom — the GOV.UK protected food and drink
names register (content API per GI) against raw/gb/gov-uk/index.json."""
from __future__ import annotations

import json

from . import CURRENT, GONE, NEWER, ROOT, UNREACHABLE, Http, Probe

CONTENT_API = "https://www.gov.uk/api/content/protected-food-drink-names/{slug}"
SEARCH_API = ("https://www.gov.uk/api/search.json?filter_format=protected_food_drink_name"
              "&filter_register=wines&filter_country_of_origin=united-kingdom&count=100")


def probe(http: Http) -> list[Probe]:
    p = ROOT / "raw" / "gb" / "gov-uk" / "index.json"
    if not p.exists():
        return []
    idx = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(idx, list):
        rows = idx
    else:
        rows = []
        for v in idx.values():
            if isinstance(v, list):
                rows += [r for r in v if isinstance(r, dict) and r.get("slug")]
            elif isinstance(v, dict) and v.get("slug"):
                rows.append(v)
    out: list[Probe] = []
    def gov_slug(r: dict) -> str:
        return (r.get("register_url") or "").rstrip("/").rsplit("/", 1)[-1] or (r.get("slug") or "")
    held_slugs = {gov_slug(r) for r in rows}
    for r in rows:
        slug = gov_slug(r)
        url = CONTENT_API.format(slug=slug)
        data = http.get_json(url)
        if isinstance(data, str):
            out.append(Probe(tier="national", source_key="gov_uk_register_url", url=r.get("register_url") or url,
                             verdict=UNREACHABLE if "HTTP 404" not in data else GONE, method="api", reason=data))
            continue
        updated = (data.get("public_updated_at") or "")[:10]
        atts = []
        for a in (data.get("details") or {}).get("attachments") or []:
            if isinstance(a, dict) and a.get("url"):
                atts.append(a["url"])
        held_spec = r.get("spec_url") or ""
        if held_spec and atts and held_spec not in atts:
            out.append(Probe(tier="national", source_key="gov_uk_spec_url", url=r.get("register_url") or url, verdict=NEWER,
                             held=held_spec.rsplit("/", 1)[-1][:60], upstream=f"{atts[0].rsplit('/', 1)[-1][:60]} ({updated})",
                             upstream_url=atts[0], method="api", reason="the register links a different specification attachment",
                             recipe="scripts/gb/00_fetch_data.py → 01_fetch_specs.py → 02_extract_specs.py → 04"))
        else:
            out.append(Probe(tier="national", source_key="gov_uk_register_url", url=r.get("register_url") or url, verdict=CURRENT,
                             held=(r.get("date_registration") or ""), upstream=updated, method="api"))
    data = http.get_json(SEARCH_API)
    if isinstance(data, dict):
        live = {(h.get("link") or "").rstrip("/").rsplit("/", 1)[-1]: h for h in data.get("results") or []}
        for s, h in live.items():
            if s in held_slugs:
                continue
            page = http.get_json(CONTENT_API.format(slug=s))
            meta = ((page.get("details") or {}).get("metadata") or {}) if isinstance(page, dict) else {}
            status = str(meta.get("status") or meta.get("protection_status") or "").lower()
            under_consideration = isinstance(page, dict) and any(
                "under-consideration" in str(hd.get("id") or "") for hd in (page.get("details") or {}).get("headers") or [])
            url = "https://www.gov.uk" + (h.get("link") or "")
            if under_consideration or (status and "registered" not in status):
                out.append(Probe(tier="national", source_key="gov_uk_register", url=url, verdict=CURRENT,
                                 upstream=h.get("title") or s, method="api",
                                 reason=f"application pending ({status or 'under consideration'}) — not registered, nothing to add yet"))
            else:
                out.append(Probe(tier="national", source_key="gov_uk_register", url=url, verdict=NEWER,
                                 upstream=h.get("title") or s, method="api",
                                 reason="a registered UK wine GI the index lacks",
                                 recipe="scripts/gb/00_fetch_data.py (add its file number to _FILE_NUMBER_BY_SLUG) → 01 → 02 → 04"))
    return out
