"""Behaviour tests for the ES national-pliego variety parser
(`scripts/_lib/es/national_pliego.py`).

Focus on the two seams that carry the regulator-format variation documented
inline in the module:

  - find_variety_section: locating section 6 ("Variedad(es)…") across the
    strong/weak heading forms and the regional quirks called out in the code
    (penedes drops the "DE" linker and has a mid-section page number; mentrida
    runs 6→7; los-cerrillos reuses prefix "6" for the next section so the stop
    is by title, not number; TOC dot-leader / page-number lines must not match).
  - _normalise_token rejection rules: the pre-match cleaning + structural-noise
    drops that fire BEFORE the vocab matcher (so they're testable without the
    rapidfuzz-backed match_variety vocab).

These use small synthetic section texts rather than whole cached pliegos — the
behaviours under test are heading-regex routing and token rejection, exercised
precisely by minimal crafted input. Real cached pliego text lives under
raw/es/national-pliegos-extracted/ (gitignored) for manual spot-checks.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.es.national_pliego import (  # noqa: E402
    _normalise_token,
    find_variety_section,
)


def _section(text: str) -> str:
    """Return the located variety-section body, or '' if not found."""
    span = find_variety_section(text)
    return text[span[0]:span[1]].strip() if span else ""


# --------------------------------------------------------------------------
# find_variety_section — heading detection
# --------------------------------------------------------------------------

def test_strong_header_standard_numbered():
    text = (
        "5. Rendimiento máximo\n"
        "100 hl/ha.\n"
        "6. Variedad o variedades de uva\n"
        "Tempranillo, Garnacha Tinta.\n"
        "7. Vínculo con la zona geográfica\n"
        "El clima continental...\n"
    )
    body = _section(text)
    assert "Tempranillo, Garnacha Tinta." in body
    # Must stop before section 7.
    assert "Vínculo" not in body
    assert "clima continental" not in body


def test_strong_header_penedes_no_de_linker():
    # penedes: "6.-Variedades Vitis viníferas" — the "DE" linker is dropped.
    text = (
        "6.-Variedades Vitis viníferas\n"
        "Macabeo, Xarel.lo, Parellada.\n"
        "7.- Vínculo\n"
        "...\n"
    )
    body = _section(text)
    assert "Macabeo" in body and "Parellada" in body
    assert "Vínculo" not in body


def test_weak_header_variedades_alone():
    # ribeira-sacra style: "6. Variedad o variedades" with no keyword trailer.
    text = (
        "6. Variedad o variedades\n"
        "Mencía, Godello.\n"
        "7. Otros\n"
    )
    body = _section(text)
    assert "Mencía" in body and "Godello" in body


def test_toc_dot_leader_line_is_not_a_header():
    # A table-of-contents entry must not be mistaken for the real heading.
    text = (
        "6. Variedades de uva .................. 12\n"
        "\n"
        "6. Variedades de uva de vinificación\n"
        "Airén, Cencibel.\n"
        "7. Vínculo\n"
    )
    body = _section(text)
    # The real section (with the grape list) must be the one located.
    assert "Airén" in body and "Cencibel" in body


def test_stop_by_title_on_repeated_prefix():
    # los-cerrillos: the next section reuses prefix "6" ("6.- Vínculo"), so the
    # stop must be by post-variety title, not by a greater number.
    text = (
        "6.- Variedades de uva\n"
        "País, Moscatel.\n"
        "6.- Vínculo con la zona\n"
        "Suelos graníticos...\n"
    )
    body = _section(text)
    assert "País" in body and "Moscatel" in body
    assert "graníticos" not in body


def test_no_variety_section_returns_none():
    text = "1. Nombre\nDO Foo\n2. Descripción\nVino tinto.\n"
    assert find_variety_section(text) is None


# --------------------------------------------------------------------------
# _normalise_token — rejection rules (fire before the vocab matcher)
# --------------------------------------------------------------------------

def test_normalise_token_rejects_too_short():
    assert _normalise_token("ab", "") is None


def test_normalise_token_rejects_digits():
    assert _normalise_token("variedad 2024", "") is None


def test_normalise_token_rejects_too_many_words():
    assert _normalise_token("uno dos tres cuatro cinco seis", "") is None


def test_normalise_token_rejects_structural_noise():
    # Anything in the _DROP set (section boilerplate) must be rejected.
    from _lib.es.national_pliego import _DROP  # noqa: E402
    sample = next(iter(_DROP))
    assert _normalise_token(sample, "") is None
