"""Derive the Bulgarian wine region (винарски район) for a wine GI.

Bulgarian wine law (Закон за виното и спиртните напитки) groups the
country's vineyards into 5 traditional wine regions. The 2 EU PGIs
(Дунавска равнина / Тракийска низина) are themselves named regions —
Дунавска равнина PGI covers exactly the Northern wine region of the
same name; Тракийска низина PGI covers the four southern regions
(Black Sea + Rose Valley + Thracian Lowlands + Struma Valley).

The region facet is shown in native Bulgarian (Cyrillic) form, matching
the AT Bundesland / HR macro region / HU borrégió / RO regiune
viticolă convention — not gettext-translated.

The 5 macro wine regions:

  - Дунавска равнина        Northern region (north of Stara Planina,
                              the Danube Plain). Vidin, Lom, Pleven,
                              Veliko Tarnovo, Ruse, Shumen, Veliki
                              Preslav, Targovishte, Lyaskovets, Suhindol,
                              Pavlikeni, …
  - Черноморски район       Eastern region (Black Sea coast). Varna,
                              Pomorie, Burgas, Karnobat, Sungurlare,
                              Slaviantsi, Yuzhno Chernomorie, …
  - Розова долина           Sub-Balkan region (Rose Valley between
                              Stara Planina and Sredna Gora). Karlovo,
                              Hisaria, …
  - Тракийска низина        South-Central region (Thracian Lowlands /
                              Maritsa basin south of Sredna Gora).
                              Plovdiv, Asenovgrad, Brestnik, Stara
                              Zagora, Nova Zagora, Haskovo, Sakar,
                              Stambolovo, Lyubimets, Ivaylovgrad, …
  - Долината на Струма      Southwestern region (Struma valley).
                              Melnik, Sandanski, Hrsovo, …

Resolution order: explicit `record['region']` → curated
`_REGION_BY_FILE_NUMBER` → scan the supplied text candidates.

Cyrillic normalisation: `.casefold()` + whitespace collapse, *not*
NFKD-ASCII-encode (which would erase Cyrillic). A secondary `unidecode`-
ASCII index is kept for fuzzy fallback against texts that quote
romanised region names.
"""

from __future__ import annotations

import re

from unidecode import unidecode

REGIONS = (
    "Дунавска равнина",
    "Черноморски район",
    "Розова долина",
    "Тракийска низина",
    "Долината на Струма",
)


def _norm(s: str) -> str:
    """Cyrillic-preserving normaliser. casefold + collapse whitespace,
    strip punctuation that isn't a Cyrillic / Latin letter or digit."""
    s = s.casefold()
    s = re.sub(r"[^a-z0-9а-яё \-]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _ascii(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", unidecode(s).lower()).strip()


_CANON_BY_NORM = {_norm(r): r for r in REGIONS}
_CANON_BY_ASCII = {_ascii(r): r for r in REGIONS}

# Extra fuzzy aliases for the text scan — common alternative names.
_TEXT_ALIASES = {
    _norm("Северен район"): "Дунавска равнина",
    _norm("Северна България"): "Дунавска равнина",
    _norm("Източен район"): "Черноморски район",
    _norm("Източна България"): "Черноморски район",
    _norm("Подбалкански район"): "Розова долина",
    _norm("Подбалкански"): "Розова долина",
    _norm("Южен централен район"): "Тракийска низина",
    _norm("Южна Тракия"): "Тракийска низина",
    _norm("Югозападен район"): "Долината на Струма",
    _norm("Струмска долина"): "Долината на Струма",
}
_CANON_BY_NORM.update(_TEXT_ALIASES)
_CANON_BY_ASCII.update({_ascii(k): v for k, v in {
    "Северен район": "Дунавска равнина",
    "Северна България": "Дунавска равнина",
    "Източен район": "Черноморски район",
    "Източна България": "Черноморски район",
    "Подбалкански район": "Розова долина",
    "Южен централен район": "Тракийска низина",
    "Югозападен район": "Долината на Струма",
    "Струмска долина": "Долината на Струма",
}.items()})


# Curated file_number → винарски район, hand-verified against the
# Bulgarian wine-law regional classification + eAmbrosia. North-of-Stara-
# Planina PDOs go to Дунавска равнина; the 4 southern wine regions
# subdivide everything south of Stara Planina.
_REGION_BY_FILE_NUMBER: dict[str, str] = {
    # Дунавска равнина (Northern) — 22 wines incl. the PGI
    "PGI-BG-A1538": "Дунавска равнина",
    "PDO-BG-A0952": "Дунавска равнина",  # Драгоево
    "PDO-BG-A1030": "Дунавска равнина",  # Хан Крум
    "PDO-BG-A0951": "Дунавска равнина",  # Лясковец
    "PDO-BG-A1441": "Дунавска равнина",  # Лом
    "PDO-BG-A0956": "Дунавска равнина",  # Ловеч
    "PDO-BG-A0360": "Дунавска равнина",  # Лозица
    "PDO-BG-A1314": "Дунавска равнина",  # Монтана
    "PDO-BG-A1031": "Дунавска равнина",  # Нови Пазар
    "PDO-BG-A0382": "Дунавска равнина",  # Ново село
    "PDO-BG-A1344": "Дунавска равнина",  # Оряховица
    "PDO-BG-A0420": "Дунавска равнина",  # Павликени
    "PDO-BG-A1477": "Дунавска равнина",  # Плевен
    "PDO-BG-A1425": "Дунавска равнина",  # Русе
    "PDO-BG-A0997": "Дунавска равнина",  # Шумен
    "PDO-BG-A1018": "Дунавска равнина",  # Сухиндол
    "PDO-BG-A0957": "Дунавска равнина",  # Свищов
    "PDO-BG-A1439": "Дунавска равнина",  # Търговище
    "PDO-BG-A0370": "Дунавска равнина",  # Върбица
    "PDO-BG-A0885": "Дунавска равнина",  # Велики Преслав
    "PDO-BG-A1346": "Дунавска равнина",  # Видин
    "PDO-BG-A0955": "Дунавска равнина",  # Враца

    # Черноморски район (Eastern) — 8 wines
    "PDO-BG-A1392": "Черноморски район",  # Черноморски район (DOP)
    "PDO-BG-A0881": "Черноморски район",  # Евксиноград
    "PDO-BG-A1347": "Черноморски район",  # Южно Черноморие
    "PDO-BG-A1175": "Черноморски район",  # Карнобат
    "PDO-BG-A0430": "Черноморски район",  # Поморие
    "PDO-BG-A1008": "Черноморски район",  # Славянци
    "PDO-BG-A1489": "Черноморски район",  # Сунгурларе
    "PDO-BG-A1032": "Черноморски район",  # Варна

    # Розова долина (Sub-Balkan / Rose Valley) — 2 wines
    "PDO-BG-A1044": "Розова долина",      # Карлово
    "PDO-BG-A1393": "Розова долина",      # Хисаря

    # Тракийска низина (South-Central / Thracian Lowlands) — 18 wines
    # incl. the PGI
    "PGI-BG-A1552": "Тракийска низина",
    "PDO-BG-A0877": "Тракийска низина",   # Асеновград
    "PDO-BG-A0985": "Тракийска низина",   # Болярово
    "PDO-BG-A0944": "Тракийска низина",   # Брестник
    "PDO-BG-A1179": "Тракийска низина",   # Ямбол
    "PDO-BG-A1047": "Тракийска низина",   # Ивайловград
    "PDO-BG-A1043": "Тракийска низина",   # Хасково
    "PDO-BG-A1177": "Тракийска низина",   # Любимец
    "PDO-BG-A1494": "Тракийска низина",   # Нова Загора
    "PDO-BG-A1182": "Тракийска низина",   # Пазарджик
    "PDO-BG-A1474": "Тракийска низина",   # Перущица
    "PDO-BG-A1297": "Тракийска низина",   # Пловдив
    "PDO-BG-A0013": "Тракийска низина",   # Сакар
    "PDO-BG-A1185": "Тракийска низина",   # Септември
    "PDO-BG-A1391": "Тракийска низина",   # Шивачево
    "PDO-BG-A1190": "Тракийска низина",   # Сливен
    "PDO-BG-A1487": "Тракийска низина",   # Стамболово
    "PDO-BG-A1394": "Тракийска низина",   # Стара Загора

    # Долината на Струма (Southwestern / Struma valley) — 4 wines
    "PDO-BG-A1473": "Долината на Струма",  # Долината на Струма (DOP)
    "PDO-BG-A0946": "Долината на Струма",  # Хърсово
    "PDO-BG-A1472": "Долината на Струма",  # Мелник
    "PDO-BG-A1006": "Долината на Струма",  # Сандански
}


def region_for_file_number(file_number: str) -> str:
    """Curated fallback region for a wine GI file_number, or '' if unknown."""
    return _REGION_BY_FILE_NUMBER.get(file_number or "", "")


def find_region_in_text(text: str) -> str | None:
    """Scan text for a region name. Returns the canonical form or None.
    Earliest match wins. Tries Cyrillic-preserving match first, then
    ASCII fallback for romanised texts."""
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
    if best:
        return best[1]
    low_ascii = " " + _ascii(text) + " "
    for needle, canon in _CANON_BY_ASCII.items():
        pos = low_ascii.find(" " + needle + " ")
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
