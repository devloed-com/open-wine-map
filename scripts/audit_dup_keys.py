"""Detect duplicate dict-literal keys across the scripts/ tree.

Python keeps the *last* value when a dict literal repeats a key, so a key
re-defined with a different value is a silent override — the kind of bug that
split VIVC #4121 (Fetească regală / Királyleányka) across two map slugs and
mis-bound the Gelber Muskateller cluster. This audit walks every dict literal
under `scripts/` and classifies each repeated constant key as:

  - **clash**: the key is re-bound to a DIFFERENT value (the later one silently
    wins). Always a bug — fold the synonyms onto one value or delete the dead
    entry.
  - **benign**: the key repeats with the IDENTICAL value. Functionally inert,
    but a latent footgun (editing one copy creates a clash), so it's reported
    too — just doesn't fail the run.

Exit status: 0 when no clashes, 1 when any clash is found (so it doubles as a
CI / pre-commit guard). `--strict` additionally fails on benign duplicates.

Usage:
    .venv/bin/python scripts/audit_dup_keys.py
    .venv/bin/python scripts/audit_dup_keys.py --strict
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class DupKey:
    file: str
    key: str
    first_line: int
    first_value: str
    later_line: int
    later_value: str

    @property
    def clash(self) -> bool:
        return self.first_value != self.later_value


def _key_repr(node: ast.expr) -> str | None:
    """Stable text for a constant or all-constant-tuple key, else None."""
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Tuple):
        parts = [_key_repr(e) for e in node.elts]
        if all(p is not None for p in parts):
            return "(" + ", ".join(p for p in parts if p) + ")"
    return None


def find_duplicates(root: Path = SCRIPTS_DIR) -> list[DupKey]:
    """Every repeated constant dict key under `root` (clash + benign)."""
    out: list[DupKey] = []
    for path in sorted(root.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError as exc:  # pragma: no cover - parse errors surface elsewhere
            print(f"PARSE ERROR {path}: {exc}", file=sys.stderr)
            continue
        rel = str(path.relative_to(root.parent))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            seen: dict[str, tuple[int, str]] = {}
            for k, v in zip(node.keys, node.values):
                if k is None:  # dict unpacking (**other)
                    continue
                kr = _key_repr(k)
                if kr is None:
                    continue
                vtxt = ast.get_source_segment(src, v) or ast.dump(v)
                if kr in seen:
                    first_line, first_v = seen[kr]
                    out.append(DupKey(rel, kr, first_line, first_v, k.lineno, vtxt))
                seen[kr] = (k.lineno, vtxt)
    return out


def find_clashes(root: Path = SCRIPTS_DIR) -> list[DupKey]:
    """Only the dangerous subset: key re-bound to a different value."""
    return [d for d in find_duplicates(root) if d.clash]


def _format(d: DupKey) -> str:
    head = f"{d.file}:{d.later_line}  key {d.key}"
    if d.clash:
        return (
            f"{head}\n"
            f"     first      (L{d.first_line}): {d.first_value}\n"
            f"     LATER WINS (L{d.later_line}): {d.later_value}"
        )
    return f"{head}  == {d.later_value}  (dup of L{d.first_line})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--strict", action="store_true", help="also fail on benign same-value duplicates"
    )
    ap.add_argument("--root", type=Path, default=SCRIPTS_DIR, help="tree to scan")
    args = ap.parse_args()

    dups = find_duplicates(args.root)
    clashes = [d for d in dups if d.clash]
    benign = [d for d in dups if not d.clash]

    print("=== DANGEROUS CLASHES (key overridden with a DIFFERENT value) ===", file=sys.stderr)
    for d in clashes:
        print(_format(d), file=sys.stderr)
    if not clashes:
        print("  none", file=sys.stderr)

    print("\n=== BENIGN duplicates (same key, same value) ===", file=sys.stderr)
    for d in benign:
        print(_format(d), file=sys.stderr)
    if not benign:
        print("  none", file=sys.stderr)

    print(f"\nClashes: {len(clashes)}   Benign dups: {len(benign)}", file=sys.stderr)

    if clashes:
        return 1
    if args.strict and benign:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
