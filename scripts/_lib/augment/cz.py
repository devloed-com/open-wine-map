"""CZ national-spec + CHZO augmentation (stage 04).

Moved verbatim out of 04_build_maps.py — no behaviour change. The shared
provenance caches + sidecar dir live in `_shared` (same objects as the
`_sources_for()` reader in stage 04). The CZ colour-block map and the
in-function grape-lexicon import move with the function.
"""
from __future__ import annotations

import json

from ._shared import _CZ_CHZO_BY_SLUG, _CZ_NATIONAL_SPEC_BY_SLUG, NATIONAL_SPECS_CZ

_COLOUR_FROM_CZ_BLOCK: dict[str, str] = {
    "blanc": "blanc",
    "noir": "noir",
    "zemske": "",  # mixed; let match_variety supply the per-variety colour
}


def augment_cz_records_with_national_specs(records: list[dict]) -> int:
    """In-place merge of the Czech national variety roster (Vyhláška
    č. 88/2017 Sb. Příloha č. 2) into every CZ wine record.

    Czech wine law publishes one national variety list (35 white + 26
    red + 6 zemské-víno = 67 varieties) that applies to every jakostní
    víno regardless of podoblast — no per-appellation restriction. So
    every CZ wine that *should* carry a variety list (10 of 13, all
    except 3 newer single-vineyard / single-varietal PDOs whose
    Vyhláška-88 status is undocumented) gets the same fold:

      - white-wine PDOs/PGIs → all 35 white varieties as `principal`
      - red-wine PDOs/PGIs → all 26 red varieties as `principal`
      - mixed (most macros + podoblasti) → both lists folded;
        zemské-víno-only varieties go under `accessory` (they apply
        only to the lower zemské-víno PGI tier).

    Since the Vyhláška doesn't enumerate a per-appellation principal/
    accessory split (it's a flat national authorisation), we mark
    everything `principal` and let the panel render "All Czech
    jakostní vína authorise these 67 varieties — see Vyhláška č.
    88/2017 Sb." in the provenance.

    Stage 04 reads the cached provenance later via
    `_CZ_NATIONAL_SPEC_BY_SLUG`.

    Returns the number of records augmented.
    """
    _CZ_NATIONAL_SPEC_BY_SLUG.clear()
    _CZ_CHZO_BY_SLUG.clear()
    if not NATIONAL_SPECS_CZ.exists():
        return 0

    # Load the two SZPI CHZO region specs (terroir source + style roster +
    # provenance), keyed by region. Both PGIs are the spec's own subject;
    # the macro CHOPs + podoblasti in that region share its section-1
    # terroir description (rendered by 02d) and cite the same SZPI PDF.
    chzo_by_region: dict[str, dict] = {}
    for key in ("chzo-moravske", "chzo-ceske"):
        p = NATIONAL_SPECS_CZ / f"{key}.json"
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if d.get("region"):
            chzo_by_region[d["region"]] = d
    # The 2 PGI slugs whose own product specification this is (they
    # inherit the spec's per-style roster; the CHOPs/podoblasti keep
    # grape-colour-inferred styles only).
    chzo_pgi_slugs = {"moravske", "ceske"}

    varieties_path = NATIONAL_SPECS_CZ / "varieties.json"
    manifest_path = NATIONAL_SPECS_CZ / "manifest.json"
    if not varieties_path.exists():
        return 0
    try:
        spec = json.loads(varieties_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return 0
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    except (ValueError, OSError):
        manifest = {}
    src_meta = (manifest.get("sources") or {}).get("vyhlaska-88-2017") or {}

    # Build a slug → match details index for the lexicon match.
    from _lib.grape_entity import match_variety, set_pliego_context  # noqa: E402
    sidecar_details: list[dict] = []
    set_pliego_context("vyhlaska-88-2017")
    for v in spec.get("varieties") or []:
        m = match_variety(v.get("name") or "")
        if m is None:
            continue
        sidecar_details.append({
            "slug": m.slug,
            "name": v.get("name"),
            "role": "principal",
            "colour": m.colour or _COLOUR_FROM_CZ_BLOCK.get(v.get("colour", ""), ""),
            "source": "vyhlaska-88-2017",
        })
    set_pliego_context(None)

    provenance_base = {
        "url": src_meta.get("canonical_url") or src_meta.get("fetch_url") or "",
        "fetch_url": src_meta.get("fetch_url") or "",
        "title": src_meta.get("title") or "",
        "sbirka_castka": src_meta.get("sbirka_castka") or "",
        "sha256": src_meta.get("sha256") or "",
        "fetched_at": (src_meta.get("fetched_at") or "")
                       if isinstance(src_meta, dict) else "",
        "source_org": "sbirka",
        "license": "Czech law text per §3(d) of the Czech Copyright Act",
        "n_varieties": spec.get("n_total") or 0,
        "n_white": spec.get("n_white") or 0,
        "n_red": spec.get("n_red") or 0,
        "n_zemske": spec.get("n_zemske") or 0,
    }

    augmented = 0
    for record in records:
        if record.get("country") != "cz":
            continue
        slug = record.get("slug") or ""
        # Build the per-record details list. Start from the sidecar
        # (the national variety roster) since the EU-OJ extracted record
        # has no grapes (every CZ wine is a stub in v1). Folding by
        # role: everything `principal` because the Vyhláška doesn't
        # split.
        grapes = dict(record.get("grapes") or {})
        existing_slugs = {d.get("slug") for d in (grapes.get("details") or []) if d.get("slug")}
        new_details = list(grapes.get("details") or [])
        for d in sidecar_details:
            if d["slug"] in existing_slugs:
                continue
            existing_slugs.add(d["slug"])
            new_details.append(d)
        principal = [d["slug"] for d in new_details if d["slug"] and d.get("role") != "accessory"]
        accessory = [d["slug"] for d in new_details if d["slug"] and d.get("role") == "accessory"]
        # Dedup while preserving order.
        principal_seen: set[str] = set()
        principal_ordered = [s for s in principal if not (s in principal_seen or principal_seen.add(s))]
        accessory_seen: set[str] = set()
        accessory_ordered = [s for s in accessory if not (s in accessory_seen or accessory_seen.add(s))]
        grapes["principal"] = principal_ordered
        grapes["accessory"] = accessory_ordered
        grapes["details"] = new_details
        record["grapes"] = grapes
        # Czech wine law publishes no per-appellation wine-description
        # section, so styles can't be read from a spec the way HR/SI/BG
        # do. Infer the base colour styles from the authorised variety
        # roster instead (the BE colour-distribution fallback): a
        # blanc/gris variety authorises white, a noir variety authorises
        # red + rosé. Every CZ wine carries the national roster, so all
        # carry white/red/rosé — honest (any CZ jakostní víno appellation
        # may be made in any colour) and it makes CZ wines findable in the
        # style facet instead of invisible. The single straw-wine PDO
        # (Novosedelské Slámové víno) additionally carries vin-de-paille,
        # evident from its own name.
        colours = {d.get("colour") for d in new_details if d.get("colour")}
        styles = set(record.get("styles") or [])
        if colours & {"blanc", "gris"}:
            styles.add("white")
        if "noir" in colours:
            styles.add("red")
            styles.add("rose")
        if slug == "novosedelske-slamove-vino":
            styles.add("vin-de-paille")
        # The 2 PGIs ("zemské víno") additionally carry the real style
        # roster from their SZPI CHZO spec section 2 (sparkling /
        # semi-sparkling / vin-de-liqueur on top of the colour bases).
        chzo = chzo_by_region.get(record.get("region") or "")
        if chzo and slug in chzo_pgi_slugs:
            styles |= set(chzo.get("styles") or [])
        record["styles"] = sorted(styles)
        # All CZ wines cite the region's CHZO spec as their terroir
        # source (02d grounds on its section-1 region description), so
        # surface its provenance uniformly for the panel source block.
        if chzo:
            chzo_prov = {
                "url": chzo.get("source_url") or "",
                "title": chzo.get("source_title") or "",
                "region": chzo.get("region") or "",
                "source_org": chzo.get("source_org") or "szpi",
                "sha256": chzo.get("source_sha256") or "",
                "parser_template": chzo.get("parser_template") or "",
            }
            record["chzo_spec"] = chzo_prov
            _CZ_CHZO_BY_SLUG[slug] = chzo_prov
        record["national_spec"] = provenance_base
        _CZ_NATIONAL_SPEC_BY_SLUG[slug] = provenance_base
        augmented += 1
    return augmented


# CZ variety-block colour → grape-entity colour mapping. The Vyhláška
# 88/2017 block headers are "Bílé moštové odrůdy" (blanc) / "Modré
# moštové odrůdy" (noir) / "Odrůdy pro výrobu zemských vín" (mixed
# colours, kept as `zemske` here — falls back via match_variety()).
