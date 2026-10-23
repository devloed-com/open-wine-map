"""The § 6 roster of an EU-register fiche technique: which varieties are main.

The 2011 technical-file template splits § 6 into "a. <main varieties>",
"b. <varieties on the OIV list>", "c. <other varieties>". The newer template
tags each bulleted line "(MAIN)" / "(OIV)" / "(OTHER)", and the tag, not the
bullet, carries the role: Hungary writes "** Hárslevelű (MAIN)" beside
"* Kabar (OTHER)" (Tokaj), and a "** … (MAIN)" line had read as accessory.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "extract_register_fiches", ROOT / "scripts" / "extract_register_fiches.py")
fiches = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fiches)


def _roles(text: str) -> dict[str, str]:
    return {d["slug"]: d["role"] for d in fiches._parse_grapes(text)["details"]}


def test_tag_decides_whatever_the_bullet():
    roles = _roles(
        "      * Zéta (OTHER)\n"
        "      * Furmint (MAIN)\n"
        "    ** Hárslevelű (MAIN)\n"
        "    ** Sárgamuskotály (OTHER)\n"
    )
    assert roles["furmint"] == "principal"
    assert roles["harslevelu"] == "principal"
    assert roles["zeta"] == "accessory"
    assert roles["muscat-a-petits-grains"] == "accessory"


def test_oiv_tagged_variety_is_kept_and_the_oiv_heading_is_not():
    # Crișana lists its OIV-named varieties as "** Burgund Mare (OIV)"; the
    # stoplist word "oiv" is for the block heading, which carries no bullet
    roles = _roles(
        "  ** 10. Fetească neagră (MAIN)\n"
        "  ** Burgund Mare (OIV)\n"
        "      b. Винени сортове лози по списъка на Международната организация по лозарство и\n"
        "винарство (OIV)\n"
    )
    assert roles == {"feteasca-neagra": "principal", "blaufrankisch": "accessory"}


def test_2011_template_blocks():
    # Asenovgrad: Syrah and Rubin are listed under "c. Други сортове" only
    roles = _roles(
        "      a. Списък на основните винени сортове лози\n"
        "         11 Мавруд\n"
        "         03 Мерло\n"
        "      b. Винени сортове лози по списъка на Международната организация по лозарство и\n"
        "винарство (OIV)\n"
        "  c. Други сортове\n"
        "    Сира\n"
    )
    assert roles == {"mavrud": "principal", "merlot": "principal", "syrah": "accessory"}
