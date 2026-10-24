"""The national pliego's §7 vínculo reader (scripts/_lib/es/national_pliego.py,
2026-10-24): the heading forms the 60 cached PDFs use, the body's end at the
next top-level section or a post-link title (never a lettered sub-item of a
numbered section), the page furniture dropped, the change-log line of a
revision table never taken, and `is_summary_link` — the test ES 02d and the
stage-04 augmenter apply before preferring the pliego's text.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.es.national_pliego import (  # noqa: E402
    SUMMARY_LINK_MAX_CHARS,
    find_link_section,
    is_summary_link,
    parse_link_section,
)

BODY = ("La zona posee un microclima particular, mediterráneo templado húmedo, con una "
        "orografía en ladera y suelos de pizarra que condicionan la maduración de la uva. ") * 4

PLIEGO = f"""6. VARIEDADES DE UVAS DE VINIFICACIÓN

- Tintas: Rufete, Garnacha tinta.

7. VÍNCULO CON LA ZONA GEOGRÁFICA.

a) Datos de la zona geográfica.

A) Factores naturales.
{BODY}
                                   12
PLIEGO DE CONDICIONES D.O.P. «Sierra de Salamanca», 4 de marzo de 2019
b) Datos del producto.
{BODY}
8. REQUISITOS APLICABLES

Normativa nacional.
"""


def test_the_vinculo_section_runs_to_the_next_numbered_heading():
    r = parse_link_section(PLIEGO)
    assert r["found"] and r["heading"] == "7. VÍNCULO CON LA ZONA GEOGRÁFICA."
    assert r["text"].startswith("a) Datos de la zona geográfica.")
    assert "A) Factores naturales." in r["text"]      # a lettered sub-item never ends it
    assert "b) Datos del producto." in r["text"]
    assert "REQUISITOS" not in r["text"]
    assert "PLIEGO DE CONDICIONES" not in r["text"]   # the running header
    assert "\n12\n" not in r["text"]                  # the page number


def test_heading_forms():
    for head in ("7) VÍNCULO CON LA ZONA GEOGRÁFICA.", "7.- Vínculo con la zona geográfica.",
                 "7 VINCULO CON LA ZONA GEOGRAFICA.", "7. Vínculo", "7. Vínculo.",
                 "7. Vínculo con el medio", "7.-VÍNCULO CON LA ZONA GEOGRÁFICA",
                 "6.- Vínculo existente entre la calidad y características del vino con el entorno"):
        text = f"6. VARIEDADES\n\n- Tintas: Rufete.\n\n{head}\n\n{BODY}\n\n8. REQUISITOS\n"
        assert parse_link_section(text)["found"], head


def test_a_lettered_section_ends_at_the_next_letter():
    text = f"F. VARIEDADES\n\n- Tintas: Rufete.\n\nG. VÍNCULO ENTRE LA ZONA GEOGRÁFICA Y LA CALIDAD DE LOS VINOS.\n\nG.1. Vínculo a través de los factores humanos.\n{BODY}\nH. REQUISITOS APLICABLES\n\nNormativa.\n"
    r = parse_link_section(text)
    assert r["found"] and r["heading"].startswith("G. VÍNCULO")
    assert "G.1." in r["text"] and "REQUISITOS" not in r["text"]


def test_a_change_log_line_is_not_the_heading():
    text = (f"Revisión 7) Vínculo: revisión de su redacción para\n\n6. VARIEDADES\n\n- Tintas: Rufete.\n\n"
            f"7. VÍNCULO CON LA ZONA GEOGRÁFICA.\n\n{BODY}\n\n8. REQUISITOS\n")
    r = parse_link_section(text)
    assert r["found"] and r["heading"] == "7. VÍNCULO CON LA ZONA GEOGRÁFICA."


def test_toc_lines_and_sub_headings_are_skipped():
    text = (f"7. Vínculo con la zona geográfica ........ 14\n\n6. VARIEDADES\n\n- Tintas: Rufete.\n\n"
            f"7. VÍNCULO CON LA REGIÓN GEOGRÁFICA\n\n7.3. Vínculo con los productos protegidos\n{BODY}\n\n8. REQUISITOS\n")
    r = parse_link_section(text)
    assert r["found"] and r["heading"] == "7. VÍNCULO CON LA REGIÓN GEOGRÁFICA"
    assert "7.3. Vínculo" in r["text"]


def test_no_heading_no_section():
    assert find_link_section("6. VARIEDADES\n\n- Tintas: Rufete.\n") is None
    assert parse_link_section("texto sin vínculo")["found"] is False


def test_is_summary_link():
    assert is_summary_link("")
    assert is_summary_link("Categoría de producto vitivinícola 1. Vino Resumen del vínculo La zona …" + "x" * 1200)
    assert is_summary_link("x" * (SUMMARY_LINK_MAX_CHARS - 1))
    assert not is_summary_link("La zona geográfica " * 100)
