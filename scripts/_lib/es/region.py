"""Derive the Spanish Comunidad Autónoma (CCAA) for each ES wine record.

The pliego text is the primary signal: most pliegos mention the
producing region as "Comunidad Autónoma de <X>" or "C.A. de <X>" or
"Comunitat Autònoma de <X>" (Catalan) somewhere in the geo-area or
link-to-terroir sections. When no mention is detectable, we fall back
to a hand-curated map keyed by the EU file number. Wines that aren't
in the curated map and have no text mention get the placeholder
"ESPAÑA" so they still show up under a region in the sidebar.

CCAA names are returned in the canonical Spanish form (so the
sidebar lists them consistently regardless of which co-official
language the pliego happened to be written in).
"""

from __future__ import annotations

import re

# Canonical Spanish CCAA names. Co-official-language variants normalise
# to these (Cataluña ≡ Catalunya ≡ Catalonia; País Vasco ≡ Euskadi
# ≡ Basque Country; Galicia ≡ Galiza; Comunidad Valenciana ≡ Comunitat
# Valenciana; Castilla y León ≡ Castela e León; etc.).
CCAA_NAMES = (
    "Andalucía", "Aragón", "Asturias", "Baleares", "Canarias",
    "Cantabria", "Castilla y León", "Castilla-La Mancha", "Cataluña",
    "Comunidad Valenciana", "Extremadura", "Galicia", "La Rioja",
    "Madrid", "Murcia", "Navarra", "País Vasco",
)

# Aliases mapping co-official + variant forms → canonical CCAA name.
CCAA_ALIASES: dict[str, str] = {
    # Catalan / Valencian / Galician variants
    "catalunya": "Cataluña",
    "catalonia": "Cataluña",
    "comunitat valenciana": "Comunidad Valenciana",
    "valencian community": "Comunidad Valenciana",
    "comunitat de madrid": "Madrid",
    "comunidad de madrid": "Madrid",
    "comunidad foral de navarra": "Navarra",
    "nafarroa": "Navarra",
    "comunitat foral de navarra": "Navarra",
    "galiza": "Galicia",
    "euskadi": "País Vasco",
    "basque country": "País Vasco",
    "euskal herria": "País Vasco",  # broader but commonly used in pliegos
    "principado de asturias": "Asturias",
    "región de murcia": "Murcia",
    "regio de murcia": "Murcia",
    "castella i lleó": "Castilla y León",
    "castela e leon": "Castilla y León",
    "castilla la mancha": "Castilla-La Mancha",
    "islas baleares": "Baleares",
    "illes balears": "Baleares",
    "illas baleares": "Baleares",
    "islas canarias": "Canarias",
    "comunidad autónoma de la rioja": "La Rioja",
    # Article "La" is consumed by the leadin pattern (de la / del / etc.),
    # so a bare "Rioja" capture must still resolve to "La Rioja" CCAA.
    "rioja": "La Rioja",
    # Same for Mancha — pliegos say "Castilla-La Mancha" but the leadin
    # may eat the "La" article. Both forms map to the canonical CCAA.
    "mancha": "Castilla-La Mancha",
    # Spanish "del + capital noun" → País Vasco / Principado de Asturias
    "país vasco": "País Vasco",
    "principado": "Asturias",  # "Principado de Asturias" → "de Asturias" eaten
    # Common ALL-CAPS in pliegos
    "ANDALUCIA": "Andalucía",
    "ARAGON": "Aragón",
}
for canonical in CCAA_NAMES:
    CCAA_ALIASES.setdefault(canonical.lower(), canonical)
# Add the aliases without their CCAA-canonical lowercase entries
CCAA_ALIASES["la rioja"] = "La Rioja"


def _normalise(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


# Patterns for the "Comunidad Autónoma de X" lead-in. The CCAA name
# follows; we capture up to the next punctuation / linebreak. Multiple
# language variants because pliegos may be in any co-official language.
_CCAA_LEADIN_RE = re.compile(
    r"(?:"
    r"Comunidad\s+Autónoma\s+(?:de(?:\s+la|\s+los|\s+las)?\s+|del\s+|de\s+)?"
    r"|Comunitat\s+Autònoma\s+(?:de(?:\s+la)?\s+|del\s+)?"
    r"|C\.\s*A\.?\s+de\s+|CCAA\s+(?:de\s+)?"
    r"|Principado\s+de\s+|Comunidad\s+Foral\s+de\s+"
    r"|Comunitat\s+Foral\s+de\s+|Región\s+de\s+|Regió\s+de\s+"
    r")"
    r"(?P<ccaa>[A-ZÁÉÍÓÚÑÜa-záéíóúñü' \-]{3,40}?)"
    r"(?=[,.;:\n)]|\s+(?:y|e|o|hasta|en|con|que)\b)",
    re.IGNORECASE,
)


def _resolve_alias(raw: str) -> str | None:
    """Map a captured CCAA candidate to a canonical name. Returns None
    when no match can be made — caller can then try the next mention or
    the fallback."""
    n = _normalise(raw)
    if n in CCAA_ALIASES:
        return CCAA_ALIASES[n]
    # Strip trailing connectors that the regex might have included
    n = re.sub(r"\s+(y|e|o)\s.*$", "", n)
    if n in CCAA_ALIASES:
        return CCAA_ALIASES[n]
    return None


# Hand-curated fallback for wines whose pliego text doesn't yield a
# clean CCAA mention. Keyed by slug (more stable than file_number for
# manual curation; file_number can change on amendments). Add entries
# as needed when audit_es_coverage flags wines without a region.
# Keys are the slug emitted by stage 02 (slugify of protectedNames[0]).
# An empty value means "no region" — the wine appears top-level in the
# appellation list but doesn't get bucketed under any region heading.
# Use this for genuinely multi-region wines (Cava spans Catalonia,
# Aragón, Rioja, Navarra, Extremadura, País Vasco, Valencia; the
# Castilla IGP spans 5 CCAAs).
CCAA_OVERRIDES: dict[str, str] = {
    "cava": "",
    "castilla": "",
    "islas-canarias": "Canarias",  # umbrella DOP for the islands
    # Cataluña DOPs (the pliegos tend to use Catalan-language place names
    # that don't trigger our Spanish "provincia de" regex)
    "alella": "Cataluña",
    "cataluna": "Cataluña",
    "conca-de-barbera": "Cataluña",
    "costers-del-segre": "Cataluña",
    "emporda": "Cataluña",
    "montsant": "Cataluña",
    "penedes": "Cataluña",
    "pla-de-bages": "Cataluña",
    "priorat": "Cataluña",
    "tarragona": "Cataluña",
    # Comunidad Valenciana
    "alicante": "Comunidad Valenciana",
    "valencia": "Comunidad Valenciana",
    "los-balagueses": "Comunidad Valenciana",
    "vera-de-estenas": "Comunidad Valenciana",
    "el-terrerazo": "Comunidad Valenciana",
    "utiel-requena": "Comunidad Valenciana",
    # Castilla-La Mancha (Vinos de Pago + Albacete-area DOPs)
    "almansa": "Castilla-La Mancha",
    "campo-de-calatrava": "Castilla-La Mancha",
    "casa-del-blanco": "Castilla-La Mancha",
    "dehesa-del-carrizal": "Castilla-La Mancha",
    "dominio-de-valdepusa": "Castilla-La Mancha",
    "finca-elez": "Castilla-La Mancha",
    "la-jaraba": "Castilla-La Mancha",
    "los-cerrillos": "Castilla-La Mancha",
    "manchuela": "Castilla-La Mancha",
    "mentrida": "Castilla-La Mancha",
    "pago-florentino": "Castilla-La Mancha",
    "ribera-del-jucar": "Castilla-La Mancha",
    "ucles": "Castilla-La Mancha",
    "vallegarcia": "Castilla-La Mancha",
    # Andalucía
    "jerez-xeres-sherry": "Andalucía",
    "manzanilla-de-sanlucar": "Andalucía",
    "condado-de-huelva": "Andalucía",
    "vino-naranja-del-condado-de-huelva": "Andalucía",
    "lebrija": "Andalucía",
    "malaga": "Andalucía",
    # Madrid
    "vinos-de-madrid": "Madrid",
    # País Vasco
    "arabako-txakolina": "País Vasco",
    "bizkaiko-txakolina": "País Vasco",
    "getariako-txakolina": "País Vasco",
    "ekain": "País Vasco",
    # Galicia (some pliegos use Galician place names that miss the regex)
    "monterrei": "Galicia",
    "ribeiras-do-morrazo": "Galicia",
    "ribeiro": "Galicia",
    # Baleares
    "binissalem": "Baleares",
    "formentera": "Baleares",
    "isla-de-menorca": "Baleares",
    "ibiza": "Baleares",
    "mallorca": "Baleares",
    "pla-i-llevant": "Baleares",
    # Canarias
    "abona": "Canarias",
    "el-hierro": "Canarias",
    "gran-canaria": "Canarias",
    "la-gomera": "Canarias",
    "la-palma": "Canarias",
    "lanzarote": "Canarias",
    "tacoronte-acentejo": "Canarias",
    "valle-de-guimar": "Canarias",
    "valle-de-la-orotava": "Canarias",
    "ycoden-daute-isora": "Canarias",
    # Aragón Vinos de Pago
    "ayles": "Aragón",
    # Navarra (pliego just says "Navarra" without "Comunidad")
    "navarra": "Navarra",
}


# Province name (Spanish or co-official form) → 2-digit INE code. Used
# to translate pliego province mentions into GISCO LAU filters.
PROVINCE_TO_INE: dict[str, str] = {
    # Andalucía
    "Almería": "04", "Cádiz": "11", "Córdoba": "14", "Granada": "18",
    "Huelva": "21", "Jaén": "23", "Málaga": "29", "Sevilla": "41",
    # Aragón
    "Huesca": "22", "Teruel": "44", "Zaragoza": "50",
    # Asturias
    "Asturias": "33",
    # Baleares
    "Illes Balears": "07", "Islas Baleares": "07", "Baleares": "07",
    # Canarias
    "Las Palmas": "35", "Santa Cruz de Tenerife": "38",
    # Cantabria
    "Cantabria": "39",
    # Castilla y León
    "Ávila": "05", "Burgos": "09", "León": "24", "Palencia": "34",
    "Salamanca": "37", "Segovia": "40", "Soria": "42",
    "Valladolid": "47", "Zamora": "49",
    # Castilla-La Mancha
    "Albacete": "02", "Ciudad Real": "13", "Cuenca": "16",
    "Guadalajara": "19", "Toledo": "45",
    # Cataluña
    "Barcelona": "08", "Girona": "17", "Gerona": "17",
    "Lleida": "25", "Lérida": "25", "Tarragona": "43",
    # Comunidad Valenciana
    "Alicante": "03", "Alacant": "03",
    "Castellón": "12", "Castelló": "12",
    "Valencia": "46", "València": "46",
    # Extremadura
    "Badajoz": "06", "Cáceres": "10",
    # Galicia
    "A Coruña": "15", "La Coruña": "15", "Coruña": "15",
    "Lugo": "27", "Ourense": "32", "Orense": "32",
    "Pontevedra": "36",
    # La Rioja
    "La Rioja": "26",
    # Madrid
    "Madrid": "28",
    # Murcia
    "Murcia": "30",
    # Navarra
    "Navarra": "31", "Nafarroa": "31",
    # País Vasco
    "Álava": "01", "Araba": "01",
    "Bizkaia": "48", "Vizcaya": "48",
    "Gipuzkoa": "20", "Guipúzcoa": "20",
}


# CCAA → list of INE province codes within it. Lets a CCAA-wide IGP
# (Castilla = "all parcels in Castilla-La Mancha territory") resolve
# to the union of all GISCO municipios in those provinces.
CCAA_TO_PROVINCE_INES: dict[str, tuple[str, ...]] = {
    "Andalucía":            ("04", "11", "14", "18", "21", "23", "29", "41"),
    "Aragón":               ("22", "44", "50"),
    "Asturias":             ("33",),
    "Baleares":             ("07",),
    "Canarias":             ("35", "38"),
    "Cantabria":            ("39",),
    "Castilla y León":      ("05", "09", "24", "34", "37", "40", "42", "47", "49"),
    "Castilla-La Mancha":   ("02", "13", "16", "19", "45"),
    "Cataluña":             ("08", "17", "25", "43"),
    "Comunidad Valenciana": ("03", "12", "46"),
    "Extremadura":          ("06", "10"),
    "Galicia":              ("15", "27", "32", "36"),
    "La Rioja":             ("26",),
    "Madrid":               ("28",),
    "Murcia":               ("30",),
    "Navarra":              ("31",),
    "País Vasco":           ("01", "20", "48"),
}


# Spanish provinces → CCAA. Most pliegos cite "Provincia de X" (the
# 50 provinces) rather than the parent Comunidad Autónoma. Build the
# inverse map so we can derive CCAA from any provincia mention.
PROVINCE_TO_CCAA: dict[str, str] = {
    # Andalucía (8)
    "Almería": "Andalucía", "Cádiz": "Andalucía", "Córdoba": "Andalucía",
    "Granada": "Andalucía", "Huelva": "Andalucía", "Jaén": "Andalucía",
    "Málaga": "Andalucía", "Sevilla": "Andalucía",
    # Aragón (3)
    "Huesca": "Aragón", "Teruel": "Aragón", "Zaragoza": "Aragón",
    # Asturias (1)
    "Asturias": "Asturias",
    # Baleares (1)
    "Illes Balears": "Baleares", "Islas Baleares": "Baleares", "Baleares": "Baleares",
    # Canarias (2)
    "Las Palmas": "Canarias", "Santa Cruz de Tenerife": "Canarias",
    # Cantabria (1)
    "Cantabria": "Cantabria",
    # Castilla y León (9)
    "Ávila": "Castilla y León", "Burgos": "Castilla y León",
    "León": "Castilla y León", "Palencia": "Castilla y León",
    "Salamanca": "Castilla y León", "Segovia": "Castilla y León",
    "Soria": "Castilla y León", "Valladolid": "Castilla y León",
    "Zamora": "Castilla y León",
    # Castilla-La Mancha (5)
    "Albacete": "Castilla-La Mancha", "Ciudad Real": "Castilla-La Mancha",
    "Cuenca": "Castilla-La Mancha", "Guadalajara": "Castilla-La Mancha",
    "Toledo": "Castilla-La Mancha",
    # Cataluña (4)
    "Barcelona": "Cataluña", "Girona": "Cataluña", "Gerona": "Cataluña",
    "Lleida": "Cataluña", "Lérida": "Cataluña",
    "Tarragona": "Cataluña",
    # Comunidad Valenciana (3)
    "Alicante": "Comunidad Valenciana", "Alacant": "Comunidad Valenciana",
    "Castellón": "Comunidad Valenciana", "Castelló": "Comunidad Valenciana",
    "Valencia": "Comunidad Valenciana", "València": "Comunidad Valenciana",
    # Extremadura (2)
    "Badajoz": "Extremadura", "Cáceres": "Extremadura",
    # Galicia (4)
    "A Coruña": "Galicia", "La Coruña": "Galicia",
    "Lugo": "Galicia", "Ourense": "Galicia", "Orense": "Galicia",
    "Pontevedra": "Galicia",
    # La Rioja (1)
    "La Rioja": "La Rioja",
    # Madrid (1)
    "Madrid": "Madrid",
    # Murcia (1)
    "Murcia": "Murcia",
    # Navarra (1)
    "Navarra": "Navarra", "Nafarroa": "Navarra",
    # País Vasco (3)
    "Álava": "País Vasco", "Araba": "País Vasco",
    "Bizkaia": "País Vasco", "Vizcaya": "País Vasco",
    "Gipuzkoa": "País Vasco", "Guipúzcoa": "País Vasco",
}

# Pattern for "Provincia de X" / "PROVINCIA DE X:" / "provincia(s) de X y Y".
# Captures one province name, fairly conservatively.
_PROVINCE_LEADIN_RE = re.compile(
    r"(?:provincia|província)s?\s+de\s+"
    r"(?P<prov>[A-ZÁÉÍÓÚÑÜa-záéíóúñü' \-]{3,30}?)"
    r"(?=[,.;:\n)]|\s+(?:y|e|o|hasta|en|con|que|según|con\s+sus)\b)",
    re.IGNORECASE,
)


def _province_to_ccaa(prov_raw: str) -> str | None:
    n = prov_raw.strip().rstrip(".,:;").strip()
    # First pass: exact match (case-insensitive but accent-sensitive)
    for k, v in PROVINCE_TO_CCAA.items():
        if k.lower() == n.lower():
            return v
    return None


def derive_ccaa(record: dict) -> str:
    """Return the canonical CCAA name for an ES wine record. Returns
    an empty string for explicitly multi-region wines (CCAA_OVERRIDES
    with "" value); that makes them appear top-level in the appellation
    list rather than bucketed under a fake "España" group."""
    slug = record.get("slug") or ""
    if slug in CCAA_OVERRIDES:
        return CCAA_OVERRIDES[slug]

    # Scan the structured text fields for a CCAA mention. Order: the
    # brief geographic area is most likely to carry the canonical
    # mention; the link-to-terroir is a backup.
    haystack_parts = [
        record.get("geo_area_brief") or "",
        record.get("link_to_terroir") or "",
    ]
    for body in haystack_parts:
        if not body:
            continue
        for m in _CCAA_LEADIN_RE.finditer(body):
            resolved = _resolve_alias(m.group("ccaa"))
            if resolved:
                return resolved

    # Province-name fallback. Counts the CCAAs voted-for by each province
    # mention; the most-voted CCAA wins. This handles cross-province DOPs
    # (e.g. Ribera del Duero spans Burgos + Soria + Valladolid +
    # Segovia — all in Castilla y León).
    from collections import Counter
    ccaa_votes: Counter[str] = Counter()
    for body in haystack_parts:
        if not body:
            continue
        for m in _PROVINCE_LEADIN_RE.finditer(body):
            ccaa = _province_to_ccaa(m.group("prov"))
            if ccaa:
                ccaa_votes[ccaa] += 1
    if ccaa_votes:
        return ccaa_votes.most_common(1)[0][0]

    return "España"
