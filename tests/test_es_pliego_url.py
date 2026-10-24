"""es/02f's choice of the national-pliego URL in a single document's text."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "es02f", ROOT / "scripts" / "es" / "02f_extract_national_pliegos.py")
es02f = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(es02f)


def _record(text: str) -> dict:
    return {"sections": {}, "section_roles": {"additional_conditions": text}}


def test_the_link_labelled_as_the_pliego_wins_over_the_first_pdf():
    # Condado de Huelva, OJ C/2026/4233: the first PDF is a map of its pagos.
    text = ("… Unciales. Puede verse su ubicación en: https://docondadodehuelva.es/wp-content/"
            "uploads/2026/02/pagos.pdf En los vinos elaborados … Referencia electrónica (URL) a la "
            "publicación del pliego de condiciones https://juntadeandalucia.es/sites/default/files/"
            "inline-files/2026/03/PC_Condado_modificado_6.pdf ( 1 ) Reglamento …")
    assert es02f.find_pliego_url(_record(text)).endswith("PC_Condado_modificado_6.pdf")


def test_a_labelled_landing_page_falls_back_to_the_first_pdf():
    text = ("Pliego de condiciones: https://lajunta.es/6eno9 — véase también "
            "https://example.org/pliego.pdf")
    assert es02f.find_pliego_url(_record(text)) == "https://example.org/pliego.pdf"


def test_no_pdf_no_url():
    assert es02f.find_pliego_url(_record("Pliego de condiciones: https://lajunta.es/6eno9")) is None


def test_a_moved_regional_host_is_rewritten():
    old = ("http://pagina.jccm.es/agricul/paginas/comercial-industrial/consejos_new/pliegos/"
           "3_PLIEGO_DEHESA_CARRIZAL_20180628.pdf")
    assert es02f.relocate(old) == ("https://ficheroscomunes.castillalamancha.es/agricultura-dop/"
                                   "3_PLIEGO_DEHESA_CARRIZAL_20180628.pdf")
    assert es02f.relocate("https://agacal.xunta.gal/x.pdf") == "https://agacal.xunta.gal/x.pdf"
