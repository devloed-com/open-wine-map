"""Commune-precise geometry for Italian wine GIs.

Bétard 2022 EU_PDO.gpkg draws PDO polygons at whole-municipality
resolution and assigns shared comuni to every appellation that touches
them — measured Barbera d'Asti ∩ Dolcetto d'Asti = 100 %, Soave ∩
Valpolicella = 53 %. The Italian *documento unico* / MASAF disciplinare
instead names the production area precisely: a list of comuni, a list
of province, or a region.

`ITCommuneIndex` parses that description and unions the named comune
polygons. It joins two public sources:

  - ISTAT `Elenco-comuni-italiani.csv` — comune name ↔ 6-digit code ↔
    provincia ↔ regione
  - Eurostat GISCO LAU — comune polygons, keyed by the same 6-digit
    code (`GISCO_ID = IT_<code>`)

The code joins the two exactly (no name-matching between them), so the
only fuzzy step is matching the disciplinare's free-text comune /
provincia / regione names against the ISTAT registry.

Resolution precedence: an explicit comune list wins; a province list is
used only when no comuni are named (province headers like "provincia
di Verona: i comuni di …" are locational, not inclusions, and are
dropped when comuni are present — mirroring the AT "im Bundesland X"
rule) — except a province the text includes whole ("l'intero territorio
amministrativo delle province di Forlì-Cesena, Ravenna e Rimini e dei
comuni di …", Rubicone), which is a member and is unioned with the
comuni; a region is the last resort.

An exclusion clause — "ad esclusione dei comuni di …", "esclusi i
comuni di Pantelleria, Favignana ed Alcamo" (Marsala), "ad eccezione
dell'intero territorio della provincia di …" — runs to the end of its
sentence: the names in it are subtracted, never added, and a quantified
province inside it is never promoted to a member. A bare "Provincia di X:"
header (Costa Toscana, Carso, Asolo) opens the comune list that follows
its colon even when the word "comuni" is absent.

Caveat: docs that say "in tutto o in parte" (whole *or partial*
territory) are resolved as whole comuni — slight boundary over-cover,
but far better than Bétard's gross overlap.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections import Counter
from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# ISTAT CSV column indices (Elenco-comuni-italiani.csv, cp1252, ';').
_COL_CODE = 4        # Codice Comune formato alfanumerico — "001001"
_COL_NAME = 6        # Denominazione in italiano
_COL_REGION = 10     # Denominazione Regione
_COL_PROVINCE = 11   # Denominazione dell'Unità territoriale sovracomunale

_KW_COMUNE = {"comune", "comuni"}
_KW_PROVINCE = {"provincia", "province"}
_KW_REGION = {"regione", "regioni"}
_KW_ALL = _KW_COMUNE | _KW_PROVINCE | _KW_REGION
_MAX_NAME_WORDS = 6

# Adjectival / official region-name forms a disciplinare may use that the
# ISTAT registry doesn't carry: "Regione Siciliana" (vs ISTAT "Sicilia").
# Keyed by _norm(ISTAT name) → extra _norm aliases.
_REGION_NAME_ALIAS = {
    "sicilia": ("siciliana",),
}


# Connectors a comune name runs through ("Castel Guelfo di Bologna",
# "Ozzano dell'Emilia", "Savignano sul Rubicone", "San Giovanni in
# Persiceto"). Not "e": it is the list conjunction ("Romagna e Verucchio"),
# so a match followed by it is a list end, not a truncated name.
_NAME_CONNECTORS = {
    "di", "del", "dell", "della", "dei", "degli", "delle",
    "sul", "sulla", "sullo", "in", "a", "al", "alla", "nel", "nell", "nella",
}
# What a bare (connector-less) name form drops: the connectors plus the
# elided "d'" / "l'" ("Sant'Angelo d'Alife" ↔ a disciplinare's "S. Angelo
# Alife", "Santa Teresa di Gallura" ↔ ISTAT "Santa Teresa Gallura").
_BARE_DROP = _NAME_CONNECTORS | {"d", "l"}


def _bare(words: list[str]) -> list[str]:
    return [w for w in words if w not in _BARE_DROP]


# ISTAT writes some hagionyms as one word ("Santarcangelo di Romagna",
# "Santeramo in Colle") where a disciplinare writes "S. Arcangelo di
# Romagna"; `_norm` folds only the spaced / apostrophed forms, so the
# fused ones are also indexed under their "san"-split form.
_FUSED_HAGIONYM_RE = re.compile(r"^(?:santo|santa|sant|san)(?=[aeiou])")
# Punctuation that closes a name inside a list ("Lizzano, in provincia di …").
_NAME_END_RE = re.compile(r"[,;:.)\]»”]$")

# A province is a whole-territory MEMBER of the area, not a locational
# qualifier of a comune list, when the keyword closes "l'intero territorio
# (amministrativo) della / delle …", "tutto il territorio della …", or when
# "l'intero territorio provinciale" follows its name. The quantifier is
# what tells the two apart: "il territorio della provincia di Rimini ad
# esclusione dei comuni di …" and "nel territorio della provincia di Reggio
# Emilia, in particolare i comuni di …" carry none and stay qualifiers.
_WHOLE_QUANTIFIERS = {"intero", "intera", "interi", "intere", "tutto", "tutta", "tutti", "tutte"}
_TERRITORY_LINKS = {"della", "delle", "dell", "di", "amministrativo", "amministrativa",
                    "autonoma", "autonome"}
_ARTICLES = {"l", "il", "lo", "la", "gli", "le"}
_KW_PROVINCIALE = "provinciale"
# The sentence is about where the wine is made, not where the grapes grow.
_WINEMAKING_RE = re.compile(
    r"^(?:vinificazion|elaborazion|imbottigliament|invecchiament|affinament|spumantizzazion)"
)
# An exclusion opens with one of these word forms — never the adverb
# "esclusivamente" ("devono essere prodotte esclusivamente nel territorio
# del Comune di Torgiano" includes Torgiano) — and runs to the end of its
# sentence, or to the closing parenthesis when it opened inside one
# ("Casale Monferrato (esclusa la parte sulla riva sinistra del Po),
# Castelletto Merli, …" — the list goes on after the bracket).
_EXCLUSION_WORDS = {"escluso", "esclusa", "esclusi", "escluse", "esclusione", "esclusioni",
                    "eccetto", "eccettuato", "eccettuata", "eccettuati", "eccettuate",
                    "eccezione", "tranne"}
# Inside an exclusion only a WHOLE unit is subtracted: "esclusi i comuni di
# Pantelleria, Favignana ed Alcamo" (Marsala), "dell'intero comune di
# Bellaria Igea Marina" (Rimini), "dei territori comunali di Cellarengo
# d'Asti" (Freisa d'Asti). The corpus's other exclusions are parts of a
# comune — "le tre isole amministrative … del comune di Atella", "i fondi
# valle … del comune di Senigallia", "Roma ad esclusione dell'area interna
# al GRA", "la fascia pianeggiante della Valdichiana" — and a partial marker
# anywhere in the clause keeps every name of the clause in the area.
_EXCL_WHOLE_WORDS = {"comune", "comuni", "comunale", "comunali"}
_EXCL_PARTIAL_WORDS = {
    "parte", "parti", "porzione", "porzioni", "zona", "zone", "area", "aree", "fascia",
    "fasce", "fondi", "fondo", "versante", "versanti", "isola", "isole", "frazione",
    "frazioni", "terreni", "terreno", "colle", "tratto", "tratti", "quelli", "quelle",
    "riva", "sponda", "vallivi", "vallive", "golenali", "pianeggiante", "pianeggianti",
    "altitudine", "quota", "metri", "località", "localita",
}
# A word that resumes an inclusion inside the same sentence.
_INCLUSION_RE = re.compile(r"^(?:comprend|includ|nonche$|oltre$)")
# Tokens ending in "." that are abbreviations, not sentence ends: "art. 3",
# "D.M. 12.5.2010", "lett. a)", "n. 4". A lookback that stopped at "art."
# would never see the winemaking verb before it.
_ABBREVIATION_RE = re.compile(
    r"^(?:art|artt|n|nn|lett|cfr|ecc|dd|d|m|p|s|dm|dpr|dlgs|reg|regg|all|allegato|"
    r"[a-z]|[ivx]+)\.$"
)


def _is_sentence_end(word: str) -> bool:
    w = word.strip("»”\")')")
    if w.endswith(";"):
        return True
    if not w.endswith("."):
        return False
    return not _ABBREVIATION_RE.match(w.lower())


def _whole_territory_before(words: list[str], i: int) -> bool:
    """Does words[i] close a quantified "territorio" phrase — "l'intero
    territorio amministrativo delle [province]", "tutto il territorio della
    [provincia]", "l'intero territorio [provinciale]"? The lookback runs over
    `_norm_words`, since the apostrophe stays inside the token ("l’intero")."""
    flat = [w for tok in words[max(0, i - 8):i] for w in _norm_words(tok)]
    j = len(flat) - 1
    while j >= 0 and flat[j] in _TERRITORY_LINKS:
        j -= 1
    if j < 0 or flat[j] not in ("territorio", "territori"):
        return False
    j -= 1
    while j >= 0 and flat[j] in _ARTICLES:
        j -= 1
    return j >= 0 and flat[j] in _WHOLE_QUANTIFIERS


def _in_winemaking_clause(words: list[str], i: int) -> bool:
    """Is the sentence running up to words[i] about winemaking operations?
    "le operazioni di vinificazione, elaborazione ed imbottigliamento …
    devono essere effettuate nell'intero territorio della provincia di
    Alessandria" (Grignolino del Monferrato Casalese) names a whole province
    that is not the grape area — the phrase must not make it a member."""
    for j in range(i - 1, -1, -1):
        if _is_sentence_end(words[j]):
            return False
        if _WINEMAKING_RE.match(_norm(words[j])):
            return True
    return False


# Spellings a disciplinare uses for an ISTAT comune that no fold recovers —
# a dropped disambiguator ("Castelguelfo" / "Castel Guelfo" for Castel Guelfo
# di Bologna), a dropped article ("Ozzano Emilia") and a source typo ("Terre
# del Sole"); all in MASAF Bianco del Sillaro Art. 3 (the first two also in
# Romagna Art. 3), each the only comune of the named province with that
# stem. Keyed by _norm(ISTAT name) → extra _norm aliases.
_COMUNE_NAME_ALIAS = {
    "castelguelfodibologna": ("castelguelfo",),
    "ozzanodellemilia": ("ozzanoemilia",),
    "castrocarotermeeterradelsole": ("castrocarotermeeterredelsole",),
}


def _fold(s: str) -> str:
    """Lowercase ASCII with apostrophes as spaces and the Italian hagionym
    prefix folded — San / Sant' / Santo / Santa / abbreviated "S." all
    collapse to "san" — so a disciplinare's "S. Alfio" matches ISTAT
    "Sant'Alfio". Word boundaries are kept; `_norm` strips them."""
    s = (s or "").lower()
    s = unicodedata.normalize("NFKD", s)
    s = re.sub(r"['’`]", " ", s)
    s = s.encode("ascii", "ignore").decode()
    # "Gioiosa Jonica" / ISTAT "Gioiosa Ionica", "Jesi": the two spellings of
    # one sound, folded on both sides.
    s = s.replace("j", "i")
    return re.sub(r"\bs(?:anto|anta|ante|ant|an)?\.?\s+", "san ", s)


def _norm(s: str) -> str:
    """Diacritics stripped, hagionym folded, only a–z0–9."""
    return re.sub(r"[^a-z0-9]+", "", _fold(s))


def _norm_words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _fold(s))


def _name_variants(raw: str) -> set[str]:
    """Normalised forms of a province/region name, including each
    slash-separated bilingual part on its own ("Bolzano/Bozen" →
    {bolzanobozen, bolzano, bozen})."""
    parts = [raw] + (raw.split("/") if "/" in raw else [])
    return {v for v in (_norm(p) for p in parts) if v}


class ITCommuneIndex:
    def __init__(
        self,
        istat_csv: Path,
        gisco_lau_zip: Path,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self._comune_by_name: dict[str, list[str]] = {}
        self._codes_by_province: dict[str, set[str]] = {}
        self._codes_by_region: dict[str, set[str]] = {}
        self._regione_keys_by_code: dict[str, set[str]] = {}
        self._province_by_code: dict[str, str] = {}
        # Word-boundary proper prefixes of every comune name ("castelguelfo",
        # "castelguelfodi" for Castel Guelfo di Bologna) — the guard that
        # stops a name from matching on its first words alone.
        self._name_prefixes: set[str] = set()
        self._geom_by_code: dict[str, BaseGeometry] = {}

        if istat_csv.exists():
            raw = istat_csv.read_bytes()
            for enc in ("cp1252", "latin-1", "utf-8-sig"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            rows = list(csv.reader(io.StringIO(text), delimiter=";"))
            aliases: list[tuple[str, str]] = []
            for r in rows[1:]:
                if len(r) <= _COL_PROVINCE:
                    continue
                code = (r[_COL_CODE] or "").strip()
                name = (r[_COL_NAME] or "").strip()
                if not (len(code) == 6 and code.isdigit() and name):
                    continue
                key = _norm(name)
                self._comune_by_name.setdefault(key, []).append(code)
                self._regione_keys_by_code[code] = _name_variants(r[_COL_REGION])
                self._province_by_code[code] = _norm(r[_COL_PROVINCE])
                forms = [_norm_words(name)]
                words = forms[0]
                if words and _FUSED_HAGIONYM_RE.match(words[0]):
                    forms.append(["san", _FUSED_HAGIONYM_RE.sub("", words[0])] + words[1:])
                # A disciplinare drops the connector of a compound name
                # ("Santa Margherita Belice" for ISTAT Santa Margherita di
                # Belice, Valle Belice IGT): index the connector-less form
                # too, as an alias that never shadows a real name.
                bare = _bare(words)
                if len(bare) >= 2 and bare != words:
                    forms.append(bare)
                for ws in forms:
                    self._name_prefixes.update("".join(ws[:k]) for k in range(1, len(ws)))
                    alias = "".join(ws)
                    if alias != key:
                        aliases.append((alias, code))
                aliases.extend((a, code) for a in _COMUNE_NAME_ALIAS.get(key, ()))
                # Bilingual ISTAT province/region names carry both forms
                # slash-joined ("Bolzano/Bozen", "Valle d'Aosta/Vallée
                # d'Aoste"); a disciplinare names just one ("provincia di
                # Bolzano"), so register each slash-part as an alias too.
                for prov in _name_variants(r[_COL_PROVINCE]):
                    self._codes_by_province.setdefault(prov, set()).add(code)
                for reg in _name_variants(r[_COL_REGION]):
                    self._codes_by_region.setdefault(reg, set()).add(code)
                    for alias in _REGION_NAME_ALIAS.get(reg, ()):  # adjectival/official forms
                        self._codes_by_region.setdefault(alias, set()).add(code)
            # An alias never shadows a comune that carries the name itself,
            # and a code is listed once under a key however many forms
            # reach it.
            for alias, code in aliases:
                codes = self._comune_by_name.setdefault(alias, [])
                if not codes:
                    codes.append(code)
                elif code in codes:
                    continue
                elif alias not in {_norm(n) for n in ()}:
                    # a real comune already carries this name: the alias
                    # would shadow it and is dropped
                    continue

        if gisco_lau_zip.exists():
            gdf = gpd.read_file(gisco_lau_zip)
            it = gdf[gdf["CNTR_CODE"] == "IT"]
            if it.crs is None or it.crs.to_string() != target_crs:
                it = it.to_crs(target_crs)
            for _, row in it.iterrows():
                gid = str(row.get("GISCO_ID") or "")
                code = gid.split("_", 1)[1] if "_" in gid else ""
                geom = row.geometry
                if len(code) == 6 and code.isdigit() and geom is not None \
                        and not geom.is_empty:
                    self._geom_by_code[code] = geom

    @property
    def n_comuni(self) -> int:
        return len(self._geom_by_code)

    # ── parsing ──────────────────────────────────────────────────────────

    def parse_geo_area(self, text: str) -> dict:
        """Parse an Italian disciplinare geo-area description into
        `{comuni, province, regioni}` name lists."""
        t = re.sub(r"[„“”\"'`]", " ", text or "")
        # pdftotext drops the space after some commas ("Jonico,San Marzano
        # di San Giuseppe"); a glued pair is two names, not one word.
        t = re.sub(r"([,;])(?=\S)", r"\1 ", t)
        out = {"comuni": [], "province": [], "regioni": [],
               "excluded_comuni": [], "excluded_province": []}
        # Parallel to out["province"]: named as a whole-territory member.
        members: list[bool] = []
        member_run = False
        bucket = None
        miss_run = 0
        # Exclusion clause state: `excluded` while inside one, `excl_paren`
        # when it opened inside a parenthesis, `excl_whole` once the clause
        # named a whole comune ("comuni di", "territori comunali di",
        # "intero territorio della provincia"), `excl_partial` once it named
        # a part of one — a partial clause subtracts nothing.
        excluded = excl_paren = excl_whole = excl_partial = False
        words = t.split()
        i = 0
        while i < len(words):
            wn = _norm(words[i])
            ws = _norm_words(words[i])
            if excluded and i > 0 and (
                _is_sentence_end(words[i - 1])
                or (excl_paren and words[i - 1].rstrip(",;.").endswith(")"))
            ):
                excluded = excl_paren = excl_whole = excl_partial = False
            if any(w in _EXCLUSION_WORDS for w in ws):
                excluded = True
                excl_paren = words[i].startswith("(")
                excl_whole = excl_partial = False
                i += 1
                continue
            if excluded:
                if _INCLUSION_RE.match(wn):
                    excluded = excl_paren = excl_whole = excl_partial = False
                elif ws and ws[-1] in _EXCL_WHOLE_WORDS:
                    excl_whole = True
                    # "… dei territori posti a valle della s.s. 16, e
                    # dell'intero comune di Bellaria Igea Marina" (Rimini):
                    # the quantifier reopens a whole exclusion after a
                    # partial one in the same clause.
                    if i > 0 and _norm(words[i - 1]) in _WHOLE_QUANTIFIERS:
                        excl_partial = False
                    if ws[-1] in ("comunale", "comunali"):
                        bucket = "comuni"
                        miss_run = 0
                elif ws and ws[-1] in ("territorio", "territori") and i + 1 < len(words) \
                        and _norm(words[i + 1]) not in ("comunale", "comunali") \
                        and _norm(words[i - 1]) not in _WHOLE_QUANTIFIERS:
                    excl_partial = True
                elif any(w in _EXCL_PARTIAL_WORDS for w in ws):
                    excl_partial = True
            if wn in _KW_COMUNE:
                bucket = "comuni"
                miss_run = 0
                i += 1
                continue
            if wn in _KW_PROVINCE:
                bucket = "province"
                member_run = not excluded and _whole_territory_before(words, i) \
                    and not _in_winemaking_clause(words, i)
                if excluded and _whole_territory_before(words, i):
                    excl_whole = True
                miss_run = 0
                i += 1
                continue
            if wn == _KW_PROVINCIALE and members and not excluded \
                    and _whole_territory_before(words, i) \
                    and not _in_winemaking_clause(words, i):
                # "Provincia di Livorno: comuni costituenti l'intero
                # territorio provinciale" (Costa Toscana) — the quantifier
                # follows the name it qualifies.
                members[-1] = True
                i += 1
                continue
            if wn in _KW_REGION:
                bucket = "regioni"
                miss_run = 0
                i += 1
                continue
            prev = out["comuni"][-1] if bucket == "comuni" and out["comuni"] else None
            matched = self._greedy_match(words, i, bucket, prev)
            if matched is not None:
                name, span = matched
                if name:
                    if excluded and bucket in ("comuni", "province"):
                        if excl_whole and not excl_partial:
                            out["excluded_" + bucket].append(name)
                    else:
                        out[bucket].append(name)
                        if bucket == "province":
                            members.append(member_run)
                    miss_run = 0
                else:
                    # One unresolved comune, not one miss per word of it.
                    miss_run += 1
                i += span
                # "Provincia di Livorno: Bibbona, Bolgheri, …" — the colon
                # after a province name opens the comune list it heads,
                # with or without the word "comuni" (Costa Toscana, Carso,
                # Asolo Prosecco, Alta Langa).
                if name and bucket == "province" and words[i - 1].rstrip("»”)").endswith(":"):
                    bucket = "comuni"
                    miss_run = 0
            elif bucket == "province" and not member_run and out["comuni"] \
                    and i > 0 and (_norm(words[i - 1]) in ("e", "ed", "nonche")
                                   or words[i - 1].endswith((",", ";"))) \
                    and (matched := self._greedy_match(words, i, "comuni", prev)) is not None:
                # "Menfi, in provincia di Agrigento e Contessa Entellina in
                # provincia di Palermo" (Valle Belice): a comune list resumes
                # after a locational province — the qualifier closed, the
                # list did not.
                name, span = matched
                bucket = "comuni"
                if name:
                    if not excluded:
                        out["comuni"].append(name)
                    elif excl_whole and not excl_partial:
                        out["excluded_comuni"].append(name)
                    miss_run = 0
                else:
                    miss_run += 1
                i += span
            else:
                # A name list runs name–connector–name; once prose
                # resumes, several non-name words pile up — close the
                # bucket so comune-homonyms in the prose ("Roma", "Monti",
                # "Ponte") aren't scooped into the list. A capitalised run
                # the index does not carry ("Santa Margherita Belice" for
                # ISTAT's "… di Belice") is one unresolved name, one miss,
                # never a bucket closer on its own.
                if not excluded:
                    miss_run += 1
                i += 1
                if bucket and words[i - 1][:1].isupper():
                    while i < len(words) and i - 1 < len(words) and (
                        words[i][:1].isupper() or _norm(words[i]) in _NAME_CONNECTORS
                    ) and _norm(words[i]) not in _KW_ALL \
                            and not _NAME_END_RE.search(words[i - 1]):
                        i += 1
                if miss_run >= 4:
                    bucket = None
        # A province / region named alongside an explicit comune list is
        # locational ("… in provincia di Livorno", "provincia di Verona:
        # i comuni di …") — not an inclusion. A province the text includes
        # whole stays: the area is that province plus the comuni.
        if out["comuni"]:
            out["province"] = [p for p, member in zip(out["province"], members) if member]
            out["regioni"] = []
        return out

    def _greedy_match(
        self, words: list[str], i: int, bucket: str | None, prev: str | None = None,
    ):
        """Longest known name starting at words[i] for the active bucket;
        `("", n)` when the text runs a known name past the match — the
        `n` words of one comune the index does not carry. `prev` is the
        comune matched just before, the list's geographic context."""
        if bucket == "comuni":
            index = self._comune_by_name
        elif bucket == "province":
            index = self._codes_by_province
        elif bucket == "regioni":
            index = self._codes_by_region
        else:
            return None
        for span in range(min(_MAX_NAME_WORDS, len(words) - i), 0, -1):
            # Join with a space so `_norm`'s hagionym-fold sees word
            # boundaries ("S. Maria" → "san maria") before the final
            # alnum strip.
            text = " ".join(words[i:i + span])
            cand = _norm(text)
            if cand not in index:
                # The text's connectors may differ from ISTAT's ("Concordia
                # sul Secchia" / "Concordia sulla Secchia"): the bare forms
                # of both sides meet in the index (the bare alias). Only a
                # span that opens and closes on a content word — a leading
                # "di" would fold "di Lugo di Vicenza" onto Lugo di Vicenza
                # one word early, a trailing one would skip the run-on guard.
                ws = _norm_words(text)
                if not ws or ws[0] in _BARE_DROP or ws[-1] in _BARE_DROP:
                    continue
                bare = "".join(_bare(ws))
                if len(bare) < 4 or bare == cand or bare not in index:
                    continue
                cand = bare
            if bucket == "comuni" and i + span < len(words):
                extra = self._name_run_on(words, i + span, cand, prev)
                if extra:
                    return "", span + extra
            return cand, span
        return None

    def _name_run_on(self, words: list[str], j: int, cand: str, prev: str | None) -> int:
        """Words from words[j] on that continue the matched comune `cand`
        into a longer name the index does not carry — "Tramonti di Biassa"
        (a frazione of La Spezia, not Tramonti SA), "Castelnuovo del Friuli"
        (ISTAT spells Castelnovo; Castelnuovo is in Trentino), a typo "S.
        Arcangelo di Romagn" (not Sant'Arcangelo, PZ). 0 when `cand` is the
        whole name and list prose follows."""
        if _NAME_END_RE.search(words[j - 1]):
            return 0
        conn = _norm_words(words[j])
        if not conn or conn[0] not in _NAME_CONNECTORS \
                or cand + conn[0] not in self._name_prefixes:
            return 0
        if len(conn) > 1:  # "dell’Xyz" — the next name word rides in the same token
            nxt, extra = re.split(r"[’'`]", words[j], maxsplit=1)[-1], 1
        elif j + 1 < len(words):
            nxt, extra = words[j + 1], 2
        else:
            return 0
        nxt = nxt.lstrip("«(“")
        # A name runs on into a capitalised word; "Lizzano in provincia di
        # Taranto" is Lizzano then list prose, and a keyword is never eaten.
        if not nxt[:1].isupper() or _norm(nxt) in _KW_ALL:
            return 0
        # A comune named with a regional qualifier ("Lugo di Romagna" for
        # ISTAT Lugo, RA) sits in the list's province; the homonym prefix a
        # longer name starts with (Tramonti SA in a La Spezia list) does not.
        if prev and self._share_province(cand, prev):
            return 0
        return extra

    def _share_province(self, a: str, b: str) -> bool:
        pa = {self._province_by_code.get(c) for c in self._comune_by_name.get(a, ())}
        pb = {self._province_by_code.get(c) for c in self._comune_by_name.get(b, ())}
        return bool((pa & pb) - {None, ""})

    # ── resolution ───────────────────────────────────────────────────────

    def resolve(
        self, geo_area: str, regione: str = "",
    ) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve one Italian appellation's geometry from its geo-area
        text. Returns (geometry, geom_source, stats) — geom_source is
        `gisco-comune-union`, `gisco-comune-provincia-union` when the text
        also includes whole provinces, `gisco-provincia-union` or
        `gisco-regione-union`. `regione` is the record's derived regione;
        it settles homonyms. A name ISTAT carries
        in that regione keeps only that comune (Castro LE, not BG, for a
        Puglia record). A name with no comune there is kept only when the
        list names another comune of the same province: an appellation that
        crosses into a second regione lists a group there (Alto Livenza: six
        Pordenone comuni; Garda: fifteen Verona comuni), while a lone match
        outside the regione is the homonym of a prose word or of a place
        elsewhere (Rio LI for "il rio Funtana" in Sibiola, Rivoli TO for
        Garda's Rivoli Veronese)."""
        parsed = self.parse_geo_area(geo_area or "")
        codes: set[str] = set()
        source = "none"
        n_units = 0

        if parsed["comuni"]:
            source = "gisco-comune-union"
            want = _norm(regione)
            if want not in self._codes_by_region:
                want = ""
            cands = {
                nm: [c for c in self._comune_by_name.get(nm, []) if c in self._geom_by_code]
                for nm in parsed["comuni"]
            }
            if want:
                local = {
                    nm: [c for c in cs if want in self._regione_keys_by_code.get(c, ())]
                    for nm, cs in cands.items()
                }
                support = Counter(
                    p for nm, cs in cands.items() if not local[nm]
                    for p in {self._province_by_code.get(c) for c in cs}
                )
                for nm, cs in cands.items():
                    cands[nm] = local[nm] or [
                        c for c in cs if support[self._province_by_code.get(c)] >= 2
                    ]
            for nm in parsed["comuni"]:
                codes.update(cands[nm])
                n_units += len(cands[nm])
            for nm in parsed["province"]:  # whole-territory members only (see parse)
                hit = self._codes_by_province.get(nm, set()) & self._geom_by_code.keys()
                if hit:
                    codes |= hit
                    n_units += 1
                    source = "gisco-comune-provincia-union"
        elif parsed["province"]:
            source = "gisco-provincia-union"
            for nm in parsed["province"]:
                hit = self._codes_by_province.get(nm, set()) & self._geom_by_code.keys()
                codes |= hit
                if hit:
                    n_units += 1
        elif parsed["regioni"]:
            source = "gisco-regione-union"
            for nm in parsed["regioni"]:
                hit = self._codes_by_region.get(nm, set()) & self._geom_by_code.keys()
                codes |= hit
                if hit:
                    n_units += 1

        # "ad esclusione dei comuni di …": the excluded units leave the
        # union (a province inside an exclusion is never a member, so only
        # its comuni can be in `codes` — through a whole-province term).
        n_excluded = 0
        for nm in parsed.get("excluded_comuni", ()):
            drop = set(self._comune_by_name.get(nm, ())) & codes
            n_excluded += len(drop)
            codes -= drop
        for nm in parsed.get("excluded_province", ()):
            drop = self._codes_by_province.get(nm, set()) & codes
            n_excluded += len(drop)
            codes -= drop

        if not codes:
            return None, "none", {"matched": 0, "unmatched": 0, "n_units": n_units}
        geom = unary_union([self._geom_by_code[c] for c in codes])
        stats = {"matched": len(codes), "unmatched": 0, "n_units": n_units}
        if n_excluded:
            stats["excluded"] = n_excluded
        return geom, source, stats
