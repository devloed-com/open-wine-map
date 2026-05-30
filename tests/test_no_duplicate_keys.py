"""Guard: no dict literal under scripts/ may re-bind a key to a different value.

Python keeps the last value on a duplicate key, so such a clash is a silent
override (it split VIVC #4121 across two grape slugs before this guard existed).
Run via `pytest`; the audit logic lives in scripts/audit_dup_keys.py and is also
invokable directly as a CI / pre-commit step.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_dup_keys import find_clashes, _format  # noqa: E402


def test_no_conflicting_duplicate_dict_keys() -> None:
    clashes = find_clashes()
    assert not clashes, "Silent dict-key overrides found:\n" + "\n".join(
        _format(c) for c in clashes
    )
