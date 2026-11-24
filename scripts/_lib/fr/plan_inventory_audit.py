"""The cross-check of the French corpus against INAO's delimitation-plan
inventory and its scanned plans — the pure part (no file, no network), so the
tests run it on canned rows. `scripts/audit_plan_inventory.py` loads the data.

Four sources speak about one (appellation, commune) pair, and none is the
truth:

- **the inventory** (`inventaire_etat_de_la_delimitation.xlsx`): a parcel
  delimitation expected (oui / non / «identification parcellaire»), the plan's
  state (disponible / en cours d'élaboration / aucune parcelle classée), a
  revision under way. It can be incomplete or outdated (Cassis reads non
  although its cahier sets an approved parcel area);
- **INAO's aires-communes rows**, with the cited supplements: the aire
  géographique, a decade older than the cahier at times;
- **the cahier** as stage 02 read its commune list — it wins wherever it is
  explicit (2026-11-13), but the list reader can miss names;
- **INAO's parcellaire shapefile** (the coverage index): what a parcellaire
  record is drawn from.

A record's data is called wrong (`CONFLICT_OURS`) only when two of those agree
against what we draw or say, or when the cahier does; the inventory alone
against us and another source is `CONFLICT_INVENTORY`; a disagreement nothing
settles is `UNDETERMINED`; INAO's inventory against INAO's own plan folders is
`INTERNAL` — the plans never decide anything about our data; a revision under
way or a plan older than the text is `REVISION`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable

CONFLICT_OURS = "CONFLICT-OURS"
CONFLICT_INVENTORY = "CONFLICT-INVENTORY"
UNDETERMINED = "UNDETERMINED"
INTERNAL = "INTERNAL"
REVISION = "REVISION"
BUCKETS = (CONFLICT_OURS, CONFLICT_INVENTORY, UNDETERMINED, INTERNAL, REVISION)

PARCEL_SOURCES = frozenset({"parcellaire", "parcellaire-dgc"})
UNION_SOURCES = frozenset({"aires-csv", "aires-csv-dgc", "dgc-village-override", "communes"})
INHERITED_SOURCES = frozenset({"parent-appellation", "sibling-dgc"})

# A commune union whose inventory parcel communes are at most this share of
# the communes drawn: a Champagne-style candidate (Champagne: 321 of 617)
SMALL_SHARE = 0.6
# A plan sheet this many years older than the cahier in force
PLAN_AGE_YEARS = 10

ATTENDU_OUI = "oui"
ATTENDU_NON = "non"
ATTENDU_IDENT = "identification"
PLAN_DISPO = "disponible"
PLAN_EN_COURS = "en cours"
PLAN_AUCUNE = "aucune"


def norm(s: str) -> str:
    """Letters and digits, lower case, no accents — the aires key."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalnum())


def _alias_parts(name: str) -> set[str]:
    return {norm(p) for p in re.split(r"\s+ou\s+", name or "")} - {""}


def attendu_of(value: str | None) -> str:
    v = (value or "").strip().lower()
    if v == "oui":
        return ATTENDU_OUI
    if v.startswith("identification"):
        return ATTENDU_IDENT
    return ATTENDU_NON


def plan_of(value: str | None) -> str:
    v = (value or "").strip().lower()
    if v.startswith("plan disponible"):
        return PLAN_DISPO
    if "laboration" in v:
        return PLAN_EN_COURS
    return PLAN_AUCUNE


# ---------------------------------------------------------------- inventory
@dataclass
class CommuneStatus:
    """One commune of today in one inventory appellation, all its rows folded
    (the inventory writes a commune nouvelle once per former commune)."""
    code: str
    name: str
    raw: set[str] = field(default_factory=set)
    attendu: set[str] = field(default_factory=set)
    plans: set[str] = field(default_factory=set)
    revision: bool = False

    @property
    def oui(self) -> bool:
        return ATTENDU_OUI in self.attendu

    @property
    def ident(self) -> bool:
        return ATTENDU_IDENT in self.attendu

    @property
    def plan(self) -> str:
        """The strongest plan state of the commune's oui rows (else of all)."""
        for p in (PLAN_DISPO, PLAN_EN_COURS):
            if p in self.plans:
                return p
        return PLAN_AUCUNE


@dataclass
class InventoryApp:
    name: str
    signe: str
    communes: dict[str, CommuneStatus] = field(default_factory=dict)

    def codes(self, pred: Callable[[CommuneStatus], bool] | None = None) -> set[str]:
        return {c for c, s in self.communes.items() if pred is None or pred(s)}

    @property
    def raw_codes(self) -> set[str]:
        return set().union(*(s.raw for s in self.communes.values())) if self.communes else set()


def sign_of(value: str | None) -> str:
    """AOC or IGP: the inventory's two signs (an AOP is an AOC there)."""
    v = (value or "").strip().upper()
    return "IGP" if v.startswith("IGP") else "AOC"


def group_inventory(rows: Iterable[dict], canon: Callable[[str], str]) -> dict[tuple[str, str], InventoryApp]:
    """Inventory rows → {(sign, appellation as written, lower case):
    InventoryApp}, each code folded into its commune of today by `canon`. The
    sign is part of the key: «calvados» is both the AOC spirit and the IGP
    wine."""
    out: dict[tuple[str, str], InventoryApp] = {}
    for r in rows:
        app = (r.get("appellation") or "").strip().lower()
        code = (r.get("insee") or "").strip()
        if not app or not code:
            continue
        sign = sign_of(r.get("signe"))
        entry = out.setdefault((sign, app), InventoryApp(name=app, signe=sign))
        today = canon(code)
        st = entry.communes.setdefault(today, CommuneStatus(code=today, name=r.get("commune") or ""))
        st.raw.add(code)
        attendu = attendu_of(r.get("attendu"))
        st.attendu.add(attendu)
        if attendu == ATTENDU_OUI:
            st.plans.add(plan_of(r.get("plan")))
        if (r.get("revision") or "").strip().lower() == "oui":
            st.revision = True
    return out


# ----------------------------------------------------------------- matching
@dataclass
class Match:
    by_slug: dict[str, tuple[tuple[str, str], str]]   # slug → ((sign, inventory name), via)
    unmatched_records: list[dict]                       # {slug, name, reason}
    unmatched_inventory: list[tuple[str, str]]


def record_sign(rec: dict) -> str:
    """The inventory sign of a record: its SIQO `signe_fr` when it has one (a
    French cider AOC is stored with `kind` IGP, the paint key), else IGP for an
    IGP and AOC for the rest."""
    signe = (rec.get("signe_fr") or "").strip().upper()
    if signe in ("AOC", "IGP"):
        return signe
    return "IGP" if (rec.get("kind") or "").upper() == "IGP" else "AOC"


def match_records(records: list[dict], inv_keys: Iterable[tuple[str, str]],
                  pins: dict[str, dict] | None = None, near: Callable | None = None) -> Match:
    """Bind each record to one inventory appellation of its own sign: a cited
    pin, the exact normalised name, one " ou " alias of the record, one " ou "
    alias of the inventory name, or `near` (a near-exact spelling, one
    candidate). Two records claiming one inventory appellation: the one with
    the exact name keeps it, the other is unbound."""
    keys = list(inv_keys)
    by_key = {(sign, norm(n)): (sign, n) for sign, n in keys}
    by_alias: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for sign, n in keys:
        for p in _alias_parts(n):
            by_alias.setdefault((sign, p), set()).add((sign, n))
    names_of_sign: dict[str, dict[str, tuple[str, str]]] = {}
    for (sign, k), v in by_key.items():
        names_of_sign.setdefault(sign, {})[k] = v
    claims: dict[tuple[str, str], list[tuple[str, str]]] = {}
    unmatched: list[dict] = []
    for rec in records:
        slug, name = rec["slug"], rec.get("name") or ""
        sign = record_sign(rec)
        pin = (pins or {}).get(slug)
        if pin:
            target = (pin.get("sign") or sign, pin.get("inventory"))
            if target in set(keys):
                claims.setdefault(target, []).append((slug, "pin"))
            else:
                unmatched.append({"slug": slug, "name": name, "reason": pin.get("reason") or "pinned absent"})
            continue
        key = norm(name)
        hit, via = by_key.get((sign, key)), "exact"
        if hit is None:
            parts = {by_key[(sign, p)] for p in _alias_parts(name) if (sign, p) in by_key}
            if len(parts) == 1:
                hit, via = parts.pop(), "record-alias"
        if hit is None and len(by_alias.get((sign, key), ())) == 1:
            hit, via = next(iter(by_alias[(sign, key)])), "inventory-alias"
        if hit is None and near is not None:
            cand = near(key, names_of_sign.get(sign, {}))
            if cand:
                hit, via = names_of_sign[sign][cand], "near-exact"
        if hit is None:
            other = "AOC" if sign == "IGP" else "IGP"
            reason = (f"no {sign} of this name in the inventory (an {other} of this name is)"
                      if (other, key) in by_key else "no inventory appellation of this name")
            unmatched.append({"slug": slug, "name": name, "reason": reason})
            continue
        claims.setdefault(hit, []).append((slug, via))
    by_slug: dict[str, tuple[tuple[str, str], str]] = {}
    for inv, who in claims.items():
        exact = [w for w in who if w[1] in ("exact", "pin")]
        keep = exact[0] if len(exact) == 1 else (who[0] if len(who) == 1 else None)
        for slug, via in who:
            if keep == (slug, via):
                by_slug[slug] = (inv, via)
            else:
                unmatched.append({"slug": slug, "name": "",
                                  "reason": f"«{inv[1]}» ({inv[0]}) is bound to "
                                            + (keep[0] if keep else f"none of {len(who)} records") })
    used = {v[0] for v in by_slug.values()}
    return Match(by_slug=by_slug, unmatched_records=unmatched,
                 unmatched_inventory=sorted(k for k in keys if k not in used))


# ----------------------------------------------------------------- findings
@dataclass
class Finding:
    check: str
    bucket: str
    slug: str
    name: str
    kind: str
    summary: str
    communes: list[dict] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    route: str = ""

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class RecordContext:
    """Everything the checks know about one record, its codes folded into
    communes of today."""
    slug: str
    name: str
    is_dgc: bool
    geom_source: str
    inv: InventoryApp | None
    aire: set[str]                 # INAO's rows (+ supplements) — parent's for a DGC without its own
    aire_own: bool                 # the rows are the record's own
    cahier: set[str]               # the cahier's commune list, as stage 02 read it
    coverage: set[str]             # the parcellaire shapefile's communes for the record
    coverage_any: set[str] = field(default_factory=set)   # communes with any parcel row
    coverage_old: set[str] = field(default_factory=set)   # … in an earlier release
    drawn: set[str] = field(default_factory=set)          # the communes a union draws
    gap_fills: set[str] = field(default_factory=set)      # pinned in parcellaire_gap_fills.json
    folders: dict[str, str] | None = None                 # the record's plan folder: code → name
    folder: str = ""
    card_parcel_area: str = ""     # the card's geom_parcel_area ("" = the old line)
    own_parcel_area: bool = False  # parcel_area.sets_own_parcel_area on the cahier
    parcel_area_table: str = ""    # its parcel_area_communes.json source
    homologated_at: str = ""
    plan_dates: tuple[str, str] = ("", "")
    names: dict[str, str] = field(default_factory=dict)
    kind: str = ""                 # AOC / IGP / EDV
    gap_audit_aire: set[str] = field(default_factory=set)  # the aire audit_parcellaire_gaps.py reads
    # a sub-denomination shares its parent's cahier: a name in it says nothing
    # about the DGC itself, only that the commune is in the parent's area
    cahier_own: bool = True
    # codes whose name the zone text carries though the commune list stage 02
    # read did not («Ponteilla en partie (sections A1, A2 …)»)
    cahier_text: set[str] = field(default_factory=set)
    # … and the ones it names in part, under another heading or in an
    # exclusion (audit_aires_vs_cahier.classify): code → the quote
    cahier_partial: dict[str, str] = field(default_factory=dict)
    # code → (first, last, sheets) of the sheets in the commune's own plan
    # folder, for the communes a check disputes (listed on demand)
    commune_plans: dict[str, tuple[str, str, int]] = field(default_factory=dict)
    # communes a curator decided in aires_supplements.json (`not_drawn`,
    # `remove`): never a finding again
    aire_decided: set[str] = field(default_factory=set)
    # INAO's aires CSV carries the record's name under several IDAs — another
    # product of the same name (Valençay the wine and the cheese, both AOC):
    # the inventory's list for the name may mix them
    name_shared: int = 0

    @property
    def own_cahier(self) -> set[str]:
        """The communes the record's own text names whole: the list stage 02
        read keeps «Le Bignon (partie)» as Le Bignon, so a name the text
        qualifies is taken out."""
        if not self.cahier_own:
            return set()
        return (self.cahier | self.cahier_text) - set(self.cahier_partial)

    @property
    def any_cahier(self) -> set[str]:
        """The communes the record's text names, its parent's for a DGC: in
        the parent's area at least."""
        return self.cahier | self.cahier_text | set(self.cahier_partial)

    def plan_newer_than_cahier(self, code: str) -> bool:
        last = (self.commune_plans.get(code) or ("", "", 0))[1]
        return bool(last and self.homologated_at and last > self.homologated_at)


def _row(ctx: RecordContext, code: str, **extra) -> dict:
    st = ctx.inv.communes.get(code) if ctx.inv else None
    return {
        "insee": code, "name": ctx.names.get(code) or (st.name if st else code),
        **({"inventory": sorted(st.attendu), "plan": st.plan} if st else {"inventory": None}),
        "in_aire": code in ctx.aire,
        **({"folder": code in ctx.folders} if ctx.folders is not None else {}),
        **({"plan": {"first": ctx.commune_plans[code][0], "last": ctx.commune_plans[code][1],
                     "sheets": ctx.commune_plans[code][2]}} if code in ctx.commune_plans else {}),
        **extra,
    }


def check_parcellaire(ctx: RecordContext) -> list[Finding]:
    """Check 1: a record drawn from INAO's parcels against the inventory."""
    if ctx.geom_source not in PARCEL_SOURCES or ctx.inv is None:
        return []
    out: list[Finding] = []
    inv = ctx.inv
    oui_dispo = inv.codes(lambda s: s.oui and s.plan == PLAN_DISPO)
    oui_cours = inv.codes(lambda s: s.oui and s.plan == PLAN_EN_COURS)
    missing = sorted((oui_dispo | oui_cours) - ctx.coverage - ctx.gap_fills)
    if missing:
        # the inventory's oui is not specific to the appellation: 20 Jurançon
        # communes read «oui, plan disponible» under every product covering
        # them, Ossau-Iraty and Jambon de Bayonne included (2026-11-23). The
        # appellation's own plan, with sheets, is what makes it its parcels.
        candidates = [c for c in missing if c in oui_dispo and c in ctx.aire]
        sheets = {c: (ctx.commune_plans.get(c) or ("", "", 0))[2] for c in candidates}
        confirmed = [c for c in candidates if sheets[c] > 0]
        unconfirmed = [c for c in candidates if sheets[c] == 0]
        outside = [c for c in missing if c not in ctx.aire]
        in_progress = [c for c in missing if c in oui_cours and c not in oui_dispo and c in ctx.aire]
        cls = {c: ("other-aoc" if c in ctx.coverage_any else "not-digitised") for c in missing}
        if confirmed:
            out.append(Finding(
                "1a", CONFLICT_OURS, ctx.slug, ctx.name, "parcels-missing",
                f"{len(confirmed)} commune(s) the inventory marks «oui, plan disponible», INAO's rows put "
                "in the aire and the appellation's plan folder holds sheets for, with no parcel of the "
                "record in the shapefile we draw",
                [_row(ctx, c, coverage=cls[c], listed_by_gap_audit=c in ctx.gap_audit_aire)
                 for c in confirmed],
                route="gap fill (parcellaire_gap_fills.json) once the plan is read; else a question for INAO",
            ))
        if unconfirmed:
            out.append(Finding(
                "1a", UNDETERMINED, ctx.slug, ctx.name, "parcels-missing-no-plan",
                f"{len(unconfirmed)} commune(s) the inventory marks «oui, plan disponible» with no parcel "
                "of the record in the shapefile, and no plan sheet in the appellation's folder (empty, "
                "absent or not listed)",
                [_row(ctx, c, coverage=cls[c], listed_by_gap_audit=c in ctx.gap_audit_aire)
                 for c in unconfirmed],
                route="read the plans of a neighbouring appellation; else a question for INAO",
            ))
        if in_progress:
            out.append(Finding(
                "1a", REVISION, ctx.slug, ctx.name, "parcels-in-preparation",
                f"{len(in_progress)} commune(s) with a parcel plan «en cours d'élaboration» and no "
                "parcel in the shapefile: the delimitation is not finished",
                [_row(ctx, c, coverage=cls[c]) for c in in_progress],
            ))
        if outside:
            # named in part counts here: the commune is in the area, and the
            # inventory and its plan say the parcels are (Anjou's Oiron)
            own_any = ctx.any_cahier if ctx.cahier_own else set()
            in_cahier = [c for c in outside if c in own_any]
            bucket = CONFLICT_OURS if in_cahier else CONFLICT_INVENTORY
            out.append(Finding(
                "1a", bucket, ctx.slug, ctx.name, "parcels-missing-outside-aire",
                f"{len(outside)} commune(s) the inventory marks oui that INAO's rows leave out of the aire"
                + (f" ({len(in_cahier)} named by the cahier)" if in_cahier else ""),
                [_row(ctx, c, coverage=cls[c], in_cahier=c in own_any,
                      **({"cahier_quote": ctx.cahier_partial[c]} if c in ctx.cahier_partial else {}))
                 for c in outside],
                route=("aires supplement pin, cited (the cahier names them)" if in_cahier
                       else "question for INAO: the inventory lists communes the aire does not"),
            ))
    extra = sorted(c for c in ctx.coverage if not (inv.communes.get(c) and inv.communes[c].oui))
    if extra:
        inside = [c for c in extra if c in ctx.aire or c in ctx.any_cahier]
        outside = [c for c in extra if c not in ctx.aire and c not in ctx.any_cahier]
        newer = [c for c in outside if ctx.plan_newer_than_cahier(c)]
        outside = [c for c in outside if c not in newer]
        if inside:
            out.append(Finding(
                "1b", CONFLICT_INVENTORY, ctx.slug, ctx.name, "parcels-inventory-non",
                f"{len(inside)} commune(s) with parcels of the record in the shapefile, in the aire or named "
                "by the cahier, that the inventory marks non or does not list",
                [_row(ctx, c, in_rows=c in ctx.aire, in_cahier=c in ctx.any_cahier) for c in inside],
                route="question for INAO (the inventory row); the drawing follows the shapefile",
            ))
        if newer:
            out.append(Finding(
                "1b", REVISION, ctx.slug, ctx.name, "parcels-newer-than-cahier",
                f"{len(newer)} commune(s) with parcels of the record in the shapefile that neither INAO's rows "
                "nor the cahier in the build put in the aire, whose plan is newer than the cahier "
                f"({ctx.homologated_at}): a delimitation the text predates",
                [_row(ctx, c) for c in newer],
                route="BO Agri title search for a cahier newer than the build's; else a question for INAO",
            ))
        if outside:
            out.append(Finding(
                "1b", CONFLICT_OURS if ctx.inv.communes else UNDETERMINED, ctx.slug, ctx.name,
                "parcels-outside-aire",
                f"{len(outside)} commune(s) with parcels of the record in the shapefile that neither "
                "INAO's rows, the cahier nor the inventory put in the appellation",
                [_row(ctx, c, in_cahier=False) for c in outside],
                route="read the parcels: a coding error in the shapefile (patch CSV) or a commune the rows miss",
            ))
    drawn_in_prep = sorted(c for c in ctx.coverage if c in oui_cours and c not in oui_dispo)
    if drawn_in_prep:
        out.append(Finding(
            "1c", REVISION, ctx.slug, ctx.name, "drawn-plan-in-preparation",
            f"{len(drawn_in_prep)} commune(s) drawn from parcels whose plan is «en cours d'élaboration»",
            [_row(ctx, c) for c in drawn_in_prep],
        ))
    return out


def check_commune_union(ctx: RecordContext) -> list[Finding]:
    """Check 2: a record drawn as a commune union — what the card says about a
    parcel delimitation, and whether the parcels lie in a few of the communes."""
    if ctx.geom_source not in UNION_SOURCES or ctx.inv is None:
        return []
    out: list[Finding] = []
    inv = ctx.inv
    oui = inv.codes(lambda s: s.oui)
    ident = inv.codes(lambda s: s.ident)
    says_delimited = ctx.card_parcel_area in ("unpublished", "apart", "communes-inventory", "communes-cahier")
    if not ctx.is_dgc or ctx.geom_source != "aires-csv-dgc":
        if oui and not says_delimited:
            if ctx.kind == "IGP":
                # an IGP has no parcel area: the oui is the inventory's
                bucket, route = CONFLICT_INVENTORY, "question for INAO: an IGP has no parcel area"
            elif ctx.own_parcel_area:
                bucket, route = CONFLICT_OURS, "the card line (parcel_area.py)"
            else:
                bucket, route = UNDETERMINED, "read the cahier: another appellation's parcel area, or a reader gap"
            out.append(Finding(
                "2a", bucket, ctx.slug, ctx.name, "card-says-no-parcel-area",
                f"the card says no parcel delimitation exists; the inventory marks {len(oui)} commune(s) oui",
                [_row(ctx, c) for c in sorted(oui)][:40],
                evidence={"oui": len(oui), "own_parcel_area_in_cahier": ctx.own_parcel_area},
                route=route,
            ))
        if says_delimited and not oui:
            out.append(Finding(
                "2a", CONFLICT_INVENTORY, ctx.slug, ctx.name, "inventory-says-no-parcel-area",
                "the cahier sets the record's own parcel area; the inventory marks no commune oui"
                + (f" ({len(ident)} «identification parcellaire»)" if ident else ""),
                evidence={"card": ctx.card_parcel_area, "rows": len(inv.communes)},
                route="question for INAO; the cahier wins",
            ))
        if ident and says_delimited:
            out.append(Finding(
                "2a", UNDETERMINED, ctx.slug, ctx.name, "identification-vs-delimitation",
                f"the card says the cahier delimits parcels; the inventory says «identification "
                f"parcellaire» for {len(ident)} commune(s)",
                route="read the cahier's section IV",
            ))
    drawn = ctx.drawn
    if oui and len(drawn) >= 3 and not ctx.parcel_area_table:
        share = len(oui & drawn) / len(drawn)
        if share <= SMALL_SHARE:
            # a DGC's cahier is its parent's: the parcel-area clause is the
            # parent's statement, not the DGC's
            out.append(Finding(
                "2b", CONFLICT_OURS if ctx.own_parcel_area and ctx.cahier_own else UNDETERMINED,
                ctx.slug, ctx.name, "parcel-area-small-share",
                f"the parcel area lies in {len(oui & drawn)} of the {len(drawn)} communes drawn "
                f"({share:.0%}) per the inventory",
                evidence={"oui_in_drawn": len(oui & drawn), "drawn": len(drawn), "share": round(share, 3),
                          "oui_outside_drawn": sorted(oui - drawn)[:20],
                          "own_parcel_area_in_cahier": ctx.own_parcel_area},
                route="parcel_area_communes.json entry (the Champagne treatment) after reading the cahier",
            ))
    return out


def _classify_code_diff(code: str, other_raw: set[str], canon: Callable[[str], str],
                        recoded: Callable[[str], bool]) -> str:
    """How a raw code one side has and the other lacks differs: the same
    commune of today on the other side (`merged` / `code-changed`), else
    `different`."""
    today = canon(code)
    if today in {canon(c) for c in other_raw}:
        return "code-changed" if recoded(code) else "merged"
    return "different"


def check_aire(ctx: RecordContext, *, aire_raw: set[str], canon: Callable[[str], str],
               recoded: Callable[[str], bool]) -> tuple[list[Finding], dict]:
    """Check 3: the inventory's commune set against INAO's rows and the
    cahier's list. Returns the findings and the counts of code-only
    differences (merged since / code changed), which are not findings."""
    if ctx.inv is None or not ctx.aire_own or not ctx.aire:
        return [], {}
    if ctx.name_shared > 1:
        return [Finding(
            "3", UNDETERMINED, ctx.slug, ctx.name, "inventory-name-shared",
            f"INAO's aires CSV carries the name under {ctx.name_shared} IDAs (another product of this "
            f"name); the inventory's {len(ctx.inv.communes)} communes against the {len(ctx.aire)} of the "
            "record's rows say nothing until the products are told apart",
            evidence={"inventory": len(ctx.inv.communes), "rows": len(ctx.aire)},
            route="none: compare by hand if the record's area is in question",
        )], {}
    inv_raw = ctx.inv.raw_codes
    counts = {"merged": 0, "code-changed": 0, "different": 0}
    for code in (inv_raw - aire_raw):
        counts[_classify_code_diff(code, aire_raw, canon, recoded)] += 1
    for code in (aire_raw - inv_raw):
        counts[_classify_code_diff(code, inv_raw, canon, recoded)] += 1
    inv_today = ctx.inv.codes()
    only_inv = sorted(inv_today - ctx.aire - ctx.aire_decided)
    only_rows = sorted(ctx.aire - inv_today - ctx.aire_decided)
    # INAO's rows draw the record only when it is a commune union; a
    # parcellaire record's polygon does not move with them
    drawn_from_rows = {"rows_draw_the_polygon": ctx.geom_source in UNION_SOURCES}
    out: list[Finding] = []
    cahier = ctx.own_cahier
    cahier_known = bool(cahier) and len(cahier & ctx.aire) >= 0.9 * len(ctx.aire)
    partial = ctx.cahier_partial if ctx.cahier_own else {}
    if only_inv:
        named = [c for c in only_inv if c in cahier]
        in_part = [c for c in only_inv if c not in cahier and c in partial]
        not_named = [c for c in only_inv if c not in cahier and c not in partial]
        if named:
            out.append(Finding(
                "3", CONFLICT_OURS, ctx.slug, ctx.name, "aire-rows-lack",
                f"{len(named)} commune(s) the inventory and the cahier put in the aire, INAO's rows do not",
                [_row(ctx, c, in_cahier=True) for c in named], evidence=drawn_from_rows,
                route="aires supplement pin (aires_supplements.json), once the cahier is the newest published",
            ))
        if in_part:
            out.append(Finding(
                "3", UNDETERMINED, ctx.slug, ctx.name, "aire-named-in-part",
                f"{len(in_part)} commune(s) in the inventory, not in INAO's rows, that the cahier names in "
                "part, under another heading or in an exclusion",
                [_row(ctx, c, cahier_quote=partial[c]) for c in in_part], evidence=drawn_from_rows,
                route="read the quote: a `not_drawn` decision in aires_supplements.json, or a pin",
            ))
        if not_named:
            out.append(Finding(
                "3", CONFLICT_INVENTORY if cahier_known else UNDETERMINED, ctx.slug, ctx.name,
                "inventory-extra",
                f"{len(not_named)} commune(s) in the inventory and not in INAO's rows"
                + (" nor the cahier" if cahier_known else " (the cahier lists no communes)"),
                [_row(ctx, c, in_cahier=False) for c in not_named], evidence=drawn_from_rows,
                route="question for INAO" if cahier_known else "read the cahier's zone text",
            ))
    if only_rows:
        named = [c for c in only_rows if c in cahier or c in partial]
        not_named = [c for c in only_rows if c not in cahier and c not in partial]
        if named:
            out.append(Finding(
                "3", CONFLICT_INVENTORY, ctx.slug, ctx.name, "inventory-lacks",
                f"{len(named)} commune(s) of INAO's rows and the cahier that the inventory leaves out",
                [_row(ctx, c, in_cahier=True, **({"cahier_quote": partial[c]} if c in partial else {}))
                 for c in named], evidence=drawn_from_rows,
                route="question for INAO (inventory incomplete)",
            ))
        if not_named:
            out.append(Finding(
                "3", CONFLICT_OURS if cahier_known else UNDETERMINED, ctx.slug, ctx.name, "rows-extra",
                f"{len(not_named)} commune(s) of INAO's rows that neither the inventory nor the cahier carry"
                + ("" if cahier_known else " (the cahier lists no communes, or few)"),
                [_row(ctx, c, in_cahier=False) for c in not_named], evidence=drawn_from_rows,
                route=("read the cahier: a neighbouring code (aires supplement `remove`) or a reader gap"
                       if cahier_known else "read the cahier's zone text"),
            ))
    return out, counts


def check_plans(ctx: RecordContext) -> list[Finding]:
    """Check 4: the record's plan folder against its inventory «plan
    disponible» communes — INAO against INAO."""
    if ctx.inv is None or ctx.folders is None:
        return []
    dispo = ctx.inv.codes(lambda s: s.oui and s.plan == PLAN_DISPO)
    folders = set(ctx.folders)
    out: list[Finding] = []
    no_folder = sorted(dispo - folders)
    no_row = sorted(folders - dispo)
    if no_folder:
        out.append(Finding("4", INTERNAL, ctx.slug, ctx.name, "plan-disponible-no-folder",
                           f"{len(no_folder)} commune(s) «plan disponible» with no folder in {ctx.folder}",
                           [_row(ctx, c) for c in no_folder]))
    if no_row:
        out.append(Finding("4", INTERNAL, ctx.slug, ctx.name, "folder-not-plan-disponible",
                           f"{len(no_row)} commune folder(s) of {ctx.folder} the inventory does not mark "
                           "«plan disponible»",
                           [_row(ctx, c, folder_name=ctx.folders[c]) for c in no_row]))
    return out


def check_dates(ctx: RecordContext) -> list[Finding]:
    """Check 5: a revision under way, a plan much older than the text, and
    parcel rows an earlier shapefile release had."""
    out: list[Finding] = []
    if ctx.inv is not None:
        rev = sorted(ctx.inv.codes(lambda s: s.revision))
        if rev:
            out.append(Finding("5a", REVISION, ctx.slug, ctx.name, "revision-under-way",
                               f"«Delim/revision en cours» oui on {len(rev)} of {len(ctx.inv.communes)} commune(s)",
                               [_row(ctx, c) for c in rev][:40], evidence={"communes": len(rev)}))
    last = ctx.plan_dates[1]
    if last and ctx.homologated_at and int(ctx.homologated_at[:4]) - int(last[:4]) >= PLAN_AGE_YEARS:
        out.append(Finding("5b", REVISION, ctx.slug, ctx.name, "plan-older-than-cahier",
                           f"the sampled plan sheets date from {ctx.plan_dates[0]}–{last}; the cahier was "
                           f"homologated on {ctx.homologated_at}",
                           evidence={"plan_first": ctx.plan_dates[0], "plan_last": last,
                                     "homologated_at": ctx.homologated_at, "folder": ctx.folder}))
    if ctx.geom_source in PARCEL_SOURCES and ctx.coverage_old:
        lost = sorted(ctx.coverage_old - ctx.coverage - ctx.gap_fills)
        if lost:
            oui = [c for c in lost if ctx.inv and ctx.inv.communes.get(c) and ctx.inv.communes[c].oui]
            out.append(Finding(
                "5c", CONFLICT_OURS if oui else UNDETERMINED, ctx.slug, ctx.name, "parcel-rows-dropped",
                f"{len(lost)} commune(s) with parcels of the record in an earlier shapefile release and "
                f"none in the current one ({len(oui)} marked oui by the inventory)",
                [_row(ctx, c) for c in lost],
                route="parcellaire_carry_forward.json entry with the act that leaves the delimitation in force",
            ))
    return out


def check_subdenomination(ctx: RecordContext) -> list[Finding]:
    """Check 6: a DGC with its own plan folder or its own parcel communes in
    the inventory, drawn coarser than its parcels — and a hand-curated village
    override that lacks a commune the inventory gives the DGC and the text
    names (Champagne grand cru: Oger, a commune déléguée of Blancs-Coteaux
    since 2018, which the override took for part of Le Mesnil-sur-Oger)."""
    if not ctx.is_dgc or ctx.geom_source in PARCEL_SOURCES or ctx.geom_source == "cadastre-lieu-dit-dgc":
        return []
    own_oui = ctx.inv.codes(lambda s: s.oui) if ctx.inv else set()
    out: list[Finding] = []
    if ctx.geom_source == "dgc-village-override" and own_oui - ctx.drawn:
        lacks = sorted(own_oui - ctx.drawn)
        named = [c for c in lacks if c in ctx.any_cahier]
        out.append(Finding(
            "6", CONFLICT_OURS if named else UNDETERMINED, ctx.slug, ctx.name, "override-lacks-commune",
            f"{len(lacks)} commune(s) the inventory marks oui for the DGC that its village override "
            f"(dgc_village_overrides.py) does not draw" + (f", {len(named)} named by the text" if named else ""),
            [_row(ctx, c, in_cahier=c in ctx.any_cahier,
                  **({"cahier_quote": ctx.cahier_partial[c]} if c in ctx.cahier_partial else {}))
             for c in lacks],
            route="dgc_village_overrides.py: the commune the list names, by its own outline when it has merged since",
        ))
    if ctx.folders is None and not own_oui:
        return out
    out.append(Finding(
        "6", UNDETERMINED, ctx.slug, ctx.name, "precision-candidate",
        f"drawn as {ctx.geom_source}"
        + (f" ({len(ctx.drawn)} commune(s))" if ctx.drawn else "")
        + f"; the inventory marks {len(own_oui)} commune(s) oui for it"
        + (f", and {ctx.folder} holds {len(ctx.folders)} commune folder(s)" if ctx.folders is not None else ""),
        [_row(ctx, c) for c in sorted(own_oui)],
        evidence={"drawn": len(ctx.drawn), "oui": len(own_oui),
                  "folders": len(ctx.folders) if ctx.folders is not None else None},
        route="a precision candidate: its parcels are INAO's plans only (no shapefile row); the card says the area is approximate",
    ))
    return out
