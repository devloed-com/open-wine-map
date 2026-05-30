"""Extract the Croatian national specifikacija proizvoda for each HR
content-stub. Sibling of stage 02 — covers the 16 grandfathered HR
wines whose EU-OJ JEDINSTVENI DOKUMENT was never published.

Pipeline stage 02f (hr). Modelled on `scripts/si/02f_extract_specifikacije.py`
(SI MKGP .doc) and the ES MAPA / IT MASAF / DE BLE national-spec
pattern: pulls the regulator's canonical product specification from
the Ministarstvo poljoprivrede (poljoprivreda.gov.hr) and writes one
sidecar JSON that stage 04's `augment_hr_records_with_specifikacija()`
merges into each in-memory stub record.

Reads:
  raw/hr/specifikacije/<slug>.{doc,docx,pdf,html}   (fetched by stage 01c)
  raw/hr/specifikacije/manifest.json
  raw/hr/specifikacije/manual_overrides.json        (slug → url mapping)

Writes:
  raw/hr/specifikacije-extracted/<slug>.json        (sidecar)
  raw/hr/specifikacije-extracted/_index.json
  raw/hr/specifikacije-extracted/manifest.json

Format branches (three):
  - `.doc`  (14 wines) — antiword via Docker `owm-antiword` image
  - `.docx` (Primorska Hrvatska) — stdlib zip → word/document.xml
  - `.pdf`  (Dingač) — `pdftotext -layout`
All three feed `_lib.hr.specifikacija.parse_specifikacija`.

The `.doc` conversion shells out to a Docker image built from
`scripts/si/Dockerfile.doc-converter` (debian:bookworm-slim + antiword,
shared with the SI pipeline). Build once with:
  docker build -t owm-antiword:latest -f scripts/si/Dockerfile.doc-converter scripts/si/

Re-runnable per slug or sweep:
  .venv/bin/python scripts/hr/02f_extract_specifikacije.py --slug dingac
  .venv/bin/python scripts/hr/02f_extract_specifikacije.py --all
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.hr.specifikacija import parse_specifikacija  # noqa: E402
from _lib.grape_entity import flush_unknowns_queue, set_pliego_context  # noqa: E402

OVERRIDES_PATH = ROOT / "raw" / "hr" / "specifikacije" / "manual_overrides.json"
SPECS_DIR = ROOT / "raw" / "hr" / "specifikacije"
SPECS_MANIFEST = SPECS_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "hr" / "specifikacije-extracted"
OUT_INDEX = OUT_DIR / "_index.json"
OUT_MANIFEST = OUT_DIR / "manifest.json"
UNKNOWNS = ROOT / "raw" / "hr" / "extraction-unknowns-specifikacije.json"
DOCKER_IMAGE = "owm-antiword:latest"


def antiword_to_text(doc_path: Path) -> str:
    """Convert a Word 97-2003 .doc to UTF-8 text via the antiword Docker
    image (shared with SI). `-w 0` keeps paragraphs intact; `-m UTF-8.txt`
    preserves Croatian diacritics."""
    abs_dir = str(doc_path.parent.resolve())
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "-v", f"{abs_dir}:/data:ro", DOCKER_IMAGE,
             "-w", "0", "-m", "UTF-8.txt", f"/data/{doc_path.name}"],
            capture_output=True, timeout=60, check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "docker not on PATH; install Docker Desktop or rebuild the antiword "
            f"image: docker build -t {DOCKER_IMAGE} "
            "-f scripts/si/Dockerfile.doc-converter scripts/si/"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"antiword timed out on {doc_path.name}") from exc
    if result.returncode != 0 and not result.stdout.strip():
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"antiword failed on {doc_path.name}: rc={result.returncode}\n{stderr[:400]}"
        )
    return result.stdout.decode("utf-8", errors="replace")


def docx_to_text(docx_path: Path) -> str:
    """Extract paragraph text from a .docx via stdlib zip + a light
    word/document.xml strip (reproducible — no external converter).

    The paragraph-properties block (`<w:pPr>…</w:pPr>`) is removed first
    so its tab/indent/font children can't leak into the captured run
    text, and any run that still contains markup is dropped as a
    mis-capture."""
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    out: list[str] = []
    for para in re.split(r"</w:p>", xml):
        para = re.sub(r"<w:pPr\b.*?</w:pPr>", "", para, flags=re.S)
        runs = re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, re.S)
        runs = [r for r in runs if "<w:" not in r]
        txt = html_lib.unescape("".join(runs)).strip()
        if txt:
            out.append(txt)
    return "\n".join(out)


def pdf_to_text(pdf_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, timeout=60, check=False,
    )
    if result.returncode != 0 and not result.stdout.strip():
        raise RuntimeError(f"pdftotext failed on {pdf_path.name}")
    return result.stdout.decode("utf-8", errors="replace")


def extract_text(spec_path: Path, fmt: str) -> str:
    if fmt == "doc":
        return antiword_to_text(spec_path)
    if fmt == "docx":
        return docx_to_text(spec_path)
    if fmt == "pdf":
        return pdf_to_text(spec_path)
    if fmt == "html":
        return spec_path.read_text(encoding="utf-8")
    raise RuntimeError(f"unsupported format: {fmt}")


def _sidecar_for(slug: str, parsed: dict, source: dict) -> dict:
    return {
        "country": "hr",
        "source_lang": "hr",
        "slug": slug,
        "summary": parsed.get("summary", ""),
        "grapes": parsed.get("grapes") or {},
        "geo_area_brief": parsed.get("geo_area_brief", ""),
        "link_to_terroir": parsed.get("link_to_terroir", ""),
        "section_roles": parsed.get("section_roles") or {},
        "section_titles": parsed.get("section_titles") or {},
        "styles": parsed.get("styles") or [],
        "n_sections": parsed.get("n_sections", 0),
        "parser_template": parsed.get("parser_template", ""),
        "source": source,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", help="single slug")
    ap.add_argument("--all", action="store_true", help="every slug with a cached spec")
    ap.add_argument("--only", action="append", default=[], help="slug substring (repeatable)")
    args = ap.parse_args()
    if not args.slug and not args.all and not args.only:
        ap.error("specify --slug SLUG, --only SUBSTR, or --all")

    if not OVERRIDES_PATH.exists():
        print(f"error: {OVERRIDES_PATH} missing", file=sys.stderr)
        return 1
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))

    fetch_manifest: dict[str, dict] = {}
    if SPECS_MANIFEST.exists():
        try:
            fetch_manifest = json.loads(
                SPECS_MANIFEST.read_text(encoding="utf-8")
            ).get("by_slug", {})
        except (ValueError, OSError):
            fetch_manifest = {}

    if args.slug:
        targets = [args.slug]
    elif args.only:
        needles = [s.lower() for s in args.only]
        targets = [s for s in overrides if not s.startswith("__")
                   and any(n in s.lower() for n in needles)]
    else:
        targets = [s for s in overrides if not s.startswith("__")
                   and (overrides[s].get("url") or "").startswith("http")]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    if OUT_INDEX.exists():
        try:
            index = json.loads(OUT_INDEX.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            index = {}

    n_ok = n_skipped = n_failed = 0
    for slug in tqdm(targets, desc="hr-specifikacije-extract", leave=False):
        set_pliego_context(slug)
        cached = [p for p in SPECS_DIR.glob(f"{slug}.*")
                  if p.suffix in {".doc", ".docx", ".pdf", ".html"}]
        if not cached:
            n_skipped += 1
            continue
        spec_path = cached[0]
        fmt = spec_path.suffix.lstrip(".")
        meta = fetch_manifest.get(slug, {})
        source = {
            "url": meta.get("source_url") or overrides.get(slug, {}).get("url", ""),
            "final_url": meta.get("final_url", ""),
            "format": fmt,
            "filename": spec_path.name,
            "sha256": meta.get("sha256") or hashlib.sha256(spec_path.read_bytes()).hexdigest(),
            "bytes": meta.get("bytes") or spec_path.stat().st_size,
            "fetched_at": meta.get("fetched_at", ""),
            "source_org": overrides.get(slug, {}).get("source_org", "mps"),
            "license": (
                "MPS product specification (Croatia, poljoprivreda.gov.hr) — "
                "public regulator material, reuse with attribution"
            ),
        }

        try:
            text = extract_text(spec_path, fmt)
            parsed = parse_specifikacija(text, slug)
        except Exception as exc:  # noqa: BLE001 — surface to manifest
            print(f"[err] {slug}: {exc}", file=sys.stderr)
            n_failed += 1
            continue

        sidecar = _sidecar_for(slug, parsed, source)
        (OUT_DIR / f"{slug}.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
        index[slug] = {
            "filename": f"{slug}.json",
            "parser_template": parsed.get("parser_template", ""),
            "n_principal": len(parsed.get("grapes", {}).get("principal") or []),
            "n_sections": parsed.get("n_sections", 0),
            "summary_chars": len(parsed.get("summary") or ""),
            "terroir_chars": len((parsed.get("link_to_terroir") or "")),
            "has_terroir": len((parsed.get("link_to_terroir") or "").strip()) >= 200,
        }
        n_ok += 1

    set_pliego_context(None)
    OUT_INDEX.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    OUT_MANIFEST.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license_summary": (
            "MPS product specifications (poljoprivreda.gov.hr): public regulator "
            "material, reuse with attribution."
        ),
        "counts": {"ok": n_ok, "skipped_no_spec": n_skipped, "failed": n_failed,
                   "total_in_index": len(index)},
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    n_unknowns = flush_unknowns_queue(UNKNOWNS)
    if n_unknowns:
        print(f"[entity] {n_unknowns} unknown variety candidates → "
              f"{UNKNOWNS.relative_to(ROOT)}", file=sys.stderr)
    print(f"[done] ok={n_ok} skipped={n_skipped} failed={n_failed} "
          f"→ {OUT_DIR.relative_to(ROOT)}", file=sys.stderr)
    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
