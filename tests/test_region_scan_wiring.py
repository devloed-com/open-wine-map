"""Wiring lint: the region facet must never be derived from the terroir
narrative.

A lien names other regions freely — for contrast, or for a shared
geology — and a passing mention is not a location. ΠΓΕ Άγιο Όρος was
labelled Στερεά Ελλάδα because its lien compares Athos with "…η Αττική"
6 kB in, and the facet then became a 42,000 km² polygon (2026-09-23).
Every per-country `derive_region` scan reads the geo-area text and the
appellation name only — the IT `derive_regione` rule. This test fails the
moment a stage-02 script or the stage-04 region fill passes
`link_to_terroir` back in.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_STAGE02_CALL = re.compile(r"derive_region\((?:[^()]|\([^()]*\))*\)", re.S)
_STAGE04_CALL = re.compile(r"derive_\w+_region\((?:[^()]|\([^()]*\))*\)", re.S)


def test_no_stage02_region_scan_reads_the_terroir_narrative():
    offenders = []
    for path in sorted((ROOT / "scripts").glob("*/02_extract_*.py")):
        src = path.read_text(encoding="utf-8")
        for call in _STAGE02_CALL.findall(src):
            if "link_to_terroir" in call:
                offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == [], f"terroir narrative fed into the region scan: {offenders}"


def test_stage04_region_fill_does_not_read_the_terroir_narrative():
    src = (ROOT / "scripts" / "04_build_maps.py").read_text(encoding="utf-8")
    bad = [c for c in _STAGE04_CALL.findall(src) if "link_to_terroir" in c]
    assert bad == [], bad[:1]


def test_the_lint_itself_sees_the_calls():
    """Guard against the regex silently matching nothing."""
    src = (ROOT / "scripts" / "04_build_maps.py").read_text(encoding="utf-8")
    assert len(_STAGE04_CALL.findall(src)) >= 9
    n = sum(len(_STAGE02_CALL.findall(p.read_text(encoding="utf-8")))
            for p in (ROOT / "scripts").glob("*/02_extract_*.py"))
    assert n >= 10
