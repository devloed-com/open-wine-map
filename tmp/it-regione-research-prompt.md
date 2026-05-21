# Research task — administrative region for 159 Italian wine DOPs

## Context

I maintain a wine-appellation reference (open-wine-map). The Italian
corpus has 412 wine DOPs. Each appears on a map and is filterable by
its Italian administrative *regione* (Piemonte, Toscana, Veneto, …).

For **159 DOPs** the source document we extracted carries no regione
field — they were stub records whose disciplinare didn't expose the
region in a machine-parseable way — so they currently render with the
placeholder region "Italia". I want to build a small curated mapping
file that fills these in.

## What I need from you

For each of the 159 DOPs below, give its Italian administrative
**regione**. Use the 20 standard regioni:

> Abruzzo · Basilicata · Calabria · Campania · Emilia-Romagna ·
> Friuli-Venezia Giulia · Lazio · Liguria · Lombardia · Marche ·
> Molise · Piemonte · Puglia · Sardegna · Sicilia · Toscana ·
> Trentino-Alto Adige · Umbria · Valle d'Aosta · Veneto

Some DOPs are **interregional** (the production zone spans two or more
regioni — e.g. a DOC straddling a provincial border). For those, return
an array of every regione the disciplinare's production zone covers,
ordered by where the bulk of the zone sits.

Authoritative sources, in priority order:

1. The wine's **it.wikipedia.org** article — the infobox carries a
   `Regione` row.
2. **eAmbrosia** (the EU GI register, `ec.europa.eu/.../eambrosia`) —
   the GI entry's geographical-area text.
3. The **disciplinare di produzione** (`Articolo 3`, "Zona di
   produzione") on `masaf.gov.it` or `gazzettaufficiale.it`.

Decide from the *production zone*, not from where the consorzio office
happens to be.

## The 159 DOPs

```
PDO-IT-A0232 | Fiano di Avellino
PDO-IT-A0236 | Greco di Tufo
PDO-IT-A0238 | Aversa
PDO-IT-A0240 | Capri
PDO-IT-A0242 | Castel San Lorenzo
PDO-IT-A0243 | Cilento
PDO-IT-A0248 | Falanghina del Sannio
PDO-IT-A0251 | Ischia
PDO-IT-A0252 | Vesuvio
PDO-IT-A0277 | Aglianico del Taburno
PDO-IT-A0278 | Costa d'Amalfi
PDO-IT-A0280 | Penisola Sorrentina
PDO-IT-A0281 | Sannio
PDO-IT-A0284 | Colli Bolognesi Pignoletto
PDO-IT-A0285 | Romagna Albana
PDO-IT-A0287 | Bosco Eliceo
PDO-IT-A0289 | Colli Bolognesi
PDO-IT-A0290 | Colli d'Imola
PDO-IT-A0291 | Colli di Faenza
PDO-IT-A0292 | Colli di Parma
PDO-IT-A0293 | Alto Adige
PDO-IT-A0294 | Lago di Caldaro
PDO-IT-A0297 | Rimini
PDO-IT-A0312 | Colli Piacentini
PDO-IT-A0318 | Colli Romagna centrale
PDO-IT-A0327 | Gutturnio
PDO-IT-A0332 | Lambrusco di Sorbara
PDO-IT-A0337 | Lambrusco Grasparossa di Castelvetro
PDO-IT-A0342 | Lambrusco Salamino di Santa Croce
PDO-IT-A0350 | Ortrugo dei Colli Piacentini
PDO-IT-A0355 | Portofino
PDO-IT-A0358 | Rossese di Dolceacqua
PDO-IT-A0359 | Val Polcèvera
PDO-IT-A0428 | Rosso Cònero
PDO-IT-A0431 | Lacrima di Morro
PDO-IT-A0433 | Falerio
PDO-IT-A0435 | Amarone della Valpolicella
PDO-IT-A0436 | Bardolino
PDO-IT-A0438 | Arcole
PDO-IT-A0439 | Breganze
PDO-IT-A0440 | Merlara
PDO-IT-A0441 | Recioto della Valpolicella
PDO-IT-A0442 | Valpolicella
PDO-IT-A0443 | Colli Maceratesi
PDO-IT-A0444 | Bianchello del Metauro
PDO-IT-A0446 | Valpolicella Ripasso
PDO-IT-A0447 | Lessini Durello
PDO-IT-A0456 | Corti Benedettine del Padovano
PDO-IT-A0462 | Monti Lessini
PDO-IT-A0465 | Recioto di Soave
PDO-IT-A0466 | Bagnoli di Sopra
PDO-IT-A0467 | Bagnoli Friularo
PDO-IT-A0469 | Gambellara
PDO-IT-A0470 | Recioto di Gambellara
PDO-IT-A0472 | Soave
PDO-IT-A0473 | Soave Superiore
PDO-IT-A0474 | Valdadige
PDO-IT-A0475 | Valdadige Terradeiforti
PDO-IT-A0480 | Verdicchio di Matelica Riserva
PDO-IT-A0481 | Verdicchio di Matelica
PDO-IT-A0482 | Verdicchio dei Castelli di Jesi
PDO-IT-A0483 | Castelli di Jesi Verdicchio Riserva
PDO-IT-A0506 | Reno
PDO-IT-A0517 | Venezia
PDO-IT-A0528 | Grottino di Roccanova
PDO-IT-A0541 | Alezio
PDO-IT-A0544 | Cacc'e mmitte di Lucera
PDO-IT-A0547 | Copertino
PDO-IT-A0548 | Galatina
PDO-IT-A0549 | Gioia del Colle
PDO-IT-A0551 | Lizzano
PDO-IT-A0552 | Locorotondo
PDO-IT-A0553 | Martina
PDO-IT-A0556 | Nardò
PDO-IT-A0558 | Orta Nova
PDO-IT-A0561 | Ostuni
PDO-IT-A0563 | Leverano
PDO-IT-A0566 | Rosso di Cerignola
PDO-IT-A0568 | San Severo
PDO-IT-A0610 | Cirò
PDO-IT-A0618 | Lamezia
PDO-IT-A0619 | Melissa
PDO-IT-A0742 | Terre Tollesi
PDO-IT-A0748 | Casteller
PDO-IT-A0749 | Teroldego Rotaliano
PDO-IT-A0757 | Montecompatri Colonna
PDO-IT-A0762 | Velletri
PDO-IT-A0764 | Zagarolo
PDO-IT-A0774 | Alcamo
PDO-IT-A0777 | Delia Nivolelli
PDO-IT-A0778 | Eloro
PDO-IT-A0779 | Erice
PDO-IT-A0782 | Malvasia delle Lipari
PDO-IT-A0785 | Marsala
PDO-IT-A0793 | Riesi
PDO-IT-A0795 | Salaparuta
PDO-IT-A0834 | Torgiano Rosso Riserva
PDO-IT-A0843 | Colli Perugini
PDO-IT-A0844 | Lago di Corbara
PDO-IT-A0847 | Rosso Orvietano
PDO-IT-A0848 | Spoleto
PDO-IT-A0851 | Torgiano
PDO-IT-A0908 | Collio Goriziano
PDO-IT-A0949 | Scanzo
PDO-IT-A1034 | Franciacorta
PDO-IT-A1035 | Sforzato di Valtellina
PDO-IT-A1036 | Valtellina Superiore
PDO-IT-A1042 | Curtefranca
PDO-IT-A1066 | Albugnano
PDO-IT-A1071 | Barbera del Monferrato
PDO-IT-A1073 | Lambrusco Mantovano
PDO-IT-A1092 | Cisterna d'Asti
PDO-IT-A1098 | Collina Torinese
PDO-IT-A1104 | Botticino
PDO-IT-A1106 | Colline Saluzzesi
PDO-IT-A1108 | Cellatica
PDO-IT-A1111 | Cortese dell'Alto Monferrato
PDO-IT-A1118 | Calosso
PDO-IT-A1124 | Capriano del Colle
PDO-IT-A1137 | Riviera del Garda Classico
PDO-IT-A1138 | Coste della Sesia
PDO-IT-A1139 | Dolcetto d'Acqui
PDO-IT-A1164 | Nuragus di Cagliari
PDO-IT-A1176 | Dolcetto di Ovada
PDO-IT-A1178 | Fara
PDO-IT-A1181 | Freisa di Chieri
PDO-IT-A1183 | Gabiano
PDO-IT-A1186 | Grignolino d'Asti
PDO-IT-A1187 | Grignolino del Monferrato Casalese
PDO-IT-A1188 | Valtènesi
PDO-IT-A1194 | Malvasia di Casorzo d'Asti
PDO-IT-A1201 | Malvasia di Castelnuovo Don Bosco
PDO-IT-A1213 | Nebbiolo d'Alba
PDO-IT-A1220 | Carmignano
PDO-IT-A1232 | Pinerolese
PDO-IT-A1234 | Rubino di Cantavenna
PDO-IT-A1236 | Sizzano
PDO-IT-A1238 | Strevi
PDO-IT-A1241 | Terre Alfieri
PDO-IT-A1246 | Montecucco Sangiovese
PDO-IT-A1261 | Roero
PDO-IT-A1263 | Ghemme
PDO-IT-A1315 | Erbaluce di Caluso
PDO-IT-A1318 | San Martino della Battaglia
PDO-IT-A1323 | Valtellina rosso
PDO-IT-A1325 | Barco Reale di Carmignano
PDO-IT-A1358 | Terre del Colleoni
PDO-IT-A1366 | Valcalepio
PDO-IT-A1389 | Barolo
PDO-IT-A1397 | Barbera del Monferrato Superiore
PDO-IT-A1400 | Grance Senesi
PDO-IT-A1421 | Montecarlo
PDO-IT-A1437 | Montescudaio
PDO-IT-A1442 | Orcia
PDO-IT-A1486 | Sant'Antimo
PDO-IT-A1491 | Terratico di Bibbona
PDO-IT-A1512 | Valdinievole
PDO-IT-A1669 | Vin Santo di Carmignano
PDO-IT-A1671 | Bolgheri Sassicaia
```

## Output format

Return a single JSON object keyed by file number, ready to drop into
`scripts/_lib/it/regione_by_file_number.json`:

```json
{
  "PDO-IT-A1389": "Piemonte",
  "PDO-IT-A0327": "Emilia-Romagna",
  "PDO-IT-A0474": ["Veneto", "Trentino-Alto Adige"]
}
```

Then, separately, list any DOP where you were **not confident** —
interregional cases, name collisions, or DOPs you could not pin to a
source — with one line each explaining the doubt, so I can spot-check
them.
