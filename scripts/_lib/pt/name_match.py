"""Normalised matching between eAmbrosia GI names and IVV caderno
master-index labels.

In practice the two sources agree 1:1 on names today, but eAmbrosia /
IVV editorial drift (capitalisation, "DO " / "DOP " prefixes, spelling
of "DoTejo" vs "Do Tejo") may show up in future runs. Keep the
normaliser narrow so a mismatch surfaces as a stub rather than as a
silent wrong-PDF match.
"""

from __future__ import annotations

import re
import unicodedata

_KIND_PREFIX_RE = re.compile(
    r"^(?:DOP|DOC|DO|IGP|IG|VR)\s+", flags=re.IGNORECASE
)


def normalise(name: str) -> str:
    """Lowercase, strip diacritics, drop kind prefixes, collapse spaces."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = _KIND_PREFIX_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def build_lookup(ivv_entries: list[dict]) -> dict[str, dict]:
    """Return {normalised_name: ivv_entry} for the IVV cadernos-index."""
    out: dict[str, dict] = {}
    for entry in ivv_entries:
        out[normalise(entry["name"])] = entry
    return out


def find_match(name: str, lookup: dict[str, dict]) -> dict | None:
    """eAmbrosia name → IVV entry, or None when there is no clean match."""
    return lookup.get(normalise(name))
