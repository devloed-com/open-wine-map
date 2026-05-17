"""VIVC (Vitis International Variety Catalogue) — search + passport-page parser.

VIVC is maintained by the Julius Kühn-Institut, Geilweilerhof (Germany) at
https://www.vivc.de/ . It is the most thorough public grapevine-cultivar
reference (~23k accessions, dense FR/ES/PT synonym coverage, stable VIVC
IDs).

This module is a *spike* helper for stage 02g. It does not yet make any
claim about licence (JKI publishes no explicit data-redistribution
licence). Downstream consumers should ship VIVC IDs + locally-keyed
synonym strings only, until JKI grants explicit CC-BY-SA permission.

Three entry points:

- `search_cultivarname(session, text)` — POSTs the cultivarname/index
  form with `cultivarnames=cultivarn` (search both prime names and
  synonyms) and `text=<NAME>`, returns the raw HTML.
- `parse_search_results(html)` — extracts the result rows as
  `[{cultivar_name, prime_name, vivc_id, color, country}, …]`.
- `parse_passport(html)` — extracts the kv-attribute fields and the
  synonym list (with each synonym's per-country "Official name in X"
  flag).

The codebase prefers stdlib + regex over bs4/lxml (mirroring
`scripts/es/02_extract_pliegos.py`), so this module follows the same
pattern.
"""

from __future__ import annotations

import html
import re
import time
import unicodedata
from dataclasses import dataclass
from urllib.parse import quote

import requests

BASE = "https://www.vivc.de/index.php"

SEARCH_URL = (
    BASE
    + "?r=cultivarname%2Findex"
    + "&CultivarnameSearch%5Bcultivarnames%5D=cultivarn"
    + "&CultivarnameSearch%5Btext%5D={q}"
)

PASSPORT_URL = BASE + "?r=passport%2Fview&id={vid}"


# --- HTTP -------------------------------------------------------------------


def _get_with_retry(
    session: requests.Session, url: str, timeout: float, retries: int
) -> str:
    """GET with retry-on-timeout / 5xx. VIVC's upstream (Yii/MySQL) can stall
    for 30–60s under cultivarname-index load and occasionally returns a 504
    from the edge; backoff is 5s, 15s, 30s."""
    delay = 5.0
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=timeout)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
        else:
            if r.status_code < 500:
                r.raise_for_status()
                return r.text
            last_exc = requests.HTTPError(f"{r.status_code} {r.reason}", response=r)
        if attempt < retries:
            time.sleep(delay)
            delay *= 3
    raise last_exc if last_exc else requests.RequestException("unknown error")


def search_cultivarname(
    session: requests.Session, text: str, timeout: float = 90.0, retries: int = 2
) -> str:
    """Search the VIVC cultivarname index across both prime names and synonyms.
    Returns raw HTML."""
    return _get_with_retry(session, SEARCH_URL.format(q=quote(text)), timeout, retries)


def fetch_passport(
    session: requests.Session, vivc_id: int, timeout: float = 90.0, retries: int = 2
) -> str:
    return _get_with_retry(session, PASSPORT_URL.format(vid=vivc_id), timeout, retries)


# --- Search-results parser --------------------------------------------------


@dataclass(frozen=True)
class SearchRow:
    cultivar_name: str
    prime_name: str
    vivc_id: int
    color: str
    country: str


_TBODY_RE = re.compile(r"<tbody>(.*?)</tbody>", re.DOTALL)
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _cell_text(raw: str) -> str:
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub("", raw))).strip()


def parse_search_results(raw: str) -> list[SearchRow]:
    """Parse the cultivarname/index result grid. Returns one SearchRow per
    `<tr>` in the first `<tbody>`. Empty/`No results found.` tbody → []."""
    m = _TBODY_RE.search(raw)
    if not m:
        return []
    body = m.group(1)
    if "No results found" in body:
        return []
    rows: list[SearchRow] = []
    for tr in _ROW_RE.findall(body):
        cells = [_cell_text(c) for c in _CELL_RE.findall(tr)]
        if len(cells) < 6:
            continue
        try:
            vivc_id = int(cells[2])
        except ValueError:
            continue
        rows.append(
            SearchRow(
                cultivar_name=cells[0],
                prime_name=cells[1],
                vivc_id=vivc_id,
                color=cells[4],
                country=cells[5],
            )
        )
    return rows


# --- Passport-page parser ---------------------------------------------------


_FIELD_RE = re.compile(
    r'<th[^>]*>\s*([^<]+?)\s*</th>\s*<td[^>]*>\s*<div class="kv-attribute">(.*?)</div>',
    re.DOTALL,
)

# Synonyms section: "<th...>Synonyms: <N></th>" then a kv-grid-table whose
# cells are each either <a>NAME</a> or <span ...>NAME</span>. Some <a> carry
# title="Official name in PORTUGAL" (etc.) — capture that.
_SYNONYMS_HEAD_RE = re.compile(r"Synonyms:\s*(\d+)\s*</th>", re.IGNORECASE)
_SYN_ITEM_RE = re.compile(
    r"<(?P<tag>a|span)\b(?P<attrs>[^>]*)>(?P<name>[^<]+)</(?P=tag)>",
    re.DOTALL,
)
_TITLE_ATTR_RE = re.compile(r'\btitle="([^"]*)"', re.IGNORECASE)
_OFFICIAL_RE = re.compile(r"Official name in\s+(.+)", re.IGNORECASE)


@dataclass(frozen=True)
class Synonym:
    name: str
    official_in: str | None  # country if flagged "Official name in X", else None


@dataclass(frozen=True)
class Passport:
    vivc_id: int
    prime_name: str
    color: str  # NOIR / BLANC / GRIS / ROUGE / ROSE / NOT SPECIFIED / ''
    country: str  # country of origin
    species: str
    parent1: str | None
    parent2: str | None
    pedigree_confirmed: bool
    synonyms: list[Synonym]
    fields: dict[str, str]  # all raw kv-attribute fields, for forward-compat


def _extract_passport_fields(raw: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for m in _FIELD_RE.finditer(raw):
        label = _WS_RE.sub(" ", html.unescape(m.group(1))).strip()
        val = _WS_RE.sub(" ", html.unescape(_TAG_RE.sub("", m.group(2)))).strip()
        fields[label] = val
    return fields


def _extract_synonyms(raw: str) -> list[Synonym]:
    head = _SYNONYMS_HEAD_RE.search(raw)
    if not head:
        return []
    start = head.end()
    end = raw.find("</table>", start)
    block = raw[start : end if end != -1 else len(raw)]
    out: list[Synonym] = []
    seen: set[str] = set()
    for m in _SYN_ITEM_RE.finditer(block):
        name = html.unescape(m.group("name").strip())
        if not name or name.lower() in ("synonyms", "literature") or name in seen:
            continue
        seen.add(name)
        title_match = _TITLE_ATTR_RE.search(m.group("attrs") or "")
        official_in: str | None = None
        if title_match:
            om = _OFFICIAL_RE.match(html.unescape(title_match.group(1).strip()))
            if om:
                official_in = om.group(1).strip()
        out.append(Synonym(name=name, official_in=official_in))
    return out


def parse_passport(raw: str) -> Passport:
    """Parse a passport-view page into a Passport record."""
    fields = _extract_passport_fields(raw)
    try:
        vivc_id = int(fields.get("Variety number VIVC", "").strip())
    except ValueError:
        vivc_id = 0
    return Passport(
        vivc_id=vivc_id,
        prime_name=fields.get("Prime name", "").strip(),
        color=fields.get("Color of berry skin", "").strip(),
        country=fields.get("Country or region of origin of the variety", "").strip(),
        species=fields.get("Species", "").strip(),
        parent1=fields.get("Prime name of parent 1") or None,
        parent2=fields.get("Prime name of parent 2") or None,
        pedigree_confirmed=bool(fields.get("Pedigree confirmed by markers")),
        synonyms=_extract_synonyms(raw),
        fields=fields,
    )


# --- Name normalisation (for slug↔result matching) --------------------------


def normalise(name: str) -> str:
    """Strip diacritics, uppercase, collapse internal whitespace.
    VIVC stores names in uppercase ASCII (no diacritics)."""
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.upper()
    n = _WS_RE.sub(" ", n).strip()
    # VIVC sometimes uses hyphen-free / apostrophe-free forms.
    return n


def pick_best(
    rows: list[SearchRow],
    query: str,
) -> tuple[SearchRow | None, str]:
    """Choose the best result row for `query`.

    Strategy:
      1. Among rows whose `cultivar_name` exactly matches `query` (normalised),
         if all share the same VIVC ID → unique match. If multiple distinct
         VIVC IDs → ambiguous.
      2. Else among rows whose `prime_name` exactly matches `query` →
         unique → match; multiple → ambiguous.
      3. Else: no match.

    Returns `(row, status)` where status ∈ {"exact-cultivar",
    "exact-prime", "ambiguous-cultivar", "ambiguous-prime", "miss"}.
    """
    q = normalise(query)

    exact_cultivar = [r for r in rows if normalise(r.cultivar_name) == q]
    if exact_cultivar:
        ids = {r.vivc_id for r in exact_cultivar}
        if len(ids) == 1:
            return exact_cultivar[0], "exact-cultivar"
        return None, "ambiguous-cultivar"

    exact_prime = [r for r in rows if normalise(r.prime_name) == q]
    if exact_prime:
        ids = {r.vivc_id for r in exact_prime}
        if len(ids) == 1:
            return exact_prime[0], "exact-prime"
        return None, "ambiguous-prime"

    return None, "miss"
