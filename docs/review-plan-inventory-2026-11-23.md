# INAO's delimitation-plan inventory and plans against the French corpus — 2026-11-23

A read-only cross-check of every French record against INAO's portal of official
delimitation plans (https://www.inao.gouv.fr/portail-plans-delimitation). Nothing in
`wiki/`, the geometry, the cards or any override was changed. The audit is
[scripts/audit_plan_inventory.py](../scripts/audit_plan_inventory.py) (logic in
[scripts/_lib/fr/plan_inventory_audit.py](../scripts/_lib/fr/plan_inventory_audit.py),
WebDAV listing in [scripts/_lib/fr/plans_portal.py](../scripts/_lib/fr/plans_portal.py),
tests in [tests/test_plan_inventory_audit.py](../tests/test_plan_inventory_audit.py)).
The full output is `tmp/validation/plan-inventory-2026-11-23.{md,json}`.

    .venv/bin/python scripts/audit_plan_inventory.py [--only SLUG …] [--json PATH] [--strict] [--fetch] [--all]

It reads the share's listing cache (`raw/cache/inao-plans-portal/`, 1,265 listings, about
12 minutes to rebuild at 0.5 s a request), so a re-run is offline and takes 25 s;
`--fetch` lists what the cache lacks. `--strict` exits 1 on CONFLICT-OURS, and does today.

## What was compared

| source | vintage | what it says |
|---|---|---|
| `inventaire_etat_de_la_delimitation.xlsx` | last modified 9 May 2026; 355,274 rows, 1,783 (sign, appellation) pairs | per (appellation, commune): a parcel delimitation expected (oui / non / «identification parcellaire»), the plan's state, a revision under way |
| the scanned plans, `AIRE_PARCELLAIRE/par_appellation/` | 621 folders, all AOC, one per **denomination** (every grand cru and premier-cru climat has its own); 9,647 commune folders; sheets dated 1998 to 2026 | the legally binding delimitation |
| INAO's aires-communes rows | CSV in `raw/inao/`, with `aires_supplements.json` | the aire géographique |
| the parcellaire shapefile | release of 2026-10-19 (coverage index; 2026-05-11 and 2026-09-28 for comparison) | what a parcellaire record is drawn from |
| the cahier | the build's `raw/inao/cahier-extracted/`, the zone text searched name by name | the delimitation — it wins where it is explicit |

The build on disk (`aocs.en.2d57ea988b.js`, 15:35 today) predates the parcel-area table of
this morning's triage for Champagne, Coteaux champenois and Rosé des Riceys; the audit reads
the table, as the next stage-04 build will.

### Binding

1,515 of the 1,541 AOC / IGP records bind to an inventory appellation: 1,510 by name,
2 by an " ou " alias of the record ("Alsace ou Vin d'Alsace" → «alsace»), 1 by an alias of
the inventory name ("Blagny" → «blagny ou blagny côte de beaune»), and 2 by a cited pin in
the audit ("La Livinière" → «minervois-la livinière», the former name; "Marc d'Alsace
Gewurztraminer" → «marc d'alsace», the referentiel's appellation column). The sign is part
of the key: «calvados» is both the AOC spirit and the IGP wine. A French cider AOC is stored
with `kind` IGP, so the sign comes from `signe_fr`. The 34 IG spirits are outside the
inventory, which lists AOC and IGP only.

**Records with no inventory appellation (26).**
- Eight Chablis premier-cru climats: Beauroy, Berdiot, Chapelot, Côte de Bréchain, Côte de
  Léchet, Côte de Vaubarousse, Montée de Tonnerre, Pied d'Aloup. The inventory lists 33
  other climats.
- IGP Île-de-France and its five sub-denominations, IGP Lorraine, Isère Trièves, Var
  Correns, the two Pineau des Charentes island denominations, Rasteau tranquille, the
  Fiefs Vendéens parent (its DGCs are listed), Sable de Camargue, Euskal Sagardoa and
  Rhum de la Martinique.
- Montpeyroux, which is newer than the inventory.
- The parent `calvados-domfontais`: SIQO's misspelt appellation row («Domfontais»). Its
  one denomination row, `calvados-domfrontais`, takes the inventory entry, so the corpus
  carries the same product twice, as a parent and as a sub-denomination.

**Inventory names with no record.**
- «pouilly-loché / pouilly-vinzelles complété par une dénomination de climat», and the
  retired «côtes de blaye» (AOC, 35 communes «oui, plan disponible»; its EU cancellation is
  pending, CURATOR_TODO).
- «blaye», which SIQO rolls into Côtes de Bordeaux Blaye.
- Food AOCs and IGPs, which have plan folders of their own: Béa du Roussillon, Pomme de
  terre de l'Île de Ré, Taureau de Camargue.

**Plan folders.** 617 of the 621 bind:
- 544 by name, with the number the sheets carry agreeing.
- 69 by name alone. A premier-cru climat's sheets carry its premier cru's number:
  Ladoix's eleven climats carry 665.
- 4 by the number alone: `AOC_RASTEAU` holds the still wine's sheets (2899),
  `AOC_RASTEAU_VIN_DOUX_NATUREL` the VDN's.

## How a finding is bucketed

- **CONFLICT-OURS**: two INAO sources agree against what we draw or say, or the cahier
  does.
- **CONFLICT-INVENTORY**: the inventory alone against us and another source.
- **UNDETERMINED**: nothing settles it.
- **INTERNAL**: INAO's inventory against INAO's own plan folders.
- **REVISION**: a revision under way, a plan newer than the cahier, or a plan much older
  than it.

A name in the cahier counts only as a whole list item under its own département, with
`audit_aires_vs_cahier.classify` and its exclusion-clause rule. «Saint-Vérand» in the
Saône-et-Loire list is not Saint-Vérand (Rhône); «Ponteilla en partie (sections A1, A2 …)»
and «Le Bignon (partie)» are partial, though stage 02's list reader keeps them as whole
communes.

**Two departures from the brief, and why.**
1. *For check 1a the appellation's own plan corroborates the inventory.* The inventory's
   «oui» is not specific to one appellation: the same 20 Pyrénées-Atlantiques communes, the
   Jurançon / Béarn area, read «oui, plan disponible» under every product covering them,
   among them Ossau-Iraty (a cheese), Jambon de Bayonne, Volailles du Béarn and all six
   Comté Tolosan IGPs. So a missing parcel area is CONFLICT-OURS only when the appellation's
   folder for that commune holds plan sheets. An empty or absent folder leaves it
   UNDETERMINED.
2. *A plan newer than the cahier routes a contradiction to REVISION.* Ladoix's shapefile
   rows reach Magny-lès-Villers, which neither the cahier of 2011 nor INAO's rows name. The
   plan shows why: «Délimitation définitive approuvée par décision du comité national … en
   sa séance du 12/02/2026», ref. 2026-CN113.

## What the inventory is (useful before trusting it again)

1. **The «oui» bleeds across products in a commune.** See the Jurançon block above; an IGP
   has no parcel area, yet six Comté Tolosan IGPs and Côtes de Meuse read «oui».
2. **Its commune lists follow INAO's commune table, not the cahier.** Communes pinned from a
   newer cahier are missing from the inventory exactly as from the CSV:
   - Cévennes' 40 Lozère communes,
   - Maures' 3,
   - Côtes de Thau's 9,
   - Calvados' 20.

   So when the inventory and the CSV agree, that is not two independent sources. The
   telling case is the inventory and the cahier together against the CSV.
3. **It lists the aire géographique, vineless communes included.** Of the 3,308 aire
   communes the 161 parcellaire records draw no parcel in, the inventory marks 3,271 «non»,
   15 «oui, plan disponible», 1 «en cours» and leaves 21 out. The parcellaire-gap queue in
   CURATOR_TODO is therefore almost entirely aire communes with nothing to draw.
4. **IGP sub-denominations carry their parent's whole aire** (Comté Tolosan Bigorre: 4,388
   rows, as the parent).
5. **A name shared by two products of one sign is one appellation.** Valençay (wine and
   cheese, both AOC) is mixed this way; Haute-Marne likely is too. The audit reports such a
   name once, as UNDETERMINED.
6. **Codes lose their leading zero and mix communes of today with former communes**: 13,257
   code differences are only a merger. Names are mojibake.
7. **The plans.** Most are PDFs (4,265 sheets against 443 TIFs). File names carry the SIQO
   `id_denomination_geo` (`…_AOC_0055_DF.tif`, Champagne's 55); `…_M_TA_DF` is a
   modification's assemblage. Some folders are empty (Bourgogne aligoté's Chânes and
   Chasselas). Some carry a note: `Avertissement_84129.txt` in Châteauneuf-du-Pape's Sorgues
   folder says to disregard the Côtes du Rhône delimitation drawn on the same 1999 sheets.

## Counts

| bucket | 1a | 1b | 1c | 2a | 2b | 3 | 4 | 5a | 5b | 5c | 6 | total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CONFLICT-OURS | 9 | | | | | 25 | | | | | 1 | **35** |
| CONFLICT-INVENTORY | 3 | 23 | | 4 | | 30 | | | | | | 60 |
| UNDETERMINED | 5 | | | 1 | 4 | 115 | | | | | 11 | 136 |
| INTERNAL | | | | | | | 55 | | | | | 55 |
| REVISION | 1 | 1 | 717 | | | | | 487 | 72 | | | 1,278 |

The checks:
1. Parcellaire records against the inventory.
2. Commune unions: the card's parcel line, and the parcel area's share of the communes
   drawn.
3. The aire.
4. Plans against the inventory.
5. Dates.
6. Sub-denominations.

Check 5c (parcel rows an earlier shapefile release had) found nothing once the 2026-05-11
cache's two-code fields were split («49078,49115»). The carry-forward entries cover
Saint-Sardos and Languedoc Montpeyroux.

## CONFLICT-OURS (35), by failure mode

### A. A parcel area INAO's shapefile lacks — the map draws the record without it (9 findings, 9 records, 5 communes)

Each case has four things in common:
- the inventory marks the commune «oui, plan disponible»;
- INAO's rows (or the cahier) put it in the aire;
- the appellation's own folder holds sheets;
- the 2026-10-19 shapefile has no parcel of the record there.

| record(s) | commune | coverage | plan | evidence |
|---|---|---|---|---|
| `chateauneuf-du-pape` | Sorgues (84129) | Côtes du Rhône rows only | 2 sheets of 1999 (`84129-0H01`, `-0I01`), legend: «seules sont incluses dans l'aire de production des vins à appellation d'origine contrôlée : CHATEAUNEUF DU PAPE, COTES DU RHONE — les parties : quadrillées … approuvé par décision de l'I.N.A.O. le 11.02.93» | cahier IV 1°: «Bédarrides, Châteauneuf-du-Pape, Courthézon, Orange, Sorgues» |
| `lirac` | Saint-Laurent-des-Arbres (30278) | no row for any AOC | 12 sheets of 13 Sept 2024 | cahier IV 1°: «Lirac, Roquemaure, Saint-Geniès-de-Comolas, Saint-Laurent-des-Arbres» |
| `madiran`, `pacherenc-du-vic-bilh`, `bearn` | Mont-Disse (64401) | no row for any AOC | 4 sheets of 6 Aug 2021 | named in all three cahiers' lists |
| `bourgogne` | Préty (71359) | other AOCs' rows | 3 sheets of 2010 | Bourgogne IV 1° a), Saône-et-Loire list |
| `anjou`, `cremant-de-loire`, `rose-de-loire` | Plaine-et-Vallées / Oiron (79196) | no row for any AOC; INAO's rows lack it too | 12 sheets of 9 June 2011 | «Plaine-et-Vallées (pour le seul territoire de la commune déléguée d'Oiron)» |

**Isolated or broader?** One failure mode, *a delimitation INAO has plans for and has not
put in the published shapefile*, with two forms: the commune has no row for any AOC
(Saint-Laurent-des-Arbres, Mont-Disse, Oiron), or rows for its neighbours only (Sorgues,
Préty). These 5 communes are all of it. The other 9 (record, commune) pairs the inventory
marks «oui, plan disponible» have empty folders (UNDETERMINED below), and the rest of the
3,308-commune gap queue reads «non». Côtes du Rhône already carries Saint-Laurent-des-Arbres
as a gap fill; Lirac, the appellation whose own plans those are, does not.

### B. INAO's rows behind the cahier on records the rows draw (10 findings, 9 records)

Here the inventory and the cahier name the commune, INAO's rows lack it, and the record
is a commune union, so the polygon lacks the ground.

| record | communes | cahier / rows | note |
|---|---|---|---|
| `whisky-breton-ou-whisky-de-bretagne` | 105 Loire-Atlantique communes (Abbaretz, Ancenis, Assérac, Avessac, Batz-sur-Mer …) | cahier 19 May 2021 / AOC CSV, four Breton départements, 1,320 communes | «Loire-Atlantique en partie : Communes en totalité situées au nord de la Loire : Abbaretz, Ancenis, …»; 2 more in part (Indre, Nantes). **Not in CURATOR_TODO, and `audit_aires_vs_cahier.py` cannot see it**: stage 02 resolved none of the record's names |
| `ardeche` | Vallées-d'Antraigues-Asperjoc (07011) | cahier 9 Nov 2020 / rows of 6 Dec 2021 | the cahier writes «Vallées- d'Antraigues-Asperjoc» (line break). The CURATOR_TODO note "the CSV keeps the pre-merger codes" is wrong: IDA 1977 carries neither 07011 nor Asperjoc 07016, while Comtés Rhodaniens and Méditerranée carry 07011 |
| `comtes-rhodaniens` | 13 (Pourchères, Saint-Cierge-la-Serre, Saint-Laurent-du-Pape …) | cahier 14 Apr 2021 / rows of 6 Dec 2024 | rows newer than the cahier: look for a newer cahier first |
| `pays-de-brive` | Astaillac, Saint-Viance, Segonzac, Ussac | cahier 25 Sept 2020 / rows of 5 Sept 2025 | rows newer: look for a newer cahier first (already in CURATOR_TODO) |
| `atlantique` | Saint-Christophe (16306) | cahier 26 Nov 2025 / rows of 9 Nov 2015 | the cahier is newer: pin |
| `coteaux-de-narbonne` | Armissan, Coursan, Fleury (+3 in part) | cahier 31 Jan 2023 / rows of 2012 | cancelled IGP; already queued |
| `haute-vallee-de-l-aude` | Cassaignes (11073); row La Cassaigne (11072) where the cahier lists Cassaignes | cahier 2011 / rows of 2012 | the neighbouring-code mode of Marc des Côtes du Rhône (Gignac for Gigondas); Alaigne is in part (cadastral parcels listed) |
| `urfe` | Perreux, Roanne, Sail-les-Bains, Saint-Martin-d'Estréaux | PNOCDC draft (`extranet…/PNOCDCIGPUrfé.pdf`) / rows of 2015 | «Canton de Perreux : Perreux, Montagny …»; wait for the BO publication (queued) |
| `pommeau-de-bretagne` | Saint-Grégoire (35278) | cahier 22 Mar 2022 | «l'aire géographique constituée par … l'ensemble des communes incluses dans la zone de production … et par le territoire des communes suivantes … Département de l'Ille et Vilaine : Saint-Grégoire» — the processing area. `eau-de-vie-de-cidre-de-bretagne` has the same commune as `not_drawn`; decide the two the same way |

**Isolated or broader?** The failure mode, *INAO's rows lag the cahier*, is the one
`audit_aires_vs_cahier.py` already queues for 28 wines (CURATOR_TODO "the same audit over
the wines"). Seven of these nine are queued there or in the rows above it (Atlantique,
Comtés Rhodaniens, Coteaux de Narbonne, Haute Vallée de l'Aude, Pays de Brive, Urfé,
Ardèche). Two are new: Whisky breton, and Pommeau de Bretagne's Saint-Grégoire, a pinned
record whose pin lacks this commune. In all nine the inventory adds a second INAO voice on
the cahier's side.

### C. INAO's rows behind the cahier on parcellaire records (15 findings) — no polygon moves

The rows draw only the village layer and feed the text audits:
- Bourgogne: 60 Rhône communes, IV 1° a) «Département du Rhône : Alix, Anse …»; the
  inventory marks them «non», no parcel there.
- Côtes de Provence: 16 Bouches-du-Rhône communes.
- Languedoc: the five Picpoul communes of 1° b), white wines.
- Vin de Savoie: 6.
- The Muscadets: 2 + 2 + 1.
- Gros Plant: 3.
- Côtes du Roussillon Villages: Saint-Jean-Lasseille, Terrats.
- Ventoux: 2.
- Cheverny: Chambord.
- Côtes d'Auvergne: Mur-sur-Allier.
- Crémant de Bourgogne: Sainte-Marie-la-Blanche.
- Crémant de Loire: Saint-Georges-sur-Loire.
- Roussette de Savoie: Marin.

All are already in `audit_aires_vs_cahier.py`'s NEW / UNCLEAR list. Low priority.

### D. A hand-curated village override that misses a commune and over-draws others (1 finding; read by hand: 2 records)

`champagne-grand-cru` is drawn from `DGC_VILLAGE_INSEE` (16 codes). The cahier lists 17
grand-cru communes: «… Le Mesnil-sur-Oger, Oger, Oiry …». The override's comment, «51367
Le Mesnil-sur-Oger (now also covers former Oger)», is wrong. INSEE's movements put Oger
(51411) into **Blancs-Coteaux** (51612) on 1 January 2018, with Vertus, Gionges and
Voipreux, and the inventory marks Blancs-Coteaux «oui» for the grand cru. So the grand-cru
polygon lacks Oger. Oger keeps an outline of its own (a commune déléguée in
`communes-associees-deleguees.geojson`).

Reading the override against the list shows the same failure the other way: a commune
nouvelle drawn whole where the list names one of its former communes.
- **Grand cru:** Aÿ-Champagne (51030) includes Bisseuil and Mareuil-sur-Aÿ, which are
  premier cru only; Val de Livre (51564) includes Tauxières-Mutry, also premier cru only.
- **Premier cru:** Blancs-Coteaux is drawn whole, Gionges included, which the list does not
  name; Val-des-Marais (51158) is drawn whole for Coligny.

This is the 2026-11-14 rule that a commune named in a list is the commune of the list's
day (`seat_communes.narrowed_seats`), which the override path bypasses. **Broader?** 13 of
the 39 village overrides draw at least one commune nouvelle whole. Champagne grand cru and
premier cru are wrong. The 11 IGP sub-denominations (Aude, Coteaux de l'Ain, Isère, Pays
d'Hérault) need their own lists read.

## Other buckets — what matters

- **REVISION.**
  - Ladoix / Magny-lès-Villers: an extension approved on 12 February 2026; the build's
    cahier is of 2011. Look for a newer cahier on BO Agri.
  - 717 records (2,521 commune rows) are drawn from parcels where the inventory says a new
    plan is «en cours d'élaboration», and 487 records (4,143 rows) carry «révision en
    cours». Nearly all are Burgundy premier crus (Chassagne-Montrachet, Montagny, Beaune,
    Givry, Mercurey …): INAO is redrawing them on the 2023 cadastre, as the Ladoix plan
    states.
  - 72 records' sampled plans are 10 or more years older than their cahier.
  - The inventory's Champagne revision flag predates the stop of 21 October 2026.
- **CONFLICT-INVENTORY.**
  - Cassis and Rosé des Riceys: the cahier sets a parcel area, the inventory none (known).
  - Comté Tolosan and Côtes de Meuse: the Jurançon bleed.
  - 23 parcellaire records where the shapefile draws parcels in a commune the inventory
    marks «non»: the Saumur family (Le Coudray-Macouard, Montsoreau, Parnay, Varrains,
    Berrie), Pouilly-Fuissé premier cru (all four communes), Touraine Azay-le-Rideau and
    Mesland, three Côtes du Rhône Villages DGCs.
  - Roussette de Savoie Frangy «oui» in Thonon-les-Bains.
  - The inventory lacks every commune we pinned from a newer cahier (Cévennes, Maures,
    Côtes de Thau, Calvados).
- **UNDETERMINED.**
  - Empty plan folders for «oui, plan disponible» communes: the three Bourgogne regionals in
    Chânes and Chasselas, Côtes de Bordeaux in Donnezac, Crépy in Ballaison and Loisin.
  - Marc d'Alsace Gewurztraminer: 117 «oui», the Alsace AOC parcel area its grapes come
    from (the second look of this morning stands).
  - Côtes de Provence Fréjus: parcels in Callas and Trans-en-Provence only, of the 8
    communes drawn; plans for both.
  - Precision candidates, sub-denominations with their own plans drawn as a whole commune:
    Beaujolais Chânes, Beaujolais Saint-Symphorien-d'Ancelles.
- **INTERNAL.**
  - `AOC_VOLNAY_PREMIER_CRU` holds Flagey-Échezeaux and Vosne-Romanée folders whose sheets
    carry 1277, Vosne-Romanée premier cru.
  - `AOC_ROMANEE-SAINT-VIVANT`'s sheets carry 1084, Romanée-Conti.
  - Sainte-Croix-du-Mont has two folders, one holding only a modification's assemblage.
  - 48 records with folders the inventory does not mark «plan disponible» (Côtes de
    Bordeaux, the Die appellations, Rosé de Loire's Touraine communes).
  - Montpeyroux's sheets carry 2951, INAO's number for the AOC, against our provisional
    `p23354`.

**Champagne-style candidates (check 2b).** No other parent drawn as a commune union has its
parcel area in a small share of what it draws. The only records with a parcel area in the
inventory are Champagne and Coteaux champenois (now drawn from it), Bellet (1 of 1) and
Marc d'Alsace (117 of 117). The low shares are IGPs (the bleed) and Côtes de Provence
Fréjus.

## What could not be checked

- **Plan contents beyond the five folders opened** (Ladoix / Magny, Châteauneuf-du-Pape /
  Sorgues sheet and legend; the rest read through listings and dates). Whether a hatched
  area on a 1999 sheet still matches the parcels was not tested against the cadastre.
- **Sheet dates.** Only the first commune folder of each appellation was listed, plus the 27
  disputed ones; check 5b's dates are a sample. A PDF's date is the file's production date,
  not the approval.
- **Former-commune sub-folders** were listed only for the disputed communes.
- **Records outside the inventory**: the 34 IG spirits, and the 26 unbound records listed
  above.
- **The inventory's own vintage**: 9 May 2026. Anything decided since, such as Ladoix's
  extension or the Champagne revision stop, is not in it.

## What I would do next

1. Fix the Champagne grand-cru / premier-cru overrides (failure mode D): Oger by its own
   outline, and the merged communes narrowed the way `seat_communes` narrows rows. Then
   read the 11 IGP overrides with communes nouvelles.
2. Gap fills for failure mode A after reading each plan: Lirac and Mont-Disse ×3 whole (no
   donor); Sorgues for Châteauneuf-du-Pape with a Côtes du Rhône donor, or a question to
   INAO; Oiron needs a former-commune outline, which the gap fill cannot draw yet. Préty
   for Bourgogne.
3. Pin Whisky breton's Loire-Atlantique communes (105 whole, 2 in part), with a BO Agri
   title search first. Do the same for Atlantique; Ardèche, Comtés Rhodaniens and Pays de
   Brive after the search for a newer cahier.
4. Teach `audit_parcellaire_gaps.py` to read the inventory: «non» closes a gap,
   «oui, plan disponible» with sheets opens one. That would turn its 3,308-commune queue
   into about 15 communes.
5. Ask INAO (service-delimitation@inao.gouv.fr) about: the Jurançon «oui» rows; the eight
   absent Chablis premier crus; the Volnay / Romanée-Saint-Vivant filing; why the
   2026-10-19 shapefile lacks the delimitations of A.
