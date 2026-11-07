"""A Maltese GI with no OJ publication is built from the register's single
document (scripts/mt/02_extract_pliegos.py `build_record_from_fiche`, 2026-11-07).

The Maltese Islands IĠT has no publication in eAmbrosia; its 2011 technical
file carries the roster (MAIN / OTHER), "Red, white and rosé wines are
produced …", the categories, the demarcated area and the link text. The card
had shown nothing.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location("mt02", ROOT / "scripts" / "mt" / "02_extract_pliegos.py")
mt02 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mt02)

WINE = {"giIdentifier": "EUGI00000007083", "fileNumber": "PGI-MT-A1631", "slug": "maltese-islands",
        "name": "Maltese Islands", "kind": "IGP", "producer_group": {}, "publications": []}

FICHE = {
    "grapes": {"principal": ["chardonnay", "gellewza"], "accessory": ["merlot"],
               "details": [{"slug": "chardonnay", "name": "Chardonnay", "role": "principal", "colour": "blanc"},
                           {"slug": "gellewza", "name": "Ġellewża", "role": "principal", "colour": "noir"},
                           {"slug": "merlot", "name": "Merlot", "role": "accessory", "colour": "noir"}]},
    "categories": "1. Wine\n 4. Sparkling wine\n 15. Wine from raisined grapes",
    "description": "Red, white and rosé wines are produced following established norms for the production region.",
    "geo_area": "The Maltese Islands.",
    "link_to_terroir": "The climate of the Maltese Islands is typically Mediterranean.",
    "source": {"url": "https://ec.europa.eu/x/attachments/11088", "ref": "Ares(2011)1412142",
               "attachment_uri": "11088", "fetched_at": "2026-10-23T16:01:09+00:00"},
}


def test_the_fiche_becomes_the_record():
    rec = mt02.build_record_from_fiche(WINE, FICHE, {})
    assert rec["stub"] is False
    assert rec["grapes"]["principal"] == ["chardonnay", "gellewza"]
    assert rec["grapes"]["accessory"] == ["merlot"]
    assert rec["grapes"]["details"][0]["source"] == "eambrosia-register-fiche"
    assert {"white", "red", "rose", "sparkling", "raisin-wine"} <= set(rec["styles"])
    assert rec["link_to_terroir"].startswith("The climate")
    assert rec["section_roles"]["geo_area"] == "The Maltese Islands."
    assert rec["summary"].startswith("Red, white and rosé wines")
    assert rec["source"]["kind"] == "eambrosia-register-fiche"
    assert rec["source"]["source_url"].endswith("/attachments/11088")
    assert rec["register_fiche"] == {"url": "https://ec.europa.eu/x/attachments/11088", "ref": "Ares(2011)1412142"}
