"""Greek-keyword tables for parsing the Cyprus ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ.

Cyprus wine specifications are Greek-language EU single-document
templates — structurally identical to the Greek (GR) ones. Rather than
duplicate the ~270 lines of fragile inflection-aware Greek regex, this
module re-exports the canonical Greek tables from `_lib.gr.eniaio_engrafo`
so any future Cyprus-specific quirk lands in this namespace without
churning the shared Greek machinery.
"""

from __future__ import annotations

from _lib.gr.eniaio_engrafo import (  # noqa: F401
    COLOUR_BY_KEYWORD,
    DOC_ANCHOR_NORM,
    INLINE_ROLE_RE,
    ROLE_BY_KEYWORD,
    ROLE_HEADER_RE,
    SECTION_HEADER_RE,
    SECTION_NUM_RE,
    SECTION_ROLE_KEYWORDS,
    STYLE_MARKERS,
    _GEO_AREA_TITLE_BLOCKLIST,
    greek_norm,
)
