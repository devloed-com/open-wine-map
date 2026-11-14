"""The four sub-sections of a French link text that is headed by titles.

The AOC wine cahiers number section X "1° - Informations sur la zone
géographique / a) facteurs naturels / b) facteurs humains / 2° - … produit /
3° - Interactions causales", and `slice_section_x` in stage 02d reads those.
The IGP wine cahiers ("7.1 – Spécificité de la zone géographique", "7.2 –
Spécificité du produit", "7.3 – Lien causal …") and the spirit and cider
cahiers ("5.1 Les facteurs physiques du lien", "5.2 Les facteurs humains du
lien", "5.3 Les spécificités du produit", "5.4 Lien causal …"; "a) Éléments
historiques concernant les facteurs du lien au terroir", "Caractéristiques du
rhum attribuables à l'aire géographique") carry no such numerals: until
2026-11-13 the whole text went through the one natural-factors call, and
every fact of 62 IGP wines and 50 drinks was filed under "natural factors",
history and product included.

`slice_by_titles` reads the headings by their words. A heading is a short
line of its own, numbered or not, whose title opens on one of the phrases
below; the text under it runs to the next heading. Slices of one sub-section
are joined in text order.
"""
from __future__ import annotations

import re
import unicodedata

SUB_KEYS = ("facteurs_naturels", "facteurs_humains", "produit", "interactions")

# Tested in this order: "Éléments historiques liés à la réputation" is the
# product's reputation, "Éléments historiques concernant les facteurs du
# lien" the human factors.
_TITLE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("interactions", r"(?:lien causal|interactions? causales?)\b"),
    ("produit", r"(?:(?:les )?specificites? du produit\b"
                r"|caracteristiques?(?: et reputation)? (?:du |de la |de l'|des )"
                r"(?:produits?|rhums?|whisk|creme|eaux?[ -]de[ -]vie|vins?|cidres?|poires?|kirsch|marcs?|liqueurs?|pommeau|[\"«])"
                r"|informations sur (?:la qualite|le produit|les produits)\b|(?:la )?reputation\b"
                r"|elements lies a la reputation\b"
                r"|elements historiques lies a (?:l'anteriorite et a )?la reputation\b)"),
    ("facteurs_humains", r"(?:(?:les |description des )?facteurs humains\b|elements historiques\b|aspects? historiques?\b"
                         r"|(?:le |les )?savoir-faire\b|histoire\b|historique\b|facteurs historiques\b)"),
    ("facteurs_naturels", r"(?:(?:les |description des )?facteurs (?:naturels|physiques)\b"
                          r"|(?:specificites?|caracteristiques?) de (?:l'aire|la zone)\b"
                          r"|description des facteurs de l'aire\b|details de l'aire\b"
                          r"|informations sur la zone\b)"),
)
_HEADING_RE = re.compile(
    r"^[ \t\x0c]*(?P<num>(?:\d{1,2}\.\d(?:\.\d)?\.?|\d{1,2}\.|\d[ \t]*°|[a-dA-D][.)]|[-–•])[ \t]*[-–]?[ \t]*)?"
    r"(?P<title>[A-ZÉÈÀÂÎÔ][^\n]{3,118}?)[ \t]*[.:]?[ \t]*$",
    re.MULTILINE,
)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.replace("’", "'").replace("œ", "oe"))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def title_key(title: str) -> str | None:
    folded = _fold(title).strip()
    for key, pattern in _TITLE_PATTERNS:
        if re.match(pattern, folded):
            return key
    return None


def spans_by_titles(lien: str) -> list[tuple[str, int, int]]:
    """(sub-section, start, end) of each headed stretch of `lien`, in text
    order — empty when fewer than two sub-sections are headed."""
    heads: list[tuple[str, int]] = []
    for m in _HEADING_RE.finditer(lien):
        title = m.group("title")
        # an unnumbered line is a heading only when it stands alone and reads
        # as a title, not as a sentence
        if not m.group("num") and (len(title) > 80 or title.count(",") > 1 or re.search(r"[.;]\s", title)):
            continue
        key = title_key(title)
        if key:
            heads.append((key, m.start()))
    if len({k for k, _ in heads}) < 2:
        return []
    spans = []
    for i, (key, start) in enumerate(heads):
        end = heads[i + 1][1] if i + 1 < len(heads) else len(lien)
        spans.append((key, start, end))
    return spans


def slice_by_titles(lien: str) -> dict[str, str]:
    """{sub-section: text}; the text before the first heading joins the
    natural factors when they are headed."""
    spans = spans_by_titles(lien)
    if not spans:
        return {}
    out: dict[str, list[str]] = {}
    for key, start, end in spans:
        out.setdefault(key, []).append(lien[start:end].strip())
    head = lien[: spans[0][1]].strip()
    if head and "facteurs_naturels" in out and len(head) >= 200:
        out["facteurs_naturels"].insert(0, head)
    return {key: "\n\n".join(parts) for key, parts in out.items()}
