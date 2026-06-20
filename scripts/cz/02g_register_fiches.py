"""Stage 02g (cz): fetch + extract the EU-register **fiche technique** (the
official EU single document) for every CZ wine.

Czech wine law publishes no per-appellation CHOP terroir narrative — today
CZ terroir comes from the two shared-region SZPI CHZO specs (same text for
all 9 Morava + 4 Čechy wines). The eAmbrosia register, however, hosts a
**per-DOP** fiche technique whose `I. JEDINÝ DOKLAD` block carries a per-DOP
link-to-terroir (§7 Popis souvislosti) + a per-DOP principal-variety list
(§6 Hlavní moštové odrůdy) — richer + differentiated.

This stage resolves each wine's `singleDocTechFile` attachment via
`scripts/_lib/eambrosia_register.py`, downloads the PDF, parses the
`I. JEDINÝ DOKLAD` block with the shared `parse_fiche_sections`, and writes
one sidecar per wine under `raw/cz/register-fiches-extracted/`. Stage 04's
`augment_cz_records_with_national_specs` prefers this per-DOP terroir +
varieties over the shared-region CHZO text; cz/02d grounds on it.

Re-runnable: cached PDFs at `raw/cz/register-fiches/<slug>.pdf` are reused
unless `--refresh`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib import eambrosia_register as er  # noqa: E402
from _lib.cz.jednotny_dokument import SECTION_ROLE_KEYWORDS  # noqa: E402
from _lib.fiche_technique import parse_fiche_sections  # noqa: E402
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue,
    match_variety,
    set_pliego_context,
)

INDEX_IN = ROOT / "raw" / "cz" / "eambrosia" / "index.json"
PDF_DIR = ROOT / "raw" / "cz" / "register-fiches"
OUT_DIR = ROOT / "raw" / "cz" / "register-fiches-extracted"
INDEX_OUT = OUT_DIR / "_index.json"

# The fiche's single-document block heading (Czech) + the trailing "other
# information" heading that ends it. Tolerate the OJ-template synonyms too.
ANCHOR_TERMS = ("JEDINÝ DOKLAD", "JEDNOTNÝ DOKUMENT", "JEDNOTNÝ DOKLAD")
END_TERMS = ("DALŠÍ INFORMACE",)

_PAREN_RE = re.compile(r"\s*\(.*?\)\s*")


def _pdftotext(pdf: Path) -> str:
    import subprocess
    try:
        r = subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"],
            capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    return r.stdout or ""


def _route(sections: dict[str, str], titles: dict[str, str]) -> dict[str, str]:
    routed: dict[str, str] = {}
    for role, kws in SECTION_ROLE_KEYWORDS.items():
        for kw in kws:
            hit = next((n for n, t in titles.items() if kw in t.lower()), None)
            if hit is not None:
                routed[role] = sections.get(hit, "")
                break
    return routed


def _parse_grapes(section_text: str) -> dict:
    """The §6 list is one variety per line: `Czech name (syn. …)`."""
    out: dict[str, list] = {"principal": [], "accessory": [], "observation": [], "details": []}
    seen: set[str] = set()
    for line in (section_text or "").splitlines():
        cand = _PAREN_RE.sub(" ", line).strip(" .,;\t")
        if len(cand) < 3:
            continue
        m = match_variety(cand)
        if m is None or m.slug in seen:
            continue
        seen.add(m.slug)
        out["principal"].append(m.slug)
        out["details"].append(
            {"slug": m.slug, "name": cand, "role": "principal", "colour": m.colour}
        )
    return out


def _summary(text: str, max_chars: int = 600) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[:max_chars].rsplit(". ", 1)[0] + "."


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="process every CZ wine")
    ap.add_argument("--only", action="append", default=[], help="slug substring (repeatable)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch cached PDFs")
    args = ap.parse_args()

    wines = json.loads(INDEX_IN.read_text(encoding="utf-8"))["wines"]
    if args.only:
        needles = [s.lower() for s in args.only]
        wines = [w for w in wines if any(n in w["slug"].lower() for n in needles)]
    elif not args.all:
        print("pass --all or --only <slug>", file=sys.stderr)
        return 2

    session = requests.Session()
    id_map = er.load_id_map(session=session)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    index: dict[str, dict] = {}
    n_ok = n_grapes = n_terroir = n_miss = 0
    for w in tqdm(wines, desc="cz-register-fiches", leave=False):
        slug = w["slug"]
        set_pliego_context(slug)
        refs = er.attachment_refs(w["fileNumber"], id_map, session=session)
        uri = refs.get("single_doc_uri") if refs else None
        if not uri:
            n_miss += 1
            continue
        pdf = PDF_DIR / f"{slug}.pdf"
        if args.refresh or not pdf.exists():
            if not er.fetch_attachment(uri, pdf, session=session):
                print(f"[warn] fetch failed: {slug} (uri {uri})", file=sys.stderr)
                n_miss += 1
                continue
        text = _pdftotext(pdf)
        sections, titles = parse_fiche_sections(text, ANCHOR_TERMS, END_TERMS)
        if not sections:
            print(f"[warn] no I.-block sections: {slug}", file=sys.stderr)
            n_miss += 1
            continue
        routed = _route(sections, titles)
        grapes = _parse_grapes(routed.get("grape_varieties", ""))
        link = routed.get("link_to_terroir", "")
        sidecar = {
            "country": "cz",
            "slug": slug,
            "name": w["name"],
            "file_number": w["fileNumber"],
            "summary": _summary(routed.get("description") or routed.get("geo_area") or ""),
            "grapes": grapes,
            "geo_area": routed.get("geo_area", ""),
            "link_to_terroir": link,
            "section_titles": titles,
            "source": {
                "kind": "eambrosia-register-fiche",
                "attachment_uri": uri,
                "ref": refs.get("single_doc_ref"),
                "url": er.ATTACHMENT_URL.format(uri=uri),
                "parser_template": "eu-fiche-technique-v1",
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        }
        (OUT_DIR / f"{slug}.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        index[slug] = {
            "slug": slug, "file_number": w["fileNumber"],
            "n_grapes": len(grapes["principal"]),
            "terroir_chars": len(link),
        }
        n_ok += 1
        n_grapes += bool(grapes["principal"])
        n_terroir += bool(link)

    set_pliego_context(None)
    INDEX_OUT.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    n_unknown = flush_unknowns_queue(ROOT / "raw" / "cz" / "extraction-unknowns-register-fiches.json")
    print(
        f"[done] ok={n_ok} with_grapes={n_grapes} with_terroir={n_terroir} "
        f"miss={n_miss} unknown_varieties={n_unknown} → {OUT_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
