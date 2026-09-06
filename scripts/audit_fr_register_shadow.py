"""Shadow-compare the eAmbrosia register cahier against the in-build FR record.

Read-only with respect to the build: fetches each appellation's register
cahier into `raw/inao/register/cahiers/`, extracts it with the *unchanged*
stage-02 parser in memory, and reports whether the result matches the record
already in `raw/inao/cahier-extracted/`. Nothing under `raw/inao/cahiers/`
or `raw/inao/cahier-extracted/` is written, so the comparison can be shipped
before any behaviour change.

Three columns per appellation:

* **build** — the record on disk today (BO Agri / curator URL / OCR mirror).
* **self** — re-extracting the build's own PDF right now. This is the
  determinism control: if `self` already differs from `build`, a `register`
  difference on the same appellation says nothing about the register.
* **register** — extracting the register attachment.

`lien_au_terroir` is the headline comparison (it is the largest verbatim
block the wiki renders), with section / commune / grape counts and the
homologation date alongside so a *vintage* difference is distinguishable
from a *parse* difference.

    .venv/bin/python scripts/audit_fr_register_shadow.py            # all 466
    .venv/bin/python scripts/audit_fr_register_shadow.py --only Chablis
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import signal
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import eambrosia_register as er  # noqa: E402
from _lib.fr import register_cahier as rc  # noqa: E402

m02 = importlib.import_module("02_extract_cahiers")

CAHIERS = ROOT / "raw" / "inao" / "cahiers"
MANIFEST_PATH = CAHIERS / "manifest.json"
EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
INDEX_PATH = EXTRACTED / "_index.json"
TEXT_CACHE = rc.REGISTER_DIR / ".text"
REPORT_JSON = rc.REGISTER_DIR / "shadow-report.json"
REPORT_MD = rc.REGISTER_DIR / "shadow-report.md"


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


_WS_RE = re.compile(r"\s+")


def _words(s: str) -> Counter:
    return Counter(_WS_RE.sub(" ", s).strip().split(" "))


def _similarity(a: str, b: str) -> float:
    """Word-multiset Dice coefficient — linear, so it survives the 340 KB
    Alsace-grand-cru bundle, and sensitive enough to separate a cosmetic
    delta (a guillemet space, `mélant` → `mêlant`) from a rewritten section."""
    wa, wb = _words(a), _words(b)
    total = sum(wa.values()) + sum(wb.values())
    if not total:
        return 1.0
    return 2 * sum((wa & wb).values()) / total


def _norm_sha(s: str) -> str:
    """Hash with all whitespace collapsed. Two PDFs of the same cahier laid
    out at different column widths wrap differently, so a byte comparison
    over-reports; this separates 'same text, different wrapping' from a real
    textual (vintage) difference."""
    return _sha(_WS_RE.sub(" ", s).strip())


def _pdftotext(pdf: Path) -> str:
    """`pdftotext -layout` with a cache next to the register PDFs. Deliberately
    NOT stage 02's cache, which lives inside the cahiers directory — the
    filenames are sha256 either way, so the two would otherwise share entries.

    An empty result is never cached: it means pdftotext failed or the PDF has
    no text layer, and freezing that would turn a transient problem into a
    permanent `register-extract-failed` verdict."""
    TEXT_CACHE.mkdir(parents=True, exist_ok=True)
    cached = TEXT_CACHE / f"{pdf.stem}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    proc = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    out = proc.stdout or ""
    if not out.strip():
        print(f"[warn] pdftotext produced nothing for {pdf.name} "
              f"(rc={proc.returncode}) — not cached", file=sys.stderr)
        return out
    cached.write_text(out, encoding="utf-8")
    return out


class _ExtractTimeout(Exception):
    pass


def _extract(name: str, text: str, limit: int) -> dict | None:
    """`extract_one` under a wall-clock guard.

    `extract_aire`'s department-header regex backtracks pathologically on some
    layouts — the register's JORF-issue attachment for Pouilly-Fumé takes
    minutes on a 2 KB area section (see CURATOR_TODO). That is a pre-existing
    extractor bug, not a register one, but an unguarded call lets a single
    document stall a 466-appellation sweep."""
    if limit <= 0:
        return m02.extract_one(name, text)

    def _fire(_sig, _frm):
        raise _ExtractTimeout

    previous = signal.signal(signal.SIGALRM, _fire)
    signal.alarm(limit)
    try:
        return m02.extract_one(name, text)
    except _ExtractTimeout:
        raise
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _shape(record: dict | None) -> dict:
    """The comparable surface of an extraction."""
    if record is None:
        return {"ok": False}
    lien = record.get("lien_au_terroir") or ""
    aire = (record.get("aire") or {}).get("aire_geographique") or {}
    return {
        "ok": True,
        "kind": record.get("kind", ""),
        "sections": len(record.get("sections") or {}),
        "section_keys": sorted((record.get("sections") or {}).keys()),
        "lien_chars": len(lien),
        "lien_sha256": _sha(lien),
        "lien_norm_sha256": _norm_sha(lien),
        "lien": lien,
        "communes": sum(len(v) for v in aire.values()),
        "departements": len(aire),
        "bundle_size": record.get("bundle_size", 0),
    }


def _drop_text(shape: dict) -> dict:
    shape.pop("lien", None)
    return shape


def _build_shape(on_disk: dict) -> dict:
    shape = _shape(on_disk)
    shape["grapes"] = len(((on_disk.get("grapes") or {}).get("details")) or [])
    return shape


# A delta at or above this word-overlap is typographic, not editorial: the two
# PDFs carry the same cahier, laid out differently or with a stray accent
# fixed. Below it the sections genuinely diverge.
COSMETIC_SIMILARITY = 0.99


def _parent_slugs() -> dict[str, str]:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return {
        e["id_appellation"]: e["slug"]
        for e in index.values()
        if not e.get("is_sub_denomination")
    }


def _verdict(reg: dict, build: dict, self_: dict) -> str:
    if not reg.get("ok"):
        return "register-extract-failed"
    if not build.get("ok"):
        return "no-build-record"
    if not reg["lien_chars"] and not build["lien_chars"]:
        # Two empty liens hash the same; calling that "identical" would let a
        # wrong bind whose section X did not parse count as a match.
        return "no-lien-either-side"
    if reg["lien_sha256"] == build["lien_sha256"]:
        return "identical"
    if reg["lien_norm_sha256"] == build["lien_norm_sha256"]:
        return "identical-normalised"
    if self_.get("ok") and self_["lien_sha256"] != build["lien_sha256"]:
        return "differs-build-not-reproducible"
    if not reg["lien_chars"]:
        return "differs-register-lien-empty"
    return "differs"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[],
                    help="appellation name substring (repeatable)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=rc.DEFAULT_DELAY,
                    help="seconds between register requests")
    ap.add_argument("--refresh", action="store_true", help="re-fetch cached attachments")
    ap.add_argument("--no-selfcheck", action="store_true",
                    help="skip re-extracting the build's own PDF")
    ap.add_argument("--extract-timeout", type=int, default=20,
                    help="seconds before an extraction is abandoned (0 = no guard)")
    args = ap.parse_args()

    for path in (MANIFEST_PATH, INDEX_PATH, rc.RESOLVED_PATH):
        if not path.exists():
            print(f"error: {path.relative_to(ROOT)} missing "
                  f"(run stages 01, 02 and 01d first)", file=sys.stderr)
            return 1

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    resolved = rc.load_resolved()
    slugs = _parent_slugs()

    items = sorted(manifest.items(), key=lambda kv: kv[1]["name"].lower())
    if args.only:
        needles = [s.lower() for s in args.only]
        items = [(k, v) for k, v in items if any(n in v["name"].lower() for n in needles)]
    if args.limit:
        items = items[: args.limit]

    session = requests.Session()
    id_map = er.id_map_from_rows(er.load_gi_rows(session=session))
    reg_manifest = rc.load_manifest()

    rows: list[dict] = []
    verdicts: Counter[str] = Counter()
    fetch_status: Counter[str] = Counter()

    for id_app, meta in tqdm(items, desc="shadow", leave=False):
        name = meta["name"]
        slug = slugs.get(id_app, "")
        on_disk_path = EXTRACTED / f"{slug}.json" if slug else None
        on_disk = (
            json.loads(on_disk_path.read_text(encoding="utf-8"))
            if on_disk_path and on_disk_path.exists() else None
        )
        binding = resolved.get(id_app)

        row: dict = {
            "id_appellation": id_app,
            "name": name,
            "slug": slug,
            "file_number": (binding or {}).get("file_number", ""),
            "register_name": (binding or {}).get("register_name", ""),
            "matched_via": (binding or {}).get("matched_via", ""),
            "build": _build_shape(on_disk) if on_disk else {"ok": False},
            "build_source": {
                "filename": ((on_disk or {}).get("source") or {}).get("filename", ""),
                "boagri_url": ((on_disk or {}).get("source") or {}).get("boagri_url", ""),
                "homologated_at": ((on_disk or {}).get("source") or {}).get(
                    "homologated_at", ""),
                "rescued_from_pdf": ((on_disk or {}).get("source") or {}).get(
                    "rescued_from_pdf", ""),
            },
        }

        if not binding:
            row["fetch_status"] = "unresolved-name"
            row["register"] = {"ok": False}
            row["self"] = {"ok": False}
            row["verdict"] = "unresolved-name"
            fetch_status["unresolved-name"] += 1
            verdicts["unresolved-name"] += 1
            _drop_text(row["build"])
            rows.append(row)
            continue

        cahier, status = rc.fetch(
            binding["file_number"], id_map, reg_manifest,
            session=session, refresh=args.refresh, delay=args.delay,
        )
        fetch_status[status] += 1
        row["fetch_status"] = status
        if cahier is None:
            row["register"] = {"ok": False}
            row["self"] = {"ok": False}
            row["verdict"] = status
            verdicts[status] += 1
            _drop_text(row["build"])
            rows.append(row)
            continue

        row["register_attachment"] = {
            "uri": cahier.attachment_uri,
            "url": cahier.attachment_url,
            "name": cahier.attachment_name,
            "sha256": cahier.sha256,
            "bytes": cahier.bytes,
        }
        reg_text = _pdftotext(cahier.path)
        try:
            reg_record = _extract(name, reg_text, args.extract_timeout)
        except _ExtractTimeout:
            print(f"[timeout] {name}: register extraction exceeded "
                  f"{args.extract_timeout}s", file=sys.stderr)
            row["register"] = {"ok": False, "timeout": True}
            row["self"] = {"ok": False}
            row["verdict"] = "register-extract-timeout"
            verdicts["register-extract-timeout"] += 1
            _drop_text(row["build"])
            rows.append(row)
            continue
        row["register"] = _shape(reg_record)
        if row["register"].get("ok") and row["build"].get("ok"):
            row["lien_similarity"] = round(
                _similarity(row["build"]["lien"], row["register"]["lien"]), 4)
        if reg_record is not None:
            # Same rule stage 02 applies to the build value: date the matched
            # segment, not the whole file. For a GI whose attachment is a
            # whole Journal-officiel issue, a whole-file scan would report a
            # neighbouring appellation's homologation date.
            segment = m02.find_segment(m02.split_bundle(reg_text), name) or reg_text
            row["register"]["homologated_at"] = m02.homologation_date(segment) or ""

        self_shape: dict = {"ok": False}
        build_pdf = row["build_source"]["filename"]
        if not args.no_selfcheck and build_pdf and (CAHIERS / build_pdf).exists():
            try:
                self_shape = _shape(
                    _extract(name, m02.pdftotext(CAHIERS / build_pdf), args.extract_timeout)
                )
            except (subprocess.CalledProcessError, OSError, _ExtractTimeout):
                self_shape = {"ok": False}
        row["self"] = self_shape

        row["verdict"] = _verdict(row["register"], row["build"], self_shape)
        verdicts[row["verdict"]] += 1
        for key in ("build", "register", "self"):
            _drop_text(row[key])
        rows.append(row)

    rc.save_manifest(reg_manifest)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    REPORT_JSON.write_text(json.dumps(
        {"generated_at": generated_at, "n": len(rows),
         "verdicts": dict(verdicts), "fetch_status": dict(fetch_status), "rows": rows},
        ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(_markdown(rows, verdicts, fetch_status, generated_at),
                         encoding="utf-8")

    print(f"[verdicts] {dict(verdicts)}", file=sys.stderr)
    print(f"[fetch] {dict(fetch_status)}", file=sys.stderr)
    print(f"[done] {len(rows)} appellations -> {REPORT_JSON.relative_to(ROOT)}, "
          f"{REPORT_MD.relative_to(ROOT)}", file=sys.stderr)
    return 0


def _vintage(row: dict) -> str:
    """Which side carries the more recent homologation, when both are dated."""
    b = row["build_source"].get("homologated_at") or ""
    r = row["register"].get("homologated_at") or ""
    if not b or not r:
        return "unknown"
    if b == r:
        return "same"
    return "register older" if r < b else "register newer"


def _markdown(rows, verdicts, fetch_status, generated_at) -> str:
    n = len(rows)
    with_cahier = sum(1 for r in rows if r["register"].get("ok"))
    lines = [
        "# FR eAmbrosia register — shadow report",
        "",
        f"Generated {generated_at}. {n} parent appellations.",
        "",
        "Read-only comparison of the register's national cahier attachment "
        "(`productSpecifications[0]`) against the record currently in "
        "`raw/inao/cahier-extracted/`, both parsed by the unchanged stage-02 "
        "extractor. `self` re-extracts the build's own PDF as a determinism "
        "control.",
        "",
        "## Coverage",
        "",
        "| step | count | share |",
        "|---|---:|---:|",
        f"| parent appellations | {n} | 100.0 % |",
        f"| resolved to a register file number | "
        f"{sum(1 for r in rows if r['file_number'])} | "
        f"{100.0 * sum(1 for r in rows if r['file_number']) / max(n, 1):.1f} % |",
        f"| register serves a cahier PDF | "
        f"{sum(1 for r in rows if r.get('register_attachment'))} | "
        f"{100.0 * sum(1 for r in rows if r.get('register_attachment')) / max(n, 1):.1f} % |",
        f"| register cahier extracts | {with_cahier} | "
        f"{100.0 * with_cahier / max(n, 1):.1f} % |",
        "",
        "## Verdicts",
        "",
        "| verdict | count |",
        "|---|---:|",
    ]
    for k, v in sorted(verdicts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v} |")
    lines += ["", "## Fetch status", "", "| status | count |", "|---|---:|"]
    for k, v in sorted(fetch_status.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v} |")

    compared = [r for r in rows if r.get("lien_similarity") is not None]
    cosmetic = [r for r in compared
                if r["verdict"].startswith("differs")
                and r["lien_similarity"] >= COSMETIC_SIMILARITY]
    substantive = [r for r in compared
                   if r["verdict"].startswith("differs")
                   and r["lien_similarity"] < COSMETIC_SIMILARITY]
    lines += [
        "",
        "## How far apart are the two documents?",
        "",
        "`lien_similarity` is the word-multiset Dice coefficient between the two "
        f"`lien_au_terroir` blocks. At or above {COSMETIC_SIMILARITY} the delta is "
        "typographic — a guillemet space, `mélant` → `mêlant`, a different column "
        "width — rather than a different text.",
        "",
        "| bucket | count |",
        "|---|---:|",
        f"| byte-identical | {sum(1 for r in compared if r['verdict'] == 'identical')} |",
        f"| differs, cosmetically (≥ {COSMETIC_SIMILARITY}) | {len(cosmetic)} |",
        f"| differs, substantively (< {COSMETIC_SIMILARITY}) | {len(substantive)} |",
        "",
        "### Vintage, where both sides carry a homologation date",
        "",
        "| relation | count |",
        "|---|---:|",
    ]
    vintages = Counter(_vintage(r) for r in compared)
    for k, v in sorted(vintages.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v} |")
    if substantive:
        lines += [
            "",
            f"### Substantively different ({len(substantive)}) — the ones to read",
            "",
            "| appellation | file number | similarity | build lien | register lien | vintage |",
            "|---|---|---:|---:|---:|---|",
        ]
        for r in sorted(substantive, key=lambda r: r["lien_similarity"]):
            lines.append(
                f"| {r['name']} | {r['file_number']} | {r['lien_similarity']:.3f} | "
                f"{r['build']['lien_chars']} | {r['register']['lien_chars']} | "
                f"{_vintage(r)} |"
            )

    interesting = [r for r in rows if r["verdict"] != "identical"]
    lines += [
        "",
        f"## Non-identical ({len(interesting)})",
        "",
        "| appellation | file number | verdict | sim. | build lien | register lien | "
        "build homol. | register homol. | vintage |",
        "|---|---|---|---:|---:|---:|---|---|---|",
    ]
    for r in sorted(interesting, key=lambda r: (r["verdict"], r["name"].lower())):
        sim = r.get("lien_similarity")
        lines.append(
            f"| {r['name']} | {r['file_number'] or '—'} | {r['verdict']} | "
            f"{'—' if sim is None else format(sim, '.3f')} | "
            f"{r['build'].get('lien_chars', '—')} | "
            f"{r['register'].get('lien_chars', '—')} | "
            f"{r['build_source'].get('homologated_at') or '—'} | "
            f"{r['register'].get('homologated_at') or '—'} | "
            f"{_vintage(r)} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
