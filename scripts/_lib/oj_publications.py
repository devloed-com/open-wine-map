"""Which eAmbrosia publication a stage 01 fetches as a GI's single document.

eAmbrosia lists a GI's publications without a type and in no reliable order:
new ones are usually prepended, but older lists interleave years (Jerez's
held list read C 98/2023, Ares(2024)…, C/2025/2129, L 2025/1713), so "the
first OJ C listed" — the rule every country's stage 01 used until
2026-10-24 — fetched a superseded single document for ~45 records whose own
list already named a newer one (validator run of 2026-10-23).

The rule here: the newest OJ Series C publication by the date the register
gives (its text "d.m.yyyy", else the ELI / Formex number of its URI), a
corrigendum after every other OJ C, OJ Series L (the implementing
regulation, which carries no single document) and other http links last.
A newest OJ C that is not a single document — a cancellation notice, a
temporary amendment — is pinned per record in the country's
`raw/<cc>/oj-pages/manual_overrides.json`, which every stage 01 reads first.
The register does not say whether an OJ C is an amendment application still
under opposition or an approved standard amendment (which no OJ L follows),
so `amendmentsInProgressFlag` is not used to choose: only the document's own
heading tells the two apart.
"""

from __future__ import annotations

import re

_TEXT_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})(?!\d)")
_ELI_C_RE = re.compile(r"/eli/c/(\d{4})/(\d+)", re.I)
_FORMEX_ACT_RE = re.compile(r"OJ:C_(\d{4})(\d{5})", re.I)
_URISERV_ISSUE_RE = re.compile(r"OJ\.C_\.(\d{4})\.(\d{3})\.01\.(\d{4})", re.I)
_JOC_RE = re.compile(r"JOC_(\d{4})_(\d{3})", re.I)
_TEXT_ELI_NUMBER_RE = re.compile(r"C/(\d{4})/(\d+)")


def is_oj_c(pub: dict) -> bool:
    """An OJ Series C publication: the series that carries single documents."""
    text = (pub.get("text") or "").lower()
    uri = (pub.get("uri") or "").lower()
    if "official journal l" in text or "/reg_impl/" in uri or "oj.l_." in uri:
        return False
    return (
        "official journal c" in text
        or "/eli/c/" in uri
        or "oj.c_." in uri
        or "oj:c_" in uri
        or "joc_" in uri
    )


def is_corrigendum(pub: dict) -> bool:
    text = (pub.get("text") or "").lower()
    uri = (pub.get("uri") or "").lower()
    return (
        "corrigendum" in text
        or "/corrigendum/" in uri
        or "διορθωτικό" in text
        or "διορθωση" in text
    )


def sort_key(pub: dict) -> tuple[int, int, int, int]:
    """(year, month, day, number) — the date the register prints when it
    prints one, the act or issue number of the URI as the tie-break (both
    rise through a year). Unknown parts are 0, so an undated publication
    sorts before a dated one of the same year."""
    text = pub.get("text") or ""
    uri = pub.get("uri") or ""
    number = 0
    year_from_uri = 0
    for rx in (_ELI_C_RE, _FORMEX_ACT_RE, _URISERV_ISSUE_RE, _JOC_RE):
        m = rx.search(uri)
        if m:
            year_from_uri, number = int(m.group(1)), int(m.group(2))
            break
    if not number:
        m = _TEXT_ELI_NUMBER_RE.search(text)
        if m:
            year_from_uri, number = int(m.group(1)), int(m.group(2))
    m = _TEXT_DATE_RE.search(text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return (year, month, day, number)
    return (year_from_uri, 0, 0, number)


def ordered_publication_uris(pubs: list[dict]) -> list[str]:
    """Every http publication URI, in the order a stage 01 should try them:
    OJ C newest first (corrigenda after the rest), then the other http links
    in the register's own order."""
    http = [p for p in pubs or [] if (p.get("uri") or "").startswith("http")]
    oj_c = [p for p in http if is_oj_c(p)]
    main = sorted((p for p in oj_c if not is_corrigendum(p)), key=sort_key, reverse=True)
    corr = sorted((p for p in oj_c if is_corrigendum(p)), key=sort_key, reverse=True)
    rest = [p for p in http if not is_oj_c(p)]
    out: list[str] = []
    for p in (*main, *corr, *rest):
        uri = p.get("uri") or ""
        if uri not in out:
            out.append(uri)
    return out


def preferred_publication_uri(pubs: list[dict]) -> str | None:
    """The single-document URI a stage 01 fetches for a GI, or None."""
    uris = ordered_publication_uris(pubs)
    return uris[0] if uris else None
