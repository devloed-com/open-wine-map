"""Czech obec (LAU2 municipality) normaliser for matching
Vyhláška-254/2010 obec names against GISCO LAU 2024 polygons.

Both sides are Latin script with Czech diacritics. The normaliser
casefolds, strips diacritics via NFKD (the GISCO `LAU_NAME` strings
and the Vyhláška obec names agree on diacritics, but folding makes
the index robust against case + edge-case spelling drift like
`Mělník` vs `Melnik`), and collapses whitespace + punctuation.

Czech obec names occasionally compound with an `XY` district suffix
(e.g. `Bechlín u Loun` vs `Bechlín`); since the Vyhláška carries the
full disambiguated form, the normaliser preserves the entire string
rather than truncating at the first space.
"""

from __future__ import annotations

import re
import unicodedata


def _normalise_commune(name: str) -> str:
    """Strip diacritics + casefold + collapse whitespace/punctuation.
    Use as both the key in the GISCO index and the lookup token from
    the Vyhláška obec list."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.casefold()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s
