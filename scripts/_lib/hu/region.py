"""Derive the Hungarian wine area (borrégió) for a wine GI.

Hungarian wine law groups the 22 wine districts (borvidék) into 6 wine
regions (borrégió); these regions also appear as PGIs in eAmbrosia
(Balaton, Duna-Tisza-közi, Dunántúli, Felső-Magyarország, Zemplén — the
Tokaj area — plus the Balatonmelléki PGI which is a subset of Balaton).
Tokaj itself is structurally its own region, even though there is no
"Tokaj PGI" in eAmbrosia — the Zemplén PGI covers the surrounding
Tokaj-Hegyalja area instead.

For the map facet we use the 7 borrégió as the region label (native
Hungarian form, not gettext-translated — same convention as AT
Bundesland / SI vinorodna dežela / HR macro region):

  - Tokaj             — Tokaji PDOs (Tokaj, Debrői Hárslevelű)
  - Felső-Magyarország — Eger, Bükk, Mátra, Felső-Magyarország PGI
  - Duna              — Kunság, Hajós-Baja, Csongrád, Duna, Soltvadkerti, Izsáki
                         Arany Sárfehér, Monor, Duna-Tisza-közi PGI
  - Balaton           — Badacsony, Balaton-felvidék, Balatonboglár,
                         Balatonfüred-Csopak, Csopak, Káli, Tihany, Füred,
                         Nagy-Somló, Somlói, Zala, Balaton PGI, Balatonmelléki PGI
  - Pannon            — Pécs, Pannon, Szekszárd, Tolna, Villány
  - Felső-Pannon      — Etyek-Buda, Mór, Neszmély, Pannonhalma, Sopron,
                         Etyeki Pezsgő, Kőszeg, Dunántúli PGI (umbrella
                         Transdanubia regional PGI assigned to the
                         largest member borrégió)
  - Zemplén           — Zemplén PGI (Tokaj-area umbrella)

Resolution order: explicit `record['region']` → curated
`_REGION_BY_FILE_NUMBER` → scan the supplied text candidates.
"""

from __future__ import annotations

import re
import unicodedata

REGIONS = (
    "Tokaj",
    "Felső-Magyarország",
    "Duna",
    "Balaton",
    "Pannon",
    "Felső-Pannon",
    "Zemplén",
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


_CANON_BY_NORM = {_norm(r): r for r in REGIONS}


# Curated file_number → borrégió, hand-verified against eAmbrosia + the
# Hungarian wine-law region structure. Every registered HU wine GI maps
# to exactly one of the 7 borrégió.
_REGION_BY_FILE_NUMBER: dict[str, str] = {
    # Tokaj
    "PDO-HU-A1254": "Tokaj",            # Tokaj
    "PDO-HU-A1373": "Tokaj",            # Debrői Hárslevelű (Bükkalja, but Hárslevelű-Tokaj orbit)
    # Felső-Magyarország
    "PDO-HU-A1328": "Felső-Magyarország",  # Eger
    "PDO-HU-A1368": "Felső-Magyarország",  # Mátra
    "PDO-HU-A1500": "Felső-Magyarország",  # Bükk
    "PGI-HU-A1329": "Felső-Magyarország",  # Felső-Magyarország PGI
    "PDO-HU-N1638": "Felső-Magyarország",  # Monor (sits between Duna and Felső-Magyarország;
                                            # closer to Pest county wine area, but
                                            # Hungarian wine law puts it in the Duna borrégió).
    # Duna
    "PDO-HU-A1332": "Duna",             # Kunság
    "PDO-HU-A1383": "Duna",             # Csongrád
    "PDO-HU-A1388": "Duna",             # Hajós-Baja
    "PDO-HU-A1341": "Duna",             # Izsáki Arany Sárfehér
    "PDO-HU-A1345": "Duna",             # Duna
    "PDO-HU-02171": "Duna",             # Soltvadkerti
    "PGI-HU-A1342": "Duna",             # Duna-Tisza-közi PGI
    # Balaton
    "PDO-HU-A1378": "Balaton",          # Balatonboglár
    "PDO-HU-A1506": "Balaton",          # Badacsony
    "PDO-HU-A1509": "Balaton",          # Balaton-felvidék
    "PDO-HU-A1516": "Balaton",          # Balatonfüred-Csopak
    "PDO-HU-02378": "Balaton",          # Csopak
    "PDO-HU-03043": "Balaton",          # Füred
    "PDO-HU-A1503": "Balaton",          # Tihany
    "PDO-HU-A1505": "Balaton",          # Káli
    "PDO-HU-A1501": "Balaton",          # Nagy-Somló
    "PDO-HU-A1376": "Balaton",          # Somlói
    "PDO-HU-A1502": "Balaton",          # Zala
    "PGI-HU-A1507": "Balaton",          # Balaton PGI
    "PGI-HU-A1508": "Balaton",          # Balatonmelléki PGI (Balaton subset)
    # Pannon
    "PDO-HU-A1349": "Pannon",           # Szekszárd
    "PDO-HU-A1353": "Pannon",           # Tolna
    "PDO-HU-A1380": "Pannon",           # Pannon
    "PDO-HU-A1381": "Pannon",           # Villány
    "PDO-HU-A1385": "Pannon",           # Pécs
    # Felső-Pannon
    "PDO-HU-A1333": "Felső-Pannon",     # Mór
    "PDO-HU-A1335": "Felső-Pannon",     # Neszmély
    "PDO-HU-A1338": "Felső-Pannon",     # Pannonhalma
    "PDO-HU-A1350": "Felső-Pannon",     # Etyek-Buda
    "PDO-HU-A1504": "Felső-Pannon",     # Sopron
    "PDO-HU-02772": "Felső-Pannon",     # Etyeki Pezsgő
    "PDO-HU-02804": "Felső-Pannon",     # Kőszeg
    "PGI-HU-A1351": "Felső-Pannon",     # Dunántúli PGI (Transdanubia umbrella —
                                         # spans Pannon + Felső-Pannon; assigned
                                         # to the largest member borrégió by member count)
    # Zemplén
    "PGI-HU-A1375": "Zemplén",          # Zemplén PGI (Tokaj-area umbrella)
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
    """Resolve the wine borrégió for one record. The curated file_number
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
