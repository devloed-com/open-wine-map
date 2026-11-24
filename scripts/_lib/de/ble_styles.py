"""Wine types a BLE Produktspezifikation states.

Six Anbaugebiete (Ahr, Baden, Hessische Bergstraße, Rheingau, Sachsen,
Saale-Unstrut) and fourteen Landweine have no EU single document that states
their wine types, so their cards showed the berry-colour floor and the line
"the regulator's text names no colour" — untrue: the national specification
states them (card validator on Baden, 2026-11-17). Baden's § 2 reads "Wein,
Qualitätsschaumwein, Perlwein, Likörwein, teilweise gegorener Traubenmost"
and its § 3.3 describes «Weißwein», «Roséwein, Weißherbst», «Rotwein» under
headings of their own; the Ahr's § 2.2 "An der Ahr werden insbesondere
Rotweine und daneben auch traditionell Rosé- und Weißweine hergestellt".

`stated_styles(text)` returns {style: the sentence that states it}, read from
the specification without its area section, its variety roster and what
follows the roster — except the sub-section "Kategorien von Erzeugnissen" of
the link text, which names the product categories («Erzeugnisart
„Perlwein“»). Two readings:

  * colours — the wine words ("Weißweine", "Rot- und Roséweine", "Weißherbst",
    "Blanc de Noir", a bare "Rosé"), never in an analytical limit: "150 mg/l
    bei Rotwein", "11,5 % vol bei Weiß- und Roséwein" restate ceilings the
    law sets per colour whatever the region makes;
  * categories and Prädikate — the EU reader's own markers (`STYLE_MARKERS`),
    negation-aware, without the sweetness words ("trocken", "lieblich" are
    the EU labelling terms in these texts, not wine types): first in a
    statement with no figure — the title block, the traditional terms, a
    heading — then in the region's own minimum must weights ("5.1.2.4.
    Beerenauslese alle Rebsorten 15,3%vol / (110° Öchsle)"), never in a
    ceiling the law sets ("30 Milliäquivalent je Liter bei Wein, der den
    traditionellen Begriff Beerenauslese oder Eiswein trägt").

Rotling, Schieler and Badisch Rotgold are wine types of their own in German
law with no node in the style taxonomy; they add nothing.
"""

from __future__ import annotations

import re

from _lib.de.einziges_dokument import NEGATION_RE, STYLE_MARKERS

_COLOUR_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bwei(?:ß|ss)weine?[ns]?\b|\bwei(?:ß|ss)-(?=[,\s])", re.I), "blanc"),
    (re.compile(r"\brotweine?[ns]?\b|\brot-(?=[,\s])", re.I), "noir"),
    (re.compile(r"\bros[ée]weine?[ns]?\b|\bros[ée]-(?=[,\s])|\brosé\b"
                r"|\bwei(?:ß|ss)herbste?[ns]?\b", re.I), "rose"),
)
# a white wine too, where the text names no "Weißwein"
_BLANC_DE_NOIRS = re.compile(r"\bblanc de noirs?\b", re.I)
_SKIPPED_MARKERS = frozenset({"dry", "sweet"})
# An ice wine is not a late harvest (the house rule): the EU reader's table
# files Eiswein under the late-harvest marker, and its ice-wine pill comes
# from stage 04's scan of the record's own sections — which a stub has not.
_MARKERS: tuple[tuple[re.Pattern, str], ...] = tuple(
    (pattern, "icewine" if "eiswein" in pattern.pattern else slug)
    for pattern, slug in STYLE_MARKERS)
_LEGAL_CEILING = re.compile(r"mg\s*/\s*l|\bg\s*/\s*l|milli[äa]quivalent", re.I)
_ANALYTICAL = re.compile(_LEGAL_CEILING.pattern + r"|%\s*vol|vol\.?\s*-?\s*%|°\s*oe|öchsle", re.I)

_AREA_HEAD = re.compile(r"^[ \t_]*\d{0,2}\s*\.?\s*Abgrenzung\s+des\s+(?:geogra(?:f|ph)ischen\s+)?Gebiet",
                        re.M)
_AFTER_AREA_HEAD = re.compile(
    r"^[ \t_]*\d{1,2}\s*\.?\s+(?:Traditionelle\s+Begriffe|Spezifische\s+[öo]nologische"
    r"|H[öo]chstertrag|Hektarh[öo]chstertrag|Rebsorten|Zugelassene\s+Kel[lt]ertraubensorten"
    r"|Angaben,\s+aus\s+denen|Zusammenhang\s+mit)", re.M)
_ROSTER_HEAD = re.compile(
    r"^[ \t_]*(?:\d{1,2}\s*\.?\s+)?(?:Rebsorten\s*$|Zugelassene\s+Kel[lt]ertraubensorten)", re.M)
_CATEGORIES_HEAD = re.compile(r"^[ \t_]*\d{1,2}\.\d\s*\.?\s+Kategorien\s+von\s+Erzeugnissen", re.M)
_CATEGORIES_END = re.compile(
    r"^[ \t_]*(?:\d{1,2}\.\d\s*\.?\s+Kausaler|\d{1,2}\s*\.?\s+(?:Sonstige|Weitere|Namen?\s+und))",
    re.M)
_PAGE_FURNITURE = re.compile(r"^[ \t_]*(?:Seite\s+\d+\s+von\s+\d+|-\s*\d+\s*-|\d+\s*/\s*\d+)[ \t]*$",
                             re.M)
_ELISION = re.compile(r"-\n[ \t_]*(?=(?:und|oder|bzw|sowie)\b)", re.I)
_LINE_HYPHEN = re.compile(r"(?<=[a-zäöüß])-\n[ \t_]*(?=[a-zäöüß])")
# a sentence end — not the dot of "b. A." or "z. B." — a blank line, or a
# line that opens on a bullet or an enumerator
_STATEMENT_SPLIT = re.compile(
    r"(?<=[.;!?])(?<!\b[A-Za-zÄÖÜäöü]\.)\s+(?=[A-ZÄÖÜ„•])|\n[ \t_]*\n"
    r"|\n[ \t_]*(?=(?:[•−–\-o\uf02d]|[a-z]\)|\d+(?:\.\d+)*\.?)\s)")
_HEADING = re.compile(r"^[^.;!?]{1,60}:?$")
_BULLET = re.compile(r"^[•−–\-]\s+")
_GLYPHS = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\uf02d\uf0b7\uf0a7]")


# The category and Prädikat words in any number and in an elided compound —
# "Auch Schaum-, Perl- und Likörweine können die kontrollierte
# Ursprungsbezeichnung tragen" (the Schwyz and Zürich rulings): the EU
# reader's markers are singular and whole.
_TYPE_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bschaum(?:weine?[ns]?\b|-(?=[,\s]))|\bsekt\b", re.I), "sparkling"),
    (re.compile(r"\bperl(?:weine?[ns]?\b|-(?=[,\s]))", re.I), "semi-sparkling"),
    (re.compile(r"\blikör(?:weine?[ns]?\b|-(?=[,\s]))", re.I), "vin-de-liqueur"),
    (re.compile(r"\bspätlesen?\b", re.I), "vendanges-tardives"),
    (re.compile(r"\b(?:trocken)?beerenauslesen?\b", re.I), "grains-nobles"),
)


def clause_styles(quote: str) -> list[str]:
    """The wine types one clause of a ruling names: its colours and its
    categories, an elided compound read whole. A clause that restates a
    ceiling of the law names none."""
    if _LEGAL_CEILING.search(quote or ""):
        return []
    found = [colour for pattern, colour in _COLOUR_PATTERNS if pattern.search(quote)]
    found += [slug for pattern, slug in _TYPE_PATTERNS
              if any(not NEGATION_RE.search(quote[:m.start()]) for m in pattern.finditer(quote))]
    return found


def readable_text(text: str) -> str:
    """The specification without its area section, its roster and what
    follows it, plus the "Kategorien von Erzeugnissen" block; line-break
    hyphens closed ("Weiß-⏎herbste"), an elided compound kept ("Rot- ⏎und
    Roséweine")."""
    # a bullet set in a symbol font comes out as a control or private-use glyph
    text = _GLYPHS.sub("•", (text or "").replace("\x0c", "\n"))
    text = _PAGE_FURNITURE.sub("", text)
    roster = _ROSTER_HEAD.search(text)
    head = text[:roster.start()] if roster else text
    area = _AREA_HEAD.search(head)
    if area:
        after = _AFTER_AREA_HEAD.search(head, area.end())
        head = head[:area.start()] + (head[after.start():] if after else "")
    categories = ""
    cat = _CATEGORIES_HEAD.search(text)
    if cat:
        end = _CATEGORIES_END.search(text, cat.end())
        categories = text[cat.start():end.start() if end else len(text)]
    blob = head + "\n\n" + categories
    blob = _ELISION.sub("- ", blob)
    return _LINE_HYPHEN.sub("", blob)


def _statements(blob: str) -> list[str]:
    """Sentences, bullet items and headings; a bare heading ("Weißwein",
    "Roséwein, Weißherbst") is read with the paragraph it heads."""
    parts = [_BULLET.sub("", re.sub(r"[\s_]+", " ", s).strip())
             for s in _STATEMENT_SPLIT.split(blob.replace("•", "\n• "))]
    parts = [p for p in parts if p]
    out: list[str] = []
    for i, part in enumerate(parts):
        nxt = parts[i + 1] if i + 1 < len(parts) else ""
        if _HEADING.match(part) and nxt and not _HEADING.match(nxt) \
                and not _ANALYTICAL.search(nxt):
            out.append(f"{part} {nxt}" if part.endswith(",") else f"{part.rstrip(':')}: {nxt}")
        else:
            out.append(part)
    return out


def _marker_hits(statement: str) -> list[str]:
    hits = []
    for pattern, slug in _MARKERS:
        if slug in _SKIPPED_MARKERS or slug in hits:
            continue
        if any(not NEGATION_RE.search(statement[:m.start()]) for m in pattern.finditer(statement)):
            hits.append(slug)
    return hits


def stated_styles(text: str) -> dict[str, str]:
    """{style: the statement that states it} for one specification text."""
    statements = _statements(readable_text(text))
    prose = [s for s in statements if not _ANALYTICAL.search(s)]
    out: dict[str, str] = {}
    for statement in prose:
        for pattern, colour in _COLOUR_PATTERNS:
            if colour not in out and pattern.search(statement):
                out[colour] = statement[:300]
    if "blanc" not in out:
        for statement in prose:
            if _BLANC_DE_NOIRS.search(statement):
                out["blanc"] = statement[:300]
                break
    # a sentence first, then a bare heading or list item, then the region's
    # own minimum must weights per Prädikat and category
    for pool in ([s for s in prose if len(s.split()) >= 4], prose,
                 [s for s in statements if not _LEGAL_CEILING.search(s)]):
        for statement in pool:
            for slug in _marker_hits(statement):
                out.setdefault(slug, statement[:300])
    return out
