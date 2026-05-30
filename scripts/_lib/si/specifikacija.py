"""Parser library for the Slovenian national specifikacija proizvoda.

Two source patterns:

  1. **MKGP per-wine `.doc`** — Microsoft Word 97-2003 binary format
     hosted at `gov.si/assets/ministrstva/MKGP/DOKUMENTI/HRANA/VINO/ZOP/`.
     11 of the 16 grandfathered SI wines. Layout is the
     "SPECIFIKACIJA PROIZVODA v skladu s 118 c členom Uredbe Sveta
     1234/2007" template — 9 numbered sections matching the EU Enotni-
     dokument structure (1 Ime, 2 Opis vin, 3 Posebni enološki postopki,
     4 Opredelitev geografskega območja, 5 Največji donos, 6 Sorte,
     7 Povezava z geografskim območjem, 8 Veljavne zahteve, 9 Pregledi).
     Section 6 (Sorte) is the variety list, split by colour (`bele:` /
     `rdeče:` / `rose:`) — a flat list, no principal / accessory split,
     same shape as the EU template.

  2. **Uradni list RS pravilnik HTML** — Slovenian official gazette.
     5 of the 16 wines:
       - `bela-krajina` + 3 PGIs (`podravje` / `posavje` / `primorska`) all
         share **Uradni list RS št. 49/2007, predpis 2634** —
         *Pravilnik o seznamu geografskih označb za vina in trsnem
         izboru*. The page has the regulation body inline (numbered
         articles `N. člen`) followed by `PRILOGA 1` (per-okoliš
         podokoliš / vinorodni kraj / vinorodni leg list) and
         `PRILOGA 2` (per-okoliš variety roster split into
         *priporočene sorte* vs *dovoljene sorte*).
       - `belokranjec` (and incidentally `metliska-crnina`) is defined
         by **Uradni list RS št. 112/2022, predpis 2690** — *Pravilnik
         o vinu s priznanim tradicionalnim poimenovanjem Metliška
         črnina in vinu s priznanim tradicionalnim poimenovanjem
         Belokranjec* — a single-style PTP regulation with per-wine
         `N. člen` sections (značilnosti vina, geografska označba,
         področje pridelave, sorte, …).

The two parser branches share a common output dict shape so stage 02f /
stage 04's augment hook treats them uniformly.

Public entry points:
  `parse_mkgp_doc(text, slug)` → dict
  `parse_uradni_list_pravilnik(html, slug)` → dict | None

Both return:
  {
    "summary": str,
    "grapes": {"principal": [slug], "accessory": [slug],
               "observation": [], "details": [...]},
    "geo_area_brief": str,
    "link_to_terroir": str,
    "section_roles": {role → text},
    "parser_template": str,
  }
"""

from __future__ import annotations

import html as html_lib
import re

from _lib.grape_entity import match_variety


# ----------------------------------------------------------------- shared

# `priporočene sorte` ↔ recommended (principal-tier in SI law)
# `dovoljene sorte`  ↔ permitted   (accessory-tier in SI law)

_GRAPE_COLOUR_LINE_RE = re.compile(r"^(bele|rdeče|rose|rose vino)\s*:\s*(.+)$", re.I)
_GRAPE_NAME_SPLIT_RE = re.compile(r"\s*,\s*|\s+in\s+", re.I)


def _slug_from_candidate(raw: str, default_colour: str) -> dict | None:
    name = re.sub(r"\s*\(.*?\)\s*", " ", raw).strip(" \t.;,")
    if not name:
        return None
    m = match_variety(name)
    if m is None:
        return None
    return {
        "slug": m.slug,
        "name": name,
        "colour": m.colour or default_colour or "",
    }


def _build_grapes_dict() -> dict:
    return {
        "principal": [],
        "accessory": [],
        "observation": [],
        "details": [],
    }


def _add_variety(grapes: dict, role: str, raw: str, colour_hint: str) -> bool:
    d = _slug_from_candidate(raw, colour_hint)
    if d is None:
        return False
    if d["slug"] in grapes["principal"] or d["slug"] in grapes["accessory"]:
        return False
    grapes[role].append(d["slug"])
    grapes["details"].append({**d, "role": role})
    return True


def _colour_to_hint(colour_label: str) -> str:
    cl = colour_label.lower()
    if cl == "bele":
        return "blanc"
    if cl in {"rdeče", "rose vino", "rose"}:
        return "noir"
    return ""


def derive_summary(text: str, max_chars: int = 600) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


# ----------------------------------------------------- MKGP .doc parser

_MKGP_SECTION_RE = re.compile(
    r"^\s*(\d+(?:\.[0-9A-Z])?)\.\s+([A-ZČŠŽa-zčšž][^\n]{1,120}?)\s*:\s*$",
    re.M,
)

_MKGP_SECTION_KEYWORDS = {
    "name": ("ime",),
    "description": ("opis vin",),
    "oenological": ("posebni enološki",),
    "geo_area": ("opredelitev geografskega", "geografsko območje"),
    "yield": ("največji donos",),
    "grape_varieties": ("sorte",),
    "link_to_terroir": ("povezava z geografskim", "povezava z območjem"),
    "requirements": ("veljavne zahteve",),
    "controls": ("pregledi",),
}


def _mkgp_sections(text: str) -> tuple[dict[int, str], dict[int, str]]:
    """Walk the MKGP doc text and slice it into {section_num → body} +
    {section_num → title}. Section numbers are 1..9 with optional
    `.A` / `.B` suffixes (e.g. `7.A. Vzročna zveza...`). We only keep
    the integer part — sub-sections fold into the parent body."""
    headers: list[tuple[int, str, int, int]] = []
    for m in _MKGP_SECTION_RE.finditer(text):
        num_str = m.group(1)
        try:
            num = int(num_str.split(".")[0])
        except ValueError:
            continue
        headers.append((num, m.group(2).strip(), m.start(), m.end()))

    bodies: dict[int, str] = {}
    titles: dict[int, str] = {}
    for i, (num, title, _hstart, hend) in enumerate(headers):
        end = headers[i + 1][2] if i + 1 < len(headers) else len(text)
        body = text[hend:end].strip()
        if num in bodies:
            bodies[num] = bodies[num] + "\n" + body
        else:
            bodies[num] = body
            titles[num] = title
    return bodies, titles


def _route_mkgp(
    sections: dict[int, str], titles: dict[int, str]
) -> dict[str, str]:
    routed: dict[str, str] = {}
    for role, keywords in _MKGP_SECTION_KEYWORDS.items():
        for num, title in titles.items():
            tlow = title.lower()
            if any(kw in tlow for kw in keywords):
                routed[role] = sections.get(num, "")
                break
    return routed


def _parse_mkgp_grape_section(body: str) -> dict:
    """Section 6 (Sorte): typically two coloured lines —
        bele: Rebula, Sauvignon, Chardonnay, ...
        rdeče: Merlot, Refošk, Modri pinot, ...
    Some wines (Teran, Metliška črnina) have only one colour; single-
    variety wines may have no colour prefix at all."""
    grapes = _build_grapes_dict()
    seen_any_colour = False
    leftover: list[str] = []

    for raw_line in body.splitlines():
        line = raw_line.strip(" \t.;")
        if not line:
            continue
        m = _GRAPE_COLOUR_LINE_RE.match(line)
        if m:
            seen_any_colour = True
            colour_hint = _colour_to_hint(m.group(1))
            for tok in _GRAPE_NAME_SPLIT_RE.split(m.group(2)):
                _add_variety(grapes, "principal", tok, colour_hint)
        else:
            leftover.append(line)

    # No colour markers → treat the whole body as a single comma list.
    # Covers single-variety wines like Teran (just "refošk").
    if not seen_any_colour and leftover:
        blob = " ".join(leftover)
        for tok in _GRAPE_NAME_SPLIT_RE.split(blob):
            _add_variety(grapes, "principal", tok, "")
    return grapes


_MKGP_STYLE_MARKERS = [
    (re.compile(r"\bpene[čc]e\s+vino\b", re.I), "sparkling-quality"),
    (re.compile(r"\bvrhunsko\s+pene[čc]e", re.I), "sparkling-quality"),
    (re.compile(r"\bsuhi?\s+jagodni\s+izbor\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bjagodni\s+izbor\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bpozna\s+trgatev\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bledeno\s+vino\b", re.I), "vendanges-tardives"),
    (re.compile(r"\bslamno\s+vino\b|\bvino\s+iz\s+su[šs]enega\s+grozdja\b", re.I),
     "vendanges-tardives"),
]
_MKGP_COLOUR_TO_STYLE = {
    "blanc": "blanc",
    "noir": "rouge",
}


def _parse_mkgp_styles(description: str, grapes: dict) -> list[str]:
    """Detect style tags from the description blob. Slice off the
    `Tradicionalna imena` boilerplate (lists every predikat designation
    authorised in Slovenian wine law for this okoliš, not styles
    actually produced) before scanning — otherwise every okoliš ends up
    tagged sparkling + vendanges-tardives."""
    blob = description or ""
    m = re.search(r"\bTradicionalna\s+imena\b", blob, re.I)
    if m:
        blob = blob[: m.start()]
    out: set[str] = set()
    for pat, slug in _MKGP_STYLE_MARKERS:
        if pat.search(blob):
            out.add(slug)
    for d in grapes.get("details") or []:
        style = _MKGP_COLOUR_TO_STYLE.get(d.get("colour"))
        if style:
            out.add(style)
    return sorted(out)


def parse_mkgp_doc(text: str, slug: str) -> dict:
    sections, titles = _mkgp_sections(text)
    routed = _route_mkgp(sections, titles)
    grapes = _parse_mkgp_grape_section(routed.get("grape_varieties", ""))
    summary = derive_summary(routed.get("description") or routed.get("geo_area") or "")
    return {
        "summary": summary,
        "grapes": grapes,
        "geo_area_brief": derive_summary(routed.get("geo_area", ""), max_chars=2000),
        "link_to_terroir": (routed.get("link_to_terroir") or "").strip(),
        "section_roles": routed,
        "styles": _parse_mkgp_styles(routed.get("description", ""), grapes),
        "parser_template": "mkgp-doc-v1",
        "section_titles": {str(k): v for k, v in titles.items()},
        "n_sections": len(sections),
    }


# -------------------------------------- Uradni list pravilnik HTML parsers

def _html_to_text(html: str) -> str:
    """Strip HTML to a clean single-string body. Drops script/style,
    collapses whitespace, preserves paragraph breaks as \\n."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    text = re.sub(r"<(p|tr|li|td|th|h[1-6]|br|div)\b[^>]*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(p|tr|li|td|th|h[1-6]|div)\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


# ------------------------- 2007 consolidated pravilnik (UL 49/2007 #2634)

# `Pravilnik o seznamu geografskih označb za vina in trsnem izboru`
# Article 5 enumerates wine regions → okoliši (paragraphs 1, 2, 3 for
# Podravje, Posavje, Primorska). Priloga 1 lists podokoliši / vinorodne
# kraji / vinorodne lege per okoliš. Priloga 2 lists priporočene +
# dovoljene varieties per okoliš.

_PRAVILNIK_2007_TITLE = re.compile(
    r"Pravilnik\s+o\s+seznamu\s+geografskih\s+označb\s+za\s+vina",
    re.I,
)

# Article 5 region paragraphs — `(1) ... Podravje`, `(2) ... Posavje`,
# `(3) ... Primorska`, followed by `(4)` referring to priloga 1.
_REGION_PARA_RE = re.compile(
    r"\((\d+)\)\s+Geografsk[ei]\s+označb[ei]\s+vinorodnih\s+okolišev\s+na\s+območju"
    r"\s+vinorodne\s+dežele\s+(Podravje|Posavje|Primorska)[\s\S]+?(?=\(\d+\)|$)",
    re.I,
)

# Priloga 2 per-okoliš block — start: `N. v vinorodnem okolišu NAME:`
# (Bela krajina is enumerated; the body has priporočene + dovoljene).
_PRILOGA2_OKOLIS_RE = re.compile(
    r"\b\d+\.\s+v\s+vinorodnem\s+okolišu\s+([^\:\n]+?)\s*:"
    r"\s*a\)\s*priporočene\s+sorte\s*:?\s*([^;]+?);"
    r"\s*b\)\s*dovoljene\s+sorte\s*:?\s*([^.]+?)\.",
    re.I | re.S,
)

# Slug → okoliš name canonicalisation. SI 2007 pravilnik uses the same
# name as eAmbrosia for the okoliš.
_SLUG_TO_OKOLIS_2007 = {
    "bela-krajina": ("Bela krajina",),
}
_SLUG_TO_REGION_2007 = {
    "podravje": "Podravje",
    "posavje": "Posavje",
    "primorska": "Primorska",
}


def _parse_pravilnik_2007(text: str, slug: str) -> dict | None:
    if not _PRAVILNIK_2007_TITLE.search(text):
        return None

    grapes = _build_grapes_dict()
    geo_area_blob: list[str] = []
    summary_blob: list[str] = []

    okoliši_in_region: list[str] = []
    if slug in _SLUG_TO_REGION_2007:
        region_name = _SLUG_TO_REGION_2007[slug]
        for m in _REGION_PARA_RE.finditer(text):
            if m.group(2).strip().lower() == region_name.lower():
                paragraph = re.sub(r"\s+", " ", m.group(0)).strip()
                summary_blob.append(paragraph)
                geo_area_blob.append(paragraph)
                # Names of okoliši inside this region, used for the
                # PGI variety roll-up below.
                # The paragraph ends "... so X, Y in Z." or "... sta X in Y."
                tail = paragraph.split("so")[-1] if " so " in paragraph else \
                       paragraph.split("sta")[-1] if " sta " in paragraph else ""
                for raw in re.split(r",|\s+in\s+", tail):
                    cleaned = raw.strip(" .;")
                    cleaned = re.sub(r"^Brda\s+ali\s+", "", cleaned)
                    cleaned = re.sub(r"\s+ali\s+.*$", "", cleaned)
                    if cleaned and cleaned.lower() not in {"podravje", "posavje", "primorska"}:
                        okoliši_in_region.append(cleaned)
                break

    target_okoliši: list[str] = []
    if slug in _SLUG_TO_OKOLIS_2007:
        target_okoliši = list(_SLUG_TO_OKOLIS_2007[slug])
    elif okoliši_in_region:
        target_okoliši = okoliši_in_region

    matched_okoliši: list[str] = []
    for m in _PRILOGA2_OKOLIS_RE.finditer(text):
        name = m.group(1).strip()
        if not any(name.lower().startswith(t.lower()) or t.lower() in name.lower()
                   for t in target_okoliši):
            continue
        matched_okoliši.append(name)
        priporocene = m.group(2)
        dovoljene = m.group(3)
        for tok in _GRAPE_NAME_SPLIT_RE.split(priporocene):
            _add_variety(grapes, "principal", tok, "")
        for tok in _GRAPE_NAME_SPLIT_RE.split(dovoljene):
            _add_variety(grapes, "accessory", tok, "")

    if not matched_okoliši and slug not in _SLUG_TO_REGION_2007:
        # Couldn't bind to any okoliš — fail (caller falls through).
        return None

    summary = derive_summary("\n".join(summary_blob) or
                              f"Vinorodna dežela / okoliš {slug}.")
    return {
        "summary": summary,
        "grapes": grapes,
        "geo_area_brief": derive_summary("\n".join(geo_area_blob), max_chars=2000),
        "link_to_terroir": "",
        "section_roles": {
            "description": summary,
            "geo_area": "\n".join(geo_area_blob),
            "grape_varieties": "; ".join(matched_okoliši),
        },
        "styles": [],
        "parser_template": "uradni-list-pravilnik-2007",
        "section_titles": {},
        "n_sections": len(matched_okoliši),
        "matched_okoliši": matched_okoliši,
    }


# -------------------- 2022 PTP pravilnik (UL 112/2022 #2690 — Belokranjec)

_PRAVILNIK_2022_TITLE = re.compile(
    r"Pravilnik\s+o\s+vinu\s+s\s+priznanim\s+tradicionalnim\s+poimenovanjem"
    r"\s+Metliška\s+črnina",
    re.I,
)

# `N. člen (title)` headers. Strict `\bčlen\b` so genitive/locative
# references inside the body ("5. člena", "9. členu") don't match.
_PRAVILNIK_CLEN_RE = re.compile(
    r"\b(\d+)\.\s+člen\b\s*(?:\(([^)]{1,80})\))?",
    re.I,
)

# Per-paragraph `(N)` markers inside an article.
_PRAVILNIK_PARA_RE = re.compile(r"\((\d+)\)\s+(.+?)(?=\s*\(\d+\)|\Z)", re.S)

# Article-5 paragraph variety list: each line is `N. NAME;` (the
# regulator's enumerated format).
_NUMBERED_VARIETY_RE = re.compile(r"^\s*\d+\.\s+(.+?)\s*[;.]?\s*$", re.M)


def _articles_2022(text: str) -> dict[int, tuple[str, str]]:
    members = list(_PRAVILNIK_CLEN_RE.finditer(text))
    bodies: dict[int, tuple[str, str]] = {}
    for i, m in enumerate(members):
        try:
            num = int(m.group(1))
        except ValueError:
            continue
        end = members[i + 1].start() if i + 1 < len(members) else len(text)
        if num not in bodies:  # first occurrence wins (real article header)
            bodies[num] = (m.group(2) or "", text[m.end():end].strip())
    return bodies


def _find_article_by_title(
    bodies: dict[int, tuple[str, str]], needle: str
) -> tuple[int, str] | None:
    for num, (title, body) in bodies.items():
        if needle.lower() in (title or "").lower():
            return num, body
    return None


def _parse_pravilnik_2022_belokranjec(text: str, slug: str) -> dict | None:
    if not _PRAVILNIK_2022_TITLE.search(text):
        return None
    if slug != "belokranjec":
        return None

    bodies = _articles_2022(text)
    if not bodies:
        return None

    # Article 2 (značilnosti vina): paragraph (2) is Belokranjec.
    description = ""
    art2 = _find_article_by_title(bodies, "značilnosti")
    if art2:
        for pm in _PRAVILNIK_PARA_RE.finditer(art2[1]):
            if pm.group(1) == "2":
                description = re.sub(r"\s+", " ", pm.group(2)).strip()
                break

    # Article 4 (področje pridelave): production area — single paragraph
    # covering both PTP wines (Metliška črnina + Belokranjec).
    geo_area = ""
    art4 = _find_article_by_title(bodies, "področje")
    if art4:
        geo_area = re.sub(r"\s+", " ", art4[1]).strip()

    # Article 5 paragraph (2): the enumerated Belokranjec variety list.
    grapes = _build_grapes_dict()
    variety_body = ""
    art5 = _find_article_by_title(bodies, "sorte vinske")
    if art5:
        for pm in _PRAVILNIK_PARA_RE.finditer(art5[1]):
            if pm.group(1) != "2":
                continue
            variety_body = pm.group(2)
            for vm in _NUMBERED_VARIETY_RE.finditer(variety_body):
                _add_variety(grapes, "principal", vm.group(1), "blanc")
            break

    return {
        "summary": derive_summary(description),
        "grapes": grapes,
        "geo_area_brief": derive_summary(geo_area, max_chars=2000),
        "link_to_terroir": "",
        "section_roles": {
            "description": description,
            "geo_area": geo_area,
            "grape_varieties": variety_body,
        },
        "styles": ["blanc"],
        "parser_template": "uradni-list-pravilnik-2022-ptp",
        "section_titles": {str(n): t for n, (t, _) in bodies.items() if t},
        "n_sections": len(bodies),
    }


# ----------------------------------------------------- public dispatch

def parse_uradni_list_pravilnik(html: str, slug: str) -> dict | None:
    """Dispatch to the right parser branch by pravilnik title."""
    text = _html_to_text(html)
    if _PRAVILNIK_2007_TITLE.search(text):
        return _parse_pravilnik_2007(text, slug)
    if _PRAVILNIK_2022_TITLE.search(text):
        return _parse_pravilnik_2022_belokranjec(text, slug)
    return None
