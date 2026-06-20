"""Diff two build-output snapshots, ignoring content-hash differences in
asset/data filenames (the hash changes iff the content changed, so compare
by logical name: aocs.<lang>.<hash>.js -> aocs.<lang>.js).

Usage: uv run scripts/compare_build_output.py tmp/golden-before wiki
Exit 0 = identical, 1 = differences (listed on stdout).

This is the safety net for the stage-04 refactor phases: a move-only refactor
must produce byte-identical output (hashes aside). Stage 04 is deterministic
by design — it sorts set-derived structures specifically so a no-op rerun is a
no-op — so any DIFF here from a refactor means behaviour changed.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

# A hashed asset filename: foo.0123456789.js  /  bar.0123456789.css
HASH_RE = re.compile(r"\.[0-9a-f]{10}\.(js|css)$")
# A hashed reference *inside* a text file (HTML/JS/XML): src=".../app.<hash>.js"
REF_RE = re.compile(r"(\.)[0-9a-f]{10}(\.(?:js|css))")

TEXT_SUFFIXES = (".html", ".js", ".css", ".xml", ".txt")


def logical(p: Path, root: Path) -> str:
    """Path with the content-hash stripped from the filename."""
    rel = str(p.relative_to(root))
    return HASH_RE.sub(lambda m: "." + m.group(1), rel)


def digest(p: Path) -> str:
    data = p.read_bytes()
    if p.suffix in TEXT_SUFFIXES:
        text = data.decode("utf-8", "replace")
        # Normalise hashed references so a renamed-but-identical bundle does
        # not cascade into a diff on every page that links it.
        text = REF_RE.sub(r"\1HASH\2", text)
        data = text.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def index(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in TEXT_SUFFIXES:
            out[logical(p, root)] = digest(p)
    return out


def main() -> int:
    if len(sys.argv) != 3:
        sys.exit("usage: compare_build_output.py <dir-a> <dir-b>")
    a, b = Path(sys.argv[1]), Path(sys.argv[2])
    ia, ib = index(a), index(b)
    bad = 0
    for k in sorted(set(ia) | set(ib)):
        va, vb = ia.get(k), ib.get(k)
        if va != vb:
            kind = (
                "missing-left" if va is None
                else "missing-right" if vb is None
                else "content"
            )
            print(f"DIFF {k}  ({kind})")
            bad += 1
    print(f"{bad} differences" if bad else "identical")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
