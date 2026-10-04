"""GR-side geometry resolution — Bétard PDO + GISCO commune-list fallback.

Reuses the shared artifacts the ES pipeline already caches:
  - `raw/es/figshare/EU_PDO.gpkg` (Bétard et al. 2022, CC0) — covers
    all 33 GR PDOs (`PDO-GR-*`). Greece joined the EU in 1981; every
    GR PDO predates the Nov-2021 cutoff.
  - `raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip` (Eurostat GISCO LAU
    2024, CC-BY 4.0) — ~6,142 Greek δημοτική κοινότητα (community)
    polygons (CNTR_CODE='EL' — Greece's EU country code, *not* ISO
    `GR`) used by the commune-list fallback. Note: GISCO LAU is at
    community granularity in Greece (finer than the δήμος / dimos),
    so the parser-side normaliser must strip the tier prefix
    `Δημοτική Κοινότητα NAME` → `NAME`.

Stage 04 resolves each GR record by:

  1. **figshare-pdo** — exact `file_number` → `PDOid` match. Covers
     all 33 GR DOPs.
  2. **gisco-nuts-region (curated pin)** — a `slug → [NUTS_ID]`
     override in `nuts.py` is curator-verified, so it outranks the
     commune heuristic below (which parses free prose and is silently
     partial whenever a name fails to match).
  3. **gisco-commune-list** — parse the documento-unic geo-area body
     into δήμος / κοινότητα names (Greek-preserving) and union
     matching GISCO LAU polygons. Mirrors the RO / BG chains. v1 hit
     rate is small since only ~11 of 147 GR wines have a fetchable
     single document; the 114 PGIs are mostly content-stubs. A name
     that matches several communes nationwide is ambiguous and is
     skipped, not unioned.
  4. **gisco-nuts-region (by name)** — the spec's cited NUTS unit, else
     the appellation name. Never the `region` facet.
  5. **stub-no-geometry** — no polygon resolvable (the dominant case
     for the ~110 grandfathered Greek PGIs whose only eAmbrosia
     reference is an `Ares(...)` summary-sheet). Visible in the
     sidebar/search, absent from the map until curator-pinned.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# " της Λάρισας" / " του Νομού Χ" / " των Χανίων" at the end of a
# candidate: an article plus one to three capitalised tokens.
# Greek iotacism / isochrony: η ι υ ει οι υι all sound [i], ο ω [o], αι [e];
# a spec and GISCO often spell one name two ways (Κομήτου / Κομίτου,
# Ρογών / Ρωγών, Μεσσοράχης / Μεσορράχης). The phonetic key folds them.
# "ου" [u] is folded first to a placeholder so its υ is not read as [i].
_PHON_PAIRS = (("ου", "u"), ("ει", "ι"), ("οι", "ι"), ("υι", "ι"), ("αι", "ε"), ("η", "ι"), ("υ", "ι"), ("ω", "ο"))
_DOUBLE_CONS_RE = re.compile(r"([βγδζθκλμνξπρστφχψ])\1")
# Inflection endings of Greek place names, longest first; the stem is what
# is left when one is removed (Κερασίτσας / Κερασίτσης → κερασιτσ).
def phonetic_key(key: str) -> str:
    """The pronunciation-level key of a normalised name (see `_PHON_PAIRS`)."""
    s = unicodedata.normalize("NFD", key.casefold())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    for a, b in _PHON_PAIRS:
        s = s.replace(a, b)
    return _DOUBLE_CONS_RE.sub(r"\1", s)


_STEM_ENDINGS_RAW = (
    "εως", "εων", "ιου", "ιας", "ιων", "αίοι", "αίων", "ειο", "ιο", "ια",
    "ων", "ου", "ας", "ης", "ος", "ις", "ες", "οι", "α", "η", "ο", "ι", "ε",
)
# The one place-name word whose stem is shorter than the minimum: Άγιος /
# Αγία / Αγίου … (Άγιος Στέφανος in a spec, Αγίου Στεφάνου in GISCO).
_SHORT_STEM_WORDS = {
    phonetic_key(w): "αγ" for w in ("άγιος", "αγία", "αγίου", "αγίας", "αγίων", "άγιοι", "άγιο")
}


# The endings as they read after the phonetic fold (ης → ισ, ων → ον …),
# longest first, deduplicated.
_STEM_ENDINGS = tuple(sorted({phonetic_key(e) for e in _STEM_ENDINGS_RAW}, key=len, reverse=True))
assert "ασ" in _STEM_ENDINGS and "u" in _STEM_ENDINGS


def stem_key(key: str) -> str:
    """Phonetic key with each word's inflection ending removed."""
    words = []
    for w in phonetic_key(key).split():
        if w in _SHORT_STEM_WORDS:
            words.append(_SHORT_STEM_WORDS[w])
            continue
        for end in _STEM_ENDINGS:
            if w.endswith(end) and len(w) - len(end) >= 4:
                w = w[: -len(end)]
                break
        words.append(w)
    return " ".join(words)


def _pin_targets(pin) -> list[str]:
    """A pin's GISCO targets: one id / prefix, or a list of them."""
    if not pin:
        return []
    return list(pin) if isinstance(pin, (list, tuple)) else [pin]


# NUTS name tokens that are not a place a list item could lie in.
_NUTS_TOKEN_STOPLIST = frozenset({"ελλαδα", "ελλασ", "στερεα"})

# Abbreviations Greek specs use in place names, with every inflected form a
# GISCO name may carry (the gender is not recoverable from the abbreviation).
_ABBREVIATIONS = {
    "κ.": ("κάτω",), "άν.": ("άνω",), "αν.": ("άνω",), "ν.": ("νέου", "νέας", "νέων", "νέο", "νέα"),
    "αγ.": ("αγίου", "αγίας", "αγίων"), "αρχ.": ("αρχαίας", "αρχαίου", "αρχαίων"),
    "παλ.": ("παλαιού", "παλαιάς", "παλαιών"), "μ.": ("μεγάλου", "μεγάλης", "μεγάλων"),
}


def _expand_abbreviations(key: str) -> list[str]:
    """Every reading of a normalised key whose first word is an abbreviation."""
    words = key.split()
    if not words or words[0] not in _ABBREVIATIONS:
        return []
    return [" ".join([full, *words[1:]]) for full in _ABBREVIATIONS[words[0]]]


_GENITIVE_QUALIFIER_RE = re.compile(
    r"\s+(?:της|του|των)\s+[Α-ΩΆΈΉΊΌΎΏΪΫ][^\s,;()]*(?:\s+[Α-ΩΆΈΉΊΌΎΏΪΫ][^\s,;()]*){0,2}\s*$"
)

class GRPolygonIndex:
    """In-memory polygon index for GR records: Bétard PDO match +
    GISCO κοινότητα-list fallback."""

    def __init__(
        self,
        figshare_gpkg: Path,
        gisco_lau_zip: Path | None = None,
        nuts3_geojson: Path | None = None,
        nuts2_geojson: Path | None = None,
        target_crs: str = "EPSG:4326",
    ) -> None:
        self.target_crs = target_crs
        self._pdo_polygons: dict[str, BaseGeometry] = {}
        # commune (LAU_NAME, normalised) → list of (GISCO_ID, polygon).
        self._lau_by_name: dict[str, list[tuple[str, BaseGeometry]]] = {}
        # GISCO_ID prefix → polygons. Greek LAU ids are hierarchical —
        # EL_13020105 is community 05 of municipal unit 01 of municipality
        # 02 of Chalkidiki 13 — so a δήμος (7-character prefix) or a
        # δημοτική ενότητα (9) is the union of its communities.
        self._lau_by_prefix: dict[str, list[BaseGeometry]] = {}
        self._lau_ids_by_prefix: dict[str, list[str]] = {}
        # first word of a normalised name → the multi-word names starting
        # with it, for the bare-name homonym test in `_lau_candidates`.
        self._lau_keys_by_head: dict[str, set[str]] = {}
        # last word of a normalised name → the multi-word names ending with
        # it, for a δήμος whose seat is "Λουτρών Αιδηψού" (see `units_union`).
        self._lau_keys_by_tail: dict[str, set[str]] = {}
        self._lau_rep: dict[str, BaseGeometry] = {}
        self._lau_geom: dict[str, BaseGeometry] = {}
        # pronunciation-level and stem-level keys → entries, the fallbacks
        # for a name GISCO spells otherwise (see `_lau_candidates`).
        self._lau_by_phon: dict[str, list[tuple[str, BaseGeometry]]] = {}
        self._lau_by_stem: dict[str, list[tuple[str, BaseGeometry]]] = {}
        # stem of the first word of a compound name → entries ("Σπάτα" in a
        # spec, "Σπάτων - Λούτσας" in GISCO), see `_lau_candidates`.
        self._lau_by_head_stem: dict[str, list[tuple[str, BaseGeometry]]] = {}
        # the NUTS units the current record's text names (set by `resolve`),
        # and their name tokens — a list item that only repeats one of them
        # ("(Εύβοια)" after the wine's name) is not a unit to draw
        self._named_units: list[BaseGeometry] = []
        self._named_unit_names: list[str] = []
        self._n_lau = 0
        # NUTS region polygons for the PGI fallback: NUTS_ID → geometry,
        # plus a normalised-name-token → NUTS_ID index.
        self._nuts_by_id: dict[str, BaseGeometry] = {}
        self._nuts_name_to_id: dict[str, str] = {}
        # stem of a NUTS name token → NUTS_ID ("Αττικής" in a spec qualifier,
        # "Aττική" in the layer)
        self._nuts_stem_to_id: dict[str, str] = {}

        if figshare_gpkg.exists():
            gdf = gpd.read_file(figshare_gpkg)
            gdf = gdf[gdf["PDOid"].astype(str).str.startswith(("PDO-GR", "PGI-GR"))]
            if gdf.crs is None or gdf.crs.to_string() != target_crs:
                gdf = gdf.to_crs(target_crs)
            for _, row in gdf.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    self._pdo_polygons[row["PDOid"]] = row.geometry

        if gisco_lau_zip is not None and gisco_lau_zip.exists():
            from .commune import _normalise_commune  # late import — same package
            gdf = gpd.read_file(gisco_lau_zip)
            # GISCO uses CNTR_CODE='EL' for Greece (EU convention, not ISO).
            gr = gdf[gdf["CNTR_CODE"] == "EL"]
            if gr.crs is None or gr.crs.to_string() != target_crs:
                gr = gr.to_crs(target_crs)
            for _, r in gr.iterrows():
                name = (r.get("LAU_NAME") or "").strip()
                geom = r.geometry
                if not name or geom is None or geom.is_empty:
                    continue
                gid = (r.get("GISCO_ID") or "").strip()
                key = _normalise_commune(name)
                self._lau_by_name.setdefault(key, []).append((gid, geom))
                self._lau_by_phon.setdefault(phonetic_key(key), []).append((gid, geom))
                self._lau_by_stem.setdefault(stem_key(key), []).append((gid, geom))
                self._lau_rep[gid] = geom.representative_point()
                self._lau_geom[gid] = geom
                if " " in key:
                    self._lau_keys_by_head.setdefault(key.split(" ", 1)[0], set()).add(key)
                    self._lau_keys_by_tail.setdefault(key.rsplit(" ", 1)[1], set()).add(key)
                    head_stem = stem_key(key.split(" ", 1)[0])
                    if len(head_stem) >= 4:
                        self._lau_by_head_stem.setdefault(head_stem, []).append((gid, geom))
                # prefecture (5), Kallikratis municipality (7), municipal unit
                # (9) and the community itself, so a pin or a curated prefix
                # may name any tier.
                for n in (5, 7, 9, len(gid)):
                    self._lau_by_prefix.setdefault(gid[:n], []).append(geom)
                    self._lau_ids_by_prefix.setdefault(gid[:n], []).append(gid)
                self._n_lau += 1

        self._load_nuts(nuts3_geojson, target_crs)
        self._load_nuts(nuts2_geojson, target_crs)

    def _load_nuts(self, path: Path | None, target_crs: str) -> None:
        """Index the EL features of a GISCO NUTS GeoJSON (any level) by
        NUTS_ID and by normalised name-token (for the PGI fallback)."""
        if path is None or not path.exists():
            return
        from .nuts import name_tokens  # late import — same package
        gdf = gpd.read_file(path)
        gdf = gdf[gdf["CNTR_CODE"] == "EL"]
        if gdf.crs is None or gdf.crs.to_string() != target_crs:
            gdf = gdf.to_crs(target_crs)
        for _, r in gdf.iterrows():
            nid = (r.get("NUTS_ID") or "").strip()
            geom = r.geometry
            if not nid or geom is None or geom.is_empty:
                continue
            self._nuts_by_id[nid] = geom
            for tok in name_tokens(r.get("NUTS_NAME") or ""):
                self._nuts_name_to_id.setdefault(tok, nid)
                self._nuts_stem_to_id.setdefault(stem_key(tok), nid)

    @property
    def n_pdo_polygons(self) -> int:
        return len(self._pdo_polygons)

    @property
    def n_lau(self) -> int:
        return self._n_lau

    def figshare_polygon(self, file_number: str) -> BaseGeometry | None:
        return self._pdo_polygons.get(file_number)

    def _fuzzy_in_prefixes(
        self, key: str, prefixes: Iterable[str],
    ) -> tuple[str, BaseGeometry, int] | None:
        """The one community under `prefixes` whose pronunciation is within
        a typo of `key` (rapidfuzz ratio ≥ 88, the runner-up ≥ 8 points
        behind): a spec's "Καλοποδίου" / "Μεγαπλατάντου" against GISCO's
        Καλαποδίου / Μεγαπλατάνου inside the unit the text itself names.
        Never outside such a unit — a prefecture holds near-namesakes."""
        from rapidfuzz import fuzz
        prefixes = tuple(prefixes)
        if not prefixes:
            return None
        target = phonetic_key(key)
        scored: list[tuple[int, str, BaseGeometry]] = []
        for name_key, entries in self._lau_by_name.items():
            for gid, geom in entries:
                if gid.startswith(prefixes):
                    scored.append((int(fuzz.ratio(target, phonetic_key(name_key))), gid, geom))
        scored.sort(key=lambda t: -t[0])
        if not scored or scored[0][0] < 88:
            return None
        if len(scored) > 1 and scored[1][0] >= scored[0][0] - 8:
            return None
        return scored[0][1], scored[0][2], scored[0][0]

    def commune_union(
        self, commune_names: Iterable[str], within: BaseGeometry | None = None,
        pins: dict[str, str] | None = None, established: Iterable[str] = (),
        fuzzy_prefixes: Iterable[str] = (),
    ) -> tuple[BaseGeometry | None, dict]:
        """Union the GISCO LAU polygons matching the given δήμος /
        κοινότητα names (after Greek-preserving normalisation).

        `pins` (normalised name → community id, from
        commune_overrides.json) are taken first. `within` is the NUTS unit
        the spec cites ("a. Περιοχή NUTS GR242 Εύβοια"): it settles a
        homonym and lets a phonetic or stem match inside it beat an exact
        row outside it (Κάρυστος named Αμυγδαλιά; the one exact row is in
        Φωκίδα, the Euboean village is Αμυγδαλέα) — but a lone exact row
        outside it is kept, since a spec's NUTS line names one unit even
        when the zone straddles two (Πλαγιές Κιθαιρώνα: Βοιωτία and Αττική).
        `established` seeds the same-δήμος rule with the municipality
        prefixes of units already resolved."""
        polys: list[BaseGeometry] = []
        matched: list[str] = []
        unmatched: list[str] = []
        ambiguous: list[str] = []
        fuzzy: list[str] = []
        pinned: list[str] = []
        pending: list[tuple[str, list[tuple[str, BaseGeometry]], str]] = []
        ids: list[str] = []
        pins = pins or {}
        from .commune import _normalise_commune
        for raw_name in commune_names:
            key = _normalise_commune(raw_name)
            pin = [t for t in _pin_targets(pins.get(key)) if t in self._lau_by_prefix]
            if pin:
                # a pinned id or prefix names every row under it
                for t in pin:
                    polys.extend(self._lau_by_prefix[t])
                    ids.extend(self._lau_ids_by_prefix[t])
                matched.append(raw_name)
                pinned.append(f"{raw_name} → {'+'.join(pin)} [{sum(len(self._lau_ids_by_prefix[t]) for t in pin)}]")
                continue
            cands, kind, homonym = self._lau_candidates(raw_name, within)
            if cands is None:
                continue
            if not cands and fuzzy_prefixes:
                hit = self._fuzzy_in_prefixes(key, fuzzy_prefixes)
                if hit is not None:
                    ids.append(hit[0])
                    polys.append(hit[1])
                    matched.append(raw_name)
                    fuzzy.append(f"{raw_name} → {hit[0]} (typo {hit[2]})")
                    continue
            if not cands:
                unmatched.append(raw_name)
                continue
            if len(cands) > 1 or homonym or kind in ("phonetic", "stem", "tail"):
                pending.append((raw_name, cands, kind))
                continue
            ids.append(cands[0][0])
            polys.append(cands[0][1])
            matched.append(raw_name)
        # Greek community names repeat nationwide — Ροδιά is six communes
        # (one of them on Crete), Τούμπα three — and unioning every homonym
        # stretched appellations across the country. A homonym — also one
        # the NUTS scope narrowed to a single row, or a phonetic / stem
        # match — is kept only when exactly one candidate sits in a δήμος
        # the unambiguous names already established (or, inside the spec's
        # NUTS unit, is the only candidate there); otherwise it contributes
        # nothing and is reported.
        dimoi = {i[:7] for i in ids} | set(established)
        for raw_name, cands, kind in pending:
            local = [c for c in cands if c[0][:7] in dimoi]
            if len(local) != 1 and within is not None and len(cands) == 1:
                local = cands
            if len(local) == 1:
                ids.append(local[0][0])
                polys.append(local[0][1])
                matched.append(raw_name)
                if kind in ("phonetic", "stem", "tail"):
                    fuzzy.append(f"{raw_name} → {local[0][0]} ({kind})")
            else:
                ambiguous.append(f"{raw_name} ({len(cands)}{', ' + kind if kind in ('phonetic', 'stem') else ''})")
        stats = {
            "matched": len(matched),
            "unmatched": len(unmatched),
            "names_unmatched": unmatched[:30],
            "names_ambiguous": ambiguous[:30],
            "names_fuzzy": fuzzy[:30],
            "pinned": pinned[:30],
            "gisco_ids": list(dict.fromkeys(ids)),
        }
        if not polys:
            return None, stats
        return unary_union(polys), stats

    def _inside(
        self, cands: list[tuple[str, BaseGeometry]], within: BaseGeometry | None,
    ) -> list[tuple[str, BaseGeometry]]:
        if within is None:
            return cands
        out = []
        for c in cands:
            if within.contains(self._lau_rep.get(c[0]) or c[1].representative_point()):
                out.append(c)
            elif c[1].intersects(within) and c[1].intersection(within).area > 0.5 * c[1].area:
                # a coastal unit whose representative point the generalised
                # NUTS coastline leaves at sea (Άγιο Όρος)
                out.append(c)
        return out

    def named_nuts_units(self, area_text: str) -> list[BaseGeometry]:
        """The NUTS units whose name the area text mentions ("του Ν.
        Αττικής", "Νομού Βοιωτίας", the spec's NUTS line): a row lying in
        none of them is a homonym elsewhere."""
        from .commune import area_body
        from .nuts import greek_norm
        norm = greek_norm(area_body(area_text or ""))
        out = []
        self._named_unit_names = []
        for tok, nid in self._nuts_name_to_id.items():
            if tok in _NUTS_TOKEN_STOPLIST or len(tok) < 5 or nid not in self._nuts_by_id:
                continue
            # the name as a whole word in any case ending: "Αττική" /
            # "Αττικής", never "παρουσίαση" for Πάρος
            if re.search(rf"\b{re.escape(tok[:-1])}\w{{0,3}}\b", norm):
                out.append(self._nuts_by_id[nid])
                self._named_unit_names.append(tok)
        return out

    def _scope(
        self, cands: list[tuple[str, BaseGeometry]], within: BaseGeometry | None,
    ) -> list[tuple[str, BaseGeometry]]:
        """Candidates inside the spec's unit; else inside a unit the text
        names; else none when the text names any unit at all."""
        inside = self._inside(cands, within) if within is not None else []
        if inside:
            return inside
        if within is None and len(cands) <= 1:
            # no NUTS line to bound the text: a name GISCO carries once is
            # taken as written (Άγιο Όρος lies in no NUTS-3 polygon at all)
            return cands
        if self._named_units:
            return [c for c in cands if any(self._inside([c], u) for u in self._named_units)]
        return cands if within is None else []

    def _lau_candidates(
        self, raw_name: str, within: BaseGeometry | None = None,
    ) -> tuple[list[tuple[str, BaseGeometry]] | None, str, bool]:
        """The LAU entries a list item may name, with how they were found
        and whether the name is a homonym nationwide: exact on the
        normalised name; else the bare head of "Δαμασίου της Λάρισας" (a
        trailing genitive place qualifier) or of "Μαρκοπούλου Αττικής" (a
        trailing NUTS-unit name), when that head is itself a community;
        else — inside the spec's NUTS unit, or nationwide when the spec
        cites none — a phonetic match, then a stem match. Inside the unit
        also beats an exact row outside it. (None, "", False) for an empty
        item."""
        from .commune import _normalise_commune
        from .eniaio_engrafo import greek_norm
        key = _normalise_commune(raw_name)
        if not key:
            return None, "", False
        exact = self._lau_by_name.get(key)
        kind = "exact"
        if not exact:
            head = _GENITIVE_QUALIFIER_RE.sub("", raw_name).strip()
            qualifier = None
            if head == raw_name.strip():
                words = raw_name.split()
                if len(words) >= 2:
                    last = greek_norm(words[-1]).strip()
                    # "Παλλήνη Αττικής": the genitive of the unit's name
                    nid = self._nuts_name_to_id.get(last) or self._nuts_stem_to_id.get(stem_key(last))
                    if nid:
                        head = " ".join(words[:-1])
                        qualifier = self._nuts_by_id.get(nid)
            if head and head != raw_name.strip():
                key = _normalise_commune(head)
                exact = self._lau_by_name.get(key)
                kind = "qualifier"
                if exact and qualifier is not None:
                    # "Μαρκοπούλου Αττικής": the qualifier names the NUTS
                    # unit the community lies in, so it settles the homonym.
                    cands = self._with_qualified_homonyms(key, exact)
                    inside = self._inside(cands, qualifier)
                    return (inside or cands), kind, len(cands) > 1
        cands = self._with_qualified_homonyms(key, exact or [])
        homonym = len(cands) > 1
        # An exact row outside the spec's unit is kept only where the text
        # names the unit it lies in (Πλαγιές Κιθαιρώνα names both Βοιωτία
        # and Αττική); Δοκός of Ροδόπη is not Euboea's Δοκός.
        scoped = self._scope(cands, within)
        if scoped:
            return scoped, kind, homonym
        cands = []
        for fkind, index, fkey in (
            ("phonetic", self._lau_by_phon, phonetic_key(key)),
            ("stem", self._lau_by_stem, stem_key(key)),
        ):
            if not fkey or len(fkey.replace(" ", "")) < (4 if fkind == "stem" else 5):
                continue
            found = self._scope(index.get(fkey) or [], within)
            if within is None and cands and not self._named_units:
                found = []  # an exact row exists and no scope disqualifies it
            if found:
                return found, fkind, len(index.get(fkey) or []) > 1
        if not cands and "." in key:
            # "Κ. Τιθορέας", "Αρχ. Ολυμπίας", "Αγ. Άννης": expand the
            # abbreviation every way it inflects and keep a unique hit.
            hits: dict[str, tuple[str, BaseGeometry]] = {}
            hkind = ""
            for variant in _expand_abbreviations(key):
                for fkind, index, fkey in (
                    ("exact", self._lau_by_name, variant),
                    ("phonetic", self._lau_by_phon, phonetic_key(variant)),
                ):
                    for pair in self._scope(index.get(fkey) or [], within):
                        hits.setdefault(pair[0], pair)
                        hkind = hkind or fkind
                if hits:
                    break
            if hits:
                found = list(hits.values())
                return found, hkind, len(found) > 1
        if not cands and " " in key:
            # "Μονοπολάτων Σκινέως": a community named with a local qualifier
            # GISCO does not carry — its head, when unique in scope.
            head_key = key.rsplit(" ", 1)[0]
            all_heads = self._lau_by_name.get(head_key) or []
            found = self._scope(all_heads, within)
            if len(found) == 1 and (within is not None or self._named_units or len(all_heads) == 1):
                return found, "head", False
            # "Μοναστήρια Μεταξάτων": a place inside a community, named with
            # the community's name as its tail — that community, when
            # unique in the spec's unit; reported as a proxy.
            tail_key = key.rsplit(" ", 1)[1]
            found = self._scope(self._lau_by_name.get(tail_key) or [], within)
            if len(found) == 1 and within is not None and not self._lau_keys_by_head.get(key.split(" ", 1)[0]):
                return found, "tail", False
        if not cands and " " not in key and len(stem_key(key)) >= 4:
            # "Σπάτα": GISCO merged the town with a neighbour under a
            # compound name ("Σπάτων - Λούτσας"); its head, when unique in scope.
            heads = self._lau_by_head_stem.get(stem_key(key)) or []
            found = self._scope(heads, within)
            if len(found) == 1 and (within is not None or self._named_units or len(heads) == 1):
                return found, "head", False
        return cands, kind, homonym

    def _dimos_unit_by_seat_tail(
        self, raw_name: str, within: BaseGeometry | None,
    ) -> tuple[str, list[str]] | None:
        """A pre-2011 δήμος whose name is not a community's own but the
        tail of its seat's — Δήμος Αιδηψού, seat Λουτρά Αιδηψού; Δήμος
        Αυλίδος, seat Παραλία Αυλίδος. The unit is the 9-character prefix
        those communities share; several prefixes is ambiguity, not a
        match. Returns (prefix, [seat keys]) or None."""
        from .commune import _normalise_commune
        key = _normalise_commune(raw_name)
        if not key or " " in key:
            return None
        prefixes: dict[str, list[str]] = {}
        for other in self._lau_keys_by_tail.get(key, ()):
            for gid, _geom in self._inside(self._lau_by_name.get(other, []), within):
                prefixes.setdefault(gid[:9], []).append(other)
        if len(prefixes) != 1:
            return None
        return next(iter(prefixes.items()))

    def _with_qualified_homonyms(
        self, key: str, cands: list[tuple[str, BaseGeometry]],
    ) -> list[tuple[str, BaseGeometry]]:
        """A bare name that GISCO also carries with a qualifier is a homonym,
        not a unique match: "Μαρκοπούλου" alone is a village on Kefalonia,
        while the retsina's town is Δ.Κ. Μαρκοπούλου Μεσογαίας in Attica.
        Every such entry is returned, so the same-δήμος rule, a NUTS
        qualifier or the guard decides."""
        out = list(cands)
        seen = {c[0] for c in out}
        for other in self._lau_keys_by_head.get(key.split(" ", 1)[0], ()):
            if other != key and other.startswith(key + " "):
                for pair in self._lau_by_name.get(other, []):
                    if pair[0] not in seen:
                        out.append(pair)
                        seen.add(pair[0])
        return out

    def _unit_prefix(
        self, name: str, within: BaseGeometry | None, pins: dict[str, str],
        tier: str, year: int,
    ) -> list[str] | None:
        """The GISCO prefix a δήμος / δημοτική ενότητα / κοινότητα named as
        a member stands for: a pin; else the community of that name — the
        municipal unit that carries it (9 characters — the pre-2011
        municipality of that name; Kapodistrias merged a town with its
        villages under the town's name), or the whole Kallikratis
        municipality (7) for a δήμος in a text from 2011 on whose community
        is the municipality's seat (ELSTAT numbers the seat unit and
        community 01); else the unit whose seat's name ends in it (Δήμος
        Αιδηψού, seat Λουτρά Αιδηψού)."""
        from .commune import _normalise_commune
        key = _normalise_commune(name)
        pin = [t for t in _pin_targets(pins.get(key)) if t in self._lau_by_prefix]
        if pin:
            return pin
        cands, _kind, _homonym = self._lau_candidates(name, within)
        cands = cands or []
        if len(cands) == 1:
            gid = cands[0][0]
            if tier == "community":
                return [gid]
            if tier == "dimos" and year >= 2011 and gid.endswith("0101"):
                return [gid[:7]]
            return [gid[:9]]
        if not cands and (seat := self._dimos_unit_by_seat_tail(name, within)):
            return [seat[0]]
        return None

    def units_union(
        self, units: dict, within: BaseGeometry | None = None,
        pins: dict[str, str] | None = None, frame: Iterable[str] = (),
        landmark_points: dict[str, tuple[float, float] | None] | None = None,
    ) -> tuple[BaseGeometry | None, dict]:
        """The area a text delimits by named units — see
        `commune.parse_area_units`. Communities resolve as in
        `commune_union`; a δήμος or δημοτική ενότητα named as a member
        expands to its unit (`_unit_prefix`); a locality below the
        community tier ("την περιοχή Ριτσώνα του Δήμου Αυλίδας") that no
        community carries is drawn as its container, the finest polygon
        that holds it, and reported as a proxy. A whole-unit text is left
        to the NUTS step, and the union is used only when at least as many
        items resolved as failed — a text that is mostly prose would
        otherwise be drawn as the few names that happened to match."""
        pins = pins or {}
        polys: list[BaseGeometry] = []
        ids: list[str] = []
        expanded: list[str] = []
        unmatched_units: list[str] = []
        proxied: list[str] = []
        year = units.get("decree_year") or 0

        from .commune import _normalise_commune, eparchy_pins

        def take(prefixes: list[str], label: str) -> None:
            n = 0
            for prefix in prefixes:
                members = self._lau_by_prefix.get(prefix) or []
                polys.extend(members)
                ids.extend(self._lau_ids_by_prefix.get(prefix) or [])
                n += len(members)
            expanded.append(f"{label} → {'+'.join(prefixes)} [{n}]")

        # a former επαρχία is the area even inside a text that also names the
        # prefecture it lies in ("του Νομού Ευβοίας στην πρώην επαρχία
        # Χαλκίδας") — a tier GISCO never carried, so only a pin resolves it
        eparchy_table = eparchy_pins()
        for name in units.get("eparchies") or []:
            record_key = _normalise_commune(f"επαρχία {name}")
            if record_key in pins:
                # a record pin outranks the shared table; an empty one says
                # the text is a source defect (Ρετσίνα Κορωπίου pastes
                # Καρύστου's delimitation) and the eparchy is not drawn
                prefixes = [t for t in _pin_targets(pins[record_key]) if t in self._lau_by_prefix]
                if not prefixes:
                    unmatched_units.append(f"επαρχία {name} (source defect)")
                    continue
            else:
                prefixes = [t for t in eparchy_table.get(_normalise_commune(name), []) if t in self._lau_by_prefix]
            if prefixes:
                take(prefixes, f"επαρχία {name}")
            else:
                unmatched_units.append(f"επαρχία {name}")
        if units.get("whole_unit") and not expanded:
            return None, {"skipped": "whole-unit"}

        for tier, names in (("dimos", units.get("dimoi") or []), ("unit", units.get("units") or [])):
            for name in names:
                prefixes = self._unit_prefix(name, within, pins, tier, year)
                if prefixes is None:
                    unmatched_units.append(name)
                else:
                    take(prefixes, name)
        # a container carries a curator pin only where the pin file says the
        # unit is drawn whole ("Δήμου Ληλαντίου (Δ.Δ. …)": the sidecar's own
        # section names the whole former δήμος)
        for name in units.get("containers") or []:
            pin = [t for t in _pin_targets(pins.get(_normalise_commune(name))) if t in self._lau_by_prefix]
            if pin:
                take(pin, name)
        established = {i[:7] for i in ids}
        # the units the text names as containers bound a typo-tolerant match
        # for a listed community none of the exact keys carry
        container_prefixes: list[str] = []
        for name in units.get("containers") or []:
            for prefix in self._unit_prefix(name, within, pins, "unit", year) or []:
                if len(prefix) >= 9 and prefix not in container_prefixes:
                    container_prefixes.append(prefix)
        # the spec's own NUTS unit named as the frame ("στη διοικητική περιοχή
        # της Λευκάδας και συγκεκριμένα …") is not a list item
        frame_stems = {stem_key(_normalise_commune(f)) for f in frame if f}
        frame_stems |= {stem_key(n) for n in self._named_unit_names}
        communities = [
            c for c in units.get("communities") or []
            if stem_key(_normalise_commune(c)) not in frame_stems
        ]
        geom, stats = self.commune_union(
            communities, within, pins, established, fuzzy_prefixes=container_prefixes,
        )
        if geom is not None:
            polys.append(geom)
            ids.extend(stats.get("gisco_ids") or [])
        matched_communities = set(communities) - set(stats.get("names_unmatched") or [])
        matched_communities -= {a.rsplit(" (", 1)[0] for a in stats.get("names_ambiguous") or []}
        from .commune import _normalise_commune
        for loc in units.get("localities") or []:
            if loc["name"] in matched_communities:
                continue
            pin = [t for t in _pin_targets(pins.get(_normalise_commune(loc["name"]))) if t in self._lau_by_prefix]
            if pin:
                take(pin, loc["name"])
                continue
            prefixes = self._unit_prefix(loc["container"], within, pins, loc["tier"], year)
            if prefixes is None:
                continue
            take(prefixes, f"{loc['name']} (locality of {loc['container']})")
            proxied.append(f"{loc['name']} → {loc['container']} {'+'.join(prefixes)}")
        # "Μοναστήρια Μεταξάτων" drawn as ΔΚ Μεταξάτων: a proxy, not a match
        for entry in stats.get("names_fuzzy") or []:
            if entry.endswith("(tail)"):
                proxied.append(entry[: -len(" (tail)")].replace(" → ", " → ΔΚ "))
        # a boundary traced through named places: the polygon those places
        # outline, each at the point the gazetteer gives it (landmarks.json),
        # in the order the text names them — a place no gazetteer locates is
        # reported and the line runs straight between its neighbours. With
        # too few points located, the units the located places lie in are
        # drawn instead (the earlier, coarser reading).
        landmarks_drawn: list[str] = []
        landmarks_unmatched: list[str] = []
        landmarks_polygon: list[str] = []
        landmarks = list(units.get("landmarks") or [])
        points = landmark_points or {}
        located = [(name, points[name]) for name in landmarks if points.get(name)]
        if len(located) >= 4 and len(located) * 2 >= len(landmarks):
            from shapely.geometry import Polygon
            ring = Polygon([xy for _name, xy in located]).buffer(0)
            if within is not None:
                ring = ring.intersection(within)
            if not ring.is_empty:
                polys.append(ring)
                landmarks_polygon = [name for name, _xy in located]
                landmarks_unmatched = [n for n in landmarks if n not in points or not points[n]]
        if not landmarks_polygon:
            for name in landmarks:
                cands, _kind, _homonym = self._lau_candidates(name, within)
                cands = cands or []
                if len(cands) != 1 or (within is None and not self._named_units):
                    landmarks_unmatched.append(name)
                    continue
                polys.append(cands[0][1])
                ids.append(cands[0][0])
                landmarks_drawn.append(f"{name} → {cands[0][0]}")
        n_ok = stats.get("matched", 0) + len(expanded) + len(landmarks_drawn) + len(landmarks_polygon)
        n_bad = (stats.get("unmatched", 0) + len(stats.get("names_ambiguous") or [])
                 + len(unmatched_units) + len(landmarks_unmatched))
        stats = {**stats, "dimoi_expanded": expanded, "dimoi_unmatched": unmatched_units,
                 "proxied": proxied, "landmarks_drawn": landmarks_drawn,
                 "landmarks_polygon": landmarks_polygon,
                 "landmarks_unmatched": landmarks_unmatched,
                 "gisco_ids": list(dict.fromkeys(ids)),
                 "decree_year": units.get("decree_year")}
        if n_ok == 0 or n_bad > n_ok:
            return None, {**stats, "skipped": f"guard {n_ok} ok / {n_bad} failed"}
        return unary_union(polys), stats

    def nuts_ids_covering(self, geom: BaseGeometry | None, min_share: float = 0.2) -> list[str]:
        """The NUTS-3 units a polygon lies in — those covering at least
        `min_share` of its area, largest share first. The region facet of a
        record drawn from LAU units (which carries no NUTS id of its own)
        is read from them."""
        if geom is None or geom.is_empty:
            return []
        area = geom.area
        shares = []
        for nid, poly in self._nuts_by_id.items():
            if len(nid) != 5 or not poly.intersects(geom):
                continue
            share = poly.intersection(geom).area / area
            if share >= min_share:
                shares.append((share, nid))
        return [nid for _share, nid in sorted(shares, reverse=True)]

    def prefix_union(self, prefixes: list[str]) -> BaseGeometry | None:
        polys = [p for pre in prefixes for p in (self._lau_by_prefix.get(pre) or [])]
        return unary_union(polys) if polys else None

    def nuts_region(self, record: dict) -> tuple[BaseGeometry | None, dict]:
        """Resolve a GR PGI to its GISCO NUTS region(s). Order: curated
        slug override → the spec's cited NUTS name → appellation name →
        region facet. Returns (geometry, stats)."""
        from .nuts import greek_norm, override_ids, spec_nuts_name
        slug = record.get("slug", "")
        ids = override_ids(slug)
        how = "nuts-override"
        if not ids:
            # Deliberately NOT the `region` facet: it is a soft label
            # that falls back to a text scan, so a passing mention of a
            # region in the terroir narrative would become a polygon.
            # ΠΓΕ Άγιο Όρος was drawn as the whole of Στερεά Ελλάδα
            # (42,000 km², ~93 km south of the peninsula) because its
            # lien compares Athos with "…η Αττική".
            candidates = [
                spec_nuts_name(record.get("geo_area_brief") or ""),
                record.get("name") or "",
            ]
            for cand in candidates:
                nid = self._nuts_name_to_id.get(greek_norm(cand).strip())
                if nid:
                    ids = [nid]
                    how = "nuts-name"
                    break
        if not ids:
            return None, {"matched": 0, "unmatched": 0}
        polys = [self._nuts_by_id[i] for i in ids if i in self._nuts_by_id]
        if not polys:
            return None, {"matched": 0, "unmatched": len(ids), "nuts_ids": ids}
        return unary_union(polys), {
            "matched": len(polys), "unmatched": 0, "nuts_ids": ids, "how": how,
        }

    def resolve(
        self, file_number: str, commune_names: Iterable[str] | None = None,
        record: dict | None = None, area_text: str = "",
    ) -> tuple[BaseGeometry | None, str, dict]:
        """Resolve geometry for one GR record. Returns (geometry,
        geom_source, stats). Bétard PDO match first; then the units the
        area text names (communities, δήμοι — `units_union`, guarded);
        then a curated GISCO-prefix pin; then a curated NUTS pin, the NUTS
        unit the spec cites, the appellation name; else a stub.

        Until 2026-09-24 a curated NUTS pin outranked the text, because the
        parser then took prose words for names and drew Τύρναβος across
        Crete. The units step now skips a whole-unit text and any parse
        where fewer items resolved than failed, so a pin is the fallback,
        not the answer: Τύρναβος and Πλαγιές Παϊκού enumerate their
        communities and are drawn from them."""
        fn = file_number or ""
        if fn in self._pdo_polygons:
            return (
                self._pdo_polygons[fn], "figshare-pdo",
                {"matched": -1, "unmatched": 0},
            )
        from .commune import landmark_points, parse_area_units, record_pins  # late import
        from .nuts import greek_norm, override_ids, prefix_ids, spec_nuts_name
        slug = record.get("slug", "") if record is not None else ""
        # The NUTS unit the spec cites ("a. Περιοχή NUTS GR242 Εύβοια")
        # settles homonyms among the names it lists (see `commune_union`).
        within = None
        spec_nid = self._nuts_name_to_id.get(greek_norm(spec_nuts_name(area_text)).strip())
        if spec_nid:
            within = self._nuts_by_id.get(spec_nid)
        elif override_ids(slug):
            # no NUTS line: the curator-verified NUTS pin bounds the names
            # the text does list (Πλαγιές Πεντελικού's Δροσιά is Attica's)
            polys = [self._nuts_by_id[i] for i in override_ids(slug) if i in self._nuts_by_id]
            within = unary_union(polys) if polys else None
        self._named_units = self.named_nuts_units(area_text) if area_text else []
        pins = record_pins(slug)
        if area_text:
            units = parse_area_units(area_text)
            geom, stats = self.units_union(
                units, within, pins, frame=[spec_nuts_name(area_text)],
                landmark_points=landmark_points(slug),
            )
            if geom is not None:
                return geom, "gisco-commune-list", {
                    **stats, "how": "area-units", "spec_nuts": spec_nid,
                }
        elif commune_names:
            geom, stats = self.commune_union(commune_names, within, pins)
            if geom is not None:
                return geom, "gisco-commune-list", stats
        pins = prefix_ids(slug)
        if pins and self._lau_by_prefix:
            geom = self.prefix_union(pins)
            if geom is not None:
                return geom, "gisco-commune-list", {
                    "matched": sum(len(self._lau_by_prefix.get(p) or []) for p in pins),
                    "gisco_ids": [i for p in pins for i in (self._lau_ids_by_prefix.get(p) or [])],
                    "unmatched": 0, "how": "prefix-pin", "gisco_prefixes": pins,
                }
        if record is not None and self._nuts_by_id and override_ids(slug):
            geom, stats = self.nuts_region(record)
            if geom is not None:
                return geom, "gisco-nuts-region", stats
        if record is not None and self._nuts_by_id:
            geom, stats = self.nuts_region(record)
            if geom is not None:
                return geom, "gisco-nuts-region", stats
        return None, "stub-no-geometry", {"matched": 0, "unmatched": 0}

    def union_all(self, file_numbers: Iterable[str]) -> BaseGeometry | None:
        polys = [
            self._pdo_polygons[fn]
            for fn in file_numbers
            if fn in self._pdo_polygons
        ]
        return unary_union(polys) if polys else None
