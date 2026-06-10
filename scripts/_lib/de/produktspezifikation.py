"""Parse a BLE Produktspezifikation PDF into a principal/accessory variety split.

The BLE (Bundesanstalt für Landwirtschaft und Ernährung) hosts the
canonical wine-law Produktspezifikation per German Anbaugebiet at a
stable URL pattern under https://www.ble.de/SharedDocs/Downloads/DE/
Ernaehrung-Lebensmittel/EU-Qualitaetskennzeichen/Wein/Antraege/
Bestimmte_Anbaugebiete/01_Produktspezifiaktion_Anbaugebiete/.

These PDFs are *Amtliche Werke* per §5 UrhG — free reuse with attribution.

The 13 PDFs use FOUR different templates (the BLE generated them across
different agency drafting eras). The parser tries each template in turn:

  - **Template A** (post-2022 reform): numbered "8 Zugelassene
    Keltertraubensorten" + `Weiße Rebsorten` / `Rote Rebsorten`
    subheaders. §3.2 names individual varieties with their own
    Mindestmostgewicht threshold. Used by: Mosel, Pfalz, Nahe,
    Mittelrhein, Rheinhessen, Franken, Württemberg, Saale-Unstrut
    (the last with a "Kellertraubensorten" typo in the PDF source).

  - **Template B** (older Schutzgemeinschaft drafting):
    "Zugelassene Keltertraubensorten:" un-numbered + bullet markers
    `• Weißwein` / `• Weißweine` / `• Rot- und Roséwein` /
    `• Rot- und Roseweine`. Used by: Ahr, Sachsen. Sachsen also has
    named-variety §5.1.X subsections (Weißwein - Ruländer, Traminer,
    Weißburgunder) giving an explicit principal split; Ahr's §5.1 is
    flat-by-colour (no principal split available).

  - **Template C** (Hessen / Rheingau drafting):
    "7. Rebsorten" (NOT §8!) with named subsections `Weißweinsorten:`
    / `Rot- und Roséweinsorten:` (Hessische Bergstraße) or bullet
    markers `• Rebsorten für Weißwein` / `• Rebsorten für Rot- und
    Roséwein` (Rheingau). Often includes inline named principals
    ("insbes. Weißer Riesling mit rd. 80 % auf der Rebfläche" or
    "Spätburgunder Rotwein 8,4 66°" in §5.1.X).

  - **Template D** (Baden multi-Bereich):
    §3.2.X with multiple regional Bereich subsections, each containing
    bullet-form `- VarietyName1, VarietyName2 ... 8,X % vol und YY°Oe`
    tiered by Mostgewicht. The first (lowest) tier per colour names the
    lead varieties → PRINCIPAL. Used by: Baden.

The output shape is uniform across templates:

  {
    "section_3_2_principal_names": [...],  # de-facto principal varieties
    "section_8_white_names": [...],
    "section_8_red_names": [...],
  }

`grape_entity.match_variety` resolves each raw name to a slug downstream.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# ─────────────────────────────────────────────────────  Template A  ──

# Template A: numbered "8 Zugelassene Keltertraubensorten" — the post-2022
# reform shape. Tolerates "Kellertraubensorten" (Saale-Unstrut PDF typo).
_SECTION_8_RE = re.compile(
    r"^\s*8\s*\.?\s+Zugelassene\s+(?:Kelter|Keller)traubensorten\s*$",
    re.M,
)
_SECTION_3_2_RE = re.compile(
    r"^\s*3\.2\s+(?:\.\s+)?Natürliche?r?\s+Mindest(?:alkohol|most)",
    re.M,
)
_SECTION_END_RE = re.compile(
    r"^\s*9\s+(?:\.\s+)?Angaben",
    re.M,
)
_SECTION_3_3_RE = re.compile(
    r"^\s*3\.3\s+(?:\.\s+)?(?:Organoleptisch)",
    re.M,
)

# ─────────────────────────────────────────────────────  Template B  ──

# Template B: "Zugelassene Keltertraubensorten:" un-numbered + bullet
# markers. Section may be followed by "Zusammenhang mit dem
# geografischen Gebiet" or end-of-document.
_TEMPLATE_B_ANCHOR_RE = re.compile(
    r"^\s*Zugelassene\s+Keltertraubensorten\s*:?\s*$",
    re.M,
)
_TEMPLATE_B_END_RE = re.compile(
    r"^\s*Zusammenhang\s+mit\s+dem\s+geografischen\s+Gebiet",
    re.M,
)
# `• Weißwein` / `• Weißweine` / `• Rot- und Roséwein` / `• Rot- und Roseweine`
# pdftotext emits U+2022 BULLET as `•` and occasionally U+0001 (SOH) as
# a glyph fallback when the source font lacks a bullet glyph.
_BULLET_CLASS = r"[•\-]"
_TEMPLATE_B_WHITE_RE = re.compile(
    rf"^\s*(?:{_BULLET_CLASS}\s*)?Weißweine?\s*$",
    re.M,
)
_TEMPLATE_B_RED_RE = re.compile(
    rf"^\s*(?:{_BULLET_CLASS}\s*)?Rot[\s-]+und[\s-]+Ros[ée]weine?\s*$",
    re.M,
)

# Sachsen's §5.1.X named-principal subsections — only the lines that
# list real varieties, NOT the "übrige Sorten" / "Weine ohne
# Sortenangabe" lines which are the implicit accessory bucket. We
# match the "and Weine ohne Sortenangabe" suffix that follows the
# named varieties (for the §5.1.3 form), and explicitly reject the
# "übrige Sorten" subsection header form.
_TEMPLATE_B_SACHSEN_NAMED_WHITE_RE = re.compile(
    r"^\s*5\.1\.\d+\.?\s+Weißwein\s+[-–]\s+(?!übrige|Weine\s+ohne)([^(\n]+?)(?:\s+und\s+Weine\s+ohne|\s+\(|\s*$)",
    re.M,
)
_TEMPLATE_B_SACHSEN_NAMED_RED_RE = re.compile(
    r"^\s*5\.1\.\d+\.?\s+Rotwein\s+[-–]\s+(?!übrige|Weine\s+ohne)([^(\n]+?)(?:\s+und\s+Weine\s+ohne|\s+\(|\s*$)",
    re.M,
)

# ─────────────────────────────────────────────────────  Template C  ──

# Template C: "7. Rebsorten" section.
_TEMPLATE_C_SECTION_7_RE = re.compile(
    r"^\s*7\.\s*Rebsorten\s*$",
    re.M,
)
_TEMPLATE_C_END_RE = re.compile(
    r"^\s*8\.\s*Angaben|^\s*Zusammenhang\s+mit\s+dem\s+geografischen",
    re.M,
)
# Header variants for white inside §7:
#   • Rebsorten für Weißwein
#   Weißweinsorten:
_TEMPLATE_C_WHITE_RE = re.compile(
    rf"^\s*(?:{_BULLET_CLASS}\s*Rebsorten\s+für\s+Weißwein\s*$"
    r"|Weißweinsorten\s*:?\s*$)",
    re.M,
)
_TEMPLATE_C_RED_RE = re.compile(
    rf"^\s*(?:{_BULLET_CLASS}\s*Rebsorten\s+für\s+Rot[\s-]+und[\s-]+Ros[ée]wein\s*$"
    r"|Rot[\s-]+und[\s-]+Ros[ée]weinsorten\s*:?\s*$"
    r"|Rotweinsorten\s*:?\s*$)",
    re.M,
)

# "insbes. {variety} mit rd. X %" — Rheingau-style inline principal.
_TEMPLATE_C_INSBES_RE = re.compile(
    r"insbes\.\s+([A-ZÄÖÜ][\w\s\-]+?)\s+mit\s+rd\.\s+\d",
)
# "die Rebsorten {V1} (X %), {V2} (Y %) sowie {V3} (Z %) angebaut" —
# Hessische-Bergstraße cultivation-statistics inline (the §8.1.1
# geographic-facts section names the Leitsorten by cultivation share).
# Each variety is followed by `(NN,N % der Rebfläche)` or similar.
_TEMPLATE_C_VORWIEGEND_RE = re.compile(
    r"vorwiegend\s+die\s+Rebsorten\s+(.+?)\s+angebaut",
    re.S,
)
_TEMPLATE_C_PERCENT_NAME_RE = re.compile(
    r"([A-ZÄÖÜ][\wäöüß\s\-]+?)\s*\(\s*\d{1,3}[,.]?\d*\s*%",
)
# §5.1.X named: "Spätburgunder Rotwein 8,4 66°" — Rheingau/Hessische-Bergstraße.
_TEMPLATE_C_NAMED_MOST_RE = re.compile(
    r"^\s*([A-ZÄÖÜ][\w\-]+(?:\s+[\w\-]+)?)\s+Rotwein\s+\d{1,2}[,.]\d\s+\d{2,3}\s*°?",
    re.M,
)

# ─────────────────────────────────────────────────────  Template D  ──

# Template D (Baden): §3.2.X multi-Bereich subsections with bullet-form
# tiered Mostgewicht rows.
_TEMPLATE_D_BEREICH_RE = re.compile(
    r"^\s*3\.2\.\d+\.?\s+Bereich:",
    re.M,
)
# Inside a Bereich block, "Weiße Rebsorten" / "Rote Rebsorten" subheaders.
_TEMPLATE_D_COLOUR_HEADER_RE = re.compile(
    r"^\s*(Weiße|Rote)\s+Rebsorten\s*$",
    re.M,
)
# Row form: "- Variety1, Variety2 ... 8,X % vol und YY°Oe"
_TEMPLATE_D_ROW_RE = re.compile(
    r"^\s*[-–—]\s+(.+?)\s+(\d{1,2}[,.]\d)\s*%\s*vol\s+und\s+\d{2,3}\s*°?[Oo]e",
    re.M,
)
# "alle übrigen Rebsorten" — implicit accessory bucket; skip.
_ALL_REST_RE = re.compile(
    r"\balle\s+(?:übrigen\s+)?(?:Weißen?\s+|Roten?\s+)?Rebsorten\b",
    re.I,
)
# "als Versuch angebaute ..." — experimental, skip.
_TEMPLATE_D_VERSUCH_RE = re.compile(r"\bals\s+Versuch\b", re.I)

# ───────────────────────────────────────────────  Shared utilities  ──

# Threshold-line pattern: covers both "% vol und ° Öchsle" and other forms.
_MOSTGEWICHT_LINE_RE = re.compile(
    r"\d{1,2}[,.]\d\s*%\s*vol(?:\s+und)?\s+\d{2,3}\s*°?\s*Öchsle",
)

_REBSORTE_PREFIX_RE = re.compile(r"^\s*Rebsorten?\s+", re.I)
_PAREN_CLEAN_RE = re.compile(r"\s*\([^)]*\)\s*")

# Header keywords that reset the §3.2 pending-names accumulator.
_PRADIKAT_HEADERS = (
    "kabinett", "spätlese", "auslese", "beerenauslese",
    "trockenbeerenauslese", "eiswein", "sekt", "winzersekt",
    "qualitätswein", "prädikatswein", "perlwein", "likörwein",
    "qualitätsschaumwein", "wein", "teilweise",
)


def _strip_paren(s: str) -> str:
    return _PAREN_CLEAN_RE.sub(" ", s).strip()


def _split_variety_phrase(seg: str) -> list[str]:
    seg = _REBSORTE_PREFIX_RE.sub("", seg).strip()
    seg = _strip_paren(seg)
    parts = re.split(r"\s+und\s+|,\s*", seg)
    out: list[str] = []
    for p in parts:
        name = p.strip().rstrip(".")
        if not name:
            continue
        if name.lower() in ("alle", "rebsorten", "rebsorte", "sonstige", "sorten"):
            continue
        out.append(name)
    return out


def _parse_comma_enum(blob: str) -> list[str]:
    if not blob:
        return []
    flat = re.sub(r"\s+", " ", blob).strip().rstrip(".")
    # Hyphenation drift in pdftotext output: "Burgun-\nder" → "Burgunder".
    flat = re.sub(r"([a-zäöüß])-\s+([a-zäöüß])", r"\1\2", flat)
    parts = re.split(r",\s*|\s+und\s+", flat)
    out: list[str] = []
    for p in parts:
        name = p.strip().rstrip(".:")
        if not name:
            continue
        if name.lower() in ("alle", "rebsorten", "rebsorte", "sonstige", "sorten"):
            continue
        if len(name) <= 2:
            continue
        out.append(name)
    return out


def pdf_to_text(pdf_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return result.stdout


# ─────────────────────────────────────────────────  Template A core  ──


def _slice_section_a_3_2(text: str) -> str:
    m_start = _SECTION_3_2_RE.search(text)
    if not m_start:
        return ""
    m_end = _SECTION_3_3_RE.search(text, m_start.end())
    end = m_end.start() if m_end else len(text)
    return text[m_start.start():end]


def _slice_section_a_8(text: str) -> str:
    m_start = _SECTION_8_RE.search(text)
    if not m_start:
        return ""
    m_end = _SECTION_END_RE.search(text, m_start.end())
    end = m_end.start() if m_end else len(text)
    return text[m_start.start():end]


def _parse_template_a_principal(text: str) -> list[str]:
    blob = _slice_section_a_3_2(text)
    if not blob:
        return []
    seen: list[str] = []
    seen_set: set[str] = set()
    pending: list[str] = []
    for raw_line in blob.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(line.lower().startswith(p) for p in _PRADIKAT_HEADERS):
            pending = []
            continue
        m_thresh = _MOSTGEWICHT_LINE_RE.search(line)
        if m_thresh:
            head = line[:m_thresh.start()].strip()
            if head:
                pending.append(head)
            blob_pending = " ".join(pending)
            if not _ALL_REST_RE.search(blob_pending):
                for name in _split_variety_phrase(blob_pending):
                    norm = name.strip().rstrip(".")
                    if norm and norm not in seen_set:
                        seen.append(norm)
                        seen_set.add(norm)
            pending = []
            continue
        if line.lower().startswith("rebsorte") or pending:
            pending.append(line)
    return seen


def _parse_template_a_authorised(text: str) -> dict[str, list[str]]:
    blob = _slice_section_a_8(text)
    if not blob:
        return {"white": [], "red": []}
    body = _SECTION_8_RE.sub("", blob, count=1)
    sub_starts = []
    for m in re.finditer(
        r"^\s*(Weiße\s+Rebsorten|Rote\s+Rebsorten)\s*:?\s*$",
        body,
        re.M,
    ):
        sub_starts.append((m.start(), m.end(), m.group(1).lower()))
    if not sub_starts:
        return {"white": _parse_comma_enum(body), "red": []}
    sub_starts.append((len(body), len(body), ""))
    out = {"white": [], "red": []}
    for i in range(len(sub_starts) - 1):
        _hstart, hend, head = sub_starts[i]
        end = sub_starts[i + 1][0]
        chunk = body[hend:end].strip()
        names = _parse_comma_enum(chunk)
        if head.startswith("weiße"):
            out["white"] = names
        elif head.startswith("rote"):
            out["red"] = names
    return out


# ─────────────────────────────────────────────────  Template B core  ──


def _slice_template_b(text: str) -> str:
    m_start = _TEMPLATE_B_ANCHOR_RE.search(text)
    if not m_start:
        return ""
    m_end = _TEMPLATE_B_END_RE.search(text, m_start.end())
    end = m_end.start() if m_end else len(text)
    return text[m_start.start():end]


def _parse_template_b_authorised(text: str) -> dict[str, list[str]]:
    blob = _slice_template_b(text)
    if not blob:
        return {"white": [], "red": []}
    # Skip the anchor line itself.
    body = _TEMPLATE_B_ANCHOR_RE.sub("", blob, count=1)
    # PDFs occasionally include the anchor twice (Ahr's first occurrence
    # is in the TOC); keep slicing from the last anchor inside `blob`.
    # We've already started from the first; the second-anchor case is
    # rare and benign — body just contains both.
    sub_starts: list[tuple[int, int, str]] = []
    for m in _TEMPLATE_B_WHITE_RE.finditer(body):
        sub_starts.append((m.start(), m.end(), "white"))
    for m in _TEMPLATE_B_RED_RE.finditer(body):
        sub_starts.append((m.start(), m.end(), "red"))
    sub_starts.sort()
    if not sub_starts:
        return {"white": [], "red": []}
    sub_starts.append((len(body), len(body), ""))
    out = {"white": [], "red": []}
    for i in range(len(sub_starts) - 1):
        _hstart, hend, colour = sub_starts[i]
        end = sub_starts[i + 1][0]
        chunk = body[hend:end].strip()
        names = _parse_comma_enum(chunk)
        if colour and not out[colour]:
            out[colour] = names
    return out


def _parse_template_b_principal_sachsen(text: str) -> list[str]:
    """Sachsen-style: §5.1.X named subsections.
    "5.1.1. Weißwein - Ruländer, Traminer, Weißburgunder" → 3 principals."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _TEMPLATE_B_SACHSEN_NAMED_WHITE_RE.finditer(text):
        for name in _parse_comma_enum(m.group(1)):
            if name not in seen:
                out.append(name)
                seen.add(name)
    for m in _TEMPLATE_B_SACHSEN_NAMED_RED_RE.finditer(text):
        for name in _parse_comma_enum(m.group(1)):
            if name not in seen:
                out.append(name)
                seen.add(name)
    return out


# ─────────────────────────────────────────────────  Template C core  ──


def _slice_template_c_section_7(text: str) -> str:
    m_start = _TEMPLATE_C_SECTION_7_RE.search(text)
    if not m_start:
        return ""
    m_end = _TEMPLATE_C_END_RE.search(text, m_start.end())
    end = m_end.start() if m_end else len(text)
    return text[m_start.start():end]


def _parse_template_c_authorised(text: str) -> dict[str, list[str]]:
    blob = _slice_template_c_section_7(text)
    if not blob:
        return {"white": [], "red": []}
    sub_starts: list[tuple[int, int, str]] = []
    for m in _TEMPLATE_C_WHITE_RE.finditer(blob):
        sub_starts.append((m.start(), m.end(), "white"))
    for m in _TEMPLATE_C_RED_RE.finditer(blob):
        sub_starts.append((m.start(), m.end(), "red"))
    sub_starts.sort()
    if not sub_starts:
        return {"white": [], "red": []}
    sub_starts.append((len(blob), len(blob), ""))
    out = {"white": [], "red": []}
    for i in range(len(sub_starts) - 1):
        _hstart, hend, colour = sub_starts[i]
        end = sub_starts[i + 1][0]
        chunk = blob[hend:end].strip()
        # Strip the "insbes. X mit rd. Y %" preamble before the
        # comma-list — the preamble names the dominant variety, the
        # comma-list is the full authorised set.
        m_insbes = re.search(r"klassifizierte\s+Rebsorten[^:]*:", chunk)
        if m_insbes:
            chunk = chunk[m_insbes.end():]
        names = _parse_comma_enum(chunk)
        if colour and not out[colour]:
            out[colour] = names
    return out


def _parse_template_c_principal(text: str) -> list[str]:
    """Template C principals from three signals:
      - 'insbes. {variety} mit rd. X %' inline (Rheingau-style)
      - §5.1.X named-Mostgewicht rows ('Spätburgunder Rotwein 8,4 66°')
      - 'vorwiegend die Rebsorten {V1} (X %), {V2} (Y %) sowie {V3} (Z %)
        angebaut' (Hessische-Bergstraße cultivation-statistics inline).
    """
    out: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        nm = name.strip()
        if nm and nm not in seen:
            out.append(nm)
            seen.add(nm)

    blob = _slice_template_c_section_7(text)
    if blob:
        for m in _TEMPLATE_C_INSBES_RE.finditer(blob):
            _add(m.group(1))
    for m in _TEMPLATE_C_NAMED_MOST_RE.finditer(text):
        name = m.group(1).strip()
        if name.lower().startswith(("sonstige", "weißwein", "rotwein", "alle")):
            continue
        _add(name)
    # Cultivation-statistics fallback — only fires when §3.2/§5.1 didn't
    # yield enough. Hessische-Bergstraße's only Riesling signal is here.
    for m in _TEMPLATE_C_VORWIEGEND_RE.finditer(text):
        cluster = m.group(1)
        for vm in _TEMPLATE_C_PERCENT_NAME_RE.finditer(cluster):
            name = vm.group(1).strip().rstrip(",").rstrip(".")
            # Strip leading "sowie " or "und " connectors.
            name = re.sub(r"^(?:sowie|und)\s+", "", name)
            _add(name)
    return out


# ─────────────────────────────────────────────────  Template D core  ──


def _parse_template_d(text: str) -> tuple[list[str], dict[str, list[str]]]:
    """Baden-style: multi-Bereich §3.2.X with tiered Mostgewicht rows.
    Returns (principal_names, {"white": [...], "red": [...]}).

    For each (Bereich, colour) sub-block, the rows are tiered by ascending
    threshold. The lowest-threshold row(s) name the Leitsorten → principal.
    Higher-tier rows + "alle übrigen Rebsorten" → accessory. We union all
    principal sets across Bereiche (Baden authorises varieties from each
    Bereich union)."""
    bereich_starts = list(_TEMPLATE_D_BEREICH_RE.finditer(text))
    if not bereich_starts:
        return [], {"white": [], "red": []}
    # End of Baden's §3.2 multi-Bereich block — §3.3 or §4.
    end_match = re.search(r"^\s*(3\.3|3\.4|4\.)\s+", text, re.M)
    final_end = end_match.start() if end_match else len(text)

    all_principal: list[str] = []
    seen_principal: set[str] = set()
    white_all: list[str] = []
    red_all: list[str] = []
    seen_white: set[str] = set()
    seen_red: set[str] = set()

    for i, m in enumerate(bereich_starts):
        b_start = m.start()
        b_end = bereich_starts[i + 1].start() if i + 1 < len(bereich_starts) else final_end
        bereich = text[b_start:b_end]
        # Sub-blocks by colour header inside the Bereich.
        colour_headers = list(_TEMPLATE_D_COLOUR_HEADER_RE.finditer(bereich))
        if not colour_headers:
            continue
        colour_headers.append(re.match(r"$", "") or type(colour_headers[0])(*[]))  # sentinel ignored below
        # Iterate colour blocks.
        for j, ch in enumerate(colour_headers[:-1]):
            colour = "white" if ch.group(1).startswith("Weiß") else "red"
            block_start = ch.end()
            block_end = colour_headers[j + 1].start() if j + 1 < len(colour_headers) - 1 else len(bereich)
            block = bereich[block_start:block_end]
            # Parse rows in order; collect varieties at the lowest threshold.
            rows: list[tuple[float, str]] = []
            for rm in _TEMPLATE_D_ROW_RE.finditer(block):
                row_names_blob = rm.group(1)
                thresh = float(rm.group(2).replace(",", "."))
                if _ALL_REST_RE.search(row_names_blob) or _TEMPLATE_D_VERSUCH_RE.search(row_names_blob):
                    continue
                rows.append((thresh, row_names_blob))
            if not rows:
                continue
            min_thresh = min(t for t, _ in rows)
            for thresh, names_blob in rows:
                for name in _parse_comma_enum(names_blob):
                    if colour == "white":
                        if name not in seen_white:
                            white_all.append(name)
                            seen_white.add(name)
                    else:
                        if name not in seen_red:
                            red_all.append(name)
                            seen_red.add(name)
                    if thresh == min_thresh and name not in seen_principal:
                        all_principal.append(name)
                        seen_principal.add(name)
    return all_principal, {"white": white_all, "red": red_all}


# ────────────────────────────────────────  Template detection + extract  ──


def _detect_template(text: str) -> str:
    """Pick the template whose §8/§7 parser yields the most varieties.

    Multiple templates can have positive markers in the same PDF
    (Sachsen / Rheingau both contain the phrase "Zugelassene
    Keltertraubensorten" as part of §7, even though their real
    variety-list shape is C / B). Try each parser, score by variety
    count, return the winner.
    """
    if _TEMPLATE_D_BEREICH_RE.search(text):
        return "D"
    scores = {
        "A": _parse_template_a_authorised(text),
        "B": _parse_template_b_authorised(text),
        "C": _parse_template_c_authorised(text),
    }
    return max(scores, key=lambda k: len(scores[k]["white"]) + len(scores[k]["red"]))


def parse_section_3_2_principal_names(text: str) -> list[str]:
    """Public API. Template-dispatch + accumulate principals from
    multiple sub-template heuristics (Sachsen §5.1.X named subsections
    are detected independently of the variety-list template choice)."""
    template = _detect_template(text)
    out: list[str] = []
    seen: set[str] = set()

    def _add(names: list[str]) -> None:
        for n in names:
            if n and n not in seen:
                out.append(n)
                seen.add(n)

    if template == "A":
        _add(_parse_template_a_principal(text))
    elif template == "C":
        _add(_parse_template_c_principal(text))
    elif template == "D":
        principal, _ = _parse_template_d(text)
        _add(principal)
    # Sachsen §5.1.X always tried — independent of template selection,
    # because some Template-B docs (Sachsen) DO carry the named
    # subsection while others (Ahr) do not.
    _add(_parse_template_b_principal_sachsen(text))
    return out


def parse_section_8_authorised(text: str) -> dict[str, list[str]]:
    """Public API — dispatch to the detected template's parser. For
    Template D (Baden), prefer Template A's §8 list when present — Baden
    embeds the multi-Bereich Mostgewicht tiers in §3.2 (Template D) AND
    a comprehensive flat §8 (Template A). The §3.2 list is incomplete;
    §8 has the full authorised set.
    """
    template = _detect_template(text)
    if template == "A":
        return _parse_template_a_authorised(text)
    if template == "B":
        return _parse_template_b_authorised(text)
    if template == "C":
        return _parse_template_c_authorised(text)
    if template == "D":
        a_result = _parse_template_a_authorised(text)
        if a_result["white"] or a_result["red"]:
            return a_result
        _, d_result = _parse_template_d(text)
        return d_result
    return {"white": [], "red": []}


# Backwards-compatible helpers retained for callers / tests.
def slice_section_3_2(text: str) -> str:
    return _slice_section_a_3_2(text)


def slice_section_8(text: str) -> str:
    return _slice_section_a_8(text)


# ─────────────────────────────────────────  Terroir / Zusammenhang  ──

# BLE Produktspezifikation "Angaben, aus denen sich der Zusammenhang
# … ergibt" section. Numbered §8 (older Ahr/Rheingau/Hessische-
# Bergstraße/Sachsen template) or §9 (post-2022 reform Mosel/Baden/
# Pfalz/Nahe/Mittelrhein/Rheinhessen/Franken/Württemberg/Saale-Unstrut).
# Substantially richer than the EU Einziges Dokument's section-8
# narrative — covers landscape, geology, climate, human history, and
# the categories-of-product-specific Zusammenhang sub-sections.
_ZUSAMMENHANG_START_RE = re.compile(
    r"^\s*[89]\s*\.?\s*Angaben,?\s+aus\s+denen\s+sich\s+der\s+Zusammenhang",
    re.M,
)
_ZUSAMMENHANG_END_RE = re.compile(
    r"^\s*(?:10\.?|Sonstige\s+Bedingungen|Bezug\s+auf\s+die\s+Produktspezifikation)\s*",
    re.M,
)
# Page-furniture lines pdftotext emits (running header / footer); strip.
_PAGE_FURNITURE_RE = re.compile(
    r"^\s*(?:Seite\s+\d+\s+von\s+\d+|\d+\s*/\s*\d+|-\s*\d+\s*-)\s*$",
    re.M,
)


def extract_terroir_text(text: str) -> str:
    """Return the plain-text "Zusammenhang" section as a single block.

    Strips page-furniture lines (running headers, "Seite X von Y",
    form-feed-induced spacers). The section starts at the numbered
    "8./9. Angaben..." header and ends at "10. ..." / "Sonstige
    Bedingungen" / "Bezug auf die Produktspezifikation"."""
    m_start = _ZUSAMMENHANG_START_RE.search(text)
    if not m_start:
        return ""
    m_end = _ZUSAMMENHANG_END_RE.search(text, m_start.end())
    end = m_end.start() if m_end else len(text)
    block = text[m_start.start():end]
    # Strip page-furniture and form-feed indicators line-by-line.
    cleaned: list[str] = []
    for line in block.splitlines():
        if _PAGE_FURNITURE_RE.match(line):
            continue
        cleaned.append(line.rstrip())
    # Collapse runs of empty lines to a single blank.
    out: list[str] = []
    prev_empty = False
    for line in cleaned:
        is_empty = not line.strip()
        if is_empty and prev_empty:
            continue
        out.append(line)
        prev_empty = is_empty
    return "\n".join(out).strip()


def extract(pdf_path: Path) -> dict:
    """Parse a BLE Produktspezifikation PDF — template-aware.

    Returns:
      {
        "template": "A" | "B" | "C" | "D",
        "section_3_2_principal_names": [...],
        "section_8_white_names": [...],
        "section_8_red_names": [...],
        "zusammenhang_text": "...",   # plain text of §8/§9 terroir block
      }
    """
    text = pdf_to_text(pdf_path)
    template = _detect_template(text)
    principal = parse_section_3_2_principal_names(text)
    section_8 = parse_section_8_authorised(text)
    zusammenhang = extract_terroir_text(text)
    return {
        "template": template,
        "section_3_2_principal_names": principal,
        "section_8_white_names": section_8["white"],
        "section_8_red_names": section_8["red"],
        "zusammenhang_text": zusammenhang,
    }
