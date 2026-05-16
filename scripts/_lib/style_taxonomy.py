"""Canonical wine-style taxonomy shared by FR + ES pipelines.

The tree is a directed forest: every slug has at most one parent. Buckets
(red, white, rose, sparkling, sweet, other) are the six top-level nodes
the simple-mode facet exposes. Internal groups (fortified, late-harvest,
raisin-wine, oxidative, generoso) collect siblings whose membership is
shared semantics; they're selectable as filters and expand to all
descendants. Leaves are the fine-grained tags that records actually
carry.

Some leaves are `panel_only` — they appear as chips on the AOC panel
when the pliego identifies them (Sherry sub-styles fino / manzanilla /
…) but are not surfaced in the facet sidebar; users filter the parent
`generoso` to reach them.

The `country` tag is informational — it marks which corpora actually
use a slug, so audits can flag a record carrying a slug from the wrong
country.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class StyleNode:
    slug: str
    parent: str | None
    msgid: str         # FR-language label; gettext key
    country: tuple[str, ...] = ()   # which corpora use this slug
    panel_only: bool = False


_NODES_RAW: tuple[StyleNode, ...] = (
    # ----- top-level buckets -----
    StyleNode("red",       None,  "rouge"),
    StyleNode("white",     None,  "blanc"),
    StyleNode("rose",      None,  "rosé"),
    StyleNode("sparkling", None,  "mousseux"),
    StyleNode("sweet",     None,  "moelleux"),
    StyleNode("other",     None,  "autres"),
    # ----- colour sub-styles -----
    StyleNode("clairet",   "red", "clairet",  ("fr",)),
    StyleNode("primeur",   "red", "primeur",  ("fr",)),
    # ----- sparkling sub-styles -----
    StyleNode("sparkling-quality", "sparkling", "mousseux de qualité", ("fr", "es")),
    StyleNode("cremant",           "sparkling", "crémant",             ("fr",)),
    StyleNode("semi-sparkling",    "sparkling", "pétillant",           ("es",)),
    # ----- sweet groups -----
    StyleNode("fortified",   "sweet", "vin muté",       ("fr", "es")),
    StyleNode("late-harvest","sweet", "vendanges tardives (catégorie)", ("fr", "es")),
    StyleNode("raisin-wine", "sweet", "vin de raisins passerillés",     ("fr", "es")),
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
    # ----- other-bucket leaves -----
    StyleNode("tranquille", "other", "tranquille", ("fr",)),
    StyleNode("dry",        "other", "sec",        ("fr", "es")),
    StyleNode("oxidative",  "other", "oxydatif",   ("fr", "es")),
    # ----- oxidative leaves -----
    StyleNode("rancio",    "oxidative", "rancio",    ("fr", "es")),
    StyleNode("vin-jaune", "oxidative", "vin jaune", ("fr",)),
    StyleNode("generoso",  "oxidative", "generoso",  ("es",)),
    # ----- generoso panel-only sub-tags -----
    StyleNode("fino",         "generoso", "fino",         ("es",), panel_only=True),
    StyleNode("manzanilla",   "generoso", "manzanilla",   ("es",), panel_only=True),
    StyleNode("amontillado",  "generoso", "amontillado",  ("es",), panel_only=True),
    StyleNode("oloroso",      "generoso", "oloroso",      ("es",), panel_only=True),
    StyleNode("palo-cortado", "generoso", "palo cortado", ("es",), panel_only=True),
)


NODES: dict[str, StyleNode] = {n.slug: n for n in _NODES_RAW}


def parent(slug: str) -> str | None:
    n = NODES.get(slug)
    return n.parent if n else None


def children(slug: str) -> list[str]:
    return [n.slug for n in _NODES_RAW if n.parent == slug]


def descendants(slug: str, *, include_self: bool = True) -> set[str]:
    """All slugs reachable downward from `slug` (transitive closure)."""
    out: set[str] = {slug} if include_self else set()
    stack = [slug]
    while stack:
        cur = stack.pop()
        for c in children(cur):
            if c in out:
                continue
            out.add(c)
            stack.append(c)
    return out


# Top-level buckets — simple-mode facet entries.
BUCKETS: tuple[str, ...] = ("red", "white", "rose", "sparkling", "sweet", "other")


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
        _("rouge"), _("blanc"), _("rosé"), _("mousseux"), _("moelleux"),
        _("autres"),
        _("clairet"), _("primeur"),
        _("mousseux de qualité"), _("crémant"), _("pétillant"),
        _("vin muté"), _("vendanges tardives (catégorie)"),
        _("vin de raisins passerillés"),
        _("vin doux naturel"), _("vin de liqueur"), _("mistelle"),
        _("vendanges tardives"), _("uvas sobremaduradas"),
        _("vin naturellement doux"), _("grains nobles"),
        _("vin de paille"), _("uvas pasificadas"),
        _("tranquille"), _("sec"), _("oxydatif"),
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
        "sweet":     _("moelleux"),
        "other":     _("autres"),
    }
