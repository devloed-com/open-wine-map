"""Italian province reference data + province/commune text scanners.

The unit that pins an Italian wine to its administrative regione is the
**provincia**, not a free-text regione name. A documento unico's
geographic-area section ("Zona geografica delimitata") and a MASAF
disciplinare's Article 3 enumerate the wine's own provinces and communes;
a province → regione mapping is unambiguous (each of Italy's 107
provinces belongs to exactly one of the 20 regioni). The terroir /
legame text, by contrast, routinely names a *neighbouring* regione
(comparisons, river sources, the Apennine watershed) — so a bare
first-mention regione scan latches onto the wrong one.

This module is the lower-level half of the IT region machinery:
  - `PROVINCE_TABLE` — the 107 provinces, each `(istat_code, sigla,
    name, regione)`. ISTAT 3-digit codes verified against the Eurostat
    GISCO 2024 LAU layer (every IT `GISCO_ID` prefix is covered).
  - `regione_for_istat_code` — the geometry side: a GISCO commune's
    `GISCO_ID` is `IT_<istat_code><commune>`; its 3-digit prefix is the
    province. Used by `scripts/audit_it_regions.py`.
  - `scan_province_mentions` — the text side: province sigle ("(CN)")
    and "provincia di NAME" anchors → a Counter of regioni.
  - `load_comune_regione_map` / `scan_commune_mentions` — the commune
    side: build a normalised commune-name → regione index from GISCO
    LAU, then tally the communes named in an area description. This is
    the strongest signal: a disciplinare that never writes "provincia
    di …" or a regione name still lists every commune by name.

`scripts/_lib/it/region.py` is the higher-level half — it combines
these signals with the curated `regione_by_file_number.json` fallback.
"""

from __future__ import annotations

import functools
import re
import unicodedata
from collections import Counter
from pathlib import Path


def _norm(s: str) -> str:
    """Lowercase, strip diacritics, collapse non-alphanumerics to single
    spaces. Shared normaliser for province / commune / regione names."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


# The 20 Italian regioni, canonical ISTAT spelling.
REGIONI: tuple[str, ...] = (
    "Abruzzo", "Basilicata", "Calabria", "Campania", "Emilia-Romagna",
    "Friuli-Venezia Giulia", "Lazio", "Liguria", "Lombardia", "Marche",
    "Molise", "Piemonte", "Puglia", "Sardegna", "Sicilia", "Toscana",
    "Trentino-Alto Adige", "Umbria", "Valle d'Aosta", "Veneto",
)
_REGIONE_ORDER = {r: i for i, r in enumerate(REGIONI)}


# (ISTAT 3-digit code, 2-letter sigla, canonical name, regione).
# 107 rows — every administrative province-level unit. The ISTAT codes
# match the distinct `IT_<code>` prefixes in GISCO LAU 2024 exactly.
PROVINCE_TABLE: tuple[tuple[str, str, str, str], ...] = (
    # Piemonte
    ("001", "TO", "Torino", "Piemonte"),
    ("002", "VC", "Vercelli", "Piemonte"),
    ("003", "NO", "Novara", "Piemonte"),
    ("004", "CN", "Cuneo", "Piemonte"),
    ("005", "AT", "Asti", "Piemonte"),
    ("006", "AL", "Alessandria", "Piemonte"),
    ("096", "BI", "Biella", "Piemonte"),
    ("103", "VB", "Verbano-Cusio-Ossola", "Piemonte"),
    # Valle d'Aosta
    ("007", "AO", "Aosta", "Valle d'Aosta"),
    # Lombardia
    ("012", "VA", "Varese", "Lombardia"),
    ("013", "CO", "Como", "Lombardia"),
    ("014", "SO", "Sondrio", "Lombardia"),
    ("015", "MI", "Milano", "Lombardia"),
    ("016", "BG", "Bergamo", "Lombardia"),
    ("017", "BS", "Brescia", "Lombardia"),
    ("018", "PV", "Pavia", "Lombardia"),
    ("019", "CR", "Cremona", "Lombardia"),
    ("020", "MN", "Mantova", "Lombardia"),
    ("097", "LC", "Lecco", "Lombardia"),
    ("098", "LO", "Lodi", "Lombardia"),
    ("108", "MB", "Monza e della Brianza", "Lombardia"),
    # Trentino-Alto Adige
    ("021", "BZ", "Bolzano", "Trentino-Alto Adige"),
    ("022", "TN", "Trento", "Trentino-Alto Adige"),
    # Veneto
    ("023", "VR", "Verona", "Veneto"),
    ("024", "VI", "Vicenza", "Veneto"),
    ("025", "BL", "Belluno", "Veneto"),
    ("026", "TV", "Treviso", "Veneto"),
    ("027", "VE", "Venezia", "Veneto"),
    ("028", "PD", "Padova", "Veneto"),
    ("029", "RO", "Rovigo", "Veneto"),
    # Friuli-Venezia Giulia
    ("030", "UD", "Udine", "Friuli-Venezia Giulia"),
    ("031", "GO", "Gorizia", "Friuli-Venezia Giulia"),
    ("032", "TS", "Trieste", "Friuli-Venezia Giulia"),
    ("093", "PN", "Pordenone", "Friuli-Venezia Giulia"),
    # Liguria
    ("008", "IM", "Imperia", "Liguria"),
    ("009", "SV", "Savona", "Liguria"),
    ("010", "GE", "Genova", "Liguria"),
    ("011", "SP", "La Spezia", "Liguria"),
    # Emilia-Romagna
    ("033", "PC", "Piacenza", "Emilia-Romagna"),
    ("034", "PR", "Parma", "Emilia-Romagna"),
    ("035", "RE", "Reggio nell'Emilia", "Emilia-Romagna"),
    ("036", "MO", "Modena", "Emilia-Romagna"),
    ("037", "BO", "Bologna", "Emilia-Romagna"),
    ("038", "FE", "Ferrara", "Emilia-Romagna"),
    ("039", "RA", "Ravenna", "Emilia-Romagna"),
    ("040", "FC", "Forlì-Cesena", "Emilia-Romagna"),
    ("099", "RN", "Rimini", "Emilia-Romagna"),
    # Toscana
    ("045", "MS", "Massa-Carrara", "Toscana"),
    ("046", "LU", "Lucca", "Toscana"),
    ("047", "PT", "Pistoia", "Toscana"),
    ("048", "FI", "Firenze", "Toscana"),
    ("049", "LI", "Livorno", "Toscana"),
    ("050", "PI", "Pisa", "Toscana"),
    ("051", "AR", "Arezzo", "Toscana"),
    ("052", "SI", "Siena", "Toscana"),
    ("053", "GR", "Grosseto", "Toscana"),
    ("100", "PO", "Prato", "Toscana"),
    # Umbria
    ("054", "PG", "Perugia", "Umbria"),
    ("055", "TR", "Terni", "Umbria"),
    # Marche
    ("041", "PU", "Pesaro e Urbino", "Marche"),
    ("042", "AN", "Ancona", "Marche"),
    ("043", "MC", "Macerata", "Marche"),
    ("044", "AP", "Ascoli Piceno", "Marche"),
    ("109", "FM", "Fermo", "Marche"),
    # Lazio
    ("056", "VT", "Viterbo", "Lazio"),
    ("057", "RI", "Rieti", "Lazio"),
    ("058", "RM", "Roma", "Lazio"),
    ("059", "LT", "Latina", "Lazio"),
    ("060", "FR", "Frosinone", "Lazio"),
    # Abruzzo
    ("066", "AQ", "L'Aquila", "Abruzzo"),
    ("067", "TE", "Teramo", "Abruzzo"),
    ("068", "PE", "Pescara", "Abruzzo"),
    ("069", "CH", "Chieti", "Abruzzo"),
    # Molise
    ("070", "CB", "Campobasso", "Molise"),
    ("094", "IS", "Isernia", "Molise"),
    # Campania
    ("061", "CE", "Caserta", "Campania"),
    ("062", "BN", "Benevento", "Campania"),
    ("063", "NA", "Napoli", "Campania"),
    ("064", "AV", "Avellino", "Campania"),
    ("065", "SA", "Salerno", "Campania"),
    # Puglia
    ("071", "FG", "Foggia", "Puglia"),
    ("072", "BA", "Bari", "Puglia"),
    ("073", "TA", "Taranto", "Puglia"),
    ("074", "BR", "Brindisi", "Puglia"),
    ("075", "LE", "Lecce", "Puglia"),
    ("110", "BT", "Barletta-Andria-Trani", "Puglia"),
    # Basilicata
    ("076", "PZ", "Potenza", "Basilicata"),
    ("077", "MT", "Matera", "Basilicata"),
    # Calabria
    ("078", "CS", "Cosenza", "Calabria"),
    ("079", "CZ", "Catanzaro", "Calabria"),
    ("080", "RC", "Reggio di Calabria", "Calabria"),
    ("101", "KR", "Crotone", "Calabria"),
    ("102", "VV", "Vibo Valentia", "Calabria"),
    # Sicilia
    ("081", "TP", "Trapani", "Sicilia"),
    ("082", "PA", "Palermo", "Sicilia"),
    ("083", "ME", "Messina", "Sicilia"),
    ("084", "AG", "Agrigento", "Sicilia"),
    ("085", "CL", "Caltanissetta", "Sicilia"),
    ("086", "EN", "Enna", "Sicilia"),
    ("087", "CT", "Catania", "Sicilia"),
    ("088", "RG", "Ragusa", "Sicilia"),
    ("089", "SR", "Siracusa", "Sicilia"),
    # Sardegna
    ("090", "SS", "Sassari", "Sardegna"),
    ("091", "NU", "Nuoro", "Sardegna"),
    ("092", "CA", "Cagliari", "Sardegna"),
    ("095", "OR", "Oristano", "Sardegna"),
    ("111", "SU", "Sud Sardegna", "Sardegna"),
)

assert len(PROVINCE_TABLE) == 107, f"province table has {len(PROVINCE_TABLE)} rows"
assert {r for *_, r in PROVINCE_TABLE} == set(REGIONI), "province/regione mismatch"


_REGIONE_BY_CODE: dict[str, str] = {code: reg for code, _s, _n, reg in PROVINCE_TABLE}
_REGIONE_BY_SIGLA: dict[str, str] = {sig: reg for _c, sig, _n, reg in PROVINCE_TABLE}

# Province name (normalised) → regione, plus common spelling variants.
# Short variants ("Pesaro", "Massa") are matched only inside a
# "provincia di …" window, so they cannot collide with prose.
_REGIONE_BY_PROV_NAME: dict[str, str] = {_norm(n): r for _c, _s, n, r in PROVINCE_TABLE}
_PROV_NAME_VARIANTS: dict[str, str] = {
    "verbania": "Piemonte",
    "monza e brianza": "Lombardia",
    "monza": "Lombardia",
    "bozen": "Trentino-Alto Adige",
    "alto adige": "Trentino-Alto Adige",
    "spezia": "Liguria",
    "reggio emilia": "Emilia-Romagna",
    "forli": "Emilia-Romagna",
    "forli e cesena": "Emilia-Romagna",
    "massa e carrara": "Toscana",
    "massa": "Toscana",
    "pesaro ed urbino": "Marche",
    "pesaro urbino": "Marche",
    "pesaro": "Marche",
    "aquila": "Abruzzo",
    "reggio calabria": "Calabria",
}
_REGIONE_BY_PROV_NAME.update(_PROV_NAME_VARIANTS)

# Province names sorted longest-first so multi-word names ("Reggio
# nell'Emilia") match before any embedded shorter name.
_PROV_NAMES_BY_LEN: tuple[str, ...] = tuple(
    sorted(_REGIONE_BY_PROV_NAME, key=lambda n: -len(n))
)


def regione_for_istat_code(istat_code: str) -> str:
    """ISTAT 3-digit province code → regione, or '' if unknown.

    The code is the prefix of a GISCO LAU `GISCO_ID` numeric part
    (`IT_004081` → province `004` → Cuneo → Piemonte)."""
    return _REGIONE_BY_CODE.get((istat_code or "")[:3], "")


def regione_for_gisco_id(gisco_id: str) -> str:
    """GISCO LAU `GISCO_ID` ('IT_004081') → regione."""
    num = gisco_id.split("_", 1)[1] if "_" in (gisco_id or "") else ""
    return regione_for_istat_code(num)


_SIGLA_RE = re.compile(r"\(\s*([A-Z]{2})\s*\)")
# "provincia/province/provincie di …" — optionally "autonoma" — capturing
# the clause that follows (a province name or a short province list).
_PROV_ANCHOR_RE = re.compile(
    r"provinc(?:ia|ie|e)\s+(?:autonom[ae]\s+)?di\s+([^.;:\n]{0,200})",
    re.IGNORECASE,
)


def scan_province_mentions(text: str) -> Counter:
    """Tally regioni named in `text` by **province**, two ways:
      - province sigle in parentheses — "(CN)", "(VR)";
      - "provincia/province di NAME" anchors, scanning the following
        clause for one or more province names.
    Both are anchored, so they pick up the wine's *own* provinces and
    not a regione mentioned loosely in surrounding prose."""
    tally: Counter = Counter()
    if not text:
        return tally
    for m in _SIGLA_RE.finditer(text):
        reg = _REGIONE_BY_SIGLA.get(m.group(1))
        if reg:
            tally[reg] += 1
    for m in _PROV_ANCHOR_RE.finditer(text):
        window = " " + _norm(m.group(1)) + " "
        for name in _PROV_NAMES_BY_LEN:
            if f" {name} " in window:
                tally[_REGIONE_BY_PROV_NAME[name]] += 1
    return tally


# A geo-area description ends in a boundary-tracing prose ("la linea di
# delimitazione segue il torrente …, partendo dal ponte …"). That prose
# is pure noise for region derivation — it names roads, hamlets and
# hydronyms, many of which collide with tiny commune names elsewhere in
# Italy ("Canale", "Terzo", "Viale" are Piedmontese comuni).
# `truncate_at_delimitation` drops everything from the prose onward,
# keeping the commune enumeration that precedes it. The markers are
# boundary-prose-specific on purpose: a bare "così delimitata" can just
# as well introduce a *commune list* (e.g. the "Vicenza" DOC), so it
# must not trigger a cut.
_DELIM_MARKER_RE = re.compile(
    r"\bpartendo\s+da|\ba\s+partire\s+da\b"
    r"|\blinea\s+di\s+delimitazione\b|\bdelimitazione\s+segue\b",
)


def _ascii_lower(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def truncate_at_delimitation(text: str) -> str:
    """Return `text` up to the first boundary-prose marker (or the whole
    string when there is none). Guards against a marker landing in the
    section heading by requiring an offset past the first few words."""
    if not text:
        return text
    m = _DELIM_MARKER_RE.search(_ascii_lower(text))
    if m and m.start() > 40:
        return text[:m.start()]
    return text


_TOKEN_RE = re.compile(r"[a-z0-9]+|[,;:]")
_LIST_PUNCT = {",", ";", ":"}
_LIST_TAIL = {"e", "ed"}
# Words that, before a "di NAME", mark NAME as a single commune —
# "comune di X", "territorio comunale di X", "territori amministrativi
# … di X", "parte di quello di X". Lets a one-commune wine be counted
# even with no comma list.
_COMMUNE_ANCHOR = {
    "comune", "comuni", "comunale", "comunali",
    "amministrativo", "amministrativi", "territorio", "territori",
    "quello", "quella", "quelli", "quelle",
}

# Wine colour / style words that are also tiny commune names (Bianco in
# Calabria, Dolcè in Veneto, …). They saturate every disciplinare's
# wine-type enumeration ("bianco, rosso e rosato"), so a bare one-token
# match on them is noise, never a real commune reference.
_COMMUNE_STOPWORDS = {
    "bianco", "bianchi", "rosso", "rossi", "rosato", "rosati",
    "dolce", "dolci", "secco", "spumante", "frizzante", "passito",
    "novello", "classico", "superiore", "riserva",
}

_SAINT_PREFIXES = ("san ", "sant ", "santo ", "santa ", "santi ", "ss ")


def _commune_aliases(norm_name: str) -> list[str]:
    """A normalised commune name plus a 'San X' → 'S X' alias, so an
    abbreviated disciplinare spelling ("S. Michele Mondovì") still
    matches the GISCO official name ("San Michele Mondovì")."""
    out = [norm_name]
    for pref in _SAINT_PREFIXES:
        if norm_name.startswith(pref):
            out.append("s " + norm_name[len(pref):])
            break
    return out


def resolve_gisco_lau(gisco_dir: Path | str) -> Path | None:
    """Locate the Eurostat GISCO LAU shapefile zip under `gisco_dir`.
    The ES / AT stages cache it under one of two filenames; return the
    first that exists, or None."""
    gisco_dir = Path(gisco_dir)
    for name in ("LAU_RG_01M_2024_3035.shp.zip", "lau-eu-2024-01m.shp.zip"):
        candidate = gisco_dir / name
        if candidate.exists():
            return candidate
    return None


@functools.lru_cache(maxsize=4)
def load_comune_regione_map(gisco_lau_zip: str) -> dict[str, frozenset]:
    """Build `{normalised commune name: frozenset(regioni)}` from the
    Eurostat GISCO LAU layer. A name maps to >1 regione only when two
    distinct communes in different regioni share it (≈ a few dozen
    cases) — `scan_commune_mentions` skips those as ambiguous.

    Path-keyed `lru_cache` so the stage scripts pay the GISCO read once.
    Geometry is dropped at read time — only the attribute table is
    needed. Returns `{}` when the file is absent (callers degrade to
    the province / file-number signals)."""
    path = Path(gisco_lau_zip)
    if not path.exists():
        return {}
    try:
        import pyogrio
        df = pyogrio.read_dataframe(
            path, read_geometry=False, columns=["GISCO_ID", "CNTR_CODE", "LAU_NAME"],
        )
        rows = zip(df["GISCO_ID"], df["CNTR_CODE"], df["LAU_NAME"])
    except Exception:  # noqa: BLE001 — fall back to geopandas
        import geopandas as gpd
        gdf = gpd.read_file(path)
        rows = zip(gdf["GISCO_ID"], gdf["CNTR_CODE"], gdf["LAU_NAME"])

    by_name: dict[str, set[str]] = {}
    for gisco_id, cntr, lau_name in rows:
        if cntr != "IT" or not lau_name:
            continue
        reg = regione_for_gisco_id(gisco_id or "")
        if not reg:
            continue
        # GISCO carries bilingual names ("Bolzano/Bozen") in the
        # autonomous provinces — index the whole name and each half.
        parts = [lau_name] + [p for p in str(lau_name).split("/") if p.strip()]
        for part in parts:
            norm = _norm(part)
            if not norm:
                continue
            for alias in _commune_aliases(norm):
                by_name.setdefault(alias, set()).add(reg)
    return {name: frozenset(regs) for name, regs in by_name.items()}


def scan_commune_mentions(text: str, comune_map: dict[str, frozenset]) -> Counter:
    """Tally regioni by the **communes** named in `text`. This is the
    strongest signal — a disciplinare always lists its communes by name
    even when it never writes a province or regione name.

    A longest-match-first n-gram sweep (commune names run 1–4 tokens),
    but a match is only counted when it sits in a **list context** — it
    is comma / semicolon / colon-adjacent, follows an "e"/"ed" list
    tail, or follows a "comune/i di" anchor. That gate is what keeps a
    Piedmontese hamlet's worth of generic words ("il canale", "il
    terzo") in boundary prose from being mistaken for the comuni
    Canale and Terzo. Pass text already run through
    `truncate_at_delimitation`. Communes whose name is shared across
    regioni are skipped as ambiguous."""
    tally: Counter = Counter()
    if not text or not comune_map:
        return tally
    toks = _TOKEN_RE.findall(_ascii_lower(text))
    n = len(toks)
    i = 0
    while i < n:
        if toks[i] in _LIST_PUNCT:
            i += 1
            continue
        # Longest run of consecutive word tokens (a punctuation token
        # breaks a multi-word commune name).
        run: list[str] = []
        j = i
        while j < n and toks[j] not in _LIST_PUNCT and len(run) < 4:
            run.append(toks[j])
            j += 1
        regs = None
        matched = 0
        for length in range(len(run), 0, -1):
            cand = " ".join(run[:length])
            if length == 1 and cand in _COMMUNE_STOPWORDS:
                continue
            regs = comune_map.get(cand)
            if regs:
                matched = length
                break
        if not matched:
            i += 1
            continue
        prev = toks[i - 1] if i > 0 else ""
        prev2 = toks[i - 2] if i > 1 else ""
        nxt = toks[i + matched] if i + matched < n else ""
        in_list = (
            prev in _LIST_PUNCT
            or nxt in (",", ";")
            or prev in _LIST_TAIL
            or (prev == "di" and prev2 in _COMMUNE_ANCHOR)
        )
        if in_list and len(regs) == 1:
            tally[next(iter(regs))] += 1
        i += matched
    return tally


def dominant_regione(tally: Counter) -> str:
    """The most-tallied regione; deterministic tie-break by `REGIONI`
    order. '' for an empty tally."""
    if not tally:
        return ""
    return max(tally.items(), key=lambda kv: (kv[1], -_REGIONE_ORDER[kv[0]]))[0]
