"""Regenerate the manual_overrides.json template for PT wines whose
caderno PDF is not auto-discovered from the IVV master indexes.

Reads:
  raw/pt/eambrosia/index.json       — full PT wine list
  raw/pt/ivv/cadernos/manifest.json — stage 01 fetch outcomes per wine

Writes:
  raw/pt/ivv/cadernos/manual_overrides.json — one entry per wine that
  needs curation, with `pdf_url` and `verification_note` fields. Entries
  with non-empty `pdf_url` from a previous run are preserved.

Use:
  .venv/bin/python scripts/pt/regen_manual_overrides_template.py
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EAMBROSIA_INDEX = ROOT / "raw" / "pt" / "eambrosia" / "index.json"
CADERNOS_MANIFEST = ROOT / "raw" / "pt" / "ivv" / "cadernos" / "manifest.json"
OVERRIDES_PATH = ROOT / "raw" / "pt" / "ivv" / "cadernos" / "manual_overrides.json"


def main() -> int:
    if not EAMBROSIA_INDEX.exists():
        print(
            f"error: {EAMBROSIA_INDEX} missing — run scripts/pt/00_fetch_data.py first",
            file=sys.stderr,
        )
        return 1
    data = json.loads(EAMBROSIA_INDEX.read_text(encoding="utf-8"))
    manifest = (
        json.loads(CADERNOS_MANIFEST.read_text(encoding="utf-8")).get("by_slug", {})
        if CADERNOS_MANIFEST.exists()
        else {}
    )

    needs = []
    for w in data["wines"]:
        status = manifest.get(w["slug"], {}).get("status", "unknown")
        if status == "ok":
            continue
        needs.append((w, status))
    needs.sort(key=lambda kv: (kv[0]["kind"] != "DOP", kv[0]["name"].lower()))

    out: OrderedDict = OrderedDict()
    out["__doc__"] = (
        "Curator-filled overrides for PT wines whose caderno de "
        "especificações PDF is not auto-discovered from the IVV master "
        "indexes (np4/8617.html for DOP, np4/8616.html for IGP). Fill "
        "the `pdf_url` field for each entry to point at a public, "
        "licence-clear caderno PDF (IVV alternate path, BOE-style "
        "national gazette PDF, consejo regulador, etc.). Stage 01 reads "
        "this file before falling back to the auto-matched IVV URL. "
        "Re-run scripts/pt/01_fetch_cadernos.py after editing. Entries "
        "with empty pdf_url are ignored."
    )
    for w, status in needs:
        out[w["slug"]] = OrderedDict(
            [
                ("pdf_url", ""),
                ("source_org", ""),
                ("verification_note", ""),
                ("name", w["name"]),
                ("file_number", w["fileNumber"]),
                ("kind", w["kind"]),
                ("eu_protect_date", (w.get("eu_protection_date") or "")[:10]),
                ("status", status),
            ]
        )

    n_preserved = 0
    if OVERRIDES_PATH.exists():
        existing = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        for slug, entry in out.items():
            if slug == "__doc__":
                continue
            ex = existing.get(slug)
            if ex and ex.get("pdf_url"):
                entry["pdf_url"] = ex["pdf_url"]
                if ex.get("source_org"):
                    entry["source_org"] = ex["source_org"]
                if ex.get("verification_note"):
                    entry["verification_note"] = ex["verification_note"]
                n_preserved += 1

    OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDES_PATH.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    n_dop = sum(1 for w, _ in needs if w["kind"] == "DOP")
    n_igp = sum(1 for w, _ in needs if w["kind"] == "IGP")
    print(
        f"[overrides] wrote {OVERRIDES_PATH.relative_to(ROOT)} "
        f"with {len(needs)} entries (DOP={n_dop}, IGP={n_igp}); "
        f"preserved {n_preserved} curator-filled URLs",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
