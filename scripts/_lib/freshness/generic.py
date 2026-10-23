"""Any document URL a card cites — national specs, register attachments,
national pliegos, BLE / MASAF / IVV / ONVPV / ÚPV / SZPI / MKGP / MPS PDFs,
regional registers, Galician parish layers, cantonal règlements, and the
trade bodies' sites.

HEAD first (a ranged GET where HEAD is refused): a 404 / 410 is GONE; a
`Last-Modified` after the fetch date, or a content length the held byte
count does not match, is a candidate for NEWER-UPSTREAM; with `deep` the
body is re-fetched and its sha256 compared with the held one — exact,
content-addressed, the only test that settles a PDF whose headers say
nothing. Trade bodies are liveness only: nothing is ever read from them.
"""
from __future__ import annotations

from . import (
    CURRENT,
    GONE,
    NEWER,
    RELINKED,
    UNREACHABLE,
    UNVERIFIABLE,
    WAF_HOSTS,
    Http,
    Probe,
    host_of,
    parse_http_date,
    parse_iso,
)

# per-country re-fetch recipes for a national-spec / sidecar document
RECIPES = {
    "es": "scripts/es/02f_extract_national_pliegos.py --slug {slug} --refresh → 04",
    "it": "scripts/it/02f_extract_masaf.py --slug {slug} (or refresh the bundle: scripts/it/00_fetch_data.py) → 04",
    "de": "scripts/de/00_fetch_data.py → scripts/de/02f_extract_produktspezifikation.py --slug {slug} → 04",
    "si": "scripts/si/01c_fetch_specifikacije.py --refresh → 02f_extract_specifikacije.py --slug {slug} → 04",
    "hr": "scripts/hr/01c_fetch_specifikacije.py --refresh → 02f_extract_specifikacije.py --slug {slug} → 04",
    "bg": "scripts/bg/01c_fetch_specifikacije.py → 02f_extract_national_specs.py --slug {slug} --refresh → 04",
    "gr": "scripts/gr/01c_fetch_specifikacije.py → 02f_extract_national_specs.py --refresh → 04",
    "cy": "scripts/cy/01c_fetch_specifikacije.py → 02f_extract_national_specs.py → 04",
    "ro": "scripts/ro/01c_fetch_specifikacije.py → 02f_extract_national_specs.py --all → 04",
    "hu": "scripts/hu/01c_fetch_specifikacije.py → 02f → 04",
    "sk": "scripts/sk/01c_fetch_specifikacije.py → 02f_extract_national_specs.py --slug {slug} → 04",
    "cz": "scripts/cz/02f_extract_national_specs.py --refresh → 04",
    "pt": "scripts/pt/01_fetch_cadernos.py → 02_extract_cadernos.py → 04",
    "ch": "scripts/ch/01_fetch_reglements.py → 02_extract_reglements.py → 04",
    "lu": "re-download the cahier by hand into raw/lu/ivv/cahiers/ (WAF) → scripts/lu/01 → 02 → 04",
    "gb": "scripts/gb/00_fetch_data.py → 01_fetch_specs.py → 02_extract_specs.py → 04",
    "fr": "scripts/01_scrape_cahiers.py (French exit node) → 02 → 04",
}


def probe_url(http: Http, *, tier: str, source_key: str, url: str, country: str, slug: str,
              fetched_at: str = "", held_sha256: str = "", held_bytes: str = "", deep: bool = False) -> Probe:
    base = dict(tier=tier, source_key=source_key, url=url, held=(held_sha256[:12] if held_sha256 else fetched_at[:10]),
                recipe=RECIPES.get(country, "re-run the country's fetch stage → 02 → 04").format(slug=slug))
    host = host_of(url)
    if any(host == w or host.endswith("." + w) for w in WAF_HOSTS):
        return Probe(**base, verdict="COVERED", method="-",
                     reason="EUR-Lex / data.europa.eu answer non-browser clients with a WAF challenge; the EU tier is checked through eAmbrosia")
    if tier == "trade":
        h = http.head(url)
        if isinstance(h, str):
            return Probe(**base, verdict=UNREACHABLE, method="head", reason=h)
        if h["status"] in (404, 410):
            return Probe(**base, verdict=GONE, method="head", reason=f"HTTP {h['status']} — the trade body's site moved or closed; fix the entry in scripts/_lib/appellation_urls.py")
        return Probe(**base, verdict=CURRENT, method="head", upstream=f"HTTP {h['status']}", reason="liveness only — a trade body is a signal, never a source")
    if deep and held_sha256:
        s = http.sha256(url)
        if isinstance(s, str):
            return Probe(**base, verdict=UNREACHABLE, method="sha", reason=s)
        if s.get("status", 200) in (404, 410):
            return Probe(**base, verdict=GONE, method="sha", reason=f"HTTP {s['status']}")
        if s.get("too_large"):
            return Probe(**base, verdict=UNVERIFIABLE, method="sha", reason=f"body over the size cap ({s.get('bytes')} bytes)")
        if s.get("sha256") == held_sha256:
            v = RELINKED if s.get("final_url") and s["final_url"] != url and host_of(s["final_url"]) != host else CURRENT
            return Probe(**base, verdict=v, method="sha", upstream=s["sha256"][:12], upstream_url=s.get("final_url") or "")
        ct = (s.get("content_type") or "").lower()
        if "html" in ct and held_sha256:
            return Probe(**base, verdict=UNVERIFIABLE, method="sha", upstream=f"text/html {s.get('bytes')} bytes",
                         reason="the URL now serves an HTML page where a document was held (a landing page, a WAF challenge or a moved file)")
        return Probe(**base, verdict=NEWER, method="sha", upstream=(s.get("sha256") or "")[:12], upstream_url=s.get("final_url") or "",
                     reason="the document at this URL differs byte for byte from the one the build holds")
    h = http.head(url)
    if isinstance(h, str):
        return Probe(**base, verdict=UNREACHABLE, method="head", reason=h)
    if h["status"] in (404, 410):
        return Probe(**base, verdict=GONE, method="head", reason=f"HTTP {h['status']}")
    if h["status"] >= 400:
        return Probe(**base, verdict=UNREACHABLE, method="head", reason=f"HTTP {h['status']}")
    lm = parse_http_date(h.get("last_modified") or "")
    fa = parse_iso(fetched_at)
    if lm and fa and lm > fa:
        return Probe(**base, verdict=NEWER, method="head", upstream=lm.date().isoformat(), upstream_url=h.get("final_url") or "",
                     reason=f"Last-Modified {lm.date().isoformat()} is after our fetch {fa.date().isoformat()} (confirm with --deep: a server re-stamp is not a new document)")
    if held_bytes and h.get("content_length") and str(h["content_length"]) != str(held_bytes):
        return Probe(**base, verdict=NEWER, method="head", upstream=f"{h['content_length']} bytes", upstream_url=h.get("final_url") or "",
                     reason=f"Content-Length {h['content_length']} differs from the {held_bytes} bytes held (confirm with --deep)")
    if h.get("final_url") and host_of(h["final_url"]) != host:
        return Probe(**base, verdict=RELINKED, method="head", upstream_url=h["final_url"], reason="the URL redirects to another host")
    return Probe(**base, verdict=CURRENT, method="head", upstream=(lm.date().isoformat() if lm else f"HTTP {h['status']}"))
