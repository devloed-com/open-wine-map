"""Canonical wine-style taxonomy shared by FR + ES pipelines.

The tree is a directed forest: every slug has at most one parent. Buckets
(red, white, rose, sparkling, sweet, other) are the six top-level nodes
the simple-mode facet exposes. Internal groups (fortified, late-harvest,
raisin-wine, oxidative, generoso) collect siblings whose membership is
shared semantics; they're selectable as filters and expand to all
descendants. Leaves are the fine-grained tags that records actually
carry.

`panel_only` is an available leaf flag: a panel_only leaf shows as a
chip on the AOC panel but is kept out of the advanced facet tree and
the omnisearch index. No leaf currently uses it — the Sherry sub-styles
(fino / manzanilla / amontillado / oloroso / palo-cortado) under
`generoso` are first-class facetable + searchable leaves, so a user can
filter or search them directly rather than only via the parent.

The `country` tag is informational — it marks which corpora actually
use a slug, so audits can flag a record carrying a slug from the wrong
country.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from unidecode import unidecode


@dataclass(frozen=True)
class StyleNode:
    slug: str
    parent: str | None
    msgid: str         # FR-language label; gettext key
    country: tuple[str, ...] = ()   # which corpora use this slug
    panel_only: bool = False
    # Secondary parents for genuinely multi-membership styles — the tree shows
    # the node once under `parent`, but filtering ANY of `extra_parents` also
    # selects it (vin-santo is both a raisin-wine and an oxidative wine).
    extra_parents: tuple[str, ...] = ()
    # Searchable alternative / local names that fold to this canonical slug —
    # the wine-style analogue of grape synonyms. The record carries the
    # canonical tag; search resolves a synonym to it (fondillón → rancio).
    # Store every spelling users might type, incl. diacritic + ASCII forms.
    synonyms: tuple[str, ...] = ()


_NODES_RAW: tuple[StyleNode, ...] = (
    # ----- top-level buckets -----
    StyleNode("red",       None,  "rouge"),
    StyleNode("white",     None,  "blanc"),
    StyleNode("rose",      None,  "rosé"),
    StyleNode("sparkling", None,  "mousseux"),
    StyleNode("sweet",     None,  "doux"),
    StyleNode("other",     None,  "autres"),
    # ----- colour sub-styles -----
    StyleNode("clairet",   "red", "clairet",  ("fr",)),
    StyleNode("primeur",   "red", "primeur",  ("fr",)),
    # ----- sparkling sub-styles -----
    StyleNode("sparkling-quality", "sparkling", "mousseux de qualité", ("fr", "es")),
    StyleNode("cremant",           "sparkling", "crémant",             ("fr",)),
    # Sparkling production methods — a coherent set (so méthode ancestrale isn't
    # the lone one). Traditionnelle = 2nd fermentation in bottle (crémant, Cava,
    # Franciacorta, Sekt); Charmat/Martinotti = tank method (Prosecco, Asti,
    # most spumante); ancestrale = single fermentation (pét-nat); dioise = the
    # Die variant of ancestrale.
    StyleNode("methode-ancestrale", "sparkling", "méthode ancestrale",
              ("fr", "es", "it"),
              synonyms=("methode ancestrale", "metodo ancestral", "metodo ancestrale",
                        "ancestral method", "pet nat", "petillant naturel",
                        "pétillant naturel", "pet-nat")),
    StyleNode("methode-traditionnelle", "sparkling", "méthode traditionnelle",
              ("fr", "es", "it", "de"),
              synonyms=("methode traditionnelle", "methode classique",
                        "méthode classique", "metodo classico", "metodo tradizionale",
                        "metodo tradicional", "metodo clasico", "traditional method",
                        "classic method", "flaschengarung", "flaschengärung",
                        "klassische flaschengarung", "traditionelle flaschengarung")),
    StyleNode("methode-charmat", "sparkling", "méthode Charmat",
              ("it", "fr", "es"),
              synonyms=("methode charmat", "metodo charmat", "metodo martinotti",
                        "charmat", "martinotti", "cuve close", "cuve-close",
                        "metodo granvas", "granvas", "tank method", "tankgarung",
                        "tankgärung")),
    StyleNode("methode-dioise", "sparkling", "méthode dioise",
              ("fr",), synonyms=("methode dioise",)),
    StyleNode("semi-sparkling",    "sparkling", "pétillant",           ("es",)),
    # ----- sweet groups -----
    StyleNode("fortified",   "sweet", "vin muté",       ("fr", "es")),
    StyleNode("late-harvest","sweet", "vendanges tardives (catégorie)", ("fr", "es")),
    StyleNode("raisin-wine", "sweet", "vin de raisins passerillés",     ("fr", "es")),
    # ----- sweet leaves (sweetness level + icewine) -----
    StyleNode("semi-sweet", "sweet", "demi-doux",
              ("it",), synonyms=("amabile", "semidulce", "halbsüß",
                                 "lieblich", "polsladko", "polosladke", "feledes")),
    StyleNode("icewine", "sweet", "vin de glace",
              ("de", "at", "hu", "cz", "sk", "es", "si"),
              synonyms=("eiswein", "eis wein", "ice wine", "icewine", "vin de glace",
                        "jegbor", "jégbor", "ladove vino", "ľadové víno",
                        "ledove vino", "ledové víno", "ledeno vino",
                        "vino de hielo", "vino di ghiaccio", "ghiacciato")),
    # ----- fortified leaves -----
    StyleNode("vdn",            "fortified", "vin doux naturel", ("fr",)),
    StyleNode("vin-de-liqueur", "fortified", "vin de liqueur",   ("fr", "es")),
    StyleNode("mistela",        "fortified", "mistelle",         ("es", "fr")),
    # ----- late-harvest leaves -----
    StyleNode("vendanges-tardives",  "late-harvest", "vendanges tardives",   ("fr",)),
    StyleNode("uvas-sobremaduradas", "late-harvest", "uvas sobremaduradas",  ("es",)),
    StyleNode("dulce-natural",       "late-harvest", "vin naturellement doux", ("es",)),
    StyleNode("grains-nobles",       "late-harvest", "grains nobles",        ("fr",)),
    # ----- raisin-wine leaves -----
    StyleNode("vin-de-paille",     "raisin-wine", "vin de paille",        ("fr",)),
    StyleNode("uvas-pasificadas",  "raisin-wine", "uvas pasificadas",     ("es",)),
    # vin-santo: a dried-grape (passito) wine AND an oxidatively cask-aged one —
    # filtering either raisin-wine or oxidative selects it (extra_parents).
    StyleNode("vin-santo", "raisin-wine", "vin santo", ("it", "gr"),
              extra_parents=("oxidative",),
              synonyms=("vinsanto", "vino santo", "vin santo")),
    # ----- other-bucket leaves -----
    StyleNode("tranquille", "other", "tranquille", ("fr",)),
    StyleNode("sur-lie",    "other", "sur lie",    ("fr",)),
    StyleNode("dry",        "other", "sec",        ("fr", "es")),
    StyleNode("semi-dry",   "other", "demi-sec",
              ("fr",), synonyms=("demi-sec", "demisec", "semi-seco", "semiseco",
                                 "halbtrocken", "abboccato", "polusuho",
                                 "polosuche", "felszaraz")),
    # ----- oxidative top-level bucket -----
    StyleNode("oxidative",  None,    "oxydatif",   ("fr", "es")),
    # ----- oxidative leaves -----
    StyleNode("rancio",    "oxidative", "rancio",    ("fr", "es"),
              synonyms=("fondillon", "fondillón", "ranci")),
    StyleNode("vin-jaune", "oxidative", "vin jaune", ("fr",)),
    StyleNode("generoso",  "oxidative", "generoso",  ("es",)),
    # ----- generoso (Sherry) sub-styles — facetable + searchable -----
    StyleNode("fino",         "generoso", "fino",         ("es",)),
    StyleNode("manzanilla",   "generoso", "manzanilla",   ("es",)),
    StyleNode("amontillado",  "generoso", "amontillado",  ("es",)),
    StyleNode("oloroso",      "generoso", "oloroso",      ("es",)),
    StyleNode("palo-cortado", "generoso", "palo cortado", ("es",)),
)


NODES: dict[str, StyleNode] = {n.slug: n for n in _NODES_RAW}


def parent(slug: str) -> str | None:
    n = NODES.get(slug)
    return n.parent if n else None


def children(slug: str) -> list[str]:
    """Primary-parent children only — the single-position tree used by the
    advanced-mode facet DFS. A multi-membership node appears here once, under
    its canonical `parent` (see `_filter_children` for the filtering view)."""
    return [n.slug for n in _NODES_RAW if n.parent == slug]


def _filter_children(slug: str) -> list[str]:
    """Children for FILTERING/expansion — includes nodes whose `extra_parents`
    name `slug`, so selecting either parent of a multi-membership node (e.g.
    vin-santo under raisin-wine OR oxidative) reaches it."""
    return [n.slug for n in _NODES_RAW if n.parent == slug or slug in n.extra_parents]


def descendants(slug: str, *, include_self: bool = True) -> set[str]:
    """All slugs reachable downward from `slug` (transitive closure), following
    both primary and secondary (extra_parents) membership — this is the set the
    facet expansion uses, so a multi-parent node is reachable from each parent."""
    out: set[str] = {slug} if include_self else set()
    stack = [slug]
    while stack:
        cur = stack.pop()
        for c in _filter_children(cur):
            if c in out:
                continue
            out.add(c)
            stack.append(c)
    return out


# Top-level buckets — simple-mode facet entries.
BUCKETS: tuple[str, ...] = ("red", "white", "rose", "sparkling", "sweet", "oxidative", "other")


def simple_bucket(slug: str) -> str:
    """Walk up to the top-level bucket. Returns 'other' for unknown slugs."""
    cur: str | None = slug
    seen: set[str] = set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        p = parent(cur)
        if p is None:
            return cur if cur in BUCKETS else "other"
        cur = p
    return "other"


def simple_buckets(slug: str) -> set[str]:
    """Every top-level bucket a slug belongs to, following primary AND secondary
    (extra_parents) membership — so a multi-membership leaf (vin-santo) reports
    both `sweet` and `oxidative`. Returns {'other'} for unknown slugs."""
    out: set[str] = set()
    seen: set[str] = set()
    stack = [slug]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        n = NODES.get(cur)
        if n is None:
            continue
        parents = [p for p in (n.parent, *n.extra_parents) if p]
        if not parents:
            if cur in BUCKETS:
                out.add(cur)
        else:
            stack.extend(parents)
    return out or {"other"}


def bucket_descendants() -> dict[str, list[str]]:
    """`{bucket: [every leaf-or-group reachable below it]}` — feeds the JS-side
    expansion map for simple-mode filtering."""
    return {b: sorted(descendants(b) - {b}) for b in BUCKETS}


def taxonomy_dfs_order(
    *, exclude_panel_only: bool = True,
) -> list[tuple[str, str | None, int]]:
    """`(slug, parent, depth)` tuples in declared DFS order, roots in
    `BUCKETS` order. Feeds the advanced-mode tree facet."""
    out: list[tuple[str, str | None, int]] = []

    def visit(slug: str, depth: int) -> None:
        node = NODES[slug]
        if exclude_panel_only and node.panel_only:
            return
        out.append((slug, node.parent, depth))
        for c in children(slug):
            visit(c, depth + 1)

    for b in BUCKETS:
        visit(b, 0)
    return out


def descendants_map(*, exclude_panel_only: bool = True) -> dict[str, list[str]]:
    """`{slug: [slug, ...descendants]}` — the expansion set the JS uses to
    translate a tree-facet click into the leaf slugs records actually carry."""
    out: dict[str, list[str]] = {}
    for slug, _, _ in taxonomy_dfs_order(exclude_panel_only=exclude_panel_only):
        ds = descendants(slug)
        if exclude_panel_only:
            ds = {s for s in ds if not NODES[s].panel_only}
        out[slug] = sorted(ds)
    return out


def all_slugs() -> list[str]:
    return [n.slug for n in _NODES_RAW]


def facetable_slugs() -> list[str]:
    """Every slug except panel-only leaves — i.e. what the facet sidebar shows
    in advanced mode."""
    return [n.slug for n in _NODES_RAW if not n.panel_only]


def panel_only_slugs() -> set[str]:
    return {n.slug for n in _NODES_RAW if n.panel_only}


def _norm_synonym(term: str) -> str:
    """Search-normalise a style name: lowercase + strip diacritics so the
    diacritic and ASCII spellings of a synonym collapse (fondillón→fondillon)."""
    return unidecode(term).strip().lower()


def style_synonyms() -> dict[str, str]:
    """`{normalised synonym → canonical slug}` — the wine-style analogue of the
    grape synonym index. Each canonical slug also maps from its own slug form.
    Raises on a synonym claimed by two slugs (the dict-clash guard: an ambiguous
    style synonym would silently fold a wine under the wrong style)."""
    out: dict[str, str] = {}
    for n in _NODES_RAW:
        for term in (n.slug, *n.synonyms):
            key = _norm_synonym(term)
            if not key:
                continue
            prior = out.get(key)
            if prior is not None and prior != n.slug:
                raise ValueError(
                    f"style synonym {key!r} claimed by both {prior!r} and {n.slug!r}"
                )
            out[key] = n.slug
    return out


def canonical_style(term: str) -> str | None:
    """Resolve a free-text style name (canonical slug or any synonym, any
    spelling) to its canonical taxonomy slug, or None if unknown."""
    return style_synonyms().get(_norm_synonym(term))


def style_search_terms() -> dict[str, list[str]]:
    """`{canonical slug → [extra searchable terms]}` for slugs that have
    synonyms — emitted into the build so the JS search box matches local names
    (typing 'fondillon' surfaces the rancio wines). Excludes the slug itself
    and the localized label (those are already searchable)."""
    return {
        n.slug: list(dict.fromkeys(_norm_synonym(s) for s in n.synonyms))
        for n in _NODES_RAW if n.synonyms
    }


def build_style_labels(_: Callable[[str], str]) -> dict[str, str]:
    """slug → translated label. msgid is the FR form (project convention)."""
    return {n.slug: _(n.msgid) for n in _NODES_RAW}


def _msgid_anchors_for_babel(_: Callable[[str], str]) -> tuple[str, ...]:
    """Static `_()` calls so pybabel's AST extractor can see every msgid.

    `build_style_labels` looks msgids up via `n.msgid` (a variable), which
    pybabel can't follow. Listing each literal here keeps the FR `.po`
    catalog in sync. Never called at runtime — referenced only by the
    pybabel extractor pass over this module.
    """
    return (
        _("rouge"), _("blanc"), _("rosé"), _("mousseux"), _("doux"),
        _("autres"),
        _("clairet"), _("primeur"),
        _("mousseux de qualité"), _("crémant"), _("méthode ancestrale"),
        _("méthode traditionnelle"), _("méthode Charmat"), _("méthode dioise"),
        _("pétillant"),
        _("vin muté"), _("vendanges tardives (catégorie)"),
        _("vin de raisins passerillés"),
        _("demi-doux"), _("vin de glace"),
        _("vin doux naturel"), _("vin de liqueur"), _("mistelle"),
        _("vendanges tardives"), _("uvas sobremaduradas"),
        _("vin naturellement doux"), _("grains nobles"),
        _("vin de paille"), _("uvas pasificadas"), _("vin santo"),
        _("tranquille"), _("sur lie"), _("sec"), _("demi-sec"), _("oxydatif"),
        _("rancio"), _("vin jaune"), _("generoso"),
        _("fino"), _("manzanilla"), _("amontillado"),
        _("oloroso"), _("palo cortado"),
    )


def build_simple_style_labels(_: Callable[[str], str]) -> dict[str, str]:
    """Top-bucket labels for simple mode. msgids parallel `build_style_labels`
    but are pulled from the shared LABELS catalog so existing translations
    keep working — see scripts/_lib/map_template.build_labels keys
    `style_simple_*`."""
    # Re-routed via the existing simple_* msgids so locale .po files don't
    # need to gain new entries for what is essentially the same word with
    # a slightly different translator note.
    return {
        "red":       _("rouge"),
        "white":     _("blanc"),
        "rose":      _("rosé"),
        "sparkling": _("mousseux"),
        "sweet":     _("doux"),
        "other":     _("autres"),
    }
