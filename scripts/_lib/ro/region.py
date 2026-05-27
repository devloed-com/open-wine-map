"""Derive the Romanian wine region (regiune viticolă) for a wine GI.

Romanian wine law (Legea viei și vinului nr. 164/2015, plus the ONVPV
regional classification) groups the country's vineyards into 8 wine
regions (regiuni viticole). Unlike Hungary, none of these regions
themselves appear as PGIs in eAmbrosia — Romanian IGPs are named
regional aliases (Dealurile Crișanei, Dealurile Sătmarului, Viile
Timișului, Colinele Dobrogei, Hușilor, Dealurile Vrancei, Dealurile
Munteniei, …) rather than the macro region names. The region facet is
shown in its native form (with diacritics), not gettext-translated —
same convention as AT Bundesland / HR macro region / HU borrégió.

The 8 macro wine regions used as the facet label:

  - Crișana și Maramureș   (NW)
  - Banat                  (W)
  - Transilvania           (C, includes the Târnave plateau, Apold)
  - Moldova                (E, the Podișul Moldovei plateau —
                              Cotnari, Iași, Huși, Odobești, Panciu,
                              Bohotin, Coteşti)
  - Muntenia               (S, includes Dealu Mare, Pietroasa,
                              Ștefănești)
  - Oltenia                (SW, includes Drăgășani, Sâmburești, Banu
                              Mărăcine, Mehedinți, Severin)
  - Dobrogea               (SE, the Black Sea: Murfatlar, Sarica
                              Niculițel, Babadag)
  - Terasele Dunării       (S, the Danube terraces: Greaca,
                              Oltina-Ostrov)

Resolution order: explicit `record['region']` → curated
`_REGION_BY_FILE_NUMBER` → scan the supplied text candidates.
"""

from __future__ import annotations

import re
import unicodedata

REGIONS = (
    "Crișana și Maramureș",
    "Banat",
    "Transilvania",
    "Moldova",
    "Muntenia",
    "Oltenia",
    "Dobrogea",
    "Terasele Dunării",
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


_CANON_BY_NORM = {_norm(r): r for r in REGIONS}
# Extra fuzzy aliases for the text scan (e.g. older texts use
# "Podișul Moldovei" instead of "Moldova" for the macro region label).
_TEXT_ALIASES = {
    _norm("Podișul Moldovei"): "Moldova",
    _norm("Câmpia Munteniei"): "Muntenia",
    _norm("Podișul Transilvaniei"): "Transilvania",
    _norm("Câmpia Olteniei"): "Oltenia",
    _norm("Maramureș"): "Crișana și Maramureș",
    _norm("Crișana"): "Crișana și Maramureș",
}
_CANON_BY_NORM.update(_TEXT_ALIASES)


# Curated file_number → regiune viticolă, hand-verified against
# eAmbrosia + the Romanian wine-law regional classification (ONVPV /
# Legea viei și vinului 164/2015). Every registered RO wine GI maps
# to exactly one of the 8 macro regions. Sourced by name + judet
# placement; cross-checked against the documento-unic geo-area text.
_REGION_BY_FILE_NUMBER: dict[str, str] = {
    # Moldova (Podișul Moldovei — Iași / Vaslui / Vrancea / Galați)
    "PDO-RO-A0135": "Moldova",          # Cotnari (Iași)
    "PDO-RO-A0139": "Moldova",          # Iași
    "PDO-RO-A0138": "Moldova",          # Bohotin (Iași)
    "PDO-RO-A1583": "Moldova",          # Huși (Vaslui)
    "PDO-RO-A0136": "Moldova",          # Iana (Vaslui)
    "PDO-RO-A1577": "Moldova",          # Coteşti (Vrancea)
    "PDO-RO-A1586": "Moldova",          # Odobeşti (Vrancea)
    "PDO-RO-A1584": "Moldova",          # Panciu (Vrancea)
    "PDO-RO-A0133": "Moldova",          # Nicoreşti (Galați)
    "PDO-RO-A0132": "Moldova",          # Dealu Bujorului (Galați)
    "PGI-RO-A1591": "Moldova",          # Dealurile Moldovei IGP
    "PGI-RO-A1582": "Moldova",          # Dealurile Vrancei IGP
    # Muntenia (Dealu Mare belt — Prahova / Buzău / Argeș / Dâmbovița)
    "PDO-RO-A1079": "Muntenia",         # Dealu Mare (Prahova / Buzău)
    "PDO-RO-A0134": "Muntenia",         # Pietroasa (Buzău)
    "PDO-RO-A1309": "Muntenia",         # Ștefănești (Argeș)
    "PGI-RO-A1085": "Muntenia",         # Dealurile Munteniei IGP
    # Oltenia (Vâlcea / Olt / Dolj / Mehedinți)
    "PDO-RO-A0286": "Oltenia",          # Drăgăşani (Vâlcea)
    "PDO-RO-A0282": "Oltenia",          # Sâmbureşti (Olt)
    "PDO-RO-A1558": "Oltenia",          # Banu Mărăcine (Dolj — Craiova)
    "PDO-RO-A1214": "Oltenia",          # Segarcea (Dolj)
    "PDO-RO-A1072": "Oltenia",          # Mehedinţi
    "PGI-RO-A1095": "Oltenia",          # Dealurile Olteniei IGP
    # Dobrogea (Constanța / Tulcea — Black Sea, inland)
    "PDO-RO-A0030": "Dobrogea",         # Murfatlar (Constanța)
    "PDO-RO-N0037": "Dobrogea",         # Adamclisi (Constanța)
    "PDO-RO-A1575": "Dobrogea",         # Sarica Niculiţel (Tulcea)
    "PDO-RO-A1424": "Dobrogea",         # Babadag (Tulcea)
    "PGI-RO-A0612": "Dobrogea",         # Colinele Dobrogei IGP
    # Transilvania (Alba / Sibiu / Bistrița-Năsăud — Carpathian basin)
    "PDO-RO-A0365": "Transilvania",     # Târnave (Alba / Sibiu)
    "PDO-RO-A0366": "Transilvania",     # Aiud (Alba)
    "PDO-RO-A0368": "Transilvania",     # Alba Iulia (Alba)
    "PDO-RO-02854": "Transilvania",     # Jidvei (Alba — Târnave plateau)
    "PDO-RO-A0369": "Transilvania",     # Lechinţa (Bistrița-Năsăud)
    "PDO-RO-A0371": "Transilvania",     # Sebeş-Apold (Alba / Sibiu)
    "PGI-RO-A0288": "Transilvania",     # Dealurile Transilvaniei IGP
    # Banat (Timiș / Caraș-Severin)
    "PDO-RO-A0028": "Banat",            # Banat (umbrella DOP)
    "PDO-RO-A0027": "Banat",            # Recaş (Timiș)
    "PGI-RO-A0108": "Banat",            # Viile Timișului IGP
    "PGI-RO-A0032": "Banat",            # Viile Carașului IGP
    # Crișana și Maramureș (Bihor / Arad / Satu Mare)
    "PDO-RO-A0105": "Crișana și Maramureș",  # Crișana (umbrella DOP)
    "PDO-RO-A0029": "Crișana și Maramureș",  # Miniş (Arad)
    "PGI-RO-A0106": "Crișana și Maramureș",  # Dealurile Crișanei IGP (Bihor)
    "PGI-RO-A0107": "Crișana și Maramureș",  # Dealurile Sătmarului IGP
    "PGI-RO-A0031": "Crișana și Maramureș",  # Dealurile Zarandului IGP (Arad)
    # Terasele Dunării (Danube-bank — Brăila / S Constanța)
    "PDO-RO-N1588": "Terasele Dunării",  # Însurăţei (Brăila)
    "PDO-RO-A0611": "Terasele Dunării",  # Oltina (S Constanța — Danube bank)
    "PGI-RO-A1077": "Terasele Dunării",  # Terasele Dunării IGP
}


def region_for_file_number(file_number: str) -> str:
    """Curated fallback region for a wine GI file_number, or '' if unknown."""
    return _REGION_BY_FILE_NUMBER.get(file_number or "", "")


def find_region_in_text(text: str) -> str | None:
    """Scan text for a region name. Returns the canonical form or None.
    Earliest match wins."""
    if not text:
        return None
    low = " " + _norm(text) + " "
    best: tuple[int, str] | None = None
    for needle, canon in _CANON_BY_NORM.items():
        pos = low.find(" " + needle + " ")
        if pos < 0:
            continue
        if best is None or pos < best[0]:
            best = (pos, canon)
    return best[1] if best else None


def derive_region(record: dict, *text_candidates: str) -> str:
    """Resolve the wine region for one record. The curated file_number
    map is authoritative; the text scan only runs when the file_number
    is unknown."""
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
