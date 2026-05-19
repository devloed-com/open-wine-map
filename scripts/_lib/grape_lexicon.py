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
        slug = _canonical_slug(name)
        if not slug or slug in GRAPE_BLOCKLIST:
            continue
        if slug in seen:
            continue
        seen.add(slug)
        out.append({
            "slug": slug,
            "name": name,
            "colour": COLOUR_CODES.get(m.group(1), ""),
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
