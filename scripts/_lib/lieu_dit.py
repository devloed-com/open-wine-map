"""Cadastre-derived lieu-dit polygon resolver.

Stage 04 calls this when a DGC has no parcellaire row, no village override,
and is part of a cluster whose siblings share the parent commune polygon —
the canonical case being Chablis premier-cru climats (Vaillons, Beugnons,
Berdiot, …) which sit as named cadastral lieux-dits inside Chablis commune
(INSEE 89068) but have no INAO parcellaire delimitation.

Source: cadastre.data.gouv.fr (Etalab, Licence Ouverte 2.0). Each commune's
`cadastre-<INSEE>-lieux_dits.json.gz` carries the named cadastral parcels
as polygons.

The resolver normalises both sides (strip diacritics, leading articles),
exact-matches first, then accepts substring + Levenshtein fuzz down to a
configurable threshold. Tied-best polygons are unioned (Côte de Bréchain
appears as two cadastre polygons in Chablis; together they delimit the
climat).

Manual override hatch: `cadastre_lieu_dit_overrides.json` (in this dir),
keyed by id_denomination_geo, lets a curator pin a {commune, lieu_dit}
pair when the fuzzy match misses or picks the wrong polygon.
"""

from __future__ import annotations

import gzip
import json
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent.parent
CADASTRE_DIR = ROOT / "raw" / "cadastre" / "lieux-dits"
OVERRIDES_PATH = Path(__file__).resolve().parent / "cadastre_lieu_dit_overrides.json"

DEFAULT_THRESHOLD = 0.85

_LEADING_ARTICLE = re.compile(r"^(?:les|la|le|l)\s+")


def _normalize(name: str) -> str:
    """Loose match key — strip diacritics, articles, punctuation, casefold."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.lower()
    s = s.replace("'", " ").replace("’", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = _LEADING_ARTICLE.sub("", s)
    s = re.sub(r"[\W_]+", "", s)
    return s


def _score(climat: str, lieu_dit: str) -> float:
    """Score a climat/lieu-dit pair on [0, 1].

    1.0 = exact-normalized match (after diacritic + article stripping).
    0.85 = climat-name appears as a substring of the lieu-dit name (so
    the lieu-dit is the climat or a sub-piece of it — e.g. "Buttaux"
    inside "REPLAT DES BUTTAUX"). Tied 0.85 hits get unioned upstream so
    multi-piece climats reassemble.
    0.7 = the reverse direction (lieu-dit is a substring of climat). Less
    informative — covers only a fragment of the climat — but still better
    than the commune-scale fallback.
    Levenshtein ratio for everything else, gated at the configured
    threshold so near-misses (e.g. cadastre "PIED D'ALOUE" vs cahier
    "Pied d'Aloup") still resolve.
    """
    a = _normalize(climat)
    b = _normalize(lieu_dit)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b:
        return 0.85
    if b in a:
        return 0.7
    return SequenceMatcher(None, a, b).ratio()


def _load_overrides() -> dict[str, dict]:
    if not OVERRIDES_PATH.exists():
        return {}
    raw = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _insee_from_filename(path: Path) -> str:
    name = path.name
    if name.endswith(".json.gz"):
        return name[: -len(".json.gz")]
    if name.endswith(".geojson.gz"):
        return name[: -len(".geojson.gz")]
    return path.stem


class LieuDitIndex:
    """Index of cadastral lieu-dit polygons by commune INSEE."""

    def __init__(self, dir: Path = CADASTRE_DIR) -> None:
        self._by_commune: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        self.overrides = _load_overrides()
        if not dir.exists():
            return
        for path in sorted(dir.glob("*.json.gz")):
            insee = _insee_from_filename(path)
            with gzip.open(path, "rt", encoding="utf-8") as f:
                fc = json.load(f)
            for feat in fc.get("features", []):
                nom = (feat.get("properties") or {}).get("nom") or ""
                if not nom or "geometry" not in feat:
                    continue
                self._by_commune[insee].append((nom, feat["geometry"]))

    @property
    def communes(self) -> set[str]:
        return set(self._by_commune.keys())

    @property
    def total_lieux_dits(self) -> int:
        return sum(len(v) for v in self._by_commune.values())

    def resolve(
        self,
        climat_name: str,
        candidate_insees: set[str] | frozenset[str] | None,
        threshold: float = DEFAULT_THRESHOLD,
        id_denom: str | None = None,
    ) -> dict | None:
        """Resolve a climat name to a polygon by best-scoring lieu-dit match.

        Returns `{geom, score, lieu_dit, commune}` (str names — multiple
        polygons are joined with "; " for attribution), or None if no
        candidate scored at or above `threshold`.

        `candidate_insees` should be the parent appellation's commune
        set; the climat must geometrically live inside it. None or empty
        falls back to all loaded communes (slower, less precise).
        """
        if id_denom and id_denom in self.overrides:
            ov = self.overrides[id_denom]
            return self._resolve_override(ov, id_denom)

        insees = candidate_insees or self.communes
        best_score = 0.0
        winners: list[tuple[float, str, str, dict]] = []
        for insee in insees:
            for nom, geom in self._by_commune.get(insee, []):
                s = _score(climat_name, nom)
                if s < threshold:
                    continue
                if s > best_score + 1e-9:
                    best_score = s
                    winners = [(s, nom, insee, geom)]
                elif abs(s - best_score) < 1e-9:
                    winners.append((s, nom, insee, geom))
        if not winners:
            return None
        polys = [shape(w[3]) for w in winners]
        merged = polys[0] if len(polys) == 1 else unary_union(polys)
        names = sorted({w[1] for w in winners})
        communes = sorted({w[2] for w in winners})
        return {
            "geom": merged,
            "score": best_score,
            "lieu_dit": "; ".join(names),
            "commune": "; ".join(communes),
        }

    def _resolve_override(self, ov: dict, id_denom: str) -> dict | None:
        commune = str(ov.get("commune_insee") or "").strip()
        targets = ov.get("lieu_dit_names") or [ov.get("lieu_dit_name")]
        targets = [t for t in (targets or []) if t]
        if not commune or not targets:
            return None
        wanted = {_normalize(t) for t in targets}
        polys: list[object] = []
        matched: list[str] = []
        for nom, geom in self._by_commune.get(commune, []):
            if _normalize(nom) in wanted:
                polys.append(shape(geom))
                matched.append(nom)
        if not polys:
            return None
        merged = polys[0] if len(polys) == 1 else unary_union(polys)
        return {
            "geom": merged,
            "score": 1.0,
            "lieu_dit": "; ".join(sorted(set(matched))),
            "commune": commune,
            "override": True,
        }


def derive_climat_name(name: str, parent_name: str = "", umbrella_name: str = "") -> str:
    """Strip the parent/umbrella prefix to recover the bare climat name.

    "Chablis premier cru Vaillons" with umbrella "Chablis premier cru"
    → "Vaillons". Falls back to stripping just the parent name when no
    umbrella matches.
    """
    for prefix in (umbrella_name, parent_name):
        if not prefix:
            continue
        p = prefix.rstrip()
        if name.startswith(p + " "):
            return name[len(p) + 1 :].strip()
    return name.strip()
