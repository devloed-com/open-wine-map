"""The appellation card as a reader sees it, next to every source document
behind it — the packet an independent validator grades.

Two halves, built from what the site ships and what the pipeline cached:

- **card** — the record as the map renders it in one locale: the startup
  record (`wiki/data/aocs.<locale>.<hash>.js`) merged with the panel payload
  (`wiki/data/d/<locale>/<slug>.json`), rendered through the same
  `render_content_block` the server-rendered entity page uses, then reduced
  to plain text. What the reader sees, nothing the pipeline knows.
- **documents** — the regulator texts and sidecars the card was built from:
  the extracted record's routed sections (the whole document, not the lien
  alone), the national-spec and register-fiche sidecars where the country
  has them, and the Wikipedia page stage 02b fetched. Each document carries
  its kind, label, URL / path and text, so a verdict can quote it.

Country-agnostic: the per-country directory tables below are the only
place a country is named; a new corpus adds one row. Nothing here reads the
pipeline's grounding quotes, prompts or gate verdicts — the validator must
stay independent of the machinery it grades (docs/plan-validators.md).
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "wiki"
RAW = ROOT / "raw"

LOCALES = ("en", "fr", "es", "nl")

# Where each country's stage-02 records live (the table in 04_build_maps.py,
# `EXTRACTED*`). Several dirs per country: the first that holds the slug wins.
EXTRACTED_DIRS: dict[str, tuple[Path, ...]] = {
    "fr": (RAW / "inao" / "cahier-extracted",),
    "es": (RAW / "es" / "pliegos-extracted",),
    "pt": (RAW / "pt" / "cadernos-extracted",),
    "it": (RAW / "it" / "disciplinari-extracted",),
    "at": (RAW / "at" / "dokumente-extracted",),
    "de": (RAW / "de" / "dokumente-extracted",),
    "si": (RAW / "si" / "dokumenti-extracted",),
    "hr": (RAW / "hr" / "dokumenti-extracted",),
    "hu": (RAW / "hu" / "dokumentumok-extracted",),
    "ro": (RAW / "ro" / "dokumente-extracted",),
    "bg": (RAW / "bg" / "dokumenti-extracted",),
    "gr": (RAW / "gr" / "dokumenti-extracted",),
    "cy": (RAW / "cy" / "dokumenti-extracted",),
    "sk": (RAW / "sk" / "dokumenty-extracted",),
    "cz": (RAW / "cz" / "dokumenty-extracted",),
    "ch": (RAW / "ch" / "dokumente-extracted",),
    "lu": (RAW / "lu" / "cahier-extracted",),
    "be": (RAW / "be" / "dokumenten-extracted",),
    "nl": (RAW / "nl" / "dokumenten-extracted",),
    "mt": (RAW / "mt" / "dokumente-extracted",),
    "gb": (RAW / "gb" / "specs-extracted",),
    "us": (RAW / "us" / "avas-extracted",),
    "au": (RAW / "au" / "gis-extracted",),
}

# Per-country sidecars stage 04 merges into the card at load time (the
# national-spec layers) and the EU-register fiche extracted beside them. Each
# entry: (kind, label shown to the judge, directory). A sidecar is read when
# `<dir>/<slug>.json` exists.
SIDECAR_DIRS: dict[str, tuple[tuple[str, str, Path], ...]] = {
    "es": (("national-spec", "Pliego de condiciones (national, MAPA / autonomous community)",
            RAW / "es" / "national-pliegos-extracted"),),
    "it": (("national-spec", "Disciplinare di produzione (MASAF)",
            RAW / "it" / "masaf-disciplinari-extracted"),),
    "de": (("national-spec", "Produktspezifikation (BLE)",
            RAW / "de" / "produktspezifikationen-extracted"),),
    "at": (("national-spec", "Produktspezifikation (BML)",
            RAW / "at" / "produktspezifikationen-extracted"),),
    "si": (("national-spec", "Specifikacija proizvoda (MKGP / Uradni list)",
            RAW / "si" / "specifikacije-extracted"),
           ("register-fiche", "EU register fiche technique", RAW / "si" / "register-fiches-extracted")),
    "hr": (("national-spec", "Specifikacija proizvoda (Ministarstvo poljoprivrede)",
            RAW / "hr" / "specifikacije-extracted"),
           ("register-fiche", "EU register fiche technique", RAW / "hr" / "register-fiches-extracted")),
    "bg": (("national-spec", "Продуктова спецификация (ИАЛВ)", RAW / "bg" / "national-specs-extracted"),
           ("register-fiche", "EU register fiche technique", RAW / "bg" / "register-fiches-extracted")),
    "gr": (("national-spec", "Προδιαγραφή προϊόντος (ΥΠΑΑΤ)", RAW / "gr" / "national-specs-extracted"),
           ("register-fiche", "EU register fiche technique", RAW / "gr" / "register-fiches-extracted")),
    "cy": (("national-spec", "Τεχνικός φάκελος (ΥΓΑΑΠ)", RAW / "cy" / "national-specs-extracted"),),
    "ro": (("national-spec", "Caiet de sarcini (ONVPV)", RAW / "ro" / "national-specs-extracted"),
           ("register-fiche", "EU register fiche technique", RAW / "ro" / "register-fiches-extracted")),
    "hu": (("national-spec", "Termékleírás (HNT)", RAW / "hu" / "national-specs-extracted"),
           ("register-fiche", "EU register fiche technique", RAW / "hu" / "register-fiches-extracted")),
    "sk": (("national-spec", "Špecifikácia výrobku (ÚPV SR)", RAW / "sk" / "national-specs-extracted"),
           ("register-fiche", "EU register fiche technique", RAW / "sk" / "register-fiches-extracted")),
    "cz": (("register-fiche", "EU register fiche technique", RAW / "cz" / "register-fiches-extracted"),),
}

# The Wikipedia cache is keyed by the regulator's language, not the country
# code (CLAUDE.md: AT/DE → de, SI → sl, GR/CY → el, CZ → cs, LU → fr, MT/GB →
# en); BE and CH carry a per-record `source_lang`, read from the payload.
WIKI_LANG_BY_COUNTRY = {
    "fr": "fr", "es": "es", "pt": "pt", "it": "it", "at": "de", "de": "de", "si": "sl",
    "hr": "hr", "hu": "hu", "ro": "ro", "bg": "bg", "gr": "el", "cy": "el", "sk": "sk",
    "cz": "cs", "lu": "fr", "nl": "nl", "mt": "en", "gb": "en", "us": "en", "au": "en",
}

# Text-bearing keys of an extracted record or a sidecar, in the order the
# judge should read them. Dict-valued keys are joined section by section.
_TEXT_KEYS = ("summary", "description_text", "geo_area", "geo_area_brief", "geo_area_text",
              "section_text", "link_to_terroir_full", "link_to_terroir", "zusammenhang_text",
              "region_terroir_text", "max_yields", "demarcation")
_SECTION_DICT_KEYS = ("sections", "article_bodies")
_LIST_TEXT_PREFIX = "raw_section_"

MAX_WIKI_CHARS = 12_000
MAX_SOURCE_CHARS = 90_000

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9,
          "X": 10, "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15}


def _section_order(key: str) -> tuple:
    """Sort key for section ids: Roman numerals first, then dotted / lettered
    numbering ("7", "7.1", "a") — a fixed-width tuple so int never meets str."""
    if key in _ROMAN:
        return (0, _ROMAN[key], 0, 0, "")
    parts = re.findall(r"\d+|[a-z]+", str(key).lower())
    nums = [int(x) if x.isdigit() else ord(x[0]) for x in parts][:3]
    nums += [0] * (3 - len(nums))
    return (1, *nums, str(key))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────── the site ──


@lru_cache(maxsize=None)
def load_startup(locale: str) -> tuple[dict, dict]:
    """(aocs, grapes_info) of the locale's startup bundle, or ({}, {}) when
    the site has not been built."""
    paths = sorted((WIKI / "data").glob(f"aocs.{locale}.*.js"))
    if not paths:
        return {}, {}
    text = paths[-1].read_text(encoding="utf-8")
    m = re.search(r"__OWM_DATA\s*=\s*(\{.*\})\s*;?\s*$", text, re.S)
    if not m:
        return {}, {}
    data = json.loads(m.group(1))
    return data.get("aocs") or {}, data.get("grapes_info") or {}


def load_payload(locale: str, slug: str) -> dict | None:
    p = WIKI / "data" / "d" / locale / f"{slug}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def merged_record(locale: str, slug: str) -> dict | None:
    """The record as the JS app holds it after the panel payload is
    hydrated: startup fields overlaid with the payload."""
    aocs, _ = load_startup(locale)
    rec = aocs.get(slug)
    if rec is None:
        return None
    payload = load_payload(locale, slug) or {}
    out = {**rec, **payload, "slug": slug}
    return out


# ──────────────────────────────────────────────────────── the sources ──


# The spirit drinks, aromatised wines and ciders outside France: one directory
# for every country (scripts/drinks/), each record carrying its own country.
DRINKS_DIR = RAW / "drinks" / "extracted"


def record_path(country: str, slug: str) -> Path | None:
    for d in (*EXTRACTED_DIRS.get(country, ()), DRINKS_DIR):
        p = d / f"{slug}.json"
        if p.exists():
            return p
    return None


def load_json(path: Path) -> dict | None:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def roster_text(grapes: dict | list | None) -> str:
    """The parsed variety roster as the judge should read it — one line per
    variety with its role and colour, the regulator's spelling first. A
    record carries a dict with `details`; the DE and AT Produktspezifikation
    sidecars carry the detail list itself."""
    if isinstance(grapes, list):
        grapes = {"details": grapes}
    if not isinstance(grapes, dict):
        return ""
    details = grapes.get("details") or []
    lines = []
    seen = set()
    for d in details:
        if not isinstance(d, dict):
            continue
        name = d.get("name") or d.get("slug") or ""
        key = (name, d.get("role"))
        if not name or key in seen:
            continue
        seen.add(key)
        bits = [name]
        if d.get("slug") and d.get("slug") != name:
            bits.append(f"[{d['slug']}]")
        if d.get("role"):
            bits.append(f"— {d['role']}")
        if d.get("colour"):
            bits.append(f"({d['colour']})")
        lines.append(" ".join(bits))
    if not lines:
        for role in ("principal", "accessory"):
            for s in grapes.get(role) or []:
                lines.append(f"{s} — {role}")
    return "\n".join(lines)


def text_blocks(d: dict, *, label: str) -> list[tuple[str, str]]:
    """(heading, text) blocks of an extracted record or sidecar, deduplicated
    by content so `link_to_terroir` next to `link_to_terroir_full` is read
    once."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(heading: str, text) -> None:
        if not isinstance(text, str):
            return
        t = text.strip()
        if len(t) < 20:
            return
        h = _sha(t)
        if h in seen:
            return
        seen.add(h)
        out.append((heading, t))

    titles = d.get("section_titles") if isinstance(d.get("section_titles"), dict) else {}
    for key in _SECTION_DICT_KEYS:
        sec = d.get(key)
        if isinstance(sec, dict) and sec:
            for k in sorted(sec, key=_section_order):
                title = titles.get(k) if isinstance(titles, dict) else None
                heading = f"{label} — section {k}" + (f" · {title}" if title and title != k else "")
                add(heading, sec[k])
    if not any(isinstance(d.get(k), dict) and d.get(k) for k in _SECTION_DICT_KEYS):
        roles = d.get("section_roles")
        if isinstance(roles, dict):
            for k, v in roles.items():
                add(f"{label} — {k}", v)
    for key in _TEXT_KEYS:
        if key == "link_to_terroir" and isinstance(d.get("link_to_terroir_full"), str) and d["link_to_terroir_full"]:
            continue
        add(f"{label} — {key}", d.get(key))
    for key, v in d.items():
        if key.startswith(_LIST_TEXT_PREFIX) and isinstance(v, list):
            add(f"{label} — {key}", "\n".join(str(x) for x in v))
    for ann in d.get("annexes") or []:
        if isinstance(ann, dict):
            bodies = ann.get("article_bodies") or {}
            for k in sorted(bodies, key=_section_order):
                add(f"{label} — annex «{ann.get('title') or ''}» article {k}", bodies[k])
    gc = d.get("geo_communes")
    if isinstance(gc, list) and gc:
        names = [x.get("name") if isinstance(x, dict) else str(x) for x in gc]
        add(f"{label} — geo_communes (parsed)", ", ".join(n for n in names if n))
    roster = roster_text(d.get("grapes"))
    if roster:
        add(f"{label} — variety roster (parsed)", roster)
    return out


def _source_url(d: dict) -> str:
    src = d.get("source") or {}
    if isinstance(src, dict):
        for k in ("source_url", "url", "final_url", "boagri_url", "register_attachment_url",
                  "show_texte_url", "product_url"):
            if src.get(k):
                return str(src[k])
    for k in ("source_url", "url"):
        if isinstance(d.get(k), str) and d[k]:
            return d[k]
    srcs = d.get("sources")
    if isinstance(srcs, list):
        for s in srcs:
            if isinstance(s, dict) and s.get("url"):
                return str(s["url"])
    return ""


def wikipedia_record(country: str, slug: str, source_lang: str | None) -> dict | None:
    lang = source_lang or WIKI_LANG_BY_COUNTRY.get(country) or country
    p = RAW / "wikipedia" / "aocs" / lang / f"{slug}.json"
    d = load_json(p) if p.exists() else None
    if not d or not (d.get("full_text") or d.get("lead_extract")):
        return None
    return d


def source_documents(country: str, slug: str, *, source_lang: str | None = None,
                     parent_slug: str | None = None,
                     max_chars: int = MAX_SOURCE_CHARS) -> list[dict]:
    """Every document behind the card, primary first, capped at `max_chars`
    of text in total (the regulator record is never cut before a sidecar).
    A sub-denomination with no record of its own reads its parent's."""
    docs: list[dict] = []
    budget = max_chars

    def push(kind: str, label: str, path: Path | None, url: str, blocks: list[tuple[str, str]],
             cap: int | None = None) -> None:
        nonlocal budget
        if not blocks:
            return
        text = "\n\n".join(f"## {h}\n{t}" for h, t in blocks)
        if cap is not None and len(text) > cap:
            text = text[:cap] + "\n[… truncated …]"
        if len(text) > budget:
            if budget < 2000:
                return
            text = text[:budget] + "\n[… truncated: budget …]"
        budget -= len(text)
        rel = (str(path.relative_to(ROOT)) if path and path.is_relative_to(ROOT) else str(path or ""))
        docs.append({"kind": kind, "label": label, "path": rel,
                     "url": url, "chars": len(text), "text": text})

    rp = record_path(country, slug)
    rec = load_json(rp) if rp else None
    from_parent = False
    if (rec is None or not text_blocks(rec, label="x")) and parent_slug:
        prp = record_path(country, parent_slug)
        prec = load_json(prp) if prp else None
        if prec and text_blocks(prec, label="x"):
            rp, rec, from_parent = prp, prec, True
    if rec:
        label = "Regulator record" + (f" (parent «{parent_slug}»)" if from_parent else "")
        push("regulator", label, rp, _source_url(rec), text_blocks(rec, label=label))
    for kind, label, d in SIDECAR_DIRS.get(country, ()):
        for s in (slug, parent_slug if from_parent or parent_slug else None):
            if not s:
                continue
            p = d / f"{s}.json"
            if not p.exists():
                continue
            side = load_json(p)
            if side:
                push(kind, label + (f" (parent «{s}»)" if s != slug else ""), p, _source_url(side),
                     text_blocks(side, label=label))
            break
    if country == "cz":
        decree = load_json(RAW / "cz" / "national-specs" / "varieties.json")
        if decree and decree.get("varieties"):
            # the roster every CZ card follows (the 2011 register fiches
            # predate it — graded against the fiche alone, Moravské drew
            # four false findings on the first run)
            rows = [f"{v.get('name')} [{v.get('slug') or '?'}] — principal ({v.get('colour') or '?'})"
                    for v in decree["varieties"]]
            push("national-spec", f"{decree.get('source_anchor') or 'Vyhláška 88/2017 Sb.'} — variety roster",
                 RAW / "cz" / "national-specs" / "varieties.json", decree.get("source_canonical_url") or "",
                 [(decree.get("source_title") or "Vyhláška 88/2017 Sb.", "\n".join(rows))])
        region = (rec or {}).get("region") or ""
        for p in sorted((RAW / "cz" / "national-specs").glob("chzo-*.json")):
            side = load_json(p)
            if side and (not region or side.get("region") == region):
                push("national-spec", "SZPI CHZO specification (region)", p, side.get("source_url") or "",
                     text_blocks(side, label="SZPI CHZO specification"))
    wiki = wikipedia_record(country, slug, source_lang)
    if wiki:
        push("wikipedia", f"Wikipedia ({wiki.get('lang')}) «{wiki.get('page_title')}»", None,
             wiki.get("page_url") or "", [("full text", wiki.get("full_text") or wiki.get("lead_extract") or "")],
             cap=MAX_WIKI_CHARS)
    return docs


# ───────────────────────────────────────────────────────────── the card ──


class _Text(HTMLParser):
    _BLOCK = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "section",
              "article", "header", "footer", "tr", "br", "details", "summary", "nav", "blockquote"}
    _SKIP = {"script", "style", "svg", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        if tag in self._BLOCK:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("• ")
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag in ("span", "a") and ("pill" in cls or "chip" in cls):
            self.parts.append(" · ")
        if tag == "img" and a.get("alt"):
            self.parts.append(a["alt"])

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        if tag in self._BLOCK:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" ")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    p = _Text()
    p.feed(markup or "")
    text = html.unescape("".join(p.parts))
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@lru_cache(maxsize=None)
def _render_ctx(locale: str):
    """A `RenderCtx` for the locale — the same inputs render() gives the
    server-rendered card (labels through gettext, the grape and term
    tooltips); style tooltips are left out, they are hover-only."""
    from _lib import map_template as mt
    from _lib.content_block import RenderCtx
    from _lib.gi_terms import build_terms_info
    from _lib.i18n import load_translations
    from _lib.vineyard_envelope import lod_config

    tr = load_translations(locale).gettext
    grapes_info = load_startup(locale)[1]
    return RenderCtx(
        locale=locale, labels=mt.build_labels(tr), region_labels=mt.build_region_labels(tr),
        country_labels=mt.build_country_labels(tr), country_flag_emoji=mt._COUNTRY_FLAG_EMOJI,
        grapes_info=grapes_info, styles_info={}, style_labels=mt.build_style_labels(tr),
        github_new_issue_url=mt._GITHUB_NEW_ISSUE_URL, terms_info=build_terms_info(locale),
        lod=lod_config(), browse_path="",
    )


def card_html(locale: str, slug: str, rec: dict | None = None) -> str:
    """The card as the entity page renders it (server-side), for one record
    of the built site."""
    from _lib.content_block import render_content_block
    rec = rec if rec is not None else merged_record(locale, slug)
    if rec is None:
        return ""
    aocs, _ = load_startup(locale)
    kids = [
        {"name": aocs[k].get("name") or k, "path": f"/{locale}/{k}",
         "classification": aocs[k].get("class_label") or ""}
        for k in (rec.get("children") or []) if isinstance(k, str) and k in aocs
    ]
    return render_content_block(rec, slug, _render_ctx(locale), children=kids)


def card_text(locale: str, slug: str, rec: dict | None = None) -> str:
    return html_to_text(card_html(locale, slug, rec))


def _grape_label(slug: str, grapes_info: dict, rec: dict) -> str:
    names = rec.get("grape_names") or {}
    if isinstance(names, dict) and names.get(slug):
        return str(names[slug])
    gi = grapes_info.get(slug) or {}
    return str(gi.get("name") or gi.get("canonical_name") or slug)


def card_fields(locale: str, slug: str, rec: dict | None = None) -> dict:
    """The card's content as structured fields — what the judge is asked
    about section by section (and what a finding is anchored to)."""
    rec = rec if rec is not None else merged_record(locale, slug)
    if rec is None:
        return {}
    _, grapes_info = load_startup(locale)
    tf = rec.get("terroir_facts") or {}
    facts = (tf.get("facts") or []) if isinstance(tf, dict) else (tf if isinstance(tf, list) else [])
    srcs = rec.get("sources") or {}
    urls = {}
    for k, v in (srcs.items() if isinstance(srcs, dict) else []):
        if isinstance(v, str) and v.startswith("http"):
            urls[k] = v
        elif isinstance(v, dict) and v.get("url"):
            urls[k] = v["url"]
    return {
        "name": rec.get("name"), "name_latin": rec.get("name_latin") or "",
        "classification": rec.get("class_label"), "kind": rec.get("kind"),
        "eu_scheme": rec.get("eu_scheme"), "national_term": rec.get("national_term"),
        "country": rec.get("country"), "region": rec.get("region"),
        "is_sub_denomination": bool(rec.get("is_sub_denomination")), "parent_slug": rec.get("parent_slug") or "",
        "parent_name": rec.get("parent_name") or "", "children": rec.get("children") or [],
        "is_stub": bool(rec.get("is_stub")), "is_wine": rec.get("is_wine"),
        "styles": rec.get("styles") or [], "styles_simple": rec.get("styles_simple") or [],
        "grapes_principal": [{"slug": g, "label": _grape_label(g, grapes_info, rec)} for g in rec.get("grapes_principal") or []],
        "grapes_accessory": [{"slug": g, "label": _grape_label(g, grapes_info, rec)} for g in rec.get("grapes_accessory") or []],
        "geom_source": rec.get("geom_source"), "area_deg2": rec.get("area"),
        "terroir_facts": [{"bullet": f.get("bullet"), "subsection": f.get("subsection"),
                           "provenance": f.get("provenance")} for f in facts if isinstance(f, dict)],
        "facts_inherited_from": (tf.get("inherited_from") if isinstance(tf, dict) else None),
        # facts XOR summary: the card renders the summary only when it has no
        # facts, so the judge sees it only then (the first 40-card run graded
        # 16 summaries no reader ever saw).
        "summary": (rec.get("summary") or "") if not facts else "",
        "summary_translation": bool(rec.get("summary_translation")) if not facts else False,
        "note": rec.get("note") or None, "menzioni": len(rec.get("menzioni") or []),
        "dulok": len(rec.get("dulok") or []), "source_urls": urls,
        "cancelled": rec.get("cancelled") or None, "promoted": rec.get("promoted") or None,
    }


# ──────────────────────────────────────────────────── known checks ──


def known_checks(slug: str, rec: dict) -> list[str]:
    """Deterministic facts about the record the judge is told up front, so
    it does not spend its attention re-finding what the audits already
    know: an empty roster, a stub, inherited facts, verified-misleading
    claims already on file."""
    out: list[str] = []
    if rec.get("is_stub"):
        out.append("The record is a STUB: no regulator document was parsed for it; the card shows the catalogue entry only.")
    if not (rec.get("grapes_principal") or rec.get("grapes_accessory")):
        out.append("The grape roster is EMPTY on the card.")
    tf = rec.get("terroir_facts") or {}
    if isinstance(tf, dict) and tf.get("inherited_from"):
        out.append(f"The terroir facts are INHERITED from the parent record «{tf['inherited_from']}» (a sub-denomination shows its parent's facts).")
    if rec.get("is_sub_denomination"):
        out.append("The record is a sub-denomination: its roster and styles are the parent's unless the regulator singles it out.")
    try:
        from _lib.terroir_feedback import load_feedback
        fb = load_feedback(slug)
    except Exception:  # noqa: BLE001
        fb = None
    if fb:
        for e in (fb.get("do_not_claim") or [])[:12]:
            claim = e.get("bullet") or e.get("src") or e.get("claim") or ""
            if claim:
                out.append(f"Already verified misleading (do not re-report, check it is gone): {claim[:200]}")
    return out


# ───────────────────────────────────────────────────────────── packet ──


def build_packet(locale: str, slug: str, *, max_source_chars: int = MAX_SOURCE_CHARS) -> dict | None:
    rec = merged_record(locale, slug)
    if rec is None:
        return None
    country = rec.get("country") or ""
    source_lang = rec.get("source_lang") or None
    fields = card_fields(locale, slug, rec)
    text = card_text(locale, slug, rec)
    docs = source_documents(country, slug, source_lang=source_lang,
                            parent_slug=rec.get("parent_slug") or None, max_chars=max_source_chars)
    return {
        "slug": slug, "locale": locale, "country": country,
        "source_lang": source_lang or WIKI_LANG_BY_COUNTRY.get(country) or country,
        "card_text": text, "card": fields, "documents": docs,
        "known_checks": known_checks(slug, rec),
        "documents_sha": _sha("\n".join(d["text"] for d in docs)),
        "card_sha": _sha(text),
    }


def packet_user_message(p: dict) -> str:
    """The judge's user turn: card first (what the reader sees), then the
    documents it must be checked against."""
    card = p["card"]
    head = [
        f"RECORD: {card.get('name')} ({p['slug']}) · country {p['country']} · regulator language {p['source_lang']} · card locale {p['locale']}",
        f"geometry source: {card.get('geom_source')}",
    ]
    if p.get("known_checks"):
        head.append("KNOWN (do not re-report):\n- " + "\n- ".join(p["known_checks"]))
    card_json = json.dumps({k: v for k, v in card.items() if k not in ("source_urls",)}, ensure_ascii=False, indent=0)
    docs = []
    for i, d in enumerate(p["documents"]):
        docs.append(f"=== DOCUMENT {i} [{d['kind']}] {d['label']}\n{d['url'] or d['path']}\n{d['text']}")
    return (
        "\n".join(head)
        + "\n\nCARD AS RENDERED (plain text of the reader's card):\n" + p["card_text"]
        + "\n\nCARD FIELDS (structured):\n" + card_json
        + "\n\nSOURCE DOCUMENTS (" + str(len(docs)) + "):\n\n" + "\n\n".join(docs)
    )
