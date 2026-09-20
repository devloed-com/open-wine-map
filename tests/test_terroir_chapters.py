"""Own-chapter windows in a shared cahier (scripts/_lib/terroir_chapters.py)."""
from __future__ import annotations

from _lib.terroir_chapters import chapter_windows, is_shared, own_chapter


def chapter(name: str, body: str) -> str:
    return (
        f"                 « Alsace grand cru {name} »\n\n"
        f"1°– Informations sur la zone géographique\n\na) - Description des facteurs naturels\n\n{body}\n\n"
        f"2°– Informations sur la qualité et les caractéristiques des produits\n\nVins blancs.\n\n"
        f"3°– Interactions causales\n\nLe lien.\n\n"
    )


LIEN = (
    "Préambule commun mentionnant « Alsace grand cru Zotzenberg » en passant.\n\n"
    + chapter("Altenberg de Bergheim", "Marnes et calcaires.")
    + chapter("Kastelberg", "Schistes de Steige.")
    + chapter("Zotzenberg", "Marnes très denses sur socle calcaire.")
)


def test_windows_are_found_in_order_and_ignore_passing_mentions():
    names = [n for n, _, _ in chapter_windows(LIEN)]
    assert names == ["Altenberg de Bergheim", "Kastelberg", "Zotzenberg"]
    assert is_shared(LIEN)


def test_own_chapter_matches_the_record_name_accent_and_case_folded():
    s, e = own_chapter(LIEN, "Alsace grand cru KASTELBERG")
    assert "Schistes de Steige" in LIEN[s:e]
    assert "Zotzenberg" not in LIEN[s:e]
    s2, e2 = own_chapter(LIEN, "Altenberg de Bergheim")
    assert "Marnes et calcaires" in LIEN[s2:e2] and "Kastelberg" not in LIEN[s2:e2]


def test_last_chapter_runs_to_the_end():
    s, e = own_chapter(LIEN, "Alsace grand cru Zotzenberg")
    assert e == len(LIEN) and "socle calcaire" in LIEN[s:e]


def test_missing_own_chapter_is_none_not_a_fallback():
    assert own_chapter(LIEN, "Alsace grand cru Rangen") is None


def test_single_chapter_lien_is_not_shared():
    single = chapter("Rangen", "Volcanique.")
    assert not is_shared(single)
    assert own_chapter(single, "Alsace grand cru Rangen") is None
