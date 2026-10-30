"""The eAmbrosia list writes `productType` as it likes: "WINE" until October
2026, "Wine" from then on. A stage 00 that compared it case-sensitively would
write an empty index for its country, and the next stage 02 would empty the
corpus; the freshness probe called all 149 Spanish GIs GONE (2026-10-30)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# `.get("productType") == "WINE"`, `["productType"] != "WINE"`,
# `(r.get("productType") or "") != "WINE"` — any read of the field compared
# with the capitalised literal
_CASE_SENSITIVE = re.compile(
    r"""productType["'][\])](?:\s*or\s*["']{2}\s*\))?\s*[!=]=\s*["']WINE["']""")


def test_no_case_sensitive_product_type_comparison():
    offenders = [
        f"{p.relative_to(ROOT)}:{n}"
        for p in sorted((ROOT / "scripts").rglob("*.py"))
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if "productType" in line and _CASE_SENSITIVE.search(line) and ".upper()" not in line
    ]
    assert not offenders, offenders


def test_every_eambrosia_stage00_filters_on_product_type():
    stage00 = sorted((ROOT / "scripts").glob("*/00_fetch_data.py"))
    filtering = [p for p in stage00 if '.upper() == "WINE"' in p.read_text(encoding="utf-8")]
    assert len(filtering) >= 18, [str(p.relative_to(ROOT)) for p in filtering]


def test_lint_regex_catches_every_comparison_form():
    for line in ('if g.get("productType") == "WINE":', 'if row["productType"] != "WINE":',
                 'if (r.get("productType") or "") != "WINE":', "x = g['productType'] == 'WINE'"):
        assert _CASE_SENSITIVE.search(line), line
    assert not _CASE_SENSITIVE.search('if (g.get("productType") or "").upper() == "WINE":')
