# Visitor feedback triage — 2026-11-23

Queue: `scripts/feedback_report.py --range 30d`, rows since the 2026-11-20
triage (anything after 2026-11-17 22:00): 10 flags on 3 cards, 7 retracted,
one note, one name offered for credit, one e-mail-link click (no detail in the
report).

| flagged | aspect | locale · view | verdict |
|---|---|---|---|
| Côtes de Bordeaux Castillon, 2026-11-20 14:00, all retracted | boundary ×2, grapes | fr · parcels z12 | no defect: drawn from its own INAO parcels (`parcellaire-dgc`); the card validator trusts the roster |
| Coteaux champenois, 2026-11-22 15:00, **note**, credit «Tom Van Oppens» | boundary | nl · zone z6.3 | defect: the map draws the 635-commune aire géographique as the vineyard, and the card said no parcel delimitation exists |
| Meursault, 2026-11-22 21:00, all retracted | grapes ×2, facts, boundary | fr · footprint z11.8 | defect: Aligoté, Melon and Sacy shown as principal (convention varieties); and, found reading the cahier, the premier-cru climats' own colours were never read |

The note, verbatim: «de champagne grenzen zijn niet overal even correct, er
zijn ook wat percelen die wel interresant zijn. Maar het is moeilijk de
percelen te vinden, ze staan niet op het kadaster (in tegestelling to elk ander
frans wijngebied)» — the Champagne boundaries are not right everywhere; the
parcels are hard to find, they are not in the cadastre, unlike every other
French wine region.

## Coteaux champenois — boundary (fr AOC, commune union)

**What was drawn.** `aires-csv`: INAO's aires-communes rows for Coteaux
champenois, 635 rows, 617 communes of today; Champagne is drawn the same way.
`audit_geometry_vs_text.py` gives OK — the polygon is exactly INAO's rows.

**What the rows are.** INAO's own product pages say it: «L'aire Géographique
ou Champagne Viticole s'étend sur cinq départements … et concerne au total 635
communes» and «L'aire de production du raisin (ou aire délimitée parcellaire)
est répartie sur 319 communes au sein de l'aire géographique : 39 dans
l'Aisne, 63 dans l'Aube, 2 en Haute-Marne, 212 dans la Marne, 3 en Seine et
Marne» ([Champagne](https://www.inao.gouv.fr/node/9132),
[Coteaux champenois](https://www.inao.gouv.fr/node/9063), read 2026-11-23).
The map draws the zone in which the wine may be made — about twice the communes
the vineyard lies in. The cahier itself names sixteen communes where «aucune
parcelle n'a été retenue» (Brienne-le-Château, Corfélix, Verdon …); all sixteen are
in the rows and drawn whole. INAO's parcellaire layer has no Champagne row, so
the parcel area is not drawable from INAO — the visitor's «niet op het
kadaster». No public list of the 319 communes was found (INAO's product page
lists the 635; the 2017 CNAOV document on the INAO extranet resets connections
from outside France).

**And the card said something false.** The commune-union line read
"Approximate area — the union of the 617 commune(s) of the delimited area
(INAO); no parcel delimitation exists for this denomination." A parcel
delimitation exists (the cahier's section IV); INAO does not publish it.

**Failure mode:** *the commune-union disclosure says "no parcel delimitation
exists" for an AOC whose cahier sets one.* Sweep over the French records drawn
as a commune union (`aires-csv`, `dgc-village-override`, `communes`) whose
cahier writes «aire parcellaire délimitée»: Champagne, Coteaux champenois,
Cassis, Bellet, Corrèze, Duché d'Uzès, Rosé des Riceys, Champagne grand cru and
premier cru, and eight spirits (Armagnac, Fine Bordeaux, Fine champenoise, Marc
de Champagne, Ratafia de Champagne, Marc d'Alsace Gewurztraminer, Marc du Jura,
Rhum de la Martinique). Every IGP is right as it was (an IGP has no parcel
area); the `aires-csv-dgc` line already said "no parcel data available".

**Changed.**

- Stage 04 sets a sparse panel field `geom_parcels_unpublished` on such a
  record (`_fr_states_parcel_area`); both renderers then print
  `geom_approx_aires_union_parcels`: "Approximate area — the union of the {n}
  commune(s) of the geographical area (INAO); the specification delimits the
  vineyard parcel by parcel, but INAO does not publish that delimitation." (fr /
  es / nl in the catalogs).
- `scripts/_lib/appellation_notes.json`: a cited ⓘ note on `champagne` and
  `coteaux-champenois` — the map draws the Champagne viticole of the law of
  22 July 1927, 635 communes as INAO counts them, within which the wine is made;
  the grapes come from the parcel area, in 319 of them; INAO publishes no parcel
  layer, so the map cannot show which communes hold the vineyard. Sources: the
  INAO page and the cahier of each record.
- Not changed: the polygon. Drawing the vineyard needs a source (queued, below).

**Credited:** Tom Van Oppens (`scripts/_lib/contributors.json`).

### Second look, the same afternoon

A second read of this section (another session, read-only) held the facts and
corrected the fix:

- **The line was too wide.** It keyed on «aire parcellaire délimitée» anywhere
  in the cahier, and 7 of its 17 records were wrong or loose. Marc du Jura,
  Marc d'Alsace Gewurztraminer and Fine Bordeaux take their grapes from the
  parcel areas of the wine AOCs, which INAO publishes. Armagnac, Corrèze and
  Duché d'Uzès identify parcels on application («procédure d'identification»,
  «parcelles identifiées selon des critères») and delimit none, like the ciders,
  Floc and Pineau that kept the old line. Rhum de la Martinique has an area of
  its own, which INAO publishes as a resource of its own in the parcellaire
  dataset (`2020-11-25-rhum-de-martinique.zip`). The build doesn't read that
  file.
- **Fixed:** `scripts/_lib/fr/parcel_area.py` keeps a record's own parcel area,
  one INAO's committee approved with its plans deposited at the town halls. It
  excludes an identification and the areas of other appellations.
  `PUBLISHED_APART` holds the rum, cited. The panel field is now
  `geom_parcel_area`:
  - `unpublished` → "…; the specification delimits the vineyard parcel by
    parcel, and that delimitation is not in INAO's published parcel data". It
    is reworded: INAO deposits the plans at the town halls, so "INAO does not
    publish it" was loose. It covers Champagne, Coteaux champenois, grand cru,
    premier cru, Rosé des Riceys, Cassis, Bellet and the three Champagne
    spirits.
  - `apart` → the union alone ("…of the geographical area (INAO)."), for the rum
    until its parcels are drawn.
  - The other six are back on the old line. `tests/test_fr_parcel_area.py`;
    `--shell-only` re-emit; 2,527 tests pass.
- **The 319 communes are public, though not where we looked first.**
  `extranet.inao.gouv.fr` resets every connection, from a French VPN and a
  Belgian IP, through curl, headless Chromium and Boris's Chrome: it is closed
  to the public. INAO's product page lists the 635 flat, and the cahier names no
  list (its 16 «aucune parcelle» communes are all in INAO's rows, not 15).
  INAO's parcel release of 2026-11-09 still has no Champagne, Cassis or Bellet
  row. Boris pointed at the product page's map. Its «Télécharger le json» is
  the aire géographique (7,805 km²), but the «ici» under it leads to INAO's
  portal of official delimitation plans: a public Nextcloud share
  (`inao.cognix.cloud/index.php/s/AfChDpBNxYPolzH`, readable over WebDAV).
  - Its `inventaire_etat_de_la_delimitation.xlsx` gives every (appellation,
    commune) pair a status. For Champagne, exactly **319** communes have
    «Délimitation parcellaire attendu: oui» (297 plan published, 31 in
    preparation) and 301 have «Aucune parcelle classée». Coteaux champenois has
    277. The union of the 319 is ≈ 3,600 km².
  - `AIRE_PARCELLAIRE/par_appellation/AOC_CHAMPAGNE/` holds the plans, scanned
    in 2009, one per cadastral sheet: 2,052 sheets in 299 commune folders.
  - 85 % of the sheet ids still exist in Etalab's cadastre; 29 communes match
    none (their cadastre has been redrawn since). A union of the matched sheets
    is 802 km² and holds 79 % of IGN's vines. It is too fragile to draw from.
- **IGN's vineyard layer matches INAO's split.** BD TOPO `zone_de_vegetation`,
  nature «Vigne», inside the aire:

  | | INAO | IGN «Vigne» |
  |---|---:|---:|
  | communes holding vineyard (IGN: ≥ 0.5 ha) | 319 | 313 |
  | Aube | 63 | 63 |
  | Marne | 212 | 210 |
  | Aisne | 39 | 36 |
  | Seine-et-Marne | 3 | 3 |
  | area | 35,280 ha delimited | 33,156 ha |

  12 of the 16 «aucune parcelle» communes have no vines in the layer, and the
  other 4 have under 0.5 ha. The growers' syndicate stopped the 2003 revision
  of the area on 2026-10-21, so the 635 / 319 stand.
- **Rosé des Riceys.** Its aire géographique is the 8 communes drawn: 1° a)
  harvest in Les Riceys, 1° b) vinification in 7 more. Its vines are in Les
  Riceys alone (2°). It follows the Champagne decision: unchanged if the aire
  géographique stays, the vines of Les Riceys under the land-cover option.

### Decision (a): the communes holding the parcel area

Boris chose (a) the same day.
- **Champagne:** drawn as the 321 communes of today the inventory lists «oui»
  (a commune nouvelle counts when any of its rows reads oui). None of the
  cahier's 16 «aucune parcelle» communes is among them. The new commune union
  is ≈ 3,600 km², against 7,803 for the aire.
- **Coteaux champenois:** drawn as Champagne's list. Its cahier's section IV
  is Champagne's word for word, and INAO's page gives both 319. The
  inventory's own list for it (278, like its plan folders) lacks 17 Côte des
  Bar communes. The ⓘ note says so.
- **Rosé des Riceys:** drawn as Les Riceys, from its cahier's IV 2°.
- **Card line:** "Approximate area — the union of the N commune(s) that hold
  the delimited parcel area, per INAO's inventory of delimitation plans; the
  parcels themselves are not in INAO's published parcel data". The card gets
  a Sources row, «Official delimitation plans (INAO)».
- **Code:** stage 00 fetches the inventory, stage 04 draws the list
  (`_lib/fr/plan_inventory.py`, `_lib/fr/parcel_area_communes.json`), and the
  geometry-vs-text audit reads the same list.
- **Not changed:** the three Champagne spirits keep the aire géographique,
  where they may be made.
- **Cross-check of the whole corpus:**
  [docs/prompt-inao-plan-inventory-crosscheck.md](prompt-inao-plan-inventory-crosscheck.md)
  is a prompt for it.

**Build and checks.**
- Full stage 04 against the build before the decision (`diff_records.py`):
  three records changed, in area, commune count and sources only.
  - Champagne and Coteaux champenois: 617 → 319 communes of today (INAO's own
    figure; two of the inventory's 321 codes are former communes inside
    listed communes), area ×0.46, and the plans portal among the sources.
  - Rosé des Riceys: 8 → 1 commune, area ×0.23.
- `audit_geometry_vs_text.py`: OK on all three.
- `audit_geometry_outliers.py --strict`: two new detached groups, both parcel
  area. One is the Vitryat, which the cahier's section IV names (Bassu,
  Vavray-le-Grand, Vitry-en-Perthois …); the other is Montgueux, west of
  Troyes. Both are whitelisted with that evidence; the audit then passes.
- `audit_geometry_overlaps.py --strict`: no suspicious sliver.
- `pytest`: 2,556 passed.
- Card validator (en, three cards): all "trust", no area finding. The rest is
  known or queued: Champagne's grand cru / premier cru as AOC entries, the
  regulator's French sub-denomination heading, Coteaux champenois' fact
  wording. One new omission: «Coteaux champenois» may be followed by the name
  of the commune the grapes come from (cahier, labelling).

## Meursault — grapes (fr AOC, parcellaire)

**Card validator** (`audit_cards_llm.py --only meursault --locale fr`,
"caution"): «Aligoté, Melon and Sacy are shown as principal varieties
alongside Chardonnay and Pinot Blanc». The cahier (BO Agri, 11 juin 2026):

> a) - Les vins blancs sont issus des cépages suivants :
> - cépages principaux : chardonnay B et pinot blanc B.
> - et les variétés aligoté B, melon B, sacy B, sous réserve de la signature
>   entre l'INAO, l'ODG, l'opérateur habilité concerné et l'opérateur-vinificateur
>   d'une convention conforme à la convention cadre approuvée par le comité
>   national compétent.

capped at 10 % of the encépagement and 1 ha per holding (2°). The FR roster
reader gave a variety after "et les variétés …" the role of the header before
it, so after "cépages principaux" they were principal (and César, after the red
clause's accessories, accessory). The retracted grapes flags pointed at a real
defect.

**Failure mode:** *a variety admitted only under the INAO convention cadre (the
mechanism of Alsace's «variétés d'intérêt à fin d'adaptation») takes its
clause's role.* Sweep over the 365 French parents with a section V: 24 such
clauses in 16 parents — Meursault, Blagny (César), Arbois, Côtes du Jura,
L'Étoile, Macvin du Jura, Bordeaux, Bordeaux supérieur, Médoc, Haut-Médoc,
Listrac-Médoc, Buzet, Languedoc, Saint-Chinian, Mâcon, Viré-Clessé; principal
in 9 of them (the four Médoc-side rosters' Arinarnoa, Castets, Marselan,
Touriga Nacional; Macvin's Béclan, Enfariné, Franc noir, Gamay; Buzet's
Floréal, Voltis …), accessory in the rest.

**Fixed** (`grape_lexicon.parse_grapes`): such an add-on — "et des / les / la /
de la variété(s) …" up to the end of its "sous réserve de la signature … d'une
convention …" sentence — is read as `observation`, the card's "Varieties of
interest", as Alsace's VIFA already are; a singular "et la variété" counts only
when the convention sentence follows; a two-column table label inside the
phrase ("et les AOC « Languedoc » (Vins rouges) variétés suivantes") is
allowed. French stage 02 against a snapshot: **75 records changed, `grapes`
only** — the 16 parents and the 59 sub-denominations inheriting their roster.
Old and new reader compared on every parent: the 16, nothing else.
`tests/test_fr_grape_roles.py` (the Bordeaux expectation of "accessory" became
"observation").

### Found on the same cahier: the premier-cru climats' colours

The validator's second finding (sub-denomination omission): Meursault's section
III gives each climat its colour — «La Jeunellotte» Vins tranquilles blancs,
«Charmes» blancs ou rouges, «Côte de Beaune» rouges — and every climat card
showed red and white. Two causes in `dgc_rules`:

- `dgc_keys` stripped the parent's name, not the mention: "Meursault premier
  cru La Jeunellotte" answered to "premier cru la jeunellotte", never to the
  row's «La Jeunellotte» — no Burgundy premier-cru climat ever matched its row;
- "Meursault ou Meursault Côte de Beaune" answered to "meursault", the parent's
  own name, and took the parent's row (white) beside its own (red only).

**Fixed:** a climat key without its «premier / grand cru» mention; stage 02
drops the parent's own keys from a DGC's (`_apply_dgc_rules`). French stage 02
against a snapshot: **61 records changed**, 22 in their colours and 23 in their
roster (the existing colour-clause drop), every one read against its row:
Meursault ten white-only climats and Côte de Beaune red; Puligny-Montrachet
Hameau de Blagny, La Garenne, Sous le Puits white; Pernand-Vergelesses Clos
Berthet, Sous Frétille, Village de Pernand white; Ladoix Le Rognet et Corton,
Les Grêchons et Foutrières white, Les Buis, Les Joyeuses red; the Côte de
Beaune DGCs of Chorey-lès-Beaune, Ladoix and Saint-Romain red. Morey-Saint-Denis
premier cru Monts Luisants now carries Aligoté — its cahier: «Les vins blancs
provenant de parcelles de vigne situées dans le climat « Monts Luisants » sont
issus des cépages aligoté B, chardonnay B et pinot blanc B». The other 38
changed in `dgc_rules` only (Vin de Corse Figari lost a spurious "types: own"
the parent's alias had given it; its styles are unchanged).
`tests/test_fr_dgc_rules.py`.

Sweep of every «premier / grand cru» climat against a one-line row of its
parent's colour table: 55 rows found, 52 match now; three do not —
Ladoix En Naget (blancs) and Bois Roussot (rouges), Meursault Blagny (blancs):
their rows share lines with the table's wrapped left label ("- complétée par la
mention « premier cru » et suivie du nom …"), and the table reader pairs them
with the rows beside them (queued).

## Castillon and Meursault — boundary (both retracted)

- Côtes de Bordeaux Castillon: `parcellaire-dgc`, its own INAO parcels at z12;
  the card validator: "trust" (one dropped hedge, «souvent», in an inherited
  fact).
- Meursault: geometry-vs-text OK, no parcel gap, footprint 1.38× its parcels,
  0.2 % bridged.

## Build and re-check

Full stage 04 against the morning's build (`diff_records.py`): **88 records
changed, all French, in `grapes` and `styles` only** — the two stage-02 changes
above and nothing else. `pytest`: 2,522 passed. Card validator on seven changed
cards (en): the Côte de Beaune DGC, La Jeunellotte, Ladoix Les Buis, Haut-Médoc
and Monts Luisants "trust"; Coteaux champenois's area finding gone. Two
findings remained:

- Coteaux champenois, terroir fact (misleads): "the marly Vitryat" for «le
  Vitryat marnais» — the Vitryat in the Marne département. Isolated (the three
  Champagne spirits keep «Vitryat marnais» verbatim); fixed by the translation
  back-check on that record (`02e_verify --lang en --only coteaux-champenois
  --refresh`, run `triage-2026-11-23`): "the Vitryat in the Marne".
- Champagne, sub-denominations (misleads): the card lists «Champagne grand cru»
  and «Champagne premier cru» as AOC (PDO) entries, while the cahier makes them
  mentions («le nom de l'appellation peut être complété par les mentions …»).
  INAO's referentiel lists them as denominations; this predates the triage and
  is the case Boris settled for «Alsace suivi d'un nom de lieu-dit» on
  2026-11-07 (kept, with a note) — queued.

## Queued (CURATOR_TODO)

- The inventory's Coteaux champenois list (278) is shorter than the
  delimitation its cahier sets: a question for INAO.
- The cross-check of the whole French corpus against INAO's inventory and
  plans (the prompt above).
- Rhum de la Martinique: draw it from INAO's own parcel resource.
- The three climat rows the table reader merges (Ladoix En Naget, Bois Roussot,
  Meursault Blagny).
- Champagne grand cru / premier cru: a note saying the cahier treats them as
  mentions of the AOC (the Alsace lieu-dit precedent).
- The validator's smaller findings: Castillon's dropped «souvent» (inherited
  fact); on Coteaux champenois the élevage sentence narrowed to the white
  wines, the reds given the rosés' description, an invented water-reserve link
  — feedback-sidecar entries for the next scoped re-run.
