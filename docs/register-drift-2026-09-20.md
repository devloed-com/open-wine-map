# Register drift check — 2026-09-20

What changed upstream since the caches under `raw/` were built: new cahiers / single
documents, new registrations, cancellations. Method and re-run recipe at the end.
Scratch outputs: `/tmp/owm-boagri-drift.log`, `/tmp/owm-show-texte-compare.log`.

## 1. Deprecated GIs (cancellation regulation verified on EUR-Lex)

| GI | Country | Cancellation | Corpus state today |
|---|---|---|---|
| Cité de Carcassonne (PGI-FR-A1203) | FR | Reg. (EU) 2025/2538, 16 Dec 2025; INAO: arrêté du 31 mars 2025 (annulation) | still built as IGP (SIQO 2025-12-31 still lists it `Publié`; `raw/inao/register/unresolved.json` already says `withdrawn-registration`) |
| Coteaux de Narbonne (PGI-FR-A1202) | FR | Reg. (EU) 2025/2536, 16 Dec 2025; INAO: arrêté du 31 mars 2025 | still built as IGP |
| Sable de Camargue (PGI-FR-A1227) | FR | Reg. (EU) 2023/2162 — the IGP became the AOC PDO-FR-02848 | AOC already bound; nothing to do |
| Salemi (PGI-IT-A0807) | IT | Reg. (EU) 2026/1043, 12 May 2026 | still in `raw/it/eambrosia/index.json` (523) as the one `stub-no-geometry`; add to `CANCELLED_GIS` in `scripts/it/00_fetch_data.py` → 522 |
| Ambt Delden (PDO-NL-02169) | NL | Reg. (EU) 2026/1068, 18 May 2026 | still built (English-template record, 9 facts); NL stage 00 has no cancellation registry yet — mirror the AT `CANCELLED_PDOS` pattern |

## 2. New registrations

| GI | Country | Registration | Notes |
|---|---|---|---|
| Mura / Murai (PDO-HU-02817) | HU | Reg. (EU) 2026/1792, 15 Jul 2026; single document OJ C/2026/1833 | not in `raw/hu/eambrosia/index.json` (41 → 42); needs a `_REGION_BY_FILE_NUMBER` entry (Zala / Balaton?) and geometry (post-Bétard → commune list) |

Pending on eAmbrosia (not registered yet, no action): **published for opposition** — Lumbarda (HR, C/2025/6437), Nivegy-völgy (HU, C/2026/2812), Sümeg (HU, C/2026/3477); **applied** — Laudun and Grés de Montpellier (FR; both already built from SIQO/INAO as AOC), mittlere Havel (DE), Viñedos de Álava / Tharsys / Cercado de la Huerta Nueva (ES), Buje (HR), Egri Bikavér / Egri Csillag (HU), Pignoletto (IT), Strunga (RO), Račanská frankovka (SK). GOV.UK: The Crouch Valley still `applied-for` (2023-03-06).

Stale FR EU registrations with no SIQO row (neither new nor deprecated, just INAO merges the register never followed): Blaye, Côtes de Blaye, Sainte-Foy-Bordeaux, Cabernet de Saumur.

## 3. France — newer cahier on INAO than the one we hold

INAO's product page now links a **newer homologation arrêté** for 22 appellations (our BO Agri fetch is April/May 2026). The PDFs are not downloaded yet: `info.agriculture.gouv.fr` resets every connection from this machine today (see method), so stage 01 could not fetch them.

| id | Appellation | We hold | INAO now links |
|---:|---|---|---|
| 125 | Coteaux du Giennois | 2020-09-25 Arrêté du 25 septembre 2020 homologuant le cahier des charge | **2026-09-02** Arrêté du 2 septembre 2026 homologuant le cahier des charges |
| 171 | Côte de Nuits-Villages ou Vins fins de la | 2011-10-24 Décret n°2011-1350 du 24 octobre 2011 relatif à l'appellatio | **2026-09-02** Arrêté du 2 septembre 2026 homologuant le cahier des charges |
| 4 | Côtes de Toul | 2011-09-22 Décret n°2011-1159 du 22 septembre 2011 modifié relatif à l' | **2026-09-02** Arrêté du 2 septembre 2026 homologuant le cahier des charges |
| 32 | Entre-deux-Mers | 2025-09-19 Arrêté du 19 septembre 2025 homologuant le cahier des charge | **2026-09-02** Arrêté du 2 septembre 2026 homologuant le cahier des charges |
| 187 | L'Etoile | 2011-09-09 Décret n°2011-1096 du 9 septembre 2011 modifié relatif à l'a | **2026-09-02** Arrêté du 2 septembre 2026 homologuant le cahier des charges |
| 1091 | Marc d'Alsace | —  | **2026-09-02** Arrêté du 2 septembre 2026 relatif à l'appellation d'origine |
| 583 | Mâcon | 2023-12-19 Arrêté du 19 décembre 2023 homologuant le cahier des charges | **2026-08-07** Arrêté du 7 août 2026 homologuant le cahier des charges de l |
| 1032 | Beaujolais | 2022-09-02 Arrêté du 2 septembre 2022 homologuant le cahier des charges | **2026-08-05** Arrêté du 5 août 2026 homologuant le cahier des charges de l |
| 246 | Viré-Clessé | 2011-12-05 Décret n°2011-1794 du 5 décembre 2011 modifié relatif à l'ap | **2026-07-27** Arrêté du 27 juillet 2026 homologuant le cahier des charges  |
| 136 | Blagny | 2011-11-28 Décret n°2011-1690 du 28 novembre 2011 relatif à l'appellati | **2026-06-08** Arrêté du 8 juin 2026 homologuant le cahier des charges de l |
| 582 | Coteaux varois en Provence | 2022-04-25 Arrêté du 25 avril 2022 homologuant le cahier des charges de | **2026-06-08** Arrêté du 8 juin 2026 homologuant le cahier des charges de l |
| 91 | Crémant de Loire | 2024-01-12 Arrêté du 12 janvier 2024 homologuant le cahier des charges  | **2026-06-08** Arrêté du 8 juin 2026 homologuant le cahier des charges de l |
| 690 | Moselle | 2019-09-12 Arrêté du 12 septembre 2019 homologant le cahier des charges | **2026-06-08** Arrêté du 8 juin 2026 homologuant le cahier des charges de l |
| 304 | Muscat de Frontignan ou Frontignan ou Vin | 2011-12-02 Décret n°2011-1761 du 2 décembre 2011 relatif à l'appellatio | **2026-06-08** Arrêté du 8 juin 2026 homologuant le cahier des charges de l |
| 329 | Pineau des Charentes | 2025-07-01 Arrêté du 1er juillet 2025 homologuant le cahier des charges | **2026-06-08** Arrêté du 8 juin 2026 homologuant le cahier des charges de l |
| 107 | Rosé de Loire | 2024-01-12 Arrêté du 12 janvier 2024 homologuant le cahier des charges  | **2026-06-08** Arrêté du 8 juin 2026 homologuant le cahier des charges de l |
| 478 | Saint-Bris | 2011-11-16 Décret n°2011-1570 du 16 novembre 2011 relatif à l'appellati | **2026-06-08** Arrêté du 8 juin 2026 homologuant le cahier des charges de l |
| 1130 | Vinsobres | 2024-07-04 Arrêté du 4 juillet 2024 homologuant le cahier des charges d | **2026-06-08** Arrêté du 8 juin 2026 homologuant le cahier des charges de l |
| 585 | Bordeaux supérieur | 2025-11-26 Arrêté du 26 novembre 2025 homologuant le cahier des charges | **2026-06-04** Arrêté du 4 juin 2026 homologuant le cahier des charges de l |
| 204 | Meursault | 2011-11-28 Décret n°2011-1689 du 28 novembre 2011 relatif à l'appellati | **2026-06-04** Arrêté du 4 juin 2026 homologuant le cahier des charges de l |
| 297 | Côtes de Provence | 2025-07-28 Arrêté du 28 juillet 2025 homologuant le cahier des charges  | **2026-04-27** Arrêté du 27 avril 2026 homologuant le cahier des charges de |
| 896 | Coteaux de l'Auxois | 2015-11-26 Arrêté du 26 novembre 2015 modifié relatif à l'indication gé | **2022-09-20** Arrêté du 20 septembre 2022 homologuant le cahier des charge |

Only 3 of the 22 (Bordeaux supérieur, Coteaux de l'Auxois, Vinsobres) were also flagged by eAmbrosia — the EU register is a weak proxy for national arrêtés.

**Regression to check:** Crémant de Bordeaux (31) — we hold the arrêté du 25 novembre 2025; INAO's product page now links the older arrêté du 22 mars 2021.

### Modification in progress (product page shows a PNO notice instead of the cahier link)

Bordeaux (14), Chinon (85), Clos de Vougeot ou Clos Vougeot (162), Cognac ou Eau-de-vie de Cognac ou Eau-de-v (320), Coteaux d'Aix-en-Provence (295), Grés de Montpellier (1265), Ladoix (192), Muscat de Lunel (309), Premières Côtes de Bordeaux (64), Périgord (900), Saumur (110). The link-less state means a *procédure nationale d'opposition* on a cahier modification is open; a new arrêté will follow. Alsace (1) is in the same state (its manifest entry is a curator override, so it reports as a miss).

### Same text, different BO Agri document id (51)

INAO re-pointed the same décret/arrêté to another BO Agri bundle or host form (`/boagri/` ↔ `/gedei/site/bo-agri/`), or replaced a curator-override / mirror URL with its own link (Bergerac, Franche-Comté, Pouilly-Loché, Pouilly-Vinzelles, Côte de Nuits-Villages, Muscat de Frontignan, …). Not new content; a stage 01 re-run will re-download them (content-addressed, so a byte-identical bundle is a no-op).

### eAmbrosia FR modifications not (yet) visible on INAO

83 FR GIs have an eAmbrosia `modificationDate` after our fetch; 60 of them carry a new OJ C single document — the whole Alsace grand cru wave (51, 14 Aug–3 Sep 2026), Alsace, Crémant d'Alsace, Champagne, Coteaux champenois, Savoie (Reg. 2026/2016), Bourgogne aligoté, Côtes de Bordeaux, Clos de Vougeot, Muscat de Lunel, Côtes du Marmandais, Bonnezeaux, Coteaux du Layon, Coteaux de l'Aubance, Duché d'Uzès, Cheverny, Cour-Cheverny, Anjou Villages, Cassis, Mont Caume, Crémant de Bordeaux. Their INAO cahier link is unchanged, so either the arrêté predates our fetch (the OJ C publication lags the national arrêté) or the update is inside a shared bundle we cannot diff while BO Agri is unreachable. 42 FR GIs carry `amendmentsInProgressFlag`. Full list: scratchpad `modified-since-fetch.txt`.

## 4. Other countries — modified on eAmbrosia after our document fetch

| Country | GIs | Detail |
|---|---:|---|
| ES | 14 | new OJ C single document: Almansa (C/2026/3796), Arlanza (C/2026/4630), Binissalem (C/2026/4121), Condado de Huelva (C/2026/4233), Jerez-Xérès-Sherry (C/2026/4549), Manzanilla de Sanlúcar (C/2026/4513), Manchuela (C/2026/3565), Pago de Otazu (C/2026/3580, first ever), Penedès (C/2026/2777), 3 Riberas (C/2026/3089, first ever); date-only: Arribes, Conca de Barberà, Navarra, Priorat (new register attachments) |
| HU | 8 | Tokaj (Reg. 2026/1556 + corrigendum), Balatonfüred-Csopak (C/2026/3256, first ever), Csopak (C/2026/4519); amendments in progress: Badacsony, Felső-Magyarország, Pécs, Szekszárd, Villány |
| IT | 8 | Asti (C/2026/4239), Fara (C/2026/2778), Morellino di Scansano (C/2026/2835), Terre Abruzzesi (C/2026/4811), Romagna (Reg. 2026/1920), Romagna Albana; in progress: Marsala, Toscano |
| RO | 3 | Drăgășani (Reg. 2026/1702), Segarcea (Reg. 2026/2106); in progress: Babadag |
| SI | 2 | Belokranjec (C/2026/3572), Metliška črnina (C/2026/3598) — first EU single documents for these two national-spec stubs |
| DE | 2 | Landwein Main (C/2026/4338, first ever); Württemberg in progress |
| GR | 1 | Τύρναβος (C/2026/3788) |
| PT | 2 | Alentejano, Douro — modification date only, no new publication |
| NL | 1 | Ambt Delden — the cancellation |
| AT, BE, BG, CY, CZ, HR, LU, MT, SK | 0 | — |

RO also shows 8 "new" file numbers (Murfatlar, Târnave, Panciu ×2, Dealu Mare ×3, Dealurile Munteniei): the duplicate administrative re-registrations RO stage 00 already dedupes — not new wines. NL shows Maasvallei Limburg as "new" only because it is BE-owned.

## 5. Unchanged spines

- SIQO referentiel: the live data.gouv.fr resource is still the 2025-12-31 extraction, sha256 identical to `raw/inao/siqo-referentiel.csv`.
- GOV.UK wines register: 6 registered, unchanged.
- CH OFAG répertoire: annual (1 Jan); the 2026 edition is the one cached.

## Method / re-run

1. `curl https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications` (4,017 rows) diffed against every `raw/<cc>/eambrosia/index.json` (new / gone / `removedFlag` / `modificationDate` / `publications`) and, for FR, against `raw/inao/register/resolved.json`; per-GI `modificationDate` compared with the document `fetched_at` in each country's manifests. Cancellations confirmed by reading the regulation title on EUR-Lex (`legal-content/EN/TXT/HTML/?uri=CELEX:…`).
2. FR: re-walked all 466 INAO product pages with stage 01's own `resolve_cahier` (no downloads, manifest untouched) and compared the *dated title* of the prior vs current `show_texte` — a changed BO Agri URL alone is not a signal (51 same-text relinks).
3. A plain `scripts/01_scrape_cahiers.py` run is the designed detector, but it stalled at 70 s/appellation because `info.agriculture.gouv.fr` reset every connection (BO Agri root returns HTTP 000 from here — try with the VPN off). Two stage-01 regex gaps surfaced: `BOAGRI_RE` misses the new `…/boagri/rectificatif-<uuid>/telechargement` form and `LEGIFRANCE_JORFTEXT_RE` misses the `legifrance.gouv.fr/eli/arrete/…` form INAO now emits (Atlantique's page carries only those two links).
