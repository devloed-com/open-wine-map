"""Derive the German wine region (Anbaugebiet for PDOs, Bundesland-scale
territory for PGIs) for a wine GI.

Germany has 13 traditional **Anbaugebiete** (regional wine PDOs) plus a
small set of Einzellage-PDOs (single-vineyard appellations modelled as
sub-denominations of their parent Anbaugebiet) and ~27 Landwein PGIs
that span larger territories — typically a Bundesland or a multi-state
river basin.

The region facet drives stage 03 (wiki frontmatter) and stage 04 (panel
header + region facet filter). Labels are shown verbatim (proper noun,
not gettext-translated, consistent with AT/IT/ES/SI/HR/HU/RO/BG/GR).

Resolution order: explicit `record['region']` → curated
`_REGION_BY_FILE_NUMBER` fallback → text scan over the supplied
candidates → "Deutschland" catch-all for multi-Bundesland PGIs.
"""

from __future__ import annotations

import re
import unicodedata

# The 13 traditional Anbaugebiete (regional PDOs) + plus the PGI-level
# regional names. The latter are stable wine-law identifiers; some
# overlap with Bundesland names (Sachsen, Brandenburg, Mecklenburg-
# Vorpommern, Schleswig-Holstein), and some are river-basin labels
# (Mosel, Rhein, Saar, Ruwer) shared by PDOs and PGIs.
REGIONS = (
    # 13 traditional Anbaugebiete
    "Ahr",
    "Baden",
    "Franken",
    "Hessische Bergstraße",
    "Mittelrhein",
    "Mosel",
    "Nahe",
    "Pfalz",
    "Rheingau",
    "Rheinhessen",
    "Saale-Unstrut",
    "Sachsen",
    "Württemberg",
    # Landwein-PGI territories that are not coextensive with an
    # Anbaugebiet.
    "Bayern",
    "Brandenburg",
    "Hessen",
    "Mecklenburg-Vorpommern",
    "Rheinland-Pfalz",
    "Saarland",
    "Sachsen-Anhalt",
    "Schleswig-Holstein",
    "Deutschland",
)

# Diacritic-free / common variants → canonical name. Keys are normalised
# (NFKD-ASCII + lowercased + non-alnum stripped).
_VARIANTS: dict[str, str] = {
    "wuerttemberg": "Württemberg",
    "wurttemberg": "Württemberg",
    "hessische bergstrasse": "Hessische Bergstraße",
    "saale unstrut": "Saale-Unstrut",
    "rheinland pfalz": "Rheinland-Pfalz",
    "rheinland palatinate": "Rheinland-Pfalz",
    "mecklenburg vorpommern": "Mecklenburg-Vorpommern",
    "sachsen anhalt": "Sachsen-Anhalt",
    "schleswig holstein": "Schleswig-Holstein",
    "deutschland": "Deutschland",
    "germany": "Deutschland",
    "germania": "Deutschland",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


_CANON_BY_NORM = {_norm(r): r for r in REGIONS}
_CANON_BY_NORM.update({k: v for k, v in _VARIANTS.items()})


# Curated file_number → region. Hand-verified against eAmbrosia + the
# German Weingesetz / Weinverordnung's list of wine regions. Each of the
# 13 Anbaugebiete maps to itself; the 6 Einzellage PDOs use their parent
# Anbaugebiet; Landwein PGIs use the Bundesland or river-basin label.
_REGION_BY_FILE_NUMBER: dict[str, str] = {
    # ---- 13 traditional Anbaugebiete (regional PDOs) ----
    "PDO-DE-A0867": "Ahr",                       # Ahr
    "PDO-DE-A1264": "Baden",                     # Baden
    "PDO-DE-A1267": "Franken",                   # Franken
    "PDO-DE-A1268": "Hessische Bergstraße",      # Hessische Bergstraße
    "PDO-DE-A1269": "Mittelrhein",               # Mittelrhein
    "PDO-DE-A1270": "Mosel",                     # Mosel
    "PDO-DE-A1271": "Nahe",                      # Nahe
    "PDO-DE-A1272": "Pfalz",                     # Pfalz
    "PDO-DE-A1273": "Rheingau",                  # Rheingau
    "PDO-DE-A1274": "Rheinhessen",               # Rheinhessen
    "PDO-DE-A1275": "Saale-Unstrut",             # Saale-Unstrut
    "PDO-DE-A1277": "Sachsen",                   # Sachsen
    "PDO-DE-A1276": "Württemberg",               # Württemberg
    # ---- 6 Einzellage PDOs (modelled as sub-denominations) ----
    "PDO-DE-N1822": "Franken",                   # Bürgstadter Berg
    "PDO-DE-02403": "Franken",                   # Würzburger Stein-Berg
    "PDO-DE-02363": "Nahe",                      # Monzinger Niederberg
    "PDO-DE-02081": "Mosel",                     # Uhlen Blaufüsser Lay
    "PDO-DE-02082": "Mosel",                     # Uhlen Laubach
    "PDO-DE-02083": "Mosel",                     # Uhlen Roth Lay
    # ---- 27 Landwein PGIs ----
    "PGI-DE-A1278": "Rheinland-Pfalz",           # Ahrtaler Landwein
    "PGI-DE-A1279": "Baden",                     # Badischer Landwein
    "PGI-DE-A1280": "Bayern",                    # Bayerischer Bodensee-Landwein
    "PGI-DE-A1281": "Brandenburg",               # Brandenburger Landwein
    "PGI-DE-02660": "Brandenburg",               # Großräschener See
    "PGI-DE-A1282": "Bayern",                    # Landwein Main
    "PGI-DE-A1284": "Württemberg",               # Landwein Neckar
    "PGI-DE-A1285": "Baden",                     # Landwein Oberrhein
    "PGI-DE-A1286": "Rheinland-Pfalz",           # Landwein Rhein
    "PGI-DE-A1287": "Rheinland-Pfalz",           # Landwein Rhein-Neckar
    "PGI-DE-A1283": "Rheinland-Pfalz",           # Landwein der Mosel
    "PGI-DE-A1288": "Rheinland-Pfalz",           # Landwein der Ruwer
    "PGI-DE-A1289": "Saarland",                  # Landwein der Saar
    "PGI-DE-A1290": "Mecklenburg-Vorpommern",    # Mecklenburger Landwein
    "PGI-DE-A1291": "Sachsen-Anhalt",            # Mitteldeutscher Landwein
    "PGI-DE-A1293": "Rheinland-Pfalz",           # Nahegauer Landwein
    "PGI-DE-A1294": "Rheinland-Pfalz",           # Pfälzer Landwein
    "PGI-DE-A1296": "Bayern",                    # Regensburger Landwein
    "PGI-DE-A1298": "Rheinland-Pfalz",           # Rheinburgen-Landwein
    "PGI-DE-A1299": "Hessen",                    # Rheingauer Landwein
    "PGI-DE-A1301": "Rheinland-Pfalz",           # Rheinischer Landwein
    "PGI-DE-A1302": "Saarland",                  # Saarländischer Landwein
    "PGI-DE-A1304": "Schleswig-Holstein",        # Schleswig-Holsteinischer Landwein
    "PGI-DE-A1305": "Baden",                     # Schwäbischer Landwein
    "PGI-DE-A1306": "Hessen",                    # Starkenburger Landwein
    "PGI-DE-A1303": "Sachsen",                   # Sächsischer Landwein
    "PGI-DE-A1307": "Württemberg",               # Taubertäler Landwein
}


def region_for_file_number(file_number: str) -> str:
    """Curated fallback region for a wine GI file_number, or '' if unknown."""
    return _REGION_BY_FILE_NUMBER.get(file_number or "", "")


def find_region_in_text(text: str) -> str | None:
    """Scan text for a German region / Bundesland name. Returns the
    canonical form or None. Earliest match wins; longer needle breaks
    ties."""
    if not text:
        return None
    low = " " + _norm(text) + " "
    best: tuple[int, str] | None = None
    for needle, canon in _CANON_BY_NORM.items():
        if not needle:
            continue
        pos = low.find(" " + needle + " ")
        if pos < 0:
            continue
        if best is None or pos < best[0] or (
            pos == best[0] and len(needle) > len(_norm(best[1]))
        ):
            best = (pos, canon)
    return best[1] if best else None


def derive_region(record: dict, *text_candidates: str) -> str:
    """Resolve the region for one DE record. The curated file_number map
    is authoritative; the text scan only runs when the file_number is
    unknown."""
    if record.get("region"):
        return record["region"]
    curated = region_for_file_number(record.get("file_number", ""))
    if curated:
        return curated
    for text in text_candidates:
        hit = find_region_in_text(text or "")
        if hit:
            return hit
    return ""
