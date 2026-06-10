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

from unidecode import unidecode

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
    "muscat-blanc-a-petits-grains": "muscat-a-petits-grains",  # spelling variant — same VIVC #8193
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
    "garnacha-tintorera": "alicante-bouschet",  # ES synonym
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
    "pinot-grigio": "pinot-gris",  # Italian name
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
    "goldmuskateller": "moscato-giallo",         # German synonym (≠ Gelber Muskateller, which is Muscat Blanc à Petits Grains — see German section)
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
    # Tuscan natives from the IGT Toscano allegato-1 roster (2026-05-30).
    "abrusco": "abrusco",
    "barsaglina": "barsaglina",
    "bonamico": "bonamico",
    "bracciola-nera": "bracciola-nera",
    "colombana-nera": "colombana-nera",
    "foglia-tonda": "foglia-tonda",
    "groppello-gentile": "groppello-gentile",
    "groppello-di-santo-stefano": "groppello-di-santo-stefano",
    "incrocio-bruni-54": "incrocio-bruni-54",
    "livornese-bianca": "livornese-bianca",
    "orpicchio": "orpicchio",
    "pollera-nera": "pollera-nera",
    "sanforte": "sanforte",
    "vermentino-nero": "vermentino-nero",
    "barbera": "barbera",  # Italian red (used in some DE Sekt)
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
    # `Ranina` is a VIVC-ambiguous synonym name claimed by BOTH Bouvier
    # (VIVC #1625, the Slovenian/Austrian aromatic white) and Portugieser
    # Blau (VIVC #9620, the central-European blue cultivar). Neither
    # VIVC record carries a country-disambiguation flag, so the
    # vocabulary-builder's iteration order arbitrarily binds bare
    # "ranina" to portugais-bleu — which then dedup-collides with the
    # SI Cviček variety list ("Portugalka" → portugais-bleu, then
    # "Ranina - Radgonska ranina" tries head `ranina` first and gets
    # dropped). Force the Slovenian reading: ranina → bouvier.
    "ranina": "bouvier",
    # ----- HR EUR-Lex Jedinstveni-dokument varieties. Croatian wine
    # grapes the EU single document lists that the FR/ES/PT/IT/AT/SI
    # seed never carried. Surfaced by scripts/hr/02_extract_pliegos.py
    # into raw/hr/extraction-unknowns.json. Each alias is grounded in
    # VIVC (Vitis International Variety Catalogue): the prime name's
    # slug is the canonical target; aliases fold local Croatian and
    # synonym spellings onto it.
    "plavac-mali": "plavac-mali",               # VIVC #9252 PLAVAC MALI CRNI (Dalmatian flagship)
    "plavac-mali-crni": "plavac-mali",
    "posip": "posip",                           # VIVC #9601 POŠIP BIJELI (Korčula white)
    "posip-bijeli": "posip",
    "marastina": "marastina",                   # VIVC #7338 MARAŠTINA (= Rukatac, Pavlos / Malvasia del Chianti synonym in Dalmatia)
    "rukatac": "marastina",
    "babic": "babic",                           # VIVC #952 BABIĆ (Šibenik / Primošten red)
    "bogdanusa": "bogdanusa",                   # VIVC #1422 BOGDANUŠA (Hvar white)
    "vugava": "vugava",                         # VIVC #13245 VUGAVA (Vis white; = Bugava)
    "bugava": "vugava",
    "grk": "grk",                               # VIVC #5026 GRK BIJELI (Korčula white)
    "grk-bijeli": "grk",
    "debit": "debit",                           # VIVC #3308 DEBIT (Dalmatian white)
    "trbljan": "trbljan",                       # VIVC #12503 TRBLJAN (= Kuč, Dalmatian white)
    "kuc": "trbljan",
    "tribidrag": "tribidrag",                   # VIVC #17636 TRIBIDRAG (= Crljenak Kaštelanski = Zinfandel = Primitivo)
    "crljenak-kastelanski": "tribidrag",        # Croatian name for the same variety
    "kastelanski-crljenak": "tribidrag",
    "zinfandel": "tribidrag",                   # US/Croatian-origin synonym
    "primitivo": "tribidrag",                   # IT synonym (DNA-equivalent)
    "grasevina": "welschriesling",              # VIVC #13096 WELSCHRIESLING (= Graševina = Laški rizling = Riesling Italico — distinct from Renski rizling / Riesling)
    "laski-rizling": "welschriesling",
    "rizvanac": "muller-thurgau",               # VIVC #8141 MÜLLER-THURGAU; Croatian name
    "malvazija-istarska": "malvazija-istarska", # VIVC #7349 MALVAZIJA ISTARSKA (Istrian white)
    "muskat-zuti": "muskat-zuti",               # VIVC #8242 MUSCAT D'ALEXANDRIE — but the Croatian "Muškat žuti" is the YELLOW (Muscat Lunel) cluster; pinned as its own slug until VIVC reconciliation
    "frankovka": "blaufrankisch",               # VIVC #1459 BLAUFRÄNKISCH; Croatian name for Lemberger/Blaufränkisch
    "skrlet": "skrlet",                         # VIVC #11343 ŠKRLET BIJELI (Moslavina white)
    "skrlet-bijeli": "skrlet",
    "zlahtina": "zlahtina",                     # VIVC #13832 ŽLAHTINA (Krk white)
    "zelenac-slatki": "zelenac-slatki",         # Plešivica
    "kraljevina-crvena": "kraljevina",          # Zagorje
    "moslavac": "furmint",                      # VIVC #4456 FURMINT; Croatian name in Moslavina
    "moslavac-zuti": "furmint",
    "pusipel": "furmint",                       # alternate Croatian name in eastern Slavonia/Međimurje
    "mediteranska-istra": "malvazija-istarska", # source-text typo, occasionally appears (cf. INAO-typo precedent)
    # ----- HU EUR-Lex Egységes-dokumentum varieties. Hungarian wine
    # grapes the EU single document lists in section 7 ("Fontosabb
    # borszőlőfajták") that the FR/ES/PT/IT/AT/SI/HR seed never
    # carried. Surfaced by scripts/hu/02_extract_pliegos.py into
    # raw/hu/extraction-unknowns.json. Hungarian synonyms / regional
    # names fold to the canonical slug; native Hungarian crossings
    # stay on their own slug.
    "harslevelu": "harslevelu",                 # VIVC #5331 HÁRSLEVELŰ (Tokaj signature white)
    "lindenblattrige": "harslevelu",            # German synonym
    "lindeblattrige": "harslevelu",
    "feuilles-de-tilleul": "harslevelu",        # French synonym
    "lipovina": "harslevelu",                   # Slovak synonym
    "olaszrizling": "welschriesling",           # VIVC #13096 WELSCHRIESLING (Hungarian name)
    "olasz-rizling": "welschriesling",
    "nemes-rizling": "welschriesling",
    "rajnai-rizling": "riesling",               # Hungarian name for Riesling
    "tramini": "gewurztraminer",                # Hungarian name for Gewürztraminer
    "kekfrankos": "blaufrankisch",              # Hungarian name for Blaufränkisch
    "kek-frankos": "blaufrankisch",
    "kadarka": "kadarka",                       # VIVC #5734 KADARKA (Hungarian/Bulgarian red)
    "jenei-fekete": "kadarka",                  # Hungarian synonym
    "biborkadarka": "biborkadarka",             # Hungarian crossing (Kadarka × Csókaszőlő)
    "kekoporto": "blauer-portugieser",          # Hungarian for Blauer Portugieser
    "kek-oporto": "blauer-portugieser",
    "portugizer": "blauer-portugieser",
    "blauer-portugieser": "blauer-portugieser",
    "portugieser": "blauer-portugieser",
    "cserszegi-fuszeres": "cserszegi-fuszeres", # native Hungarian crossing
    "irsai-oliver": "irsai-oliver",             # native Hungarian crossing
    "irsai": "irsai-oliver",
    "muskat-oliver": "irsai-oliver",            # synonym
    "zolotis": "irsai-oliver",                  # synonym
    "kiralyleanyka": "feteasca-regala",         # Hungarian "Little Queen" — VIVC #4121 prime FETEASCA REGALA
    "feteasca-regale": "feteasca-regala",
    "danosi-leanyka": "feteasca-regala",
    "galbena-de-ardeal": "feteasca-regala",
    "leanyka": "feteasca-alba",                 # Hungarian — VIVC #4119 prime FETEASCA ALBA
    "leanyszolo": "feteasca-alba",
    "madchentraube": "feteasca-alba",           # German synonym
    "juhfark": "juhfark",                       # native Hungarian (Somló signature white)
    "ezerjo": "ezerjo",                         # native Hungarian (Mór signature white)
    "kolmreifler": "ezerjo",
    "tausendgute": "ezerjo",
    "tausendachtgute": "ezerjo",
    "trummertraube": "ezerjo",
    "korponai": "ezerjo",
    "szadocsina": "ezerjo",
    "szurkebarat": "pinot-gris",                # Hungarian name for Pinot Gris
    "feher-burgundi": "pinot-blanc",            # Hungarian name for Pinot Blanc
    "kek-rulandi": "pinot-noir",                # Hungarian name for Pinot Noir
    "ottonel-muskotaly": "muscat-ottonel",      # Muscat Ottonel
    "muscat-ottonel": "muscat-ottonel",  # VIVC #8246
    "hamburgi-muskotaly": "muscat-hambourg",    # Hungarian for Muscat de Hambourg
    "muscat-de-hamburg": "muscat-hambourg",
    "sarga-muskotaly": "muscat-a-petits-grains",   # Hungarian "Yellow Muscat" = Muscat Lunel / Muscat à petits grains blancs (VIVC #8193)
    "sargamuskotaly": "muscat-a-petits-grains",    # one-word spelling in the termékleírás PDFs (Tokaj, Balatonboglár, …)
    "mátrai-muskotaly": "muscat-a-petits-grains",
    "korai-piros-veltelini": "fruhroter-veltliner",      # Korai piros veltelíni = Frühroter Veltliner
    "kovidinka": "kovidinka",                   # Hungarian — Vojvodina cluster
    "dinka-crvena": "kovidinka",
    "goher": "goher",                           # Gohér — heritage Hungarian white (Zemplén, Balaton)
    "gohier": "goher",
    "banati-rizling": "banati-rizling",         # Bánáti rizling = Banat Riesling / Kreaca, white (Somló)
    "banati": "banati-rizling",
    "csabagyongye": "csabagyongye",             # native Hungarian crossing
    "perle-di-csaba": "csabagyongye",
    "pearl-of-csaba": "csabagyongye",
    "csaba-gyongye": "csabagyongye",
    "zalagyongye": "zalagyongye",               # native Hungarian crossing
    "kunleany": "kunleany",                     # native Hungarian crossing
    "nektar": "nektar",                         # native Hungarian crossing
    "aletta": "aletta",                         # native Hungarian crossing
    "medina": "medina",                         # native Hungarian crossing
    "generosa": "generosa",                     # native Hungarian crossing
    "zenit": "zenit",                           # native Hungarian crossing
    "zeta": "zeta",                             # native Hungarian crossing
    "kabar": "kabar",                           # native Hungarian crossing
    "turan": "turan",                           # native Hungarian crossing
    "csokaszolo": "csokaszolo",                 # native Hungarian (Tokaj-area red)
    "pozsonyi-feher": "pozsonyi-feher",         # native Hungarian (Pozsony / Bratislava white)
    "czetenyi-feher": "pozsonyi-feher",
    "kereklevelu": "chardonnay",                # Hungarian synonym for Chardonnay
    "cabernet-dorsa": "cabernet-dorsa",         # German crossing, used in HU eAmbrosia
    "blauburger": "blauburger",                 # Austrian crossing also used in HU
    # Additional HU varieties surfaced by stage 02 unknowns:
    "zefir": "zefir",                           # Hungarian crossing (white)
    "ezerfurtu": "ezerfurtu",                   # Hungarian "thousand-cluster" white
    "zengo": "zengo",                           # Hungarian crossing
    "alibernet": "alibernet",                   # crossing (Alicante Bouschet × Cabernet Sauvignon)
    "menoire": "menoire",                       # Hungarian crossing (red)
    "arany-sarfeher": "arany-sarfeher",         # native Hungarian (Izsák specialty)
    "izsaki-sarfeher": "arany-sarfeher",        # alias — Izsák regional name
    "huszar-szolo": "huszar-szolo",             # native Hungarian
    "gyongyrizling": "gyongyrizling",           # Hungarian "pearl riesling" crossing
    "kerner": "kerner",                         # German Müller-Thurgau × Trollinger crossing
    "rubintos": "rubintos",                     # Hungarian crossing (red)
    "decsi-szagos": "decsi-szagos",             # Hungarian "Decs perfume" white
    "zold-szagos": "zold-szagos",               # Hungarian "green perfume" white
    "patria": "patria",                         # Hungarian crossing
    "poloskei-muskotaly": "poloskei-muskotaly", # Hungarian Muscat crossing
    "rozalia": "rozalia",                       # Hungarian crossing
    "rozsako": "rozsako",                       # Hungarian crossing
    "viktoria-gyongye": "viktoria-gyongye",     # Hungarian crossing
    "csomor": "csomor",                         # native Hungarian white
    "csomorika": "csomor",                      # diminutive form
    "domina": "domina",                         # German Portugieser × Pinot Noir crossing
    "grasa-de-cotnari": "grasa-de-cotnari",     # Romanian variety, also in HU
    "koverszolo": "koverszolo",                 # native Hungarian (Tokaj-area Grasă)
    "sagrantino": "sagrantino",                 # Italian, used in HU
    "cirfandli": "zierfandler",                 # Hungarian name for Zierfandler (AT Spätrot)
    "piros-cirfandli": "zierfandler",
    "zierfandler": "zierfandler",
    "meszikadar": "meszikadar",                 # Hungarian crossing
    "bakator": "bakator",                       # native Hungarian / Transylvanian family
    "kek-bakator": "bakator",
    "piros-bakator": "bakator",
    "bakar-rozsa": "bakator",
    "bakator-rouge": "bakator",
    "bakatortraube": "bakator",
    "budai-zold": "budai-zold",                 # native Hungarian
    "zold-budai": "budai-zold",
    "budai": "budai-zold",
    "duna-gyongye": "duna-gyongye",             # Hungarian "Pearl of the Danube" crossing
    "pannon-frankos": "blaufrankisch",          # Hungarian Kékfrankos clone, folded
    "jubileum-75": "jubileum-75",               # Hungarian crossing
    "odysseus": "odysseus",                     # Hungarian crossing
    "orpheus": "orpheus",                       # Hungarian crossing
    "zeus": "zeus",                             # Hungarian crossing
    "pintes": "pintes",                         # Hungarian
    "refren": "refren",                         # Hungarian crossing
    "vertes-csillaga": "vertes-csillaga",       # Hungarian crossing
    "vulcanus": "vulcanus",                     # Hungarian crossing
    "szederkenyi-feher": "szederkenyi-feher",   # Hungarian
    "nemet-dinka": "kovidinka",                 # Hungarian "German Dinka" — folded to kovidinka cluster
    "gyudi-feher": "gyudi-feher",               # Hungarian (Pécs)
    "zoldfeher": "zoldfeher",                   # native Hungarian
    "zoldszolo": "zoldfeher",
    "csillam": "csillam",                       # Hungarian crossing
    # ── Romanian (RO) native varieties ────────────────────────────────
    # The upstream slugifier ASCII-folds + kebab-cases, so all alias
    # keys here are ASCII-only. Comments carry the diacritic forms.
    "feteasca-alba": "feteasca-alba",            # VIVC #4119 FETEASCĂ ALBĂ — RO Moldova white (= HU Leányka)
    "feteasca-regala": "feteasca-regala",        # VIVC #4121 FETEASCĂ REGALĂ — RO, Fetească albă × Frâncușă (= HU Királyleányka)
    "feteasca-neagra": "feteasca-neagra",        # VIVC #4120 FETEASCĂ NEAGRĂ — RO native red
    "tamaioasa-romaneasca": "muscat-a-petits-grains",
                                                 # Tămâioasă Românească — VIVC syn. of Muscat à petits grains blancs (#8193)
    "tamaioasa": "muscat-a-petits-grains",       # bare form
    "tamioasa-romaneasca": "muscat-a-petits-grains",  # alt spelling
    "busuioaca-de-bohotin": "busuioaca-de-bohotin",
                                                 # Busuioacă de Bohotin — Moldova native aromatic rosé
    "grasa": "grasa-de-cotnari",                 # bare form
    "babeasca-neagra": "babeasca-neagra",        # VIVC #908 BĂBEASCĂ NEAGRĂ — Moldova red
    "negru-de-dragasani": "negru-de-dragasani",  # Negru de Drăgășani — RO crossing
    "novac": "novac",                            # RO interspecific red — Drăgășani
    "crampoșie-selectionata": "crampoșie-selectionata",  # diacritic form as it arrives from the documento-unic
    "crampoșie": "crampoșie-selectionata",                # bare diacritic form
    "crampoșie-selectionată": "crampoșie-selectionata",   # both -ata/-ată variants seen
    "crampo-ie-selectionata": "crampoșie-selectionata",   # `_grape_entity` slug-key (NFKD-stripped variant)
    "francusa": "francusa",                      # Frâncușă — Cotnari/Iași white
    "galbena-de-odobesti": "galbena-de-odobesti",  # Galbenă de Odobești — Moldova-Vrancea white
    "plavaie": "plavaie",                        # Plăvaie — native RO white (Vrancea)
    "zghihara-de-husi": "zghihara-de-husi",      # Zghihară de Huși — native RO white (Huși)
    "sarba": "sarba",                            # Șarbă — RO crossing (Tămâioasă × Riesling italian)
    "mustoasa-de-maderat": "mustoasa-de-maderat", # Mustoasă de Măderat — native RO white (Banat / Miniș)
    "mustoasa": "mustoasa-de-maderat",
    "iordana": "iordana",                        # Iordană — Transilvania native white
    "majarca-alba": "majarca-alba",              # Majarcă Albă — Banat / Crișana native white
    "raluca": "raluca",                          # RO crossing (Recaș)
    # SCDVV / Romanian breeding-station crossings (1970s–1990s).
    # Iași unless noted; VIVC IDs in DEFAULT_COLOUR comments below.
    "alutus": "alutus",                          # Drăgășani — Băbească Neagră × Saperavi
    "arcas": "arcas",                            # Iași — Cabernet Sauvignon × Băbească Neagră
    "aromat-de-iasi": "aromat-de-iasi",          # Iași — Tămâioasă Românească OP
    "balada": "balada",                          # Iași — Băbească Neagră × Pinot Noir
    "batuta-neagra": "batuta-neagra",            # VIVC #1042 — Moldova native red
    "negru-batut": "batuta-neagra",              # word-order variant — same VIVC accession
    "cadarca": "kadarka",                        # Romanian spelling of Kadarka — fold to existing canonical
    "codana": "codana",                          # Iași/Odobești — Băbească Neagră × Cabernet Sauvignon
    "columna": "columna",                        # Murfatlar — Pinot Gris × Grasă de Cotnari
    "cristina": "cristina",                      # Murfatlar / ICDVV — RO crossing, red (Colinele Dobrogei)
    "donaris": "donaris",                        # Greaca-Giurgiu — Bicane × Muscat Hamburg
    "golia": "golia",                            # Iași — Șarbă × Sauvignon Blanc
    "miorita": "miorita",                        # Odobești-Vrancea — Coarna Albă OP
    "negru-aromat": "negru-aromat",              # Drăgășani — Cabernet Sauvignon OP
    "ozana": "ozana",                            # Iași — Csaba Gyöngye × Afus Ali
    "unirea": "unirea",                          # Iași — Crâmpoșie × Muscat Ottonel
    "babeasca-gri": "babeasca-gri",              # VIVC #842 — Băbească Neagră gris mutation (Odobești 1975)
    "babeasca-gris": "babeasca-gri",             # VIVC prime spelling
    # RO/foreign-language synonyms folded to existing canonicals.
    "rkatsiteli": "rkatsiteli",                  # VIVC #10116 — Georgian white
    "rkatiteli": "rkatsiteli",                   # RO/RU spelling
    "dedali-rkatiteli": "rkatsiteli",            # VIVC syn DEDALI RKATITERLI
    "korolioc-rkatiteli": "rkatsiteli",          # VIVC syn KOROLIOK RKATITELI / COROLIOC
    "schwarzer-kadarka": "kadarka",              # German "black Kadarka"
    "rubinroter-kadarka": "kadarka",             # German "ruby-red Kadarka" — synonym, NOT Bíborkadarka
    "riesling-de-rin": "riesling",               # RO "Rhine Riesling"
    "riesling-de-rhin": "riesling",
    "petit-vidure": "cabernet-sauvignon",        # Bordeaux synonym
    "bourdeos-tinto": "cabernet-sauvignon",      # Spanish synonym
    "affume": "pinot-gris",                      # French Pinot Gris synonym (Affumé)
    "grau-burgunder": "pinot-gris",              # German Pinot Gris synonym
    "grauer-monch": "pinot-gris",                # "Grauer Mönch"
    "pinot-cendre": "pinot-gris",                # French synonym
    "rulander": "pinot-gris",                    # German name
    "blauer-spatburgunder": "pinot-noir",        # German Pinot Noir synonym
    "burgund-mic": "pinot-noir",                 # RO "small Burgundy"
    "burgunder-roter": "pinot-noir",
    "klavner-morillon-noir": "pinot-noir",       # Klävner/Morillon — Austrian synonyms
    "olasz-riesling": "welschriesling",          # Hungarian "Italian Riesling" (space variant)
    "rosetraminer": "gewurztraminer",            # German rose-Traminer synonym
    "savagnin-roz": "gewurztraminer",            # RO "pink Savagnin"
    "konigliche-madchentraube": "feteasca-regala", # German "Royal Madchentraube" — VIVC #4121 syn.
    "konigsast": "feteasca-regala",              # German synonym (VIVC #4121)
    "ktralyleanka": "feteasca-regala",           # corrupt-spelling Királyleányka (seen in Lechința doc)
    "danasana": "feteasca-regala",               # Dănăşană — RO Transylvanian synonym (VIVC #4121)
    "pasareasca-alba": "feteasca-alba",          # RO "white Păsărească" — Leányka/Fetească albă synonym
    "poama-fetei": "feteasca-alba",              # RO "maiden's grape"
    "schwarze-madchentraube": "feteasca-neagra", # German — black Madchentraube
    "poama-fetei-neagra": "feteasca-neagra",
    "pasareasca-neagra": "feteasca-neagra",
    "coada-randunicii": "feteasca-neagra",       # RO "swallow's tail" — local Fetească Neagră synonym
    "tamaioasa-roza": "muscat-a-petits-grains-rouges",  # rose-coloured Tămâioasă = Muscat Rouge de Frontignan
    # Internationally-known varieties on Romanian-language labels —
    # the Romanian spelling-variants land here so they fold to VIVC primes.
    "riesling-italian": "welschriesling",        # Riesling italian = Welschriesling family
    "pinot-gris-rulanda": "pinot-gris",          # RO synonym
    "rulanda": "pinot-gris",                     # RO bare form
    "traminer-rose": "gewurztraminer",           # Traminer roz = rosé-pink Traminer = Gewürztraminer
    "traminer-aromat": "gewurztraminer",         # RO official name (Traminer aromat = Gewürztraminer)
    "traminer-aromat-alb": "gewurztraminer",     # white-form variant on Romanian labels
    # ----- BG (Bulgaria) native varieties + Cyrillic→Latin folds -----
    # Bulgarian native varieties self-canonicalise; the Cyrillic spellings
    # round-trip through unidecode() in slugify() to the same Latin slugs.
    # Cross-language synonyms fold to the existing canonical.
    "mavrud": "mavrud",                           # VIVC #7414 MAVRUD — BG native red
    "shiroka-melnishka-loza": "shiroka-melnishka-loza",  # BG native "broad-leaf Melnik vine"
    "shiroka-melnishka": "shiroka-melnishka-loza",
    "shiroka-melnishka-loza-melnik": "shiroka-melnishka-loza",
    "melnik-1300": "shiroka-melnishka-loza",      # umbrella name on labels
    "rannamelniska-loza": "early-melnik",         # "early Melnik" — Melnik 55 crossing
    "rannna-melniska-loza": "early-melnik",
    "ranna-melnishka-loza": "early-melnik",
    "early-melnik": "early-melnik",               # Мелник 55 (early variant)
    "melnik-55": "early-melnik",
    "melnik-82": "melnik-82",                     # BG Mavrud × Pinot noir crossing
    "melnik-iubileen-1300": "melnik-iubileen-1300",
    "melnishki-rubin": "melnishki-rubin",         # BG crossing (Shiroka × Cabernet)
    "pamid": "pamid",                             # BG native red (Plovdiv basin)
    "dimyat": "dimyat",                           # BG native white (Dunavska / Black Sea)
    "dimiat": "dimyat",                           # alt transliteration
    "cherven-misket": "cherven-misket",           # BG "red Misket" (native white-pink)
    "misket-cherven": "cherven-misket",
    "tamyanka": "muscat-a-petits-grains",         # BG name for Muscat à petits grains blancs (#8193)
    "tamianka": "muscat-a-petits-grains",
    "temenuga": "muscat-a-petits-grains",         # BG synonym (Tamyanka labelled "Temenuga")
    "sandanski-misket": "sandanski-misket",       # BG SW native white
    "misket-sandanski": "sandanski-misket",
    "muskat-sandanski": "sandanski-misket",       # Latin transliteration variant
    "gamza": "kadarka",                           # BG synonym for Kadarka (DNA match)
    "kerasuda": "kerasuda",                       # BG SW native white (Melnik area)
    "keratsuda": "kerasuda",                      # alt transliteration
    "bogdan": "bogdan",                           # BG modern crossing
    "rubin": "rubin",                             # BG Nebbiolo × Syrah crossing
    "ruen": "ruen",                               # BG modern crossing
    "storgozia": "storgozia",                     # BG modern crossing
    "kaylashki-misket": "kaylashki-misket",       # BG modern crossing (white)
    "varnenski-misket": "varnenski-misket",       # BG Varna-area Misket
    # Internationally-known varieties transliterated from Cyrillic via
    # unidecode — folded to VIVC primes.
    "kaberne-sovinion": "cabernet-sauvignon",     # Каберне Совиньон
    "kaberne-fran": "cabernet-franc",             # Каберне Фран
    "merlo": "merlot",                            # Мерло
    "sira": "syrah",                              # Сира
    "shiraz": "syrah",
    "sovinion-blan": "sauvignon-blanc",           # Совиньон блан
    "shardone": "chardonnay",                     # Шардоне
    "shardonne": "chardonnay",
    "pino-nuar": "pinot-noir",                    # Пино ноар
    "pino-noar": "pinot-noir",
    "pino-gri": "pinot-gris",                     # Пино гри
    "pino-blan": "pinot-blanc",                   # Пино блан
    "muskat-otonel": "muscat-ottonel",            # Мускат отонел
    "vionie": "viognier",                         # Вионие
    "grenash": "grenache",                        # Гренаш
    "mourvedr": "mourvedre",                      # Мурведр
    "mourvedre-bg": "mourvedre",
    "muskat": "muscat-a-petits-grains",           # generic Cyrillic Muskat fallback (VIVC #8193)
    "tramin-aromaten": "gewurztraminer",          # Bulgarian "aromatic Traminer"
    "traminer": "gewurztraminer",                 # bare Traminer fallback (BG context)
    "biser": "biser",                             # BG modern crossing
    "marselan": "marselan",                       # Marselan in Cyrillic-transliterated docs
    "vrachanski-misket": "vrachanski-misket",     # BG Vratsa-area Misket
    "buket": "buket",                             # BG modern crossing
    "trakiiski-biser": "trakiiski-biser",         # BG modern crossing
    # International varieties named in the ИАЛВ продуктови спецификации,
    # transliterated from Cyrillic via unidecode — folded to VIVC primes.
    # `ъ`/`ь` render as an apostrophe under unidecode (Гъмза → g'mza,
    # Мьоние → m'onie), so those keys carry the apostrophe rather than the
    # slugify hyphen form (which would normalise differently).
    "iuni-blan": "ugni-blanc",                    # Юни блан (Ugni blanc = Trebbiano)
    "g'mza": "kadarka",                           # Гъмза (ъ-spelling of Гамза = Kadarka)
    "shenin-blan": "chenin",                      # Шенин блан (Chenin blanc)
    "geviurtstraminer": "gewurztraminer",         # Гевюрцтраминер (full spelling)
    "miuler-tiurgao": "muller-thurgau",           # Мюлер тюргао (Müller-Thurgau)
    "kharsh-laveliu": "harslevelu",               # Харш Лавелю (Hárslevelű)
    "m'onie": "meunier",                          # Мьоние (Meunier / Pinot Meunier)
    "senzo": "cinsault",                          # Сензо (BG name for Cinsault)
    "rizling-nemski": "sylvaner",                 # Ризлинг немски (= Немски ризлинг → Sylvaner)
    # BG breeding-station crossings + old natives self-canonicalise (colours
    # in DEFAULT_COLOUR). `ъ`/`ь` render as an apostrophe under unidecode, so
    # `balgarski-rizling` is reached via the apostrophe key "rizling-b'lgarski".
    "evmolpiia": "evmolpiia",                     # Евмолпия
    "trakiiska-slava": "trakiiska-slava",         # Тракийска слава
    "shevka": "shevka",                           # Шевка
    "akheloi": "akheloi",                         # Ахелой
    "chernomorski-briliant": "chernomorski-briliant",  # Черноморски брилянт
    "chernomorski-eliksir": "chernomorski-eliksir",    # Черноморски еликсир
    "kamchiia": "kamchiia",                       # Камчия
    "khebros": "khebros",                         # Хеброс
    "kokorko": "kokorko",                         # Кокорко
    "kuklenski-mavrud": "kuklenski-mavrud",       # Кукленски мавруд
    "orfei": "orfei",                             # Орфей
    "plovdivska-malaga": "plovdivska-malaga",     # Пловдивска малага
    "pomoriiski-biser": "pomoriiski-biser",       # Поморийски бисер
    "sungurlarski-biser": "sungurlarski-biser",   # Сунгурларски бисер
    "septemvriiski-rubin": "septemvriiski-rubin",  # Септемврийски рубин
    "misket-markovski": "misket-markovski",       # Мискет марковски
    "misket-sungurlarski": "misket-sungurlarski",  # Мискет сунгурларски
    "rizling-b'lgarski": "balgarski-rizling",     # Ризлинг български (Dimyat × Riesling)
    "balgarski-rizling": "balgarski-rizling",
    # ----- GR (Greece) native varieties — Greek-script folds via unidecode -----
    # The Greek-script names round-trip through unidecode() in slugify()
    # to non-standard romanisations (asurtiko / ksinomauro / rompola /
    # maurodaphne / sabbatiano / negkoska / …). We fold those to the
    # internationally-used English canonical slug (assyrtiko / xinomavro
    # / robola / mavrodaphne / savatiano / negoska / …) so VIVC search
    # and the Wikipedia lexicon both find the right page.
    # Whites:
    "asurtiko": "assyrtiko",                      # Ασύρτικο — Santorini white
    "athiri": "athiri",                           # Αθήρι — Aegean white
    "atheri": "athiri",
    "aidani": "aidani",                           # Αηδάνι — Santorini white
    "aedani": "aidani",
    "malagousia": "malagousia",                   # Μαλαγουζιά — modern revival
    "malagouzia": "malagousia",
    "moschofilero": "moschofilero",               # Μοσχοφίλερο — Mantinia pink-skinned
    "moskhophilero": "moschofilero",
    "moshofilero": "moschofilero",
    "roditis": "roditis",                         # Ροδίτης — Patras pink-skinned
    "rodites": "roditis",                         # unidecode
    "rhoditis": "roditis",
    "robola": "robola",                           # Ρομπόλα — Kefallinia white
    "rompola": "robola",                          # unidecode
    "savatiano": "savatiano",                     # Σαββατιανό — Attika white
    "sabbatiano": "savatiano",                    # unidecode
    "vilana": "vilana",                           # Βιλάνα — Cretan white
    "bilana": "vilana",                           # unidecode
    "vidiano": "vidiano",                         # Βιδιανό — Cretan white revival
    "bidiano": "vidiano",
    "debina": "debina",                           # Ντεμπίνα — Zitsa white
    "ntempina": "debina",                         # unidecode
    "thrapsathiri": "thrapsathiri",               # Θραψαθήρι — Cretan white
    "thrapsatheri": "thrapsathiri",
    "batiki": "batiki",                           # Μπατίκι — Thessaly white
    "mpatiki": "batiki",                          # unidecode
    "lagorthi": "lagorthi",                       # Λαγόρθι — Peloponnese white
    "monemvasia": "monemvasia",                   # Μονεμβασιά — Peloponnese white
    "monemvasia-malvasia": "monemvasia",
    "kakotrygis": "kakotrygis",                   # Κακοτρύγης — Corfu white (Halikouna/Kerkira)
    "kakotruges": "kakotrygis",                   # unidecode (Greek-script)
    "petrokoritho": "petrokoritho",               # Πετροκόριθο (Πετροκόριθο Λευκό) — Corfu white
    "petrokoritho lefko": "petrokoritho",
    "priknadi": "priknadi",                       # Πρικνάδι — Siatista/W. Macedonia white
    # Reds:
    "xinomavro": "xinomavro",                     # Ξινόμαυρο — Naoussa red
    "ksinomauro": "xinomavro",                    # unidecode
    "xynomavro": "xinomavro",
    "xinogalsto": "xinomavro",                    # Ξινόγκαλτσο — local Xinomavro biotype/synonym
    "ksinogkaltso": "xinomavro",
    "agiorgitiko": "agiorgitiko",                 # Αγιωργίτικο — Nemea red
    "agiorghitiko": "agiorgitiko",
    "mavrodaphne": "mavrodaphne",                 # Μαυροδάφνη — Patras/Kefallinia red
    "maurodaphne": "mavrodaphne",                 # unidecode
    "mavrodafni": "mavrodaphne",                  # eAmbrosia transcription form
    "mavrodaphni": "mavrodaphne",
    "limnio": "limnio",                           # Λημνιό — Limnos red
    "lemnio": "limnio",                           # unidecode
    "kalampaki": "limnio",                        # Καλαμπάκι — Limnio synonym
    "limniona": "limniona",                       # Λημνιώνα — Thessaly red revival
    "lemniona": "limniona",
    "mandilaria": "mandilaria",                   # Μανδηλαριά — Aegean/Cretan red
    "mandelaria": "mandilaria",                   # unidecode
    "amorgiano": "mandilaria",                    # Αμοργιανό — Mandilaria synonym
    "doumbiano": "mandilaria",                    # Δουμπιανό — Mandilaria synonym
    "kotsifali": "kotsifali",                     # Κοτσιφάλι — Cretan red
    "kotsiphali": "kotsifali",
    "liatiko": "liatiko",                         # Λιάτικο — Cretan red
    "negoska": "negoska",                         # Νεγκόσκα — Goumenissa red
    "negkoska": "negoska",                        # unidecode
    "negoshka": "negoska",
    "vradiano": "vradiano",                       # Βραδιανό — Evia red
    "bradiano": "vradiano",
    "stavroto": "stavroto",                       # Σταυρωτό — Rapsani red
    "krasato": "krasato",                         # Κρασάτο — Rapsani red
    "mavro-mesenikola": "mavro-mesenikola",       # Μαύρο Μεσενικόλα — Mesenikola red
    "mauro mesenikola": "mavro-mesenikola",       # unidecode (Greek-script)
    "moschomavro": "moschomavro",                 # Μοσχόμαυρο — Siatista red
    "moskhomauro": "moschomavro",                 # unidecode (Greek-script)
    "chondromavro": "chondromavro",               # Χονδρόμαυρο — Siatista red
    "khondromauro": "chondromavro",               # unidecode (Greek-script)
    # Greek synonyms for international varieties:
    "fileri": "moschofilero",                     # Φιλέρι — synonym
    "asuda": "asproudes",                         # absorbed (white-skinned generic, dropped in BLOCKLIST below)
    # ----- CY (Cyprus) native varieties — moa.gov.cy τεχνικός φάκελος ----
    # Greek-script forms round-trip through unidecode() to non-standard
    # romanisations (ksunisteri / mauro / maratheutiko / ophthalmo /
    # blouriko / bertzami / …); fold those + the Latin spellings used in
    # the spec OIV lists (Giannoudhi / Vlouriko / Morocanella / Canella)
    # to the internationally-used slug. Colours from VIVC / wein.plus /
    # wineriesofcyprus.com (research 2026-05-31).
    # Whites:
    "ksunisteri": "xynisteri",                    # Ξυνιστέρι — Cyprus's main white (VIVC #704)
    "xynisteri": "xynisteri",
    "promara": "promara",                         # Προμάρα — rare-native white revival
    "morokanella": "morokanella",                 # Μοροκανέλλα — white ('little cinnamon')
    "marokanella": "morokanella",
    "morocanella": "morokanella",                 # Latin spec spelling
    "spourtiko": "spourtiko",                     # Σπούρτικο — thin-skinned white
    "kanella": "kanella",                         # Κανέλλα / Canella — white ('cinnamon')
    "canella": "kanella",
    "basilissa": "vasilissa",                     # Βασίλισσα — recently registered white
    "vasilissa": "vasilissa",
    # Reds:
    "mauro": "mavro",                             # Μαύρο / Ντόπιο Μαύρο — Cyprus's main red
    "mavro": "mavro",
    "ntopio mauro": "mavro",
    "ntopio mavro": "mavro",
    "ntopio-mavro": "mavro",
    "maratheutiko": "maratheftiko",               # Μαραθεύτικο — red native
    "maratheftiko": "maratheftiko",
    "bambakada": "maratheftiko",                  # Βαμβακάδα — Maratheftiko synonym
    "vamvakada": "maratheftiko",
    "pampakada": "maratheftiko",                  # Παμπακάδα — Maratheftiko synonym
    "pampakia": "maratheftiko",
    "giannoudi": "giannoudi",                     # Γιαννούδι — red native (revived)
    "giannoudhi": "giannoudi",                    # Latin spec spelling
    "yiannoudi": "giannoudi",
    "ophthalmo": "ofthalmo",                      # Οφθαλμό — high-tannin red native
    "ofthalmo": "ofthalmo",
    "blouriko": "vlouriko",                       # Βλούρικο / Φλούρικο — red native
    "phlouriko": "vlouriko",
    "vlouriko": "vlouriko",
    "flouriko": "vlouriko",
    "bertzami": "vertzami",                       # Βερτζαμί — Ionian/Greek red (VIVC #13011)
    "vertzami": "vertzami",
    "leukada": "vertzami",                        # Λευκάδα — DNA-identical to Vertzami
    "lefkada": "vertzami",
    "maurotragano": "mavrotragano",               # Μαυροτράγανο — Greek (Santorini) red
    "mavrotragano": "mavrotragano",
    "maurathero": "mavrathiro",                   # Μαυράθηρο — Greek (Santorini) red
    "mavrathiro": "mavrathiro",
    # CY synonyms for international varieties:
    "malaga": "muscat-d-alexandrie",              # Μαλάγα — = Muscat of Alexandria in Cyprus
    "moskhato kuprou": "muscat-a-petits-grains",  # Μοσχάτο Κύπρου — Muscat blanc à petits grains
    "moschato kyprou": "muscat-a-petits-grains",
    # ----- DE (Germany) Einziges-Dokument varieties --------------------
    # German wine carries the most prolific set of breeding-station
    # crossings in the corpus: Geilweilerhof (JKI; "GM" + named releases),
    # Geisenheim, Weinsberg ("WE" codes), Würzburg (Klosterneuburg/Würzburg
    # parentage). Most named releases have VIVC entries. Anonymous breeder
    # codes (gm-643-10, we-94-26-36, vb-91-26-5, …) are kept as raw
    # candidates for now — no Wikipedia + no VIVC presence in v1.
    # International varieties under their German names fold to the
    # canonical slug; native German crossings stay on their own slug.
    "spatburgunder": "pinot-noir",                # VIVC #9279 PINOT NOIR — German Spätburgunder
    "fruhburgunder": "frueburgunder",              # VIVC #4461 PINOT MEUNIER siblings? — actually Frühburgunder is a clone of Pinot Noir, but treated as a distinct variety in Germany
    "fruehburgunder": "frueburgunder",
    "frueburgunder": "frueburgunder",
    "blauer-fruhburgunder": "frueburgunder",
    "blauer-fruehburgunder": "frueburgunder",
    # LU cahier des charges section f names this variety in French:
    # "Pinot noir précoce" — same cultivar as DE Frühburgunder.
    "pinot-noir-precoce": "frueburgunder",
    "pinot-precoce": "frueburgunder",
    "weissburgunder": "pinot-blanc",              # VIVC #9276 PINOT BLANC — German Weißburgunder
    "weisser-burgunder": "pinot-blanc",
    "grauer-burgunder": "pinot-gris",
    "schwarzriesling": "pinot-meunier",           # VIVC #9275 PINOT MEUNIER — German Schwarzriesling
    "mullerrebe": "pinot-meunier",                # synonym
    "muellerrebe": "pinot-meunier",
    "muller-thurgau": "muller-thurgau",           # VIVC #8141 MÜLLER-THURGAU (Riesling × Madeleine Royale)
    "mueller-thurgau": "muller-thurgau",
    "rivaner": "muller-thurgau",                  # luxembourgish / DE synonym
    "roter-muller-thurgau": "muller-thurgau",     # colour mutation, same cultivar (VIVC #8141)
    "blauer-limberger": "lemberger",              # VIVC #1459 BLAUFRÄNKISCH — German Lemberger / Limberger
    "limberger": "lemberger",
    "blauer-trollinger": "schiava-grossa",         # VIVC #11237 SCHIAVA GROSSA = Vernatsch = Trollinger
    "trollinger": "schiava-grossa",
    "gutedel": "chasselas",                       # German Chasselas
    "weisser-gutedel": "chasselas",
    "elbling": "elbling",                          # VIVC #3811 ELBLING — Mosel native white
    "weisser-elbling": "elbling",
    "roter-elbling": "roter-elbling",              # VIVC #3819 ELBLING RUDE — red colour-mutation
    "elbling-rouge": "roter-elbling",
    "dornfelder": "dornfelder",                   # VIVC #3776 DORNFELDER (Helfensteiner × Heroldrebe)
    "helfensteiner": "helfensteiner",              # VIVC #5364 HELFENSTEINER
    "heroldrebe": "heroldrebe",                   # VIVC #5400 HEROLDREBE
    "regent": "regent",                           # VIVC #9788 REGENT (Diana × Chambourcin), Geilweilerhof
    "reberger": "reberger",                       # VIVC #19999 REBERGER (Regent × Lemberger), Geilweilerhof — red
    "rondo": "rondo",                             # VIVC #10153 RONDO (Saperavi Severnyi × St Laurent)
    "deckrot": "deckrot",                          # VIVC #3493 DECKROT (Pinot gris × Teinturier)
    "dunkelfelder": "dunkelfelder",                # VIVC #3815 DUNKELFELDER (teinturier red)
    "dakapo": "dakapo",                            # VIVC #3267 DAKAPO (Portugieser × Deckrot)
    "tauberschwarz": "tauberschwarz",              # VIVC #11842 TAUBERSCHWARZ — native red
    "blauer-affenthaler": "blauer-affenthaler",    # VIVC #79 AFFENTHALER — old Württemberg red; not Trollinger
    "acolon": "acolon",                            # VIVC #82 ACOLON (Lemberger × Dornfelder), Weinsberg
    "cabernet-mitos": "cabernet-mitos",            # VIVC #2078 CABERNET MITOS (Lemberger × Teinturier)
    "cabernet-dorio": "cabernet-dorio",            # VIVC #2031 CABERNET DORIO (Dornfelder × Cab Sauv), sibling
    "cabernet-cubin": "cabernet-cubin",            # VIVC #2026 CABERNET CUBIN
    "cabernet-cortis": "cabernet-cortis",          # VIVC #2025 CABERNET CORTIS (Solaris × Cab Sauv)
    "cabernet-blanc": "cabernet-blanc",            # VIVC #16258 CABERNET BLANC
    "cabernet-cantor": "cabernet-cantor",          # VIVC #2017 CABERNET CANTOR (Bronner × Cab Sauv)
    "cabernet-jura": "cabernet-jura",              # Valentin Blattner CH crossing (Cab Sauv x resistant)
    "cabaret-noir": "cabaret-noir",                # VIVC interspecific red
    "cabernet-bordo": "cabernet-franc",            # eastern-European Cab Franc synonym
    "bacchus": "bacchus",                          # VIVC #908 BACCHUS (Silvaner × Riesling × Müller-Thurgau)
    "faberrebe": "faberrebe",                      # VIVC #3917 FABER — Geisenheim crossing
    "faber": "faberrebe",
    "ortega": "ortega",                            # VIVC #8732 ORTEGA — Würzburg crossing
    "optima": "optima",                            # VIVC #8731 OPTIMA — Geilweilerhof
    "optima-113": "optima",                        # OPTIMA 113 = full breeder name
    "reichensteiner": "reichensteiner",            # VIVC #9787 REICHENSTEINER — Geisenheim
    "schonburger": "schonburger",                  # VIVC #11160 SCHÖNBURGER — Geisenheim
    "schoenburger": "schonburger",
    "siegerrebe": "siegerrebe",                    # VIVC #11629 SIEGERREBE — Alzey crossing
    "sieger": "sieger",                            # VIVC #11627 SIEGER — Alzey crossing (sibling)
    "wurzer": "wurzer",                            # VIVC #13469 WÜRZER — Alzey aromatic
    "wuerzer": "wurzer",
    "huxelrebe": "huxelrebe",                      # VIVC #5563 HUXELREBE (Chasselas × Courtillier Musqué)
    "huxel": "huxelrebe",
    "ehrenfelser": "ehrenfelser",                  # VIVC #3801 EHRENFELSER (Riesling × Knipperle)
    "kernling": "kernling",                        # VIVC #5918 KERNLING — Kerner mutation
    "samling": "scheurebe",
    "morio-muskat": "morio-muskat",                # VIVC #8194 MORIO-MUSKAT — Geilweilerhof
    "phoenix": "phoenix",                          # VIVC #9192 PHOENIX (Bacchus × Villard Blanc), Geilweilerhof
    "phonix": "phoenix",
    "phoenix-de": "phoenix",
    "hibernal": "hibernal",                        # VIVC #5424 HIBERNAL — interspecific white
    "helios": "helios",                            # VIVC #5362 HELIOS — Freiburg crossing
    "felicia": "felicia",                          # VIVC #3961 FELICIA — Geilweilerhof
    "merzling": "merzling",                        # VIVC #7659 MERZLING — Freiburg crossing
    "solaris": "solaris",                          # VIVC #11781 SOLARIS — Freiburg crossing
    "souvignier-gris": "souvignier-gris",          # VIVC #15947 SOUVIGNIER GRIS — Freiburg
    "souvignier": "souvignier-gris",
    "bronner": "bronner",                          # VIVC #1581 BRONNER — Freiburg interspecific white
    "johanniter": "johanniter",                    # VIVC #5642 JOHANNITER — Freiburg
    "muscaris": "muscaris",                        # VIVC #21068 MUSCARIS — Freiburg aromatic
    "sauvignac": "sauvignac",                      # VIVC interspecific white
    "saphira": "saphira",                          # VIVC #15966 SAPHIRA — Geilweilerhof
    "serena": "serena",                            # VIVC #4739 SERENA — interspecific white (02g confirms)
    "albalonga": "albalonga",                      # VIVC #109 ALBALONGA — Geilweilerhof
    "kanzler": "kanzler",                          # VIVC #5910 KANZLER — Alzey crossing
    "juwel": "juwel",                              # VIVC #5710 JUWEL — Geilweilerhof
    "mariensteiner": "mariensteiner",              # VIVC #7361 MARIENSTEINER — Würzburg
    "septimer": "septimer",                        # VIVC #11367 SEPTIMER — Alzey
    "sibera": "sibera",                            # VIVC #11589 SIBERA — Mlazice CZ crossing
    "fidelio": "fidelio",                          # VIVC #4084 FIDELIO — Geilweilerhof
    "sirius": "sirius",                            # VIVC #11696 SIRIUS — Geilweilerhof
    "orion": "orion",                              # VIVC #8729 ORION — Geilweilerhof
    "pollux": "pollux",                            # VIVC #9389 POLLUX — Geilweilerhof
    "prinzipal": "prinzipal",                      # VIVC #9509 PRINZIPAL — Geilweilerhof
    "rinot": "rinot",                              # VIVC interspecific white
    "calandro": "calandro",                        # VIVC #2207 CALANDRO — Geilweilerhof red
    "calardis-blanc": "calardis-blanc",            # VIVC #21065 CALARDIS BLANC — Geilweilerhof
    "calardis-musque": "calardis-musque",          # Calardis Musqué — Geilweilerhof
    "calardis-royal": "calardis-royal",            # Calardis Royal — Geilweilerhof
    "calardis-soleil": "calardis-soleil",          # Calardis Soleil — Geilweilerhof
    "villaris": "villaris",                        # VIVC #13169 VILLARIS — Geilweilerhof
    "hegel": "hegel",                              # VIVC #5354 HEGEL — Geilweilerhof
    "holder": "holder",                            # VIVC #5519 HÖLDER
    "hoelder": "holder",
    "freisamer": "freisamer",                      # VIVC #4459 FREISAMER — Freiburg
    "regner": "regner",                            # VIVC #9802 REGNER — Alzey
    "ehrenbreitsteiner": "ehrenbreitsteiner",      # VIVC #3800 EHRENBREITSTEINER — Geisenheim
    "osteiner": "osteiner",                        # VIVC #8801 OSTEINER — Geisenheim
    "rabaner": "rabaner",                          # VIVC #9667 RABANER — Geisenheim
    "nobling": "nobling",                          # VIVC #8508 NOBLING — Freiburg
    "perle": "perle",                              # VIVC #8865 PERLE (Müller-Thurgau × Gewürztraminer) — Würzburg
    "gutenborner": "gutenborner",                  # VIVC #5283 GUTENBORNER — Geisenheim
    "bukettsilvaner": "bukettsilvaner",            # VIVC #1812 BUKETTSILVANER — Alzey
    "noblessa": "noblessa",                        # VIVC #8506 NOBLESSA — Geilweilerhof
    "muskat-trollinger": "muskat-trollinger",      # VIVC #8338 MUSCAT TROLLINGER
    "muskateller": "muscat-a-petits-grains",       # German Muscat (VIVC #8193)
    "gelber-muskateller": "muscat-a-petits-grains",  # Gelber Muskateller = Muscat à petits grains blancs
    "roter-muskateller": "muscat-a-petits-grains-rouges",
    "blauer-muskateller": "muscat-a-petits-grains-rouges",
    "muskat-ottonel": "muscat-ottonel",            # already present
    "morio": "morio-muskat",
    "morio-muscat": "morio-muskat",
    "auxerrois": "auxerrois",                      # VIVC #913 AUXERROIS (sibling of Chardonnay)
    "auxerrois-blanc": "auxerrois",
    "portugieser-blau": "blauer-portugieser",
    "blauer-gaensfusser": "blauer-gaensfusser",     # VIVC GÄNSFÜSSER — Pfalz heritage red
    "blauer-gansfusser": "blauer-gaensfusser",
    "gelber-orleans": "gelber-orleans",            # VIVC #4622 ORLEANS — historical Rheingau white
    "weisser-rauschling": "raeuschling",            # VIVC #9742 RÄUSCHLING — historical Rheinland white
    "weisser-raeuschling": "raeuschling",
    "rauschling": "raeuschling",
    "raeuschling": "raeuschling",
    "roter-rauschling": "raeuschling",              # colour mutation of Räuschling, same cultivar
    "kleinberger": "kleinberger",                  # VIVC #6113 KLEINBERGER — Mosel heritage
    "gelber-kleinberger": "kleinberger",
    "donauriesling": "donauriesling",              # AT/DE interspecific white
    "donauveltliner": "donauveltliner",            # AT/DE interspecific white
    "schwarzer-heunisch": "heunisch",              # VIVC #5392 HEUNISCH WEISS — historical European parent grape, red mutation
    "weisser-heunisch": "heunisch",
    "heunisch": "heunisch",
    "hartblau": "hartblau",                        # German interspecific red
    "bolero": "bolero",                            # interspecific red crossing
    "laurot": "laurot",                            # VIVC #12869 LAUROT — interspecific red
    "piroso": "piroso",                            # interspecific red
    "pinot-nova": "pinot-nova",                    # CH/DE interspecific red
    "pinot-iskra": "pinot-iskra",                  # CH/DE interspecific red
    "pinot-kors": "pinot-kors",                    # CH/DE interspecific red
    "accent": "accent",                            # interspecific red crossing
    "adelfraenkisch": "adelfraenkisch",             # historical Franken red — kept as own slug
    "adelfrankisch": "adelfraenkisch",
    "gruner-adelfraenkisch": "adelfraenkisch",
    "gruener-adelfraenkisch": "adelfraenkisch",
    "blauer-hangling": "blauer-hangling",          # Pfalz heritage red
    "blauer-haengling": "blauer-hangling",
    "bettlertraube": "bettlertraube",              # Franken heritage red
    "geisdutte": "geisdutte",                      # Franken heritage white
    "rheinfelder": "rheinfelder",                  # interspecific white
    "comtessa": "comtessa",                        # Geilweilerhof
    "divona": "divona",                            # Agroscope CH white
    "aromera": "aromera",                          # Geilweilerhof crossing
    "merlot-khorus": "merlot-khorus",              # IT/DE interspecific red
    "merlot-kanthus": "merlot-kanthus",            # IT/DE interspecific red
    "sauvignon-cita": "sauvignon-cita",            # IT/DE interspecific white
    "sauvignon-sary": "sauvignon-sary",            # IT/DE interspecific white
    "sauvitage": "sauvitage",                      # interspecific white
    "thurling": "thurling",                        # heritage white
    "weisser-lagler": "weisser-lagler",            # heritage white
    "dalkauer": "dalkauer",                        # heritage white
    "wildmuskat": "wildmuskat",                    # heritage aromatic
    "muscabona": "muscabona",                      # heritage aromatic
    "mucabona": "muscabona",
    "orangentraube": "orangentraube",              # heritage white
    "vogelfraenkisch": "vogelfraenkisch",          # historical Franken red
    "burgunder-fraenkisch-kleiner": "vogelfraenkisch",
    "kleiner-fraenkischer-burgunder": "vogelfraenkisch",
    "kleiner-fraenkischer": "vogelfraenkisch",
    "carillon": "carillon",                        # heritage variety
    "savilon": "savilon",                          # heritage variety
    "sulmer": "sulmer",                            # heritage variety
    "ladner": "ladner",                            # heritage white
    "jakob-gerhardt-blanc": "jakob-gerhardt-blanc", # German breeding-station crossing
    "cumdeo-blanc": "cumdeo-blanc",                 # interspecific white
    "cumdeo-rouge": "cumdeo-rouge",                 # interspecific red
    "perle-von-zala": "csabagyongye",              # alternate German name for Csabagyöngye
    "zala-gyoengye": "csabagyongye",
    "zala-gyongye": "csabagyongye",
    "staufer": "staufer",                          # VIVC #11825 STAUFER — Weinsberg
    "hecker": "hecker",                            # Weinsberg crossing
    "allegro": "allegro",                          # Geilweilerhof crossing — separate from Galego Dourado
    "arneis": "arneis",                            # Italian white (used in DE Sekt blends)
    "carmenere": "carmenere",                      # already mapped; reaffirmed
    "tannat": "tannat",                            # already mapped; reaffirmed
    "alicante-bouschet": "alicante-bouschet",      # VIVC #234 ALICANTE BOUSCHET
    "alicante": "alicante-bouschet",
    "alvarinho": "albarino",                       # PT name for ES Albariño
    "artaban": "artaban",                          # VIVC #21138 ARTABAN — INRA interspecific red
    "voltis": "voltis",                            # VIVC #21163 VOLTIS — INRA interspecific white
    "floreal": "floreal",                          # VIVC #21162 FLOREAL — INRA interspecific white
    "vidoc": "vidoc",                              # VIVC #21164 VIDOC — INRA interspecific red
    "valerie": "valerie",                          # German interspecific
    "weisser-deckling": "weisser-deckling",         # heritage white
    "schwarzer-deckling": "schwarzer-deckling",     # heritage red
    "blauer-arbst": "blauer-arbst",                # heritage red
    "weisser-arbst": "weisser-arbst",              # heritage white
    "palas": "palas",                              # Czech interspecific red — Polášek / Klingenberger crossing
    "levitage": "levitage",                        # German interspecific white
    "riesel": "riesel",                            # German crossing — Riesling × Madeleine angevine sibling
    # ─── Slovakia (Vinohradnícke novostavby) — own SK crossings,
    # bred at VÚVV Bratislava / SCPV in the 1960s-90s. Each gets its
    # own slug (no foreign-cultivar equivalent in VIVC). ──
    "devin": "devin",                              # VIVC #20242 DEVÍN — Tramín × Veltlínske červené
    "dunaj": "dunaj",                              # VIVC #20242 DUNAJ — Muscat Bouschet × (Oporto + Sankt Laurent)
    "hron": "hron",                                # SK red crossing (Castets × Svätovavrinecké)
    "rimava": "rimava",                            # SK white crossing
    "vah": "vah",                                  # SK white crossing
    "nitria": "nitria",                            # SK white crossing
    "nitriansky-jubilejny": "nitria",
    "hetera": "hetera",                            # SK white crossing
    # ÚPV national-spec MUŠTOVÉ BIELE / MODRÉ crossings (VÚVV Bratislava /
    # Pospíšilová), each VIVC-anchored, none a foreign-cultivar synonym.
    "breslava": "breslava",                        # VIVC #1671 — (Chasselas Rose × Traminer) × Santa Maria d'Alcantara
    "milia": "milia",                              # VIVC #22818 — Müller-Thurgau × Tramín červený
    "noria": "noria",                              # VIVC #22819 — Ezerjó × Savagnin (DNA-corrected)
    "nitranka": "nitranka",                        # VIVC #17282 — Castets × Abouriou
    "rudava": "rudava",                            # VIVC #17283 — Castets × I-35-9 6/28
    "torysa": "torysa",                            # VIVC #22419 — Castets × I-35-9 9/17
    "karpatska-perla": "karpatska-perla",          # SK PDO brand (not a single variety, but appears as a name in pliegos)
    # SK-side name variants that round-trip through unidecode to existing slugs
    "frankovka-modra": "blaufrankisch",            # explicit Slovak "blue Frankovka"
    "svatovavrinecke": "sankt-laurent",            # Slovak name for Sankt Laurent
    "tramin-cerveny": "gewurztraminer",            # Slovak "red Tramín"
    "rizling-vlassky": "welschriesling",
    "rizling-rynsky": "riesling",
    "rulandske-biele": "pinot-blanc",
    "rulandske-sede": "pinot-gris",
    "rulandske-modre": "pinot-noir",
    "veltlinske-zelene": "gruner-veltliner",
    "veltlinske-cervene-rane": "fruhroter-veltliner",
    "muskat-zlty": "muscat-a-petits-grains",
    "muscat-zlty": "muscat-a-petits-grains",
    "pesecka-leanka": "feteasca-alba",             # SK name for HU Leányka (VIVC #6816) — folded to Fetească albă (#4119), distinct from feteasca-regala (#4121)
    "leanka": "feteasca-alba",
    "modry-portugal": "blauer-portugieser",
    # ─── Malta — the two indigenous Maltese varieties. Both round-trip
    # through unidecode (Ġ→G, ż→z) so the diacritic and plain spellings
    # fold to one slug. No foreign-cultivar equivalent. ───
    "gellewza": "gellewza",                        # Ġellewża — Malta's indigenous red
    "girgentina": "girgentina",                    # Malta's indigenous white (Girgenti / Agrigento)
    # ─── Czech crossings (Lednice / Velké Bílovice / Polášek) ───
    "palava": "palava",                            # VIVC #18198 PÁLAVA — Tramín × Müller Thurgau
    "aurelius": "aurelius",                        # VIVC #816 AURELIUS — Neuburger × Müller-Thurgau (CZ)
    "cabernet-moravia": "cabernet-moravia",        # CZ red crossing (Cabernet Franc × Zweigeltrebe)
    # André in a Czech wine context = the CZ red crossing of Frankovka ×
    # Svatovavřinecké, distinct from any IT/ES variety the fuzzy matcher
    # might collide with.
    "andre": "andre",                              # VIVC #20242 ANDRÉ — Frankovka × Svatovavřinecké (CZ)
    "neronet": "neronet",                          # VIVC #20242 NERONET — CZ red crossing (Sankt Laurent × Alibernet)
    "ryzlink-rynsky": "riesling",
    "ryzlink-vlassky": "welschriesling",
    "rulandske-bile": "pinot-blanc",
    "veltlinske-zelene-cz": "gruner-veltliner",
    "tramin-cerveny-cz": "gewurztraminer",
    "modry-portugal-cz": "blauer-portugieser",
    "svatovavrinecke-cz": "sankt-laurent",
    "frankovka-cz": "blaufrankisch",
    "zweigeltrebe": "zweigelt",
    # ─── Czech registry-only crossings from Vyhláška 88/2017 Sb.
    # Příloha č. 2 — Lednice / Velké Bílovice / Polášek breeding
    # stations. Most have no VIVC entry; kept as own slugs. ──
    "erilon": "erilon",                            # CZ white crossing
    "florianka": "florianka",                      # CZ white crossing
    "lena": "lena",                                # CZ white crossing
    "malverina": "malverina",                      # CZ white (Rakish × Veltlínske)
    "medea": "medea",                              # CZ white crossing
    "mery": "mery",                                # CZ white crossing
    "muskat-moravsky": "muskat-moravsky",          # CZ Moravian Muscat (Müller-Thurgau × Muscat Ottonel)
    "rulenka": "rulenka",                          # CZ white crossing
    "svojsen": "svojsen",                          # CZ white crossing
    "tristar": "tristar",                          # CZ white crossing
    "veritas": "veritas",                          # CZ white crossing
    "vesna": "vesna",                              # CZ white crossing
    "vrboska": "vrboska",                          # CZ white crossing
    "agni": "agni",                                # CZ red crossing
    "fratava": "fratava",                          # CZ red crossing
    "jakubske": "jakubske",                        # CZ red crossing (Jakubské)
    "kofranka": "kofranka",                        # CZ red crossing
    "nativa": "nativa",                            # CZ red crossing
    "sevar": "sevar",                              # CZ red crossing
    # Zemské víno varieties (CZ-only or under-mapped)
    "bily-portugal": "bily-portugal",              # CZ "white Portugal" — distinct from Blauer Portugieser
    "modry-janek": "modry-janek",                  # CZ red zemské-only crossing
    "ranuse-muskatova": "ranuse-muskatova",        # CZ aromatic
    "sedy-portugal": "sedy-portugal",              # CZ "grey Portugal"
    "tramin-zluty": "tramin-zluty",                # CZ "yellow Traminer" — kept distinct from gewurztraminer

    # Croatia autochthonous varieties (MPS specifikacija proizvoda, 2026-05-29).
    # Self-maps register a distinct native variety; folds collapse a
    # documented DNA synonym. VIVC numbers verified on vivc.de where noted.
    "plavina": "plavina",                # VIVC #9557 (PLAVINA CRNA) — Dalmatia; canonical for Brajda crna / Plavčina
    "brajda-crna": "plavina",            # VIVC #9557 synonym of Plavina
    "plavcina": "plavina",               # VIVC #9557 synonym of Plavina
    "crljenak-viski": "tribidrag",       # VIVC #17636 (= Crljenak kaštelanski = Zinfandel = Primitivo)
    "kavcina-crna": "zametovka",         # documented synonym of Žametovka (Modra kavčina)
    "diseca-ranina-bijela": "diseca-belina-bijela",  # same Zagorje variety as Dišeća belina
    "belina-hizakovo": "belina-hizakovo",            # Zagorje Belina type
    "blatina": "blatina",                # VIVC #1454
    "brajdica-bijela": "brajdica-bijela",
    "bratkovina": "bratkovina",          # Korčula; a Pošip parent
    "cetinka": "cetinka",                # VIVC #2407 (CETINJKA)
    "debejan-crni": "debejan-crni",
    "diseca-belina-bijela": "diseca-belina-bijela",
    "dobricic": "dobricic",              # VIVC #3608 (Šolta; a Plavac Mali parent)
    "draganela": "draganela",
    "drnekusa": "drnekusa",              # Hvar red
    "gegic": "gegic",                    # VIVC #4493 (Pag)
    "glavinusa": "glavinusa",            # VIVC #8728 (prime name OKATAC)
    "kujundzusa": "kujundzusa",          # VIVC #6545 (KUJUNDZUSA BELA)
    "kurtelaska-bijela": "kurtelaska-bijela",
    "lasina": "lasina",                  # VIVC #6761
    "ljutac": "ljutac",
    "magrovina": "magrovina",
    "mejsko-belo": "mejsko-belo",
    "mirkovaca": "mirkovaca",
    "mladenka": "mladenka",
    "modra-kosovina": "modra-kosovina",
    "nincusa": "nincusa",
    "okatica-bijela": "okatica-bijela",  # white — distinct from noir Okatac/Glavinuša
    "osljevina": "osljevina",
    "prc": "prc",                        # Hvar white
    "rusljin-crni": "rusljin-crni",
    "sansigot": "sansigot",              # Kvarner/Susak red
    "smudna-belina": "smudna-belina",    # VIVC #24912
    "svetokriska-belina": "svetokriska-belina",
    "svrdlovina-crna": "svrdlovina-crna",
    "trnjak": "trnjak",                  # VIVC #10327 (prime name RUDEZUSA)
    "trojiscina-crvena": "trojiscina-crvena",
    "vlaska": "vlaska",
    "volarovo": "volarovo",
    "vranac": "vranac",                  # VIVC #13179 (Montenegro/Dalmatia)
    "zadarka": "zadarka",
    "zumic": "zumic",
    "bilan-bijeli": "bilan-bijeli",      # Kvarner/Primorje white
    "posip-crni": "posip-crni",          # black-berried Pošip — distinct from white posip
    # Colour-suffixed forms of varieties that already resolve via the
    # parser's colour-adjective-strip fallback — pinned explicitly so the
    # first match_variety() call succeeds and they don't log as unknowns.
    "croatina-crna": "croatina",
    "carmenere-crni": "carmenere",
    # EU-register fiche-technique natives (GR/SI/BG/CZ/HU), resolved +
    # adversarially verified against VIVC / wein.plus (2026-06). Keys are
    # the bare lookup surface the matcher sees after stripping the OIV
    # colour code (B/N/Rs). Folds to existing slugs where VIVC confirmed a
    # synonym; own slug otherwise. Cyrillic ъ → apostrophe under unidecode.
    "agoumastos": "agoumastos-lefko",
    "aidani aspro": "aidani",
    "amfioni": "amfioni",
    "araklinos": "araklinos",
    "areti": "areti",
    "ariana": "ariana",
    "asproudes": "asproudes",
    "asprovertzamo": "vertzami-lefko",
    "avgoustiatis": "avgoustiatis",
    "bekari": "bekari",
    "cabernet sauv": "cabernet-sauvignon",
    "chlores": "chlores",
    "cipro": "cipro",
    "dafni": "dafni",
    "dunavska g'mza": "dunavska-gamza",
    "fidia": "fidia",
    "gaidouria": "gaidouria",
    "glykopati": "glykopati",
    "goustolidi": "goustolidi",
    "kamenoruzak bily": "kamenoruzak-bily",
    "karabraimis": "karabraimis",
    "katsakoulias": "katsakoulias",
    "katsano": "katsano",
    "klarnica": "klarnica",
    "kokinovostitsa": "kokinovostitsa",
    "koliniatiko": "koliniatiko",
    "kontokladi": "kontokladi",
    "korfiatis": "kotsifali",
    "korinthiaki": "korinthiaki",
    "korithi": "korithi",
    "kotsifoliatiko": "kotsifoliatiko",
    "koutsoubeli": "koutsoubeli",
    "kozanitis": "kozanitis",
    "kydonitsa": "kydonitsa",
    "ladikino": "ladikino",
    "misket kail'shki": "misket-kailashki",
    "misket vrachanski": "misket-vrachanski",
    "misken vrachanski": "misket-vrachanski",  # fiche typo (Мискен for Мискет)
    "mygdali": "mygdali",
    "odusszeusz": "odysseus",
    "papadiko": "papadiko",
    "pergolin": "pergolin",
    "petrokoritho mavro": "petrokoritho-mavro",
    "platani": "platani",
    "plevenski kolorit": "plevenski-kolorit",
    "plyto": "plyto",
    "poljsakica": "poljsakica",
    "potamisi": "potamisi",
    "prachttraube": "prachttraube",
    "ritino": "ritino",
    "robola kokkini": "robola-kokkini",
    "romeiko": "romeiko",
    "sefka": "sefka",
    "skiadopoulo": "skiadopoulo",
    "skopelitiko": "skopelitiko",
    "skyloklima": "skyloklima",
    "skylopnichtis": "skylopnichtis",
    "thiako": "thiako",
    "tsaousi": "tsaoussi",
    "violento": "violento",
    "vitovska grganja": "vitovska-grganja",
    "vlahiko": "vlachiko",
    "voidomatis": "voidomatis",
    "vossos": "vossos",
    "zakynthino": "skiadopoulo",
    "zoumiatiko": "dimyat",
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
    "muscat-a-petits-grains": "blanc",
    "garganega": "blanc",
    "glera-lunga": "blanc",
    "spergola": "blanc",
    "vernaccia-di-san-gimignano": "blanc",
    "greco-bianco": "blanc",
    "friulano": "blanc",
    "pignoletto": "blanc",
    "gruner-veltliner": "blanc",
    "fruhroter-veltliner": "gris",   # reddish-grey berries, white wine (= Malvasier); HU Korai piros veltelíni, CZ Veltlínske červené rané
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
    # Tuscan natives from the IGT Toscano allegato-1 roster (2026-05-30).
    "abrusco": "noir",
    "barsaglina": "noir",
    "bonamico": "noir",
    "bracciola-nera": "noir",
    "colombana-nera": "noir",
    "foglia-tonda": "noir",
    "groppello-gentile": "noir",
    "groppello-di-santo-stefano": "noir",
    "incrocio-bruni-54": "blanc",
    "livornese-bianca": "blanc",
    "orpicchio": "blanc",
    "pollera-nera": "noir",
    "sanforte": "noir",
    "vermentino-nero": "noir",
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
    # ----- HR Jedinstveni-dokument varieties (see the matching
    # GRAPE_ALIAS block).
    "plavac-mali": "noir",
    "babic": "noir",
    "tribidrag": "noir",
    "posip": "blanc",
    "marastina": "blanc",
    "bogdanusa": "blanc",
    "vugava": "blanc",
    "grk": "blanc",
    "debit": "blanc",
    "trbljan": "blanc",
    "malvazija-istarska": "blanc",
    "muskat-zuti": "blanc",
    "skrlet": "blanc",
    "zlahtina": "blanc",
    "zelenac-slatki": "blanc",
    # ----- HU Egységes-dokumentum varieties (see the matching
    # GRAPE_ALIAS block).
    "harslevelu": "blanc",
    "cserszegi-fuszeres": "blanc",
    "irsai-oliver": "blanc",
    "feteasca-regala": "blanc",
    "feteasca-alba": "blanc",
    "feteasca-neagra": "noir",
    "juhfark": "blanc",
    "ezerjo": "blanc",
    "kovidinka": "blanc",
    "csabagyongye": "blanc",
    "zalagyongye": "blanc",
    "kunleany": "blanc",
    "nektar": "blanc",
    "aletta": "blanc",
    "medina": "noir",
    "generosa": "blanc",
    "zenit": "blanc",
    "zeta": "blanc",
    "kabar": "blanc",
    "pozsonyi-feher": "blanc",
    "kadarka": "noir",
    "goher": "blanc",
    "banati-rizling": "blanc",
    "biborkadarka": "noir",
    "blauer-portugieser": "noir",
    "turan": "noir",
    "csokaszolo": "noir",
    "muscat-ottonel": "blanc",
    "muscat-hambourg": "noir",
    "cabernet-dorsa": "noir",
    "blauburger": "noir",
    "zefir": "blanc",
    "ezerfurtu": "blanc",
    "zengo": "blanc",
    "alibernet": "noir",
    "menoire": "noir",
    "arany-sarfeher": "blanc",
    "huszar-szolo": "blanc",
    "gyongyrizling": "blanc",
    "kerner": "blanc",
    "rubintos": "noir",
    "decsi-szagos": "blanc",
    "zold-szagos": "blanc",
    "patria": "blanc",
    "poloskei-muskotaly": "blanc",
    "rozalia": "blanc",
    "rozsako": "blanc",
    "viktoria-gyongye": "blanc",
    "csomor": "blanc",
    "domina": "noir",
    "grasa-de-cotnari": "blanc",
    "koverszolo": "blanc",
    "sagrantino": "noir",
    "zierfandler": "blanc",
    "meszikadar": "noir",
    "bakator": "noir",                          # the Bakator family is dominated by red mutations
    "budai-zold": "blanc",
    "duna-gyongye": "blanc",
    "jubileum-75": "blanc",
    "odysseus": "blanc",
    "orpheus": "blanc",
    "zeus": "blanc",
    "pintes": "blanc",
    "refren": "noir",
    "vertes-csillaga": "blanc",
    "vulcanus": "blanc",
    "szederkenyi-feher": "blanc",
    "gyudi-feher": "blanc",
    "zoldfeher": "blanc",
    "csillam": "blanc",
    # ----- RO breeding-station crossings (see GRAPE_ALIAS block) -----
    "alutus": "noir",
    "arcas": "noir",
    "aromat-de-iasi": "blanc",
    "balada": "noir",
    "batuta-neagra": "noir",
    "codana": "noir",
    "columna": "blanc",
    "cristina": "noir",
    "donaris": "blanc",
    "golia": "blanc",
    "miorita": "blanc",
    "negru-aromat": "noir",
    "ozana": "blanc",
    "unirea": "blanc",
    "babeasca-gri": "gris",
    "rkatsiteli": "blanc",
    # ----- BG (Bulgaria) native varieties + crossings (see GRAPE_ALIAS block) -----
    "mavrud": "noir",
    "shiroka-melnishka-loza": "noir",
    "early-melnik": "noir",
    "melnik-82": "noir",
    "melnik-iubileen-1300": "noir",
    "melnishki-rubin": "noir",
    "pamid": "noir",
    "dimyat": "blanc",
    "cherven-misket": "blanc",
    "sandanski-misket": "blanc",
    "kerasuda": "blanc",
    "bogdan": "noir",
    "rubin": "noir",
    "ruen": "noir",
    "storgozia": "noir",
    "kaylashki-misket": "blanc",
    "varnenski-misket": "blanc",
    "vrachanski-misket": "blanc",
    "buket": "noir",
    "trakiiski-biser": "blanc",
    "biser": "blanc",
    "marselan": "noir",
    # BG breeding-station crossings + old natives named in the ИАЛВ
    # продуктови спецификации (colours researched 2026-05-30 against
    # bg.wikipedia / VIVC / wein.plus / BG institute catalogues).
    "evmolpiia": "noir",            # Mavrud × Merlot (VIVC #22725)
    "trakiiska-slava": "noir",      # Pamid × Mavrud
    "shevka": "noir",               # old Balkan red (Sliven)
    "akheloi": "blanc",             # Ugni blanc × Muscat Ottonel
    "chernomorski-briliant": "blanc",  # Tamyanka × Dimyat
    "chernomorski-eliksir": "blanc",   # Orange Muscat × Dimyat
    "kamchiia": "blanc",            # white (Misket Varnenski group)
    "khebros": "noir",              # Misket Cherven × Pinot noir (IV-9/14)
    "kokorko": "blanc",             # old Black-Sea white, near-extinct
    "kuklenski-mavrud": "noir",     # Mavrud × Saperavi
    "orfei": "blanc",               # Misket Cherven × Pinot noir (IV-9/8), white
    "plovdivska-malaga": "noir",    # Misket Cherven × Marseille Précoce
    "pomoriiski-biser": "blanc",    # Misket Cherven × Villard Blanc
    "sungurlarski-biser": "blanc",  # white bud-mutation of Misket Cherven
    "septemvriiski-rubin": "noir",  # Pamid × Cabernet Sauvignon (NOT a Rubin clone)
    "misket-markovski": "blanc",    # Muscat crossing (Plovdiv)
    "misket-sungurlarski": "blanc", # Misket Cherven × Sauvignon blanc
    "balgarski-rizling": "blanc",   # Dimyat × Riesling (distinct, NOT Welschriesling)
    # ----- GR (Greece) native varieties (see GRAPE_ALIAS block above) -----
    "athiri": "blanc",
    "aidani": "blanc",
    "malagousia": "blanc",
    "moschofilero": "rose",        # pink-skinned, vinified as white in Mantinia
    "roditis": "rose",              # pink-skinned, dominant in Patras blends
    "robola": "blanc",
    "savatiano": "blanc",
    "vilana": "blanc",
    "vidiano": "blanc",
    "debina": "blanc",
    "thrapsathiri": "blanc",
    "batiki": "blanc",
    "lagorthi": "blanc",
    "monemvasia": "blanc",
    "kakotrygis": "blanc",
    "petrokoritho": "blanc",
    "priknadi": "blanc",
    "xinomavro": "noir",
    "agiorgitiko": "noir",
    "mavrodaphne": "noir",
    "limnio": "noir",
    "limniona": "noir",
    "mandilaria": "noir",
    "kotsifali": "noir",
    "liatiko": "noir",
    "negoska": "noir",
    "vradiano": "noir",
    "stavroto": "noir",
    "krasato": "noir",
    "mavro-mesenikola": "noir",
    "moschomavro": "noir",
    "chondromavro": "noir",
    # ----- CY (Cyprus) native varieties (see GRAPE_ALIAS block above) -----
    "xynisteri": "blanc",
    "promara": "blanc",
    "morokanella": "blanc",
    "spourtiko": "blanc",
    "kanella": "blanc",
    "vasilissa": "blanc",
    "mavro": "noir",
    "maratheftiko": "noir",
    "giannoudi": "noir",
    "ofthalmo": "noir",
    "vlouriko": "noir",
    "vertzami": "noir",
    "mavrotragano": "noir",
    "mavrathiro": "noir",
    # ----- DE (Germany) varieties (see GRAPE_ALIAS block above) -----
    # Mosaic of historic German + modern breeding-station crossings.
    # PINK-skinned mutations of pinot (already covered) and ambiguous
    # bicolours are kept out; the rest split cleanly by typical
    # vinification practice.
    "elbling": "blanc",
    "roter-elbling": "rose",         # red-skinned colour mutation, vinified pale
    "frueburgunder": "noir",
    "dornfelder": "noir",
    "helfensteiner": "noir",
    "heroldrebe": "noir",
    "regent": "noir",
    "reberger": "noir",
    "blauer-affenthaler": "noir",
    "rondo": "noir",
    "deckrot": "noir",
    "dunkelfelder": "noir",
    "dakapo": "noir",
    "tauberschwarz": "noir",
    "acolon": "noir",
    "cabernet-mitos": "noir",
    "cabernet-dorio": "noir",
    "cabernet-cubin": "noir",
    "cabernet-cortis": "noir",
    "cabernet-blanc": "blanc",       # despite "Cabernet" — interspecific white
    "cabernet-cantor": "noir",
    "cabernet-jura": "noir",
    "cabaret-noir": "noir",
    "bacchus": "blanc",
    "faberrebe": "blanc",
    "ortega": "blanc",
    "optima": "blanc",
    "reichensteiner": "blanc",
    "schonburger": "rose",           # pink-skinned aromatic, vinified pale
    "siegerrebe": "blanc",
    "sieger": "blanc",
    "wurzer": "blanc",
    "huxelrebe": "blanc",
    "ehrenfelser": "blanc",
    "kernling": "blanc",
    "morio-muskat": "blanc",
    "phoenix": "blanc",
    "hibernal": "blanc",
    "helios": "blanc",
    "felicia": "blanc",
    "merzling": "blanc",
    "solaris": "blanc",
    "serena": "blanc",
    "souvignier-gris": "blanc",      # despite "gris" — vinified as white
    "bronner": "blanc",
    "johanniter": "blanc",
    "muscaris": "blanc",
    "sauvignac": "blanc",
    "saphira": "blanc",
    "albalonga": "blanc",
    "kanzler": "blanc",
    "juwel": "blanc",
    "mariensteiner": "blanc",
    "septimer": "blanc",
    "sibera": "blanc",
    "fidelio": "blanc",
    "sirius": "blanc",
    "orion": "blanc",
    "pollux": "blanc",
    "prinzipal": "blanc",
    "rinot": "blanc",
    "calandro": "noir",
    "calardis-blanc": "blanc",
    "calardis-musque": "blanc",
    "calardis-royal": "blanc",
    "calardis-soleil": "blanc",
    "villaris": "blanc",
    "hegel": "noir",
    "holder": "blanc",
    "freisamer": "blanc",
    "regner": "blanc",
    "ehrenbreitsteiner": "blanc",
    "osteiner": "blanc",
    "rabaner": "blanc",
    "nobling": "blanc",
    "perle": "rose",                  # pink-skinned mutation of Müller-Thurgau × Gewürz
    "gutenborner": "blanc",
    "bukettsilvaner": "blanc",
    "noblessa": "blanc",
    "muskat-trollinger": "noir",
    "blauer-gaensfusser": "noir",
    "gelber-orleans": "blanc",
    "raeuschling": "blanc",
    "kleinberger": "blanc",
    "donauriesling": "blanc",
    "donauveltliner": "blanc",
    "heunisch": "blanc",              # Heunisch Weiss is white; red mutations exist but rare
    "hartblau": "noir",
    "bolero": "noir",
    "laurot": "noir",
    "piroso": "noir",
    "pinot-nova": "noir",
    "pinot-iskra": "noir",
    "pinot-kors": "noir",
    "accent": "noir",
    "adelfraenkisch": "noir",         # historical Franken red
    "blauer-hangling": "noir",
    "bettlertraube": "noir",
    "geisdutte": "blanc",
    "rheinfelder": "blanc",
    "comtessa": "blanc",
    "divona": "blanc",
    "aromera": "blanc",
    "merlot-khorus": "noir",
    "merlot-kanthus": "noir",
    "sauvignon-cita": "blanc",
    "sauvignon-sary": "blanc",
    "sauvitage": "blanc",
    "thurling": "blanc",
    "weisser-lagler": "blanc",
    "dalkauer": "blanc",
    "wildmuskat": "blanc",
    "muscabona": "blanc",
    "orangentraube": "blanc",
    "vogelfraenkisch": "noir",
    "carillon": "blanc",
    "savilon": "blanc",
    "sulmer": "noir",
    "ladner": "blanc",
    "jakob-gerhardt-blanc": "blanc",
    "cumdeo-blanc": "blanc",
    "cumdeo-rouge": "noir",
    "staufer": "blanc",
    "hecker": "blanc",
    "allegro": "blanc",
    "artaban": "noir",
    "voltis": "blanc",
    "floreal": "blanc",
    "vidoc": "noir",
    "valerie": "blanc",
    "weisser-deckling": "blanc",
    "schwarzer-deckling": "noir",
    "blauer-arbst": "noir",
    "weisser-arbst": "blanc",
    "palas": "noir",
    "levitage": "blanc",
    "riesel": "blanc",
    # ─── Slovakia ────────────────────────────────────────────
    "devin": "blanc",                  # aromatic white (Tramín × Veltlínske červené)
    "dunaj": "noir",
    "hron": "noir",
    "rimava": "blanc",
    "vah": "blanc",
    "nitria": "blanc",
    "hetera": "blanc",
    "breslava": "blanc",               # VIVC #1671 berry-skin blanc; MUŠTOVÉ BIELE
    "milia": "blanc",                  # white-wine grape, ÚPV MUŠTOVÉ BIELE (VIVC #22818 berry-skin = rose, inherited from Traminer parent — filed blanc per the regulator + sibling Devín)
    "noria": "blanc",                  # VIVC #22819 berry-skin blanc; MUŠTOVÉ BIELE
    "nitranka": "noir",                # VIVC #17282 — Castets × Abouriou, MUŠTOVÉ MODRÉ
    "rudava": "noir",                  # VIVC #17283 — Castets × I-35-9, MUŠTOVÉ MODRÉ
    "torysa": "noir",                  # VIVC #22419 — Castets × I-35-9, MUŠTOVÉ MODRÉ
    "karpatska-perla": "blanc",        # placeholder — the PDO bears the brand name
    # ─── Czech Republic ──────────────────────────────────────
    "palava": "blanc",                 # aromatic white (Tramín × Müller-Thurgau)
    "aurelius": "blanc",
    "cabernet-moravia": "noir",
    "andre": "noir",                   # Frankovka × Svatovavřinecké (CZ)
    "neronet": "noir",
    # ─── Czech registry-only crossings from Vyhláška 88/2017 Sb. ───
    "erilon": "blanc",
    "florianka": "blanc",
    "lena": "blanc",
    "malverina": "blanc",
    "medea": "blanc",
    "mery": "blanc",
    "muskat-moravsky": "blanc",
    "rulenka": "blanc",
    "svojsen": "blanc",
    "tristar": "blanc",
    "veritas": "blanc",
    "vesna": "blanc",
    "vrboska": "blanc",
    "agni": "noir",
    "fratava": "noir",
    "jakubske": "noir",
    "kofranka": "noir",
    "nativa": "noir",
    "sevar": "noir",
    "bily-portugal": "blanc",
    "modry-janek": "noir",
    "ranuse-muskatova": "blanc",
    "sedy-portugal": "gris",
    "tramin-zluty": "blanc",

    # Croatia autochthonous (MPS specifikacija, 2026-05-29) — colours
    # taken from the regulator's own Bijele sorte / Crne sorte grouping.
    "plavina": "noir",
    "belina-hizakovo": "blanc",
    "blatina": "noir",
    "brajdica-bijela": "blanc",
    "bratkovina": "blanc",
    "cetinka": "blanc",
    "debejan-crni": "noir",
    "diseca-belina-bijela": "blanc",
    "dobricic": "noir",
    "draganela": "blanc",
    "drnekusa": "noir",
    "gegic": "blanc",
    "glavinusa": "noir",
    "kujundzusa": "blanc",
    "kurtelaska-bijela": "blanc",
    "lasina": "noir",
    "ljutac": "noir",
    "magrovina": "noir",
    "mejsko-belo": "blanc",
    "mirkovaca": "blanc",
    "mladenka": "blanc",
    "modra-kosovina": "noir",
    "nincusa": "noir",
    "okatica-bijela": "blanc",
    "osljevina": "blanc",
    "prc": "blanc",
    "rusljin-crni": "noir",
    "sansigot": "noir",
    "smudna-belina": "blanc",
    "svetokriska-belina": "blanc",
    "svrdlovina-crna": "noir",
    "trnjak": "noir",
    "trojiscina-crvena": "noir",
    "vlaska": "blanc",
    "volarovo": "blanc",
    "vranac": "noir",
    "zadarka": "noir",
    "zumic": "blanc",
    "bilan-bijeli": "blanc",
    "posip-crni": "noir",
    # Malta indigenous varieties.
    "gellewza": "noir",
    "girgentina": "blanc",
    # EU-register fiche-technique natives (GR/SI/BG/CZ/HU), 2026-06 — colour
    # from the regulator OIV code, VIVC/wein.plus-verified. `vertzami-lefko`
    # is the WHITE #13013 (distinct from the red `vertzami`); `petrokoritho-
    # mavro` is the red form (distinct from the white `petrokoritho`).
    "agoumastos-lefko": "blanc",
    "amfioni": "noir",
    "araklinos": "noir",
    "areti": "blanc",
    "ariana": "noir",
    "asproudes": "blanc",
    "avgoustiatis": "noir",
    "bekari": "noir",
    "chlores": "blanc",
    "cipro": "noir",
    "dafni": "blanc",
    "dunavska-gamza": "noir",
    "fidia": "noir",
    "gaidouria": "blanc",
    "glykopati": "noir",
    "goustolidi": "blanc",
    "kamenoruzak-bily": "blanc",
    "karabraimis": "noir",
    "katsakoulias": "noir",
    "katsano": "blanc",
    "klarnica": "blanc",
    "kokinovostitsa": "noir",
    "koliniatiko": "noir",
    "kontokladi": "blanc",
    "korinthiaki": "noir",
    "korithi": "blanc",
    "kotsifoliatiko": "noir",
    "koutsoubeli": "rose",
    "kozanitis": "noir",
    "kydonitsa": "blanc",
    "ladikino": "noir",
    "misket-kailashki": "blanc",
    "misket-vrachanski": "blanc",
    "mygdali": "blanc",
    "papadiko": "noir",
    "pergolin": "blanc",
    "petrokoritho-mavro": "noir",
    "platani": "blanc",
    "plevenski-kolorit": "noir",
    "plyto": "blanc",
    "poljsakica": "blanc",
    "potamisi": "blanc",
    "prachttraube": "blanc",
    "ritino": "noir",
    "robola-kokkini": "noir",
    "romeiko": "noir",
    "sefka": "noir",
    "skiadopoulo": "blanc",
    "skopelitiko": "noir",
    "skyloklima": "blanc",
    "skylopnichtis": "noir",
    "thiako": "noir",
    "tsaoussi": "blanc",
    "vertzami-lefko": "blanc",
    "violento": "rose",
    "vitovska-grganja": "blanc",
    "vlachiko": "noir",
    "voidomatis": "noir",
    "vossos": "blanc",
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
    s = unidecode(s)
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
