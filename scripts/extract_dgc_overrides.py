"""Extract per-DGC commune lists from IGP-umbrella parent cahiers.

Many IGP umbrella appellations (Aude, Pays d'Hérault, Isère, Coteaux de
l'Ain, Vaucluse) enumerate per-DGC commune lists in the parent cahier's
section IV. INAO's published aires CSV doesn't carry separate rows for
these DGCs, so without an override they fall back to the parent IGP's
full territory — see scripts/_lib/dgc_village_overrides.py for the
shape of the bug.

This script parses each parent's section text, finds each DGC's short
name (the cahier's column-1 header for that sub-zone), captures the
following commune-list chunk, normalises commune names, and resolves
them against the IGN AdminExpress index — restricted to the parent's
primary département(s) to avoid homonym collisions. The result is
written to scripts/_lib/dgc_village_overrides.json, where the runtime
override module loads it.

Re-run when the underlying parent cahiers (raw/inao/cahier-extracted/
{aude,pays-d-herault,isere,coteaux-de-l-ain,vaucluse}.json) change.

  .venv/bin/python scripts/extract_dgc_overrides.py
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.aires import _normalize  # noqa: E402

EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
COMMUNES_GEOJSON = ROOT / "raw" / "ign" / "communes.geojson"

# Parents to extract. Each entry: parent_slug → (section_key, dept_codes).
# Section key picks the cahier section that holds the DGC commune table;
# dept_codes scopes commune-name lookup to the parent's territory so we
# don't accidentally match a same-named commune in a different region.
TARGETS: dict[str, tuple[str, set[str]]] = {
    "aude": ("4", {"11"}),
    "pays-d-herault": ("4", {"34"}),
    "isere": ("4", {"38"}),
    "coteaux-de-l-ain": ("4", {"01"}),
    "vaucluse": ("4", {"84"}),
}


def normalize_commune(s: str) -> str:
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"^(?:Le|La|Les|L['’])\s+", "", s, flags=re.IGNORECASE)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[\W_]+", "", s).lower()


# Cahiers reference historical or short-form commune names; the IGN
# AdminExpress data uses current full names. Mapping (normalized) cahier
# token → (normalized) IGN commune name closes the gap. Each entry was
# verified against the loaded IGN file before being added.
COMMUNE_ALIASES: dict[str, str] = {
    # Ain (01) commune-nouvelle mergers
    "treffortcuisiat": "valrevermont",
    "pressiat": "valrevermont",
    "bellegardesurvalserine": "valserhone",
    "lancrans": "valserhone",
    "belmontluthezieu": "arviereenvalromey",
    "sutrieu": "arviereenvalromey",
    "vieu": "arviereenvalromey",
    "chavornay": "arviereenvalromey",
    "virieulepetit": "arviereenvalromey",
    # Hérault (34)
    "cessenon": "cessenonsurorb",
    "verargues": "entrevignes",
    "saintchristol": "entrevignes",
    "villeneuvelesmaguelonne": "villeneuvelesmaguelone",  # cahier double-n → IGN single-n
    "lesignanlacebe": "lezignanlacebe",                    # cahier é → IGN ê
    # Aude (11) — full-name disambiguation
    "thezan": "thezandescorbieres",
    "argens": "argensminervois",
    "ferrals": "ferralslescorbieres",
    "montredon": "montredondescorbieres",
    "lezignan": "lezignancorbieres",
    "montbrun": "montbrundescorbieres",
    "portel": "porteldescorbieres",
    "lasseredeprouilhe": "lasserredeprouille",   # cahier typo: -lhe → IGN -lle
    "escueillens": "escueillensetsaintjustdebelengard",
    "saintjustdebelengard": "escueillensetsaintjustdebelengard",
    # Vaucluse (84) — fix word-wrap fragments
    "bastidedesjourdan": "labastidedesjourdans",
    "isleslasorgue": "lislesurlasorgue",
}


def normalize_quotes(s: str) -> str:
    return s.replace("’", "'").replace("“", '"').replace("”", '"').replace("«", "").replace("»", "")


def fold_diacritics(s: str) -> str:
    """Lowercase + strip diacritics, for case/accent-insensitive matching."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def load_commune_index() -> dict[tuple[str, str], str]:
    fc = json.loads(COMMUNES_GEOJSON.read_text(encoding="utf-8"))
    idx: dict[tuple[str, str], str] = {}
    for feat in fc["features"]:
        p = feat["properties"]
        idx[(p["codeDepartement"], normalize_commune(p["nom"]))] = p["code"]
    return idx


def short_name(full: str, parent_full: str) -> str:
    """Strip the parent appellation prefix from a DGC name."""
    if full.lower().startswith(parent_full.lower() + " "):
        return full[len(parent_full) + 1:]
    return full


def extract_chunk(text: str, name: str, next_names: list[str]) -> str | None:
    """Return the slice of `text` between `name` and the next-occurring header.

    Stops at any of `next_names` if they appear after `name`, or at a
    section terminator phrase. Returns None if `name` isn't found.
    """
    pos = text.find(name)
    if pos < 0:
        return None
    start = pos + len(name)
    candidates = []
    for n in next_names:
        p = text.find(n, start)
        if p >= 0:
            candidates.append(p)
    for terminator in (
        "La zone de proximité",
        "Les documents cartographiques",
        "Publié au BO",
    ):
        p = text.find(terminator, start)
        if p >= 0:
            candidates.append(p)
    end = min(candidates) if candidates else len(text)
    return text[start:end]


def parse_communes(chunk: str) -> list[str]:
    """Split a comma-separated commune list across newlines and clean each."""
    chunk = re.sub(r"\([^)]*\)", "", chunk)
    chunk = chunk.replace("\n", " ")
    chunk = re.sub(r"\s+", " ", chunk)
    # Some cahiers separate adjacent commune names with " - " (Vaucluse).
    chunk = re.sub(r"\s+-\s+", ", ", chunk)
    # Truncate at the next bullet introducer (Coteaux-de-l'Ain-style):
    # "• pour l'unité géographique « X » :" marks the next DGC's start.
    bullet = re.search(r"•\s*pour l['’]unit[éê]", chunk, flags=re.IGNORECASE)
    if bullet:
        chunk = chunk[:bullet.start()]
    parts = re.split(r"[,;.]", chunk)
    out: list[str] = []
    for part in parts:
        s = part.strip()
        if not s or len(s) < 2:
            continue
        if any(stop in s.lower() for stop in (
            "à l'exception",
            "à l’exception",
            "section",
            "complétée",
            "récolte",
            "vinification",
            "publié",
            "rive gauche",
            "rive droite",
            "partie",
            "annexe",
            "zone de",
            "indication géographique",
            "code officiel",
            "département",
            "arrondissement",
        )):
            continue
        if not re.match(r"^[A-ZÀ-Ÿ(]", s):
            continue
        out.append(s)
    return out


def main() -> int:
    insee_idx = load_commune_index()
    print(f"loaded {len(insee_idx)} commune entries from IGN index", file=sys.stderr)

    index = {}
    for json_path in sorted(EXTRACTED.glob("*.json")):
        if json_path.name == "_index.json":
            continue
        d = json.loads(json_path.read_text(encoding="utf-8"))
        index[d["slug"]] = d

    overrides: dict[str, set[str]] = {}
    miss_log: list[str] = []
    for parent_slug, (section_key, dept_codes) in TARGETS.items():
        parent = index.get(parent_slug)
        if parent is None:
            print(f"  {parent_slug}: parent record missing", file=sys.stderr)
            continue
        text = parent["sections"].get(section_key, "")
        if not text:
            print(f"  {parent_slug}: section {section_key!r} empty", file=sys.stderr)
            continue

        # Collect this parent's DGCs (records pointing at parent_slug).
        dgcs = sorted(
            (rec for rec in index.values()
             if rec.get("is_sub_denomination") and rec.get("parent_slug") == parent_slug),
            key=lambda r: -len(r["name"]),
        )
        if not dgcs:
            continue

        parent_full = parent["name"]
        text_norm = normalize_quotes(text)
        text_folded = fold_diacritics(text_norm)
        # Build short-name → record map; longest first to avoid prefix collisions.
        shorts = [(short_name(d["name"], parent_full), d) for d in dgcs]

        # Find each short name's position (case- and diacritic-insensitive);
        # sort by occurrence in text. The chunk extractor uses the actual
        # text slice from those offsets so the original casing is preserved.
        positions = []
        for s, rec in shorts:
            needle = fold_diacritics(normalize_quotes(s))
            pos = text_folded.find(needle)
            if pos >= 0:
                actual = text_norm[pos:pos + len(needle)]
                positions.append((pos, actual, rec))
        positions.sort()

        for i, (pos, s, rec) in enumerate(positions):
            next_names = [n for _, n, _ in positions[i + 1:]]
            chunk = extract_chunk(text_norm, s, next_names)
            if chunk is None:
                miss_log.append(f"{rec['name']}: header not found in section")
                continue
            communes = parse_communes(chunk)
            insees: set[str] = set()
            unmatched: list[str] = []
            for nm in communes:
                norm = normalize_commune(nm)
                norm = COMMUNE_ALIASES.get(norm, norm)
                hit = None
                for dc in dept_codes:
                    if (dc, norm) in insee_idx:
                        hit = insee_idx[(dc, norm)]
                        break
                if hit:
                    insees.add(hit)
                else:
                    unmatched.append(nm)
            if not insees:
                miss_log.append(f"{rec['name']}: zero INSEE matches; communes={communes!r}")
                continue
            id_denom = str(rec["id_denomination_geo"])
            overrides[id_denom] = insees
            label = f"  {rec['name']}: {len(insees)} INSEE"
            if unmatched:
                label += f"  (unmatched: {unmatched})"
            print(label, file=sys.stderr)

    print(file=sys.stderr)
    if miss_log:
        print(f"{len(miss_log)} DGCs without extracted communes:", file=sys.stderr)
        for m in miss_log:
            print(f"  {m}", file=sys.stderr)
        print(file=sys.stderr)

    out_path = ROOT / "scripts" / "_lib" / "dgc_village_overrides.json"
    sidecar = {k: sorted(v) for k, v in sorted(overrides.items(), key=lambda kv: int(kv[0]))}
    out_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(overrides)} overrides written → {out_path.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
