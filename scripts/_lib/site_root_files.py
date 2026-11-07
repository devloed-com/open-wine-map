"""Static files served from the site root — search-engine ownership
verification files (Naver's `naver<token>.html`), the kind a webmaster
console asks for once and expects to find for as long as the property is
claimed. They are checked in under scripts/_lib/site_root/ so a fresh
checkout reproduces them, and stage 04 copies them into wiki/ with the
other root files (robots.txt, sitemap.xml, llms.txt, 404.html)."""

from __future__ import annotations

from pathlib import Path

SITE_ROOT_SRC = Path(__file__).resolve().parent / "site_root"


def site_root_files(src: Path = SITE_ROOT_SRC) -> list[Path]:
    if not src.is_dir():
        return []
    return sorted(p for p in src.iterdir() if p.is_file() and not p.name.startswith("."))


def copy_site_root_files(wiki: Path, src: Path = SITE_ROOT_SRC) -> list[str]:
    """Copy every file of `src` into `wiki/` (write-if-changed) and return
    the names copied, changed or not."""
    names: list[str] = []
    for p in site_root_files(src):
        body = p.read_bytes()
        dest = wiki / p.name
        if not dest.exists() or dest.read_bytes() != body:
            dest.write_bytes(body)
        names.append(p.name)
    return names
