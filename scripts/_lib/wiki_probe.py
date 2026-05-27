"""Hunt Wikipedia titles for grape slugs that did not resolve with the
default `slug_to_title` + disambiguation strategy.

Two-stage discovery:

  1. Enumerate authoritative grape lists on fr.wikipedia
     (Catégorie:Cépage_noir, Cépage_blanc, Cépage_gris). For each page in
     those categories, fetch its langlinks — that gives us the title of the
     same grape entity in en/es/nl. Match the resulting titles against our
     stubbed slugs (fold accents, longest-token substring).

  2. For slugs still unresolved, fall back to the search API +
     is_grape_summary + title-matches-slug check.

Writes `raw/wikipedia/grape_overrides.json`.
"""

from __future__ import annotations

import json
import sys
import time
import unicodedata
from pathlib import Path

import requests
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib.wiki import is_grape_summary  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "raw" / "wikipedia" / "grapes"
OUT = ROOT / "raw" / "wikipedia" / "grape_overrides.json"
API_URL = "https://{lang}.wikipedia.org/w/api.php"
SUMMARY_URL = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
QUALIFIER = {"fr": "cépage", "en": "grape", "es": "uva variedad", "nl": "druivenras"}
UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:code@devloed.com) python-requests"
)
SKIP_PREFIXES = (
    "aoc-", "blanc-", "cabrieres-", "cotes-", "cremant-", "languedoc-",
    "cotes-du-", "vin-de-", "muscat-de-", "muscat-a-",
)
FR_GRAPE_CATEGORIES = ("Cépage_noir", "Cépage_blanc", "Cépage_gris")
LOCALES_TARGET = ("en", "es", "nl")  # fr is the source of category truth


def _fold(s: str) -> str:
    nf = unicodedata.normalize("NFD", s)
    return "".join(c for c in nf if unicodedata.category(c) != "Mn").lower()


def _tokens(s: str) -> set[str]:
    """Tokenise on whitespace, hyphen, and apostrophe so `Nero d'Avola` and
    `Aramon-noir` split the same way as the kebab-case cahier slug."""
    out: set[str] = set()
    cur: list[str] = []
    for ch in _fold(s):
        if ch.isalnum():
            cur.append(ch)
        elif cur:
            tok = "".join(cur)
            if len(tok) >= 3:
                out.add(tok)
            cur = []
    if cur and len("".join(cur)) >= 3:
        out.add("".join(cur))
    return out


# Tokens that often appear as a disambiguator on the Wikipedia title but not
# on the cahier slug (and vice versa). When deciding similarity we strip
# these from the title side so e.g. `bouteillan` matches `Bouteillan noir`
# and `gamay-de-chaudenay` matches `Gamay teinturier de Chaudenay`. We do NOT
# strip them from the slug side — the cahier distinguishes `aramon-blanc`
# from `aramon` and we want those to fail to match `Aramon noir`.
_DISAMBIGUATOR_TOKENS = frozenset({
    # colours (with feminine/plural forms, since the title may use them)
    "noir", "noire", "noirs", "noires",
    "blanc", "blanche", "blancs", "blanches",
    "gris", "grise", "grises",
    "rouge", "rouges", "rose", "rosee", "rosees", "rosa",
    "red", "reds", "white", "whites", "gray", "grey", "black",
    "tinto", "tinta", "tintos", "tintas",
    "blanco", "blanca", "blancos", "blancas",
    "negro", "negra", "negros", "negras", "rojo", "roja",
    "wit", "witte", "rood", "rode", "zwart", "zwarte",
    "blauw", "blauwe", "blauer",
    # viticultural type-markers (red-fleshed grapes, muscat aromatic mutations,
    # ripening cadence) — these qualify a grape but don't change its identity
    "teinturier", "teinturiere", "musque", "musquee", "precoce",
    # parent-grape group prefix used by Wikipedia for Pinot/Muscat families;
    # safe to strip because the colour/qualifier on the slug + title still has
    # to line up (e.g. `pinot-blanc` won't match `Pinot meunier` after this).
    "pinot", "muscat", "moscatel", "moscato",
    # generic article-class words from Wikipedia disambiguation suffixes
    "cepage", "grape", "uva", "druif", "cultivar", "vid", "wijndruif",
    "vinifera", "variete", "variedad", "variety", "druivenras",
    "druivensoort",
})


_COLOUR_ONLY_TOKENS = frozenset({
    "noir", "noire", "noirs", "noires",
    "blanc", "blanche", "blancs", "blanches",
    "gris", "grise", "grises",
    "rouge", "rouges", "rose", "rosee", "rosees", "rosa",
    "red", "reds", "white", "whites", "gray", "grey", "black",
    "tinto", "tinta", "tintos", "tintas",
    "blanco", "blanca", "blancos", "blancas",
    "negro", "negra", "negros", "negras", "rojo", "roja",
    "wit", "witte", "rood", "rode", "zwart", "zwarte",
    "blauw", "blauwe", "blauer",
})


def title_matches_slug(title: str, slug: str) -> bool:
    """A discovered title points at the same grape iff title and slug agree
    modulo Wikipedia disambiguator suffixes, with one colour-only relaxation:

      - title-only extra tokens must be disambiguators (colour / type-marker /
        article-class). E.g. `Bouteillan noir` matches `bouteillan` because
        `noir` is a disambiguator.
      - slug-only extras are normally rejected (so `aramon-blanc` does not
        match `Aramon noir`), BUT if every extra slug token is a colour AND
        the title has *no* colour tokens of its own, accept. This catches the
        umbrella-article pattern, e.g. `piquepoul-gris` → `Picpoul`,
        `chardonnay-rose` → `Chardonnay`, where one Wikipedia article covers
        all colour variants of the grape.
    """
    bare = title.split(" (")[0]
    s_tokens = _tokens(slug)
    t_tokens = _tokens(bare)
    if not s_tokens or not t_tokens:
        return False
    extra_slug = s_tokens - t_tokens
    extra_title = (t_tokens - s_tokens) - _DISAMBIGUATOR_TOKENS
    if extra_title:
        return False
    if not extra_slug:
        return True
    if not extra_slug.issubset(_COLOUR_ONLY_TOKENS):
        return False
    return not (t_tokens & _COLOUR_ONLY_TOKENS)


def stubbed_slugs(lang: str) -> list[str]:
    out = []
    for f in (CACHE_DIR / lang).glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("not_grape") or d.get("missing"):
            slug = d.get("slug") or f.stem
            if any(slug.startswith(p) for p in SKIP_PREFIXES):
                continue
            out.append(slug)
    return out


def enumerate_category(session: requests.Session, lang: str, category: str) -> list[str]:
    """Walk all article (ns=0) members of `Catégorie:<category>` on `<lang>.wikipedia`."""
    titles: list[str] = []
    cont: dict = {}
    while True:
        params = {
            "action": "query", "list": "categorymembers",
            "cmtitle": f"Catégorie:{category}" if lang == "fr" else f"Category:{category}",
            "cmlimit": 500, "cmnamespace": 0,
            "format": "json", "formatversion": "2",
        }
        params.update(cont)
        r = session.get(API_URL.format(lang=lang), params=params, timeout=20)
        if r.status_code != 200:
            break
        data = r.json()
        titles.extend(m["title"] for m in data.get("query", {}).get("categorymembers", []))
        cont = data.get("continue") or {}
        if not cont:
            break
    return titles


def langlinks(session: requests.Session, source_lang: str, title: str) -> dict[str, str]:
    """Return {lang: title} for the cross-language links of `title` on
    `<source_lang>.wikipedia`. Includes the source itself."""
    params = {
        "action": "query", "titles": title, "prop": "langlinks",
        "lllimit": 50, "format": "json", "formatversion": "2",
    }
    r = session.get(API_URL.format(lang=source_lang), params=params, timeout=20)
    if r.status_code != 200:
        return {}
    pages = r.json().get("query", {}).get("pages", [])
    if not pages:
        return {}
    out = {source_lang: title}
    for ll in pages[0].get("langlinks", []):
        out[ll["lang"]] = ll["title"]
    return out


def search_fallback(session: requests.Session, lang: str, slug: str) -> str | None:
    """Wikipedia search API — slow, last-resort path."""
    words = slug.replace("-", " ")
    params = {
        "action": "query", "list": "search",
        "srsearch": f"{words} {QUALIFIER.get(lang, '')}",
        "srlimit": 3, "format": "json", "formatversion": "2",
    }
    r = session.get(API_URL.format(lang=lang), params=params, timeout=15)
    if r.status_code != 200:
        return None
    for hit in r.json().get("query", {}).get("search", []):
        title = hit["title"]
        if not title_matches_slug(title, slug):
            continue
        sr = session.get(SUMMARY_URL.format(lang=lang, title=title.replace(" ", "_")), timeout=15)
        if sr.status_code != 200:
            continue
        data = sr.json()
        if data.get("type") in ("disambiguation", "no-extract"):
            continue
        if not is_grape_summary(lang, data.get("description", ""), data.get("extract", "")):
            continue
        time.sleep(0.05)
        return data["title"]
    return None


def main() -> int:
    overrides: dict[str, dict[str, str]] = {lang: {} for lang in ("fr",) + LOCALES_TARGET}
    if OUT.exists():
        overrides.update(json.loads(OUT.read_text(encoding="utf-8")))

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})

    # Stage 1 — enumerate fr grape categories.
    fr_titles: set[str] = set()
    for cat in FR_GRAPE_CATEGORIES:
        members = enumerate_category(session, "fr", cat)
        print(f"[probe] fr Catégorie:{cat} = {len(members)} pages", file=sys.stderr)
        fr_titles.update(members)
    fr_index = {_fold(t.split(" (")[0]): t for t in fr_titles}
    print(f"[probe] {len(fr_index)} unique grape pages on fr.wikipedia", file=sys.stderr)

    # Stage 2 — for each stubbed slug per locale, look up via fr index + langlinks.
    for lang in ("fr",) + LOCALES_TARGET:
        stubs = [s for s in stubbed_slugs(lang) if s not in overrides[lang]]
        added = 0
        for slug in tqdm(stubs, desc=f"category/{lang}", leave=False):
            # Pick the shortest fr_title that satisfies the strict matcher.
            matches = [t for t in fr_titles if title_matches_slug(t, slug)]
            if not matches:
                continue
            matches.sort(key=len)
            fr_title = matches[0]
            if lang == "fr":
                overrides["fr"][slug] = fr_title
                added += 1
                continue
            ll = langlinks(session, "fr", fr_title)
            time.sleep(0.05)
            target = ll.get(lang)
            if target:
                overrides[lang][slug] = target
                added += 1
        print(f"[probe/{lang}] +{added} via category/langlinks", file=sys.stderr)

    # Stage 3 — search-API fallback for whatever remains.
    for lang in ("fr",) + LOCALES_TARGET:
        stubs = [s for s in stubbed_slugs(lang) if s not in overrides[lang]]
        added = 0
        for slug in tqdm(stubs, desc=f"search/{lang}", leave=False):
            t = search_fallback(session, lang, slug)
            if t:
                overrides[lang][slug] = t
                added += 1
            time.sleep(0.05)
        print(f"[probe/{lang}] +{added} via search fallback", file=sys.stderr)

    OUT.write_text(json.dumps(overrides, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[probe] wrote {OUT.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
