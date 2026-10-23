"""National tier, France — INAO's product page and its dated cahier link,
against the homologation date the record carries (the register-drift
method's step 2: compare the dated title of the current `show_texte`, never
the BO Agri URL alone — INAO relinks the same act, 51 times on 2026-09-20).

For one record: GET the product page (`sources.product`), find the
"accéder au cahier des charges" link, GET that show_texte page and read the
act's dated title ("Arrêté du 2 septembre 2026 homologuant le cahier des
charges …"). A product page with no such link but a PNO notice is a
modification in opposition. www2.inao.gouv.fr resets connections at times;
the host circuit breaker turns the rest of the scope into UNREACHABLE after
three failures. ~1 s per record (two requests) — scope the run.
"""
from __future__ import annotations

import re
from datetime import date

from . import CURRENT, GONE, IN_OPPOSITION, NEWER, UNREACHABLE, UNVERIFIABLE, Http, Probe

# the same link shape stage 01 keys on (scripts/01_scrape_cahiers.py CAHIER_TEXT_LINK_RE)
CAHIER_LINK_RE = re.compile(r'<a\s+href="(/show_texte/\d+)"[^>]*>\s*acc[ée]der au cahier des charges', re.I)
PNO_RE = re.compile(r"proc[ée]dure nationale d.opposition", re.I)
TITLE_RE = re.compile(r"<(?:h1|h2|title)[^>]*>(.*?)</(?:h1|h2|title)>", re.I | re.S)
MONTHS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
          "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}
DATE_RE = re.compile(r"(\d{1,2}|1er)\s+(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)\s+(\d{4})", re.I)
RECIPE = ("pin the new BO Agri URL in raw/inao/cahiers/manual_overrides.json (id {id}) or run "
          "scripts/01_scrape_cahiers.py behind a French exit node → 02_extract_cahiers.py --only «{name}» → 04")


def french_date(text: str) -> date | None:
    m = DATE_RE.search(text or "")
    if not m:
        return None
    d = 1 if m.group(1).lower() == "1er" else int(m.group(1))
    mo = MONTHS.get(m.group(2).lower().replace("é", "é"))
    if mo is None:
        key = m.group(2).lower().replace("û", "u").replace("é", "e").replace("è", "e")
        mo = MONTHS.get(key) or MONTHS.get({"fevrier": "février", "aout": "août", "decembre": "décembre"}.get(key, key))
    if mo is None:
        return None
    try:
        return date(int(m.group(3)), mo, d)
    except ValueError:
        return None


def act_title(html: str) -> str:
    for m in TITLE_RE.finditer(html):
        t = re.sub(r"<[^>]+>", " ", m.group(1))
        t = re.sub(r"\s+", " ", t).strip()
        if re.search(r"(arr[êe]t[ée]|d[ée]cret)\s+(n°|du)", t, re.I):
            return t[:200]
    m = re.search(r"((?:Arr[êe]t[ée]|D[ée]cret)[^<]{10,200}?\d{4})", html, re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:200] if m else ""


def probe_record(http: Http, *, product_url: str, show_texte_url: str, held_date_text: str,
                 id_appellation: str, name: str) -> Probe:
    base = dict(tier="national", source_key="show_texte", url=show_texte_url or product_url, held=held_date_text, method="page",
                recipe=RECIPE.format(id=id_appellation, name=name))
    if not product_url:
        return Probe(**base, verdict=UNVERIFIABLE, reason="the record cites no INAO product page")
    page = http.get_text(product_url)
    if isinstance(page, dict):
        if page.get("status") == 404:
            return Probe(**base, verdict=GONE, reason="INAO product page 404 — the product may have been retired from the catalogue")
        return Probe(**base, verdict=UNREACHABLE, reason=page.get("error") or "no page")
    m = CAHIER_LINK_RE.search(page)
    if not m:
        if PNO_RE.search(page):
            return Probe(**base, verdict=IN_OPPOSITION, reason="no cahier link on the product page; a procédure nationale d'opposition notice is up — a new arrêté follows")
        return Probe(**base, verdict=UNVERIFIABLE, reason="no «accéder au cahier des charges» link on the product page")
    show_url = "https://www2.inao.gouv.fr" + m.group(1)
    texte = http.get_text(show_url)
    if isinstance(texte, dict):
        return Probe(**base, verdict=UNREACHABLE, upstream_url=show_url, reason=texte.get("error") or "no page")
    title = act_title(texte)
    up = french_date(title)
    held = french_date(held_date_text)
    if up is None:
        return Probe(**base, verdict=UNVERIFIABLE, upstream=title, upstream_url=show_url, reason="no dated act title on the show_texte page")
    if held is None:
        return Probe(**base, verdict=UNVERIFIABLE, upstream=f"{title} ({up.isoformat()})", upstream_url=show_url,
                     reason="the record carries no homologation date to compare with")
    if up > held:
        return Probe(**base, verdict=NEWER, upstream=f"{title} ({up.isoformat()})", upstream_url=show_url,
                     reason=f"INAO links an act of {up.isoformat()}; the record's cahier is homologated {held.isoformat()}")
    if show_texte_url and show_url != show_texte_url:
        return Probe(**base, verdict=CURRENT, upstream=f"{title} ({up.isoformat()})", upstream_url=show_url,
                     reason="same act date under a different show_texte id (a relink, not new content)")
    return Probe(**base, verdict=CURRENT, upstream=f"{title} ({up.isoformat()})", upstream_url=show_url)
