"""The sub-sections of a French link text headed by titles
(`scripts/_lib/fr/lien_titles.py`): IGP wines, spirits, ciders."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.fr.lien_titles import slice_by_titles, title_key  # noqa: E402


def test_titles_are_classed_by_their_words():
    cases = {
        "Spécificité de la zone géographique": "facteurs_naturels",
        "Les facteurs physiques du lien": "facteurs_naturels",
        "Description des facteurs naturels et des facteurs humains du lien au terroir": "facteurs_naturels",
        "Caractéristiques de la zone géographique": "facteurs_naturels",
        "Les facteurs humains du lien": "facteurs_humains",
        "Éléments historiques concernant les facteurs du lien au terroir": "facteurs_humains",
        "Spécificité du produit": "produit",
        "Caractéristiques du rhum attribuables à l’aire géographique": "produit",
        "Caractéristiques de l’eau de vie de cidre": "produit",
        "Éléments historiques liés à l’antériorité et à la réputation de la production": "produit",
        "La réputation de la « Mirabelle d’Alsace »": "produit",
        "Lien causal entre l’aire géographique et la qualité ou les caractéristiques du produit": "interactions",
        "Interactions causales": "interactions",
    }
    for title, key in cases.items():
        assert title_key(title) == key, title
    # a place is no product, a sentence no title
    assert title_key("Caractéristiques des Alpilles") is None
    assert title_key("Les vergers sont situés sur des sols profonds") is None


def test_a_spirit_link_is_cut_at_its_headings():
    body = "Texte du cahier. " * 20
    lien = (
        f"5.1 Les facteurs physiques du lien\n\n{body}\n\n"
        f"5.2 Les facteurs humains du lien\n\n{body}\n\n"
        f"5.3 Les spécificités du produit\n\n{body}\n\n"
        f"5.4 Lien causal entre l’aire géographique et la qualité ou les caractéristiques du produit\n\n{body}\n"
    )
    slices = slice_by_titles(lien)
    assert list(slices) == ["facteurs_naturels", "facteurs_humains", "produit", "interactions"]
    assert slices["produit"].startswith("5.3 Les spécificités du produit")


def test_two_stretches_of_one_sub_section_are_joined_and_one_heading_is_no_split():
    body = "Texte. " * 40
    lien = (
        f"5.1 Spécificité de l’aire géographique\n\na) Description des facteurs naturels et des facteurs humains du lien au terroir\n\n{body}\n\n"
        f"b) Éléments historiques concernant les facteurs du lien au terroir\n\n{body}\n\n"
        f"5.2 Spécificité du produit\n\na) Caractéristiques du produit\n\n{body}\n\n"
        f"c) Lien causal entre l’aire géographique et la qualité ou les caractéristiques du produit\n\n{body}\n"
    )
    slices = slice_by_titles(lien)
    assert set(slices) == {"facteurs_naturels", "facteurs_humains", "produit", "interactions"}
    assert slices["produit"].count("Caractéristiques du produit") == 1
    # a sentence that merely mentions the words is no heading; one heading is no split
    assert slice_by_titles("Les facteurs naturels de la zone, à savoir le climat, le sol et le relief, expliquent le produit.\n" + body) == {}
    assert slice_by_titles(f"Spécificité du produit\n\n{body}") == {}
