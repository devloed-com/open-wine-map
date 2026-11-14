# Grape tooltips that open another variety's Wikipedia article — verdicts (2026-11-14)

`scripts/audit_grape_wikipedia.py` lists, as OTHER-CULTIVAR, every grape pill whose
Wikipedia article is titled as none of the pill's own names and as the name of another
grape that carries a different VIVC number: 108 (grape, language) entries, 96 grapes.
Each was read against three things: the two VIVC passports (number, berry colour,
parents, pedigree), the text of the article itself, and the rosters of the build (does
any specification list the two as separate entries). "Pills" is the number of cards
that carry the grape.

| group | entries | grapes | pills |
|---|---:|---:|---:|
| correct redirect | 9 | 9 | 585 |
| wrong redirect | 72 | 65 | 1151 |
| no conclusive evidence | 27 | 27 | 345 |

A grape can sit in two groups when two languages show two different articles
(Parraleta: the French article is a white grape, the Spanish one equates it with
Graciano).

## How each group was decided

- **Correct**: VIVC's pedigree makes the pill a mutation of the article's variety; or the
  article is a family article that names the pill's variety as a member; or the article
  is about the grape of the appellation the pill comes from.
- **Wrong**: VIVC gives the two different parents or berry colours (or makes the pill a
  mutation or an offspring of another variety); or the article itself says the two are
  different; or the article never names the pill's variety — it was reached through a
  synonym the two share, or through a redirect.
- **No conclusive evidence**: the article does name the pill as a name of its own subject
  (opening sentence, prose or synonym list) while VIVC keeps two passports without parents
  or colour to tell them apart, often with specifications listing the two as separate
  entries; or there is nothing to go on (no passport, article silent). These need an
  outside source — a DNA study, the national register — before a pin.

Two verdicts correct what the session first reported as right: Vinhão → Sezão is wrong
(the article says the two "are two distinct varieties"), and Sousão / Sousón → Sezão is
inconclusive (Wikipedia makes Sousão the old name of Sezão; VIVC files it under Vinhão).

## Correct redirect

| pill (slug) | pills | article shown | evidence |
|---|---:|---|---|
| Sauvignon Gris (`sauvignon-gris`) | 234 | nl: Sauvignon Blanc | VIVC #10792: "SAUVIGNON BLANC MUTATION" |
| lledoner pelut (`lledoner-pelut`) | 99 | en: Grenache | VIVC #4460 Garnacha Peluda: "GARNACHA TINTA MUTATION"; the article describes it as "Hairy Grenache" |
| chasselas rosé (`chasselas-rose`) | 94 | nl: Chasselas blanc | VIVC #2493: "CHASSELAS BLANC MUTATION" |
| clairette rosé (`clairette-rose`) | 93 | es: Clairette blanche | VIVC #2699: "CLAIRETTE BLANCHE MUTATION" |
| Moscato rosa (`moscato-rosa`) | 35 | en: Muscat (grape) | family article: it names Moscato rosa del Trentino among the Muscats; VIVC gives it Muscat à petits grains as a parent |
| mondeuse grise (`mondeuse-grise`) | 13 | en: Mondeuse noire | VIVC #7920: "MONDEUSE NOIRE MUTATION"; the article has a section on Mondeuse grise |
| Băbească gri (`babeasca-gri`) | 10 | en: Băbească neagră | VIVC #842: "BABEASCA NEAGRA MUTATION"; the article names the pink mutation Băbească gri |
| Moscatello selvatico (`moscatello-selvatico`) | 6 | en: Muscat (grape) | family article: it names Moscatello Selvatico (Bombino bianco × Muscat of Alexandria) among the Muscats, as VIVC's parents do |
| Bianchello (`bianchello`) | 1 | en: Biancame | the article describes Biancame as the grape of Bianchello del Metauro, the disciplinare the pill comes from; the card's own note reads "Bianchello (also called Biancame)" |

Two more entries joined the list once the stale-passport entries were re-fetched, and are
correct by the same rule: `carinena-gris` (en: Carignan, nl: Carignan (blauw druivenras)) —
VIVC #2097: "CARIGNAN NOIR MUTATION".

## Wrong redirect

| pill (slug) | pills | article shown | evidence |
|---|---:|---|---|
| gamay de chaudenay (`gamay-de-chaudenay`) | 114 | en: Aligoté | VIVC: a black Gamay teinturier against Aligoté, white; reached through the synonym PLANT GRIS |
| gamay de bouze (`gamay-de-bouze`) | 101 | en: Brun Fourca | VIVC #4379: "GAMAY NOIR MUTATION"; the article is Brun Fourca, reached through the synonym MOUREAU |
| morrastel (`morrastel`) | 95 | en: Mourvèdre | the article: "Mourvèdre has no relation to the Spanish wine grape Graciano which is also known as Morrastel in France" |
| chenanson (`chenanson`) | 85 | en: Chenin blanc | VIVC: a black crossing (Grenache × Jurançon noir) against Chenin blanc; reached through VAALBLAAR STEIN, a South African name of Chenin |
| Sanforte (`sanforte`) | 66 | en: Gaglioppo | the article never names Sanforte; VIVC parents ? × Visparola against Gaglioppo's Sangiovese × Mantonico; reached through GAGLIOPPA |
| Malvasia Fina (`malvasia-fina`) | 51 | es: Albillo | VIVC parents: Malvasia Fina is Heben × Alfrocheiro, Albillo Real Agostenga × ?; the article never names it |
| gamay fréaux (`gamay-freaux`) | 43 | en: Alicante Bouschet | VIVC #4382: "GAMAY TEINTURIER DE BOUZE MUTATION"; the article is Alicante Bouschet (Petit Bouschet × Grenache) |
| roussette d'ayze (`roussette-d-ayze`) | 33 | en: Marsanne | the article never names Roussette d'Ayze ("grosse roussette" is Marsanne's Savoie name); 17 cahiers list both |
| mollard (`mollard`) | 31 | en: Carignan | VIVC parents: Heunisch weiss × ? against Carignan's Castellana blanca × ?; the article's "Mollard (in Rioja)" is a Rioja name of Carignan; 16 cahiers list both |
| Tinta-Miúda (`tinta-miuda`) | 30 | en: Grenache | the slug's passport is Graciano; the article is Grenache and never names Tinta Miúda |
| saint côme (`saint-come`) | 28 | en: Saint-Pierre Doré | VIVC parents: Heunisch weiss × Moural against Saint-Pierre Doré's Heunisch weiss × Friulano; 13 cahiers list both |
| raffiat de moncade (`raffiat-de-moncade`) | 27 | en: Gewürztraminer | VIVC: white (Heunisch weiss × Bouchalès) against Gewürztraminer, pink; reached through the synonym ROUSSELET |
| Vinhão (`vinhao`) | 24 | en: Sezão | the article: Souzão (now Sezão) and Vinhão "are two distinct varieties"; 4 cadernos list both |
| Tinta Caiada (`tinta-caiada`) | 22 | fr: Carcajolo blanc | VIVC: Parraleta, black, against the white variety of the article |
| Trbljan (`trbljan`) | 21 | en: Avarengo | VIVC: white against Avarengo, black |
| Monvedro (`monvedro`) | 20 | en: Trousseau (grape) | the article never names Monvedro; reached through the homonym "Bastardo" |
| mancin (`mancin`) | 19 | en: Malbec | the article never names Mancin; reached through the synonym COT A QUEUE VERTE |
| Manteúdo (`manteudo`) | 19 | en: Albillo | the article never names Manteúdo; reached through the homonym "Castellano" |
| planta nova (`planta-nova`) | 19 | en: Merseguera | VIVC parents: Heptakilo × Rojal tinta against Merseguera's Heben × Folha de Figueira |
| forcallat tinta (`forcallat-tinta`) | 18 | nl: Viura | VIVC: black against Viura, white; reached through the synonym MACABEO |
| Lacrima (`lacrima`) | 18 | nl: Aleatico | VIVC: Lacrima is Aleatico × Nera Rada — an offspring of the article's variety; reached through LACRIMA CHRISTI |
| Boal Branco (`boal-branco`) | 17 | en: Doña Blanca | VIVC parents: Malvasia Fina × Dedo de Dama against Síria's Cayetana blanca; reached through the synonym BOAL CACHUDO |
| Cerceal Branco (`cerceal-branco`) | 17 | en: Sercial | the article never names it; VIVC gives Cerceal Branco its own parents (Malvasia Fina × Tinta Pereira); 7 cadernos list it beside Sercial |
| Cerceal Branco (`cerceal-branco`) | 17 | es: Sercial | the article lists "cerceal", a Sercial synonym, not Cerceal Branco; 7 cadernos list the two as separate castas |
| Molinara (`molinara`) | 14 | nl: Aleatico | the article never names Molinara; reached through the synonym ROSSANELLA |
| Pedral (`pedral`) | 12 | en: Caíño blanco | VIVC: black against Caíño blanco, white |
| Boal Espinho (`boal-espinho`) | 11 | en: Baga (grape) | VIVC: white (Heben × Malvasia Fina) against Baga, black; reached through the synonym CARREGA BURROS |
| Donzelinho Tinto (`donzelinho-tinto`) | 11 | en: Donzelinho branco | the article: DNA showed neither Donzelinho is a colour mutation of the other; VIVC black against white |
| forcallat blanca (`forcallat-blanca`) | 11 | en: Forcallat tinta | the article: "Forcallat blanca … is a distinct variety and not a color mutation of Forcallat tinta" |
| forcallat blanca (`forcallat-blanca`) | 11 | es: Airén | VIVC parents: Ohanes × ? against Airén's Heben × ?; 3 specifications list both (the Spanish article lists the name among Airén's synonyms) |
| forcallat blanca (`forcallat-blanca`) | 11 | nl: Airén | VIVC parents: Ohanes × ? against Airén's Heben × ?; the article never names it |
| güal (`gual`) | 11 | es: Albillo | VIVC parents: Malvasia Fina is Heben × Alfrocheiro, Albillo Real Agostenga × ? |
| Rumeni plavec (`rumeni-plavec`) | 11 | en: Piccola nera | VIVC: white (Heunisch weiss × Vulpea) against Piccola nera |
| Castelã (`castela`) | 10 | en: Castelão (grape) | the article never names Castelã; 4 cadernos list Castelã and Castelão as two castas (VIVC: two passports with the same parents — siblings) |
| Molar (`molar`) | 10 | en: Listán negro | VIVC parents: Prieto Picudo × Savagnin against Listán negro's Mollar cano × Palomino fino |
| Preto Cardana (`preto-cardana`) | 10 | en: Alvarelhão | the article never names it; reached through the synonym PILONGO; VIVC gives it its own parents (Cayetana blanca × Molar) |
| Tinta Lameira (`tinta-lameira`) | 10 | fr: Carcajolo blanc | VIVC: Parraleta, black, against the white variety of the article |
| abondant (`abondant`) | 9 | en: Grenache | VIVC: a white crossing (Kövidinka × Madeleine royale) against Garnacha tinta, black; reached through the synonym ABUNDANTE |
| bastardo blanco (`bastardo-blanco`) | 9 | es: Jaén (uva) | VIVC #24996: "TROUSSEAU NOIR MUTATION"; the article is the white Jaén and never names it |
| Guardavalle (`guardavalle`) | 9 | en: Greco (grape) | the article names Guardavalle as another grape blended with Greco; reached through the synonym GRECO BIANCO |
| caíño bravo (`caino-bravo`) | 8 | es: Caíño tinto | the article never names it; 3 specifications list Caíño bravo and Caíño tinto as separate entries |
| mornen (`mornen`) | 6 | en: Chasselas | VIVC: Mornen noir, black (Mondeuse noire × ?), against Chasselas blanc |
| tintilla de rota (`tintilla-de-rota`) | 6 | en: Grenache | the slug's passport is Graciano; the article is Grenache and never names Tintilla de Rota |
| dureza (`dureza`) | 5 | nl: Durif | the article never names Dureza; VIVC: Durif is Syrah × Peloursin, and Dureza is a parent of Syrah |
| Roupeiro-Branco (`roupeiro-branco`) | 5 | fr: Siria | VIVC parents: Heben × Folgasão against Síria's Cayetana blanca × ?; the article's "Roupeiro" is Síria's own synonym |
| sérénèze (`sereneze`) | 5 | en: Syrah | VIVC parents: Heunisch weiss × Chatus against Syrah's Mondeuse blanche × Dureza |
| sérénèze (`sereneze`) | 5 | nl: Durif | VIVC parents: Heunisch weiss × Chatus against Durif's Syrah × Peloursin |
| Trebbiano modenese (`trebbiano-modenese`) | 5 | en: Montonico bianco | the article never names it; reached through the synonym TREBBIANO MONTANARO |
| Esganinho (`esganinho`) | 4 | en: Sercial | the article never names it; 4 cadernos list Esganinho and Sercial as separate castas |
| hondarrabi beltza (`hondarrabi-beltza`) | 4 | en: Bia blanc | VIVC: black against Bia blanc, white |
| hondarrabi beltza (`hondarrabi-beltza`) | 4 | es: Courbu | VIVC: black against Courbu blanc; the article names hondarrabi beltza as the red variety blended with it |
| felen (`felen`) | 3 | en: Saint-Pierre Doré | the article never names Felen; reached through the homonym "Saint Come" |
| jaén tinto (`jaen-tinto`) | 3 | fr: Mencia | VIVC parents: Listán Prieto × Cayetana blanca against Mencía's Alfrocheiro × Patorra |
| Minutolo (`minutolo`) | 3 | nl: Ruché | VIVC: white against Ruché, black |
| Spergola (`spergola`) | 3 | en: Avarengo | VIVC: white against Avarengo, black |
| Žlahtina (`zlahtina`) | 3 | en: Chasselas | the article never names Žlahtina; VIVC #22843 apart, with its own parent (? × Vulpea) |
| borba (`borba`) | 2 | en: Welschriesling | VIVC: a black crossing (Muscat Hamburg × Castelão) against Welschriesling, white; the article's "Borba blanca" is another grape |
| Listrao (`listrao`) | 2 | en: Listán negro | the article never names Listrão; reached through the synonym LISTAN MORADO; VIVC #17248 Listrão roxo apart |
| Ljutac (`ljutac`) | 2 | fr: Plavac mali | VIVC: Ljutac is Plavac mali × Bombino bianco — an offspring of the article's variety |
| Neretta cuneese (`neretta-cuneese`) | 2 | en: Uvalino | the article never names it; reached through the synonym FREISONE |
| parraleta (`parraleta`) | 2 | fr: Carcajolo blanc | VIVC: Parraleta, black, against the white variety of the article |
| Pau Ferro (`pau-ferro`) | 2 | fr: Carcajolo blanc | VIVC: Parraleta, black, against the white variety of the article |
| Rodo (`rodo`) | 2 | fr: Mondeuse blanche | the slug's passport is Mondeuse noire; the article is Mondeuse blanche, which it says "n'est pas la forme blanche de la mondeuse noire" |
| Vencedor (`vencedor`) | 2 | en: Doña Blanca | the article never names Vencedor; reached through the synonym BOAL CACHUDO |
| calagraño (`calagrano`) | 1 | en: Cayetana blanca | the article lists Calagraño among the varieties "commonly confused" with Cayetana blanca |
| calagraño (`calagrano`) | 1 | es: Jaén (uva) | the same variety as above (Jaén = Cayetana blanca), which the English article says Calagraño is confused with; VIVC #24553 apart |
| colombaud (`colombaud`) | 1 | en: Saint-Pierre Doré | the article never names Colombaud; reached through the homonym "Saint Pierre" |
| molinera (`molinera`) | 1 | en: Carignan | the article never names Molinera; VIVC parents Heben × ? against Carignan's Castellana blanca × ? |
| molinera (`molinera`) | 1 | fr: Mollard (cépage) | the article never names Molinera; VIVC parents Heben × ? against Mollard's Heunisch weiss × ? |
| saint-jean-de-mondeuse (`saint-jean-de-mondeuse`) | 1 | fr: Mondeuse blanche | the slug's passport is Mondeuse noire; the article is Mondeuse blanche, which it says is not the white form of it |
| Tinta Porto Santo (`tinta-porto-santo`) | 1 | en: Listán negro | VIVC parents: Prieto Picudo × Savagnin (the passport of Molar) against Listán negro's Mollar cano × Palomino fino |
| uva biancona (`uva-biancona`) | 1 | en: Grenache blanc | the article: Australia's "White Grenache" was identified as Biancone — not Grenache blanc |

## No conclusive evidence

| pill (slug) | pills | article shown | evidence |
|---|---:|---|---|
| Canina Nera (`canina-nera`) | 56 | en: Fortana | the article opens "Fortana (also known as Canina nera)"; VIVC keeps two passports (no parents given); 3 specifications list both |
| genovèse (`genovese`) | 29 | en: Albarola | the article lists "Bianchetta Genovese" among Albarola's synonyms, the cahier writes "genovèse"; VIVC keeps #4766 apart |
| carcajolo (`carcajolo`) | 26 | es: Graciano (uva) | the Spanish article cites a DNA study making Graciano, Parraleta and Tintilla de Rota one variety; VIVC keeps #8951 Parraleta and #4935 Graciano apart; 14 specifications list both |
| Sousão (`sousao`) | 23 | en: Sezão | the article: Sezão was "formerly known as Souzão"; VIVC files Sousão under Vinhão #13100, which the same article calls a distinct variety |
| Tinta Caiada (`tinta-caiada`) | 22 | es: Graciano (uva) | as Parraleta (same passport #8951): the Spanish article equates it with Graciano, VIVC does not; 8 specifications list both |
| gascon (`gascon`) | 20 | en: Mondeuse noire | the article lists Gascon among Mondeuse noire's synonyms; VIVC keeps #4477 apart (no parents given); 11 cahiers list both |
| sousón (`souson`) | 20 | en: Sezão | the article: "Sezão (Spanish: Sousón)"; VIVC files Sousón under Vinhão #13100, which the same article calls a distinct variety |
| bonicaire (`bonicaire`) | 16 | en: Trepat | Wikipedia and VIVC give Bonicaire as a Trepat synonym; one specification lists the two as separate entries, which is why the slug carries no VIVC number |
| Vernaccia nera (`vernaccia-nera`) | 16 | en: Grenache | the article says Grenache is known in Italy as Vernaccia Nera; VIVC keeps #12999 apart (no parents given); 11 specifications list both |
| Μαύρο (`mavro`) | 13 | nl: Agiorgitiko | the article lists "Mavro" among Agiorgitiko's synonyms; the pill is the Cypriot Mavro, with no VIVC number here; 5 specifications list both |
| petite sainte-marie (`petite-sainte-marie`) | 13 | en: Chardonnay | the article lists Petite Sainte Marie among Chardonnay's synonyms; VIVC keeps #24308 apart with a compatible parent (Heunisch weiss × ?); one cahier lists both |
| mècle (`mecle`) | 11 | en: Poulsard | the article lists Mècle among Poulsard's synonyms; VIVC keeps #7566 apart (no parents given); 3 cahiers list both |
| Tintinha (`tintinha`) | 11 | en: Petit Bouschet | the article lists "Tintinha (in Portugal)" among Petit Bouschet's synonyms; VIVC keeps #14985 apart (no parents given); 3 cadernos list both |
| Bonvedro (`bonvedro`) | 10 | en: Parraleta | the article lists Bonvedro and Monvedro de Sines among Parraleta's synonyms; VIVC keeps #26254 Monvedro de Sines apart (no parents given); 4 cadernos list both |
| Tinta Lameira (`tinta-lameira`) | 10 | es: Graciano (uva) | as Parraleta (same passport #8951): the Spanish article equates it with Graciano, VIVC does not |
| mourvèdre blanc (`mourvedre-blanc`) | 8 | es: Monastrell (uva) | named as the white form of Mourvèdre; no VIVC passport and the article does not mention one |
| mourvèdre gris (`mourvedre-gris`) | 8 | es: Monastrell (uva) | named as the grey form of Mourvèdre; VIVC #17318 states no pedigree and the article does not mention it |
| Pilongo (`pilongo`) | 7 | en: Alvarelhão | the article lists Pilongo among Alvarelhão's synonyms; VIVC keeps #16955 apart (no parents given); 7 cadernos list both |
| Corinto Nero (`corinto-nero`) | 5 | en: Sangiovese | the article says Corinto nero of Lipari is a Sangiovese; VIVC #42341 reads "Corinto nero (non identified)"; 4 specifications list both |
| tinto velasco (`tinto-velasco`) | 4 | en: Alicante Bouschet | the article lists Tinto Velasco among Alicante Bouschet's synonyms; VIVC keeps #17353 apart (no parents given); 3 specifications list both |
| Trebbiano abruzzese (`trebbiano-abruzzese`) | 4 | en: Bombino bianco | the article lists Trebbiano Abruzzese among Bombino bianco's synonyms; VIVC keeps #24748 apart (? × Mostosa; Bombino has none given) |
| Minutolo (`minutolo`) | 3 | en: Fiano (grape) | the article lists Minutolo among Fiano's synonyms; VIVC keeps #22764 apart (? × Visparola; Fiano has none given); 3 specifications list both |
| Carrasquenho (`carrasquenho`) | 2 | en: Baga (grape) | the article lists Carrasquenho among Baga's synonyms; VIVC keeps #24566 apart with parents (Parraleta × Malvasia Fina) that do not contradict Baga's (Malvasia Fina × ?); 2 cadernos list both |
| Carrega Burros (`carrega-burros`) | 2 | en: Baga (grape) | the article lists Carrega Burros among Baga's synonyms; VIVC keeps #17267 apart (no parents given); 2 cadernos list both |
| Negretto (`negretto`) | 2 | en: Négrette | the article lists Negretto among Négrette's synonyms; VIVC keeps #8453 Negretto (Italy) apart (no parents given) |
| parraleta (`parraleta`) | 2 | es: Graciano (uva) | the Spanish article cites a DNA study making Graciano and Parraleta one variety; VIVC keeps #8951 and #4935 apart; the Somontano pliego lists both |
| Pau Ferro (`pau-ferro`) | 2 | es: Graciano (uva) | as Parraleta (same passport #8951): the Spanish article equates it with Graciano, VIVC does not |

## What was done with it

- **Wrong (72 entries)**: pinned `null` for that language in
  `raw/wikipedia/grape_overrides.json` the same day and applied with
  `02b_fetch_grape_lexicon.py --only …` (a `null` pin now takes effect on a cached
  article without `--refresh`). Four of them replaced an earlier title pin that had
  itself named the wrong article: `mollard` → Carignan, `mornen` → Chasselas,
  `morrastel` → Mourvèdre (en) and `dureza` → Durif (nl). The pill then shows the
  article of another language in translation where one is cached, else no article.
- **No conclusive evidence (27)**: left as they are and listed, one checkbox each, in
  `CURATOR_TODO.md` ("Grape tooltips — 27 redirects without conclusive evidence").
- **Correct (9)**: nothing to do.

Three verdicts also question the grape's VIVC binding rather than its article: `rodo`
and `saint-jean-de-mondeuse` resolve to Mondeuse noire, `sanforte` to Maiolica,
`spergola` / `trbljan` to Mostosa. The source locales that only feed translations
(`it`, `pt`, `de`, `hu`) and the audit's UNVERIFIED bucket (73 grapes) were not read.
