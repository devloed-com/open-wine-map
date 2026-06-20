"""Regenerate the committed grape-vocabulary snapshot used by the test suite.

The live grape matcher (`scripts/_lib/grape_entity.py`) builds its
`exact_index` vocabulary from three sources: the committed `GRAPE_ALIAS`
table, the gitignored `raw/vivc/by-slug/*.json` (VIVC prime + synonym
surfaces), and the gitignored `raw/*-extracted/` corpora. On CI only the
committed table is present, so dozens of grape surfaces that resolve
exactly against a VIVC synonym locally (`Weißer Riesling` -> riesling)
fall through to fuzzy matching and pick the wrong slug
(`Weißer Riesling` -> raeuschling). The Phase-5 parser fixture tests then
fail on CI while passing locally.

This script snapshots the full live vocabulary so `tests/conftest.py` can
feed it to the matcher when `raw/vivc/by-slug` is absent (CI), making the
parser tests deterministic regardless of whether `raw/` has been fetched.

Run from the repo root WITH a populated `raw/` (i.e. after stages 00->02g):

    .venv/bin/python tests/fixtures/gen_grape_vocab_snapshot.py

Insertion order is preserved so fuzzy tie-breaking is identical to a full
local build. Regenerate + commit whenever a new vocab-dependent parser test
is added or the VIVC / corpus data underlying the matcher changes.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from _lib.grape_entity import _VIVC_DIR, _load_vocabulary  # noqa: E402

SNAPSHOT_PATH = Path(__file__).parent / "grape_vocab_snapshot.json.gz"


def main() -> int:
    if not _VIVC_DIR.exists():
        print(
            f"refusing to regenerate: {_VIVC_DIR} is absent — run the fetch "
            "stages (00->02g) so the live vocabulary is complete first.",
            file=sys.stderr,
        )
        return 1
    vocab = _load_vocabulary()
    # exact_index preserves the matcher's source-precedence insertion order;
    # dump without sort_keys so a snapshot-backed run reproduces the same
    # fuzzy tie-breaking as a full local build.
    blob = json.dumps(vocab.exact_index, ensure_ascii=False).encode("utf-8")
    SNAPSHOT_PATH.write_bytes(gzip.compress(blob, mtime=0))
    print(f"wrote {SNAPSHOT_PATH} ({len(vocab.exact_index)} entries, "
          f"{SNAPSHOT_PATH.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
