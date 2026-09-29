"""`python -m shortsmith.reference`: the inventory and gaps commands (ticket 036).

    inventory <url> [--category C] [--tier A|B] [--style S] [--topic T] [--prompt v1|v2]
              [--out DIR] [--references FILE]
    inventory --all [--prompt v1|v2] [--out DIR] [--references FILE]
    gaps [--dir DIR]
    own <job_dir> [--dir DIR]

`inventory` builds the Gemini analyser from `.env` (`GEMINI_API_KEY`, `REFERENCE_MODEL`,
`REFERENCE_FPS`, `REFERENCE_ENDPOINT`), reads the link's tier and category from
`docs/references.md` unless the flags say otherwise, and writes
`docs/reference/inventory/<video_id>.json`: a v2 card by default (073), whose styles
come from the trace table in `styles/README.md` unless `--style` names them, and whose
topic `--topic` may set; `--prompt v1` writes a v1 card. The mood and topic files load
first; an unknown style or topic stops the tool before any request. `--all` does every
link in the file, one request each, moving past a failing video. `gaps` writes
`GAPS.md` beside the JSON. Exit 0 when every link was inventoried, 1 otherwise.

`own` (074) runs the pipeline's self-inventory step on one delivered job directory:
`out/short.mp4` through the same analyser and prompt, `out/inventory.json`, the ledger
rows, `out/meta.json` rewritten, and the comparison table printed against the style's
v2 cards in `--dir`. Exit 1 when the short was not analysed, with the reason.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from shortsmith import config, jobs, ledger, meta, render, vocab
from shortsmith.config import Settings
from shortsmith.reference import (
    INVENTORY_DIR,
    PROMPT_VERSION,
    PROMPT_VERSIONS,
    REFERENCES_FILES,
    PromptVersion,
    ReferenceError,
    Tier,
    gaps,
    inventory,
    inventory_all,
    link_for,
    links_in,
    own,
)
from shortsmith.reference.gemini import GeminiAnalyser, ReferenceAnalyser
from shortsmith.styles import STYLES_DIR


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
    inv.add_argument(
        "--prompt", choices=PROMPT_VERSIONS, default=PROMPT_VERSION, help="the card version"
    )
    inv.add_argument(
        "--style",
        action="append",
        help="a shipped style this reference informs (repeatable); default: the trace "
        "table in styles/README.md",
    )
    inv.add_argument("--topic", help="the card's topic, from assets/reference/topics.yaml")
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
    mine = commands.add_parser("own", help="run the self-inventory on a delivered job (074)")
    mine.add_argument("job_dir", type=Path, help="data/jobs/<job_id>")
    mine.add_argument("--dir", type=Path, default=INVENTORY_DIR, help="the reference cards")
    args = parser.parse_args(argv)

    if args.command == "gaps":
        path = gaps.write(cast(Path, args.dir))
        print(f"gap report written to {path}")
        return 0
    if args.command == "own":
        return _own(cast(Path, args.job_dir), cast(Path, args.dir), analyser, settings)

    if not args.all and not args.url:
        inv.error("give a url, or --all")
    out_dir = cast(Path, args.out)
    given = cast(list[Path] | None, args.references)
    references: Sequence[Path] = given if given else REFERENCES_FILES
    version = cast(PromptVersion, args.prompt)
    styles = cast(list[str] | None, args.style)
    topic = cast(str | None, args.topic)
    # 073: the closed lists load before any request; a broken file stops the tool
    lists = vocab.load()
    for style in styles or []:
        if not (STYLES_DIR / f"{style}.md").is_file():
            print(f"{style!r} is not a style in {STYLES_DIR}", file=sys.stderr)
            return 1
    if topic is not None and topic not in lists.topics.topics:
        print(f"{topic!r} is not a topic in {vocab.TOPICS_PATH.name}", file=sys.stderr)
        return 1
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
        failed = inventory_all(
            links, analyser, out_dir=out_dir, registry=registry, version=version,
            vocabulary=lists,
        )  # fmt: skip
        print(f"{len(links) - failed} of {len(links)} inventoried")
        return 1 if failed else 0
    tier = cast(Tier | None, args.tier)
    try:
        link = link_for(cast(str, args.url), references, category=args.category, tier=tier)
        inventory(
            link, analyser, out_dir=out_dir, registry=registry, version=version,
            vocabulary=lists, styles=styles, topic=topic,
        )  # fmt: skip
    except ReferenceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _own(
    job_dir: Path,
    inventory_dir: Path,
    analyser: ReferenceAnalyser | None,
    settings: Settings | None,
) -> int:
    """074: the `inventory` step on one job directory, `meta.json` rewritten, the table
    printed. With the real analyser each request is a ledger row priced from the prices
    file, exactly as in the pipeline."""
    vocab.load()
    job = jobs.load(job_dir)
    if analyser is None:
        loaded = settings if settings is not None else config.load()
        book = ledger.from_settings(loaded)
        step = own.SelfInventory(analyser_from(loaded), ledger=lambda: book)
    else:
        step = own.SelfInventory(analyser)
    result = step.run(job)
    meta.write(job, inventory_dir=inventory_dir)
    if isinstance(result, own.NotAnalysed):
        print(f"{job.id}: not analysed: {result.reason}", file=sys.stderr)
        return 1
    found = own.summary(job, inventory_dir)
    table = found.comparison if found is not None else None
    assert table is not None
    print(f"{job.id} ({table.style}): {table.references} v2 reference cards {table.note}")
    for row in table.rows:
        spread = "" if row.low is None else f"  median {row.median:g}  {row.low:g}-{row.high:g}"
        extra = f"  refs {row.refs}" if row.refs else ""
        plan = f"  plan {row.plan}" if row.plan is not None else ""
        flag = "  OUTSIDE" if row.outside else ""
        print(f"  {row.name}: {row.ours}{plan}{spread}{extra}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
