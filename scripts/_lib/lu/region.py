"""LU region facet — a single wine region.

Luxembourg's wine corpus consists of one PDO (Moselle Luxembourgeoise);
historically the IVV also distinguishes a small Sauer-valley extension
near Wasserbillig, but it shares the same AOP. There is therefore one
region facet in v1: "Moselle Luxembourgeoise" itself.

Same shape as `_lib/<country>/region.py` everywhere else, kept for
uniformity with the stage 04 region-resolver branch.
"""

from __future__ import annotations

REGIONS = (
    "Moselle Luxembourgeoise",
)

_REGION_BY_FILE_NUMBER: dict[str, str] = {
    "PDO-LU-A0452": "Moselle Luxembourgeoise",
}


def region_for_file_number(file_number: str) -> str:
    """Curated fallback region for a wine GI file_number, or '' if unknown."""
    return _REGION_BY_FILE_NUMBER.get(file_number or "", "")


def derive_region(record: dict, *_text_candidates: str) -> str:
    """Resolve the wine region for one record. There is only one in LU."""
    if record.get("region"):
        return record["region"]
    curated = region_for_file_number(record.get("file_number", ""))
    return curated or "Moselle Luxembourgeoise"
