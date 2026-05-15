"""Extract structured fields from each downloaded cahier des charges.

Pipeline stage 02.

For each cahier PDF in `raw/inao/cahiers/<sha>.pdf` (indexed by the manifest
written by stage 01), run `pdftotext -layout` and parse the XII-section legal
template to produce one JSON file per *denomination* under
`raw/inao/cahier-extracted/`.

A "denomination" here is one row of `id_denomination_geo` in the SIQO
referentiel. Most appellations have a single denomination — their own name —
but some (Muscadet Sèvre et Maine, Côtes du Rhône Villages, Coteaux du Layon,
Alsace grand cru, ...) carry several Dénominations Géographiques
Complémentaires (DGCs) under the same `id_appellation`. Each DGC gets its
own JSON, reuses the parent appellation's cahier (a single PDF per
appellation), and is tagged with `parent_*` fields so downstream stages can
render the relation.

A single BO Agri PDF sometimes bundles multiple *appellations* (e.g. all 51
Alsace grand crus share one file, or a JORF "sommaire" packs ~30 cahiers).
The parser splits on `Cahier des charges de l'appellation d'origine
contrôlée « <NAME> »` headers and keeps only the segment whose name matches
the parent appellation.

Re-runnable: a per-PDF cache keyed by sha avoids re-running pdftotext.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from tqdm import tqdm

from _lib.grape_lexicon import parse_grapes, parse_styles

ROOT = Path(__file__).resolve().parent.parent
CAHIERS = ROOT / "raw" / "inao" / "cahiers"
MANIFEST_PATH = CAHIERS / "manifest.json"
TEXT_CACHE = CAHIERS / ".text"
OUT_DIR = ROOT / "raw" / "inao" / "cahier-extracted"
INDEX_PATH = OUT_DIR / "_index.json"
SIQO_CSV = ROOT / "raw" / "inao" / "siqo-referentiel.csv"

CAHIER_HEADER_RE = re.compile(
    r"Cahier des charges\s+(?:de|des)\s+(?:"
    r"l['’]appellation d['’]origine [\wÀ-ÿ]+"
    r"|l['’]Indication G[ée]ographique Prot[ée]g[ée]e"
    r"|[\wÀ-ÿ ]+?\s+appellations? d['’]origine [\wÀ-ÿ]+"
    r")\s*"
    r"[«\"]\s*([^»\"\n]+?)\s*[»\"]",
    re.IGNORECASE,
)

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
# Cahiers use a mix of HYPHEN-MINUS, EN DASH, EM DASH, HORIZONTAL BAR, MINUS SIGN
DASH = r"[-–—―−]"
SECTION_HDR_RE = re.compile(
    # Section header: roman numeral, then either a period (post-2024 cahiers
    # write "I. Nom de l'appellation"), a dash ("I − Nom"), or both
    # ("I. − Nom"). Title runs to end of line. Requiring at least one of
    # period/dash separates real headers from in-sentence Roman references.
    rf"^[ \t]*({'|'.join(ROMAN)})[ \t]*(?:\.[ \t]*(?:{DASH}[ \t]*)?|{DASH}[ \t]*)([^\n]+?)\s*$",
    re.MULTILINE,
)
CHAPITRE_RE = re.compile(r"^[ \t]*CHAPITRE\s+[IVX]+(?:er)?\b", re.MULTILINE | re.IGNORECASE)

# A "<département header>: <comma list of communes>" block. The dept name is
# a short proper-noun token (no commas, no colons) introduced by one of:
#   - "du département du <D>" / "des départements de <D>" (single-dept form,
#     possibly followed by additional context like "sur la base du COG ...")
#   - "Département <D>:" / "- D <D> :" (multi-dept form, one per line)
# Match a département header introducing a comma-separated commune list.
# Two grammatical forms in INAO cahiers:
#   "... du département du Jura, sur la base du COG de l'année 2021 :"
#   "- Département de Maine-et-Loire : Bouchemaine, ..."
# Department names are 1+ capitalised words possibly hyphenated; we anchor
# the end on either a comma, a parenthesis, or a colon.
# French article that introduces a dept name in cahiers. Each alternative
# includes the trailing whitespace it needs so the dept token comes right
# after — important because "de l'Yonne" has no space between the apostrophe
# and the proper noun.
_ART = r"(?:du\s+|de\s+(?:la|le|les)\s+|de\s+l['’]\s*|d['’]\s*|de(?:s)?\s+)"

_DEPT_HEADER_PATTERN = (
    # in-paragraph form: "... du département <ART><DEPT> ... :"
    # Prefix alternatives are case-insensitive (sentence-start "Dans le"
    # alongside mid-sentence "dans le"); the dept-name capture is NOT,
    # because we rely on uppercase initials to bound a proper-noun span.
    r"(?:"
    r"(?i:du\s+|de(?:s)?\s+|de\s+(?:la|le|les)\s+|de\s+l['’]\s*|d['’]\s*|dans\s+(?:le|les)\s+)"
    r"(?i:d[ée]partements?)\s+(?i:" + _ART + r")"
    # or per-line list form: "- Département <ART><DEPT> :"
    + r"|(?:^|\n)\s*-?\s*(?i:d[ée]partement)\s+(?i:" + _ART + r")"
    + r")"
    + r"(?P<dept>"
    + r"[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜŸ][\wÀ-ÿ'’]*"
    + r"(?:-[\wÀ-ÿ'’]+)*"
    + r"(?:\s+[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜŸ][\wÀ-ÿ'’]*(?:-[\wÀ-ÿ'’]+)*)*"
    + r")"
    + r"\s*(?:\(\d+\))?"
    + r"(?P<after>(?:[^:\n]*\n?){0,4}?):"
    + r"(?P<communes>[^\n]*(?:\n(?!\s*\n|\s*-?\s*(?i:D[ée]partement|Dans\s+(?:le|les)\s+d[ée]partement)|\s*\d°|\s*[IVX]+\s*\.\s*-)[^\n]*)*)"
)
DEPT_HEADER_RE = re.compile(_DEPT_HEADER_PATTERN, re.MULTILINE)
COG_YEAR_RE = re.compile(r"code officiel g[ée]ographique de l['’]ann[ée]e\s+(\d{4})")


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def normalize_name(s: str) -> str:
    """Loose match key — strips diacritics, casing, spacing/hyphens."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[\W_]+", "", s).lower()


def pdftotext(pdf_path: Path) -> str:
    TEXT_CACHE.mkdir(parents=True, exist_ok=True)
    cached = TEXT_CACHE / f"{pdf_path.stem}.txt"
    if cached.exists() and cached.stat().st_mtime >= pdf_path.stat().st_mtime:
        return cached.read_text(encoding="utf-8")
    out = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout
    if out is None:
        print(f"Erreur : Impossible d'extraire le texte de {pdf_path}")
        return "" # Ou gérez l'erreur autrement
    cached.write_text(out, encoding="utf-8")
    return out


def split_bundle(text: str) -> dict[str, str]:
    """A BO Agri PDF can bundle many cahiers. Split into segments keyed by
    the appellation name from each `Cahier des charges...« NAME »` header.

    Each cahier carries two title occurrences: a sentence-case "preamble"
    line citing the homologation decret, then the all-caps section title.
    We collapse same-name runs to the *last* occurrence (the canonical
    title) and treat that as the segment start. Dedup is by normalized
    name so case variants ("Mirabelle de Lorraine" / "MIRABELLE DE
    LORRAINE") collapse together — without this, the preamble occurrence
    would carve off a tiny segment containing only the homologation
    boilerplate.
    """
    matches = list(CAHIER_HEADER_RE.finditer(text))
    if not matches:
        return {}
    starts: dict[str, int] = {}
    canonical: dict[str, str] = {}
    for m in matches:
        name = m.group(1).strip()
        key = normalize_name(name)
        starts[key] = m.start()
        canonical[key] = name
    ordered = sorted(starts.items(), key=lambda kv: kv[1])
    segments: dict[str, str] = {}
    for i, (key, pos) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(text)
        segments[canonical[key]] = text[pos:end]
    return segments


def find_segment(segments: dict[str, str], target: str) -> str | None:
    """Match by normalized name, falling back to substring contains.

    Cahiers like "Alsace grand cru" carry a single header for 51 individual
    lieux-dits — we accept a substring match in either direction so each
    lieu-dit can re-use the master cahier as its source.
    """
    if not segments:
        return None
    if len(segments) == 1:
        return next(iter(segments.values()))
    target_key = normalize_name(target)
    for name, body in segments.items():
        if normalize_name(name) == target_key:
            return body
    for name, body in segments.items():
        nk = normalize_name(name)
        if target_key in nk or nk in target_key:
            return body
    return None


# IGPs use Arabic-numbered sections (1, 2, 3.1, 3.2, ...) under
# "Chapitre 1 : Dénomination et conditions de production".
IGP_SECTION_HDR_RE = re.compile(
    # Section header in IGP cahiers: "1 Nom de l'IGP" or "1 – Nom..."
    # (post-2020 templates often interpose an en/em dash after the digit).
    rf"^[ \t]*(\d+(?:\.\d+)*)\s*(?:{DASH}\s*)?([A-ZÉÈÀÂÔÎÏÛŸ][\wÀ-ÿ '’\-]{{3,80}})\s*$",
    re.MULTILINE,
)
IGP_CHAPITRE_RE = re.compile(r"^\s*Chapitre\s+\d+\s*:", re.MULTILINE | re.IGNORECASE)


def extract_sections(segment: str) -> tuple[dict[str, str], dict[str, str]]:
    """Slice a single-appellation cahier into Roman-numeral sections.

    Returns (bodies, titles) keyed by the Roman numeral. Titles let
    downstream code route semantic roles (aire / encépagement / lien) by
    keyword rather than fixed numbering — the post-2020 INAO template
    shifted geography from IV to III and encépagement from V to IV, so any
    cahier using the new layout was getting silently mis-parsed.

    The XII-section template repeats inside CHAPITRE II (déclarations) and
    CHAPITRE III (contrôles). We keep only CHAPITRE Ier sections — those
    are the ones consumed by the wiki.
    """
    chapitre_starts = [m.start() for m in CHAPITRE_RE.finditer(segment)]
    body = segment[: chapitre_starts[1]] if len(chapitre_starts) >= 2 else segment

    matches = list(SECTION_HDR_RE.finditer(body))
    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, m in enumerate(matches):
        roman = m.group(1)
        if roman in bodies:
            continue
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        bodies[roman] = body[start:end].strip()
        titles[roman] = title
    return bodies, titles


# Title keywords that identify each semantic role inside a cahier. Match
# is case-insensitive substring on the section title; the first match wins.
SECTION_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    # "Aires et zones dans lesquelles..." or "Aire géographique" — match
    # phrases that imply a commune/parcel zone, not generic mentions of
    # "géographique" (which appears in Champagne's section II,
    # "Dénominations géographiques, mentions complémentaires").
    "aire": ("aires et zones", "aire géographique", "aire geographique"),
    "couleur": ("couleur",),
    "encepagement": ("encépagement", "encepagement"),
    "rendement": ("rendement",),
    "lien": ("lien avec", "lien au terroir"),
    "transformation": ("transformation",),
    "nom": ("nom de l'appellation", "nom de l’appellation"),
}


def route_sections(bodies: dict[str, str], titles: dict[str, str]) -> dict[str, str]:
    """Map semantic role → section body using title keywords.

    Falls back to the legacy fixed-numeral mapping when titles are empty
    or untitled — keeps older cahiers working.
    """
    routed: dict[str, str] = {}
    for role, keywords in SECTION_ROLE_KEYWORDS.items():
        for roman, title in titles.items():
            if any(kw in title.lower() for kw in keywords):
                routed[role] = bodies.get(roman, "")
                break
    # Legacy fallback for the pre-2020 numbering. Only used when title-based
    # routing didn't find a match (e.g. the old template's section II is
    # "Pas de disposition particulière" with no descriptive title).
    if "aire" not in routed:
        routed["aire"] = bodies.get("IV", "")
    if "couleur" not in routed:
        routed["couleur"] = bodies.get("III", "")
    if "encepagement" not in routed:
        routed["encepagement"] = bodies.get("V", "")
    if "lien" not in routed:
        routed["lien"] = bodies.get("X", "")
    return routed


def extract_igp_sections(segment: str) -> dict[str, str]:
    """Slice an IGP cahier into Arabic-numbered sections.

    Format: `1 Nom de l'IGP`, `2 Mentions...`, with subsections like
    `4.1 Zone géographique`. The top-level "4" usually contains nothing
    but a subheader; the real content lives in 4.1 / 4.2. We therefore
    keep both parents and children, and when a parent's body is empty we
    backfill it with the concatenated children so downstream lookups
    (which key on `"4"`) don't see an empty string.
    """
    chapitre_starts = [m.start() for m in IGP_CHAPITRE_RE.finditer(segment)]
    body = segment[: chapitre_starts[1]] if len(chapitre_starts) >= 2 else segment

    matches = list(IGP_SECTION_HDR_RE.finditer(body))
    raw: dict[str, str] = {}
    for i, m in enumerate(matches):
        num = m.group(1)
        if num in raw:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        raw[num] = body[start:end].strip()

    # Backfill sparse parents from their children.
    sections: dict[str, str] = {}
    for num, txt in raw.items():
        if "." in num:
            continue
        if txt and len(txt) > 40:
            sections[num] = txt
            continue
        children = sorted(
            (k for k in raw if k.startswith(num + ".")),
            key=lambda k: [int(p) for p in k.split(".")],
        )
        merged = "\n\n".join(raw[c] for c in children if raw[c])
        sections[num] = merged or txt
    return sections


# Eaux-de-vie / spiritueux cahiers depart from the AOC XII-section template.
# They open with "Partie I : Fiche technique" and use either letter-headed
# (A. − Nom, B. − Description) or arabic-numbered (1. Nom, 2. Description)
# top-level sections. Detection anchors on the Partie I header so we don't
# mis-fire on AOC cahiers that happen to contain enumerated lists.
SPIRITUEUX_PARTIE_I_RE = re.compile(
    r"Partie\s+I\b[\s:\-–—―−]*Fiche\s+technique", re.IGNORECASE
)
SPIRITUEUX_PARTIE_II_RE = re.compile(r"Partie\s+II\b", re.IGNORECASE)
SPIRITUEUX_HDR_LETTER_RE = re.compile(
    rf"^[ \t]*([A-H])\s*\.\s*(?:{DASH}\s*)?([A-ZÉÈÀÂÔÎÏÛŸ][^\n]{{3,90}}?)\s*$",
    re.MULTILINE,
)
SPIRITUEUX_HDR_DIGIT_RE = re.compile(
    rf"^[ \t]*(\d{{1,2}})\s*\.\s*(?:{DASH}\s*)?([A-ZÉÈÀÂÔÎÏÛŸ][^\n]{{3,90}}?)\s*$",
    re.MULTILINE,
)

SPIRITUEUX_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "nom": (
        "nom de l'appellation", "nom de l’appellation",
        "nom et catégorie", "nom et categorie",
    ),
    # "Description de la boisson spiritueuse" — the closest analog to
    # AOC section III (Couleur et types de produit). We route it under
    # "couleur" so derive_summary and downstream renderers consume it
    # transparently.
    "couleur": ("description de la boisson",),
    "aire": (
        "aire géographique", "aire geographique",
        "zone géographique", "zone geographique",
        "définition de l'aire", "définition de l’aire",
        "définition de la zone", "definition de la zone",
    ),
    "lien": (
        "lien à l'origine", "lien à l’origine",
        "lien avec la zone", "lien avec le milieu",
        "éléments corroborant le lien", "elements corroborant le lien",
    ),
}


def is_spiritueux_template(segment: str) -> bool:
    """A spiritueux/eaux-de-vie cahier opens with `Partie I … Fiche technique`."""
    return bool(SPIRITUEUX_PARTIE_I_RE.search(segment[:5000]))


def extract_spiritueux_sections(segment: str) -> tuple[dict[str, str], dict[str, str]]:
    """Slice a spiritueux cahier into top-level Partie-I sections.

    When both letter-headed (A./B./...) and arabic-numbered (1./2./...)
    headers appear, letters are top-level and digits are nested
    subsections — we keep only the level we recognise as top-level.
    """
    m_p1 = SPIRITUEUX_PARTIE_I_RE.search(segment)
    if not m_p1:
        return {}, {}
    m_p2 = SPIRITUEUX_PARTIE_II_RE.search(segment, m_p1.end())
    body = segment[m_p1.end(): m_p2.start() if m_p2 else len(segment)]

    letter_matches = list(SPIRITUEUX_HDR_LETTER_RE.finditer(body))
    if len(letter_matches) >= 3:
        matches = letter_matches
    else:
        matches = list(SPIRITUEUX_HDR_DIGIT_RE.finditer(body))

    bodies: dict[str, str] = {}
    titles: dict[str, str] = {}
    for i, m in enumerate(matches):
        label = m.group(1)
        if label in bodies:
            continue
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        bodies[label] = body[start:end].strip()
        titles[label] = title
    return bodies, titles


def route_spiritueux(bodies: dict[str, str], titles: dict[str, str]) -> dict[str, str]:
    """Map semantic role → spiritueux section body using title keywords."""
    routed: dict[str, str] = {}
    for role, keywords in SPIRITUEUX_ROLE_KEYWORDS.items():
        for label, title in titles.items():
            if any(kw in title.lower() for kw in keywords):
                routed[role] = bodies.get(label, "")
                break
    return routed


def parse_communes(field: str) -> list[str]:
    """Split `Commune A, Commune B et Commune C` into individual tokens.

    Both `, ` and ` et ` separate, but only at top level — `(...)` may
    enclose its own commas and "et"s (e.g. `Le Controis-en-Sologne (pour
    le territoire des communes déléguées de Feings, Fougères-sur-Bièvre
    et Ouchamps)`), and those must stay attached to their commune.
    pdftotext also leaves stray spaces after a soft-wrapped hyphen
    (`Saint-\n Claude-de-Diray` → `Saint- Claude-de-Diray`); we re-glue.
    """
    s = re.sub(r"\s+", " ", field).strip().rstrip(".;")
    s = re.sub(r"-\s+(?=[A-ZÀ-ÿ])", "-", s)
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif depth == 0 and ch == ",":
            tok = "".join(cur).strip()
            if tok:
                out.append(tok)
            cur = []
        elif depth == 0 and s[i : i + 4] == " et ":
            tok = "".join(cur).strip()
            if tok:
                out.append(tok)
            cur = []
            i += 3  # consume " et"; loop's i += 1 takes the trailing space
        else:
            cur.append(ch)
        i += 1
    tok = "".join(cur).strip()
    if tok:
        out.append(tok)
    return out


def extract_aire(section_iv: str) -> dict:
    """Parse section IV. Returns geographique/proximite_immediate commune lists."""
    cog_match = COG_YEAR_RE.search(section_iv)
    cog_year = int(cog_match.group(1)) if cog_match else None

    blocks = re.split(
        r"^\s*(\d°\s*[-–]?\s*[A-Za-zÀ-ÿ][^\n]*)$",
        section_iv,
        flags=re.MULTILINE,
    )
    # blocks: [pre, header1, body1, header2, body2, ...]
    by_block: dict[str, str] = {}
    for i in range(1, len(blocks) - 1, 2):
        by_block[blocks[i].strip()] = blocks[i + 1]

    def by_dept(text: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = defaultdict(list)
        for m in DEPT_HEADER_RE.finditer(text):
            dept = re.sub(r"\s+", " ", m.group("dept")).strip(" '’.,:")
            # `after` captures interstitial context like "sur la base du COG"
            # — we don't need it but we discard it explicitly so a stray
            # comma/period there isn't treated as a commune separator.
            communes_raw = m.group("communes")
            communes_raw = re.split(r"\n\s*\n|\f", communes_raw)[0]
            communes = parse_communes(communes_raw)
            if communes:
                result[dept].extend(communes)
        return dict(result)

    aire_geo_text = next(
        (v for k, v in by_block.items() if "Aire g" in k or "géographique" in k.lower()),
        section_iv,
    )
    aire_prox_text = next(
        (v for k, v in by_block.items() if "proximit" in k.lower()),
        "",
    )

    return {
        "code_officiel_geographique_annee": cog_year,
        "aire_geographique": by_dept(aire_geo_text),
        "aire_proximite_immediate": by_dept(aire_prox_text) if aire_prox_text else {},
    }


def parse_appellation_header(segment: str) -> dict:
    """Pull JORF/decret/arrêté references from the cahier preamble."""
    head = segment[:1500]
    out: dict[str, str] = {}
    m = re.search(
        r"homologu[ée](?:e)?\s+par\s+(?:le|l['’])\s+(d[ée]cret|arr[ée]t[ée])\s*n[°º]?\s*([\d\-/]+)\s+du\s+([^\n,]+?)\s*(?:,\s*JORF|\.|\n)",
        head, re.IGNORECASE,
    )
    if m:
        out["homologation_type"] = m.group(1).lower()
        out["homologation_numero"] = m.group(2)
        out["homologation_date"] = m.group(3).strip()
    m = re.search(r"JORF(?: n[°º]?\s*[\d]+)?\s+du\s+([^\n]+?)(?:\s+page|\s+texte|\.|\n)", head, re.IGNORECASE)
    if m:
        out["jorf_date"] = m.group(1).strip()
    m = re.search(r"modifi[ée](?:e)?\s+par\s+(?:l['’]?arr[êe]t[ée]|le d[ée]cret)\s+du\s+([^\n,]+?)(?:,|\.|\n)", head, re.IGNORECASE)
    if m:
        out["derniere_modification_date"] = m.group(1).strip()
    return out


def extract_one(name: str, text: str) -> dict | None:
    segments = split_bundle(text)
    segment = find_segment(segments, name) if segments else text
    if not segment:
        return None

    if is_spiritueux_template(segment):
        sections, section_titles = extract_spiritueux_sections(segment)
        if not sections:
            return None
        kind = "EDV"
        routed = route_spiritueux(sections, section_titles)
        aire = extract_aire(routed.get("aire", ""))
        lien = routed.get("lien", "")
        return {
            "name": name,
            "kind": kind,
            "header": parse_appellation_header(segment),
            "is_bundle_member": len(segments) > 1,
            "bundle_size": len(segments),
            "sections": sections,
            "section_titles": section_titles,
            "section_roles": routed,
            "aire": aire,
            "lien_au_terroir": lien,
        }

    sections, section_titles = extract_sections(segment)
    kind = "AOC"
    # Some IGP cahiers leak a single Roman "I" via a stray bullet inside the
    # CHAPITRE-1 heading; if the Arabic IGP layout looks more substantial,
    # prefer that. Heuristic: if Arabic returns >= 4 sections, switch.
    igp_sections = extract_igp_sections(segment)
    if len(igp_sections) >= 4 and len(sections) <= 2:
        sections = igp_sections
        section_titles = {}
        kind = "IGP"
    elif not sections:
        sections = igp_sections
        section_titles = {}
        kind = "IGP" if sections else "unknown"
    if not sections:
        return None

    if kind == "AOC":
        routed = route_sections(sections, section_titles)
        aire = extract_aire(routed.get("aire", ""))
        lien = routed.get("lien", "")
    else:
        # IGP layout: aire géographique is usually section 4, terroir lives
        # in a "Lien" section that's typically 7 or 8 depending on the cahier.
        routed = {
            "aire": sections.get("4", ""),
            "couleur": sections.get("3", ""),
            "encepagement": sections.get("5", ""),
            "lien": next((sections.get(k, "") for k in ("8", "7", "9") if sections.get(k)), ""),
        }
        aire = extract_aire(routed["aire"])
        lien = routed["lien"]

    return {
        "name": name,
        "kind": kind,
        "header": parse_appellation_header(segment),
        "is_bundle_member": len(segments) > 1,
        "bundle_size": len(segments),
        "sections": sections,
        "section_titles": section_titles,
        "section_roles": routed,
        "aire": aire,
        "lien_au_terroir": lien,
    }


EMPTY_AIRE = {
    "code_officiel_geographique_annee": "",
    "aire_geographique": {},
    "aire_proximite_immediate": {},
}


def _stub_source(meta: dict | None) -> dict:
    m = meta or {}
    return {
        "filename": m.get("filename", ""),
        "pdf_sha256": m.get("sha256", ""),
        "boagri_url": m.get("boagri_url", ""),
        "boagri_url_candidates": m.get("boagri_url_candidates", []),
        "show_texte_url": m.get("show_texte_url", ""),
        "product_url": m.get("product_url", ""),
        "legifrance_jorftext_ids": m.get("legifrance_jorftext_ids", []),
        "fetched_at": m.get("fetched_at", ""),
        "rescued_from_pdf": "",
        "homologated_at": "",
        "latest_known_pdf": "",
        "latest_known_homologated_at": "",
    }


def _stub_common(name: str, id_app: str, id_denom: str, slug_str: str, meta: dict | None,
                 categories: list[str], stub_reason: str) -> dict:
    m = meta or {}
    return {
        "name": name,
        "kind": "STUB",
        "header": "",
        "is_bundle_member": False,
        "bundle_size": 0,
        "sections": {},
        "section_titles": {},
        "section_roles": {},
        "aire": dict(EMPTY_AIRE),
        "lien_au_terroir": "",
        "id_appellation": id_app,
        "id_denomination_geo": id_denom,
        "slug": slug_str,
        "stub_reason": stub_reason,
        "source": _stub_source(meta),
        "signe_fr": m.get("signe_fr", ""),
        "signe_ue": m.get("signe_ue", ""),
        "categorie": m.get("categorie", ""),
        "categories": categories,
        "comite_regional": m.get("comite_regional", ""),
        "grapes": {"principal": [], "accessory": [], "observation": [], "details": []},
        "styles": [],
    }


def _stub_index_entry(record: dict, parent_slug: str = "") -> dict:
    return {
        "id_appellation": record["id_appellation"],
        "id_denomination_geo": record["id_denomination_geo"],
        "name": record["name"],
        "slug": record["slug"],
        "filename": f"{record['slug']}.json",
        "is_dgc": bool(record.get("is_dgc")),
        "parent_slug": parent_slug,
        "communes_count": 0,
        "sections_present": [],
        "grapes_count": 0,
        "styles": [],
        "categories": record["categories"],
        "stub_reason": record["stub_reason"],
    }


def _emit_parent_stub(id_app: str, parent_denom: dict, parent_slug: str,
                      meta: dict | None, categories: list[str], out_dir: Path) -> dict:
    name = parent_denom["appellation"]
    stub_reason = "no-pdf" if not meta else "no-extract"
    record = _stub_common(name, id_app, parent_denom["id_denomination_geo"],
                          parent_slug, meta, categories, stub_reason)
    record["is_dgc"] = False
    (out_dir / f"{parent_slug}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2)
    )
    return record


def _emit_dgc_stub(id_app: str, parent_denom: dict, parent_slug: str, dgc: dict,
                   meta: dict | None, categories: list[str], out_dir: Path) -> dict:
    dgc_slug = slug(dgc["denomination"])
    stub_reason = "no-pdf" if not meta else "no-extract"
    record = _stub_common(dgc["denomination"], id_app, dgc["id_denomination_geo"],
                          dgc_slug, meta, categories, stub_reason)
    record["is_dgc"] = True
    record["parent_id_appellation"] = id_app
    record["parent_id_denomination_geo"] = parent_denom["id_denomination_geo"]
    record["parent_slug"] = parent_slug
    record["parent_name"] = parent_denom["appellation"]
    (out_dir / f"{dgc_slug}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2)
    )
    return record


def emit_stub_records(
    siqo_denoms: dict[str, list[dict]],
    siqo_categories: dict[str, list[str]],
    manifest: dict,
    index: dict,
    slug_map: dict[str, str],
    out_dir: Path,
) -> int:
    """Emit placeholder JSONs for SIQO denominations stage 02 couldn't
    extract from a cahier — either because stage 01 didn't resolve a PDF
    (`stub_reason="no-pdf"`) or because the resolved PDF didn't contain
    the cahier text (`stub_reason="no-extract"`). Stubs let stage 03
    render a "cahier non disponible" page so every appellation in SIQO
    is at least searchable.

    Stub records share the same schema as extracted ones (so stage 03's
    `_index.json` consumers don't need to special-case them), but their
    `kind == "STUB"`, `aire`/`grapes`/`styles` are empty, and
    `stub_reason` records why they're missing. Re-running stage 01 +
    stage 02 promotes a stub to a full record automatically.
    """
    written = 0
    extracted_app_ids = {entry.get("id_appellation") for entry in index.values()}
    for id_app, denoms in siqo_denoms.items():
        if not denoms:
            continue
        meta = manifest.get(id_app)
        parent_denom = next(
            (d for d in denoms if d["denomination"] == d["appellation"]), denoms[0]
        )
        parent_slug = slug_map.get(id_app) or slug(parent_denom["appellation"])
        categories = siqo_categories.get(id_app, []) or denoms[0]["categories"]

        if id_app not in extracted_app_ids:
            record = _emit_parent_stub(
                id_app, parent_denom, parent_slug, meta, categories, out_dir
            )
            index[parent_denom["id_denomination_geo"] or id_app] = (
                _stub_index_entry(record, parent_slug="")
            )
            written += 1

        for d in denoms:
            if d["denomination"] == d["appellation"]:
                continue
            if d["id_denomination_geo"] in index:
                continue
            dgc_categories = d["categories"] or categories
            record = _emit_dgc_stub(
                id_app, parent_denom, parent_slug, d, meta, dgc_categories, out_dir
            )
            index[d["id_denomination_geo"]] = _stub_index_entry(record, parent_slug)
            written += 1
    return written


# Each cahier carries its homologation date next to the title in one of
# three forms:
#   "homologué par le décret n°2011-1724 du 30 novembre 2011"
#   "homologué par l'arrêté du 30 novembre 2011"
#   "homologué par le décret n°2011-1724 du 30/11/2011"
# We extract that date so the cross-bundle rescue can pick the most
# recent cahier when the same AOC appears in multiple PDFs (an older
# JORF homologation + a later modification arrêté re-publishing the
# updated cahier). Stored as ISO YYYY-MM-DD; missing dates compare last.
_FR_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
}
_HOMOL_LONG_RE = re.compile(
    r"homologu[ée]\s+par\s+(?:le\s+d[ée]cret|l['’]arr[êe]t[ée])\s+"
    r"(?:n[°º]?\s*\S+\s+)?du\s+(\d{1,2})\s+"
    r"(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|"
    r"septembre|octobre|novembre|d[ée]cembre)\s+(\d{4})",
    re.IGNORECASE,
)
_HOMOL_NUMERIC_RE = re.compile(
    r"homologu[ée]\s+par\s+(?:le\s+d[ée]cret|l['’]arr[êe]t[ée])\s+"
    r"(?:n[°º]?\s*\S+\s+)?du\s+(\d{1,2})[\s/-](\d{1,2})[\s/-](\d{4})",
    re.IGNORECASE,
)


def homologation_date(segment: str) -> str | None:
    """Best-effort ISO YYYY-MM-DD for the homologation date stamped in a
    cahier segment. Returns None when no date can be parsed."""
    head = segment[:1500]
    m = _HOMOL_LONG_RE.search(head)
    if m:
        day = int(m.group(1))
        month = _FR_MONTHS.get(m.group(2).lower().replace("é", "e").replace("û", "u"))
        year = int(m.group(3))
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"
    m = _HOMOL_NUMERIC_RE.search(head)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def build_global_segment_index(
    cahiers_dir: Path,
) -> dict[str, tuple[str, str, str]]:
    """Scan every PDF in `cahiers_dir`, bundle-split it, and return a dict
    mapping normalised cahier name → (pdf_filename, segment_text, date_iso).

    INAO routinely lands an appellation on a "modification arrêté" PDF that
    doesn't actually carry the cahier we want — but a sibling AOC's PDF
    often does (BO Agri JORF issues bundle many cahiers). One pass over
    the corpus lets us rescue those cases by matching the cahier header
    name across PDFs. Scanning the directory (not just the manifest)
    means PDFs that stage 01 fetched as fallback candidates also feed
    the rescue index.

    When the same cahier name appears in multiple PDFs (the same cahier
    text often gets re-published in subsequent modification arrêtés), we
    keep the entry with the latest homologation date — the most recent
    publication is authoritative. Entries with no parsable date sort
    earliest, so any dated entry beats them.
    """
    index: dict[str, tuple[str, str, str]] = {}
    for pdf_path in sorted(cahiers_dir.glob("*.pdf")):
        try:
            text = pdftotext(pdf_path)
        except subprocess.CalledProcessError:
            continue
        for header_name, segment in split_bundle(text).items():
            key = normalize_name(header_name)
            date_iso = homologation_date(segment) or ""
            existing = index.get(key)
            if existing is None or date_iso > existing[2]:
                index[key] = (pdf_path.name, segment, date_iso)
    return index


def _disambiguate_slugs(items: list[tuple[str, dict]]) -> dict[str, str]:
    """Map id_appellation → unique slug for *parent* denominations.

    Multiple SIQO entries can share an appellation name — e.g. id=330 is
    the AOC eau-de-vie "Calvados" and id=888 is the IGP "Vin tranquille"
    "Calvados". Both naïvely slugify to `calvados`, so the second-written
    JSON would clobber the first. We pre-scan for base-slug collisions
    and disambiguate every member of a colliding set with a short
    categorie-derived suffix (`-spiritueux`, `-vin`, `-mousseux`),
    falling back to the SIQO id when categorie doesn't separate them.
    """
    base = {id_app: slug(meta["name"]) for id_app, meta in items}
    by_slug: dict[str, list[str]] = defaultdict(list)
    for id_app, s in base.items():
        by_slug[s].append(id_app)
    out: dict[str, str] = {}
    meta_by_id = dict(items)
    for s, ids in by_slug.items():
        if len(ids) == 1:
            out[ids[0]] = s
            continue
        used: set[str] = set()
        for id_app in ids:
            cat = (meta_by_id[id_app].get("categorie") or "").lower()
            if "eau-de-vie" in cat or "eaux-de-vie" in cat or "spiritueuse" in cat or "spiritueux" in cat:
                disc = "spiritueux"
            elif "mousseux" in cat or "effervescent" in cat:
                disc = "mousseux"
            elif "tranquille" in cat or cat.startswith("vin"):
                disc = "vin"
            elif "doux naturel" in cat or "vdn" in cat:
                disc = "vdn"
            else:
                disc = id_app
            candidate = f"{s}-{disc}"
            if candidate in used:
                candidate = f"{s}-{id_app}"
            used.add(candidate)
            out[id_app] = candidate
    return out


WINE_SIGNS = {"AOC", "AOP", "IGP"}


def load_siqo_denominations() -> dict[str, list[dict]]:
    """Group SIQO rows by id_appellation → [denominations].

    Each denomination is `{id_denomination_geo, denomination, appellation,
    categories: [..]}`. The same `id_denomination_geo` can appear several
    times (one row per produit); we collapse to one entry per
    id_denomination_geo and union the `categorie` values across rows.

    Filters: VITICOLE sector, AOC/AOP/IGP signs, état "Publié" — same
    filters stage 01 applied when building the cahier manifest.
    """
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    if not SIQO_CSV.exists():
        return {}
    with SIQO_CSV.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["secteur"].strip() != "VITICOLE":
                continue
            if row["lib_etat"].strip() != "Publié":
                continue
            sign = row["signe_fr"].strip() or row["signe_ue"].strip()
            if sign not in WINE_SIGNS:
                continue
            id_app = row["id_appellation"].strip()
            id_denom = row["id_denomination_geo"].strip()
            if not id_denom:
                continue
            denom = row["denomination"].strip()
            app = row["appellation"].strip()
            cat = row["categorie"].strip()
            entry = out[id_app].setdefault(
                id_denom,
                {
                    "id_denomination_geo": id_denom,
                    "denomination": denom,
                    "appellation": app,
                    "categories": set(),
                },
            )
            if cat:
                entry["categories"].add(cat)
    # Flatten + sort: parent denomination (denomination == appellation) first,
    # then DGCs alphabetically. The parent ordering matters for slug
    # collision handling — when a DGC's denomination_slug happens to clash
    # with another row, we want the parent to keep the canonical slug.
    flat: dict[str, list[dict]] = {}
    for id_app, denoms in out.items():
        items: list[dict] = []
        for d in denoms.values():
            d["categories"] = sorted(d["categories"])
            items.append(d)
        items.sort(
            key=lambda d: (d["denomination"] != d["appellation"], d["denomination"].lower())
        )
        flat[id_app] = items
    return flat


def load_siqo_categories() -> dict[str, list[str]]:
    """Map id_appellation → sorted list of distinct `categorie` values.

    Each appellation in the SIQO referentiel can carry several rows, one
    per (categorie, denomination_geo). The manifest collapses them to a
    single value, which loses information for AOCs that produce more than
    one wine type (Champagne: tranquille + mousseux, Maury: VDN +
    tranquille, etc.). We re-derive the full set here.
    """
    out: dict[str, set[str]] = defaultdict(set)
    if not SIQO_CSV.exists():
        return {}
    with SIQO_CSV.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            id_app = (row.get("id_appellation") or "").strip()
            cat = (row.get("categorie") or "").strip()
            if id_app and cat:
                out[id_app].add(cat)
    return {k: sorted(v) for k, v in out.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[], help="appellation name substring (repeatable)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if shutil.which("pdftotext") is None:
        print("error: pdftotext not on PATH (brew install poppler)", file=sys.stderr)
        return 1

    if not MANIFEST_PATH.exists():
        print(f"error: {MANIFEST_PATH} missing — run scripts/01_scrape_cahiers.py first", file=sys.stderr)
        return 1

    manifest = json.loads(MANIFEST_PATH.read_text())
    siqo_categories = load_siqo_categories()
    siqo_denoms = load_siqo_denominations()
    # Skip manifest entries with no filename — stage 01 may record an entry
    # for an AOC whose only source is a Légifrance JORFTEXT (Cloudflare-walled
    # so we couldn't download a PDF). The stub-emission pass at the end
    # picks those up by id_appellation.
    items = sorted(
        ((k, v) for k, v in manifest.items() if v.get("filename")),
        key=lambda kv: kv[1]["name"].lower(),
    )
    if args.only:
        needles = [s.lower() for s in args.only]
        items = [(k, v) for k, v in items if any(n in v["name"].lower() for n in needles)]
    if args.limit:
        items = items[: args.limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    extracted = no_segment = no_sections = errors = dgc_emitted = rescued = 0
    global_segments = build_global_segment_index(CAHIERS)

    # Pre-compute disambiguated slugs so name collisions (e.g. AOC spirit
    # "Calvados" vs IGP wine "Calvados") don't overwrite each other on
    # disk. Suffix colliding entries with a categorie-derived hint
    # (`-spiritueux`, `-vin`, `-mousseux`) so the resulting filenames
    # stay readable; fall back to the SIQO id when categorie doesn't
    # disambiguate.
    slug_map = _disambiguate_slugs(items)

    for id_app, meta in tqdm(items, desc="extract", leave=False):
        pdf_path = CAHIERS / meta["filename"]
        if not pdf_path.exists():
            print(f"[skip] {meta['name']}: missing {pdf_path.name}", file=sys.stderr)
            errors += 1
            continue

        try:
            text = pdftotext(pdf_path)
        except subprocess.CalledProcessError as exc:
            print(f"[fail] {meta['name']}: pdftotext: {exc}", file=sys.stderr)
            errors += 1
            continue

        record = extract_one(meta["name"], text)
        rescue_pdf: str | None = None
        rescue_date: str = ""
        if record is None:
            rescue = global_segments.get(normalize_name(meta["name"]))
            if rescue and rescue[0] != meta["filename"]:
                rescue_pdf, rescue_segment, rescue_date = rescue
                record = extract_one(meta["name"], rescue_segment)
                if record is not None:
                    print(
                        f"[rescue] {meta['name']} ({id_app}) "
                        f"-> segment from {rescue_pdf[:16]} "
                        f"({rescue_date or 'no-date'})",
                        file=sys.stderr,
                    )
                    rescued += 1
        if record is None:
            segments = split_bundle(text)
            if not segments:
                print(f"[no-sections] {meta['name']} ({id_app})", file=sys.stderr)
                no_sections += 1
            else:
                print(
                    f"[no-segment] {meta['name']} ({id_app}) not in bundle of "
                    f"{len(segments)}: {sorted(segments)[:3]}...",
                    file=sys.stderr,
                )
                no_segment += 1
            continue

        record["id_appellation"] = id_app
        record["slug"] = slug_map[id_app]
        source_filename = rescue_pdf or meta["filename"]
        source_sha = (
            rescue_pdf.removesuffix(".pdf") if rescue_pdf else meta["sha256"]
        )
        # Date the cahier we ended up using. Rescue path already carries
        # the homologation date from build_global_segment_index; for the
        # assigned-PDF path we re-split and parse the segment we used.
        # Stored as ISO YYYY-MM-DD; downstream consumers (wiki/map) can
        # surface it as "Cahier homologué le …" and use it to detect
        # when a newer publication exists for the same AOC.
        if rescue_pdf:
            homologated_at = rescue_date
        else:
            seg_for_date = find_segment(split_bundle(text), meta["name"]) or text
            homologated_at = homologation_date(seg_for_date) or ""
        latest_known = global_segments.get(normalize_name(meta["name"]))
        latest_pdf = latest_known[0] if latest_known else ""
        latest_date = latest_known[2] if latest_known else ""
        record["source"] = {
            "filename": source_filename,
            "pdf_sha256": source_sha,
            "boagri_url": meta["boagri_url"],
            "show_texte_url": meta["show_texte_url"],
            "product_url": meta["product_url"],
            "fetched_at": meta["fetched_at"],
            "rescued_from_pdf": rescue_pdf or "",
            "homologated_at": homologated_at,
            "latest_known_pdf": latest_pdf,
            "latest_known_homologated_at": latest_date,
        }
        record["signe_fr"] = meta.get("signe_fr", "")
        record["signe_ue"] = meta.get("signe_ue", "")
        record["categorie"] = meta.get("categorie", "")
        record["categories"] = siqo_categories.get(id_app, [])
        record["comite_regional"] = meta.get("comite_regional", "")

        # Pull encépagement + couleur from the routed section map (handles
        # both the old template — V/III — and the post-2020 template where
        # encépagement is IV and couleur is II). Spiritueux/eaux-de-vie
        # cahiers (kind=EDV) don't carry an encépagement section, and their
        # "Description de la boisson" doesn't yield wine-style colours, so
        # we skip both parsers and emit empty results.
        roles = record.get("section_roles") or {}
        if record["kind"] == "EDV":
            record["grapes"] = {"principal": [], "accessory": [], "observation": [], "details": []}
            record["styles"] = []
        else:
            v_text = roles.get("encepagement") or ""
            iii_text = roles.get("couleur") or ""
            grapes = parse_grapes(v_text)
            record["grapes"] = {
                "principal": [t["slug"] for t in grapes["principal"]],
                "accessory": [t["slug"] for t in grapes["accessory"]],
                "observation": [t["slug"] for t in grapes["observation"]],
                "details": grapes["all"],
            }
            record["styles"] = parse_styles(iii_text, record["categories"])

        # The parent record is everything we just built. Find its SIQO row to
        # carry id_denomination_geo through, then emit one JSON per
        # denomination (parent + DGCs). Parent denomination = the SIQO row
        # whose `denomination == appellation`. DGCs reuse parent sections /
        # aire / grapes / styles — the cahier text is shared, and parsing
        # DGC-specific sub-sections is out of scope for v1.
        denoms = siqo_denoms.get(id_app, [])
        parent_denom = next(
            (d for d in denoms if d["denomination"] == d["appellation"]), None
        )
        if parent_denom is None and denoms:
            # No parent row in SIQO (rare): treat the first denomination as
            # the parent so the appellation still gets a canonical page.
            parent_denom = denoms[0]
        if parent_denom is not None:
            record["id_denomination_geo"] = parent_denom["id_denomination_geo"]

        out_path = OUT_DIR / f"{record['slug']}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2),encoding="utf-8")
        index[record.get("id_denomination_geo") or id_app] = {
            "id_appellation": id_app,
            "id_denomination_geo": record.get("id_denomination_geo") or "",
            "name": meta["name"],
            "slug": record["slug"],
            "filename": out_path.name,
            "is_dgc": False,
            "parent_slug": "",
            "communes_count": sum(len(v) for v in record["aire"]["aire_geographique"].values()),
            "sections_present": sorted(record["sections"]),
            "grapes_count": len(record["grapes"]["details"]),
            "styles": record["styles"],
            "categories": record["categories"],
        }
        extracted += 1

        # DGCs of this appellation: emit one JSON per id_denomination_geo
        # whose denomination differs from the appellation name. They share
        # the parent's cahier source, sections, aire, grapes, and styles —
        # but each gets its own slug, name, and parent_* link so the wiki
        # and map can render them independently. SIQO sometimes attaches a
        # narrower categorie set to a DGC (e.g. some Côtes du Rhône Villages
        # entries are tranquille-only); we use the DGC-level categorie list
        # when it's a strict subset, else fall back to the parent's.
        for d in denoms:
            if d["denomination"] == d["appellation"]:
                continue
            dgc_slug = slug(d["denomination"])
            dgc_name = d["denomination"]
            dgc_record = json.loads(json.dumps(record))  # deep copy
            dgc_record["name"] = dgc_name
            dgc_record["slug"] = dgc_slug
            dgc_record["id_denomination_geo"] = d["id_denomination_geo"]
            dgc_record["is_dgc"] = True
            dgc_record["parent_id_appellation"] = id_app
            dgc_record["parent_id_denomination_geo"] = (
                parent_denom["id_denomination_geo"] if parent_denom else ""
            )
            dgc_record["parent_slug"] = record["slug"]
            dgc_record["parent_name"] = record["name"]
            dgc_categories = d["categories"] or record["categories"]
            dgc_record["categories"] = dgc_categories

            dgc_path = OUT_DIR / f"{dgc_slug}.json"
            dgc_path.write_text(json.dumps(dgc_record, ensure_ascii=False, indent=2), encoding="utf-8")
            index[d["id_denomination_geo"]] = {
                "id_appellation": id_app,
                "id_denomination_geo": d["id_denomination_geo"],
                "name": dgc_name,
                "slug": dgc_slug,
                "filename": dgc_path.name,
                "is_dgc": True,
                "parent_slug": record["slug"],
                "communes_count": sum(len(v) for v in dgc_record["aire"]["aire_geographique"].values()),
                "sections_present": sorted(dgc_record["sections"]),
                "grapes_count": len(dgc_record["grapes"]["details"]),
                "styles": dgc_record["styles"],
                "categories": dgc_categories,
            }
            dgc_emitted += 1

    stubs = emit_stub_records(
        siqo_denoms, siqo_categories, manifest, index, slug_map, OUT_DIR
    )

    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True))
    print(
        f"[done] extracted={extracted} dgcs={dgc_emitted} rescued={rescued} "
        f"stubs={stubs} no-segment={no_segment} no-sections={no_sections} "
        f"errors={errors}",
        file=sys.stderr,
    )
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
