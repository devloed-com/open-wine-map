"""Per-canton cantonal-règlement URL registry.

Each Swiss canton publishes its own wine règlement on its official legal-
portal ("recueil systématique" / "Systematische Sammlung" / "Raccolta
delle leggi"). The shelf-number is stable across portal redesigns and
serves as the canonical join key.

Each entry carries:
  - url:      canonical URL of the règlement (HTML preferred, PDF accepted)
  - shelf:    cantonal shelf number / SR-number
  - lang:     règlement source language (de / fr / it / rm)
  - format:   "html" or "pdf"
  - source:   one-line description for the panel attribution
  - license:  license / open-data terms note (empty if not stated)
  - note:     curator notes (defers, mergers, etc.)

Cantons whose entry has `url=""` are pending research — they are
emitted as spine-only stubs by stage 02 until the URL is filled in.
"""

from __future__ import annotations

from typing import TypedDict


class ReglementEntry(TypedDict, total=False):
    url: str
    shelf: str
    lang: str
    format: str
    source: str
    license: str
    note: str


# Initial seeded entries — researched + verified 2026-05.
# The 21 remaining cantons are filled in by a follow-up research pass
# and merged into this dict; see `CANTON_REGLEMENT_URLS_PENDING` below.
CANTON_REGLEMENT_URLS: dict[str, ReglementEntry] = {
    "vs": {
        "url": "https://lex.vs.ch/api/fr/versions/133/pdf_file",
        "shelf": "RS 916.142",
        "lang": "fr",
        "format": "pdf",
        "source": "Ordonnance sur la vigne et le vin (OVV) — Canton du Valais",
        "license": "Recueil systématique du Valais — accès libre, source à citer",
        "note": "Bilingual canton (FR/DE); wine production is overwhelmingly on the FR side, so FR is the authoritative version.",
    },
    "vd": {
        "url": "https://www.vd.ch/fileadmin/user_upload/themes/economie_emploi/viticulture/fichiers_pdf/REG_20240101_R%C3%A8glement-vins-vaudois-VD.pdf",
        "shelf": "RSV 916.125.2",
        "lang": "fr",
        "format": "pdf",
        "source": "Règlement sur les vins vaudois — État de Vaud",
        "license": "Canton de Vaud, open data, source à citer",
        "note": "",
    },
    "ge": {
        "url": "https://silgeneve.ch/legis/data/rsg_m2_50p05.htm",
        "shelf": "rsGE M 2 50.05",
        "lang": "fr",
        "format": "html",
        "source": "Règlement sur la vigne et les vins de Genève (RVV) — République et canton de Genève",
        "license": "SILGENEVE — accès libre, source à citer",
        "note": "HTML in windows-1252 encoding; the parser autodetects via the meta tag.",
    },
    "ti": {
        "url": "https://m3.ti.ch/CAN/RLeggi/public/index.php/raccolta-leggi/pdfatto/atto/476",
        "shelf": "RL TI 916.150",
        "lang": "it",
        "format": "pdf",
        "source": "Regolamento sulla viticoltura — Repubblica e Cantone Ticino",
        "license": "Raccolta delle leggi del Cantone Ticino, accesso libero",
        "note": "The web URL `/legge/num/476` is a JS shell; the PDF is served at /pdfatto/atto/476.",
    },
    "ne": {
        "url": "https://rsn.ne.ch/DATA/program/books/RSN2010/20085/htm/9161201.htm",
        "shelf": "RSN 916.120.1",
        "lang": "fr",
        "format": "html",
        "source": "Arrêté concernant les AOC des vins de Neuchâtel — République et Canton de Neuchâtel",
        "license": "Recueil systématique neuchâtelois — accès libre, source à citer",
        "note": "Post-2016 simplification — a single 'AOC Neuchâtel' supersedes the 24 prior commune-level appellations.",
    },
    # ── 21 remaining cantons (researched + verified 2026-05) ──
    "ag": {
        "url": "https://gesetzessammlungen.ag.ch/app/de/texts_of_law/915.712",
        "shelf": "SAR 915.712", "lang": "de", "format": "html",
        "source": "Verordnung über den Weinbau — Kanton Aargau",
        "license": "Kanton Aargau, official systematische Sammlung",
        "note": "25.06.2008.",
    },
    "ai": {
        "url": "https://ai.clex.ch/app/de/texts_of_law/916.610",
        "shelf": "GS 916.610", "lang": "de", "format": "html",
        "source": "Weinverordnung (WeinV) — Kanton Appenzell Innerrhoden",
        "license": "Kanton Appenzell Innerrhoden, official",
        "note": "Recent Weinverordnung; ~5 ha vines, very small corpus.",
    },
    "ar": {
        "url": "https://ar.clex.ch/app/de/texts_of_law/920.16",
        "shelf": "bGS 920.16", "lang": "de", "format": "html",
        "source": "Kantonale Weinverordnung (kWeinV) — Kanton Appenzell Ausserrhoden",
        "license": "Kanton Appenzell Ausserrhoden, official",
        "note": "",
    },
    "be": {
        "url": "https://www.belex.sites.be.ch/app/de/texts_of_law/916.141.1",
        "shelf": "BSG 916.141.1", "lang": "de", "format": "html",
        "source": "Gesetz über den Rebbau (RebG) — Kanton Bern",
        "license": "Kanton Bern, official, free reuse",
        "note": "Bilingual canton; wine reg published as DE-primary. Bielersee/Thunersee AOC règlements separate (cooperative-issued).",
    },
    "bl": {
        "url": "https://bl.clex.ch/app/de/texts_of_law/516.31",
        "shelf": "SGS 516.31", "lang": "de", "format": "html",
        "source": "Verordnung über den Pflanzenbau — Kanton Basel-Landschaft",
        "license": "Kanton Basel-Landschaft, official",
        "note": "Wine integrated into the general plant-cultivation ordinance; no standalone Weinverordnung.",
    },
    "bs": {
        "url": "https://www.gesetzessammlung.bs.ch/app/de/texts_of_law/911.200",
        "shelf": "SG 911.200", "lang": "de", "format": "html",
        "source": "Vereinbarung über den Vollzug des Landwirtschaftsrechts — Kanton Basel-Stadt",
        "license": "Kanton Basel-Stadt, official",
        "note": "Inter-cantonal Vereinbarung with BL; no standalone BS wine reg — defers to BL SGS 516.31.",
    },
    "fr": {
        "url": "https://bdlf.fr.ch/app/fr/texts_of_law/912.4.111",
        "shelf": "RSF 912.4.111", "lang": "fr", "format": "html",
        "source": "Ordonnance sur la vigne et le vin — État de Fribourg",
        "license": "Etat de Fribourg, BDLF — official",
        "note": "Ordonnance du 01.10.2009. Bilingual canton; FR is the wine-AOC primary (Cheyres, Vully).",
    },
    "gl": {
        "url": "https://gesetze.gl.ch/app/de/texts_of_law/IX%20D/621/1",
        "shelf": "GS IX D/621/1", "lang": "de", "format": "html",
        "source": "Kantonale Weinbauverordnung — Kanton Glarus",
        "license": "Kanton Glarus, official",
        "note": "Tiny vineyard area.",
    },
    "gr": {
        "url": "https://www.gr-lex.gr.ch/app/de/texts_of_law/917.400",
        "shelf": "BR 917.400", "lang": "de", "format": "html",
        "source": "Ausführungsbestimmungen zur Weinverordnung — Kanton Graubünden",
        "license": "Kanton Graubünden, Bündner Rechtsbuch — official (no legal effect disclaimer)",
        "note": "Trilingual canton (DE/IT/RM); DE règlement is authoritative. Misox uses TI rules.",
    },
    "ju": {
        "url": "https://rsju.jura.ch/fr/viewdocument.html?idn=20192&id=33845",
        "shelf": "RSJU 916.141", "lang": "fr", "format": "html",
        "source": "Ordonnance sur la viticulture et l'appellation des vins — République et Canton du Jura",
        "license": "Rép. et Canton du Jura, RSJU — official",
        "note": "AOC Jura effective 2016 vintage.",
    },
    "lu": {
        "url": "https://srl.lu.ch/app/de/texts_of_law/917",
        "shelf": "SRL 917", "lang": "de", "format": "html",
        "source": "Verordnung über die kontrollierte Ursprungsbezeichnung Wein — Kanton Luzern",
        "license": "Kanton Luzern, SRL — official",
        "note": "Central-CH joint AOC framework.",
    },
    "nw": {
        "url": "https://gesetze.nw.ch/app/de/texts_of_law/821.12",
        "shelf": "NG 821.12", "lang": "de", "format": "html",
        "source": "Vollzugsverordnung über die kontrollierte Ursprungsbezeichnung für Weine — Kanton Nidwalden",
        "license": "Kanton Nidwalden, official",
        "note": "Central-CH joint AOC framework.",
    },
    "ow": {
        "url": "https://gdb.ow.ch/app/de/texts_of_law/921.117",
        "shelf": "GDB 921.117", "lang": "de", "format": "html",
        "source": "Ausführungsbestimmungen über die kontrollierte Ursprungsbezeichnung für Weine — Kanton Obwalden",
        "license": "Kanton Obwalden, official",
        "note": "Central-CH joint AOC framework.",
    },
    "sg": {
        "url": "https://www.gesetzessammlung.sg.ch/app/de/texts_of_law/610.11",
        "shelf": "sGS 610.11", "lang": "de", "format": "html",
        "source": "Landwirtschaftsverordnung — Kanton St. Gallen",
        "license": "Kanton St. Gallen, official",
        "note": "Wine folded into the general agriculture ordinance; no standalone Weinverordnung.",
    },
    "sh": {
        "url": "https://rechtsbuch.sh.ch/app/de/texts_of_law/817.402",
        "shelf": "SHR 817.402", "lang": "de", "format": "html",
        "source": "Kantonale Weinverordnung — Kanton Schaffhausen",
        "license": "Kanton Schaffhausen, official",
        "note": "03.11.2009; 2 production regions (Blauburgunder / Riesling-Sylvaner).",
    },
    "so": {
        "url": "https://bl.clex.ch/app/de/texts_of_law/516.34",
        "shelf": "BGS 516.34 (refers to BL SGS 516.31)", "lang": "de", "format": "html",
        "source": "Vereinbarung über die Zusammenarbeit im Rebbau — Kanton Solothurn",
        "license": "Kanton Solothurn, official",
        "note": "No standalone SO Weinverordnung; defers to BL SGS 516.31.",
    },
    "sz": {
        "url": "https://www.sz.ch/public/upload/assets/29708/312_711.pdf",
        "shelf": "SRSZ 312.711", "lang": "de", "format": "pdf",
        "source": "Verordnung über den Weinbau (WBV) — Kanton Schwyz",
        "license": "Kanton Schwyz, official",
        "note": "23.02.2010.",
    },
    "tg": {
        "url": "https://www.rechtsbuch.tg.ch/app/de/texts_of_law/910.11",
        "shelf": "RB 910.11", "lang": "de", "format": "html",
        "source": "Verordnung zum Landwirtschaftsgesetz — Kanton Thurgau",
        "license": "Kanton Thurgau, official",
        "note": "Wine integrated into the general agriculture ordinance; no standalone Weinverordnung.",
    },
    "ur": {
        "url": "https://www.lexfind.ch/dtah/82713/2/60-3231.pdf",
        "shelf": "RB 60.3231", "lang": "de", "format": "pdf",
        "source": "Weinreglement — Kanton Uri",
        "license": "Kanton Uri, official (via lexfind mirror)",
        "note": "~5.7 ha vines, very small corpus.",
    },
    "zg": {
        "url": "https://bgs.zg.ch/app/de/texts_of_law/924.25",
        "shelf": "BGS 924.25", "lang": "de", "format": "html",
        "source": "Reglement über die kontrollierte Ursprungsbezeichnung (AOC Zug) — Kanton Zug",
        "license": "Kanton Zug, official",
        "note": "ZG recognised as full wine canton in 2023.",
    },
    "zh": {
        "url": "https://www.zh.ch/de/politik-staat/gesetze-beschluesse/gesetzessammlung/zhlex-ls/erlass-916_51-1980_11_19-1980_01_01-062.html",
        "shelf": "LS 916.51", "lang": "de", "format": "html",
        "source": "Verordnung über den Rebbau — Kanton Zürich",
        "license": "Kanton Zürich, ZH-Lex — official",
        "note": "19.11.1980. ALN issues operational Verfügung as supplement.",
    },
}


CANTON_REGLEMENT_URLS_PENDING: dict[str, ReglementEntry] = {}


def reglement_for_canton(canton: str) -> ReglementEntry | None:
    """Return the cantonal-règlement entry for the given canton code, or
    None if no URL is registered yet."""
    entry = CANTON_REGLEMENT_URLS.get((canton or "").lower())
    if entry and entry.get("url"):
        return entry
    return None


def all_resolved_cantons() -> list[str]:
    """List of canton codes with a working règlement URL."""
    return sorted(
        c for c, e in CANTON_REGLEMENT_URLS.items() if e.get("url")
    )


def all_pending_cantons() -> list[str]:
    """List of canton codes still awaiting a règlement URL."""
    return sorted(CANTON_REGLEMENT_URLS_PENDING.keys())
