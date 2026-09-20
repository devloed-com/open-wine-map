"""Boilerplate-fact detector (scripts/_lib/terroir_boilerplate.py)."""
from __future__ import annotations

from _lib.terroir_boilerplate import find_boilerplate, is_tautology

TAUT = ("Η μοναδικότητα των οίνων ΠΓΕ Χαλκιδική οφείλεται στα ιδιαίτερα χαρακτηριστικά της περιοχής "
        "(έδαφος, κλίμα, επίδραση ανέμων)")
REAL = ("Το αμπέλι και το κρασί είναι άρρηκτα δεμένα με την πολιτιστική, κοινωνική και οικονομική ζωή "
        "των ανθρώπων της περιοχής από την αρχαιότητα")


def cache(slug, facts, country="gr", lang="el"):
    return {"slug": slug, "country": country, "source_lang": lang,
            "facts": [{"bullet": b, "cahier_quote": q} for b, q in facts]}


def test_tautology_patterns_are_per_language():
    assert is_tautology(TAUT.casefold(), "el")
    assert not is_tautology(TAUT.casefold(), "it")
    assert not is_tautology(REAL.casefold(), "el")


def test_shared_tautology_is_dropped_but_shared_real_fact_is_kept():
    caches = {
        f"pgi-{i}": cache(f"pgi-{i}", [("Ανάγλυφο και εδάφη.", REAL), ("Μοναδικότητα.", TAUT)])
        for i in range(3)
    }
    assert find_boilerplate(caches) == {"pgi-0": [1], "pgi-1": [1], "pgi-2": [1]}


def test_tautology_in_fewer_than_three_records_is_kept():
    caches = {f"pgi-{i}": cache(f"pgi-{i}", [("A.", REAL), ("B.", TAUT)]) for i in range(2)}
    assert find_boilerplate(caches) == {}


def test_only_fact_is_never_dropped():
    caches = {f"pgi-{i}": cache(f"pgi-{i}", [("B.", TAUT)]) for i in range(3)}
    assert find_boilerplate(caches) == {}


def test_country_partition_and_language_match():
    caches = {f"x-{i}": cache(f"x-{i}", [("A.", REAL), ("B.", TAUT)], country="cy", lang="el") for i in range(2)}
    caches.update({f"y-{i}": cache(f"y-{i}", [("A.", REAL), ("B.", TAUT)], country="gr", lang="el") for i in range(2)})
    assert find_boilerplate(caches) == {}  # 2 + 2, never 3 in one country


def test_embedded_appellation_name_and_span_length_do_not_break_the_grouping():
    caches = {}
    for i, name in enumerate(("Χαλκιδική", "Κοζάνη", "Σιθωνία")):
        q = TAUT.replace("Χαλκιδική", name) + " σε συνδυασμό" * i
        caches[name] = cache(name, [("A.", REAL), ("B.", q)])
    assert find_boilerplate(caches) == {n: [1] for n in caches}


def test_bullet_with_a_number_is_never_boilerplate():
    caches = {f"pgi-{i}": cache(f"pgi-{i}", [("A.", REAL), ("Άνεμοι 25,5 °C.", TAUT)]) for i in range(3)}
    assert find_boilerplate(caches) == {}
