"""Classification (aging / ripeness / selection tier) taxonomy.

A facet PARALLEL to the wine-style taxonomy (scripts/_lib/style_taxonomy.py) but
for the regulator *classification* dimension — the traditional aging, ripeness
and selection tiers that sit ALONGSIDE a wine's colour/style, not as a style:

  - Aging (oak/bottle): Crianza, Reserva, Gran Reserva (ES); Riserva, Superiore,
    Gran Selezione (IT); Garrafeira, Colheita (PT); Roble (ES).
  - Prädikat (ripeness at harvest, must-weight ladder): Kabinett, Spätlese,
    Auslese, Beerenauslese, Trockenbeerenauslese (DE/AT); Ausbruch (AT).
  - Selection (botrytis / berry selection): Aszú, Szamorodni, Eszencia (HU);
    Výber z hrozna / bobúľ / cibéb, Samorodné (SK/CZ).

Tier slugs carry multilingual `synonyms` (the alias pattern: a tier is found by
any local spelling and search resolves a synonym to the canonical slug). The
three families are the tree roots (the facet groups). Tier LABELS stay native
(Crianza/Spätlese/Aszú are proper terms, not translated, like region facets);
only the three group labels are gettext-translated.

Detection (stage 04) is text-scan with per-term gating — several tier words are
generic (`roble`=oak, `colheita`=vintage, `superiore`=superior), so the detector
gates them; see `04_build_maps._aging_tiers_from_text`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from unidecode import unidecode


@dataclass(frozen=True)
class TierNode:
    slug: str
    parent: str | None        # None for the three family-group roots
    msgid: str                # gettext key (group labels) / native term (tiers)
    country: tuple[str, ...] = ()
    synonyms: tuple[str, ...] = ()


# Group roots get a gettext msgid (translated heading); tier leaves get their
# native term as msgid (rendered verbatim, never translated).
_NODES_RAW: tuple[TierNode, ...] = (
    # ----- family roots (msgid = FR group label; EN/es/nl translated) -----
    TierNode("aging",     None, "Vieillissement"),
    TierNode("pradikat",  None, "Prädikat"),
    TierNode("selection", None, "Sélection"),
    # ----- aging (oak / bottle) -----
    TierNode("crianza",        "aging", "Crianza", ("es",), synonyms=("crianza",)),
    TierNode("reserva",        "aging", "Reserva", ("es", "pt"), synonyms=("reserva",)),
    TierNode("gran-reserva",   "aging", "Gran Reserva", ("es",), synonyms=("gran reserva",)),
    TierNode("riserva",        "aging", "Riserva", ("it",), synonyms=("riserva",)),
    TierNode("superiore",      "aging", "Superiore", ("it",), synonyms=("superiore",)),
    TierNode("gran-selezione", "aging", "Gran Selezione", ("it",),
             synonyms=("gran selezione",)),
    TierNode("garrafeira",     "aging", "Garrafeira", ("pt",), synonyms=("garrafeira",)),
    TierNode("colheita",       "aging", "Colheita", ("pt",), synonyms=("colheita",)),
    TierNode("roble",          "aging", "Roble", ("es",),
             synonyms=("roble", "vino de roble")),
    # ----- Prädikat (ripeness at harvest) -----
    TierNode("kabinett",     "pradikat", "Kabinett", ("de", "at"), synonyms=("kabinett",)),
    TierNode("spatlese",     "pradikat", "Spätlese", ("de", "at"),
             synonyms=("spätlese", "spatlese")),
    TierNode("auslese",      "pradikat", "Auslese", ("de", "at"), synonyms=("auslese",)),
    TierNode("beerenauslese","pradikat", "Beerenauslese", ("de", "at"),
             synonyms=("beerenauslese",)),
    TierNode("trockenbeerenauslese", "pradikat", "Trockenbeerenauslese", ("de", "at"),
             synonyms=("trockenbeerenauslese", "tba")),
    TierNode("ausbruch",     "pradikat", "Ausbruch", ("at",), synonyms=("ausbruch",)),
    # ----- selection (botrytis / berry selection) -----
    TierNode("aszu",        "selection", "Aszú", ("hu",), synonyms=("aszú", "aszu")),
    TierNode("szamorodni",  "selection", "Szamorodni", ("hu",), synonyms=("szamorodni",)),
    TierNode("eszencia",    "selection", "Eszencia", ("hu",),
             synonyms=("eszencia", "esszencia")),
    TierNode("vyber-z-hrozna", "selection", "Výber z hrozna", ("sk", "cz"),
             synonyms=("výber z hrozna", "výběr z hroznů")),
    TierNode("vyber-z-bobul",  "selection", "Výber z bobúľ", ("sk", "cz"),
             synonyms=("výber z bobúľ", "výběr z bobulí")),
    TierNode("vyber-z-cibeb",  "selection", "Výber z cibéb", ("sk", "cz"),
             synonyms=("výber z cibéb", "výběr z cibéb")),
    TierNode("samorodne",   "selection", "Samorodné", ("sk", "cz"),
             synonyms=("samorodné", "samorodné víno")),
)


NODES: dict[str, TierNode] = {n.slug: n for n in _NODES_RAW}

# Family-group roots, in display order.
GROUPS: tuple[str, ...] = ("aging", "pradikat", "selection")


def children(slug: str) -> list[str]:
    return [n.slug for n in _NODES_RAW if n.parent == slug]


def descendants(slug: str, *, include_self: bool = True) -> set[str]:
    out: set[str] = {slug} if include_self else set()
    for c in children(slug):
        out |= descendants(c)
    return out


def all_slugs() -> list[str]:
    return [n.slug for n in _NODES_RAW]


def tier_slugs() -> list[str]:
    """Leaf (non-group) slugs — the tiers records actually carry."""
    return [n.slug for n in _NODES_RAW if n.parent is not None]


def taxonomy_dfs_order() -> list[tuple[str, str | None, int]]:
    """`(slug, parent, depth)` in declared DFS order, roots in GROUPS order —
    feeds the tree facet (same shape as style_taxonomy.taxonomy_dfs_order)."""
    out: list[tuple[str, str | None, int]] = []

    def visit(slug: str, depth: int) -> None:
        out.append((slug, NODES[slug].parent, depth))
        for c in children(slug):
            visit(c, depth + 1)

    for g in GROUPS:
        visit(g, 0)
    return out


def descendants_map() -> dict[str, list[str]]:
    """`{slug: [slug, ...descendants]}` — JS expansion set so clicking a family
    group selects all its tiers."""
    return {slug: sorted(descendants(slug)) for slug, _, _ in taxonomy_dfs_order()}


def _norm(term: str) -> str:
    return unidecode(term).strip().lower()


def tier_synonyms() -> dict[str, str]:
    """`{normalised synonym -> canonical tier slug}` with a uniqueness guard
    (an ambiguous synonym would fold a wine under the wrong tier)."""
    out: dict[str, str] = {}
    for n in _NODES_RAW:
        if n.parent is None:
            continue
        for term in (n.slug, *n.synonyms):
            key = _norm(term)
            if not key:
                continue
            prior = out.get(key)
            if prior is not None and prior != n.slug:
                raise ValueError(
                    f"classification synonym {key!r} claimed by {prior!r} and {n.slug!r}"
                )
            out[key] = n.slug
    return out


def canonical_tier(term: str) -> str | None:
    return tier_synonyms().get(_norm(term))


def tier_search_terms() -> dict[str, list[str]]:
    """`{tier slug -> [extra searchable terms]}` for the omnisearch (find a tier
    by a local spelling). Excludes the slug itself."""
    return {
        n.slug: list(dict.fromkeys(_norm(s) for s in n.synonyms))
        for n in _NODES_RAW if n.parent is not None and n.synonyms
    }


def build_tier_labels(_: Callable[[str], str]) -> dict[str, str]:
    """slug -> label. Group roots are gettext-translated; tier leaves render
    their native term verbatim."""
    out: dict[str, str] = {}
    for n in _NODES_RAW:
        out[n.slug] = _(n.msgid) if n.parent is None else n.msgid
    return out


def _msgid_anchors_for_babel(_: Callable[[str], str]) -> tuple[str, ...]:
    """Static `_()` calls so pybabel sees the group-label msgids (tier leaves
    are native, never translated, so they are intentionally absent)."""
    return (
        _("Vieillissement"),
        _("Prädikat"),
        _("Sélection"),
    )
