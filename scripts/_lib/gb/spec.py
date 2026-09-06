"""Parsers for the three UK wine product-specification layouts.

Unlike the EUR-Lex countries, the UK register does not publish one
template — the six specifications come in three shapes, because they
were written under three different regimes:

1. **`defra-pfn-2011`** — the four December-2011 DEFRA specifications
   (English PDO, Welsh PDO, English Regional PGI, Welsh Regional PGI).
   A header block::

       PROTECTED NAME:            ENGLISH
       DEMARCATION:               ENGLAND

   then one `PART n: <WINE CATEGORY>` block per grapevine category
   (`STILL WINE`, `QUALITY SPARKLING WINE`, and a closing `GENERAL
   PROVISIONS` part that carries no wine). Each wine part opens with the
   link narrative — latitude, growing season, diurnal range, acidity —
   followed by `SPECIFICATION` and a run of upper-case subsections, of
   which `VINE VARIETIES` and `MAXIMUM YIELDS` are the ones we read.
   The still-wine variety roster is semicolon-separated; the sparkling
   one is a short line-per-variety list.

2. **`defra-pfn-application`** — Darnibole, the 2017 single-vineyard
   PDO, filed on the EU application form: a numbered outline (`1. Details
   of protection` … `7. Demarcated area`) with lettered sub-items. It has
   **no link/terroir section** — the file stops after the demarcated area
   and its plan — so the terroir narrative is taken from `7 b) Definition
   of the demarcated area`, which is where the slate subsoil, the slope
   and the aspect are actually described.

3. **`uk-gi-single-document`** — Sussex, the only registration made under
   the post-Brexit UK scheme (2022). A numbered EU-style single document
   (`1. Applicant(s)` … `13. Inspection and certification`) with a proper
   `9. Link` section carrying `9.1` natural + human factors, `9.2`
   characteristics and `9.3` the causal link. Varieties live in
   `7.2 Viticulture practices`, listed separately for sparkling and still.

All three are Open Government Licence v3.0, © Crown copyright.

Every UK specification lists varieties as a flat roster with no
principal/accessory split (the same shape as PT/IT/HR/BG/SK), so stage 02
resolves every match as `principal`.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------- shared

# `PART 2: QUALITY SPARKLING WINE` → the shared style-taxonomy slug.
# Order matters: the most specific pattern must win, so "QUALITY
# SPARKLING WINE" is tested before the bare "SPARKLING WINE".
PART_STYLE_MARKERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"quality\s+sparkling\s+wine", re.I), "sparkling-quality"),
    (re.compile(r"semi[\s-]?sparkling|pearl\s+wine", re.I), "semi-sparkling"),
    (re.compile(r"sparkling\s+wine", re.I), "sparkling"),
    (re.compile(r"liqueur\s+wine", re.I), "vin-de-liqueur"),
    (re.compile(r"\bstill\s+wine", re.I), ""),  # colour comes from the grapes
)

COLOUR_BY_KEYWORD: dict[str, str] = {
    "red wine": "red", "red wines": "red",
    "white wine": "white", "white wines": "white",
    "rosé wine": "rose", "rose wine": "rose", "rosé wines": "rose",
    "rosé": "rose",
}

# Section titles that are never a variety roster, guarding the loose
# keyword match used by the numbered templates.
_GRAPE_TITLE_BLOCKLIST = ("proof of origin", "labelling", "inspection")

# Boilerplate lines inside a variety block.
_GRAPE_LINE_DROP = (
    "shall be made from the following",
    "the following grape varieties",
    "permitted grape vine varieties",
    "vine varieties",
    "grape varieties",
    "grape variety",
    "the vineyard owner must keep",
    "are permitted within",
)

# Real typos in the source documents. The corpus rule is to fold source
# typos rather than hand-edit the regulator's text (see the INAO cahier
# precedent) — but these two are *structural*: a stray comma and a line
# break split one variety name into two, which no grape-alias entry can
# repair because the fragments are separate candidates by then.
#   - Sussex §7.2 still-wine roster reads "… Pinot Noir, Pinot Noir,
#     Précoce, Regent …" for "Pinot Noir, Pinot Noir Précoce, Regent".
#   - The same roster hyphenates across a line break: "Müller- Thurgau".
_SOURCE_TYPO_REPAIRS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"Pinot\s+Noir\s*,\s*Précoce", re.I), "Pinot Noir Précoce"),
    (re.compile(r"Müller-\s+Thurgau", re.I), "Müller-Thurgau"),
    #   - The DEFRA rosters run alphabetically (… Gamaret; Gamay;
    #     Garanoir; Gewurztraminer …) but drop the semicolon between
    #     Gamay and Garanoir, merging two Swiss-crossing entries into one.
    (re.compile(r"\bGamay\s+Garanoir\b", re.I), "Gamay; Garanoir"),
)


def repair_source_typos(text: str) -> str:
    for pattern, replacement in _SOURCE_TYPO_REPAIRS:
        text = pattern.sub(replacement, text)
    return text


def normalise_text(text: str) -> str:
    """Fold form feeds to newlines and squeeze intra-line whitespace.

    `pdftotext -layout` emits a form feed at every page break; a section
    that starts immediately after one would otherwise not match a
    line-anchored header regex.
    """
    text = text.replace("\x0c", "\n").replace("’", "'").replace("“", '"')
    text = text.replace("”", '"').replace("„", '"').replace("‚", "'")
    lines = [re.sub(r"[ \t\r\v]+", " ", ln).rstrip() for ln in text.splitlines()]
    return "\n".join(lines)


def _clean_block(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines()]
    out = [ln for ln in lines if ln]
    return "\n".join(out).strip()


# ------------------------------------------------- template 1: DEFRA 2011

_HEADER_FIELD_RE = re.compile(
    r"^\s*(PROTECTED NAME|DEMARCATION)\s*:\s*(.+?)\s*$", re.M)
_PART_RE = re.compile(r"^\s*PART\s+(\d+)\s*:\s*(.+?)\s*$", re.M)

# An upper-case subsection header inside a PART. Allows the trailing
# "…: 80 hl/ha" value form of MAXIMUM YIELDS, and the two-line wrap that
# `MINIMUM NATURAL, ACTUAL AND TOTAL ALCOHOLIC STRENGTHS AND\nENRICHMENT`
# produces, by matching each physical line independently.
_UPPER_HEADER_RE = re.compile(
    r"^(?P<title>[A-Z][A-Z0-9 ,\-/&\.\(\)']{3,}?)\s*(?::\s*(?P<value>.*))?$")


def _is_upper_header(line: str) -> bool:
    s = line.strip()
    if len(s) < 4 or s.startswith(("-", "(", "\u2022", "\uf0b7")):
        return False
    head = s.split(":", 1)[0]
    letters = [c for c in head if c.isalpha()]
    if len(letters) < 3:
        return False
    if any(c.islower() for c in letters):
        return False
    # A wrapped sentence in caps is still a header here; a bullet is not.
    return bool(_UPPER_HEADER_RE.match(s))


def parse_defra_pfn_2011(text: str) -> dict:
    """Parse a December-2011 DEFRA product specification."""
    text = normalise_text(text)
    fields = {m.group(1).lower().replace(" ", "_"): m.group(2).strip()
              for m in _HEADER_FIELD_RE.finditer(text)}

    parts: list[dict] = []
    matches = list(_PART_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end]
        parts.append({"num": m.group(1), "title": m.group(2).strip(), "body": body})

    varieties: list[str] = []
    yields: list[str] = []
    narratives: list[str] = []
    part_titles: list[str] = []

    for part in parts:
        title = part["title"]
        if "GENERAL PROVISIONS" in title.upper():
            continue
        part_titles.append(title)
        body = part["body"]
        # The link narrative is everything before the SPECIFICATION marker.
        spec_split = re.split(r"^\s*SPECIFICATION\s*$", body, maxsplit=1, flags=re.M)
        narrative = _clean_block(spec_split[0])
        if narrative:
            narratives.append(f"{title.title()}\n{narrative}")
        subsections = _split_upper_sections(spec_split[1] if len(spec_split) > 1 else "")
        for stitle, sbody in subsections:
            up = stitle.upper()
            if up.startswith("VINE VARIETIES"):
                varieties.append(sbody)
            elif up.startswith("MAXIMUM YIELD"):
                value = sbody.strip() or stitle.split(":", 1)[-1].strip()
                yields.append(f"{title.title()}: {value}" if value else "")

    return {
        "template": "defra-pfn-2011",
        "protected_name": fields.get("protected_name", ""),
        "demarcation": fields.get("demarcation", ""),
        "part_titles": part_titles,
        "roles": {
            "geo_area": fields.get("demarcation", ""),
            # Blank-line separated: each PART's roster is its own run, so
            # the last name of one ("… Zweigeltrebe") is never joined to
            # the first of the next ("Acolon …") as a line wrap.
            "grape_varieties": "\n\n".join(v for v in varieties if v),
            "link_to_terroir": "\n\n".join(narratives),
            "description": narratives[0] if narratives else "",
            "yields": "\n".join(y for y in yields if y),
        },
    }


def _split_upper_sections(text: str) -> list[tuple[str, str]]:
    """Split a SPECIFICATION body on its upper-case subsection headers."""
    lines = text.splitlines()
    marks: list[tuple[int, str]] = [
        (i, ln.strip()) for i, ln in enumerate(lines) if _is_upper_header(ln)
    ]
    out: list[tuple[str, str]] = []
    for j, (idx, title) in enumerate(marks):
        end = marks[j + 1][0] if j + 1 < len(marks) else len(lines)
        inline = title.split(":", 1)[1].strip() if ":" in title else ""
        body = "\n".join(lines[idx + 1:end])
        out.append((title, _clean_block(f"{inline}\n{body}" if inline else body)))
    return out


# --------------------------------------- templates 2+3: numbered outlines

# `3. Product details`, `7 a). NUTS Area`, `9.1 Details of the …`
_NUM_HEADER_RE = re.compile(
    r"^\s*(?P<num>\d+(?:\s*[a-z]\))?(?:\.\d+)*)\s*[\.\)]?\s+(?P<title>[A-Za-z][^\n]*?)\s*:?\s*$"
)
# `a) Category`, `b) Description`, `c) Analytic characteristics:`
_ALPHA_HEADER_RE = re.compile(r"^\s*(?P<num>[a-z])\)\s*(?P<title>[A-Za-z][^\n]*?)\s*:?\s*$")


def _split_numbered(text: str) -> list[tuple[str, str, str]]:
    """Return [(number, title, body)] for a numbered/lettered outline."""
    lines = text.splitlines()
    marks: list[tuple[int, str, str]] = []
    for i, ln in enumerate(lines):
        m = _NUM_HEADER_RE.match(ln) or _ALPHA_HEADER_RE.match(ln)
        if not m:
            continue
        title = m.group("title").strip()
        # Analytical rows ("1. Actual and Total Alcoholic Strengths: …")
        # and prose sentences are not headers.
        if len(title) > 90 or title.endswith((".", ",")):
            continue
        marks.append((i, re.sub(r"\s+", "", m.group("num")), title))
    out: list[tuple[str, str, str]] = []
    for j, (idx, num, title) in enumerate(marks):
        end = marks[j + 1][0] if j + 1 < len(marks) else len(lines)
        out.append((num, title, _clean_block("\n".join(lines[idx + 1:end]))))
    return out


def _pick(sections: list[tuple[str, str, str]], keywords: tuple[str, ...],
          blocklist: tuple[str, ...] = ()) -> str:
    for kw in keywords:
        for _num, title, body in sections:
            tlow = title.lower()
            if kw not in tlow or any(b in tlow for b in blocklist):
                continue
            if body.strip():
                return body
    return ""


def _pick_with_children(sections: list[tuple[str, str, str]],
                        keywords: tuple[str, ...]) -> str:
    """Section body plus every `n.x` child — Sussex's `9. Link` is an
    empty header whose content is entirely in 9.1 / 9.2 / 9.3."""
    for kw in keywords:
        for num, title, body in sections:
            if kw not in title.lower():
                continue
            chunks = [body] if body.strip() else []
            for cnum, ctitle, cbody in sections:
                if cnum.startswith(f"{num}.") and cbody.strip():
                    chunks.append(f"{ctitle}\n{cbody}")
            if chunks:
                return "\n\n".join(chunks)
    return ""


def parse_numbered_spec(text: str, template: str) -> dict:
    """Parse Darnibole's application form or Sussex's single document."""
    text = normalise_text(text)
    sections = _split_numbered(text)

    demarcation = ""
    m = re.search(r"^\s*Demarcation\s*:\s*(.+?)\s*$", text, re.M | re.I)
    if m:
        demarcation = m.group(1).strip()

    geo_area = _pick(sections, (
        "definition of the demarcated area", "demarcated area",
        "geographical area", "delimited area",
    ))
    link = _pick_with_children(sections, (
        "link between the characteristics", "link", "details of the geographical area",
    ))
    # Darnibole has no link section at all: its terroir narrative — ancient
    # slate subsoil, the steep south-facing slope, the thermal band — is in
    # the demarcated-area definition.
    if not link:
        link = geo_area
    grapes = _pick(sections, (
        "viticulture practices", "wine grape variety", "grape variety",
        "grape varieties", "vine variet",
    ), _GRAPE_TITLE_BLOCKLIST)
    description = _pick_with_children(sections, (
        "description of the wine", "description",
    ))
    yields = _pick(sections, ("maximum yield", "harvest yield"))
    categories = _pick(sections, ("category of the grapevine products", "category"))

    return {
        "template": template,
        "protected_name": _pick(sections, ("name of product to be registered",
                                           "name(s) to be registered")),
        # Parenthesised deliberately: without it Python binds the
        # conditional to the whole `or` expression, so an explicitly
        # stated "Demarcation:" line is discarded whenever the area
        # section happens to be empty.
        "demarcation": demarcation or (geo_area.splitlines()[0] if geo_area else ""),
        "part_titles": [ln.strip() for ln in categories.splitlines() if ln.strip()],
        "roles": {
            "geo_area": geo_area,
            "grape_varieties": grapes,
            "link_to_terroir": link,
            "description": description,
            "yields": yields,
        },
    }


# ------------------------------------------------------------- dispatcher

def detect_template(text: str) -> str:
    head = normalise_text(text)[:4000]
    if _HEADER_FIELD_RE.search(head) and _PART_RE.search(normalise_text(text)):
        return "defra-pfn-2011"
    if re.search(r"^\s*1\.\s*Details of protection", head, re.M | re.I):
        return "defra-pfn-application"
    return "uk-gi-single-document"


def parse_spec(text: str) -> dict:
    template = detect_template(text)
    if template == "defra-pfn-2011":
        return parse_defra_pfn_2011(text)
    return parse_numbered_spec(text, template)


# ------------------------------------------------------------ grape lines

_ITEM_SPLIT_RE = re.compile(r"[;\n]|,(?![^()]*\))|\s+and\s+(?=[A-Z])")

# "Permitted Grape Vine Varieties: Chardonnay, Pinot Noir, …" — the roster
# starts after the label, on the same line.
_ROSTER_LABEL_RE = re.compile(
    r"^.*?(?:permitted grape vine varieties|shall be made from the following"
    r"|are permitted within[^:]*|following grape varieties)\s*:?\s*", re.I)
# "100% Bacchus." — Darnibole states its single variety as a proportion.
_PROPORTION_RE = re.compile(r"^\s*\d+(?:[.,]\d+)?\s*%\s*")


def _strip_bullet(line: str) -> str:
    """Drop a leading list bullet. `pdftotext` renders the Wingdings
    bullet the DEFRA specifications use as U+F0B7 (private-use area)."""
    return re.sub(r"^[\s\u2022\u00b7\uf0b7\-\u2013]+", "", line).strip()


def _looks_like_roster(line: str) -> bool:
    """True when a line is a list of variety names rather than prose.

    Every UK roster is a run of short names; the surrounding prose ("The
    vineyard owner must keep detailed records of yield and size of each
    parcel…") is long-winded even where it contains commas. Judging by
    the *shape* of the split items keeps both apart without needing a
    per-document rule.
    """
    stripped = _ROSTER_LABEL_RE.sub("", _strip_bullet(line), count=1)
    items = [i.strip(" .;,:") for i in _ITEM_SPLIT_RE.split(stripped)]
    items = [i for i in items if i]
    if not items:
        return False
    short = [i for i in items if len(i) <= 40 and len(i.split()) <= 4]
    if len(items) == 1:
        # A one-per-line sparkling roster ("Chardonnay") or "100% Bacchus".
        only = _PROPORTION_RE.sub("", items[0])
        return bool(short) and bool(re.match(r"^[A-Z\u00c0-\u00dc]", only))
    return len(short) / len(items) >= 0.75


def _roster_runs(text: str) -> list[str]:
    """Group contiguous roster lines into runs and rejoin each correctly.

    A roster wrapped across lines by the PDF layout ("… Black Hamburg;
    Blau\nPortugueser; Blauburger …") must be joined with a *space*, or
    the wrap splits "Blau Portugueser" into two varieties. A roster
    written one-name-per-line (the bulleted sparkling lists) has no
    separators at all, so its lines must be joined with a *separator*
    instead. Which of the two a run is gets decided by whether its lines
    actually carry `;` / `,`.
    """
    runs: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if _looks_like_roster(line):
            current.append(_ROSTER_LABEL_RE.sub("", _strip_bullet(line), count=1))
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)

    out: list[str] = []
    for run in runs:
        separated = sum(1 for ln in run if ";" in ln or "," in ln)
        joiner = " " if separated * 2 >= len(run) else "; "
        out.append(joiner.join(run))
    return out


def grape_candidates(section_text: str) -> list[str]:
    """Split a UK variety roster into individual candidate names.

    The still-wine rosters are semicolon-separated and run to ~85 names;
    the sparkling ones are bulleted one-per-line; Sussex's are
    comma-separated with a trailing "X and Y". Parenthesised synonym
    tails — "Fruhburgunder (Pinot Noir Precoce)", "Rulander (Synonyms:
    Pinot Gris, Pinot Grigio)" — are stripped, since the head name is the
    one the regulator authorises. Prose lines are skipped entirely, so
    the record-keeping and yield-dispensation paragraphs around Sussex's
    two rosters never reach the matcher.
    """
    text = repair_source_typos(section_text or "")
    out: list[str] = []
    for run in _roster_runs(text):
        for raw in _ITEM_SPLIT_RE.split(run):
            item = raw.strip().strip(".;,: ")
            if not item:
                continue
            if any(d in item.lower() for d in _GRAPE_LINE_DROP):
                continue
            item = _PROPORTION_RE.sub("", item)
            item = re.sub(r"\s*\([^)]*\)\s*", " ", item).strip()
            if not item or len(item) > 40 or len(item.split()) > 4:
                continue
            if not re.search(r"[A-Za-z]", item):
                continue
            out.append(item)
    return out
