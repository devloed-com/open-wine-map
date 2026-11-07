# Visitor feedback triage — 2026-10-30

Queue: `scripts/feedback_report.py --range 30d`. New since the 2026-10-24
triage: 4 flags, all retracted, no note. They come from one Spanish-locale
visitor on two cards. A fifth flag, Crozes-Hermitage at 15:00, is handled
in the Afternoon section below.

| flagged | aspect | locale · view | verdict |
|---|---|---|---|
| Somontano, 2026-10-28 17:00, retracted | name, sources | es · zone z8.2 | name and source correct. The card misses two styles; fixed today |
| Manchuela, 2026-10-29 22:00, retracted | facts, grapes | es · zone z8.5 | grapes correct. One bullet carries a Wikipedia-only figure; queued |
| Crozes-Hermitage, 2026-10-30 15:00, not retracted | boundary | fr · footprint z10.9 | polygon correct. The cahier reader had dropped the partial commune Mercurol (56 FR records, fixed, not yet built); one bullet called the 1989 parcel selection a narrowing of the zone, re-run |

The live cards matched the local build byte for byte (data of 2026-10-27).
Both were graded with `audit_cards_llm.py --only somontano --only manchuela
--locale es` (report `tmp/validation/cards-fb-2026-10-30.md`, 3 misleading
findings, all quotes verified). The sources were checked with
`audit_source_freshness.py --tiers eu,national,regional --deep`.

## Found on the way: the register changed `productType`

On its first run the freshness probe reported all 149 Spanish GIs as GONE.
The live eAmbrosia list now writes `"productType":"Wine"`; our cached indexes
of 2026-10-24 say `"WINE"`. No other field changed: the live register still
lists 149 registered Spanish wines, the same file numbers.

- **Failure mode:** an exact-case comparison against a register value.
- **Isolated or broader:** broader. All 18 eAmbrosia stage-00 scripts (ES,
  PT, IT, AT, SI, HR, HU, RO, BG, GR, DE, SK, CZ, LU, BE, NL, MT, CY) and the
  freshness probe filtered with `== "WINE"`. Any stage 00 re-run from now on
  would have written an empty index for its country, and the next stage 02
  would then have emptied that country's corpus. No index was overwritten:
  every cached index still holds its wines.
- **Fix:** the comparison is case-insensitive in all 19 places.
  `tests/test_eambrosia_product_type.py` fails on any case-sensitive
  `productType` comparison under `scripts/`.

The probe then ran clean: Somontano and Manchuela CURRENT. It also listed the
month's Spanish drift: a new Rioja publication of 2026-10-28
(Ares(2026)9894302, not fetchable), date-only modifications for Arribes,
La Mancha, Navarra and Priorat, and 8 amendments in opposition.

## Somontano — name, sources (retracted)

- **Name and classification:** "Somontano", DO (DOP), Aragón. Correct.
- **Source:** the card cites MAPA's `somontano_2011_01_01.pdf`. Aragón's
  Somontano page lists the 2012 pliego (Orden de 2 de agosto de 2012, BOA
  164) as the one in force. A word diff of the two texts gives 0.988, with
  typographic differences only ("ác." / "ácido") plus the 2012 Order's
  citation. The register holds only the 2014 summary sheet. So the source is
  current.
- **Amendment in progress:** Aragón has published AM01-2026 (*en trámite*,
  PDO-ES-A0534-AM01): a 9 % vol minimum for still wines, partially
  dealcoholised wines, a pét-nat subtype of the quality sparkling wine, and
  a skin-macerated white (*brisado*), among other changes. Not in force;
  watched in CURATOR_TODO.

### Found on the card: two styles missing

The validator graded two omissions "misleads". The pliego defines
"a.2. Vinos espumosos de calidad" and "a.3. Vinos de licor", but the card
showed Naturally sweet, Red, Rosé, Sweet and White only.

- **Failure mode:** the ES reader's lettered type-list line (`a. Vino …`,
  La Palma, 2026-10-23) did not allow a number under the letter (`a.2.`).
- **Isolated or broader:** isolated. A sweep over all 185 ES records' section
  text found numbered type lines in two: Somontano, and Valle del Cinca
  ("Vinos no sometidos a envejecimiento"), which names no style and does not
  change.
- **Fix:** `_TYPE_LIST_LINE_RE` in `scripts/es/02_extract_pliegos.py` takes
  `a(.N)*.`; a test in `tests/test_phase_c_styles.py`. `es/02 --only
  somontano` changed the record's `styles` and nothing else: it gained
  Sparkling, Quality sparkling, Fortified and Vin de liqueur.

## Manchuela — facts, grapes (retracted)

- **Grapes:** the 31 varieties match the single document C/2026/3565 and
  the JCCM pliego. The ice-wine pill is right: the document defines *vino de
  hielo* (grapes picked at −5 °C or below).
- **Missing style (graded "misleads"):** the document's wine types are "Vino
  blanco, blanco fermentado en barrica, vino naranja y rosados", and the
  card had no pill for a white fermented on its skins. **Added the same
  day** (decision below).
- **Facts (graded "defective"):** the bullet "temperatura media anual de
  13 °C y precipitaciones en torno a 600 l/m², con ausencia casi total de
  lluvias entre mayo y septiembre" has `both` provenance. Only the dry summer
  is the pliego's; the two figures are Wikipedia's. The card showed no
  Wikipedia marker for a `both` bullet. **Marked the same day** (decision 2).

## Decision 1 — a style for the skin-contact white

The label is neither "orange" nor "amber".

**The term.**
- **The OIV.** The only international definition is its "white wine with
  maceration" (Resolution OIV-ECO 647-2020, Code I.4.9: white grapes, at
  least a month on the pomace). It was adopted on Georgia's proposal and
  uses neither colour word; its text calls the colour "orange-amber".
- **The documents in the corpus split:** "vino naranja" (Manchuela,
  Arribes), "orange wine" as an optional label term (Pla de Bages),
  "narancsbor" (Somló), "brisado" (the Catalan DOs), "maischevergorene
  Weißweine" (the DE Landweine), and "vino blanco con maceración de pieles"
  in Somontano's pending AM01.
- **The choice:** the slug `skin-contact-white`, under White. Labels:
  "skin-contact white", "blanc de macération" (OIV's French term and fr.
  Wikipedia's technical name), "blanco de maceración", "wit met
  schilcontact".
- **Search:** orange wine, amber wine, vino naranja, brisado, narancsbor,
  karvisperi and other names find the style.
- **Tooltip:** Wikipedia's "Orange wine" article in en / fr / nl ("also
  known as … amber wine"), and es "Vino brisado". The es "Vino naranja" is a
  disambiguation page that includes the orange-peel wine of Condado de
  Huelva.
- The label is a gettext entry, so "Orange / amber" is a four-line change
  if preferred.

**Which records.** 13 records state the type:
- Spain: Manchuela, Arribes, Pla de Bages, Conca de Barberà, Empordà,
  Tarragona.
- Hungary: Somló.
- Germany: six Landweine (Mosel, Ruwer, Saar, Nahegauer, Pfälzer,
  Rheinburgen).

Two candidates from the first sweep were read and left out:
- **Portugal's *curtimenta*:** fermentation on the skins in general, as
  for reds and light-skin rosés. No Portuguese document names a white of
  that kind, so the earlier count of 14 Portuguese records was wrong.
- **Italy's *ramato*:** listed by the disciplinari as a synonym of
  *rosato*.

**Readers.**
- ES: `parse_styles_es`, body patterns "vino naranja" (not "… del Condado")
  and "brisado".
- HU: `STYLE_MARKERS`, "narancsbor".
- DE: `STYLE_MARKERS`, "maischevergorene Weißwein".
- Tests are in `tests/test_phase_c_styles.py`.

**Re-extraction.** Full ES, DE and HU stage 02 runs, plus `hu/02f --slug
somloi`. The record diff shows styles changed on exactly those 13 records.
The full ES run also filled the colour of Malvasía aromática ('' →
'blanc') in 20 rosters, from the phase H lexicon entry those records had
not been re-extracted for; no roster changed membership.

## Decision 2 — the Wikipedia marker when part of a claim is Wikipedia's

Somontano has the same kind of bullet as Manchuela: the pliego describes
the Italic settlers, while only Wikipedia says "fueron los romanos quienes
consolidaron el cultivo de la vid". La Palma's tea-barrel figure
(2026-10-25) was a third instance, fixed one record at a time.

**The rule** (`scripts/_lib/terroir_wiki_part.py`). A `both` fact gets
`wiki_part` when its bullet carries a Wikipedia-only term: one the
`wiki_quote` carries and the whole regulator record lacks. That means a
standalone number, a proper noun, or two word stems. The regulator record
is the lien, the record's other sections, and the national and register
sidecars.
- **Why the whole record:** 56 of the 176 bullets flagged against the lien
  alone were claims another section states (Brindisi's comuni, Bonarda's
  tasting note, the decree dates of Corton-Charlemagne and Quincy).
- **What the rule leaves alone:** unit words ("metros" against the pliego's
  "m"), a superscript ("m²") and a single inflected word ("llamadas").

**Precision.** A hand reading of 20 flagged French and Italian bullets
found 14 genuine Wikipedia-only details:
- Kirchberg de Ribeauvillé's 60–100 cm, Jules Lavalle 1855, Palette's
  300 days of sun, the Duchi Salviati, Kaefferkopf's decree years and
  others.
- The rest were statements Wikipedia copies from another article of the
  regulator text, which the whole-record check then removed.

**Where it runs.** `recompute_terroir_provenance.py` writes the field (run
`wikipart-2026-10-30`, 735 caches snapshotted, 119 facts marked);
`rerun_terroir_facts.py` runs that pass after the gate. Stage 04 passes it
into the panel payload, and a `both` fact the pass has not read counts as
marked. The card (`app.js`) and the server-rendered card
(`content_block.py`) show the Wikipedia marker. The query core reports the
fact's source as "specification and wikipedia" and adds the CC BY-SA
licence, which the MCP server serves from its next deploy.

**Side effect.** The same pass moved two French facts whose Wikipedia quote
no longer grounds from `both` to `cahier`: Irancy #9 and Val de Loire #4.

## Changed today

- **Readers:**
  - `scripts/es/02_extract_pliegos.py`: the numbered type-list line
    (Somontano) and the skin-contact white.
  - `scripts/_lib/hu/egyseges_dokumentum.py` and
    `scripts/_lib/de/einziges_dokument.py`: the skin-contact white.
- **Style taxonomy:** `scripts/_lib/style_taxonomy.py` gains the node, with
  labels in four `.po` catalogs and the tooltip titles in
  `raw/wikipedia/style_overrides.json` (02b fetched four extracts).
- **Wikipedia marker:** the new `scripts/_lib/terroir_wiki_part.py`, wired
  through `recompute_terroir_provenance.py` and `rerun_terroir_facts.py`;
  stage 04 (`04_build_maps.py`), `content_block.py`, `app.js` and
  `query_core.mjs` render it.
- **Register filter:** the `productType` comparison, made case-insensitive
  in 18 `00_fetch_data.py` scripts and `_lib/freshness/eambrosia.py`.
- **Tests:** `tests/test_eambrosia_product_type.py`,
  `tests/test_terroir_wiki_part.py`, and new cases in
  `tests/test_phase_c_styles.py` and `tests/test_content_block.py`.
- **Re-extraction:** ES, DE and HU stage 02, and `hu/02f --slug somloi`.
  The 735 terroir source caches rewritten by the post-pass are snapshotted
  under run `wikipart-2026-10-30`.
- **Builds:** stage 04 was rebuilt twice. Against the morning's build,
  `somontano` gained four styles, then 13 records gained
  `skin-contact-white`; nothing else changed.
- **Re-grades:** Somontano and Manchuela (es) both went from "caution" to
  "trust", with no misleading findings left.
- **Tests:** 1,787 Python tests and 24 MCP tests passed at the deploy; 1,801
  after the evening follow-ups below.
- **Deployed 2026-10-30:**
  - The site went out with `deploy.sh`; IndexNow received 564 changed
    pages.
  - The MCP server went out with `deploy_mcp.py deploy` as release
    `e470bcc+dirty`, and its smoke test passed in all three protocol modes.
  - The release gate ran first (`validate_release.py --quick`): 9 of 13
    checks pass. The four failures (grape-surfaces, ambiguous-synonyms,
    untranslated, betard-delta) carry the same counts as the 2026-10-25
    gate.

### Queued from the re-grade

- **Manchuela's sweetness levels.** Fixed the same day (follow-up below).
- **No Wikipedia row in the Sources.** A card with Wikipedia-marked bullets
  lists no Wikipedia entry among its Sources. The marker links the article
  and its licence; whether the Sources list should carry it too is a UI
  decision.

## Follow-up — sweetness levels listed as types (ES)

The re-grade found that Manchuela lists "semisecos, semidulces y dulces" as
wine types, yet the card showed Ice wine and no Sweet pill. The phase-C rule
(GR, HU, BG, IT) had no Spanish reader.

**The rule.** `es/02` `sweetness_type_styles` treats a list of two
sweetness levels or more as the wine's types. Semidulce adds Semi-sweet,
dulce adds Sweet, and seco / semiseco add nothing. Lists of this kind:
- "Vinos Semisecos, Semidulces y Dulces, blancos, rosados y tintos"
  (Almansa);
- "se clasifican en secos, dulces, semisecos y semidulces" (Bullas);
- "para semisecos, semidulces y dulces", a limit set for those wines
  (Uclés).

A single word never counts ("sabor dulce", "taninos dulces"). Neither does
the link section or its sub-sections: Rosalejo's 8.3 reads "Los vinos de la
IGP Castilla pueden ser secos, semisecos, semidulces y dulces, los vinos
Rosalejo sólo son secos".

**Checking.** Every list's context was read before the re-extraction. The
full ES run changed `styles` on 31 records and nothing else: 24 parents,
the 3 Rioja subzonas and the 4 Vinos de Madrid subzonas. Two of the parents
were outside the first sweep, which read only the routed sections:
Extremadura ("Para los vinos blancos, rosados, dulces y semidulces …") and
Vinos de Madrid ("claretes dulces o semidulces").

The tests are in `tests/test_phase_c_styles.py`.


## Afternoon — Crozes-Hermitage, boundary (not retracted)

One more flag arrived at 15:00: Crozes-Hermitage, aspect *boundary*, in
the French locale. The view was the vineyard footprint at z10.9, the zoom
just before the parcels fade in. The flag was not retracted and carries no
note. The visitor saw the 2026-10-27 build, whose Crozes geometry is the
same as today's.

**The polygon is right.**
- **Against the text:** the INAO parcellaire for denomination 1365 is
  4,227 ha in 11 commune rows. The cahier's section IV names 11 communes:
  10 whole, plus Mercurol-Veaunes for the commune déléguée of Mercurol.
  `audit_geometry_vs_text.py --only crozes-hermitage-ou-crozes-ermitage`
  reports OK.
- **The footprint** (`audit_vineyard_envelopes.py --water`):
  - 51.6 km² against 41.5 km² of parcels, a ratio of 1.24;
  - 0.11 km² laid over Hermitage's parcels;
  - 0.01 km² of water.
- **A look at the live map** at z9.5, z10.9 and z12 (fr) matches the
  parcels. The card discloses the footprint under "À propos du contour".

**What the card says about the area.** The card validator rated the card
"trust" (fr, `tmp/validation/cards-fb-2026-10-30b.md`): 0 misleading
findings and 4 minor ones. One of them bears on a boundary reading. The
human-factors bullet says "La zone géographique … s'est étendue à 11
communes dès 1952 avant d'être resserrée en juin 1989 à 3200 hectares".
The cahier says something narrower: in 1989 "une nouvelle sélection des
parcelles … réduit le potentiel de production de 4800 hectares à seulement
3 200 hectares". The geographical area itself stayed at 11 communes. A
reader who takes the bullet at its word sees 3,200 ha on the card and a
4,227 ha shape on the map. Whether that is what the visitor flagged cannot
be known without a note.

- **Failure mode:** the bullet attributes a parcel selection to the
  *zone géographique* (the gate's "wrong entity").
- **Isolated or broader:** isolated as far as this triage goes. The gate
  passed it in September (`gate-v2`, Opus 5). The class is the gate's own
  over-claim catalogue, which the 2026-10-25 re-grade measured
  corpus-wide; no new sweep was run.
- **Fix:** two do-not-claim entries in the feedback sidecar. This one, and
  bullet #0's "entre Crozes-Hermitage et Serves-sur-Rhône", which the
  validator found placed after Saint-Joseph. They were merged with
  `build_terroir_feedback.py` (review `cards-fb-2026-10-30`; evidence in
  `tmp/terroir-facts-review/cards-fb-2026-10-30-crozes/`). Then a scoped
  re-run, `rerun_terroir_facts.py --slug crozes-hermitage-ou-crozes-ermitage
  --run fb-crozes-2026-10-30 --scoped-02d --scoped-gate --scoped-backcheck`.

### Found on the way: the cahier reader dropped partial communes

The record's aire list had 10 communes, not 11. Mercurol was missing.
Section IV writes:

> Communes retenues en entier : Beaumont-Monteux, …, Serves-sur-Rhône et
> Tain-l'Hermitage.
> Commune retenue en partie : Mercurol-Veaunes pour le seul territoire de
> la commune déléguée de Mercurol.

`parse_communes` read the second line as the tail of "Tain-l'Hermitage",
and `by_dept` cut it at the full stop. The label "Communes retenues en
entier : " stayed glued to the first item.

- **Failure mode:** the "Commune(s) retenue(s) en entier / en totalité /
  en partie :" labels were read as commune text.
- **Isolated or broader:** broader.
  - A determinism control first: re-extracting all 467 FR parent aires in
    memory with the old code reproduced the records on disk exactly.
  - With the fix, 56 parents change:
    - Crozes-Hermitage gains Mercurol;
    - Bergerac gains Beaumontois-en-Périgord;
    - Côtes de Provence gains Les Arcs-sur-Argens and Marseille (9e) and
      loses six label-prefixed duplicates;
    - the Alsace AOC's proximity zone gains Wingersheim;
    - the 51 Alsace grands crus gain Kaysersberg-Vignoble ("pour le seul
      territoire des communes déléguées de Kientzheim et de Sigolsheim")
      and lose a stray "de Sigolsheim" token;
    - Muscadet Sèvre et Maine loses two "de la qualité" prose fragments.
  - Nothing is drawn from these lists: every one of these records is
    `parcellaire`. They feed the wiki pages, the index's commune count,
    the register shadow report and the geometry-vs-text audit.
- **Fix:**
  - `parse_communes` strips the whole-commune labels and turns the
    partial-commune label into a list separator. A lowercase "de …" token
    that follows a "pour le seul territoire" qualifier joins it.
  - Two tests in `tests/test_fr_cahier_parser.py`.
  - `02_extract_cahiers.py --only` on the affected names: 82 files
    changed, the 56 parents and 26 DGCs that copy their parent's aire, in
    `aire` only. The index changed `communes_count` only (Crozes 10 → 11).
  - `03_generate_wiki.py --only` on the same names.
- **Residue, queued:**
  - Cadillac's partial commune ("Castets et Castillon …") follows a
    sentence-form proximity list that ends at its full stop. The commune's
    own name contains " et ".
  - About 27 prose fragments elsewhere in FR aire lists ("de la qualité",
    "l'aire parcellaire délimitée est celle …") are a different failure
    mode: a paragraph read past the end of its list.

**Overlap with another session.** The site was redeployed at 19:03 local
from the 14:34 build by the morning's session. That was a minute or two
before this stage 02 / 03 run, which touched only raw FR records and 85
`wiki/*.md` pages. Neither change reaches the live site before the next
build and deploy.

**Re-run result** (`fb-crozes-2026-10-30`, Batch API, $0.21). 02d
returned 15 facts at the regulator-text cap (7 / 4 / 3 / 1). The gate
kept 14 as supported and rewrote 1; en / es / nl were re-translated and
back-checked.
- **The 1989 claim is gone.** The first bullet now reads "la zone
  géographique compte 11 communes du département de la Drôme", which
  matches the drawn area.
- **The granite bullet** ties "entre Crozes-Hermitage et Serves-sur-Rhône"
  to the Rhône's gorge, as the cahier does. The audit's
  `feedback_recurrence` match on it (score 86) is the same topic, not the
  same error.
- Rollback, if needed: `scripts/rollback_terroir_facts.py --run
  fb-crozes-2026-10-30`.

### Found on the re-grade: grape roles across colour clauses

After the rebuild the card validator had one finding left on Crozes, graded
"misleads": Marsanne and Roussanne are shown only as accessory varieties.
Section V names them accessory for the red ("cépages accessoires : marsanne
B, roussanne B") and as the white's only grapes ("b) - Les vins blancs sont
issus des cépages marsanne B et roussanne B").

- **Failure mode, in two parts:**
  - The white clause has no role header, so `parse_grapes` read it as part
    of the red's accessory chunk.
  - A grape kept the first role it was read with, although the function's
    docstring promises "principal > accessory > observation".
- **Isolated or broader:** broader. A determinism control came first:
  replaying all 449 FR parent rosters with the old code reproduced the
  records on disk. With the fix, 39 parents change, plus 18 DGCs that copy
  them. No grape enters or leaves any roster; only roles move. The
  promotions were read one by one, and each comes from one of the record's
  own clauses:
  - the red grapes of Arbois and Côtes du Jura (accessory in the white);
  - Chinon's Chenin ("b) - Les vins blancs sont issus du cépage chenin B");
  - the white grapes of Saint-Joseph, Hermitage, Bandol, Cairanne,
    Corbières, Minervois, Côtes de Provence and Côtes de Bourg (where they
    had read as adaptation varieties);
  - the rosés' "cépages principaux" (Bourgogne's Pinot gris, Vacqueyras's
    Cinsault);
  - Gaillac's late-harvest Ondenc and Limoux's mousseux Mauzac.
- **Two promotions the first version made were wrong, and are excluded:**
  - A principal mention in a DGC's rows (Touraine's Chenin and Grolleau
    from the Amboise, Azay-le-Rideau and Mesland rows).
  - A variety in the convention add-on: "et des variétés … sous réserve de
    la signature … d'une convention". This is Bordeaux's Arinarnoa,
    Marselan, Touriga Nacional, Castets and Vidoc, which its rosé clause
    lists under "issus exclusivement des cépages".
- **Same function, older and worse: the 2026 Alsace cahier.** Its section
  V is a table whose white row carries no role label and follows the
  rosé's "variétés d'intérêt à fin d'adaptation … sous réserve de la
  signature … compétent." cell. Riesling, Gewurztraminer, Pinot gris,
  Muscat, Sylvaner and Pinot blanc were read as climate-adaptation
  varieties, and the live Alsace AOC card shows them so, with Pinot noir
  as its only principal grape.
  - Coteaux Varois en Provence had the same layout. Its whites read as
    adaptation varieties, and Clairette was lost ("concernés. clairette
    B").
  - **Rule:** an adaptation chunk ends at the full stop of its convention
    sentence, and an unlabelled row after it is the colour's roster.
    Côtes de Provence's "Toutefois, les cépages barbaroux Rs et calitor N
    sont autorisés en tant que cépages accessoires" carries its role after
    the names and is read as accessory.
  - **Effect:** 4 parents change (Alsace, Coteaux Varois, Côtes de
    Provence, Gaillac's primeur Gamay), plus 15 DGCs that copy them.
    Coteaux Varois gains Clairette; no other roster changes membership.
- **Fix:** all in `scripts/_lib/grape_lexicon.py`:
  - `_ROLE_PATTERNS` gains the unheaded colour clause;
  - `_role_chunks` cuts the adaptation chunk at its convention sentence;
  - `parse_grapes` promotes a grape to its strongest role, guarded by
    `_DGC_HEADING_RE` and `_ADDON_VARIETIES_RE`.
  - Tests are in `tests/test_fr_grape_roles.py`.
  - Two full FR stage 02 runs, each diffed field by field: `grapes` only
    (57, then 19 files), plus the index's grape count for Coteaux Varois.
- **Residue, queued in CURATOR_TODO:**
  - Saint-Mont's rosé lists "manseng B", which binds `manseng-noir`.
  - Coteaux Varois's "ugni Vins blancs blanc B" (the table's label column)
    still drops Ugni blanc.
  - The Klevener de Heiligenstein DGC inherits Alsace's full roster,
    though its cahier reserves it to Savagnin rose.
  - Touraine's section V is a table read in a jumble; its roles follow
    the jumble.

**After the rebuild.** The build's record diff showed 73 cards changed, in
grape roles only. The re-grades:
- **Crozes-Hermitage (fr):** "trust", no misleading finding. What remains is
  that the card shows one role per grape: Marsanne and Roussanne now read
  as principal, and the red's ≤ 15 % limit is not visible. That is a
  design question.
- **Alsace (en):** the trial-variety reading is gone. The judge raised four
  older findings, now queued:
  - Johanniter is lost to the table layout;
  - Savagnin rose is shown without its Klevener restriction;
  - the card cites "JORF 29 juin 2016" where the text read is the 2026 BO
    Agri version;
  - the lieu-dit mention is listed among the DGCs.
- **Coteaux Varois (en):** Clairette is back. Ugni blanc is still missing,
  and one bullet translates "fonds d'argile de décalcification" as
  "subsoils".

Reports: `tmp/validation/cards-fb-2026-10-30{b,c,d,e}.md`. Nothing from
this afternoon is committed or deployed.

## Review follow-ups (evening)

A review of this doc and its code checked every claim against disk and the
live site; all held. It raised these points, applied the same evening:

- **The gate and `wiki_part`.** `apply_verdicts` copied the fact whole on a
  rewrite, so a rewritten `both` bullet kept the verdict read on its old
  text, and outside a scoped re-run the post-pass would not have re-read it.
  The gate now drops the field on a rewrite; stage 04 shows the marker until
  the post-pass reads the new text (`tests/test_terroir_gate.py`).
- **German bullets.** The proper-noun shortcut reads any capitalised word
  inside a sentence, and German capitalises every noun. For `source_lang` de
  the shortcut is off and a word part needs two stems. Re-run on the AT / DE /
  CH caches (`review-2026-10-30`): no mark changed, Wien's is a number.
- **Sweetness lists that are labelling terms.** Castilla y León had taken
  Sweet / Semi-sweet from the analytical table's footnote "(*) Según la
  legislación vigente se podrán denominar: secos, semisecos, semidulces y
  dulces", the EU sugar-term rule restated for labelling, not a type list;
  Bailén's body has the same kind of sentence ("podrán emplearse las
  indicaciones seco, semiseco, semidulce y dulce"). A list its own sentence
  introduces that way is now skipped, read within one section body or title.
  Bailén keeps its styles: its heading "Vinos semisecos, semidulces y dulces"
  states them. A first version read the joined text and cost Méntrida its
  heading's list through "con mención Roble"; the record diff caught it, and
  "mención" is no guard word. Full ES run: styles changed on Castilla y León
  only (`tests/test_phase_c_styles.py`).
- **The geometry audit and partial communes.** The Mercurol token resolved to
  nothing in `audit_geometry_vs_text.py`; the bucket read OK through the CSV.
  The same held for 340 "X pour le seul territoire …" tokens in 142 FR records
  that predate today. The audit now resolves the commune (`fr_token`) and does
  not count it missing when its parcels fall under the drawn-in-part
  threshold. Crozes: no unresolved name; Tain-l'Hermitage still reads as
  missing because the Crozes parcels cover under 5 % of it, the audit's
  threshold, not a defect.
- **Lint and numbers.** The `productType` lint also catches subscript reads of
  the field. The `wiki_part` docstring said 120 where the run marked 119.
- **Done in a parallel session the same evening:** the per-colour role class
  behind the Crozes card's Marsanne / Roussanne (section "Found on the
  re-grade: grape roles across colour clauses" above; 73 cards, roles only,
  `tests/test_fr_grape_roles.py`). The change is not in the triage commit.
- **Built and deployed.** A deploy at 22:01 local (IndexNow fingerprints
  written 22:03; not run by either session working in the tree) carried the
  82 FR records' aire lists, the Crozes re-run, Castilla y León's styles and
  the parallel session's grape-role fix. A verification build at 01:02 on
  2026-10-31 produced byte-identical data bundles (the same hashed names);
  against the 14:34 build deployed at 19:03 it changes 74 records: 73 grape-
  role flips, Crozes' facts, Castilla y León's styles. The 01:02 build log
  shows no STALE pin and no wine record without grapes.

## Follow-up — grape names that lost their apostrophe

The live MCP answer for Manchuela listed "Muscat D Alexandrie".

- **Failure mode:** the FR roster reader splits words on letters only. An
  apostrophe acts as a separator, so the name it stores reads "muscat d
  alexandrie", and the pills and the corpus label follow it.
- **Isolated or broader:** broader. 161 French records carried such a name:
  - Muscat d'Alexandrie 93;
  - Pineau d'Aunis 50;
  - Roussette d'Ayze 43;
  - Len de l'El 25;
  - Nero d'Avola 12;
  - Rayon d'Or 11.
- **Fix, part 1:** `_with_source_apostrophes` restores the apostrophe the
  source writes between two of the name's words. The words passed to the
  matcher are unchanged, so no grape binding moves.
- **Fix, part 2:** Title Case now keeps an elided d' / l' lower case in
  both mirrors (the JS query core and `content_block.py`), so the pill reads
  "Muscat d'Alexandrie" rather than "Muscat D'Alexandrie". "Nero d'Avola"
  benefits too.
- **Re-extraction:** run in a clean worktree, because another session's
  uncommitted French role change sat in `grape_lexicon.py` and its French
  audit was reading the corpus. The worktree used the current code plus this
  fix, and a full run there, diffed against the corpus, changed the stored
  name on 161 records and nothing else (`_index.json` identical). Those 161
  files were then copied into the corpus.

**Deployed 2026-10-30, 22:00.**
- **Site:** `deploy.sh`; the CDN matched 60 / 60 sampled files and IndexNow
  received 819 changed pages.
- **MCP server:** release `d09c83d+dirty`, smoke test passed in all three
  modes. The live `get_appellation` for Manchuela lists "Muscat
  d'Alexandrie".
- **Also in this deploy:** the build carried the other session's pending
  French role rule (73 records: Arbois's poulsard, the Alsace rows,
  Crozes-Hermitage's marsanne and roussanne as principal). Its code in
  `grape_lexicon.py` is still uncommitted.

