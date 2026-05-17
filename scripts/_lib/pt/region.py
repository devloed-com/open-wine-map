"""Derive the PT wine region for each PT record.

Portugal organises wine production into ~12 regions ("Regiões
Vitivinícolas"). Each DOP/IGP and its sub-regiões belong to exactly
one region. There is no comparably clean machine-extractable field in
the caderno text (regions are an editorial / regulatory aggregation,
not a per-DOP attribute), so we use a curated slug → region map.

Region names match the conventional IVV nomenclature (Minho is the
geographic name; Vinho Verde IGP "Minho" sits inside it; the DOP Vinho
Verde sits inside it too).
"""

from __future__ import annotations

# slug → canonical PT wine region.
# Built by hand from the IVV master indexes + Wikipedia cross-check.
PT_REGION_BY_SLUG: dict[str, str] = {
    # Minho
    "vinho-verde": "Minho",
    "minho": "Minho",
    # Trás-os-Montes
    "tras-os-montes": "Trás-os-Montes",
    "transmontano": "Trás-os-Montes",
    # Douro/Porto
    "douro": "Douro/Porto",
    "porto": "Douro/Porto",
    "duriense": "Douro/Porto",
    # Bairrada / Beira Atlântico
    "bairrada": "Bairrada",
    "beira-atlantico": "Bairrada",
    # Dão / Terras do Dão
    "dao": "Dão",
    "lafoes": "Dão",
    "terras-do-dao": "Dão",
    # Beira Interior
    "beira-interior": "Beira Interior",
    "tavora-varosa": "Beira Interior",
    "terras-da-beira": "Beira Interior",
    "terras-de-cister": "Beira Interior",
    # Lisboa
    "alenquer": "Lisboa",
    "arruda": "Lisboa",
    "bucelas": "Lisboa",
    "carcavelos": "Lisboa",
    "colares": "Lisboa",
    "encostas-d-aire": "Lisboa",
    "obidos": "Lisboa",
    "torres-vedras": "Lisboa",
    "lisboa": "Lisboa",
    # Tejo
    "do-tejo": "Tejo",
    "dotejo": "Tejo",
    "tejo": "Tejo",
    # Península de Setúbal
    "palmela": "Setúbal",
    "setubal": "Setúbal",
    "peninsula-de-setubal": "Setúbal",
    # Alentejo
    "alentejo": "Alentejo",
    "alentejano": "Alentejo",
    # Algarve
    "lagoa": "Algarve",
    "lagos": "Algarve",
    "portimao": "Algarve",
    "tavira": "Algarve",
    "algarve": "Algarve",
    # Madeira
    "madeira": "Madeira",
    "madeirense": "Madeira",
    "terras-madeirenses": "Madeira",
    # Açores
    "biscoitos": "Açores",
    "graciosa": "Açores",
    "pico": "Açores",
    "acores": "Açores",
}


def derive_region(record: dict) -> str:
    """Look up the PT wine region for a record. Sub-denominations
    inherit from their parent slug. Returns 'Portugal' as a placeholder
    for any unmapped slug so the sidebar still has a region group."""
    slug = record.get("slug") or ""
    if record.get("is_sub_denomination"):
        parent = record.get("parent_slug") or ""
        if parent and parent in PT_REGION_BY_SLUG:
            return PT_REGION_BY_SLUG[parent]
    if slug in PT_REGION_BY_SLUG:
        return PT_REGION_BY_SLUG[slug]
    # Sub-denomination slug = "<parent>-<sub>"; try the parent prefix.
    if "-" in slug:
        for cut in range(slug.rfind("-"), 0, -1):
            cand = slug[:cut]
            if cand in PT_REGION_BY_SLUG:
                return PT_REGION_BY_SLUG[cand]
    return "Portugal"
