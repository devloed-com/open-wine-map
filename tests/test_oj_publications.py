"""The single-document publication a stage 01 fetches: newest OJ C by date
(scripts/_lib/oj_publications.py), not the first one eAmbrosia lists."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _lib.oj_publications import (  # noqa: E402
    is_oj_c,
    ordered_publication_uris,
    preferred_publication_uri,
    sort_key,
)

JEREZ = [  # the held list of 2026-05: the 2023 document first, the 2025 one later
    {"text": "Official Journal C 98, 16.3.2023, ",
     "uri": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=uriserv%3AOJ.C_.2023.098.01.0036.01.ENG&toc=OJ%3AC%3A2023%3A098%3ATOC"},
    {"text": "Ares(2024)1703890", "uri": "89234"},
    {"text": "Official Journal C, C/2025/2129, 8.4.2025", "uri": "http://data.europa.eu/eli/C/2025/2129/oj"},
    {"text": "Official Journal L, 2025/1713, 4.8.2025", "uri": "http://data.europa.eu/eli/reg_impl/2025/1713/oj"},
]


def test_newest_oj_c_wins_over_list_order():
    assert preferred_publication_uri(JEREZ) == "http://data.europa.eu/eli/C/2025/2129/oj"


def test_prepended_new_publication():
    pubs = [{"text": "Official Journal C, C/2026/4549, 26.8.2026", "uri": "http://data.europa.eu/eli/C/2026/4549/oj"}, *JEREZ]
    assert preferred_publication_uri(pubs) == "http://data.europa.eu/eli/C/2026/4549/oj"


def test_oj_l_and_ares_never_chosen_over_oj_c():
    order = ordered_publication_uris(JEREZ)
    assert order[:2] == ["http://data.europa.eu/eli/C/2025/2129/oj", JEREZ[0]["uri"]]
    assert order[-1] == "http://data.europa.eu/eli/reg_impl/2025/1713/oj"
    assert "89234" not in order


def test_corrigendum_after_every_other_oj_c():
    pubs = [
        {"text": "Corrigendum - Official Journal C, C/2025/90060, 1.8.2025",
         "uri": "http://data.europa.eu/eli/C/2025/90060/oj"},
        {"text": "Official Journal C 68, 24.2.2023",
         "uri": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=uriserv%3AOJ.C_.2023.068.01.0041.01.ENG"},
    ]
    assert preferred_publication_uri(pubs).endswith("OJ.C_.2023.068.01.0041.01.ENG")


def test_text_variants():
    marsala = {"text": "Official Journal, C/2026/5127, 7.10.2026", "uri": "http://data.europa.eu/eli/C/2026/5127/oj"}
    assert is_oj_c(marsala)
    assert sort_key(marsala)[:3] == (2026, 10, 7)
    undated = {"text": "Official Journal C, C/2026/3089", "uri": "http://data.europa.eu/eli/C/2026/3089/oj"}
    assert sort_key(undated) == (2026, 0, 0, 3089)
    old = {"text": "Official Journal C199 11.06.2018",
           "uri": "https://eur-lex.europa.eu/legal-content/NL/TXT/HTML/?uri=OJ%3AJOC_2018_199_R_0004"}
    assert is_oj_c(old) and sort_key(old)[:3] == (2018, 6, 11)


def test_no_http_publication():
    assert preferred_publication_uri([{"text": "Ares(2026)8001930", "uri": "64686"}]) is None
    assert preferred_publication_uri([]) is None


PENEDES = [
    {"text": "Ares(2026)9624546", "uri": "64999"},
    {"text": "Official Journal C, C/2026/2777, 19.5.2026", "uri": "http://data.europa.eu/eli/C/2026/2777/oj"},
    {"text": "Official Journal C 199, 17.5.2022",
     "uri": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=uriserv%3AOJ.C_.2022.199.01.0012.01.ENG"},
]
DRAGASANI = [
    {"text": "Official Journal C 439, 29.10.2021",
     "uri": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=uriserv%3AOJ.C_.2021.439.01.0013.01.ENG"},
    {"text": "Official Journal C, C/2026/1651, 13.03.2026", "uri": "http://data.europa.eu/eli/C/2026/1651/oj"},
    {"text": "Official Journal L, 2026/1702, 10.7.2026", "uri": "http://data.europa.eu/eli/reg_impl/2026/1702/oj"},
]


def test_flagged_amendment_is_not_second_guessed():
    # amendmentsInProgressFlag does not say which OJ C is pending: an approved
    # standard amendment is followed by no OJ L either, so the newest OJ C wins.
    assert preferred_publication_uri(PENEDES) == "http://data.europa.eu/eli/C/2026/2777/oj"
    assert preferred_publication_uri(DRAGASANI) == "http://data.europa.eu/eli/C/2026/1651/oj"
