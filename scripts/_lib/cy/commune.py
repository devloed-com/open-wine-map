"""Greek δήμος / κοινότητα / χωριό parser for the Cyprus ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ
section-area body.

Cyprus' area descriptions are Greek-language and use the same tier
vocabulary as the Greek mainland (δήμος / κοινότητα / χωριό), so the
parser + commune-name normaliser are re-exported from
`_lib.gr.commune`. CY geometry mostly resolves via Bétard PDO match +
GISCO district-union (by GISCO_ID prefix), so the commune-list path is
a defensive fallback.
"""

from __future__ import annotations

from _lib.gr.commune import _normalise_commune, parse_commune_list  # noqa: F401
