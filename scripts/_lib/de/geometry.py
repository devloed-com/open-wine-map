"""DE-side geometry resolution — pull wine-GI polygons from Figshare.

Reuses the shared artifact the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    EU PDOs registered before Nov-2021, including the 13 traditional
    German Anbaugebiete (`PDO-DE-A12xx`, `PDO-DE-A0867`).

Stage 04 resolves each DE record by:

  1. **parent-appellation** — Einzellage sub-denominations (Bürgstadter
     Berg → Franken, Monzinger Niederberg → Nahe, the three Uhlen → Mosel,
     Würzburger Stein-Berg → Franken) inherit the parent Anbaugebiet's
     polygon. The Einzellage's own commune-level polygon is not in
     Bétard; without a per-site dataset (cadastral parcels), the
     honest precision is parent-Anbaugebiet.
  2. **lgl-gemarkung-union** — Baden and Württemberg, whose documents list
     their Gemarkungen by land-register number: the union of those
     Gemarkungen from the LGL Baden-Württemberg ALKIS layer
     (`scripts/_lib/de/gemarkung.py`). Bétard drew both as whole Landkreise.
     The union replaces the Bétard polygon inside the index, so the Landwein
     PGIs that are unions of the two follow.
  2a. **gisco-commune-union** (Bavarian lists) — Franken, whose EU single
     document lists its Gemeinden by Regierungsbezirk and Kreis, and Landwein
     Main (its BLE § 4): the union of those Gemeinden from GISCO LAU
     (`scripts/_lib/de/gemeinde_list.py`). Bétard drew Franken before the
     2025 amendment removed fifteen Gemeinden and added three; Franken's
     drawn polygon replaces the Bétard one inside the index, so its
     Einzellagen follow.
  2b. **alkis-gemarkung-union / gisco-commune-union** (the record's own
     list in another layout, `scripts/_lib/de/area_units.py`) — Mittelrhein,
     Mosel, Nahe and Pfalz print each Gemarkung's land-register number,
     Saale-Unstrut names its Gemarkungen by Kreis, Mittelrhein's part in
     Nordrhein-Westfalen names five by town: drawn from the Länder's open
     Gemarkung layers (`katasterbezirk.py`). Rheingau, Ahr, Hessische
     Bergstraße and Rheinhessen list Gemeinden in prose: drawn from GISCO
     (Bétard had no part of Frankfurt am Main, which the Rheingau lists). A
     Landwein whose own text is such a list is drawn from it, ahead of its
     member table (Landwein der Saar and der Ruwer had been all of the
     Mosel).
  2c. **figshare-pdo** — exact `file_number` → `PDOid` match. Covers
     the PDOs whose text is prose (Sachsen).
  3. **region-pdo-union** — the 27 DE Landwein PGIs are not in Bétard
     (PDO-only dataset). For PGIs whose territory equals one of the 13
     Anbaugebiete (Badischer Landwein = Baden, Pfälzer Landwein = Pfalz,
     Nahegauer Landwein = Nahe, Sächsischer Landwein = Sachsen, …),
     we use the parent PDO's polygon as the IGP geometry — same
     approach the SI / HU / BG pipelines use for their region-equal
     PGIs.
  4. **stub-no-geometry** — no polygon available. The remaining ~10
     PGIs span multi-Bundesland territories that don't equal any single
     Anbaugebiet (Brandenburger Landwein, Mitteldeutscher Landwein,
     Schleswig-Holsteinischer Landwein, Mecklenburger Landwein, …).
     Phase 2: parse the commune list out of the Einziges Dokument and
     union the GISCO LAU DE polygons (same pattern as RO IGPs).

Recently-registered PDOs not in Bétard 2022 (the 6 Einzellage PDOs and
a couple of newer regional ones) fall through to the parent-appellation
inheritance step.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# Landwein PGI file_number → the regional-PDO file_number whose polygon
# matches the PGI's territory. Conservative — only included where the
# PGI explicitly covers the same Anbaugebiet (the EU-OJ Einziges Dokument
# describes the area as the same wine region). Multi-Bundesland IGPs
# (Mitteldeutscher Landwein, Schleswig-Holsteinischer Landwein, etc.)
# are deliberately left out: their territory does not coincide with one
# Anbaugebiet, and a future commune-list parser will resolve them.
DE_PGI_MEMBER_PDOS: dict[str, tuple[str, ...]] = {
    # ── Anbaugebiet-aligned Landwein PGIs ─────────────────────────────
    "PGI-DE-A1278": ("PDO-DE-A0867",),   # Ahrtaler Landwein → Ahr
    "PGI-DE-A1279": ("PDO-DE-A1264",),   # Badischer Landwein → Baden
    "PGI-DE-A1285": ("PDO-DE-A1264",),   # Landwein Oberrhein → Baden (Oberrhein-Anteil)
    "PGI-DE-A1283": ("PDO-DE-A1270",),   # Landwein der Mosel → Mosel
    "PGI-DE-A1288": ("PDO-DE-A1270",),   # Landwein der Ruwer → Mosel (Ruwer-Teilgebiet)
    "PGI-DE-A1289": ("PDO-DE-A1270",),   # Landwein der Saar → Mosel (Saar-Teilgebiet)
    "PGI-DE-A1293": ("PDO-DE-A1271",),   # Nahegauer Landwein → Nahe
    "PGI-DE-A1294": ("PDO-DE-A1272",),   # Pfälzer Landwein → Pfalz
    "PGI-DE-A1299": ("PDO-DE-A1273",),   # Rheingauer Landwein → Rheingau
    "PGI-DE-A1303": ("PDO-DE-A1277",),   # Sächsischer Landwein → Sachsen
    "PGI-DE-A1305": ("PDO-DE-A1276",),   # Schwäbischer Landwein → Württemberg
    "PGI-DE-A1284": ("PDO-DE-A1276",),   # Landwein Neckar → Württemberg (Neckar-Teilgebiet)
    "PGI-DE-A1306": ("PDO-DE-A1268",),   # Starkenburger Landwein → Hessische Bergstraße
    # ── Multi-Anbaugebiet Landwein PGIs (river-basin unions) ──────────
    # Since 2026-11-24 every Landwein of this block is drawn from the list
    # its own text prints (`_draw_unit_areas`); a row here is the fallback
    # when that list does not bind, and what the region aliases are read
    # from — so each row is the Anbaugebiete the Landwein's own list covers
    # (checked that day, list against polygon).
    # Landwein Rhein: BLE § 3 lists the Gemeinden of Rheinland-Pfalz (Ahr,
    # Mittelrhein, Mosel, Nahe, Pfalz, Rheinhessen), five Gemarkungen of
    # Nordrhein-Westfalen and 21 Gemeinden of Hessen — the Rheingau's and
    # the Hessische Bergstraße's, which this row lacked until then.
    "PGI-DE-A1286": (
        "PDO-DE-A1270",  # Mosel
        "PDO-DE-A1269",  # Mittelrhein
        "PDO-DE-A1271",  # Nahe
        "PDO-DE-A1272",  # Pfalz
        "PDO-DE-A1273",  # Rheingau
        "PDO-DE-A1274",  # Rheinhessen
        "PDO-DE-A0867",  # Ahr
        "PDO-DE-A1268",  # Hessische Bergstraße
    ),
    # Rheinburgen-Landwein: its single document prints Mittelrhein's list,
    # unit for unit (61 numbered Gemarkungen, the five of Nordrhein-
    # Westfalen) and no Gemeinde of the Ahr, which this row carried.
    "PGI-DE-A1298": (
        "PDO-DE-A1269",  # Mittelrhein
    ),
    # Rheinischer Landwein: its single document lists Rheinhessen's 133
    # Gemeinden (Albig … Zotzenheim) and none of the Nahe, the Pfalz or the
    # Mittelrhein, which this row carried.
    "PGI-DE-A1301": (
        "PDO-DE-A1274",  # Rheinhessen
    ),
    # Landwein Rhein-Neckar: its BLE Produktspezifikation § 4 lists the
    # Gemeinden and Gemarkungen of Baden and of Württemberg in one
    # alphabetical run (Achern … Zuffenhausen, 676 names) and no place of
    # Rheinhessen or the Pfalz, which this row carried until 2026-11-17.
    "PGI-DE-A1287": (
        "PDO-DE-A1276",  # Württemberg
        "PDO-DE-A1264",  # Baden
    ),
    # Landwein Main: § 4 lists Bavarian towns and Gemeinden only, by
    # Regierungsbezirk and Landkreis (Oberfranken, Mittelfranken,
    # Unterfranken) — Franken's ground. Until 2026-11-17 the row added all of
    # Baden and Württemberg. Since 2026-11-24 it is drawn from that list
    # (`_draw_gemeinde_areas`: Franken's 127 Gemeinden and the fifteen
    # Franken's 2025 amendment removed); this row is the fallback.
    "PGI-DE-A1282": (
        "PDO-DE-A1267",  # Franken
    ),
    # Bayerischer Bodensee-Landwein is not a union of a region: see
    # DE_LANDWEIN_AREA (it was drawn as all of Baden until 2026-11-17).
    # Nor is Regensburger Landwein: it sat here as Franken, some 150 km from
    # the Danube slopes its specification describes, until 2026-11-24.
    # Mitteldeutscher Landwein: BLE § 3 lists Saale-Unstrut's Gemarkungen
    # in Sachsen-Anhalt and Thüringen (86 units; not the four of Werder in
    # Brandenburg) and no place of Saxony, which this row carried.
    "PGI-DE-A1291": (   # Mitteldeutscher Landwein
        "PDO-DE-A1275",  # Saale-Unstrut
    ),
}


# Einzellage PDO → parent Anbaugebiet PDO file_number. Used for the
# `parent-appellation` step; the Einzellage's commune-precise polygon
# isn't in Bétard, so we honestly fall back to the parent Anbaugebiet.
DE_EINZELLAGE_PARENT_PDO: dict[str, str] = {
    "PDO-DE-N1822": "PDO-DE-A1267",   # Bürgstadter Berg → Franken
    "PDO-DE-02403": "PDO-DE-A1267",   # Würzburger Stein-Berg → Franken
    "PDO-DE-02363": "PDO-DE-A1271",   # Monzinger Niederberg → Nahe
    "PDO-DE-02081": "PDO-DE-A1270",   # Uhlen Blaufüsser Lay → Mosel
    "PDO-DE-02082": "PDO-DE-A1270",   # Uhlen Laubach → Mosel
    "PDO-DE-02083": "PDO-DE-A1270",   # Uhlen Roth Lay → Mosel
}


def _de_norm(s: str) -> str:
    """Normalise a German place name for GISCO-LAU matching: lowercase,
    transliterate umlauts, drop the ", Stadt" suffix — and its Bavarian
    abbreviations ", St" / ", GKSt" / ", M" (Stadt / Große Kreisstadt /
    Markt: "Röttingen, St", "Rothenburg ob der Tauber, GKSt") — and
    parentheticals (so "Werder (Havel), Stadt" and "Werder/ Havel" both
    collapse to "werder havel"). A name merely ending in "-stadt" keeps it."""
    s = s.lower().strip()
    s = s.replace("ß", "ss").replace("ä", "a").replace("ö", "o").replace("ü", "u")
    s = re.sub(r",?\s*\b(stadt|st|gkst|m)\s*$", "", s)
    s = s.replace("/", " ").replace("(", " ").replace(")", " ")
    return re.sub(r"\s+", " ", s).strip()


# Kreis name → 5-digit AGS (the GISCO_ID `DE_<AGS8>` prefix positions
# 3:8) for every Kreis DE_LANDWEIN_AREA refers to: used to union every
# GISCO commune of a whole Landkreis / kreisfreie Stadt, and to scope a
# named Gemeinde to its Kreis (Boxberg and Adelshofen have homonyms in
# other Länder). A Landkreis sharing its name with a kreisfreie Stadt
# (Würzburg 09663, Ansbach 09561) is keyed "Landkreis X". Keys are
# pre-normalised via `_de_norm`.
_DE_KREIS_AGS: dict[str, str] = {
    _de_norm(name): code for name, code in {
        "Brandenburg an der Havel": "12051",
        "Cottbus": "12052",
        "Frankfurt (Oder)": "12053",
        "Potsdam": "12054",
        "Barnim": "12060",
        "Dahme-Spreewald": "12061",
        "Elbe-Elster": "12062",
        "Havelland": "12063",
        "Märkisch-Oderland": "12064",
        "Oberhavel": "12065",
        "Oberspreewald-Lausitz": "12066",
        "Oder-Spree": "12067",
        "Ostprignitz-Ruppin": "12068",
        "Potsdam-Mittelmark": "12069",
        "Prignitz": "12070",
        "Spree-Neiße": "12071",
        "Teltow-Fläming": "12072",
        "Uckermark": "12073",
        "Main-Tauber-Kreis": "08128",
        "Landkreis Würzburg": "09679",
        "Landkreis Ansbach": "09571",
        "Landkreis Lindau (Bodensee)": "09776",
        "Regensburg": "09362",
        "Landkreis Regensburg": "09375",
    }.items()
}

# Curated commune-list geometry for Landwein PGIs that are NOT
# coextensive with a single Anbaugebiet (so `region-pdo-union` can't
# resolve them and Bétard — PDO-only — has no polygon). Transcribed
# from the BLE Produktspezifikation §3 "Abgrenzung des Gebietes".
# Resolved by `landwein_commune_union` against GISCO LAU 2024:
#   - `landkreise` / `kreisfreie`: whole-Kreis union by AGS prefix
#   - `gemeinden`: a single commune matched by name within its Kreis
#     (`spec` records the Produktspezifikation's wording when the GISCO
#     commune differs — e.g. the Ortsteil Meseberg sits in Gransee;
#     `label` is the name the card prints when GISCO's is abbreviated).
#   - `reading`: the specification lists no unit and the communes are our
#     reading of its prose — `evidence` (the verbatim sentences read, each
#     checked against the cached PDF by tests/test_de_parser.py) and
#     `disclose` (the sentence the card prints, per UI language). The card
#     then says "our reading", not "the units named in the document".
DE_LANDWEIN_AREA: dict[str, dict] = {
    # Brandenburger Landwein (PGI-DE-A1281): 6 Landkreise + 7 Gemeinden
    # + 4 kreisfreie Städte. BLE Produktspezifikation Brandenburger
    # Landwein §3.
    "PGI-DE-A1281": {
        "landkreise": [
            "Dahme-Spreewald", "Elbe-Elster", "Oberspreewald-Lausitz",
            "Oder-Spree", "Spree-Neiße", "Teltow-Fläming",
        ],
        "kreisfreie": [
            "Brandenburg an der Havel", "Cottbus", "Frankfurt (Oder)", "Potsdam",
        ],
        "gemeinden": [
            {"name": "Niederfinow", "kreis": "Barnim"},
            {"name": "Müncheberg", "kreis": "Märkisch-Oderland"},
            {"name": "Gransee", "kreis": "Oberhavel", "spec": "Meseberg (Ortsteil der Stadt Gransee)"},
            {"name": "Vielitzsee", "kreis": "Ostprignitz-Ruppin"},
            {"name": "Werder (Havel)", "kreis": "Potsdam-Mittelmark"},
            {"name": "Templin", "kreis": "Uckermark"},
            {"name": "Prenzlau", "kreis": "Uckermark"},
        ],
        "source": "BLE Produktspezifikation Brandenburger Landwein, Abschnitt 3 (Abgrenzung des Gebietes)",
    },
    # Taubertäler Landwein (PGI-DE-A1307): §4.1 lists 50 "Gemeinden und
    # Gemarkungen" of the Main-Tauber-Kreis (the Kreis is named in §7.1.1)
    # — the 13 Gemeinden are transcribed here; the other 37 are
    # Gemarkungen (Beckstein, Markelsheim, Dertingen, …), sub-commune
    # cadastral districts with no GISCO LAU polygon of their own. §4.2
    # adds five Bavarian places: four Gemeinden and the Ortsteil
    # Tauberzell, which the Gemeinde Adelshofen lists as its own (Landkreis
    # Ansbach — the BLE Franken and Landwein Main specifications name
    # "Landkreis Ansbach: Adelshofen, Rothenburg ob der Tauber").
    "PGI-DE-A1307": {
        "gemeinden": [
            {"name": "Bad Mergentheim", "kreis": "Main-Tauber-Kreis"},
            {"name": "Boxberg", "kreis": "Main-Tauber-Kreis"},
            {"name": "Creglingen", "kreis": "Main-Tauber-Kreis"},
            {"name": "Großrinderfeld", "kreis": "Main-Tauber-Kreis"},
            {"name": "Grünsfeld", "kreis": "Main-Tauber-Kreis"},
            {"name": "Königheim", "kreis": "Main-Tauber-Kreis"},
            {"name": "Külsheim", "kreis": "Main-Tauber-Kreis"},
            {"name": "Lauda-Königshofen", "kreis": "Main-Tauber-Kreis"},
            {"name": "Niederstetten", "kreis": "Main-Tauber-Kreis"},
            {"name": "Tauberbischofsheim", "kreis": "Main-Tauber-Kreis"},
            {"name": "Weikersheim", "kreis": "Main-Tauber-Kreis"},
            {"name": "Werbach", "kreis": "Main-Tauber-Kreis"},
            {"name": "Wertheim", "kreis": "Main-Tauber-Kreis"},
            {"name": "Bieberehren", "kreis": "Landkreis Würzburg"},
            {"name": "Röttingen", "kreis": "Landkreis Würzburg"},
            {"name": "Tauberrettersheim", "kreis": "Landkreis Würzburg"},
            {"name": "Rothenburg ob der Tauber", "kreis": "Landkreis Ansbach", "spec": "Rothenburg o.d.T."},
            {"name": "Adelshofen", "kreis": "Landkreis Ansbach", "spec": "Tauberzell (Ortsteil der Gemeinde Adelshofen)"},
        ],
        "source": "BLE Produktspezifikation Taubertäler Landwein, Abschnitt 4.1 (Baden-Württemberg) und 4.2 (Bayern)",
    },
    # Bayerischer Bodensee-Landwein (PGI-DE-A1280): § 3 "Die Gemarkungen
    # Hoyren und Aeschach der Großen Kreisstadt Lindau, die Gemeinden
    # Nonnenhorn und Wasserburg." Lindau is drawn whole for its two
    # Gemarkungen (`partial`, disclosed on the card).
    "PGI-DE-A1280": {
        "gemeinden": [
            {"name": "Nonnenhorn", "kreis": "Landkreis Lindau (Bodensee)"},
            {"name": "Wasserburg (Bodensee)", "kreis": "Landkreis Lindau (Bodensee)",
             "spec": "Wasserburg"},
            {"name": "Lindau (Bodensee)", "kreis": "Landkreis Lindau (Bodensee)",
             "spec": "Lindau (Gemarkungen Hoyren, Aeschach)", "partial": True},
        ],
        "source": "BLE Produktspezifikation Bayerischer Bodensee-Landwein, Abschnitt 3 (Abgrenzung des Gebietes)",
    },
    # Regensburger Landwein (PGI-DE-A1296). No list of Gemeinden exists and
    # none ever did: § 3 opens on the frame of its sister specifications
    # ("… der folgenden Gemeinden, wenn ihre Eignung … festgestellt wird")
    # and fills it with the one sentence Bavarian law has defined the
    # Untergebiet Donau by since the name was created — Erste Verordnung zur
    # Durchführung des Weingesetzes of 21 March 1983 (GVBl S. 116) § 2 (3),
    # BayWeinRAV of 31 August 1995 (GVBl S. 667) § 2 (1), where Main and
    # Lindau get the commune lists of Anlage 1 and the Danube none; the
    # BayWeinRAV of 2020 (§ 1) leaves the area to the specification. § 7
    # places the wine "im Raum der Stadt und des Landkreises Regensburg" and
    # names the Weinbaugemeinden. Boris's decision of 2026-11-24: the
    # north-bank communes of the Danube from the Naab to Wörth, inside the
    # city and Landkreis — every commune § 7 names and Donaustauf between
    # them — drawn whole and disclosed as a reading. Left out: Pettendorf
    # (at the Naab mouth) and Kirchroth (Landkreis Straubing-Bogen, where
    # the sentence ends at the Große Laber and § 7 no longer applies).
    # Evidence and options: docs/feedback-triage-2026-11-24.md.
    "PGI-DE-A1296": {
        "gemeinden": [
            {"name": "Regensburg", "kreis": "Regensburg",
             "spec": "Stadt Regensburg, Ortsteil Winzer"},
            {"name": "Tegernheim", "kreis": "Landkreis Regensburg"},
            {"name": "Donaustauf", "kreis": "Landkreis Regensburg"},
            {"name": "Bach a.d.Donau", "kreis": "Landkreis Regensburg",
             "label": "Bach a.d. Donau"},
            {"name": "Wiesent", "kreis": "Landkreis Regensburg", "spec": "Kruckenberg"},
            {"name": "Wörth a.d.Donau", "kreis": "Landkreis Regensburg",
             "label": "Wörth a.d. Donau"},
        ],
        "source": ("BLE Produktspezifikation Regensburger Landwein, Abschnitt 3 "
                   "(Abgrenzung des Gebietes) und 7 (Zusammenhang mit dem "
                   "geografischen Gebiet)"),
        "reading": {
            "evidence": [
                "Das Landweingebiet Regensburg umfasst die Südhänge des Bayerischen "
                "Waldes entlang der Donau zwischen Naab und Großer Laaber.",
                "Der Regensburger Landwein wächst innerhalb der bayerischen "
                "Weinbaugebiete im Raum der Stadt und des Landkreises Regensburg.",
                "zum Großteil in der Stadt Regensburg, Ortsteil Winzer",
                "Weinbaugemeinden Tegernheim, Bach a.d. Donau, Kruckenberg und "
                "Stadt Wörth a.d. Donau",
            ],
            "disclose": {
                "en": ("The specification lists no communes: it describes the area as the "
                       "southern slopes of the Bavarian Forest along the Danube between "
                       "the Naab and the Große Laaber, and places the wine in the city "
                       "and district of Regensburg. Drawn are the communes on the north "
                       "bank."),
                "fr": ("Le cahier des charges ne nomme aucune commune : il décrit l'aire "
                       "comme les versants sud de la Forêt de Bavière le long du Danube, "
                       "entre la Naab et la Große Laaber, et situe le vin dans la ville "
                       "et l'arrondissement de Ratisbonne. Sont dessinées les communes "
                       "de la rive nord."),
                "es": ("El pliego de condiciones no nombra ningún municipio: describe la "
                       "zona como las laderas meridionales del Bosque Bávaro a lo largo "
                       "del Danubio, entre el Naab y el Große Laaber, y sitúa el vino en "
                       "la ciudad y el distrito de Ratisbona. Se dibujan los municipios "
                       "de la orilla norte."),
                "nl": ("Het productdossier noemt geen gemeenten: het beschrijft het gebied "
                       "als de zuidhellingen van het Beierse Woud langs de Donau, tussen "
                       "de Naab en de Große Laaber, en plaatst de wijn in de stad en het "
                       "district Regensburg. Getekend zijn de gemeenten op de "
                       "noordoever."),
            },
        },
    },
}


# A record is redrawn from its Gemarkungen only when nearly all of them
# resolve; below that its Bétard polygon stays.
MIN_DRAWN_SHARE = 0.95


class DEPolygonIndex:
    """In-memory polygon index for DE records, backed by Bétard 2022 and,
    for the records that list them, the units of their own text: the LGL
    Gemarkungen (Baden, Württemberg), the Bavarian Gemeinde lists, and the
    Gemarkungen and Gemeinden of the other Länder (`area_units`)."""

    def __init__(
        self,
        figshare_gpkg: Path,
        gisco_lau_zip: Path | None = None,
        target_crs: str = "EPSG:4326",
        gemarkung_gpkg: Path | None = None,
        gemarkung_areas: dict[str, dict] | None = None,
        gemarkung_pins: dict[str, dict[int, dict]] | None = None,
        gemeinde_areas: dict[str, dict] | None = None,
        unit_areas: dict[str, dict] | None = None,
        unit_pins: dict[str, dict] | None = None,
        katasterbezirke_dir: Path | None = None,
        log=None,
    ) -> None:
        self.target_crs = target_crs
        self._log = log or (lambda msg: None)
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        # file_number → (geometry, geom_source, stats) of a record drawn from
        # the units its own text names (scripts/_lib/de/area_units.py): the
        # Länder's Gemarkungen, GISCO communes, or both.
        self._unit_areas = unit_areas or {}
        self._unit_drawn: dict[str, tuple[BaseGeometry, str, dict]] = {}
        # every German LAU row, for those lists
        self._de_rows: list[tuple[str, str, BaseGeometry]] = []
        # file_number → the stats of a record drawn from its Gemarkungen.
        self._gemarkung_stats: dict[str, dict] = {}
        self._gemarkung_areas = gemarkung_areas or {}
        # file_number → (geometry, stats) of a record drawn from its Bavarian
        # Gemeinde list (Franken, Landwein Main).
        self._gemeinde_areas = gemeinde_areas or {}
        self._gemeinde_drawn: dict[str, tuple[BaseGeometry, dict]] = {}
        # Bavarian LAU rows (GISCO_ID, LAU_NAME, geometry) for those lists.
        self._bavaria_rows: list[tuple[str, str, BaseGeometry]] = []
        # Bavarian communes by Kreis, for the units Württemberg names
        # without a number: {kreis: {normalised name: (LAU name, geometry)}}.
        self._by_communes: dict[str, dict[str, tuple[str, BaseGeometry]]] = {}
        # GISCO communes for the Landwein commune-union fallback, indexed
        # by 5-digit AGS Kreis prefix and by (kreis, normalised name).
        self._communes_by_kreis: dict[str, list[BaseGeometry]] = {}
        self._commune_by_kreis_name: dict[tuple[str, str], BaseGeometry] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].str.startswith(("PDO-DE", "PGI-DE"))]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[row["PDOid"]] = row.geometry

        if gisco_lau_zip is not None and gisco_lau_zip.exists() and DE_LANDWEIN_AREA:
            self._load_communes(gisco_lau_zip)

        if self._gemeinde_areas and self._bavaria_rows:
            self._draw_gemeinde_areas()

        if gemarkung_gpkg is not None and self._gemarkung_areas:
            self._draw_gemarkung_areas(gemarkung_gpkg, gemarkung_pins or {})

        if self._unit_areas and self._de_rows:
            self._draw_unit_areas(katasterbezirke_dir, unit_pins or {})

    def _draw_unit_areas(self, katasterbezirke_dir: Path | None, pins: dict[str, dict]) -> None:
        """Draw each record whose text names its units in one of the layouts
        `area_units` reads — a Gemeinde list in prose, Gemarkungen by Kreis,
        the Rhineland's numbered Gemarkungen — as the union of those units,
        when at least MIN_DRAWN_SHARE of them bind. A record already drawn
        from the LGL layer or a Bavarian list, or pinned in DE_LANDWEIN_AREA,
        is left to that step. A PDO's drawn polygon replaces its Bétard one
        in the index; a Landwein with a list of its own is drawn from it,
        ahead of its member table."""
        from _lib.de import area_units
        from _lib.de.katasterbezirk import SERVICES, Gemarkungen

        gemarkungen = (Gemarkungen(katasterbezirke_dir, self.target_crs)
                       if katasterbezirke_dir is not None and katasterbezirke_dir.exists() else None)
        if gemarkungen is None or not gemarkungen.rows:
            self._log("[de-geom] Gemarkung layers of the other Länder missing "
                      f"({katasterbezirke_dir}) — Gemeinde lists only; "
                      "run scripts/de/00_fetch_data.py")
        communes = area_units.CommuneRows(self._de_rows)
        for fn, spec in sorted(self._unit_areas.items()):
            if fn in self._gemarkung_stats or fn in self._gemeinde_drawn or fn in DE_LANDWEIN_AREA:
                continue
            units = spec["units"]
            if all(u.land in ("bw", "by") for u in units):
                continue
            res = area_units.resolve(units, gemarkungen, communes, pins.get(fn))
            listed = len(units)
            label = spec.get("slug") or fn
            if res.share < MIN_DRAWN_SHARE or not res.bound:
                if res.bound and res.share >= 0.5:
                    self._log(f"[de-geom] {label}: {len(res.bound)} of {listed} named units bind — "
                              f"kept as before; unmatched: {', '.join(res.unmatched[:12])}")
                continue
            geom = unary_union([b.geometry for b in res.bound])
            n_gemarkungen = sum(1 for b in res.bound if b.how == "gemarkung")
            whole = list(dict.fromkeys(b.label for b in res.bound if b.how == "gemeinde"))
            # a Gemeinde drawn whole for the parts the text names
            for_part: dict[str, list[str]] = {}
            for b in res.bound:
                if b.how == "gemeinde-for-part":
                    for_part.setdefault(b.label, []).append(b.unit.name)
            partial = [f"{g} ({', '.join(dict.fromkeys(names))})" for g, names in for_part.items()]
            pinned = [area_units.pin_text(lbl, [b for b in res.bound
                                                if area_units._label(b.unit) == lbl])
                      for lbl in (pins.get(fn) or {})
                      if any(area_units._label(b.unit) == lbl for b in res.bound)]
            lands = list(dict.fromkeys(b.land for b in res.bound if b.how == "gemarkung"))
            layer_credits = [{
                "text": gemarkungen.manifest[c].get("credit") or gemarkungen.manifest[c]["attribution"],
                "url": SERVICES[c]["publisher_url"],
                "licence": SERVICES[c]["licence_short"],
                "licence_url": SERVICES[c]["licence_url"],
            } for c in lands if gemarkungen is not None and c in gemarkungen.manifest]
            n_communes = len({b.lau_id for b in res.bound if b.how != "gemarkung"})
            stats = {
                "matched": n_communes if not n_gemarkungen else -1,
                "unmatched": len(res.unmatched),
                "unmatched_names": list(res.unmatched),
                "names_unmatched": list(res.unmatched),
                "units_listed": listed,
                "source_kind": spec["source_kind"],
                **({"gemarkungen": n_gemarkungen, "gemarkungen_listed": listed,
                    "credits": layer_credits, "whole": whole,
                    "by_number": all(b.unit.kind == "numbered" for b in res.bound
                                     if b.how == "gemarkung")} if n_gemarkungen else {}),
                **({"partial": partial} if partial else {}),
                **({"pinned": pinned} if pinned else {}),
                **({"name_disagreements": list(res.disagree)} if res.disagree else {}),
            }
            source = "alkis-gemarkung-union" if n_gemarkungen else "gisco-commune-union"
            self._unit_drawn[fn] = (geom, source, stats)
            if fn.startswith("PDO-"):
                self._pdo_polygons[fn] = geom
            self._log(f"[de-geom] {label}: drawn from its own {spec['source_kind']} list — "
                      f"{n_gemarkungen} Gemarkungen, {len(whole)} Gemeinden"
                      + (f", {len(partial)} Gemeinde(n) whole for a part" if partial else "")
                      + (f"; not drawn: {', '.join(res.unmatched)}" if res.unmatched else ""))

    def _load_communes(self, gisco_lau_zip: Path) -> None:
        """Load GISCO LAU 2024 communes for the Kreise referenced by
        DE_LANDWEIN_AREA (only the 5-digit AGS prefixes actually needed,
        so the index stays small — Brandenburg alone is 413 communes,
        Bayern would be 2,000 more)."""
        kreise = {code for area in DE_LANDWEIN_AREA.values()
                  for code in (_DE_KREIS_AGS.get(_de_norm(n))
                               for n in (*area.get("landkreise", []),
                                         *area.get("kreisfreie", []),
                                         *(g["kreis"] for g in area.get("gemeinden", []))))
                  if code}
        bavaria = bool(self._gemeinde_areas) or any(
            a["area"].by_gemeinden or a["area"].by_partial
            for a in self._gemarkung_areas.values())
        everything = bool(self._unit_areas)
        if not kreise and not bavaria and not everything:
            return
        gdf = gpd.read_file(f"zip://{gisco_lau_zip}")
        gdf = gdf[gdf["CNTR_CODE"] == "DE"]
        gid = gdf["GISCO_ID"].astype(str)
        if not everything:
            gdf = gdf[gid.str[3:8].isin(kreise) | (gid.str[3:5] == "09" if bavaria else False)]
        if gdf.crs is None or gdf.crs.to_string() != self.target_crs:
            gdf = gdf.to_crs(self.target_crs)
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            kreis = str(row["GISCO_ID"])[3:8]
            if everything:
                self._de_rows.append((str(row["GISCO_ID"]), str(row["LAU_NAME"]), geom))
            if kreis in kreise:
                self._communes_by_kreis.setdefault(kreis, []).append(geom)
                self._commune_by_kreis_name[(kreis, _de_norm(str(row["LAU_NAME"])))] = geom
            if kreis.startswith("09"):
                self._by_communes.setdefault(kreis, {})[_de_norm(str(row["LAU_NAME"]))] = (
                    str(row["LAU_NAME"]), geom)
                self._bavaria_rows.append((str(row["GISCO_ID"]), str(row["LAU_NAME"]), geom))

    def _draw_gemeinde_areas(self) -> None:
        """Draw each record whose delimitation is a Bavarian Gemeinde list as
        the union of those Gemeinden, when at least MIN_DRAWN_SHARE of the
        names bind; a PDO's drawn polygon replaces its Bétard one in the
        index (Franken's Einzellagen inherit it)."""
        from _lib.de import gemeinde_list

        rows = [(gid, name) for gid, name, _ in self._bavaria_rows]
        geom_by_id = {gid: g for gid, _, g in self._bavaria_rows}
        for fn, spec in sorted(self._gemeinde_areas.items()):
            res = gemeinde_list.resolve(spec["lists"], rows)
            if res.share < MIN_DRAWN_SHARE:
                self._log(f"[de-geom] {spec['slug']}: {len(res.drawn)} of "
                          f"{len(res.drawn) + len(res.unmatched)} listed Gemeinden bind — "
                          f"kept as before; unmatched: {', '.join(res.unmatched)}")
                continue
            geom = unary_union([geom_by_id[gid] for _, gid, _ in res.drawn])
            stats = {
                "matched": len({gid for _, gid, _ in res.drawn}),
                "unmatched": len(res.unmatched),
                "unmatched_names": list(res.unmatched),
                "gemeinden_listed": len(res.drawn) + len(res.unmatched),
                "source_kind": spec["source_kind"],
            }
            self._gemeinde_drawn[fn] = (geom, stats)
            if fn in self._pdo_polygons:
                self._pdo_polygons[fn] = geom
            self._log(f"[de-geom] {spec['slug']}: drawn from the {stats['matched']} Gemeinden "
                      f"its {spec['source_kind']} lists"
                      + (f"; not drawn: {', '.join(res.unmatched)}" if res.unmatched else ""))

    def _bavarian_units(self, area) -> tuple[list[BaseGeometry], list[str], list[str], list[str]]:
        """(geometries, Gemeinden drawn, partial, unmatched) for the Bavarian
        units a delimitation names without a number: the town whose
        Gemarkungen it names fixes the Landkreis, the Gemeinden are matched
        inside it (exact, head word, then a near-spelling — the single
        document writes "Bodholz" for Bodolz). The town is drawn whole and
        reported as partial."""
        from rapidfuzz import fuzz, process

        polys: list[BaseGeometry] = []
        drawn: list[str] = []
        partial: list[str] = []
        unmatched: list[str] = []

        def find(names: dict, wanted: str):
            key = _de_norm(wanted)
            if key in names:
                return names[key]
            heads = [v for k, v in names.items() if k.split(" ")[0] == key]
            if len(heads) == 1:
                return heads[0]
            best = process.extractOne(key, list(names), scorer=fuzz.ratio, score_cutoff=85)
            return names[best[0]] if best else None

        kreise: set[str] = set()
        for town, marks in area.by_partial:
            hits = [(k, v) for k, names in self._by_communes.items()
                    for n, v in names.items() if n.split(" ")[0] == _de_norm(town)]
            if len(hits) != 1:
                unmatched.append(f"{town} ({', '.join(marks)})")
                continue
            kreis, (lau_name, geom) = hits[0]
            kreise.add(kreis)
            polys.append(geom)
            partial.append(f"{lau_name.split(',')[0]} ({', '.join(marks)})")
        for name in area.by_gemeinden:
            hit = None
            for kreis in sorted(kreise):
                hit = find(self._by_communes.get(kreis, {}), name)
                if hit:
                    break
            if hit:
                polys.append(hit[1])
                drawn.append(hit[0].split(",")[0])
            else:
                unmatched.append(name)
        return polys, drawn, partial, unmatched

    def _draw_gemarkung_areas(self, gpkg: Path, pins: dict[str, dict[int, dict]]) -> None:
        """Union the Gemarkungen each listed record names and put the result
        in the place of its Bétard polygon. A unit is drawn when the layer
        carries its number and the printed name agrees with the layer's name
        for it; a record is redrawn only when at least `MIN_DRAWN_SHARE` of
        its units are."""
        from _lib.de.gemarkung import NAME_MATCH_MIN, GemarkungLayer, name_agreement

        layer = GemarkungLayer(gpkg, self.target_crs)
        if not layer.available:
            self._log(f"[de-geom] Gemarkung layer missing ({gpkg}) — "
                      f"{len(self._gemarkung_areas)} record(s) keep their Bétard polygon; "
                      "run scripts/de/00_fetch_data.py")
            return
        for fn, entry in self._gemarkung_areas.items():
            area = entry["area"]
            rec_pins = pins.get(fn, {})
            numbers = {u.number for u in area.units} | {p["number"] for p in rec_pins.values()}
            rows = layer.rows(numbers)
            polys: list[BaseGeometry] = []
            unmatched: list[str] = []
            disagree: list[str] = []
            pinned: list[str] = []
            stale: list[str] = []
            for u in area.units:
                row = rows.get(u.number)
                pin = rec_pins.get(u.number)
                if pin is not None:
                    target = rows.get(int(pin["number"]))
                    if row is not None or target is None:
                        stale.append(f"{u.name} ({u.number})")
                        if row is None:
                            unmatched.append(f"{u.name} ({u.number})")
                            continue
                    else:
                        polys.append(target["geometry"])
                        where = (f" ({target['gemeinde']})"
                                 if target["gemeinde"] != target["name"] else "")
                        pinned.append(f"{u.name} ({u.number}) → {pin['number']} "
                                      f"{target['name']}{where}")
                        continue
                if row is None:
                    unmatched.append(f"{u.name} ({u.number})")
                    continue
                if name_agreement(u.name, row["name"], row["gemeinde"]) < NAME_MATCH_MIN:
                    disagree.append(f"{u.name} ({u.number}; {row['name']}, {row['gemeinde']})")
                    unmatched.append(f"{u.name} ({u.number})")
                    continue
                polys.append(row["geometry"])
            n_gemarkungen = len(polys)
            by_polys, by_drawn, partial, by_unmatched = self._bavarian_units(area)
            unmatched += by_unmatched
            share = n_gemarkungen / max(1, len(area.units))
            head = (f"[de-geom] {entry.get('slug') or fn}: {n_gemarkungen}/{len(area.units)} "
                    f"Gemarkungen ({entry['source_kind']})")
            for name in stale:
                self._log(f"{head} — STALE pin {name}: re-verify scripts/_lib/de/gemarkung_pins.json")
            if share < MIN_DRAWN_SHARE or not polys:
                # Saxony's Landwein prints its own register's numbers the same
                # way: none agrees with a Baden-Württemberg Gemarkung name.
                why = ("numbers of another Land's register" if n_gemarkungen == 0
                       else f"under {MIN_DRAWN_SHARE:.0%}; not in the register: {unmatched[:8]}")
                self._log(f"{head} — not redrawn ({why})")
                continue
            self._pdo_polygons[fn] = unary_union(polys + by_polys)
            self._gemarkung_stats[fn] = {
                "matched": -1,
                "unmatched": len(unmatched),
                "gemarkungen": n_gemarkungen,
                "gemarkungen_listed": len(area.units),
                "gemeinden": by_drawn,
                "partial": partial,
                "names_unmatched": unmatched,
                "name_disagreements": disagree,
                "pinned": pinned,
                "stale_pins": stale,
                "source_kind": entry["source_kind"],
                "attribution": layer.manifest.get("attribution") or "LGL-BW, www.lgl-bw.de",
                "licence": "dl-de/by-2-0",
            }
            self._log(f"{head}; + {len(by_drawn)} Bavarian Gemeinde(n), {len(partial)} drawn "
                      f"whole for a part; pinned {pinned}; not drawn {unmatched}")

    @property
    def n_gemarkung_records(self) -> int:
        return len(self._gemarkung_stats)

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_communes(self) -> int:
        return len(self._commune_by_kreis_name)

    def landwein_commune_union(
        self, file_number: str
    ) -> tuple[BaseGeometry | None, dict]:
        """Union the GISCO communes for a curated DE_LANDWEIN_AREA wine.
        Returns (geometry, stats)."""
        area = DE_LANDWEIN_AREA.get(file_number or "")
        if not area:
            return None, {"matched": 0, "unmatched": 0}
        polys: list[BaseGeometry] = []
        n_kreis = 0
        unmatched: list[str] = []
        for name in (*area.get("landkreise", []), *area.get("kreisfreie", [])):
            code = _DE_KREIS_AGS.get(_de_norm(name))
            members = self._communes_by_kreis.get(code or "", [])
            if members:
                polys.extend(members)
                n_kreis += 1
            else:
                unmatched.append(name)
        n_gem = 0
        partial: list[str] = []
        drawn: list[str] = []
        for g in area.get("gemeinden", []):
            code = _DE_KREIS_AGS.get(_de_norm(g["kreis"]))
            geom = self._commune_by_kreis_name.get((code or "", _de_norm(g["name"])))
            if geom is not None:
                polys.append(geom)
                n_gem += 1
                drawn.append(g.get("label") or g["name"])
                if g.get("partial"):
                    partial.append(g.get("spec") or g["name"])
            else:
                unmatched.append(g.get("spec") or g["name"])
        stats = {
            "matched": len(polys) if polys else 0,
            "unmatched": len(unmatched),
            "kreise": n_kreis,
            "gemeinden": n_gem,
            "unmatched_names": unmatched,
            # a Gemeinde drawn whole where the specification names only some
            # of its Gemarkungen
            **({"partial": partial} if partial else {}),
            # the communes are our reading of the specification's prose: the
            # card names them and prints the entry's disclosure sentence
            **({"reading": {"units": drawn, "disclose": area["reading"]["disclose"]}}
               if area.get("reading") else {}),
        }
        if not polys:
            return None, stats
        return unary_union(polys), stats

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    def pgi_union(self, pgi_file_number: str) -> tuple[BaseGeometry | None, dict]:
        """Union the member-PDO polygons for one of the DE PGIs.
        Returns (geometry, stats)."""
        members = DE_PGI_MEMBER_PDOS.get(pgi_file_number or "", ())
        polys: list[BaseGeometry] = []
        for fn in members:
            geom = self._pdo_polygons.get(fn)
            if geom is not None and not geom.is_empty:
                polys.append(geom)
        stats = {"members": len(members), "resolved": len(polys)}
        # Members drawn from their Gemarkungen rather than from Bétard: the
        # card says so for the union too.
        drawn = [self._gemarkung_stats[fn] for fn in members if fn in self._gemarkung_stats]
        if drawn:
            stats["gemarkung_members"] = len(drawn)
            stats["attribution"] = drawn[0]["attribution"]
        # … or from the units their own texts name (the other Länder)
        listed = [self._unit_drawn[fn] for fn in members if fn in self._unit_drawn]
        if listed and not drawn:
            layer_credits: list[dict] = []
            for _g, _s, st in listed:
                for c in st.get("credits") or []:
                    if c not in layer_credits:
                        layer_credits.append(c)
            if layer_credits:
                stats["gemarkung_members"] = len(listed)
                stats["credits"] = layer_credits
                stats["attribution"] = "; ".join(c["text"] for c in layer_credits)
        if not polys:
            return None, stats
        return unary_union(polys), stats

    def einzellage_parent(self, file_number: str) -> tuple[BaseGeometry | None, str]:
        """Resolve an Einzellage PDO via its parent Anbaugebiet polygon.
        Returns (geometry, parent_file_number) or (None, '')."""
        parent_fn = DE_EINZELLAGE_PARENT_PDO.get(file_number or "")
        if not parent_fn:
            return None, ""
        return self._pdo_polygons.get(parent_fn), parent_fn

    def resolve(self, file_number: str) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one DE record by file_number.
        Returns (geometry, geom_source, stats). `matched == -1` is the
        project convention for a polygon resolved whole rather than
        commune-counted."""
        fn = file_number or ""
        # 1. Einzellage sub-denominations inherit parent Anbaugebiet.
        if fn in DE_EINZELLAGE_PARENT_PDO:
            geom, parent_fn = self.einzellage_parent(fn)
            if geom is not None:
                return geom, "parent-appellation", {
                    "matched": -1, "unmatched": 0, "parent_fn": parent_fn,
                }
            # Even if parent missing, fall through — but this shouldn't happen
            return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}
        # 2. The record's own Bavarian Gemeinde list (Franken, Landwein Main).
        if fn in self._gemeinde_drawn:
            geom, stats = self._gemeinde_drawn[fn]
            return geom, "gisco-commune-union", dict(stats)
        # 2a. The record's own list in another layout (Rheingau's Gemeinden,
        #     Mittelrhein's and Saale-Unstrut's Gemarkungen, a Landwein's own).
        if fn in self._unit_drawn:
            geom, source, stats = self._unit_drawn[fn]
            return geom, source, dict(stats)
        # 3. PGI region-union.
        if fn in DE_PGI_MEMBER_PDOS:
            geom, union_stats = self.pgi_union(fn)
            stats = {
                "matched": -1 if geom is not None else 0,
                "unmatched": 0,
                **union_stats,
            }
            if geom is not None:
                return geom, "region-pdo-union", stats
            return None, "stub-no-geometry", stats
        # 4. The record's own Gemarkungen (Baden, Württemberg), else the
        #    direct Figshare PDO match.
        geom = self._pdo_polygons.get(fn)
        if geom is not None and fn in self._gemarkung_stats:
            return geom, "lgl-gemarkung-union", dict(self._gemarkung_stats[fn])
        if geom is not None:
            return geom, "figshare-pdo", {"matched": -1, "unmatched": 0}
        # 5. Curated commune-list union (multi-Bundesland Landwein PGIs
        #    not coextensive with one Anbaugebiet — Brandenburger,
        #    Taubertäler, …).
        if fn in DE_LANDWEIN_AREA:
            geom, stats = self.landwein_commune_union(fn)
            if geom is not None:
                return geom, "gisco-commune-union", stats
            return None, "stub-no-geometry", stats
        # 6. Stub.
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}

    def union_all(self, file_numbers: Iterable[str]) -> BaseGeometry | None:
        polys = [
            self._pdo_polygons[fn]
            for fn in file_numbers
            if fn in self._pdo_polygons
        ]
        return unary_union(polys) if polys else None
