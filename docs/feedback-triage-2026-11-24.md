# Visitor feedback triage — 2026-11-24

Queue: `scripts/feedback_report.py --range 30d`, rows after the 2026-11-23
triage (anything after 2026-11-22 21:00): **one flag**, no note, no name offered.

| flagged | aspect | locale · view | verdict |
|---|---|---|---|
| Ahr, 2026-11-23 13:00 (not retracted) | boundary | es · zone z10 | no defect: the polygon is exactly the seven Gemeinden the specification names |

## Ahr — boundary (de DOP, Bétard polygon)

**The text.** Ahr is a stub (no EU single document); its BLE Produktspezifikation
§ 3 reads: «Zur geschützten Ursprungsbezeichnung gehören die Rebflächen der
Gemeinden Ahrbrück, Altenahr, Dernau, Grafschaft, Mayschoß, Rech und Bad
Neuenahr-Ahrweiler im Landkreis Ahrweiler des Landes Rheinland-Pfalz.»

**The polygon.** `figshare-pdo`, 164 km². Against GISCO LAU 2024 it covers those
seven Gemeinden at 99.6–100 % each and nothing else (a 0.1 km² edge sliver of
Wachtberg). The cached de.wikipedia article (Ahr (Weinanbaugebiet), rev.
264032445) places the vineyards "entlang der Ahr zwischen Altenahr und
Heimersheim", all inside them.

**What the visitor likely saw.** At z10 the shape is the seven municipalities
whole — Grafschaft (57 km²) and most of Bad Neuenahr-Ahrweiler are plateau, the
vines a ribbon along 18 km of valley. The card already says what the shape is:
"Approximate area — polygon from the Bétard 2022 dataset (EU PDOs), at commune
resolution." The text delimits the vineyard land *in* those Gemeinden; no public
German parcel layer is read by the build, and a land-cover layer was declined
for Champagne on 2026-11-23. No change.

## Isolated or broader — the German polygons against their own lists

**Failure mode looked for:** *a German polygon that does not match the
delimitation its document writes.* `audit_geometry_vs_text.py --country de`
returns NO-TEXT / NO-UNITS for all 78 German records — it has no German reader —
so no German polygon had ever been checked against its text. A one-off sweep
(GISCO LAU 2024, names scoped to the Land, homonyms by distance to the other
named Gemeinden, never by the polygon under test) over the eight Bétard-drawn
Anbaugebiete whose text lists Gemeinden:

| region | listed | drawn | result |
|---|---:|---|---|
| Ahr | 7 | the 7 | match |
| Hessische Bergstraße | 9 | the 9 | match |
| Rheinhessen | 133 | the 133 | match |
| Pfalz | 141 | the 141 | match (the PDF never closes the bracket after Landau's Ortsteile) |
| Mosel | 135 | the 135 | match (Burgen and Urbar listed twice, for two Kreise; Perl's Ortsteile in the Saarland) |
| Nahe | 91 | the 91 | match ("Boos / Roth / Schöneberg / Weinsheim bei Bad Kreuznach") |
| Mittelrhein | the RLP Gemeinden + 3 NRW Gemarkungen | the RLP Gemeinden; Bonn, Königswinter, Bad Honnef whole | NRW at city resolution (Bonn 142 km² for Kessenich) |
| Rheingau | 12 | 11 | **Frankfurt am Main** named, not drawn |
| Franken | 127 (2025) | 124 of them + 15 others | **the 15 the 2025 amendment removed are drawn; the 3 it added are not** |

The 2026 single documents of Rheinhessen (C/2026/1820), Mosel (C/2026/1628),
Nahe (C/2026/1289), Pfalz (C/2026/898) and Mittelrhein (C/2026/738) list the
same names as their BLE § 4, so those five Bétard-delta FLAGGED records are
REVIEWED (`scripts/_lib/betard_delta_overrides.json`): the post-snapshot
amendments did not move their boundary.

### Franken — the 2025 amendment, not drawn

The standard amendment PDO-DE-A1267-AM01 (8 October 2025, published as
C/2025/6794), «Abgrenzung des Gebiets»: «Folgende Gemeinden (Gemarkungen) und
deren Ortsteile wurden gestrichen: … Landkreis Bamberg: Kemmern — … Landkreis
Neustadt an der Aisch – Bad Windsheim: Markt Erlbach, Uffenheim — … Landkreis
Haßberge: Wonfurt — … Landkreis Kitzingen: Martinsheim, Wiesentheid — …
Landkreis Main-Spessart: Haßloch — … Landkreis Schweinfurt: Röthlein, Werneck —
… Landkreis Würzburg: Altertheim, Aub, Bieberehren, Höchberg, Holzkirchen,
Prosselsheim. Folgende Gemeinden … wurden hinzugefügt: … Neustadt an der Aisch
— … Sulzthal — … Röllbach». Bétard's snapshot (Nov 2021) still draws the fifteen
(≈ 431 km²) and touches the three added ones only at their edges (Neustadt a. d.
Aisch 1.2 %, Sulzthal 1.4 %, Röllbach 2.6 %).

### Landwein Main — drawn as Franken, listed as the old Franken

`DE_PGI_MEMBER_PDOS` drew Landwein Main as Franken's polygon. Its own single
document (C/2026/4338) and BLE § 4 list 142 Gemeinden: Franken's 127 and exactly
the fifteen Franken's amendment removed. So Bétard's pre-2025 Franken was, in
effect, Landwein Main's area — and redrawing Franken alone would have taken
fifteen Gemeinden off Landwein Main.

### Changed

- `scripts/_lib/de/einziges_dokument.py`: the 2024/1143 heading «Kurzbeschreibung
  der Abgrenzung des geografischen Gebiets» routes to `geo_area`. Thirteen records
  had no area section: Franken, Mosel, Pfalz, Nahe, Rheinhessen, Mittelrhein,
  Landwein der Mosel / der Ruwer / der Saar, Landwein Main, Nahegauer, Pfälzer
  and Rheinburgen-Landwein. Full DE stage 02 against a snapshot: those 13
  records, `section_roles.geo_area` and `geo_area_brief` only.
- `scripts/_lib/de/gemeinde_list.py` (new): reads the Bavarian layout
  ("Regierungsbezirk X: / Kreisfreie Städte: … / Landkreis Y: a, b, c") and binds
  each name to one GISCO commune inside its Regierungsbezirk (the AGS digit) and,
  for a Landkreis, inside the Kreis most of the group's names fall in; a name
  matching nothing there, or several communes, is reported and not drawn.
  Bavarian abbreviations are folded ("Sand a.Main", "Königsberg i.Bay., St",
  "Alzenau i. UFr."). Franken: 127 of 127 by exact name; Landwein Main 142 of 142.
- `scripts/de/02f_extract_produktspezifikation.py`: a § 4 in that layout rides
  the sidecar as `area_text` (Franken, Landwein Main), as numbered Gemarkungen
  already did (Baden, Württemberg).
- `scripts/_lib/de/geometry.py`: a record with such a list (EU area section
  first, else the sidecar) is drawn as the union of its Gemeinden
  (`gisco-commune-union`, ≥ 95 % bound), ahead of Bétard and the member unions;
  Franken's drawn polygon replaces its Bétard one in the index, so Bürgstadter
  Berg and Würzburger Stein-Berg inherit it. Stage 04 discloses a listed
  Gemeinde GISCO lacks on the shared unit line (`geom_units_unmatched`).
- `tests/test_de_gemeinde_list.py` (new): the layout, the name key, the scoping,
  and against the corpus that Franken's list is the 2025 one and Landwein Main's
  is Franken's plus the fifteen. `tests/test_de_gemarkung.py`: the sidecar rule
  widened to the four records.

| | before | after |
|---|---|---|
| Franken | Bétard, 3,925 km² | its 127 Gemeinden, 3,617 km² |
| Landwein Main | Franken's polygon | its own 142 Gemeinden, 4,016 km² |
| Bürgstadter Berg, Würzburger Stein-Berg | Franken (Bétard) | Franken (2025 list) |

**Build of 2026-11-24** (full stage 04, then `diff_records.py` against the
morning's snapshot): 5 records changed, `area` / `geom_source` / `communes` only —
the three above, Regensburger Landwein (×0.922, it unions "Franken") and no other.
`audit_geometry_outliers.py`: no stale override, nothing unreviewed.
`audit_geometry_overlaps.py --strict`: 0 suspicious slivers. Bétard-delta: Saale-Unstrut
is the one German record still FLAGGED.

### The card validator on the two redrawn cards

`audit_cards_llm.py --only franken --only landwein-main` (Opus 5.5, ≈ $0.53): the
area passes ("Name, scheme, area (127 communes) … match the documents"). It found
what the flag had not asked about:

- **Blauer Muskateller merged into Roter Muskateller** (both cards, misleading).
  `GRAPE_ALIAS` folded `blauer-muskateller` into `muscat-a-petits-grains-rouges`
  (#8248), so the six German lists that print both rows (Franken, Landwein Main,
  Pfalz, Pfälzer and Rheinischer Landwein, Rheinhessen) showed one pill, "Blauer
  Muskateller (Muscat A Petits Grains Rouges)". Live VIVC, 2026-11-24: the search
  "blauer muskateller" returns MUSCAT A PETITS GRAINS NOIRS **#8238** (NOIR) alone.
  **Fixed**: slug `muscat-a-petits-grains-noirs` (`blauer-muskateller`,
  `muskateller-blau`), colour noir, pinned on #8238; DE stage 02 / 02f re-run —
  exactly those six records and four sidecars gain it; a binding diff over all
  4,022 corpus grape names before and after fetching the passport: no other name
  moved. No Wikipedia article in any locale (the pill cites VIVC).
  `tests/test_grape_identity_guards.py`.
- **Roter Muskateller is two passports by country** (queued). VIVC flags ROTER
  MUSKATELLER as the official name *in Germany* on MUSCAT A PETITS GRAINS ROSES
  #8186 and *in Austria* on MUSCAT A PETITS GRAINS ROUGES #8248; the corpus binds
  it to #8248 everywhere (41 DE, 4 AT, 4 CH records). A per-country binding is
  needed — CURATOR_TODO.
- **Franken's fact 3 reverses where the vines stand** (misleading). The source
  bullet «Auf den mainfränkischen Platten, die … landwirtschaftlich genutzt
  werden, stehen im Gegensatz dazu auf den Böden … Reben» — the single document
  says the plateaux are farmland and the vines stand on the Buntsandstein,
  Muschelkalk and Keuper soils. Filed as a do-not-claim entry
  (`build_terroir_feedback.py --evidence tmp/terroir-facts-review/cards-2026-11-24`)
  and re-run (`rerun_terroir_facts.py --slug franken --run
  triage-franken-2026-11-24`).
- Defective, not misleading (queued or by design): Roter Gutedel bracketed
  "Chasselas Rose" where the regulator writes Chasselas Rouge; the breeder codes
  (Gf-Ga 52-42, VB Cal 1-22 / 1-28) dropped with no note on a German card (the
  Swiss cards say so since 2026-11-17); Federweißer has no style node (by design,
  2026-11-17).

### Closing build

The Franken re-run (`triage-franken-2026-11-24`, $0.25 at the batch rate; only
`franken`'s caches written): 14 facts, 13 supported and one narrowed by the gate;
the plateau claim is gone and the 2026-09-12 capture hint (the Klingen, the 60 %
land consolidation, drip irrigation) is now captured. Full stage-04 build, record
diff against the morning: 9 records — the five geometry changes, the black
Muskateller on six cards, Franken's facts (and its two Einzellagen, which inherit
them and now cite the Wikipedia article some bullets ground on). The card
validator on Franken again: **trust**, 0 misleading (was do-not-trust, 3); the
four remaining findings are omissions (Federweißer, the breeder codes, the
climate figures — "unter 550 mm", winter and late frosts — and the Erstes Gewächs
tier).

**Release gate** (`validate_release.py --quick`): the same four checks fail as on
2026-11-23 — grape-surfaces, ambiguous-synonyms (48, unchanged; #8238 now
appears among the claimants of «Moscatel-Galego», which still binds
`moscatel-galego-branco`), untranslated, Bétard-delta (121 → 115 FLAGGED). The
untranslated detector had counted Franken's new «la Bavière (Bayern)» /
«Baviera (Bayern)» (the exonym, glossed); its gloss rule now covers a place name
after its exonym (`exonyms.exonym_hits`, `tests/test_exonyms.py`) — those two
rows and no other dropped; 120 pairs, as before.

### Queued — a decision for Boris: Regensburger Landwein

Drawn as Franken (`DE_PGI_MEMBER_PDOS`, "Regensburger Landwein — Franken /
Bayern"), about 150 km from where it is. Every published version says the same:
the BLE Produktspezifikation § 3, the register's 2011 cahier (`ggA Regensburger
Landwein_111214.pdf`) and the technical file (Ares(2011)1395417) — «die … Flächen
der folgenden Gemeinden, wenn ihre Eignung von der zuständigen Behörde
festgestellt wird» followed by **no list**, then «Das Landweingebiet Regensburg
umfasst die Südhänge des Bayerischen Waldes entlang der Donau zwischen Naab und
Großer Laaber»; the technical file's NUTS row is DE2 Bayern, and it has no map.
The Bavarian ordinance names no Gemeinde either: BayWeinRAV § 1 (1) «Das Gebiet
von geschützten geografischen Herkunftsangaben ist über die Produktspezifikation
abzugrenzen», the plots being those of the Weinbaukartei (not published as
geodata). de.wikipedia's Baierwein article (rev. 265535454) places today's few
hectares at Regensburg-Winzer, Tegernheim, Donaustauf, Bach an der Donau, Wiesent
(Kruckenberg) and Wörth an der Donau (Tiefenthal).

**Second pass, the same day (Boris: is there really no list — elsewhere in the
document, elsewhere online?). There is none, and there never was: the sentence
is the legal delimitation, not what is left of a lost list.**

- *Erste Verordnung zur Durchführung des Weingesetzes* of 21 March 1983 (GVBl
  1983 Nr. 6, S. 116 — the year the name was created), § 2: the Untergebiet Main
  is the Franken areas of § 1, Lindau «den Landkreis Lindau (Bodensee)», and
  «(3) Das Untergebiet Donau umfaßt die Südhänge des Bayerischen Waldes entlang
  der Donau zwischen Naab und Großer Laaber.»; § 3 «Die Landweingebiete
  entsprechen den Untergebieten nach § 2.»
- BayWeinRAV of 31 August 1995 (GVBl 1995 Nr. 21, S. 667–677), § 2 (1): the same
  sentence, while (2) Lindau and (3) Main «umfaßt die in Anlage 1 Nr. … genannten
  Gemeinden»; Anlage 1 lists Oberfranken, Mittelfranken, Unterfranken and the
  three Lindau communes, nothing in the Oberpfalz or Niederbayern. Both gazettes
  read in the scans of verkuendung-bayern.de
  (`/files/gvbl/<year>/<nn>/gvbl-<year>-<nn>.pdf`); its other annexes are
  varieties, alcohol levels, the sugar ratio (which names «Untergebiete Main und
  Donau» for the ratio only), Lage names and the Herbstbuch.
- The last version before the repeal («Text gilt ab: 01.01.2016», last amended
  29 June 2015), in the Wayback Machine's captures of gesetze-bayern.de (the site
  serves only the 2020 ordinance now; the captures sit under session-token URLs,
  `gesetze-bayern.de/(X(1)S(…))/Content/Document/BayWeinRAV-…`): the contents
  page of 8 August 2020, five days before the repeal, still has § 1 Bestimmte
  Anbaugebiete, § 2 Untergebiete, § 3 Landweingebiete and seven annexes, none
  attached to § 2 or § 3; Anlage 1 (zu § 1), captured 22 July 2019 and read in
  full, is Franken and the three Lindau communes. The page of § 2 itself was
  never captured; a search engine's index of it quotes the same sentence.
- The specification's «der folgenden Gemeinden, wenn ihre Eignung … festgestellt
  wird» is the frame of the ordinance's § 1 and of the sister specification
  (Bayerischer Bodensee-Landwein § 3: «… der folgenden Gemeinden und Gemarkungen,
  wenn ihre Eignung … festgestellt wird: Die Gemarkungen Hoyren und Aeschach der
  Großen Kreisstadt Lindau, die Gemeinden Nonnenhorn und Wasserburg.»);
  Regensburg's fills the frame with the ordinance's sentence.
- Nothing newer, nothing elsewhere: BLE's listing carries the one PDF, never
  amended (sha256 equal to the cached file, Last-Modified 19 November 2024; read
  in a browser — BLE answers 403 to scripts; Landwein Main's, marked «geändert
  am 07.08.2026», is also the cached file); the register's detail record holds
  the cahier and the technical file only; the PDF's 14 pages, each looked at, hold
  no annex and no map (its one image is the coat of arms on the title page);
  LWG's statistics give the
  Landweingebiet as one row (5 ha in 2026), no commune; StMELF's Genusserbe page
  repeats the specification; the federal WeinV § 2 names the area only.

**What the specification does name — in § 7 (the link), not § 3.** The first
pass credited the places to Wikipedia; five of its six are the regulator's own:
«Der Regensburger Landwein wächst … im Raum der Stadt und des Landkreises
Regensburg»; a third of the vineyards «zum Großteil in der Stadt Regensburg,
Ortsteil Winzer»; two thirds in the «Weinbaugemeinden Tegernheim, Bach a.d.
Donau, Kruckenberg und Stadt Wörth a.d. Donau» (Kruckenberg is a part of
Wiesent). The Baierwein article adds Donaustauf alone, which lies between
Tegernheim and Bach.

On the ground (de.wikipedia for the two mouths, QA only; GISCO LAU 2024 against a
rough river line): the Naab joins at Mariaort, the Große Laber at
Straubing-Kagers (at Obermotzing, Aholfing, before the Straubing barrage). The
north-bank communes between them are Pettendorf (at the Naab mouth), Regensburg,
Tegernheim, Donaustauf, Bach a.d.Donau, Wiesent and Wörth a.d.Donau — city and
Landkreis Regensburg — and Kirchroth (Landkreis Straubing-Bogen). Options:

1. **§ 3 as written, inside § 7's «Stadt und Landkreis Regensburg»: the
   north-bank communes from the Naab to Wörth** — Regensburg, Tegernheim,
   Donaustauf, Bach a.d. Donau, Wiesent, Wörth a.d. Donau: every commune § 7.1
   names and Donaustauf between them. Drawn whole and disclosed on the card as a
   reading (the drinks-pin pattern). Two edge communes to settle when drawing:
   Pettendorf (Naab end, inside the Landkreis) and Kirchroth (Laaber end,
   outside it — § 3 alone reaches it, § 7 does not).
2. **The five communes § 7.1 names as planted** (Regensburg, Tegernheim, Bach,
   Wiesent, Wörth) — the regulator's words too, but a description of where the
   vines stood in 2011, not the delimitation, and it leaves a hole at Donaustauf.
3. **No polygon** — honest about the text, but stage 04 skips a record without
   a polygon, so it would leave the map *and* the sidebar.

**Decided the same day: option 1, the six.** `DE_LANDWEIN_AREA["PGI-DE-A1296"]`
(scripts/_lib/de/geometry.py) lists Regensburg, Tegernheim, Donaustauf, Bach
a.d.Donau, Wiesent and Wörth a.d.Donau with a `reading` block — the four
sentences read (`evidence`) and one sentence per UI language (`disclose`) — and
the record left `DE_PGI_MEMBER_PDOS`; Pettendorf and Kirchroth are left out. The
card's area line had no wording for this: `geom_src_admin_union` says "the
administrative units named in the document", which these are not. A record
whose units are a reading takes the new `geom_src_admin_reading` — "Approximate
area — our reading of the description the document gives, drawn as whole
communes (Eurostat GISCO boundaries)" — then the six names and the sentence
(stage 04 → `_DRINKS_GEOM_BY_SLUG` with `reading: true`; `_approx_line` /
`geomSourceLine`; four catalogs). Build of 18:19 (full stage 04,
`diff_records.py` against the snapshot before it): `regensburger-landwein`
`region-pdo-union` → `gisco-commune-union`, area ×0.053 (3,617 → 195 km², one
polygon, bbox 12.03–12.49° E), "6 commune(s)", region Bayern, no region alias
left; no other record's geometry, region or sources moved. The same build
carries 32 German rosters' Roter Muskateller on the pink passport
(`scripts/_lib/de/grape_pins.py`, the other change in the tree).
`audit_geometry_outliers.py`: 0 stale, 0 unreviewed; `audit_geometry_overlaps.py
--strict`: 0 suspicious. `tests/test_de_parser.py`
(`test_regensburger_landwein_is_a_disclosed_reading_of_its_own_text`: the
evidence verbatim in the cached PDF, § 3 still listing nothing, the six in the
GISCO layer), `tests/test_content_block.py`. Not deployed.

### Queued (CURATOR_TODO, Germany) — closed the same evening, below

- Rheingau: Frankfurt am Main (the Lohrberger Hang) is named and not drawn.
- Mittelrhein: the NRW Gemarkungen drawn as three whole cities.
- Saale-Unstrut: Bétard-delta FLAGGED; its list is in Gemarkungen, not checked.
- The Rhineland-Palatinate texts print each Gemarkung's register number, the
  Württemberg shape: an RLP Gemarkung layer would draw them at that precision.
- `audit_geometry_vs_text.py` needs a German reader.

## The five queued points, addressed the same evening

Boris pasted the queue back ("address these open points"): Roter Muskateller,
Rheingau, Mittelrhein, Saale-Unstrut, the German reader of the
polygon-versus-text audit. One cause behind the three geometry rows: Bétard
draws municipalities, the texts name other units, and nothing had read a
German polygon against its own text.

### Roter Muskateller — a German reader pin

Live VIVC, 2026-11-24 (both passports fetched and parsed with
`_lib/vivc.parse_passport`): ROTER MUSKATELLER is flagged *official name in
GERMANY* on MUSCAT A PETITS GRAINS ROSES #8186 (berry ROSE) and *official name
in AUSTRIA* on MUSCAT A PETITS GRAINS ROUGES #8248 (ROUGE). German lists print
it among the white-wine varieties (Pfalz § 8: «… Roter Müller Thurgau, Roter
Muskateller, Roter Riesling, Roter Traminer …»).

- **Germany**: `scripts/_lib/de/grape_pins.py` — `german_match` wraps the
  matcher in `de/02` and `de/02f` (a country's reading is a reader's pin, the
  Swiss «Cornalin» pattern; the lexicon alias stays the red one). DE stage 02
  and 02f against a snapshot: 15 EU records and 26 sidecars, each that one
  binding (`muscat-a-petits-grains-rouges` rouge → `-roses` rose), nothing
  else.
- **Austria**: no record binds a red Muscat. The four documents that print the
  name (Salzburg, Ruster Ausbruch, Oberösterreich, Wiener Gemischter Satz) list
  «Muskateller – Roter Muskateller» — one variety under its first name, the
  synonym after the dash — and bind `muscat-a-petits-grains`. The "4 AT
  records" of the first note were that row.
- **Switzerland**: Glarus, Schwyz, Zürich and Zürichsee print «Roter
  Muskateller» and keep #8248. The federal list (Sortenverordnung SR
  916.151.6, Anhang 8, Stand 1 December 2025, read in the fedlex PDF, sha256
  eb01ffaf…a07d304) has four small-berried or coloured Muscats — «Muscat à
  petits grains blancs B», «Muscat bleu N», «Muscat rouge à petits grains N —
  Muscat rouge», «Muscat vert B» — and no rosé one; VIVC lists MUSCAT ROUGE A
  PETITS GRAINS on #8248.

`tests/test_de_grape_pins.py`. (The other session's Regensburger build of
18:19 already carries the change.)

### The Länder publish their Gemarkungen

Probed 2026-11-24: Nordrhein-Westfalen, Brandenburg, Sachsen-Anhalt, Thüringen
and Hessen serve the AdV "ALKIS vereinfacht" layer `ave:KatasterBezirk` (WFS;
`art` = Gemarkung or Flur; Thüringen in schema 1.0, without the Gemeinde key),
Rheinland-Pfalz its own collection `vermkv:gemarkungen_rlp` (OGC API Features,
`gmkgnr` = 07 + the number the specifications print). Licences as each
publisher states them: NRW dl-de/zero-2-0; Brandenburg dl-de/by-2-0
("GeoBasis-DE/LGB"); Sachsen-Anhalt dl-de/by-2-0 ("© GeoBasis-DE / LVermGeo
ST", Nutzungsbedingungen of 1 March 2024, Nr. 2); Thüringen CC BY 4.0 ("©
GDI-Th", the service's own Fees line); Rheinland-Pfalz dl-de/by-2-0 ("©
GeoBasis-DE / LVermGeoRP"). `scripts/_lib/de/katasterbezirk.py`, stage 00 →
`raw/de/katasterbezirke/{nw,bb,st,th,rp}.gpkg` (162 / 193 / 658 / 2,704 /
3,111 Gemarkungen; NRW, Brandenburg and Sachsen-Anhalt for the Kreise the
texts name).

### The reader — `scripts/_lib/de/area_units.py`

Four layouts beside the two that had readers: the Rhineland's numbered
Gemarkungen, a town with its Gemarkungen, Gemarkungen by Kreis, Gemeinden in
prose. A unit is bound to its Land's layer or to a GISCO commune, never by
likeness across the Land: a number when the printed name agrees with the
register's and with the Kreis the text glosses it with, a name when it names
one unit inside the Land and the Kreis or Gemeinde the text gives. Drawn at
≥ 95 % bound; a PDO's polygon replaces its Bétard one in the index.

### Rheingau — Frankfurt am Main

BLE § 3: «… die Rebflächen der Städte und Gemeinden Eltville am Rhein,
Felsberg, Flörsheim am Main, Frankfurt am Main, Geisenheim, Hochheim am Main,
Kiedrich, Lorch, Oestrich-Winkel, Rüdesheim am Rhein, Walluf und der
Landeshauptstadt Wiesbaden des Bundeslandes Hessen.» Twelve, the city among
them and no Gemarkung of it — the text names Frankfurt as it names Wiesbaden,
so it is drawn whole like the other eleven (the queued "wait for a Gemarkung
source" had no text to stand on). 601 → 850 km², `gisco-commune-union`,
"12 commune(s)". Rheingauer Landwein's own § 3 is the same twelve.

### Mittelrhein — 66 Gemarkungen

The single document (C/2026/738): 61 numbered Gemarkungen under «Land
Rheinland-Pfalz», then «Land Nordrhein-Westfalen … der Stadt Königswinter mit
den Gemarkungen Oberdollendorf, Niederdollendorf und Königswinter, der Stadt
Bad Honnef mit der Gemarkung Honnef (Rhöndorf) und der Stadt Bonn mit der
Gemarkung Kessenich». All 66 bind; 949 → 601 km².

One number contradicts its own gloss: «Breitscheid (Landkreis Mainz-Bingen)
(0261)». Rheinland-Pfalz's register has Gemarkung 0261 = Breitscheid, Gemeinde
Breitscheid, **Landkreis Neuwied** (07138006), and 3501 = Breitscheid,
Landkreis Mainz-Bingen (07339007), beside Steeg 3502 and Bacharach 3503, which
the same list prints. The Kreis the text itself gives decides; the reader
refuses a number whose row lies in another Kreis than the gloss, and the unit
is pinned to 3501 with that evidence (`scripts/_lib/de/area_unit_pins.json`).
Bétard had drawn the Mainz-Bingen commune. It is the only such contradiction
among the corpus's numbered units with a Kreis gloss.

### Saale-Unstrut — checked, and redrawn

The check the row asked for (Bétard against the Gemarkungen the text names,
through the three Länder's layers): Bétard draws 48 municipalities whole,
3,274 km²; the text's units are 1,330 km². No municipality Bétard draws is
without a named Gemarkung, but six that hold one are not drawn whole — Bad
Sulza, Löberschütz, Schmiedehausen, Seitenroda, Uhlstädt-Kirchhasel,
Wallhausen (39 km² of named Gemarkungen outside Bétard). So the Bétard-delta
flag was a real difference, and the municipal resolution overstated the area
two and a half times.

Drawn: 99 Gemarkungen (Sachsen-Anhalt 61, Thüringen 34, Brandenburg 4 — Werder
(Havel), Phöben, Plessow, Neu Töplitz), Weimar's Gemarkungen Schöndorf and
Tiefurt for its two «Ortsteile», and Jena and Erfurt whole («die kreisfreien
Städte Jena und Erfurt»). Three names the registers carry otherwise are
pinned with their evidence: Stedten (the text files it under the Saalekreis;
the one Gemarkung of the name is in Seegebiet Mansfelder Land, Mansfeld-
Südharz, beside Seeburg and Lüttchendorf, which the text lists there), and
the former Gemeinden Kromsdorf (Großkromsdorf + Kleinkromsdorf) and
Dorndorf-Steudnitz (Dorndorf + Steudnitz). «Tümplingund Wichmar» in the
document is two names. **Not drawn, named on the card: «Graitschen»** — the
Saale-Holzland-Kreis has Graitschen auf der Höhe and Graitschen bei Bürgel,
each next to other names of the list (CURATOR_TODO).

### Isolated or broader — the siblings the same reader binds

**Failure mode: a German polygon at another resolution, or of other units,
than its own text.** The sweep is the reader itself, run over every German
parent record:

| record | own text | was | now |
|---|---|---|---|
| Mosel | 197 numbered Gemarkungen + 4 of Perl (Saarland) | Bétard, 1,698 km² | 1,549 km²; Perl whole for its four, disclosed |
| Nahe | 101 numbered Gemarkungen | 800 km² | 697 km² |
| Pfalz | 187 numbered Gemarkungen | 1,644 km² | 1,480 km² |
| Rheinhessen | 133 Gemeinden, 16 with their districts in a bracket | 1,326 km² | 117 Gemeinden + 58 Gemarkungen, 1,273 km² (Bingen without Bingerbrück, which the Nahe lists) |
| Ahr, Hessische Bergstraße | 7 / 9 Gemeinden | the same communes | same shape, drawn from the text |
| Landwein der Saar | 19 Gemarkungen | all of the Mosel | 147 km² |
| Landwein der Ruwer | 11 Gemarkungen | all of the Mosel | 50 km² |
| Landwein der Mosel | 167 Gemarkungen + Perl | Mosel | 1,352 km² |
| Rheinischer Landwein | Rheinhessen's 133 Gemeinden | Rheinhessen + Nahe + Pfalz + Mittelrhein | 1,324 km² |
| Rheinburgen-Landwein | Mittelrhein's 66 units | Mittelrhein + Ahr | 601 km² |
| Mitteldeutscher Landwein | Saale-Unstrut's Gemarkungen of Sachsen-Anhalt and Thüringen | Saale-Unstrut + Sachsen | 1,216 km² |
| Landwein Rhein | 573 Gemeinden of Rheinland-Pfalz and Hessen, 5 Gemarkungen of NRW | seven Anbaugebiete, without the Hessische Bergstraße | its own list, 7,251 km²; eight names not drawn |
| Saarländischer Landwein | 24 Gemeinden by Landkreis | no polygon: off the map and the sidebar | 1,441 km² |
| Ahrtaler, Nahegauer, Pfälzer, Rheingauer, Starkenburger Landwein | their Anbaugebiet's list | the Anbaugebiet | the same ground, from their own text |

`DE_PGI_MEMBER_PDOS` was corrected to what each list covers (the rows remain
the fallback and the source of the region aliases); Landwein der Saar's region
was "Saarland" — its 19 Gemarkungen are all in the Landkreis Trier-Saarburg —
now Rheinland-Pfalz. Not reached by any reader: Sachsen (boundary prose),
Sächsischer Landwein (postcodes), Mecklenburger and Schleswig-Holsteinischer
Landwein, Großräschener See; the five Baden-Württemberg Landweine keep their
member unions (their lists carry no numbers).

### The German reader of the polygon-versus-text audit

`audit_geometry_vs_text.py --country de` now reads the same three readers
stage 04 draws from (`_de_named`): EU area section first, else the sidecar's
`area_text` (stage 02f keeps the "Abgrenzung des Gebiet(e)s" section wherever
a reader reads it — 22 sidecars). A commune named whole is named; one reached
only through a Gemarkung or an Ortsteil is named in part. Gemarkung unions are
judged as unions (a whole commune the text does not name is a finding; a
commune drawn in part is the rule).

### Builds and checks

Three full stage-04 builds (the second added the bracketed districts of a
Gemeinde, the third Landwein der Saar's region), `diff_records.py` against the
snapshot taken before the first (`tmp/validation/records-before-de-units.json`):
**25 records changed, 1 added (Saarländischer Landwein), all German** —
`geom_source` 21, `area` 21, the commune count 6, `region` 1 (Landwein der Saar:
Saarland → Rheinland-Pfalz; its trade-body link moved with it, Moselwein e.V. →
DWI, as its siblings Landwein der Mosel and der Ruwer carry). The three Uhlen
and Monzinger Niederberg follow their parents' new polygons. No roster, style,
fact or source of any other record moved.

- `audit_geometry_outliers.py --strict`: 0 unreviewed, 0 stale. Three whitelist
  reasons rewritten to the new drawing: Saale-Unstrut (Werder is its four
  Gemarkungen now, ≈ 50 km²; and «Quedlinburg und Westerhausen im Landkreis
  Harz», 96 km², a second detached part the municipal polygon had hidden),
  Mitteldeutscher Landwein (the Harz part; no Werder, no Saxony), Landwein Rhein
  (Felsberg, from its own § 3).
- `audit_geometry_overlaps.py --strict`: one new pair, **Mittelrhein ∩ Mosel,
  25.4 km²** — the Gemarkung Koblenz (1401), which both single documents list
  («Koblenz (Ehrenbreitstein (1416), Koblenz (1401), Niederberg (1413))» /
  «Koblenz (Güls (1405), Koblenz (1401), Lay (1403), Metternich (1407),
  Moselweiß (1402))»). The regulator's own double listing: whitelisted with
  both quotes, as is the same pair between the two Landweine. 0 suspicious.
- `audit_betard_delta.py`: FLAGGED 115 → 114 (Saale-Unstrut is no longer a
  Bétard polygon). The five German entries reviewed this morning no longer
  describe a drawn polygon; kept, they hold for the fallback.
- `audit_geometry_vs_text.py --country de --strict`: 79 records. Of the 43
  wines **26 are read and OK** (none was read before): missing 0 everywhere,
  one whole commune beyond the text on one record (Württemberg's «Bodholz»,
  drawn as Bodolz). 12 NO-UNITS — the six Einzellagen (parcel descriptions),
  the five Baden-Württemberg Landweine (names without numbers), Sächsischer
  Landwein (postcodes); 5 NO-TEXT — Sachsen (prose) and the four records drawn
  from the curated `DE_LANDWEIN_AREA` tables. The 36 German drinks are
  NO-UNITS, as before.
- The live panel in a headless browser (en / nl / fr / es, five cards): the
  line, the credits and the unit lines render, no page error.
- `validate_release.py --quick`: the same four checks fail as this morning
  (grape-surfaces, ambiguous-synonyms 48, untranslated 120 pairs, Bétard-delta
  114), every other check passes; `pytest`: 2,614 passed.

Not run: the LLM card validator (it costs money; the change is geometry and
one grape binding, and the rebound pill was read in the panel payload: Pfalz
shows «Roter Muskateller» on `muscat-a-petits-grains-roses` beside «Blauer
Muskateller»). Not deployed.

## Credits

None offered.
