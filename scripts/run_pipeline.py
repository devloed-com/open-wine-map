"""End-to-end build: runs the full FR + ES pipeline in order.

Mirrors the stages documented in README.md. Pass `--provider` once and it
flows to every LLM stage (02c / 02d / 02e, both FR and ES variants); same
for `--workers`, `--model`, `--ollama-url`.

Slice the run with `--fr` / `--es` / `--from` / `--to`. Stage names are the
script path relative to `scripts/` minus `.py` — e.g. `02_extract_cahiers`,
`es/02_extract_pliegos`. Use `--list` to print the resolved plan without
executing.

For the manual round-trip (02c/02d/02e `--emit-todo` / `--import`), drive
the per-stage script directly — this wrapper is the unattended happy path.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
LLM_PROVIDERS = ("anthropic", "mistral", "ollama")


@dataclass
class Stage:
    """One pipeline step. `name` is the user-visible id for --from/--to.

    `script` is the path relative to scripts/ (often == name; differs only
    when one script is invoked twice with different flags, e.g.
    02b_fetch_aoc_lexicon runs once for FR and once for ES).
    """
    name: str
    script: str
    extra: list[str] = field(default_factory=list)
    llm: bool = False


FR_STAGES: list[Stage] = [
    Stage("00_fetch_data",              "00_fetch_data.py"),
    Stage("01_scrape_cahiers",          "01_scrape_cahiers.py"),
    Stage("02_extract_cahiers",         "02_extract_cahiers.py"),
    Stage("02b_fetch_grape_lexicon",    "02b_fetch_grape_lexicon.py"),
    Stage("02b_fetch_aoc_lexicon",      "02b_fetch_aoc_lexicon.py"),
    Stage("02b_fetch_style_lexicon",    "02b_fetch_style_lexicon.py"),
    Stage("02b_translate_styles",       "02b_translate_styles.py",      llm=True),
    Stage("02d_extract_terroir_facts",  "02d_extract_terroir_facts.py", llm=True),
    Stage("02c_translate_summaries",    "02c_translate_summaries.py",   llm=True),
    Stage("02e_translate_terroir_facts", "02e_translate_terroir_facts.py", llm=True),
    Stage("03_generate_wiki",           "03_generate_wiki.py"),
]

ES_STAGES: list[Stage] = [
    Stage("es/00_fetch_data",           "es/00_fetch_data.py"),
    Stage("es/01_fetch_pliegos",        "es/01_fetch_pliegos.py"),
    Stage("es/01b_solve_waf",           "es/01b_solve_waf.py"),
    Stage("es/02_extract_pliegos",      "es/02_extract_pliegos.py"),
    Stage("es/02b_fetch_aoc_lexicon",   "02b_fetch_aoc_lexicon.py",
          extra=["--lang", "es", "--source", "raw/es/pliegos-extracted/"]),
    Stage("es/02d_extract_terroir_facts", "es/02d_extract_terroir_facts.py", llm=True),
    Stage("es/02c_translate_summaries", "02c_translate_summaries.py",
          extra=["--source-lang", "es"], llm=True),
    Stage("es/02e_translate_terroir_facts", "es/02e_translate_terroir_facts.py", llm=True),
    Stage("es/03_generate_wiki",        "es/03_generate_wiki.py"),
]

FINAL = Stage("04_build_maps", "04_build_maps.py")


def resolve_index(stages: list[Stage], needle: str, flag: str) -> int:
    """Match `needle` against stage names. Accepts the exact name, the
    name without an optional `es/` prefix, or with a `.py` suffix."""
    candidates = {s.name for s in stages}
    # Try exact, then with/without es/ prefix, then with .py stripped.
    variants = [needle, needle.removesuffix(".py")]
    if "/" not in needle:
        variants += [f"es/{needle}"]
    else:
        variants += [needle.split("/", 1)[1]]
    for v in variants:
        for i, s in enumerate(stages):
            if s.name == v:
                return i
    listed = ", ".join(sorted(candidates))
    sys.exit(f"[error] {flag}={needle!r} did not match any stage. Valid: {listed}")


def slice_stages(stages: list[Stage], frm: str | None, to: str | None) -> list[Stage]:
    lo = resolve_index(stages, frm, "--from") if frm else 0
    hi = resolve_index(stages, to, "--to") if to else len(stages) - 1
    if hi < lo:
        sys.exit(f"[error] --to ({to!r}) precedes --from ({frm!r})")
    return stages[lo:hi + 1]


def run(cmd: list[str]) -> None:
    print(f"\n[run] {' '.join(shlex.quote(c) for c in cmd)}", file=sys.stderr, flush=True)
    t0 = time.time()
    result = subprocess.run(cmd, cwd=ROOT)
    dt = time.time() - t0
    if result.returncode != 0:
        print(f"[fail] exit={result.returncode} after {dt:.1f}s", file=sys.stderr)
        sys.exit(result.returncode)
    print(f"[ok] {dt:.1f}s", file=sys.stderr)


def build_plan(args: argparse.Namespace) -> list[Stage]:
    if args.fr and args.es:
        sys.exit("[error] pass --fr or --es, not both (default: both)")
    do_fr = args.fr or not args.es
    do_es = args.es or not args.fr

    plan: list[Stage] = []
    if do_fr:
        plan += slice_stages(FR_STAGES, args.from_, args.to)
    if do_es:
        es_plan = slice_stages(ES_STAGES, args.from_, args.to)
        if args.skip_waf:
            es_plan = [s for s in es_plan if s.name != "es/01b_solve_waf"]
        plan += es_plan
    if not args.skip_build:
        plan.append(FINAL)
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fr", action="store_true", help="only run FR pipeline.")
    ap.add_argument("--es", action="store_true", help="only run ES pipeline.")
    ap.add_argument("--from", dest="from_", metavar="STAGE",
                    help="start at this stage (inclusive). See --list for names.")
    ap.add_argument("--to", metavar="STAGE",
                    help="stop after this stage (inclusive).")
    ap.add_argument(
        "--provider", default="anthropic", choices=LLM_PROVIDERS,
        help="LLM backend for 02c / 02d / 02e (default: anthropic).",
    )
    ap.add_argument("--workers", type=int, default=1,
                    help="concurrent workers for LLM stages (default 1).")
    ap.add_argument("--ollama-url", default=None,
                    help="override Ollama endpoint.")
    ap.add_argument("--model", default=None,
                    help="override LLM model id.")
    ap.add_argument("--skip-waf", action="store_true",
                    help="skip es/01b_solve_waf (needs headless Chromium / bootstrap deps).")
    ap.add_argument("--skip-build", action="store_true",
                    help="skip final stage 04_build_maps.")
    ap.add_argument("--list", action="store_true",
                    help="print the resolved stage plan and exit.")
    args = ap.parse_args()

    llm_flags = ["--provider", args.provider, "--workers", str(args.workers)]
    if args.ollama_url:
        llm_flags += ["--ollama-url", args.ollama_url]
    if args.model:
        llm_flags += ["--model", args.model]

    plan = build_plan(args)
    if not plan:
        sys.exit("[error] empty plan — nothing to run")

    if args.list:
        for s in plan:
            extras = " ".join(s.extra) + (" [LLM]" if s.llm else "")
            print(f"  {s.name:40s}  →  scripts/{s.script}  {extras}".rstrip())
        return 0

    for s in plan:
        cmd = [PY, str(ROOT / "scripts" / s.script), *s.extra]
        if s.llm:
            cmd += llm_flags
        run(cmd)

    print("\n[all-done]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
