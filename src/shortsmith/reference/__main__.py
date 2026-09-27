"""`python -m shortsmith.reference`: the inventory and gaps commands (ticket 036).

    inventory <url> [--category C] [--tier A|B] [--out DIR] [--references FILE]
    inventory --all [--out DIR] [--references FILE]
    gaps [--dir DIR]

`inventory` builds the Gemini analyser from `.env` (`GEMINI_API_KEY`, `REFERENCE_MODEL`,
`REFERENCE_FPS`, `REFERENCE_ENDPOINT`), reads the link's tier and category from
`docs/references.md` unless the flags say otherwise, and writes
`docs/reference/inventory/<video_id>.json`. `--all` does every link in the file, one
request each, moving past a failing video. `gaps` writes `GAPS.md` beside the JSON.
Exit 0 when every link was inventoried, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from shortsmith import config, render
from shortsmith.config import Settings
from shortsmith.reference import (
    INVENTORY_DIR,
    REFERENCES_FILES,
    ReferenceError,
    Tier,
    gaps,
    inventory,
    inventory_all,
    link_for,
    links_in,
)
from shortsmith.reference.gemini import GeminiAnalyser, ReferenceAnalyser


def analyser_from(settings: Settings) -> GeminiAnalyser:
    return GeminiAnalyser(
        api_key=settings.gemini_api_key,
        model=settings.reference_model,
        fps=settings.reference_fps,
        endpoint=settings.reference_endpoint,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    analyser: ReferenceAnalyser | None = None,
    settings: Settings | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m shortsmith.reference")
    commands = parser.add_subparsers(dest="command", required=True)
    inv = commands.add_parser("inventory", help="inventory one reference link, or --all")
    inv.add_argument("url", nargs="?", help="a YouTube shorts, youtu.be or watch link")
    inv.add_argument("--all", action="store_true", help="every link in the references file")
    inv.add_argument("--category", help="overrides the category the references file gives")
    inv.add_argument("--tier", choices=("A", "B"), help="overrides the tier the file gives")
    inv.add_argument("--out", type=Path, default=INVENTORY_DIR)
    inv.add_argument(
        "--references",
        type=Path,
        action="append",
        help="a references file (repeatable); default "
        + ", ".join(str(p) for p in REFERENCES_FILES),
    )
    gap = commands.add_parser("gaps", help="write GAPS.md from every inventory JSON")
    gap.add_argument("--dir", type=Path, default=INVENTORY_DIR)
    args = parser.parse_args(argv)

    if args.command == "gaps":
        path = gaps.write(cast(Path, args.dir))
        print(f"gap report written to {path}")
        return 0

    if not args.all and not args.url:
        inv.error("give a url, or --all")
    out_dir = cast(Path, args.out)
    given = cast(list[Path] | None, args.references)
    references: Sequence[Path] = given if given else REFERENCES_FILES
    if analyser is None:
        loaded = settings if settings is not None else config.load()
        if loaded.gemini_api_key is None:
            print("the reference tool needs GEMINI_API_KEY in .env", file=sys.stderr)
            return 1
        analyser = analyser_from(loaded)
    registry = render.registry()
    if args.all:
        links = links_in(references)
        print(f"{len(links)} links in {', '.join(str(p) for p in references)}")
        failed = inventory_all(links, analyser, out_dir=out_dir, registry=registry)
        print(f"{len(links) - failed} of {len(links)} inventoried")
        return 1 if failed else 0
    tier = cast(Tier | None, args.tier)
    try:
        link = link_for(cast(str, args.url), references, category=args.category, tier=tier)
        inventory(link, analyser, out_dir=out_dir, registry=registry)
    except ReferenceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
