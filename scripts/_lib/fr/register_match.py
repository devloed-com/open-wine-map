"""Resolve a French SIQO appellation to its eAmbrosia register file number.

France is the one country in the corpus sourced from INAO rather than from
eAmbrosia, so its records carry no `id_eambrosia` join key. The register is
still the cheapest self-service source for a cahier des charges PDF
(`productSpecifications[0].uri` — the INAO cahier itself, not the thinner EU
single document), which makes a name-based resolver the missing link.

The resolver is deliberately conservative: a wrong bind attaches another
appellation's cahier, which is worse than a gap. Four guards:

* **Product-type partition.** The candidate pool is split by the register's
  `qualityProductType`, keyed off the SIQO `categorie`. "Calvados" is both a
  Wine PGI (the Normandy IGP wine) and a Spirit-drink PGI (the eau-de-vie);
  without the partition either could claim the other's cahier. A SIQO row with
  no categorie at all searches every partition and must come back with one GI;
  a categorie the table does not know goes to the curator rather than widening
  the pool.
* **No fuzzy matching.** Match keys are the exact normalised alias parts of
  the SIQO name (`_lib.fr.naming.candidate_keys`) against the register name
  split on its own `/` synonym separator. A key that hits more than one
  register GI resolves to nothing.
* **One-to-one.** Two appellations claiming the same file number is a symptom
  of a bad key, so the auto-matched claimants go back to the queue (a curator
  pin wins, since pinning is the deliberate answer to exactly that question).
* **Live registrations only.** A GI the Commission has struck off cannot be an
  appellation's current specification, so a `Cancelled` row is refused rather
  than bound.

Everything the resolver could not settle lands in an unresolved queue, and a
curator pins the residue in `register_overrides.json`.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from .naming import candidate_keys, normalize_name

OVERRIDES_PATH = Path(__file__).resolve().parent / "register_overrides.json"

# SIQO `categorie` → the register's `qualityProductType`. The SIQO VITICOLE
# sector bundles wine with vine/fruit spirits and cider, which the register
# files under three different product types.
CATEGORIE_PRODUCT_TYPE: dict[str, str] = {
    "Vin tranquille": "Wine",
    "Vin de triees successives": "Wine",
    "Vin de sélection de grains nobles": "Wine",
    "Vin doux naturel": "Wine",
    "Vin de liqueur": "Wine",
    "Vin mousseux": "Wine",
    'Vin mousseux "Crémant"': "Wine",
    "Vin primeur": "Wine",
    "Vin jaune": "Wine",
    "Vin de paille": "Wine",
    "Vin de raisins surmuris": "Wine",
    "Vin de vendanges tardives": "Wine",
    "Vin sur lie": "Wine",
    "Vin pétillant": "Wine",
    'Vin mousseux "Méthode ancestrale"': "Wine",
    "Eaux-de-vie de vin": "Spirit drink",
    "Eaux-de-vie de marc de raisin": "Spirit drink",
    "Eaux-de-vie de fruits": "Spirit drink",
    "Eaux-de-vie de cidre et de poiré": "Spirit drink",
    "Autres boissons spiritueuses": "Spirit drink",
    "Whisky ou Whiskey": "Spirit drink",
    "Rhum": "Spirit drink",
    "Cidre": "Food",
    "Poiré": "Food",
}

# A GI the Commission has struck off cannot be an appellation's current
# specification, so binding to one is a curator decision, not an automatic
# match. Pending registrations (Applied / Published) are fine — the
# attachment is the submitted cahier.
BINDABLE_STATUSES = ("Registered", "Published", "Applied")

# The register writes synonym lists with a slash — "Bourg / Côtes de Bourg /
# Bourgeais", "Alsace / Vin d'Alsace" — where SIQO writes " ou ". The slash is
# its ONLY separator: splitting a register name the way a SIQO name is split
# would manufacture keys out of ordinary words, and out of the parenthetical
# region lists some GIs carry ("… du Sud-Ouest (Chalosse, Gascogne, Gers,
# Landes, Périgord, Quercy)" would otherwise offer `gascogne` and `quercy` as
# bindable keys). The parenthetical is dropped for the same reason.
_REGISTER_SPLIT_RE = re.compile(r"\s*/\s*")
_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)")

# An alias fragment shorter than this is a preposition remnant or a bare
# commune word, too generic to bind an appellation on.
_MIN_ALIAS_KEY_LEN = 4

_STATUS_RANK = {"Registered": 0, "Published": 1, "Applied": 2, "Cancelled": 3}


@dataclass(frozen=True)
class Resolution:
    """One appellation → register GI binding."""

    id_appellation: str
    name: str
    file_number: str
    register_name: str
    product_type: str
    gi_type: str
    status: str
    matched_key: str
    matched_via: str  # "full" | "alias" | "override"
    partition: str  # "categorie" (SIQO-derived) | "any" | "override"


def register_keys(protected_name: str) -> list[str]:
    """Match keys for a register `protectedName`: the whole name, then each
    `/`-separated synonym, parentheticals removed."""
    name = protected_name or ""
    keys: list[str] = []
    full = normalize_name(name)
    if full:
        keys.append(full)
    for chunk in _REGISTER_SPLIT_RE.split(_PARENTHETICAL_RE.sub("", name)):
        key = normalize_name(chunk)
        if key and key not in keys:
            keys.append(key)
    return keys


def product_type_for(categorie: str) -> str | None:
    """Register product type for a SIQO `categorie`; None when unmapped."""
    return CATEGORIE_PRODUCT_TYPE.get((categorie or "").strip())


def fr_rows(rows: list[dict]) -> list[dict]:
    """The French GI rows the register shows, any product type.

    `countryId` is a comma-joined list for cross-border GIs — the Basque
    cider PDO is `es,fr` — so membership, not equality, is the test."""
    return [
        r for r in rows
        if "fr" in (r.get("countryId") or "").split(",")
        and r.get("showInRegister") and r.get("fileName")
    ]


def build_index(rows: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """product_type → match key → register rows."""
    index: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        bucket = index[row.get("qualityProductType") or ""]
        for key in register_keys(row.get("protectedName") or ""):
            bucket[key].append(row)
    return index


def load_overrides(path: Path | None = None) -> dict[str, dict]:
    """Curator pins: id_appellation → {file_number, name?, note?}. An entry
    whose `file_number` is empty is a deliberate "no register GI exists"
    marker and suppresses the appellation from the unresolved queue."""
    p = path or OVERRIDES_PATH
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _pick(candidates: list[dict]) -> list[dict]:
    """Prefer the live registration when a name resolves to several
    lifecycle rows of the same GI (a cancelled predecessor, a pending
    amendment)."""
    best = min(_STATUS_RANK.get(c.get("status") or "", 9) for c in candidates)
    return [c for c in candidates if _STATUS_RANK.get(c.get("status") or "", 9) == best]


def _product_types(candidates: list[dict]) -> set[str]:
    return {c.get("qualityProductType") or "" for c in candidates}


def _lookup(index: dict[str, dict[str, list[dict]]], pools: list[str], key: str) -> list[dict]:
    """Register rows matching `key` across the given product-type pools,
    deduplicated by file number."""
    seen: dict[str, dict] = {}
    for pool in pools:
        for row in index.get(pool, {}).get(key, ()):
            seen.setdefault(row["fileName"], row)
    return list(seen.values())


def _resolution(id_app: str, name: str, row: dict, key: str, via: str, partition: str) -> Resolution:
    return Resolution(
        id_appellation=id_app,
        name=name,
        file_number=row["fileName"],
        register_name=row.get("protectedName") or "",
        product_type=row.get("qualityProductType") or "",
        gi_type=row.get("geographicalIndicatorTypeCode") or "",
        status=row.get("status") or "",
        matched_key=key,
        matched_via=via,
        partition=partition,
    )


def resolve_all(
    appellations: list[dict],
    rows: list[dict],
    overrides: dict[str, dict] | None = None,
) -> tuple[dict[str, Resolution], list[dict]]:
    """Resolve every appellation to a register file number.

    `appellations` are `{id_appellation, name, categorie}` dicts — the parent
    rows of `raw/inao/cahiers/manifest.json`. Returns (resolved, unresolved)
    where unresolved entries carry a `reason` a curator can act on.
    """
    overrides = overrides if overrides is not None else load_overrides()
    by_file_number = {r["fileName"]: r for r in rows}
    index = build_index(rows)

    resolved: dict[str, Resolution] = {}
    unresolved: list[dict] = []

    for app in appellations:
        id_app = str(app["id_appellation"])
        name = app["name"]
        categorie = app.get("categorie") or ""
        pin = overrides.get(id_app)

        if pin is not None:
            file_number = (pin.get("file_number") or "").strip()
            if not file_number:
                continue  # curator-confirmed absent from the register
            row = by_file_number.get(file_number)
            if row is None:
                unresolved.append({
                    "id_appellation": id_app, "name": name, "categorie": categorie,
                    "reason": "override-file-number-not-in-register",
                    "detail": file_number,
                })
                continue
            resolved[id_app] = _resolution(
                id_app, name, row, file_number, "override", "override")
            continue

        # A SIQO row with no `categorie` at all (a handful of AOCs whose
        # canonical product carries none) cannot pick a partition, so it
        # searches all of them; a *populated* categorie the table does not know
        # is a new SIQO value, and widening the pool for it would trade a
        # loud gap for a quiet cross-bind, so it goes to the curator instead.
        product_type = product_type_for(categorie)
        if product_type is None and categorie:
            unresolved.append({
                "id_appellation": id_app, "name": name, "categorie": categorie,
                "reason": "unmapped-categorie",
                "detail": "add it to CATEGORIE_PRODUCT_TYPE in register_match.py",
            })
            continue
        partition = "categorie" if product_type else "any"
        pools = [product_type] if product_type else sorted(index)

        keys = candidate_keys(name)
        hit = None
        for i, key in enumerate(keys):
            if i and len(key) < _MIN_ALIAS_KEY_LEN:
                continue
            candidates = _lookup(index, pools, key)
            if not candidates:
                continue
            # With no partition to lean on, the product type itself has to be
            # unambiguous: status ranking must not be allowed to quietly pick
            # the wine over the eau-de-vie of the same name.
            best = candidates if len(_product_types(candidates)) > 1 else _pick(candidates)
            if len(best) > 1:
                unresolved.append({
                    "id_appellation": id_app, "name": name, "categorie": categorie,
                    "reason": "ambiguous",
                    "detail": f"key {key!r} matches {sorted(c['fileName'] for c in best)}",
                })
                hit = "ambiguous"
                break
            if (best[0].get("status") or "") not in BINDABLE_STATUSES:
                unresolved.append({
                    "id_appellation": id_app, "name": name, "categorie": categorie,
                    "reason": "withdrawn-registration",
                    "detail": f"{best[0]['fileName']} is {best[0].get('status')!r} — "
                              f"pin it in register_overrides.json to bind it anyway",
                })
                hit = "ambiguous"
                break
            hit = _resolution(
                id_app, name, best[0], key, "full" if i == 0 else "alias", partition)
            break

        if hit is None:
            unresolved.append({
                "id_appellation": id_app, "name": name, "categorie": categorie,
                "reason": "no-name-match",
                "detail": f"{'/'.join(pools)} partition, keys tried: {keys}",
            })
        elif hit != "ambiguous":
            resolved[id_app] = hit

    _drop_collisions(resolved, unresolved)
    unresolved.sort(key=lambda u: u["name"].lower())
    return resolved, unresolved


def _drop_collisions(resolved: dict[str, Resolution], unresolved: list[dict]) -> None:
    """Two appellations binding one register GI means at least one bind is
    wrong, so the auto-matched claimants go back to the curator. A curator pin
    is the deliberate answer to exactly this question, so it survives — losing
    it would leave no way to force a binding at all."""
    claims: dict[str, list[str]] = defaultdict(list)
    for id_app, res in resolved.items():
        claims[res.file_number].append(id_app)
    for file_number, ids in claims.items():
        if len(ids) < 2:
            continue
        pinned = [i for i in ids if resolved[i].matched_via == "override"]
        losers = [i for i in ids if i not in pinned] if len(pinned) == 1 else ids
        for id_app in losers:
            res = resolved.pop(id_app)
            unresolved.append({
                "id_appellation": id_app, "name": res.name, "categorie": "",
                "reason": "collision-with-pin" if pinned else "collision",
                "detail": f"{file_number} also claimed by {sorted(set(ids) - {id_app})}",
            })


def to_json(resolved: dict[str, Resolution]) -> dict[str, dict]:
    def _key(kv: tuple[str, Resolution]) -> tuple[int, str]:
        return (int(kv[0]) if kv[0].isdigit() else 1 << 30, kv[0])

    return {k: asdict(v) for k, v in sorted(resolved.items(), key=_key)}
