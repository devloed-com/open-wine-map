"""Regenerate the manual_overrides.json template for BG wines whose
single-document URL is not auto-discovered / not fetchable.

Reads:
  raw/bg/eambrosia/index.json — full BG wine list
  raw/bg/oj-pages/manifest.json — stage 01/01b fetch outcomes per wine

Writes:
  raw/bg/oj-pages/manual_overrides.json — one entry per wine that needs
  curation, with `url` and `note` fields the curator fills in. Entries
  with a non-empty `url` from a previous run are preserved.

Use:
  .venv/bin/python scripts/bg/regen_manual_overrides_template.py

~51 of the 54 Bulgarian wines are Art.107 / Reg.1308/2013 grandfathered
names with no fetchable single-document URL (only ~3 carry EUR-Lex
ЕДИНЕН ДОКУМЕНТ URLs). They dominate this queue. The curator fills
`url` with a public, licence-clear specification: preferred is a
Държавен вестник (https://dv.parliament.bg) PDF of the original
recognition Постановление/Заповед, fallback an IAVV (https://eavw.com)
PDO page if one exists, last-resort an EUR-Lex OJ-C amendment
publication. Phase 2 will add a national-spec parser branch — until
then, only EUR-Lex ЕДИНЕН ДОКУМЕНТ URLs promote a wine out of stub
state.

After filling URLs, re-run scripts/bg/01_fetch_pliegos.py →
02_extract_pliegos.py → stage 04.
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EAMBROSIA_INDEX = ROOT / "raw" / "bg" / "eambrosia" / "index.json"
OJ_MANIFEST = ROOT / "raw" / "bg" / "oj-pages" / "manifest.json"
OVERRIDES_PATH = ROOT / "raw" / "bg" / "oj-pages" / "manual_overrides.json"


def main() -> int:
    if not EAMBROSIA_INDEX.exists():
        print(f"error: {EAMBROSIA_INDEX} missing — run scripts/bg/00_fetch_data.py first",
              file=sys.stderr)
        return 1
    data = json.loads(EAMBROSIA_INDEX.read_text(encoding="utf-8"))
    oj = json.loads(OJ_MANIFEST.read_text(encoding="utf-8"))["by_slug"] if OJ_MANIFEST.exists() else {}

    needs = []
    for w in data["wines"]:
        status = oj.get(w["slug"], {}).get("status", "unknown")
        if status == "ok":
            continue
        needs.append((w, status))
    needs.sort(key=lambda kv: (kv[0]["kind"] != "DOP", kv[0]["name"].lower()))

    out: dict = OrderedDict()
    out["__doc__"] = (
        "Curator-filled overrides for BG wines whose single-document "
        "URL is not auto-discovered or not fetchable. Fill the `url` "
        "field for each entry to point at a public, licence-clear "
        "specification (EUR-Lex OJ-C page, or the Държавен вестник / "
        "IAVV national продуктова спецификация — Phase 2). Stage 01 "
        "reads this file before falling back to eAmbrosia publications. "
        "Re-run scripts/bg/01_fetch_pliegos.py after editing. Entries "
        "with empty url are ignored."
    )
    for w, status in needs:
        out[w["slug"]] = OrderedDict([
            ("url", ""),
            ("note", ""),
            ("name", w["name"]),
            ("file_number", w["fileNumber"]),
            ("kind", w["kind"]),
            ("eu_protect_date", (w.get("eu_protection_date") or "")[:10]),
            ("status", status),
        ])

    n_preserved = 0
    if OVERRIDES_PATH.exists():
        existing = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        for slug, entry in out.items():
            if slug == "__doc__":
                continue
            ex = existing.get(slug)
            if ex and ex.get("url"):
                entry["url"] = ex["url"]
                if ex.get("note"):
                    entry["note"] = ex["note"]
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
