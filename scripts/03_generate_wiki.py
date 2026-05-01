"""Generate the wiki — one markdown page per appellation, plus an index.

Pipeline stage 03.

Reads the JSON files written by stage 02 (`raw/inao/cahier-extracted/*.json`)
and renders one `wiki/<slug>.md` per appellation following the page format
in CLAUDE.md (frontmatter + summary + sections + sources).

Also writes:
- `wiki/_index.json` — slug → metadata, used by stage 04 and for [[wiki-link]]
  resolution by the map UI
- `wiki/index.md` — alphabetical list of all appellations with their region
- `wiki/log.md` — generation timestamp and counts

Concept pages under `wiki/concepts/` are hand-authored and not touched.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
INDEX_IN = EXTRACTED / "_index.json"
WIKI = ROOT / "wiki"
WIKI_INDEX = WIKI / "_index.json"


def fmt_communes(by_dept: dict[str, list[str]]) -> str:
    """Render a {dept: [commune, ...]} dict as a département-grouped list."""
    if not by_dept:
        return "_Non renseigné dans le cahier des charges parsé._"
    lines: list[str] = []
    for dept, communes in sorted(by_dept.items()):
        lines.append(f"**{dept}** ({len(communes)}) — " + ", ".join(communes))
    return "\n\n".join(lines)


def truncate_paragraph(text: str, max_chars: int = 600) -> str:
    """Trim long verbatim text to a few sentences for the summary slot."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def first_paragraph(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    parts = re.split(r"\n\s*\n", text, maxsplit=1)
    return re.sub(r"\s+", " ", parts[0]).strip()


STYLE_LABELS = {
    "red": "rouge",
    "white": "blanc",
    "rose": "rosé",
    "sparkling": "mousseux / effervescent",
    "tranquille": "tranquille",
    "sweet": "moelleux / liquoreux",
    "dry": "sec",
    "vdn": "vin doux naturel",
    "vin-de-liqueur": "vin de liqueur",
    "vin-jaune": "vin jaune",
    "vin-de-paille": "vin de paille",
    "vendanges-tardives": "vendanges tardives",
    "grains-nobles": "sélection de grains nobles",
    "primeur": "primeur",
    "clairet": "clairet",
    "cremant": "crémant",
}


def _grape_link(slug_str: str, name: str) -> str:
    return f"[[{slug_str}|{name}]]"


def render_grapes_block(grapes: dict) -> str:
    """Format the structured grapes dict as a clean per-role list."""
    if not grapes or not grapes.get("details"):
        return "_(non extrait — voir le cahier des charges pour la liste complète)_"
    by_slug = {t["slug"]: t for t in grapes["details"]}
    lines: list[str] = []
    for role, label in [
        ("principal", "Principaux"),
        ("accessory", "Accessoires"),
        ("observation", "Variétés d'intérêt à fin d'adaptation"),
    ]:
        slugs = grapes.get(role) or []
        if not slugs:
            continue
        items: list[str] = []
        for s in slugs:
            t = by_slug.get(s, {"name": s})
            items.append(_grape_link(s, t.get("name", s).title()))
        lines.append(f"**{label}** — " + ", ".join(items))
    return "\n\n".join(lines) if lines else "_(aucun cépage détecté)_"


def render_styles_block(styles: list[str], categories: list[str]) -> str:
    if not styles and not categories:
        return "_(non extrait)_"
    chips: list[str] = []
    for s in styles:
        chips.append(f"`{STYLE_LABELS.get(s, s)}`")
    cat_line = (", ".join(categories)) if categories else ""
    out: list[str] = []
    if chips:
        out.append("**Styles détectés** — " + " ".join(chips))
    if cat_line:
        out.append(f"**Catégories INAO** — {cat_line}")
    return "\n\n".join(out)


def render_page(record: dict) -> str:
    name = record["name"]
    slug = record["slug"]
    sections = record.get("sections", {})
    aire_geo = record["aire"]["aire_geographique"]
    aire_prox = record["aire"]["aire_proximite_immediate"]
    is_dgc = bool(record.get("is_dgc"))
    parent_slug = record.get("parent_slug") or ""
    parent_name = record.get("parent_name") or ""

    is_igp = record.get("kind") == "IGP"
    sec_type = ("AOC" if "AOC" in record.get("signe_fr", "") else None) or (
        "IGP" if "IGP" in (record.get("signe_ue", "") + record.get("signe_fr", "")) else "AOC/AOP"
    )

    if is_igp:
        first_text = sections.get("1", "") or sections.get("3", "")
    else:
        first_text = sections.get("I", "") + " " + sections.get("III", "")
    summary = truncate_paragraph(first_text)

    roles = record.get("section_roles") or {}
    cepages_text = roles.get("encepagement") or sections.get("V", "")
    rendements = "\n\n".join(filter(None, [
        ("**" + roman + ".**\n" + sections[roman].strip()) if sections.get(roman) else ""
        for roman in (("VI", "VII", "VIII", "IX") if not is_igp else ("6", "7"))
    ])) or "_(non extrait)_"
    styles_text = roles.get("couleur") or sections.get("III", "")
    lien = record.get("lien_au_terroir", "").strip() or "_(non extrait)_"

    grapes = record.get("grapes") or {}
    styles = record.get("styles") or []
    categories = record.get("categories") or []

    src = record["source"]
    cahier_relpath = f"raw/inao/cahiers/{src['filename']}"
    fetched_date = src["fetched_at"][:10]

    # YAML-friendly bracket lists for slugged fields. JSON's array syntax is
    # valid YAML, so this reads cleanly in any frontmatter parser.
    fm_lines = [
        "---",
        f"title: {name}",
        f"type: {sec_type.lower()}",
        f"slug: {slug}",
        f"region: {record.get('comite_regional') or ''}",
        f"signe_fr: {record.get('signe_fr') or ''}",
        f"signe_ue: {record.get('signe_ue') or ''}",
        f"categorie: {record.get('categorie') or ''}",
        f"categories: {json.dumps(categories, ensure_ascii=False)}",
        f"styles: {json.dumps(styles, ensure_ascii=False)}",
        f"grapes_principal: {json.dumps(grapes.get('principal') or [], ensure_ascii=False)}",
        f"grapes_accessory: {json.dumps(grapes.get('accessory') or [], ensure_ascii=False)}",
        f"grapes_observation: {json.dumps(grapes.get('observation') or [], ensure_ascii=False)}",
    ]
    if is_dgc:
        fm_lines += [
            "is_dgc: true",
            f"parent_slug: {parent_slug}",
            f"parent_name: {parent_name}",
        ]
    fm_lines += [
        "sources:",
        f"  cahier: {cahier_relpath}",
        f"  show_texte: {src['show_texte_url']}",
        f"  boagri: {src['boagri_url']}",
        f"  product: {src['product_url']}",
        f"  pdf_sha256: {src['pdf_sha256']}",
        f"last_updated: {fetched_date}",
        "---",
        "",
        f"# {name}",
        "",
    ]
    if is_dgc and parent_slug:
        fm_lines += [
            f"_Dénomination géographique complémentaire de [[{parent_slug}|{parent_name}]]._",
            "",
        ]

    body = [
        "## Summary",
        "",
        summary or "_(pas de résumé extrait)_",
        "",
        "## Aire géographique",
        "",
        fmt_communes(aire_geo),
        "",
    ]
    if aire_prox:
        body += [
            "## Aire de proximité immédiate",
            "",
            fmt_communes(aire_prox),
            "",
        ]
    body += [
        "## Styles et couleurs",
        "",
        render_styles_block(styles, categories),
        "",
        truncate_paragraph(styles_text, max_chars=1200) or "",
        "",
        "## Cépages",
        "",
        render_grapes_block(grapes),
        "",
        "_Texte du cahier (extrait):_",
        "",
        truncate_paragraph(cepages_text, max_chars=1200) or "_(non extrait)_",
        "",
        "## Rendements et conduite",
        "",
        rendements,
        "",
        "## Lien au terroir",
        "",
        lien,
        "",
        "## Sources",
        "",
        f"- Cahier des charges (PDF): [`{cahier_relpath}`]({cahier_relpath}) — sha256 `{src['pdf_sha256'][:16]}…`",
        f"- INAO show_texte: <{src['show_texte_url']}>",
        f"- BO Agri (PDF source): <{src['boagri_url']}>",
        f"- INAO produit (catalogue): <{src['product_url']}>",
        "",
    ]

    return "\n".join(fm_lines + body)


def render_index(records: list[dict]) -> str:
    by_region: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        region = r.get("comite_regional") or "Sans région"
        by_region[region].append(r)
    parents = sum(1 for r in records if not r.get("is_dgc"))
    dgcs = sum(1 for r in records if r.get("is_dgc"))
    lines = [
        "# open wine map — index des appellations",
        "",
        f"_{parents} appellations + {dgcs} dénominations géographiques complémentaires "
        "générées depuis les cahiers des charges INAO._",
        "",
    ]
    for region in sorted(by_region):
        lines.append(f"## {region}")
        lines.append("")
        # Group DGCs under their parent. Order: parents alphabetically, with
        # any DGCs listed (also alphabetically) immediately under each.
        region_records = by_region[region]
        children_by_parent: dict[str, list[dict]] = defaultdict(list)
        parents_in_region: list[dict] = []
        for r in region_records:
            if r.get("is_dgc") and r.get("parent_slug"):
                children_by_parent[r["parent_slug"]].append(r)
            else:
                parents_in_region.append(r)
        for r in sorted(parents_in_region, key=lambda x: x["name"].lower()):
            n_geo = sum(len(v) for v in r["aire"]["aire_geographique"].values())
            kind = r.get("kind", "AOC")
            lines.append(
                f"- [[{r['slug']}|{r['name']}]] — {kind}, {n_geo} commune(s) en aire géographique"
            )
            for child in sorted(children_by_parent.get(r["slug"], []), key=lambda x: x["name"].lower()):
                lines.append(f"  - [[{child['slug']}|{child['name']}]] — DGC")
        lines.append("")
    return "\n".join(lines)


def render_log(records: list[dict]) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    by_kind: dict[str, int] = defaultdict(int)
    for r in records:
        by_kind[r.get("kind", "AOC")] += 1
    lines = [
        "# Generation log",
        "",
        f"Generated at: {now}",
        "",
        f"- {len(records)} appellation pages",
    ]
    for kind, n in sorted(by_kind.items()):
        lines.append(f"  - {kind}: {n}")
    return "\n".join(lines) + "\n"


def main() -> int:
    if not INDEX_IN.exists():
        print(f"error: {INDEX_IN} missing — run scripts/02_extract_cahiers.py first", file=sys.stderr)
        return 1

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[])
    args = ap.parse_args()

    index = json.loads(INDEX_IN.read_text())
    items = sorted(index.items(), key=lambda kv: kv[1]["name"].lower())
    if args.only:
        needles = [s.lower() for s in args.only]
        items = [(k, v) for k, v in items if any(n in v["name"].lower() for n in needles)]

    WIKI.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    written = 0
    for _key, idx_entry in tqdm(items, desc="wiki", leave=False):
        path = EXTRACTED / idx_entry["filename"]
        record = json.loads(path.read_text())
        out = WIKI / f"{record['slug']}.md"
        out.write_text(render_page(record))
        records.append(record)
        written += 1

    wiki_idx = {
        r["slug"]: {
            "id_appellation": r["id_appellation"],
            "id_denomination_geo": r.get("id_denomination_geo") or "",
            "name": r["name"],
            "kind": r.get("kind", "AOC"),
            "region": r.get("comite_regional") or "",
            "is_dgc": bool(r.get("is_dgc")),
            "parent_slug": r.get("parent_slug") or "",
            "parent_name": r.get("parent_name") or "",
            "communes_count": sum(len(v) for v in r["aire"]["aire_geographique"].values()),
            "categories": r.get("categories") or [],
            "styles": r.get("styles") or [],
            "grapes_principal": (r.get("grapes") or {}).get("principal") or [],
            "grapes_accessory": (r.get("grapes") or {}).get("accessory") or [],
            "grapes_observation": (r.get("grapes") or {}).get("observation") or [],
            "page": f"{r['slug']}.md",
        }
        for r in records
    }
    WIKI_INDEX.write_text(json.dumps(wiki_idx, ensure_ascii=False, indent=2, sort_keys=True))

    (WIKI / "index.md").write_text(render_index(records))
    (WIKI / "log.md").write_text(render_log(records))

    print(f"[done] wrote {written} pages to {WIKI.relative_to(ROOT)}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
