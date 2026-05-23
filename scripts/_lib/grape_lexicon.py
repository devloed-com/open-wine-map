"""Parsing of cahier-de-charges section V (encépagement) and section III
(styles & couleurs) into structured fields.

The cahiers list grapes in a stable shape:

    cépages principaux : sémillon B, sauvignon B, sauvignon gris G ;
    cépages accessoires : colombard B, merlot blanc B, ugni blanc B
    variétés « d'intérêt à fin d'adaptation » : Floréal B, Liliorila B

Each token is `<name> <colour-code>` where colour-code ∈ {B, N, G, Rs, Rg}
(blanc, noir, gris, rosé, rouge). Synonyms or local names appear in
parentheses or after `dénommé localement`. We strip those and keep the
canonical INAO name.

For styles we scan section III for explicit colour adjectives and
mention/category keywords (vendanges tardives, mousseux, vin doux naturel,
vin jaune, primeur, etc.). The result is a small set of canonical tags that
the map UI uses as filter facets.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

COLOUR_CODES = {"B": "blanc", "N": "noir", "G": "gris", "Rs": "rose", "Rg": "rouge"}

_COLOUR_WORDS = frozenset({
    "blanc", "blanche", "blancs",
    "noir", "noire", "noirs",
    "gris", "grise",
    "rose", "rosé", "rosa", "rosada", "rosado",
    "rouge",
})


def _ends_with_colour_word(name: str) -> bool:
    tokens = name.split()
    return bool(tokens) and tokens[-1].lower() in _COLOUR_WORDS

# Map alternate spellings → canonical slug. Kept short on purpose: only
# variants that genuinely fragment the same INAO grape across cahiers go
# here. Add more as the per-AOC log surfaces them.
GRAPE_ALIAS = {
    "cinsaut": "cinsault",
    "sciaccarello": "sciacarello",
    "barbarossa": "barbaroux",
    "niellucio": "nielluccio",
    "muscat-petits-grains": "muscat-a-petits-grains",
    "muscat-a-petits-grains-blancs": "muscat-a-petits-grains",
    "muscat-petits-grains-blancs": "muscat-a-petits-grains",
    "muscat-a-petit-grain": "muscat-a-petits-grains",
    "muscats-a-petits-grains": "muscat-a-petits-grains",
    "type-gamay": "gamay",
    "gewurtztraminer": "gewurztraminer",
    "gerwurztraminer": "gewurztraminer",
    "gewurztraminer": "gewurztraminer",
    "assyrtyko": "assyrtiko",
    "assiyrtico": "assyrtiko",
    "alvarino": "alvarinho",
    "brun-fourcat": "brun-fourca",
    "morastel": "morrastel",
    "nebiollo": "nebbiolo",
    "negret-de-bahnars": "negret-de-banhars",
    "piquepoulnoir": "piquepoul-noir",
    "pousard": "poulsard",
    "roussane": "roussanne",
    "syrha": "syrah",
    "sirah": "syrah",                          # ES pliego typo (lanzarote)
    "syrah-shiraz": "syrah",                   # PT "Syrah (Shiraz)" — parenthetical synonym
    # ----- ES → canonical (international or FR slug where the variety
    # is the same trans-Pyrenean grape). Synonym pairs marked with " - "
    # inside pliegos are split before alias lookup, so every alternative
    # name lands here individually. Seed list from the 145 ES pliegos +
    # eAmbrosia synonym table; new tokens surface via
    # scripts/audit_es_grape_aliases.py.
    "garnacha": "grenache",
    "garnacha-tinta": "grenache",
    "garnacha-noir": "grenache",
    "garnacha-peluda": "grenache",
    "lladoner": "grenache",
    "lladoner-pelut": "grenache",
    "cannonau": "grenache",
    "garnacha-blanca": "grenache-blanc",
    "lladoner-blanco": "grenache-blanc",
    "garnacha-roja": "grenache-gris",
    "garnacha-gris": "grenache-gris",
    "garnacha-tintorera": "alicante-bouschet",
    "mazuela": "carignan",
    "mazuelo": "carignan",
    "carinena": "carignan",
    "samso": "carignan",
    "mataro": "mourvedre",
    "monastrell": "mourvedre",
    "macabeo": "macabeu",
    "viura": "macabeu",
    "xarel-lo": "xarello",                      # "Xarel.lo" Catalan orthography → canonical Xarello (vivc 13270)
    "xarel-lo-rosado": "xarello-rosado",        # rosé variant orthography (vivc 13273)
    "ull-de-llebre": "tempranillo",
    "tinta-del-pais": "tempranillo",
    "tinto-fino": "tempranillo",
    "tinta-de-toro": "tempranillo",
    "cencibel": "tempranillo",
    "tinta-roriz": "tempranillo",
    "hondarrabi-beltza": "hondarrabi-beltza",
    "ondarrabi-beltza": "hondarrabi-beltza",
    "hondarrabi-zuri": "hondarrabi-zuri",
    "ondarrabi-zuri": "hondarrabi-zuri",
    "moscatel-de-alejandria": "muscat-d-alexandrie",
    "moscatel": "muscat-d-alexandrie",
    "moscatel-de-grano-menudo": "muscat-a-petits-grains",
    "subirat-parent": "alarije",
    "subirant-parent": "alarije",
    "loureiro-blanco": "loureira",
    "loureiro": "loureira",
    "branco-lexitimo": "albarin-blanco",
    "listan-blanco": "palomino-fino",          # Jerez / Manzanilla synonym; Canarian Listán Blanco uses the longer slug `listan-blanco-de-canarias`.
    "tardana": "planta-nova",
    "verdosilla": "merseguera",
    "mando": "garro",
    "prensal": "moll",
    "torneiro": "espadeiro",
    "gironet": "grenache",
    "dona-branca": "siria",                    # Galician form; VIVC #2742 SIRIA
    "mouraton": "juan-garcia",                 # Bierzo/Valdeorras synonym
    "turruntes": "albillo-mayor",              # Rioja/Albillo Mayor synonym
    # ----- ES OJ-asserted `A - B` synonym pairs, VIVC-confirmed
    # (both sides resolve to the same VIVC variety number). Canonical
    # picked by: VIVC prime slug when it matches a pair member, then
    # existing GRAPE_ALIAS target, then most-used slug in the corpus.
    # Pairs whose VIVC prime is a third existing slug are folded
    # cross-canonically below.
    "malvasia-sitges": "malvasia-aromatica",   # VIVC #7266
    "malvasia-de-banyalbufar": "malvasia-aromatica",
    "diego": "vijariego-blanco",               # VIVC #13075
    "bigiriego": "vijariego-blanco",
    "malvasia-riojana": "alarije",             # VIVC #213
    "baboso-blanco": "bastardo-blanco",        # VIVC #24996
    "marmajuelo": "bermejuela",                # VIVC #24424
    "chelva": "montua",                        # VIVC #2520
    "pensal-blanca": "moll",                   # VIVC #9113 prime PENSAL BLANCA, but `moll` is the established canonical (cf. `prensal: moll`)
    "frasco": "tinto-velasco",                 # VIVC #17353
    "marques": "loureira",                     # VIVC #6912 LOUREIRO BLANCO; loureira is the established canonical
    "juan-ibanez": "moristel",                 # VIVC #12353
    "montonec": "parellada",                   # VIVC #8938
    "montonega": "parellada",
    "cartoixa": "xarello",                     # VIVC #13270
    "pansa-blanca": "xarello",
    "pansal": "xarello",
    "eva": "beba",                             # VIVC #22710
    "marisancho": "pardillo",                  # VIVC #8934
    "mandon": "garro",                         # VIVC #7326
    "dozal": "pedral",                         # VIVC #9078
    "moscatel-morisco": "muscat-a-petits-grains",  # VIVC #8193
    # Cross-canonical: pair members fold to the VIVC prime slug already
    # established elsewhere in the corpus (FR / PT canonicals).
    "pardina": "cayetana-blanca",              # VIVC #5648 CAYETANA BLANCA
    "jaen-blanco": "cayetana-blanca",
    "dona-blanca": "siria",                    # VIVC #2742 SIRIA — unifies ES Doña Blanca with PT Síria
    "ciguente": "siria",
    "malvasia-castellana": "siria",
    "brunal": "alfrocheiro",                   # VIVC #277 ALFROCHEIRO — unifies ES Brunal/Baboso Negro with PT Alfrocheiro
    "baboso-negro": "alfrocheiro",
    # ----- ES OJ-asserted pairs disambiguated by external research
    # (Chrome-extension VIVC + EU DG-AGRI + MAPA + Canary Wine + Wine
    # Grapes cross-check, 2026-05-19). Notes for each:
    "almuneco": "listan-negro",                # VIVC #14943 LISTAN NEGRO; #6860 LISTAN PRIETO (=Mission/País) is a separate variety despite carrying ALMUNECO as a legacy synonym
    "agudelo": "godello",                      # VIVC #12953 GOUVEIO (= Godello); the OJ's "AGUDELO - CHENIN BLANC" equation is an ampelographic error VIVC carries as a legacy ES synonym on #2527
    "blasco": "tinto-velasco",                 # VIVC #17353 TINTO VELASCO; #304 ALICANTE BOUSCHET also lists BLASCO as a synonym (VIVC duplication) — alias pins it to the correct variety
    "bastardo-negro": "trousseau",             # VIVC #12668 TROUSSEAU NOIR (= Merenzao); distinct from baboso-negro (= Alfrocheiro) despite the Canarian pliegos' synonymy claim
    "crudijera": "moravia-dulce",              # VIVC #23166 MORAVIA DULCE (CRUJIDERA synonym; "Crudijera" in La Mancha/Manchuela is a d↔j metathesis)
    "negro-sauri": "trousseau",                # VIVC #12668 TROUSSEAU NOIR; EU DG-AGRI List 8 and MAPA both register NEGRO SAURÍ as a synonym of Merenzao
    "merenzao": "trousseau",                   # VIVC #12668 TROUSSEAU NOIR — unifies the ES/Galician name with the FR canonical (and bastardo-negro, negro-sauri, maturana-tinta below)
    "maturana-tinta": "trousseau",             # VIVC #12668 TROUSSEAU NOIR (Rioja name)
    "tintilla": "trousseau",                   # Canarian-only in this corpus (10/10 pliegos are Canary Islands DOPs); peninsular "Tintilla" appears as the full slug `tintilla-de-rota` (= Graciano #4935), which stays separate
    # ----- Typos / alt-spellings in specific pliegos. Folded here so
    # GRAPE_ALIAS keeps source data unmodified.
    "petiti-verdot": "petit-verdot",          # Laujar-Alpujarra
    "ruby-carbernet": "ruby-cabernet",         # Islas Canarias
    "pedro-jimenez": "pedro-ximenez",          # Málaga (alt-spelling)
    "pero-ximen": "pedro-ximenez",             # Málaga (truncated)
    "chenin-blanco": "chenin",                 # Betanzos (Spanish spelling)
    # ----- PT → canonical. Synonyms unify cross-country grapes (Tinta
    # Roriz = Aragonez = Tempranillo; Gouveio = Godello; Trajadura =
    # Treixadura). Only DNA-confirmed identity mappings; ampelographic
    # synonym pairs that are debated stay separate.
    "aragonez": "tempranillo",                # PT canonical (Douro / Alentejo / Vinho Verde)
    "aragones": "tempranillo",                # Dão spelling variant
    "gouveio": "godello",                     # Galician canonical (same grape)
    "trajadura": "treixadura",                # Galician canonical
    "trincadeira-preta": "trincadeira",
    "tinta-amarela": "trincadeira",
    "esgana-cao": "sercial",                  # Madeira: distinct from "Esganinho"
    "boal": "malvasia-fina",                  # Madeira "Boal" = Malvasia Fina (DNA)
    "bual": "malvasia-fina",                  # English-language Madeira label
    "brancelho": "alvarelhao",
    "alvaraca": "batoca",
    "maria-gomes": "fernao-pires",            # Bairrada synonym
    "trebbiano-toscano": "ugni-blanc",        # international synonym
    "talia": "ugni-blanc",                    # PT name for Ugni Blanc / Trebbiano
    # ----- IT → canonical. Italian regional varieties that VIVC's
    # synonym-fold otherwise merges into wrong umbrella slugs
    # (Lambrusco spp. into NIELLUCCIO, Trebbiano cluster into UGNI
    # BLANC, Pinot Bianco/Grigio into pinot-noir, Riesling Italico
    # into Riesling, …). Each entry mints (or pins) a distinct slug.
    # Seeded from the 532 IT disciplinari extraction audit; new tokens
    # will surface via raw/it/extraction-unknowns.json.
    #
    # Lambrusco family — 6 distinct cultivars; VIVC routes them via
    # NIELLUCCIO because that VIVC entry lists "Lambrusco" as a legacy
    # synonym.
    "lambrusco": "lambrusco",
    "lambrusco-barghi": "lambrusco-barghi",
    "lambrusco-salamino": "lambrusco-salamino",
    "lambrusco-grasparossa": "lambrusco-grasparossa",
    "lambrusco-grasparossa-di-castelvetro": "lambrusco-grasparossa",
    "lambrusco-maestri": "lambrusco-maestri",
    "lambrusco-di-sorbara": "lambrusco-di-sorbara",
    "lambrusco-a-foglia-frastagliata": "lambrusco-foglia-frastagliata",
    "lambrusco-foglia-frastagliata": "lambrusco-foglia-frastagliata",
    # Other reds wrongly folded into NIELLUCCIO
    "lacrima": "lacrima",                     # Lacrima di Morro d'Alba (Marche)
    "corinto-nero": "corinto-nero",           # Greek-origin red (Aeolian Islands)
    # Sangiovese — NIELLUCCIO Corse = Sangiovese DNA, but `sangiovese`
    # is the corpus-established canonical. Pin so the bare token doesn't
    # surprise-flip when synonym-pair tokens widen the candidate set.
    "sangiovese": "sangiovese",
    # Trebbiano cluster — only Toscano = Ugni Blanc (DNA confirmed);
    # the regional Trebbianos are distinct cultivars.
    "trebbiano-romagnolo": "trebbiano-romagnolo",
    "trebbiano-di-soave": "trebbiano-di-soave",  # = Verdicchio DNA, name kept regional
    "trebbiano-modenese": "trebbiano-modenese",
    "trebbiano-spoletino": "trebbiano-spoletino",
    "trebbiano-abruzzese": "trebbiano-abruzzese",
    "trebbiano-giallo": "trebbiano-giallo",      # a/k/a Rossetto (Lazio)
    # Other whites wrongly folded into UGNI BLANC
    "coda-di-volpe": "coda-di-volpe",
    "coda-di-volpe-bianca": "coda-di-volpe",
    "falanghina": "falanghina",
    "passerina": "passerina",
    "biancame": "biancame",
    "montonico": "montonico",
    "montonico-bianco": "montonico",
    "rossola-nera": "rossola-nera",              # Valtellina red, NOT a Trebbiano
    # Pinot family — split from pinot-noir umbrella
    "pinot-bianco": "pinot-blanc",
    "pinot-grigio": "pinot-gris",
    "pinot-nero": "pinot-noir",
    "pignola": "pignola-valtellinese",
    "pignola-valtellinese": "pignola-valtellinese",
    "pignolo": "pignolo",                        # distinct Friulian red
    # Cabernet — `cabernet` bare slug is a parser artefact; pin to franc.
    "cabernet": "cabernet-franc",
    # Riesling — Italico is Welschriesling, ampelographically unrelated
    # to true Riesling (Renano).
    "riesling-italico": "welschriesling",
    "welschriesling": "welschriesling",
    "riesling-renano": "riesling",
    # Moscato cluster
    "moscato-bianco": "muscat-a-petits-grains",  # DNA-confirmed
    "moscatello": "muscat-a-petits-grains",      # historical synonym
    "moscato-reale": "muscat-a-petits-grains",   # IT synonym for Moscato bianco
    "moscato-giallo": "moscato-giallo",          # distinct (Goldmuskateller)
    "gelber-muskateller": "moscato-giallo",
    "muskateller": "moscato-giallo",
    "moscato-di-scanzo": "moscato-di-scanzo",    # distinct red Moscato (Bergamo)
    # Garganega — totally distinct from Glera (Prosecco grape)
    "garganega": "garganega",
    "glera-lunga": "glera-lunga",
    # Pugnitello — distinct from Montepulciano
    "pugnitello": "pugnitello",
    # Spergola — Reggio-Emilia white, distinct from Sauvignon
    "spergola": "spergola",
    # Vernaccia cluster + Rossese — distinct from Vermentino
    "vernaccia-nera": "vernaccia-nera",
    "vernaccia-di-san-gimignano": "vernaccia-di-san-gimignano",
    "rossese": "rossese",
    # Greco cluster — Fortana is an Emilian red, totally unrelated
    "fortana": "fortana",
    "greco-bianco": "greco-bianco",
    "greco-nero": "greco-nero",
    # Friulano = Sauvignonasse = Tocai friulano (post-2007 EU rename)
    "tocai-friulano": "friulano",
    "friulano": "friulano",
    "tai": "friulano",
    # Refosco family
    "refosco": "refosco-dal-peduncolo-rosso",
    "refosco-dal-peduncolo-rosso": "refosco-dal-peduncolo-rosso",
    "refosco-nostrano": "refosco-dal-peduncolo-rosso",
    "terrano": "refosco-dal-peduncolo-rosso",     # Refosco d'Istria (DNA)
    "refosk": "refosco-dal-peduncolo-rosso",      # SI "Refošk" — Kras Refosco
    "teran": "refosco-dal-peduncolo-rosso",       # SI "Teran" grape sense (VIVC #9987 syn.
                                                  # TERAN CRVENE); the PDO "Teran" is a
                                                  # separate appellation slug, not a grape
    # Verdicchio = Trebbiano di Soave (DNA-confirmed); regional name preserved as slug.
    "verdicchio": "trebbiano-di-soave",
    "verdicchio-bianco": "trebbiano-di-soave",
    "turbiana": "trebbiano-di-soave",             # Lugana synonym for the same grape
    # Calabrese = Nero d'Avola (DNA-confirmed); fold the Sicilian
    # synonym to the internationally recognised canonical.
    "calabrese": "nero-davola",
    # Cococciola — distinct Abruzzese white, not Bombino Bianco
    "cococciola": "cococciola",
    # Mantonico bianco — distinct Calabrian white, not Montonico bianco
    "mantonico-bianco": "mantonico",
    "mantonico": "mantonico",
    # Manzoni Bianco — distinct Veneto cross (Riesling × Pinot Bianco)
    "manzoni-bianco": "manzoni-bianco",
    # Molinara — distinct Veronese red (Valpolicella blend)
    "molinara": "molinara",
    # Pampanuto / Pampanino — Apulian local synonym for Bombino Bianco
    "pampanuto": "pagadebiti",
    "pampanino": "pagadebiti",
    # Serbina — distinct (fuzzy mismatched to corbeau)
    "serbina": "serbina",
    # Neretto di Bairo — distinct Piemonte red, not Chatus
    "neretto-di-bairo": "neretto-di-bairo",
    # Malvasia nera di Basilicata — distinct, not Tempranillo
    "malvasia-nera-di-basilicata": "malvasia-nera-di-basilicata",
    # Moscato rosa — distinct from Moscato à petits grains rosés
    "moscato-rosa": "moscato-rosa",
    "rosen-muskateller": "moscato-rosa",
    # Pignoletto — distinct Emilian white (Grechetto Gentile DNA)
    "pignoletto": "pignoletto",
    # Veltliner — IT label for Grüner Veltliner
    "veltliner": "gruner-veltliner",
    "gruner-veltliner": "gruner-veltliner",
    # Misc distinct varieties pulled into wrong umbrellas
    "marzemino": "marzemino",
    "marzemina-bianca": "marzemina-bianca",
    "ciliegiolo": "ciliegiolo",
    "tintilia": "tintilia-del-molise",
    "tintilia-del-molise": "tintilia-del-molise",
    "piedirosso": "piedirosso",
    "bombino-nero": "bombino-nero",
    "minutolo": "minutolo",
    "quagliano": "quagliano",
    "negrara": "negrara",
    "negretto": "negretto",
    "bonarda": "bonarda",
    "croatina": "croatina",
    "turca": "turca",
    "piccola-nera": "piccola-nera",
    "neretta-cuneese": "neretta-cuneese",
    "cortese": "cortese",
    "gaglioppo": "gaglioppo",
    "avana": "avana",
    "avanà": "avana",
    "pavana": "pavana",
    "franconia": "franconia",                    # Friulian name for Blaufränkisch
    "grillo": "grillo",
    "albana": "albana",
    "albanello": "albanello",
    "perera": "perera",
    "piculit-neri": "piculit-neri",
    "damaschino": "damaschino",
    "canina-nera": "canina-nera",
    "melara": "melara",
    "montu": "montu",
    "montù": "montu",
    "verdeca": "verdeca",
    "verdea": "verdea",
    "verdese": "verdese",
    "bian-ver": "bian-ver",
    "tocai-rosso": "grenache",                   # = Garnacha (DNA-confirmed)
    "fertilia": "fertilia",
    "termarina": "termarina",
    "maresco": "maresco",
    "albarola": "albarola",
    "cabernet-carbon": "cabernet-carbon",
    "viogner": "viognier",                       # IT spelling drift
    # Malvasia cluster — multiple distinct cultivars sharing the name
    "malvasia-istriana": "malvasia-istriana",
    "malvasia-bianca-lunga": "malvasia-bianca-lunga",
    "malvasia-bianca-di-candia": "malvasia-di-candia",
    "malvasia-di-candia": "malvasia-di-candia",
    "malvasia-di-candia-aromatica": "malvasia-di-candia-aromatica",
    "malvasia-nera-di-brindisi": "malvasia-nera-di-brindisi",
    "malvasia-nera-lunga": "malvasia-nera-lunga",
    "malvasia-bianca-di-basilicata": "malvasia-di-basilicata",
    "malvasia-di-basilicata": "malvasia-di-basilicata",
    "malvasia-del-lazio": "malvasia-del-lazio",
    "malvasia-di-lipari": "malvasia-di-lipari",
    "malvasia-moscata": "malvasia-moscata",
    "malvoisier": "malvasia-bianca-lunga",        # synonym pair in IT
    "malvoisie": "malvasia-di-candia",            # synonym pair in IT
    # ----- IT MASAF-disciplinare varieties. Italian wine grapes the
    # EU-OJ documento unico never carried (the wine is a no-publication
    # stub), so they never reached the VIVC-seeded vocabulary. Surfaced
    # by scripts/it/02f_extract_masaf.py into
    # raw/it/extraction-unknowns-masaf.json; each is a registro-listed
    # variety. Spelling / regional-name variants fold to the canonical.
    "barbera": "barbera",
    "monica": "monica",
    "giro": "giro",
    "uva-rara": "uva-rara",
    "negroamaro": "negroamaro",
    "nero-di-troia": "nero-di-troia",
    "vespolina": "vespolina",
    "rondinella": "rondinella",
    "raboso": "raboso",
    "raboso-piave": "raboso-piave",
    "raboso-veronese": "raboso-veronese",
    "ughetta": "ughetta",
    "grignolino": "grignolino",
    "canaiolo-nero": "canaiolo-nero",
    "susumaniello": "susumaniello",
    "sciascinoso": "sciascinoso",
    "schiava": "schiava",
    "schiava-gentile": "schiava-gentile",
    "schiava-grossa": "schiava-grossa",
    "schiava-grigia": "schiava-grigia",
    "nerello-mascalese": "nerello-mascalese",
    "nerello-cappuccio": "nerello-cappuccio",
    "frappato": "frappato",
    "corvina": "corvina",
    "corvinone": "corvinone",
    "ancellotta": "ancellotta",
    "rebo": "rebo",
    "perricone": "perricone",
    "notardomenico": "notardomenico",
    "cesanese": "cesanese",
    "cesanese-di-affile": "cesanese-di-affile",
    "cesanese-comune": "cesanese-comune",
    "malvasia-di-schierano": "malvasia-di-schierano",
    "groppello": "groppello",
    "casavecchia": "casavecchia",
    "teroldego": "teroldego",
    "pelaverga": "pelaverga",
    "pelaverga-piccolo": "pelaverga-piccolo",
    "lagrein": "lagrein",
    "schioppettino": "schioppettino",
    "pallagrello-nero": "pallagrello-nero",
    "oseleta": "oseleta",
    "rossignola": "rossignola",
    "gamba-rossa": "gamba-rossa",
    "nero-buono": "nero-buono",
    "semidano": "semidano",
    "nuragus": "nuragus",
    "ansonica": "ansonica",
    "inzolia": "inzolia",
    "bianco-di-alessano": "bianco-di-alessano",
    "moscatello-selvatico": "moscatello-selvatico",
    "verduzzo-friulano": "verduzzo-friulano",
    "pecorino": "pecorino",
    "francavilla": "francavilla",
    "catarratto": "catarratto",
    "picolit": "picolit",
    "incrocio-manzoni": "incrocio-manzoni",
    "biancolella": "biancolella",
    "nascetta": "nascetta",
    "vespaiolo": "vespaiolo",
    "ribolla-gialla": "ribolla-gialla",
    "durella": "durella",
    "erbaluce": "erbaluce",
    "ortrugo": "ortrugo",
    "vernaccia-di-oristano": "vernaccia-di-oristano",
    "invernenga": "invernenga",
    "lumassina": "lumassina",
    "catalanesca": "catalanesca",
    "guardavalle": "guardavalle",
    "bianchello": "bianchello",
    "uva-di-troia": "nero-di-troia",            # = Nero di Troia (modern name)
    "bombino": "bombino-bianco",                # bare "Bombino" in Lazio = Bombino bianco
    "canaiolo": "canaiolo-nero",
    "pignatello": "perricone",                  # disciplinari: "Pignatello o Perricone"
    "insolia": "inzolia",
    "negro-amaro": "negroamaro",
    "sussumariello": "susumaniello",
    "corvina-veronese": "corvina",
    "notar-domenico": "notardomenico",
    "bianco-d-alessano": "bianco-di-alessano",
    # ----- AT EUR-Lex Einziges-Dokument varieties. Austrian wine grapes
    # the EU single document lists in section 7 ("Keltertraubensorten")
    # that VIVC's FR/ES/PT/IT seed never carried. Surfaced by
    # scripts/at/02_extract_pliegos.py into raw/at/extraction-unknowns.json;
    # German synonyms / regional names fold to the canonical slug.
    "zweigelt": "zweigelt",
    "blauer-zweigelt": "zweigelt",
    "rotburger": "zweigelt",                    # Zweigelt's breeder name
    "sankt-laurent": "sankt-laurent",
    "st-laurent": "sankt-laurent",
    "neuburger": "neuburger",
    "scheurebe": "scheurebe",
    "samling-88": "scheurebe",                  # Sämling 88 = Scheurebe
    "blauer-wildbacher": "blauer-wildbacher",
    "wildbacher": "blauer-wildbacher",
    "bouvier": "bouvier",
    "goldburger": "goldburger",
    "rathay": "rathay",
    "blutenmuskateller": "blutenmuskateller",
    "grauburgunder": "pinot-gris",              # German name for Pinot Gris
    # ----- SI EUR-Lex Enotni-dokument varieties. Slovenian wine grapes
    # the EU single document lists that the FR/ES/PT/IT/AT seed never
    # carried. Surfaced by scripts/si/02_extract_pliegos.py into
    # raw/si/extraction-unknowns.json. The exact-match aliases also
    # pre-empt the fuzzy fallback's false positives (kraljevina and
    # ranfol are distinct varieties, not Portugieser / Savagnin rose).
    "zametovka": "zametovka",                   # Žametovka / Žametna črnina
    "zametna-crnina": "zametovka",
    "modra-kavcina": "zametovka",                # Modra kavčina = Žametovka (DNA)
    "kraljevina": "kraljevina",                 # white SI/HR variety
    "ranfol": "ranfol",                         # white SI/HR variety
    "rumeni-plavec": "rumeni-plavec",            # Rumeni plavec
    "sentlovrenka": "sankt-laurent",            # Slovenian name for Sankt Laurent
    "chardonay": "chardonnay",                  # SI Enotni-dokument typo (Cviček)
}

# Default colour for each well-known variety. When the parser extracts a
# slug that ends in `-<default-colour>`, we drop the suffix — cahiers
# usually omit the colour qualifier when it's the default (writing
# "chenin B" not "chenin blanc B"), but if one ever spells it out we
# still want a single canonical slug. Varieties whose bare slug is
# ambiguous between cultivars (`pinot-noir / pinot-blanc / pinot-gris`)
# are absent. Varieties whose bare slug denotes the dominant colour AND
# have sibling colour mutations as separate cultivars (grenache, grolleau,
# merlot) ARE listed: the verbose form "Grenache Noir" folds to the bare
# canonical, and the distinct mutations (`-blanc`, `-gris`) stay separate
# because their suffix ≠ the default.
DEFAULT_COLOUR: dict[str, str] = {
    "chardonnay": "blanc",
    "chenin": "blanc",
    "muscadelle": "blanc",
    "melon": "blanc",
    "viognier": "blanc",
    "marsanne": "blanc",
    "roussanne": "blanc",
    "semillon": "blanc",
    "vermentino": "blanc",
    "bourboulenc": "blanc",
    "ugni-blanc": "blanc",  # already canonical with the suffix
    "aligote": "blanc",
    "savagnin": "blanc",
    "altesse": "blanc",
    "jacquere": "blanc",
    "petit-manseng": "blanc",
    "gros-manseng": "blanc",
    "courbu": "blanc",
    "merlot": "noir",
    "grenache": "noir",
    "grolleau": "noir",
    "cabernet-sauvignon": "noir",
    "cabernet-franc": "noir",
    "syrah": "noir",
    "gamay": "noir",
    "mourvedre": "noir",
    "carmenere": "noir",
    "petit-verdot": "noir",
    "cot": "noir",
    "tannat": "noir",
    "negrette": "noir",
    "fer": "noir",
    "duras": "noir",
    "braucol": "noir",
    "nielluccio": "noir",
    "sciacarello": "noir",
    "poulsard": "noir",
    "trousseau": "noir",
    "mondeuse": "noir",
    "persan": "noir",
    # ----- ES varieties (single-colour mutation only) -----
    "tempranillo": "noir",
    "graciano": "noir",
    "bobal": "noir",
    "mencia": "noir",
    "monastrell": "noir",   # routed to mourvedre via GRAPE_ALIAS, but the
                            # raw slug may also surface in audits
    "alicante-bouschet": "noir",
    "albarino": "blanc",
    "godello": "blanc",
    "verdejo": "blanc",
    "treixadura": "blanc",
    "albillo": "blanc",
    "airen": "blanc",
    "palomino": "blanc",
    "pedro-ximenez": "blanc",
    "macabeu": "blanc",
    "xarello": "blanc",
    "parellada": "blanc",
    "torrontes": "blanc",
    "loureira": "blanc",
    "alarije": "blanc",
    "merseguera": "blanc",
    "moll": "blanc",
    "planta-nova": "blanc",
    "moscatel-de-alejandria": "blanc",
    "muscat-d-alexandrie": "blanc",
    "hondarrabi-zuri": "blanc",
    "hondarrabi-beltza": "noir",
    # ----- IT regional varieties (single-colour mutation only) -----
    # Reds
    "lambrusco": "noir",
    "lambrusco-barghi": "noir",
    "lambrusco-salamino": "noir",
    "lambrusco-grasparossa": "noir",
    "lambrusco-maestri": "noir",
    "lambrusco-di-sorbara": "noir",
    "lambrusco-foglia-frastagliata": "noir",
    "lacrima": "noir",
    "corinto-nero": "noir",
    "sangiovese": "noir",
    "rossola-nera": "noir",
    "pignola-valtellinese": "noir",
    "pignolo": "noir",
    "moscato-di-scanzo": "noir",
    "pugnitello": "noir",
    "vernaccia-nera": "noir",
    "rossese": "noir",
    "fortana": "noir",
    "greco-nero": "noir",
    "marzemino": "noir",
    "ciliegiolo": "noir",
    "tintilia-del-molise": "noir",
    "piedirosso": "noir",
    "bombino-nero": "noir",
    "quagliano": "noir",
    "negrara": "noir",
    "negretto": "noir",
    "bonarda": "noir",
    "croatina": "noir",
    "turca": "noir",
    "piccola-nera": "noir",
    "neretta-cuneese": "noir",
    "gaglioppo": "noir",
    "avana": "noir",
    "pavana": "noir",
    "franconia": "noir",
    "piculit-neri": "noir",
    "canina-nera": "noir",
    "fertilia": "noir",
    "termarina": "noir",
    "refosco-dal-peduncolo-rosso": "noir",
    "cabernet-carbon": "noir",
    "malvasia-nera-di-brindisi": "noir",
    "malvasia-nera-lunga": "noir",
    # Whites
    "trebbiano-romagnolo": "blanc",
    "trebbiano-di-soave": "blanc",
    "trebbiano-modenese": "blanc",
    "trebbiano-spoletino": "blanc",
    "trebbiano-abruzzese": "blanc",
    "trebbiano-giallo": "blanc",
    "coda-di-volpe": "blanc",
    "falanghina": "blanc",
    "passerina": "blanc",
    "biancame": "blanc",
    "montonico": "blanc",
    "welschriesling": "blanc",
    "moscato-giallo": "blanc",
    "garganega": "blanc",
    "glera-lunga": "blanc",
    "spergola": "blanc",
    "vernaccia-di-san-gimignano": "blanc",
    "greco-bianco": "blanc",
    "friulano": "blanc",
    "pignoletto": "blanc",
    "gruner-veltliner": "blanc",
    "marzemina-bianca": "blanc",
    "minutolo": "blanc",
    "cortese": "blanc",
    "grillo": "blanc",
    "albana": "blanc",
    "albanello": "blanc",
    "perera": "blanc",
    "damaschino": "blanc",
    "melara": "blanc",
    "montu": "blanc",
    "verdeca": "blanc",
    "verdea": "blanc",
    "verdese": "blanc",
    "bian-ver": "blanc",
    "maresco": "blanc",
    "albarola": "blanc",
    "malvasia-istriana": "blanc",
    "malvasia-bianca-lunga": "blanc",
    "malvasia-di-candia": "blanc",
    "malvasia-di-candia-aromatica": "blanc",
    "malvasia-di-basilicata": "blanc",
    "malvasia-del-lazio": "blanc",
    "malvasia-di-lipari": "blanc",
    "malvasia-moscata": "blanc",
    "cococciola": "blanc",
    "mantonico": "blanc",
    "neretto-di-bairo": "noir",
    "malvasia-nera-di-basilicata": "noir",
    "moscato-rosa": "rose",
    "manzoni-bianco": "blanc",
    "molinara": "noir",
    "serbina": "noir",
    # IT MASAF-disciplinare varieties (see the matching GRAPE_ALIAS block).
    "barbera": "noir",
    "monica": "noir",
    "giro": "noir",
    "uva-rara": "noir",
    "negroamaro": "noir",
    "nero-di-troia": "noir",
    "vespolina": "noir",
    "rondinella": "noir",
    "raboso": "noir",
    "raboso-piave": "noir",
    "raboso-veronese": "noir",
    "ughetta": "noir",
    "grignolino": "noir",
    "canaiolo-nero": "noir",
    "susumaniello": "noir",
    "sciascinoso": "noir",
    "schiava": "noir",
    "schiava-gentile": "noir",
    "schiava-grossa": "noir",
    "schiava-grigia": "noir",
    "nerello-mascalese": "noir",
    "nerello-cappuccio": "noir",
    "frappato": "noir",
    "corvina": "noir",
    "corvinone": "noir",
    "ancellotta": "noir",
    "rebo": "noir",
    "perricone": "noir",
    "notardomenico": "noir",
    "cesanese": "noir",
    "cesanese-di-affile": "noir",
    "cesanese-comune": "noir",
    "malvasia-di-schierano": "noir",
    "groppello": "noir",
    "casavecchia": "noir",
    "teroldego": "noir",
    "pelaverga": "noir",
    "pelaverga-piccolo": "noir",
    "lagrein": "noir",
    "schioppettino": "noir",
    "pallagrello-nero": "noir",
    "oseleta": "noir",
    "rossignola": "noir",
    "gamba-rossa": "noir",
    "nero-buono": "noir",
    "semidano": "blanc",
    "nuragus": "blanc",
    "ansonica": "blanc",
    "inzolia": "blanc",
    "bianco-di-alessano": "blanc",
    "moscatello-selvatico": "blanc",
    "verduzzo-friulano": "blanc",
    "pecorino": "blanc",
    "francavilla": "blanc",
    "catarratto": "blanc",
    "picolit": "blanc",
    "incrocio-manzoni": "blanc",
    "biancolella": "blanc",
    "nascetta": "blanc",
    "vespaiolo": "blanc",
    "ribolla-gialla": "blanc",
    "durella": "blanc",
    "erbaluce": "blanc",
    "ortrugo": "blanc",
    "vernaccia-di-oristano": "blanc",
    "invernenga": "blanc",
    "lumassina": "blanc",
    "catalanesca": "blanc",
    "guardavalle": "blanc",
    "bianchello": "blanc",
    # ----- AT Einziges-Dokument varieties (see the matching GRAPE_ALIAS
    # block).
    "zweigelt": "noir",
    "sankt-laurent": "noir",
    "blauer-wildbacher": "noir",
    "rathay": "noir",
    "neuburger": "blanc",
    "scheurebe": "blanc",
    "bouvier": "blanc",
    "goldburger": "blanc",
    "blutenmuskateller": "blanc",
    # SI Enotni-dokument varieties
    "zametovka": "noir",
    "kraljevina": "blanc",
    "ranfol": "blanc",
    "rumeni-plavec": "blanc",
}

# Slugs that are pure boilerplate after stop-word filtering and should be
# discarded entirely.
GRAPE_BLOCKLIST = {
    "pinot", "blanc", "ugni", "marie", "precoce", "tardif", "grise",
    "noir", "rouge", "rose", "gris",
    # Composite AOC-name + grape leaks that the 5-token name walker
    # produced before _HARD_STOP gained AOC-fragment tokens. Listed here
    # explicitly so re-running stage 02b doesn't re-mint stub Wikipedia
    # entries for them. If a new leak shape appears, surface it via
    # `scripts/audit_grape_typos.py` and add it here.
    "aoc-languedoc-assyrtiko",
    "aoc-languedoc-vermentino",
    "blanc-alicante-henri-bouschet",
    "blanc-clairette-rose",
    "blanc-fume-de-pouilly-sauvignon",
    "cabrieres-morrastel",
    "cotes-du-roussillon-villages-mourvedre",
    "gamay-cabernet-sauvignon",
    "pouilly-sur-loire-chasselas",
    "rimage-counoise",
    "rose-d-anjou-cabernet-franc",
    "saint-saturnin-grenache",
    "tuile-clairette-rose",
    "vic-bilh-suivie-de-la-manseng",
    "abymes-petite-sainte-marie",
    # Source-ambiguity (drome cahier line: "téoulier N, terret blanc gris G,
    # terret noir N" — single colour code spans two grapes due to a missing
    # comma between `terret blanc` and `gris`). Drop rather than alias.
    "terret-blanc-gris",
    # ----- FR cahier phrase fragments (not grape names) -----
    "grains",                              # fragment of "à petits grains"
    "petit",                               # fragment of "petit X"
    "petit-grains-blancs-roses",           # phrase fragment
    "interet-a-fin-coliris",               # "intérêt à fin coliris" regulation phrase
    "nom-de-lieu-dit-auxerrois",           # "nom de lieu-dit: Auxerrois" field label
    "selection-de-gewurztraminer",         # phrase, not a variety
    "originaires-de-l-aire-i",             # "originaires de l'aire I" — phrase fragment
    "callum",                              # OCR/stray-word artefact
    # ----- ES pliego boilerplate -----
    "otras-variedades",                    # ES heading "Otras variedades"
    "ourense",                             # Galician province name leaking from headers
    "val-de-mino",                         # Val de Miño — geographic name
    # ----- PT caderno boilerplate / place names -----
    "oiv",                                 # institutional acronym (Organisation Intl du Vin)
    "s-mamede",                            # São Mamede — geographic
    "setubal",                             # Setúbal DOC name (variety is Castelão = `castelao`)
    "palmela",                             # Palmela DOC name (variety is Castelão = `castelao`)
    "terras-de-lafoes",                    # Terras de Lafões DOC name
    # `brun argenté N` (Rasteau & Rasteau Tranquille) — running page-header
    # "Vins doux naturels susceptibles de bénéficier des mentions …"
    # splits the words and the back-walker picks up only `argenté`. The
    # page-header regex above catches the simple single-line case; this
    # blocklist line is the safety net for the multi-line wrap form.
    "argente",
    # Bare `Tinta` in PT IVV-table format — the parser strips the second
    # token (Tinta Roriz / Tinta Negra / Tinta Carvalha) and leaves "Tinta"
    # standalone. Seen in Açores (Tinta-Roriz row), Duriense, Madeira.
    # Never a real grape on its own; always a parse artefact.
    "tinta",
}

# Lines we strip before tokenising — these are list-headers and connector
# phrases that otherwise leak into grape names when section V is reflowed
# from PDF.
_HEADER_STRIP = re.compile(
    r"c[ée]pages?\s+(?:principaux|accessoires|principal|accessoire)\s*:?"
    r"|vari[ée]t[ée]s?\s+(?:«\s*)?d['’]int[ée]r[êe]t\s+[àa]\s+fin\s+d['’]adaptation(?:\s*»)?\s*:?"
    r"|c[ée]pages?\s+suivants?\s*:?"
    r"|seuls?\s+c[ée]pages?"
    r"|encep[ae]gement\s*:?",
    re.IGNORECASE,
)

_PAREN_RE = re.compile(r"\([^)]*\)")
_DENOM_RE = re.compile(r"d[ée]nomm[ée](?:e|s)?\s+localement[^,;]*", re.IGNORECASE)
_OU_ALIAS_RE = re.compile(r"\s+ou\s+[a-zà-ÿ\-' ]+", re.IGNORECASE)

# Word = a letter run; apostrophes act as separators so `l'ensemble` →
# ["l", "ensemble"] rather than a single welded "lensemble" token.
_WORD_RE = re.compile(r"[a-zà-ÿ][a-zà-ÿ\-]*", re.IGNORECASE)
_COLOUR_RE = re.compile(r"\b(B|N|G|Rs|Rg)\b")

# Words that immediately terminate a grape-name candidate when walking
# backwards from the colour code. These never occur inside a varietal name.
_HARD_STOP = {
    "et", "ou", "en", "issus", "issu", "issue", "issues", "sont", "est",
    "vins", "vin", "raisin", "raisins", "vifa",
    "cépage", "cepage", "cépages", "cepages",
    "principal", "principaux", "accessoire", "accessoires",
    "variété", "variete", "variétés", "varietes",
    "ensemble", "proportion", "complémentaire", "complementaire",
    "habilité", "habilite", "habilités", "habilites",
    "convention", "appellation", "mention", "mentions",
    "pour", "sous", "réserve", "reserve",
    "seul", "seuls", "exclusivement", "suivants", "suivant", "suivantes",
    "tels", "telles", "tel", "telle",
    "savoir", "savoirs", "ainsi", "notamment", "selon",
    "présent", "présents", "présente", "présentes",
    # IGP cahiers use phrasing like "produits à partir des cépages X" or
    # "cépages secondaires" / "variétés d'innovation". These prefixes
    # leak into grape names without these stopwords.
    "produits", "produit", "partir", "secondaires", "secondaire",
    "innovation", "innovations",
    # Wine-style adjectives that occasionally show up in cahiers' header
    # phrases ("vins blancs primeurs sont issus..."). They never form part
    # of a grape name.
    "mousseux", "tranquille", "tranquilles", "primeur", "primeurs",
    "moelleux", "liquoreux", "doux", "secs", "sec",
    "jaune", "jaunes", "paille",
    "vendanges", "tardives", "nobles",
    # Sub-region / classification / indication boilerplate.
    "indication", "indications", "dénomination", "denomination",
    "dénominations", "denominations", "géographique", "geographique",
    "géographiques", "geographiques",
    "qualité", "qualite", "supérieur", "superieur", "supérieure", "superieure",
    "nouveau", "nouvelle", "nouveaux", "nouvelles",
    "bénéficier", "beneficier", "bénéfice", "benefice",
    # Months and years occasionally precede grape names (e.g. "31 juillet
    # 2020 : pinot noir N").
    "janvier", "février", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "août", "aout", "septembre", "octobre", "novembre", "décembre", "decembre",
}

# Words that are valid INSIDE a grape name (e.g. "muscat à petits grains",
# "petite sainte-marie", "camaralet de Lasseube") but never anchor it. We
# trim them off the leading edge of the matched name.
_SOFT_STOP = {
    "de", "du", "des", "le", "la", "les", "à", "a", "aux", "au",
    "un", "une", "l", "d", "blancs", "rouges", "rosés", "roses",
}

# Sub-list role headers and the role label they imply.
_ROLE_PATTERNS = [
    (re.compile(r"c[ée]pages?\s+(?:principaux|principal)\b", re.IGNORECASE), "principal"),
    (re.compile(r"c[ée]pages?\s+(?:accessoires?|accessoire)\b", re.IGNORECASE), "accessory"),
    (
        re.compile(r"vari[ée]t[ée]s?\s+(?:«\s*)?d['’]int[ée]r[êe]t\s+[àa]\s+fin\s+d['’]adaptation", re.IGNORECASE),
        "observation",
    ),
    (re.compile(r"seul\s+c[ée]page", re.IGNORECASE), "principal"),
    (re.compile(r"exclusivement\s+(?:du|des|issus\s+du|issus\s+des)\s+c[ée]pages?", re.IGNORECASE), "principal"),
]


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def _clean_grape_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"\s+", " ", name)
    # drop possessive/article remnants leaking from the preceding clause
    name = re.sub(r"^(?:et|ou|de|du|des|le|la|les|un|une)\s+", "", name)
    return name.strip(" -'’")


def _canonical_slug(name: str) -> str:
    s = slugify(name)
    s = GRAPE_ALIAS.get(s, s)
    # Strip a redundant colour suffix when it matches the variety's default
    # ("merlot noir" → "merlot", "chenin blanc" → "chenin"). Varieties
    # missing from DEFAULT_COLOUR keep the suffix because the colour
    # distinguishes a real INAO-registered mutation.
    for suf in ("-blanc", "-noir", "-gris", "-rose", "-rouge"):
        if s.endswith(suf):
            stem = s[: -len(suf)]
            if DEFAULT_COLOUR.get(stem) == suf[1:]:
                return stem
    return s


def _name_from_words(words: list[str]) -> str | None:
    """Walk backwards through a list of words to recover a grape name.

    Hard stopwords terminate; soft stopwords are valid in the middle of
    a name (e.g. "muscat à petits grains") but get trimmed from the
    leading edge. Names cap at 5 tokens.
    """
    if not words:
        return None
    picked: list[str] = []
    for w in reversed(words):
        wl = w.lower()
        if wl in _HARD_STOP:
            break
        picked.append(wl)
        if len(picked) >= 5:
            break
    picked.reverse()
    while picked and picked[0] in _SOFT_STOP:
        picked.pop(0)
    if not picked:
        return None
    name = _clean_grape_name(" ".join(picked))
    return name if len(name) >= 3 else None


def _tokenise_role_chunk(chunk: str) -> list[dict]:
    """Pull every `<name> <colour>` token from a role sub-list body.

    Walks left-to-right, anchoring on each colour code (`B|N|G|Rs|Rg`)
    and collecting the preceding name words. This makes the parser robust
    to missing punctuation between adjacent entries (e.g. INAO occasionally
    drops a comma: `castets N marselan N`).
    """
    chunk = _DENOM_RE.sub("", chunk)
    chunk = _PAREN_RE.sub("", chunk)
    chunk = _OU_ALIAS_RE.sub("", chunk)
    chunk = _HEADER_STRIP.sub("", chunk)
    chunk = re.sub(r"\s+", " ", chunk)

    # Local import to avoid the grape_entity ↔ grape_lexicon circular —
    # `grape_entity` pulls GRAPE_ALIAS/DEFAULT_COLOUR/slugify from here.
    from _lib.grape_entity import match_variety  # noqa: PLC0415

    out: list[dict] = []
    seen: set[str] = set()
    cursor = 0
    for m in _COLOUR_RE.finditer(chunk):
        head = chunk[cursor : m.start()]
        # Don't cross a top-level list separator backwards. French
        # guillemets «» also terminate the scope — they bracket DGC names
        # in the Alsace cahier's encépagement table (`« Bergheim »
        # gewurztraminer Rs`), and crossing them would yield bogus
        # `bergheim-gewurztraminer` slugs.
        head = re.split(r"[,;:«»]|\s+et\s+", head)[-1]
        words = _WORD_RE.findall(head)
        name = _name_from_words(words)
        cursor = m.end()
        if not name:
            continue
        colour = COLOUR_CODES.get(m.group(1), "")
        # FR convention drops bare colour-adjective tokens (`rose`,
        # `blanc`, …) via GRAPE_BLOCKLIST applied to the *input*. The
        # back-walker occasionally lands on a bare colour word when the
        # cahier wraps a name across a line ("Clairette / rose Rs"); we
        # must reject before vocab lookup or VIVC's bare-name synonyms
        # (e.g. `rose` → `nebbiolo`) would falsely match.
        if slugify(name) in GRAPE_BLOCKLIST:
            continue
        result = match_variety(name, ambient_colour=colour or None)
        if result is None or result.slug in GRAPE_BLOCKLIST:
            continue
        # FR cahiers anchor on a colour-letter code; the back-walker
        # sometimes grabs a partial token when a variety name wraps
        # across a line ("muscat à petits / grains B" → name="grains").
        # Reject fuzzy fallbacks here — INAO typos belong in GRAPE_ALIAS
        # per the curation guide, not in the fuzzy matcher.
        if result.method.startswith("fuzzy"):
            continue
        if result.slug in seen:
            continue
        seen.add(result.slug)
        out.append({
            "slug": result.slug,
            "name": name,
            "colour": colour or result.colour,
        })
    return out


_PAGE_HEADER_RE = re.compile(
    r"\n\s*Vins\s+"
    r"(?:tranquilles?|mousseux|effervescents?|primeurs?|moelleux|"
    r"liquoreux|doux|jaunes?|sec(?:s)?|"
    r"de\s+paille|de\s+liqueur|doux\s+naturels?)"
    r"\s*\n",
    re.IGNORECASE,
)


def parse_grapes(section_v: str) -> dict:
    """Return {principal, accessory, observation, all} from a section V body.

    Each list contains {slug, name, colour}. `all` is a deduped union with
    role attached (preferring principal > accessory > observation).
    """
    if not section_v or not section_v.strip():
        return {"principal": [], "accessory": [], "observation": [], "all": []}

    # Strip running page-headers that get spliced mid-clause when section V
    # spans a PDF page break — e.g. Rasteau's encépagement reads
    # "... brun\n     argenté N (... ou\nVins tranquilles\n     vaccarèse) ..."
    # which would otherwise break the back-walker between `brun` and
    # `argenté` (vins/tranquilles are both _HARD_STOP tokens).
    section_v = _PAGE_HEADER_RE.sub("\n", section_v)
    text = re.sub(r"\s+", " ", section_v)

    # Truncate at the next sub-section header. Section V starts with
    # "1°- Encépagement" and continues with "2°- Règles de proportion à
    # l'exploitation" / "3°- ..." — the role lists live only inside (1°),
    # so anything past the first 2°/3° marker is noise that would mint
    # bogus role-headers (e.g. "l'ensemble des cépages principaux").
    cut_m = re.search(
        r"\b2\s*°|\b3\s*°|r[èe]gles?\s+de\s+proportion",
        text,
        re.IGNORECASE,
    )
    if cut_m:
        text = text[: cut_m.start()]

    offsets: list[tuple[int, str]] = []
    for pat, role in _ROLE_PATTERNS:
        for m in pat.finditer(text):
            offsets.append((m.end(), role))
    offsets.sort()

    chunks: list[tuple[str, str]] = []
    if not offsets:
        chunks.append(("principal", text))
    else:
        if offsets[0][0] > 0:
            head = text[: offsets[0][0]]
            if any(c.isalpha() for c in head):
                chunks.append(("principal", head))
        for i, (start, role) in enumerate(offsets):
            end = offsets[i + 1][0] if i + 1 < len(offsets) else len(text)
            chunks.append((role, text[start:end]))

    by_role: dict[str, list[dict]] = {"principal": [], "accessory": [], "observation": []}
    seen: set[str] = set()
    for role, body in chunks:
        for tok in _tokenise_role_chunk(body):
            if tok["slug"] in seen:
                continue
            seen.add(tok["slug"])
            by_role[role].append(tok)

    flat = (
        [{**t, "role": "principal"} for t in by_role["principal"]]
        + [{**t, "role": "accessory"} for t in by_role["accessory"]]
        + [{**t, "role": "observation"} for t in by_role["observation"]]
    )
    return {**by_role, "all": flat}


# ---- styles ----------------------------------------------------------------

# Canonical style tags, with the regex(es) that imply each one. Order
# matters: `vendanges-tardives` and `grains-nobles` must run before plain
# `sweet`, otherwise we'd lose the specific mention.
STYLE_PATTERNS: list[tuple[str, list[re.Pattern]]] = [
    ("red", [re.compile(r"\brouges?\b", re.IGNORECASE)]),
    ("white", [re.compile(r"\bblancs?\b", re.IGNORECASE)]),
    ("rose", [re.compile(r"\bros[ée]s?\b", re.IGNORECASE)]),
    ("sparkling", [
        re.compile(r"\bmousseux\b", re.IGNORECASE),
        re.compile(r"\beffervescents?\b", re.IGNORECASE),
        re.compile(r"\bp[ée]tillants?\b", re.IGNORECASE),
        re.compile(r"\bperlants?\b", re.IGNORECASE),
        re.compile(r"\bcr[ée]mant\b", re.IGNORECASE),
    ]),
    ("vendanges-tardives", [re.compile(r"\bvendanges?\s+tardives?\b", re.IGNORECASE)]),
    ("grains-nobles", [re.compile(r"\bs[ée]lection\s+de\s+grains\s+nobles\b", re.IGNORECASE)]),
    ("sweet", [
        re.compile(r"\bmoelleux\b", re.IGNORECASE),
        re.compile(r"\bliquoreux\b", re.IGNORECASE),
        re.compile(r"\bdoux\b(?!\s+naturel)", re.IGNORECASE),
    ]),
    ("dry", [re.compile(r"\bsecs?\b(?!\s*-\s*demi)", re.IGNORECASE)]),
    ("vdn", [re.compile(r"\bvins?\s+doux\s+naturels?\b", re.IGNORECASE)]),
    ("vin-de-liqueur", [re.compile(r"\bvins?\s+de\s+liqueur\b", re.IGNORECASE)]),
    ("vin-jaune", [re.compile(r"\bvins?\s+jaunes?\b", re.IGNORECASE)]),
    ("vin-de-paille", [re.compile(r"\bvins?\s+de\s+paille\b", re.IGNORECASE)]),
    ("primeur", [re.compile(r"\bprimeurs?\b", re.IGNORECASE)]),
    ("clairet", [re.compile(r"\bclairets?\b", re.IGNORECASE)]),
    ("tranquille", [re.compile(r"\btranquilles?\b", re.IGNORECASE)]),
]


# Mapping from SIQO `categorie` strings to canonical style tags. The SIQO
# referentiel has multiple rows per appellation, one per category, so this
# is the more reliable signal — section III prose is a sanity check.
CATEGORIE_TO_STYLES: dict[str, list[str]] = {
    "Vin tranquille": ["tranquille"],
    "Vin mousseux": ["sparkling"],
    'Vin mousseux "Crémant"': ["sparkling", "cremant"],
    "Vin doux naturel": ["vdn", "sweet"],
    "Vin de liqueur": ["vin-de-liqueur"],
    "Vin de raisins surmuris": ["sweet"],
    "Vin de triees successives": ["sweet", "grains-nobles"],
    "Vin de sélection de grains nobles": ["grains-nobles", "sweet"],
    "Vin de vendanges tardives": ["vendanges-tardives", "sweet"],
    "Vin primeur": ["primeur"],
    "Vin de paille": ["vin-de-paille", "sweet"],
    "Vin jaune": ["vin-jaune"],
}


def parse_styles(section_iii: str, categories: Iterable[str] = ()) -> list[str]:
    """Return a sorted, deduped list of canonical style tags for an AOC.

    Combines two signals:
      - section III prose (colour adjectives + special mentions);
      - SIQO `categorie` field(s), via CATEGORIE_TO_STYLES.
    """
    found: set[str] = set()
    text = section_iii or ""
    for tag, pats in STYLE_PATTERNS:
        if any(p.search(text) for p in pats):
            found.add(tag)
    for cat in categories:
        for tag in CATEGORIE_TO_STYLES.get(cat.strip(), []):
            found.add(tag)
    # If we have a special mention, the underlying wine is implicitly white
    # in the case of vendanges tardives / grains nobles (always) — but we
    # only add `white` if the section already says `blanc`.
    return sorted(found)
