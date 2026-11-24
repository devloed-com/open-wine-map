# Visitor feedback triage — 2026-11-17

Queue: `scripts/feedback_report.py --range 30d`, rows since the 2026-11-08
triage (`--range 2026-11-08,2026-11-17`): 4 flags on 3 cards, 2 retracted, no
note, no name offered for credit, one e-mail-link click. The live site ran
the 2026-11-14 build; the three flagged cards' panel payloads were
byte-identical live and local, so the local build is the surface checked.

| flagged | aspect | locale · view | verdict |
|---|---|---|---|
| Schwyz, 2026-11-11 16:00, retracted the same hour | grapes | en · zone z8.4 | defect: the card showed no grape; a public cantonal ruling lists them |
| Württemberg, 2026-11-16 10:00 | boundary | en · zone z7 | defect: drawn as whole Landkreise, Baden's ground included |
| Jura (CH), 2026-11-16 17:00 | grapes (kept), boundary (retracted) | nl · zone z8.3 | grapes: defect — the roster is in the Département's directives, which were never read; boundary: no defect (the canton, as Art. 11 delimits) |

A retracted flag is not proof of no defect: Schwyz's was real. And a card
that matches the document in the build is not proof either: Jura's first
verdict here was "no defect, the ordinance names no variety" — true of the
ordinance, wrong for the regulator (see below).

## Württemberg — boundary (de DOP, Bétard polygon)

**What was drawn.** `figshare-pdo`: 10,757 km² in two parts. Reverse-geocoded
on GISCO, the polygon is 13 whole Landkreise plus a few communes — Stuttgart,
Esslingen, Ludwigsburg, Rems-Murr, Heilbronn (Stadt and Land), Hohenlohe,
Main-Tauber, **Neckar-Odenwald (27 communes), Rhein-Neckar (54)**, Enzkreis,
Reutlingen, Tübingen, Bodenseekreis, four communes of Lindau. The single
document (OJ C/2025/5177, section 6) names 275 Gemarkungen: one of them in the
Neckar-Odenwald-Kreis (Neckarzimmern), none in the Rhein-Neckar-Kreis — the
country around Heidelberg is Baden's Badische Bergstraße and Kraichgau — and
it names Leonberg (Kreis Böblingen), Ravensburg and Taldorf (Kreis
Ravensburg) and Oberderdingen (Landkreis Karlsruhe), which the polygon does
not draw. At z7 a visitor sees a Württemberg that reaches the Rhine plain.

`audit_geometry_vs_text.py` has no German reader (NO-UNITS), so the comparison
was made by hand. The coarseness was known as a caveat (the outlier whitelist's
Bodensee entries; the region sweep's "Baden ∩ Württemberg 4,157 km²" row) and
queued under "commune-precise geometry, country by country".

**Failure mode:** *Bétard drew the two Baden-Württemberg regions as whole
Landkreise.* Sweep over the 13 Anbaugebiete (polygon against GISCO communes):

| region | km² | communes covered whole | of which in whole Kreise |
|---|---:|---:|---:|
| Baden | 13,231 | 398 | 374 (15 Kreise) |
| Württemberg | 10,757 | 373 | 326 (13 Kreise) |
| the other eleven | 164 – 3,925 | 7 – 141 | 0 – 4 |

Two records, and through them the seven Landwein PGIs drawn as unions of the
two (Badischer Landwein, Landwein Oberrhein, Bayerischer Bodensee-Landwein,
Schwäbischer Landwein, Landwein Neckar, Landwein Rhein-Neckar, Landwein Main).

**Fix.** Both delimitations are written in Gemarkungen with their
land-register number — "Abstatt (835), Adolzfurt (371) …": Württemberg's EU
single document (275) and Baden's BLE Produktspezifikation § 4 (353, per
Bereich; Baden is a stub with no EU document). The state survey publishes that
unit: LGL Baden-Württemberg, ALKIS layer `nora:v_al_gemarkung` (WFS, 3,380
Gemarkungen, **dl-de/by-2-0**), whose `gemarkung_id` is the printed number
(Oberstenfeld 920, Gronau 921).

- `scripts/_lib/de/gemarkung.py`: `parse_area` (every "Gemeinden (Gemarkungen)
  und deren Ortsteile:" list, the Bereich a block is headed by, the Bavarian
  units Württemberg names without a number), `fetch_layer` (stage 00 pages the
  WFS into `raw/de/lgl/gemarkungen.gpkg`), `GemarkungLayer`, `load_areas` (the
  record's own EU document when it lists numbered units, else the sidecar's
  § 4, which stage 02f now keeps as `area_text` on those two sidecars).
- `DEPolygonIndex`: new step `lgl-gemarkung-union`. A unit is drawn when the
  layer carries its number **and the printed name agrees with the layer's
  Gemarkung or Gemeinde name for it** — the guard against a mistyped number
  (0 disagreements in 628 units). A record is redrawn only when 95 % of its
  units are: Saxony's Landwein prints its own register's numbers the same way
  and none agrees, so it is left alone. The union replaces the Bétard polygon
  inside the index, so the member-union Landweine follow.
- One number is not in the register: «Stetten (761)», printed by both the
  single document and the BLE specification. Stetten am Heuchelberg (Gemeinde
  Schwaigern) is Gemarkung 768 — the list names its neighbours Schwaigern
  (765) and Niederhofen (767). Pinned with that evidence in
  `scripts/_lib/de/gemarkung_pins.json`; the card names the pin.
- Bavarian part: the Gemeinden Nonnenhorn, Wasserburg and Bodolz (the document
  writes "Bodholz") from GISCO; Lindau is drawn whole for its Gemarkungen
  Hoyren and Aeschach and listed as partial.
- Card (both renderers, four locales): "Approximate area — the union of the
  275 Gemarkungen (cadastral districts) the document lists by number;
  boundaries merged and generalised from LGL-BW (2026) … · dl-de/by-2-0", the
  Bavarian Gemeinden, the pin, the partial unit; a Landwein union says its
  members are drawn from their Gemarkungen and names Bétard only where other
  members still are. The fold still says "approximate area": the delimitation
  itself is the vineyard parcels inside those Gemarkungen.

| | before (Bétard) | after (Gemarkungen) |
|---|---:|---:|
| Württemberg | 10,757 km², 2 parts | 2,758 km², 21 parts — 275 / 275 units |
| Baden | 13,231 km², 4 parts | 3,607 km², 45 parts — 353 / 353 units |
| drawn for both | 4,157 km² | none (no Gemarkung is in both lists) |

## Three Landwein tables the old polygons had hidden

Drawn from their Gemarkungen, Baden's Bereiche Tauberfranken and Bodensee and
Württemberg's lake Gemarkungen are separate lobes — Bétard's whole Landkreise
had joined them — and the detached-part audit listed six records. Before
whitelisting any, each Landwein's own BLE Produktspezifikation was read:

| Landwein | drawn as | its own area section | now |
|---|---|---|---|
| Badischer Landwein, Landwein Oberrhein | Baden | § 4: the same list of Baden's Gemeinden and Gemarkungen (Achern … Zunzingen), Tauberfranken and the Bodensee included | unchanged; lobes whitelisted with the evidence |
| Landwein Neckar, Schwäbischer Landwein | Württemberg | § 4: Württemberg's list, Kreßbronn, Ravensburg and Taldorf included | unchanged; lobes whitelisted |
| Landwein Rhein-Neckar | Rheinhessen + Pfalz + Württemberg + Baden | § 4: Baden's and Württemberg's places in one run (676 names), none of Rheinhessen or the Pfalz | Württemberg + Baden; region Baden-Württemberg (was Rheinland-Pfalz) |
| Landwein Main | Franken + Baden + Württemberg | § 4: Bavarian towns and Gemeinden only, by Regierungsbezirk and Landkreis | Franken |
| Bayerischer Bodensee-Landwein | Baden (13,231 km²) | § 3: "Die Gemarkungen Hoyren und Aeschach der Großen Kreisstadt Lindau, die Gemeinden Nonnenhorn und Wasserburg" | those three communes (Lindau whole, listed as partial) |

The last three are table errors of long standing; the oversized polygons had
made them invisible. A member table is a claim about a specification, and
three of seven did not match theirs — the other countries' member tables are
queued for the same reading.

## Württemberg — styles (found on the card, not flagged)

The live card listed White, Sparkling, Semi-sparkling and Liqueur wine for a
region planted mostly with red varieties. The single document numbers one
sub-section of its description per wine type and names the type in the
**title** — "4.2 Wein, rot", "4.3 Wein, rosé", "4.4 Weißherbst", "4.9
Prädikatswein, Beerenauslese und Trockenbeerenauslese", "4.19 Likörwein, rot"
— with no product line in the body; the German style reader read section
bodies only. Reader gap, isolated: no other German document uses that layout.
`wine_type_titles` (de/02) gives `parse_styles` the titles. Württemberg gains
Red, Rosé, Sélection de grains nobles and Late harvest.

The sweep for declared categories the styles lacked found two siblings of a
neighbouring gap: Franken's category list declares "5. Qualitätsschaumwein"
(no Sparkling on the card) and Saale-Unstrut's "8.4 Kategorie Perlwein" speaks
of "Qualitätsperlwein b. A." (no Semi-sparkling) — the markers `\bschaumwein\b`
and `\bperlwein\b` missed the compounds. Full DE run against a snapshot after
each change: three records, styles only.

Not added: "Wein, Schillerwein" and "Wein, Rotling" — wine types of their own
in German law, with no node in the style taxonomy (queued).

## Jura and Schwyz — grapes (ch AOC); five more cantons by the sweep

Seven Swiss cantonal cards showed no grape. Five were pinned in
`empty_grapes_overrides.json` as "the regulator names no variety" (two of
those with "defers to the federal OVin", a reason taken from the project
notes, not from a text).

**Failure mode:** *the ordinance names no variety and says who does; the act
it delegates to was never read.* In every case that act is public and sits
on the same law portal, usually one systematic number on:

| card | the ordinance says | the act that holds the roster | on the card now |
|---|---|---|---|
| Jura | RSJU 916.141 Art. 12: the OIV list for Switzerland and the varieties in the cadastre for five years; Art. 24: "Le Département édicte les directives nécessaires" | *Directives* of 11 April 2019, RSJU **916.141.1**, Art. 10: "Les cépages admis pour l'obtention de l'appellation d'origine contrôlée «AOC Jura» figurent à l'annexe 1" — Annexe 1, 19 white and 26 red entries | 29 varieties |
| Appenzell Innerrhoden | GS 916.610 Art. 9: "Die Standeskommission bezeichnet die für AOC-Wein zugelassenen Rebsorten" | Standeskommissionsbeschluss of 5 July 2022, GS **916.611**, Art. 3 + Anhang 1 (67 entries) | 63 |
| Appenzell Ausserrhoden | bGS 920.16 Art. 7: "Der Regierungsrat bezeichnet …" | Verordnung über zugelassene Rebsorten of 19 February 2013, bGS **920.161**, Art. 1 (61 entries) | 54 |
| Glarus | GS IX D/621/1 Art. 9: "Der Regierungsrat legt die zulässigen Rebsorten fest" | Verordnung über die kontrollierten Ursprungsbezeichnungen für Weine of 10 November 2020, GS **IX D/621/2**, Art. 2 + Anhang 2 (121 entries) | 92 |
| Schwyz | SRSZ 312.711 § 1 Abs. 2 Bst. i, § 7: the Amt für Landwirtschaft sets the AOC requirements | Allgemeinverfügung «AOC Schwyz» of 28 July 2025, Ziff. 2.4 + Anhang (132 entries, a scan) | 100 |
| Zürichsee | the same, § 7 Abs. 2 Bst. b | Allgemeinverfügung «AOC Zürichsee» of 28 July 2025, the same annex (already cited by the build for the area) | 100 |
| Zürich | no ordinance since 2018; ALN ruling of 26 June 2020, Ziff. IV: "gemäss Anhang 2" | "Anhang 2 — Verzeichnis der zugelassenen Rebsorten / Kanton Zürich (Sept. 2022)", published apart on strickhof.ch (130 entries) | 98 |

**How Jura was nearly missed.** The first pass read the Jura ordinance —
every article, footnotes included; the cached PDF is byte-identical to the
version in force, and none of its five versions since 2000 ever listed a
variety — concluded "text-silent", and added a cited card note quoting
Art. 12. Boris asked whether the grapes might sit "in an unexpected or wrong
place". They did: Art. 24 delegates to the Département, and its directives
carry the list. The note was withdrawn before any build shipped it. The
lesson is in the project guide: before a card is pinned roster-less, read
the delegating clause and look for the act it delegates to, starting with
the next number on the same portal. That check found the Appenzell and
Glarus acts within minutes.

**Mechanism.** `scripts/_lib/ch/roster_rulings.json` holds, per card, the
act, its URL and sha256, the delegating and the applying clause, and the
list as printed; `roster_rulings.py` reads it through the roster-table cell
rule (a bracketed gloss dropped, a breeder code skipped, an exact or
near-exact lexicon match only); stage 01 fetches the PDFs into
`raw/ch/rulings/`, stage 02 gives the record the roster and a second
règlement source. The lists keep the acts' print — Glarus's «Läon Millot»
and «Marächal Foch», Ausserrhoden's «Pinotblanc» and «Pinotgris» — and a
`read_as` map gives the reading, or the two names of an entry that states
two varieties («Elbling (rot und weiss)»). `tests/test_ch_roster_rulings.py` checks
every list against its cached PDF, entry by entry and both ways (tesseract
for the two scans, the text layer for the rest).

Not shown on the cards: breeder codes (by design) and some 25 named
varieties the grape lexicon lacks — Aurora, Chancellor, De Chaunac, Vidal
blanc, Millot-Foch, Réselle, the MRAC crossings — a lexicon pass, queued.
Jura's card shows 29 of its 45 entries for that reason (twelve are codes).
Each card now says so under its grape pills (see the validator section).
Zürichsee keeps the Schwyz annex (the ruling says the list covers both AOCs;
Weinverordnung Art. 21 Abs. 3 holds the two cantons to the same
requirements); Zürich's 2022 list is the older one, six entries apart.

**What remains roster-less, and why.**

| canton | what the text says | status |
|---|---|---|
| SH (§ 12), TG (§ 37), UR (Art. 10) | an office keeps the list (Landwirtschaftsamt; Fachstelle Rebbau SH-TG-ZH; Amt für Landwirtschaft) | no sibling act on the portal, nothing found by search — queued |
| NW (§ 5), ZG (§ 4), BE (Art. 6) | the federal variety list, by reference | decision: show a roster by reference or not |

**Uri's source was worse than a wrong pin:** the cached "règlement" was
LexFind's app shell — 2.6 KB of HTML saved as `reglement.pdf` since May — so
the card cited a document nobody had read. Uri now reads the canton's own
Rechtsbuch (a LexWork portal stage 01 already resolves), and stage 01
refuses a `.pdf` that is not one and refetches a cached one. The 25 other
cantons' files are what they claim to be.

Swiss re-extraction against a snapshot, after each step: eight records
changed — the seven rosters, and Uri's source and summary.

Areas: AOC Schwyz's ruling says "Das Produktionsgebiet umfasst den gesamten
Kanton Schwyz" and Jura's Art. 11 "le territoire cantonal" — the canton-wide
polygons drawn. Jura's retracted boundary flag found nothing.

## Card validator on the changed cards

`audit_cards_llm.py` on the nine cards this triage rebuilt (the seven Swiss
rosters, Baden, Württemberg; Opus, $1.32; report
`tmp/validation/cards-triage-2026-11-17.md`). All nine came back with at
least one finding rated misleading — 30 of 47 findings, every quote grounded.
Read one by one, they sort three ways.

**Right, and fixed in this session**

| finding | failure mode | isolated or broader | fix |
|---|---|---|---|
| 25 × `missing-grape` on the Swiss cards: Schwyz showed 99 varieties of a 132-entry list, Jura 29 of 45, without a word | *a partial roster that reads as a whole one* — breeder codes are skipped by design and some 25 names are lexicon gaps, but nothing on the card said so | the seven roster cards | one amber line under the grape pills, both renderers: "102 of the 132 entries of the regulator's list are shown, as 100 varieties; not shown: 9 breeder code(s), 21 variety name(s) our grape reference does not hold yet." (`roster_rulings.coverage` → `roster_coverage` → `grapes_roster_coverage`). The figures add up to the list; "as 100 varieties" says that several entries can be one pill |
| "The card cites only the BDW trade body" on every Swiss card | *a Sources row added to the browser card and never to the server-rendered one* — the validator, crawlers and no-JS visitors read the latter | broader: all 75 Swiss cards (ordinance, roster act, area rulings, OFAG register), the UK cards (6 wines, 16 drinks: specification and register rows) and the French records bound to the EU register's cahier | rows ported to `render_sources`; a test reads every `sources.<key>` of the JS function and fails on one the Python function lacks |
| Baden, Württemberg: "Sources … not the BLE Produktspezifikation" | the specification had no Sources row in either renderer; it was named only in the provenance line, which a card with facts does not print | every German card with a BLE sidecar (13 regions, 15 Landweine) | row "National product specification (BLE, PDF)" on both |
| Jura: "the only source listed is … Neuchâtel Vins et Terroir" | *a region key for a body that is one canton's* | Bern (+ Bielersee, Thunersee), Cheyres, Jura, Vully took Neuchâtel's office through "Trois-Lacs"; Bayerischer Bodensee-Landwein took Franken's through "Bayern" | the Neuchâtel body by slug, region key gone (the four carry none until theirs is found — queued); the Bodensee Landwein carries Württemberg's; "Baden-Württemberg" → DWI gives Landwein Rhein-Neckar back the row its region correction had cost it |
| Schwyz, Zürichsee, Glarus: "Elbling only as white; the annex authorises red and white" | «Elbling (rot und weiss)»: the cell rule drops a bracketed gloss | those three lists | `read_as` takes a list — the white Elbling and its red mutation; Schwyz and Zürichsee 100 varieties, Glarus 92 |

Found while counting coverage, not by the validator: «Millot-Foch» — the
crossing the German-Swiss lists print beside both parents — was read as Léon
Millot through the matcher's hyphen split. No wrong pill (Léon Millot is on
the same lists), but the entry counted as shown. A roster cell is one
variety; the split is refused there.

**Right, older than this session, queued** (CURATOR_TODO, each with its recipe;
the first three were closed later the same day — see "Open points closed the
same day")

- Baden's roster: «Chardonel» bound to Chardonnay by a fuzzy match (the pill
  reads "Chardonel (Chardonnay Blanc)" and the Chardonnay the specification
  lists beside it is swallowed), «Grünfränkisch» to Sylvaner the same way;
  Zähringer, Muskat Gutedel, Ruling and Kolor match nothing. Lexicon entries
  with live VIVC ids, then a German 02f run against a snapshot.
- Styles of the six regions with no EU single document (Ahr, Baden,
  Hessische Bergstraße, Rheingau, Sachsen, Saale-Unstrut): the BLE
  specification states categories and types (Baden § 2, § 3) and no reader
  reads them, so the card shows the berry-colour floor and says "the
  regulator's text names no colour" — a reader gap, and the line is untrue
  there.
- Styles of Schwyz and Zürichsee: the ruling's Ziff. 2.2 ("Schaum-, Perl- und
  Likörweine"), the Reserve rule and Ziff. 2.10 (Roséwein) name wine types;
  the other five acts name none (searched).
- Baden's and eight more regions' principal / accessory split is read from
  which varieties § 3.2 gives a must weight of their own. The validator
  calls it `wrong-role`; it is an interpretation the card does not disclose
  — a decision for Boris (disclose it, or show all as principal).
- Two terroir-fact findings (Württemberg's product facts are Wikipedia's
  only; a dropped hedge on Baden) — feedback entries and a scoped re-run.
- The BLE reader's red-variety block has no end on four sidecars (Baden's
  runs to the end of the document); nothing came in from the prose (checked).

**Not defects**

- Breeder codes (CAL 1-28, VB 91-26-26 …) are not pills — by design; the
  card now counts them.
- «Roter Müller-Thurgau» and «Roter Räuschling» "missing": the lexicon folds
  each red mutation into its white variety, so two entries are one pill.
  Queued for a live VIVC check (the one-passport-per-colour rule).
- Zürichsee "presented as a standalone AOC": it is a record of its own
  listed under Schwyz and Zürich, the decision of 2026-10-25.
- Cornalin / Landroter waits for the Cornalin identity pass.

**Re-grade after the fixes** (five cards, $0.60). Schwyz, Jura and Glarus:
"trust", no misleading finding (from "do-not-trust" / "caution"). Appenzell
Innerrhoden: "caution", one finding left. Its first re-grade read the line's
first wording — "63 varieties shown for the 67 entries …; not shown: 1
breeder code, 1 name" — as leaving two entries unexplained, which it did:
«Traminer» and «Muskat» sit under the Gewürztraminer and Muskat blanc pills.
The line was reworded so the figures add up ("65 of the 67 entries … are
shown, as 63 varieties; not shown: …"), a text-only change. The finding that
remains is the fold itself: the list prints «Gewürztraminer» and «Traminer»
as two rows and the card shows one pill. The other folds are «Roter
Räuschling» and «Roter Müller-Thurgau» under their white variety (Schwyz,
Zürichsee, Zürich, Glarus), «Muskat» under «Muskat blanc» (Innerrhoden), and
two plain synonym pairs (Heida / Savagnin blanc, Blaufränkisch / Lemberger).
Whether Traminer and the two red mutations get pills of their own is a
lexicon question that needs the live VIVC passports — queued, not guessed.
What the judge still lists as "defective" on Jura and Glarus is that the
line counts the names not shown instead of naming them — a choice for
Boris, noted in the queue.

## Open points closed the same day

Boris asked for the four queued points to be addressed. Each turned out
broader than its row.

### 1. Baden's «Chardonel» — a sweep the audit had never made

**Failure mode:** *a roster name the lexicon lacks fuzzy-matches a
look-alike, and the audit that lists fuzzy bindings did not read the
sidecar.* `audit_grape_identity.py` read records with `grapes.details`;
the German BLE and Austrian BML sidecars carry a plain list. Swept over the
28 German sidecars (every raw roster name through the matcher):

| printed | was read as | now |
|---|---|---|
| Chardonel (Baden) | Chardonnay, 88 — and swallowed the Chardonnay beside it | VIVC #16072 |
| Grünfränkisch (7 lists, each beside «Grüner Silvaner») | Sylvaner, 92 | #25041 |
| Cantaro (5 lists) | Ugni blanc, 85 | #2065 (Würzburg; #2064 is a Spanish homonym) |
| Cabernet Eidos, Sauvignon Rytos (Pfalz) | Cabernet Dorsa 85, Sauvignon 89 | #24896, #24883 |
| Blauer Gelbhölzer | Trollinger, 97 | #16158 |
| Blauer Elbling | Roter Elbling, 100 (VIVC's synonym ELBLING BLAUER) | #12651 ELBLING BLAU, whose official German name it is |
| Blauer Kölner, Färbertraube, Mohrenkönigin | Trollinger 96, Gamay de Chaudenay 96, Pinot noir 96 | own slug, no bracket: VIVC files each name under three primes |
| Kleiner Fränkischer Burgunder | Vogelfränkisch (an alias from memory, May) | own slug, no bracket: no VIVC name (FERIDAC #24242 is a lead) |
| Zähringer, Muskat Gutedel, Ruling, Kolor (Baden) | nothing | #13367, #25043, #10381, #6388 |
| Rabner (Baden) | Rabaner, 92 | the same, as an alias: VIVC has no «Rabner» |

Two colours were wrong as well: Vogelfränkisch (#24640) and Adelfränkisch
(#23324) are whites — the lists print them under the white varieties, VIVC
says BLANC, the lexicon said "noir". And two reader defects surfaced: § 8
never ended on the four specifications that print "9. Angaben" with a dot
(Baden kept 141 phrases of its link text as "unmatched names"), and Mosel's
"Findling Gelber Kleinberger" lost its comma (split into two when both
halves are curated exact names — the Spanish reader's rule).

Every id was read on the live VIVC passport. Before re-extracting, every
surface the corpus has met (16,741) was matched with the old and the new
lexicon: 51 changed, one of them unintended — CORNALIN D'AOSTE's passport
lists PETIT ROUGE, so the Valle d'Aosta «Petit rouge» would have read as
Humagne rouge. Petit rouge got its own entry (#9200). German 02 and 02f
against a snapshot: 13 sidecars and 13 EU records, rosters only, every
change one of the table's.

### 2. Wine types — twenty German cards and three Swiss ones

**Failure mode:** *the text states the wine types and no reader reads it;
the card shows the berry-colour floor and says the text names no colour.*
Not six German regions but twenty records: Ahr, Baden, Hessische
Bergstraße, Rheingau, Sachsen (stubs), Saale-Unstrut (its single document is
an amendment naming its sparkling categories only) and fourteen Landweine.

`scripts/_lib/de/ble_styles.py` reads a BLE specification without its area
section and its roster: colours from the wine words ("Rot- und Roséweine"
read whole), never from an analytical limit — "150 mg/l bei Rotwein"
restates a ceiling the law sets per colour whatever the region makes;
categories and Prädikate from the EU reader's own markers, first in a
statement with no figure, then in the region's own minimum must weights,
never in a legal ceiling. Each style is stored with its sentence. The check
on the reader: on the seven regions that do have an EU statement, the BLE
reading gives the same types, one for one. Those keep their EU styles; the
augmenter fills only a record whose own styles carry no colour.

| | before (floor) | after (stated) |
|---|---|---|
| Ahr, Hessische Bergstraße, Rheingau, Saale-Unstrut | Red, White | + Rosé, Sparkling, Semi-sparkling, Late harvest, Sélection de grains nobles |
| Baden, Sachsen | Red, White | the same + Liqueur wine |
| 14 Landweine | Red, White | White, Red, Rosé |

Switzerland: the Schwyz rulings (Ziff. 2.2 "Auch Schaum-, Perl- und
Likörweine können die kontrollierte Ursprungsbezeichnung «AOC Schwyz»
tragen", 2.9, 2.10) and the Zürich ruling (Ziff. III, VII, VIII) carry the
same clauses. They are transcribed in `roster_rulings.json` and tested
against the cached PDFs; the Zürich ruling itself is fetched beside its
annex and cited on the card. The Jura directives and the Appenzell and
Glarus acts name no wine type — floor and line are right there.

### 3. The Swiss names

Of the 34 distinct unresolved names, VIVC holds 15 under a passport of
their own, 8 under none or several (own slug, no bracket), and the list
entry «Seibel 9110» is Verdelet. VIVC files the red mutations apart
(Müller-Thurgau rot #24686, Räuschling rot #24627): two slugs, no longer
folded. «Cornalin / Landroter» is the Valais ordinance's "Cornalin du Valais
(Rouge du Pays)" — the Cornalin identity pass was done with it (Humagne
rouge, Humagne blanc, Rèze), so the Valais Grand Crus show all fifteen
varieties of art. 88. Three of Jura's "breeder codes" are named varieties on
VIVC and are shown under the code; Glarus's «Weinsberg (WE 88-101-13)» is
Sauvitage.

| list | before | after | left |
|---|---|---|---|
| Schwyz, Zürichsee (132 entries) | 100 varieties | 122 | 9 codes, «VB Cabernet» |
| Zürich (130) | 98 | 121 | 8 codes, «VB Cabernet» |
| Glarus (121) | 92 | 113 | 8 codes, «VB Cabernet» |
| Jura (45) | 29 | 34 | 9 codes, «Seibel», «VB Jura 25» |
| Appenzell Ausserrhoden (61) | 54 | 59 | «Muskat Tramin» |
| Appenzell Innerrhoden (67) | 63 | 63 | 1 code, «Cabernet VB» |

Sixty Swiss records changed, because the cantons' own ordinances print the
same names: Aargau + 12, the Vaud AOCs + 8, Fribourg's + 10, Geneva's + 2,
the Valais Grand Crus + 4. Each addition was read in its text (Aargau
prints «Salomé/Siramé» and «Cornalin/Rouge du pays/Landroter», which
confirms two of the identities). No record lost a variety.

Still open, and why: Innerrhoden's «Traminer» beside «Gewürztraminer» —
VIVC files the bare name under four primes, so the catalogue does not
settle it; the federal variety list is the next thing to read.

### 4. Trade bodies

Each site was fetched on 2026-11-17 and its own words read.

| card | body | site | its own words |
|---|---|---|---|
| Vully | Interprofession des Vins du Vully (AIVV) | https://vully.ch/ | page title "AIVV \| Les vignerons – Die Winzer"; footer "INTERPROFESSION DES VINS DU VULLY — CP 20, 1786 Sugiez" |
| Bern (and Thunersee, through its parent) | «Berner Wein», the joint site of the canton's two growers' societies | https://www.bernerwein.ch/ | "Ein Weinbaukanton, zwei Weinregionen. Die Weinbauregion Bielersee und Thunersee Region bilden zusammen «Berner Wein»."; the contact page names the Rebgesellschaft Bielersee and the Rebgesellschaft Thunersee-Bern |
| Bielersee | Rebgesellschaft Bielersee | https://www.bielerseewein.ch/ | "Die Rebgesellschaft Bielersee ist die Interessensvereinigung der Winzerinnen und Winzer am Bielersee." |
| Jura | Association des vignerons jurassiens (AVJ) | https://www.avjura.ch/ | "L'association des vigneron.ne.s jurassien.ne.s (AVJ) a été créée en 2019. L'objectif est notamment de renforcer la visibilité de la viticulture jurassienne" |
| Cheyres | none | — | the only body is the Association des Vignerons Broyards, a cooperative cellar whose site is its shop; no Fribourg cantonal wine body was found. Pinned "none" |
| Regensburger Landwein | none | — | it had Franken's association through the "Bayern" region key; that body calls itself "die berufsständische Vertretung der fränkischen Winzerinnen und Winzer". Two near-fits, neither a growers' body of the Landwein area: the Baierwein-Gesellschaft e.V. (all of Altbayern) and the friends' society of the Baierwein museum at Bach. Pinned "none" |

Not settled: the Rebgesellschaft Thunersee-Bern has a site of its own
(thunerseewein.ch) that answers 403 to automated clients; the Thunersee card
carries the joint Bernese site until someone has opened it in a browser.
The Vully body's remit over both cantons rests on its 2021 press release,
not on its own pages. «Berner Wein» is a joint site, not a body with
statutes — it is listed because the two societies behind it are the
canton's growers' bodies; say if the row should name only a legal entity.

### Card validator on the rebuilt cards

Eight of the 97 changed cards (Opus, $1.31; report
`tmp/validation/cards-open-points-2026-11-17.md`): Baden, Ahr,
Saale-Unstrut, Badischer Landwein, Schwyz, Zürich, Appenzell Ausserrhoden,
Chamoson Grand Cru. The four Swiss cards: "trust", no misleading finding
(Schwyz none at all). The four German ones sent the work round once more.

**Right, fixed**

| finding | failure mode | isolated or broader | fix |
|---|---|---|---|
| Badischer Landwein "do-not-trust": no Pinot noir | *a hyphen set inside a name — "Blauer Spät-burgunder" — and the matcher's hyphen split*: it read "burgunder", a VIVC synonym of Blaufränkisch, which the dedupe then dropped | Landwein Oberrhein the same; no other hyphen-split binding in the 28 sidecars | the closed form is tried first; both cards carry «Blauer Spätburgunder» |
| Baden: Eiswein is a listed Prädikat and there is no Ice wine pill | *the EU reader files Eiswein under late harvest and leaves the ice-wine pill to stage 04's scan of the record's sections; a stub has none* | the five stub regions | the BLE reading maps Eiswein to `icewine` |
| Zürich: the card lists a repealed ordinance as its cantonal regulation | ZH-Lex prints "Aufhebungsdatum 01.01.2018" | Zürich only (Zürichsee's ordinance is Schwyz's) | the row says "(aufgehoben per 1. Januar 2018)" |

**Not a defect**

- Baden, "Findling is mapped to Bouvier" (rated misleading): VIVC flags
  FINDLING as the official German name of BOUVIER #1625, and German
  Wikipedia says the variety selected by Franz Kimmig in 1971 "handelt es
  sich gemäß DNA-Analysen um Bouvier, die unter dem Namen „Findling“ im
  Sortenregister von Deutschland noch geführt wird". The pill is right.
- Baden's principal / accessory split (rated misleading): the open decision
  of this morning (§ 3.2 must weights read as roles) — still Boris's call.

**Right, queued**: four terroir-fact findings on older facts (Saale-Unstrut's
bracket of place names given to three soils where the text gives it to one,
and no climate fact; Ahr; Baden); the category "teilweise gegorener
Traubenmost" (Federweißer), which has no node in the style taxonomy; the
English label "Grains Nobles" on a German card; the coverage line counting
the entries not shown instead of naming them (already flagged for Boris).

**Re-grade after those fixes** (Baden, Badischer Landwein, Zürich; $0.48).
Zürich: "trust", no finding. Badischer Landwein: from "do-not-trust" to
"caution" — Pinot noir is there; what remains rated misleading is «Roter
Traminer», which the list prints beside «Gewürztraminer» and the card shows
as one pill. That is the Traminer question of Appenzell Innerrhoden on a
German list: VIVC files TRAMINER ROTER under SAVAGNIN ROSE #10797 and under
GEWUERZTRAMINER #12609, so the catalogue does not settle it — queued with
that evidence, not guessed. Baden: "caution", the two findings discussed
above (roles, Findling).

### Verification of the follow-up

Two full stage-04 builds (the second after the validator round), no
`--shell-only` needed.

- **Records** (`diff_records.py`, the state before this follow-up against
  the final build): 97 of 3,191 changed, none added or removed — 63 Swiss
  (60 rosters, of which Schwyz, Zürichsee and Zürich also styles; Bern,
  Bielersee and Thunersee the trade body only), 33 German (20 styles, 21
  rosters), Valle d'Aosta (+ Petit rouge). Every change was read at
  extraction level first: the German sidecars and EU records, the Swiss
  records and the Valle d'Aosta sidecar were each re-extracted against a
  snapshot.
- **Build log:** `[grapes] FLAGGED=0 INHERIT=0 REVIEWED=7`; no STALE line.
- **Audits:** `audit_vivc_coverage.py --strict` — 0 pin findings (48 new
  pins); `audit_grape_identity.py --strict` — pass, and what it now lists
  for the German sidecars is spellings only; `audit_empty_grapes.py
  --strict`, `audit_styles.py`, `audit_gi_terms.py --strict` — pass.
- **Release gate** (`validate_release.py --quick`): 11 of 15, the same four
  standing report-only failures as this morning. The ambiguous-synonym
  count went 49 → 50 with the Swiss «Cornalin» (claimed by two passports,
  decided by the Valais ordinance through the Swiss readers' pin) and is 49
  again: the audit counts a banned bare surface with a country pin as
  reviewed.
- **Tests:** 2,502 passed before the last round; the gate's own pytest run
  passed on the final tree, and the three new or extended test files
  (`test_de_ble_styles.py`, `test_ch_roster_rulings.py`,
  `test_grape_identity_guards.py`) pass after it.
- **LLM spend:** $1.79 (two card-validator runs). No extraction or
  translation call.
- **Not deployed, not committed.** A deploy includes the MCP server.

## Three decisions and the last open points (the same evening)

Boris's answers to the follow-up's questions — "ok to use the joint site, if
this is how the legal bodies prefer to present themselves online", "disclose
it", "run translations" — and the three points still queued.

### Trade bodies: the joint site stands, Thunersee has its own

`bernerwein.ch` stays Bern's row. thunerseewein.ch answers 403 to scripts;
read in Chrome, its Impressum and Infos pages name "REBGESELLSCHAFT
THUNERSEE–BERN, c/o Peter Herren, Thörishaus bei Bern". `thunersee` is in
`appellation_urls.json` by slug (it had taken Bern's joint site through its
parent).

### The role split of the German regions: disclosed, then dropped

The specifications draw no principal / accessory line; nine regions were
split by what § 3.2 singles out. Boris's first answer was "disclose it".
Reading the nine before writing the line:

- **Mosel, Pfalz, Nahe, Mittelrhein, Rheinhessen, Sachsen** — the varieties
  named with a minimum must weight of their own ("Rebsorte Weißer Riesling
  6,7 % vol und 55° Öchsle" beside "alle übrigen Rebsorten 7,5 % vol").
- **Rheingau, Hessische Bergstraße** — a named must-weight row and the
  planting shares ("insbes. Weißer Riesling mit rd. 80 % auf der Rebfläche").
- **Baden** — an artefact. Its § 3.2 tiers some fifty-five varieties over two
  Bereich groups and six quality levels and puts Spätburgunder, a third of
  the vineyard, under "alle übrigen Rebsorten"; the "lowest tier" reading,
  run over rows that wrap across lines, had made nineteen principals
  (Tempranillo, Merzling, Baron …). Baden lost its split at once.

The line was built (one amber sentence under the pills on eight regions,
keyed on `must-weight` / `plantings`) and the card validator read the
result: Baden "trust", but Mosel still `misleads` — "only four varieties are
shown as principal … though neither document assigns roles" — with a second
finding that the stated criterion was not even applied consistently (§ 3.2
names "Riesling" and "Elbling"; the card made the white variety principal
while Roter Riesling and Roter Elbling, which share that minimum, read
accessory), and Sachsen `defective` (Riesling and Müller-Thurgau accessory).
Put to Boris with the recommendation to drop the split: "ok".

**Final state:** no split. Stage 02f lists every § 8 variety alike
(`section-8-flat-no-split` on all thirteen regions); the line, its labels
and `ble_role_basis` are gone; eight sidecars changed, roles only. The
names § 3.2 singles out stay in the sidecar as reference data. The lesson is
in CLAUDE.md: a house reading of roles that the regulator's text does not
make is not rescued by a disclosure line.

### Traminer, Roter Traminer, Gewürztraminer: one variety, by the registers

VIVC files the bare TRAMINER under four primes. The two countries' own
registers do not:

- **Switzerland** — Sortenverordnung, SR 916.151.6, Anhang 8 (Stand
  1 December 2025): "Gewürztraminer RS | Roter Traminer/Savagnin rose
  aromatique/Traminer"; «Savagnin rose RS» (Klevner de Heiligenstein) is a
  row of its own, «Weisser Traminer» a synonym of Savagnin blanc. The
  Rebsortenverordnung SR 916.151.7 (repealed 2016) read the same in 2013; the
  Rebsortenverzeichnis SR 916.140.1 was repealed on 1 January 2025.
- **Germany** — Bundessortenamt, Beschreibende Sortenliste Reben 2024: one
  registered variety, "Roter Traminer" (RBE 516), Gewürztraminer and Traminer
  its synonyms in the Länder tables; the BLE's list of classified varieties
  (31 August 2026), row 228, likewise. Baden's two rows copy
  Baden-Württemberg's classification annex of 2005 ("Gewürztraminer Rs" /
  "Roter Traminer R"); the amendment of 7 November 2025 (GBl. 2025 Nr. 110,
  Anlage 1) made it one entry.

The single pill stands on Appenzell Innerrhoden, Baden and Badischer
Landwein. A bare «Muskat» beside «Muskat blanc» (Innerrhoden) names no
variety of its own — the federal list has four Muscat varieties and no bare
name — and keeps sharing the Muskat blanc pill. The ruling's `note` cites
the federal list and the card packet hands it to the judge.

### Tooltip translations, and a collector that never read the BLE sidecars

- A German fetch for the 37 new slugs with no article in the four site
  languages bound five under the variety's own title (Adelfränkisch, Cabernet
  Eidos, Kolor, Ruling, Verdelet). The fetcher builds its titles from the
  unaccented slug, so five more needed a title pin, each lead read against
  the passport: Gelbhölzer, Grünfränkisch, Mohrenkönigin, Réselle, Roter
  Müller-Thurgau. Not attached: de «Färbertraube» (the teinturier group, not
  a cultivar), «Ontario (Rebsorte)» (one of several Ontarios; the slug is
  pinned `false`), «Blauer Kölner» (a disambiguation page).
- `02b_translate_grapes.py --batch`: 66 (slug, language) pairs in two
  batches, $0.09. 23 of the 48 slugs open a tooltip in all four languages;
  25 have no article anywhere (the Agroscope crossings, Cantaro, Zähringer,
  the no-passport names).
- **The first batch skipped four slugs without a word** — Chardonel, Kolor,
  Ruling, Blauer Gelbhölzer. The shared collector (`grape_corpus._SOURCES`,
  and 02g's own `_record_files`) did not read the BLE sidecars, whose
  `grapes` is a list: the eight varieties only the German stub regions list
  (those four, Cantaro, Muskat Gutedel, Serena, Zähringer) were in no corpus.
  Both read them now; a region with an EU document and a sidecar is counted
  once (`_SUPPLEMENT_OF`). Effect, measured before and after: 8 new corpus
  slugs, three labels better or equal ("Chardonnay rosé", "Blauer
  Affenthaler", "Melon"), thirty slugs whose dominant corpus becomes German —
  one of them, Grüner Veltliner, has a German article, so its French and
  Spanish tooltips are now translated from it (re-run in the second batch).
- **Broader, found on the same trail:** the corpus label reached a slug only
  when it had a tooltip. 221 filter-chip and search labels were the
  title-cased slug instead of the regulator's spelling — 140 by accents only
  ("Zumic" for Žumić, "Zahringer" for Zähringer), 54 would have turned Greek
  or Cyrillic. Fixed with the display rules of the next section.

### Greek and Cyrillic names: display rules, and the label fix they settle

The label finding above raised the question of the 54 labels that would turn
Greek or Cyrillic in an English interface. Boris asked for the best practices
and adopted them for the project (CLAUDE.md "Greek and Cyrillic names on
screen", `scripts/_lib/script_display.py`):

- interface text (chips, search rows, prose, titles, descriptions, MCP
  answers) leads with the Latin form, the original in brackets where there
  is room; a surface that quotes the regulator (the card's name, a grape
  pill) keeps the original first;
- the Latin form is the catalogue's name where one exists, else the national
  standard (ELOT 743, the Bulgarian Streamlined System) — never the ASCII
  fold the slugs carry;
- the original is language-tagged (`lang="el"` / `lang="bg"`) wherever it is
  written into a page; lists sort by the Latin form.

Applied the same evening:

- **Grape labels.** Every corpus slug carries its regulator label (1,656 →
  1,774 entries in the grape table: 621 gain a label, 118 varieties with
  neither a VIVC record nor an article become searchable), and the 63 with a
  Greek or Cyrillic label a Latin form: "Aheloy" for Ахелой (the slug says
  "akheloi"), "Sultanina" for Σουλτανίνα (VIVC), "Ranna melnishka loza" for
  the slug `early-melnik` (the old label stays a search alias). Chips, prose
  and MCP answers show the Latin form; a grape search row shows the original
  beside it; a chip keeps it as its tooltip.
- **Pill brackets.** The bracket of a Greek or Bulgarian pill without a VIVC
  record was unidecode's: "Σαββατιανό (Sabbatiano)", "Ξυνιστέρι (Ksunisteri)",
  "Гъмза (G'mza)", "Αθήρι Β (Atheri B)". It is the national standard now —
  Savvatiano, Xynisteri, Gamza, Athiri — on 224 pills of 68 spellings. One
  Latin pill loses a pointless bracket ("Blauer Gänsfüßer (Blauer
  Gansfusser)").
- **Language tags** on appellation names, region labels and grape pills in
  both card renderers, the sidebar, the stack and related rows, the search
  rows, the active-filter chips, the embed popup and the browse hub; the
  Python and JavaScript tagging are tested on the same cases, and a test
  fails when a build carries a Greek or Cyrillic name from a country other
  than Greece, Cyprus or Bulgaria.
- **Not changed, queued:** the Greek, Cypriot and Bulgarian region labels are
  still the native string alone in the sidebar and on the card (tagged now);
  leading with the exonym there touches the "region labels in the native
  form" rule and is a decision.

### The older terroir findings: Saale-Unstrut, Ahr, Baden, Badischer Landwein

Each finding was re-read against the BLE text before anything was written:

- **Saale-Unstrut** — the source reads "Aber auch Buntsandstein (Großjena,
  Weißenfels, Weiße Elster, z. T. Bad Kösen), Lößlehm und Kupferschiefer sind
  zu finden": the bullet gave the bracket to all three. That claim had been
  on file as a do-not-claim entry since the audit of 2026-09-14 and the
  record was never re-run. No bullet carried the climate (9.2: about 9.6 °C,
  about 500 mm in the rain shadow of the Harz, about 1,686 sun hours), and
  the English "often with a very high stone content" stood for "teilweise".
- **Ahr** — "Rebflächen auf Kiesen und Lehmen … haben im gesamten
  Weinbaugebiet eine recht weite Verbreitung"; the bullet had joined them to
  the sentence on the eastern part.
- **Baden, Badischer Landwein** — "das südlichste deutsche Anbaugebiet Baden
  … Hieraus resultiert die besonders intensive Nutzung der Rebsorten der
  Burgunderfamilie" was not captured; Baden's slope bullet had dropped "rund",
  "überwiegend" and the place.

Feedback entries (evidence `tmp/terroir-facts-review/card-validator-2026-11-17/`,
review `review-2026-11-17-cards`: 3 do-not-claim, 3 capture hints), then one
scoped run: `rerun_terroir_facts.py --run de-ble-cards-2026-11-17
--scoped-02d --scoped-gate --scoped-backcheck`, $0.71 at the batch rate
(02d $0.13, gate $0.15, 02e $0.11, back-check $0.31).

| record | facts before → after | gate | what changed |
|---|---|---|---|
| Saale-Unstrut | 7 → 12 | 1 narrowed | climate stated; the bracket claim gone; "in places with a very high stone content" |
| Ahr | 10 → 12 | 1 dropped | "quite widespread throughout the wine-growing area" |
| Baden | 8 → 13 | — | southernmost region and the Burgunder consequence; the slope sentence with its hedges and place |
| Badischer Landwein | 5 → 5 | 1 narrowed | the same link, and 7.3's sentence on the Landwein |

The back-check corrected 39 translated bullets (en 7, fr 7, es 12, nl 13).
Audit: strict failures 0, no recurrence of a known claim on the four.
Rollback: `rollback_terroir_facts.py --run de-ble-cards-2026-11-17`.

The card validator then noted that Ahr's climate sentence (8.2: 9.8 °C,
about 650 mm, about 1,450 sun hours), which the card had carried before, was
gone. A capture hint and a second scoped run (`de-ahr-climate-2026-11-17`,
$0.23) did not bring it back: the extractor returned six natural-factor
bullets of a cap of seven without it, and nothing downstream dropped it.
The second run's facts are the ones in the build (12 facts; "trust"); the
omission is queued with that evidence.

### Card validator on the rebuilt cards (evening)

Twelve cards after the first build of the round (Opus, estimate $2.26): 7
trust, 4 caution, 1 do-not-trust. The cards the round set out to fix pass —
Baden, Saale-Unstrut, Ahr, Rheingau "trust" (Baden had been "caution"),
Appenzell Innerrhoden "trust" with no finding (the Traminer note in its
packet), Naoussa and Koumandaria "trust" with the new display. What it
found, and what became of it:

| card | finding | verdict |
|---|---|---|
| Mosel, Sachsen | the role split misleads even with its disclosure line | **fixed** — the split is gone (above) |
| Sachsen | Saint Laurent, the last red variety, missing | **fixed** — the last name of a BLE roster ran into the next sentence; also Hessische Bergstraße's Blauer Zweigelt (sweep of the 28 sidecars: no other variety lost) |
| Mosel | "Cabernet Bordo (Cabernet Franc)" and no Cabernet Franc | **fixed** — VIVC #22814 is a German variety of its own and the BLE's list has both rows; six records gain the pill |
| Naoussa | a cooperative winery as "trade body" | **fixed** — `null`; the growers' association exists ("Wines of Naoussa") but no site was found; the other Greek cooperative rows are queued |
| Ahr | no climate fact after the re-run | **not fixed** — a second run with a capture hint ($0.23) did not bring it back; queued with the evidence |
| Mosel | three varieties only the national specification lists | inconclusive — which document is the newer is not established; queued |
| Baden, Mosel, Badischer Landwein | breeding lines not shown; «Roter Traminer» "missing" | queued — a roster-coverage line for German lists, as the Swiss cards have (the Traminer fold is right by the registers) |
| Thunersee | filed under Trois-Lacs | queued for a decision — Swiss Wine Promotion's own pages list "AOC Bern" and "AOC Thunersee" under Deutschschweiz and four AOCs under Drei-Seen (Bielersee, Cheyres, Neuenburg, Vully); a parent and child in two regions |
| Melnik | polygon older than the 2023 single document | queued (the Bétard-delta class) |
| Naoussa, Koumandaria, Mosel | semi-dry style; two translated facts; the Einzellage rule | queued |

Re-grade of the six German cards after the final build (estimate $1.38): 4
trust (Sachsen, Hessische Bergstraße, Ahr, Rheingau), 2 caution — Mosel, down
from do-not-trust (the three BLE-only varieties, the Einzellage rule, one
qualifier in a fact) and Pfalz (not graded before): «Blauer Muskateller» and
«Roter Muskateller» under one pill. That one is the Cabernet Bordo class
again, so the BLE's list of classified varieties (303 rows) was swept through
the lexicon: four pairs of rows share a slug — the Muskateller pair (six
records), Schwarzer / Weißer Heunisch (two records), and two pairs no list
prints today — and six rows bind nothing. Queued as one row with the recipe.
The second Ahr run is kept: both runs grade "trust" with two omissions each
(the second lacks the minerality sentence the first had; neither has the
climate).

### Verification of the evening round

Two full stage-04 builds; `--shell-only` was not used.

- **Records** (`diff_records.py`, the state before the round against the
  final build): 18 of 3,191 changed, none added or removed — the eight
  regions without a split (Mosel, Pfalz, Nahe, Mittelrhein, Rheinhessen,
  Rheingau, Hessische Bergstraße, Sachsen; + Saint Laurent, + Blauer
  Zweigelt, + Cabernet Bordo where printed), Baden (roles and facts), the
  three Mosel Landweine and Pfälzer Landwein (+ Cabernet Bordo), Ahr,
  Saale-Unstrut and Badischer Landwein (facts), Naoussa and Thunersee (trade
  body). Every roster change was read at extraction level first, against a
  snapshot (German EU records and sidecars, three times).
- **Pages** (the content part of every English and Dutch entity page,
  before against after): 288 English pages changed — Greek, Cypriot and
  Bulgarian pages for the language tags and Latin forms, the German pages
  above, Swiss and German pages whose pills gained a tooltip link, the
  browse hub. The classification of every changed page was read; samples
  diffed line by line.
- **Browser** (headless Chromium against `serve.py`): a Bulgarian card, the
  grape search in Latin and Cyrillic, a shared `?grape=` link's chip, the
  Greek region group, no role line on Mosel, Baden, Rheingau; no script
  error.
- **MCP** (the server's core on the rebuilt context): "Mavrud [Мавруд]",
  "Aheloy [Ахелой]"; `grape=Мавруд`, `Mavrud`, `Aheloy` and `early melnik`
  all resolve; `npm test` 24 of 24. The server needs a deploy with the site.
- **Build log:** `[grapes] FLAGGED=0 INHERIT=0 REVIEWED=7`; no STALE line.
- **Audits:** `audit_vivc_coverage.py --strict` — 0 pin findings (49 pins of
  the day, 37 on a passport); `audit_grape_identity.py --strict` — pass; the grape-tooltip
  identity audit lists none of the new tooltips.
- **Release gate** (`validate_release.py --quick`): 11 of 15, the same four
  standing report-only failures; none grew (ambiguous synonyms 50 → 48, with
  `roter-traminer` a lexicon key; Bétard delta 121; untranslated 120 pairs
  on 56 records, as in the morning).
- **Tests:** the gate's pytest run passes on the final tree (2,515 tests in
  the full suite; new: `tests/test_script_display.py`, and cases in
  `test_content_block.py`, `test_de_parser.py`, `test_de_ble_styles.py`,
  `test_grape_corpus_labels.py`, `test_browse_page.py`,
  `test_mcp_query_context.py`).
- **LLM spend of the round:** $1.03 at the batch rate (tooltip translations
  $0.09, the two terroir runs $0.71 + $0.23) and two card-validator runs
  (estimates $2.26 + $1.38).
- **Deployed 2026-11-17 (evening), not committed.** Site: 18,246 files
  uploaded, replicas fresh at the first probe, 60 of 60 sampled files and 7
  of 7 large files (tilesets, sitemap, MCP context) match through the CDN,
  1,528 changed pages submitted to IndexNow. MCP server: release
  `ca9fe0d+dirty`, smoke test in the three protocol modes; live, it answers
  Melnik's grapes in Latin ("Keratsuda", "Melnik 82") and resolves
  `grape=Mavrud` and `grape=Мавруд` to the same 13 appellations.


## Verification after the rebuild (the morning's triage)

Full stage-04 build of 2026-11-17 (the seventh started in this session;
five were stopped because a later finding changed records), then one
`--shell-only` re-emit for the reworded line (no staleness warning; the four
MCP context files byte-identical in size to the full build's).

- **Records** (`diff_records.py`, the pre-triage snapshot against the
  build): 25 of 3,191 changed, none added or removed, every one intended —
  the seven Swiss rosters (Jura 29, Appenzell IR 63, Appenzell AR 54, Glarus
  92, Schwyz 100, Zürichsee 100, Zürich 98 varieties; each gains the
  floor's Red and White with them); Uri's source; Baden (×0.273) and
  Württemberg (×0.256) on `lgl-gemarkung-union`; Badischer Landwein,
  Landwein Oberrhein, Landwein Neckar and Schwäbischer Landwein following
  their members; Landwein Main (×0.169), Landwein Rhein-Neckar (×0.279,
  region Baden-Württemberg) and Bayerischer Bodensee-Landwein (×0.003, three
  communes) on their own specification; Franken + Sparkling, Saale-Unstrut
  + Semi-sparkling, Württemberg + Red, Rosé, Sélection de grains nobles,
  Late harvest; the Neuchâtel trade body off Bern, Bielersee, Thunersee,
  Cheyres, Vully and Jura; the national body on Taubertäler Landwein.
- **Build log:** `baden: 353/353 Gemarkungen`, `wurttemberg: 275/275` with
  the one pin; Saxony's Landwein 0/43, not redrawn; `[grapes] FLAGGED=0
  INHERIT=0 REVIEWED=7`.
- **Geometry audits:** `audit_geometry_outliers.py --strict` ok (0
  unreviewed, 0 stale, 78 accepted); `audit_geometry_overlaps.py --strict`
  ok (0 suspicious; Baden × Württemberg is no longer a pair).
- **Release gate** (`validate_release.py --quick`): 11 of 15 checks pass.
  The four that fail are the standing report-only ones, unchanged since the
  release of 2026-11-14 (grape-surfaces, 49 ambiguous synonyms, 120
  untranslated pairs, Bétard delta 121 — one fewer than then: Württemberg,
  whose register entry was modified in July 2026, no longer draws from
  Bétard; Baden's was last modified in 2019, before the snapshot).
  `pytest`: 2,432 passed, re-run after the rewording.
- **Browser against server-rendered card** (headless Chromium on the local
  build): the coverage line and the Sources rows are the same text on both
  for Schwyz, Zürichsee, Zürich, Jura, Glarus, the two Appenzells, Baden,
  Württemberg, Sussex, Bayerischer Bodensee-Landwein and Vully, in en / fr /
  es / nl; the Württemberg and Baden boundary lines as checked before.
- **Not deployed, not committed.**

## Changes

- `scripts/_lib/de/gemarkung.py`, `gemarkung_pins.json` (new);
  `scripts/_lib/de/geometry.py` (`lgl-gemarkung-union`, the Bavarian units,
  member unions); `scripts/de/00_fetch_data.py` (layer fetch,
  `--refresh-lgl`); `scripts/de/02f_extract_produktspezifikation.py`
  (`area_text`); `scripts/de/02_extract_pliegos.py`,
  `scripts/_lib/de/einziges_dokument.py` (wine-type titles, compound
  markers).
- `scripts/_lib/ch/roster_rulings.{json,py}` (new, seven rosters);
  `scripts/ch/01_fetch_reglements.py` (act fetch, `_is_pdf`);
  `scripts/ch/02_extract_reglements.py`; `scripts/_lib/ch/reglement_index.py`
  (Uri); `scripts/_lib/empty_grapes_overrides.json` (seven pins gone, four
  reasons corrected); `scripts/_lib/card_packet.py` (the validator sees the
  ordinance and the act).
- `scripts/04_build_maps.py`, `scripts/_lib/content_block.py`,
  `scripts/_lib/assets/app.js`, `scripts/_lib/map_template.py` + the four
  catalogs (seven labels: five for the Gemarkung lines, the roster-coverage
  line, the BLE Sources row).
- After the validator: `roster_rulings.py` (`coverage`, list readings),
  `scripts/_lib/ch/reglement.py` (no half-name match in a roster cell),
  `content_block.py` (Swiss, UK, register-cahier and BLE Sources rows),
  `scripts/_lib/appellation_urls.json` (Neuchâtel by slug, the Bodensee
  Landwein, Baden-Württemberg).
- `tests/test_de_gemarkung.py`, `tests/test_ch_roster_rulings.py` (new);
  `tests/test_content_block.py`, `tests/test_de_parser.py`.
- `GEOMETRY_SOURCES.md` (Germany), `CLAUDE.md`, `CURATOR_TODO.md`.
- No contributor added (no name offered).

Evening round:

- `scripts/_lib/script_display.py` (new); `scripts/_lib/lexicon_loading.py`
  (every corpus slug labelled, `name_latin` by catalogue name or national
  standard); `scripts/_lib/assets/query_core.mjs` (`grapeName` Latin-first,
  `grapeNative`); `scripts/_lib/assets/app.js`, `scripts/_lib/content_block.py`,
  `scripts/_lib/map_template.py` (language tags, grape search rows and
  chips, the browse hub, the MCP context's `name_latin`).
- `scripts/_lib/grape_corpus.py`, `scripts/02g_fetch_vivc.py` (the BLE
  sidecars are part of the slug corpus); `scripts/_lib/grape_lexicon.py`
  (`cabernet-bordo`, `roter-traminer`); `raw/wikipedia/grape_overrides.json`
  (five German title pins).
- `scripts/_lib/de/produktspezifikation.py`,
  `scripts/de/02f_extract_produktspezifikation.py` (no role split; the last
  name of a roster cut from the sentence after it); `scripts/_lib/augment/de.py`.
- `scripts/_lib/ch/roster_rulings.json` (the Innerrhoden reading note),
  `scripts/_lib/card_packet.py` (the note reaches the judge);
  `scripts/_lib/appellation_urls.json` (Thunersee; Naoussa `null`).
- `tests/test_script_display.py` (new) and cases in six test files; the four
  catalogs (three labels added and removed again with the role line).
- `CLAUDE.md` ("Greek and Cyrillic names on screen", the German roster
  without a split, Traminer, Cabernet Bordo, the slug corpus),
  `CURATOR_TODO.md`.
- No contributor added (no name offered).
