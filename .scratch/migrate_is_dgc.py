"""One-off: rename is_dgc -> is_sub_denomination in every extracted JSON."""

from __future__ import annotations

import json
from pathlib import Path


def rename_key(obj):
    if isinstance(obj, dict):
        if "is_dgc" in obj:
            obj["is_sub_denomination"] = obj.pop("is_dgc")
        for v in obj.values():
            rename_key(v)
    elif isinstance(obj, list):
        for v in obj:
            rename_key(v)


def migrate_dir(root: Path) -> tuple[int, int]:
    touched = total = 0
    for p in sorted(root.glob("*.json")):
        total += 1
        data = json.loads(p.read_text())
        before = json.dumps(data, ensure_ascii=False)
        rename_key(data)
        after = json.dumps(data, ensure_ascii=False)
        if before != after:
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            touched += 1
    return touched, total


for path in (Path("raw/inao/cahier-extracted"), Path("raw/es/pliegos-extracted")):
    if not path.exists():
        print(f"SKIP {path} (not present)")
        continue
    touched, total = migrate_dir(path)
    print(f"{path}: rewrote {touched}/{total} files")
