"""`python -m shortsmith.compare_plan <job_dir>`: did the worked examples help? (ticket 077)

    uv run python -m shortsmith.compare_plan data/jobs/<job_id> [--dir DIR]

Re-plans the job's picture once **without** worked examples - plan only, no render, one
call on the planner `PLANNER` selects, bound to the job so a real adapter writes its
prompt under `work/planner/run<n>/` and records its ledger row - and prints the match
share of both plans by the same rule (`reference.examples.plan_match`: a named entity
depicted, or an entity or a number as the subject). The job's own `work/plan.json` (the
plan made with the examples `job.json` names) is left as it is; the bare plan is written
to `work/plan.no_examples.json`. This is the run05 measure (079). Exit 1 when the job has
no plan or the planner cannot answer.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from shortsmith import config, jobs, ledger, pipeline, render, styles
from shortsmith import planner as planner_module
from shortsmith.contracts import PicturePlan
from shortsmith.planner import PlanInvalid, Planner, PlannerError
from shortsmith.reference import INVENTORY_DIR, examples
from shortsmith.styles import StyleSpec

BARE_PLAN = "plan.no_examples.json"


def _share(plan: PicturePlan) -> str:
    matched, total = examples.plan_match(plan)
    share = matched / total if total else 0.0
    return f"{share:.2f} ({matched} of {total} beats)"


def main(
    argv: Sequence[str] | None = None,
    *,
    planner: Planner | None = None,
    specs: Mapping[str, StyleSpec] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m shortsmith.compare_plan")
    parser.add_argument("job_dir", type=Path, help="data/jobs/<job_id>")
    parser.add_argument("--dir", type=Path, default=INVENTORY_DIR, help="the reference cards")
    args = parser.parse_args(argv)

    job = jobs.load(cast(Path, args.job_dir))
    plan_path = job.work_dir / "plan.json"
    if not plan_path.is_file():
        print(f"{job.id}: no work/plan.json to compare", file=sys.stderr)
        return 1
    ours = PicturePlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    if planner is None:
        settings = config.load()
        book = ledger.from_settings(settings)
        planner = planner_module.from_settings(settings, ledger=lambda: book, reload=config.load)
    loaded = specs if specs is not None else styles.load_all(render.registry())
    request = pipeline.build_plan_request(job, loaded, cast(Path, args.dir))
    bare_request = request.model_copy(update={"examples": []})
    try:
        bare = planner.bind(job).plan_picture(bare_request)
    except (PlanInvalid, PlannerError) as exc:
        print(f"{job.id}: the re-plan without examples failed: {exc}", file=sys.stderr)
        return 1
    (job.work_dir / BARE_PLAN).write_text(bare.model_dump_json(indent=2), encoding="utf-8")
    used = ", ".join(job.record.examples) or "none"
    topic = job.record.topic or "none (style only)"
    print(f"{job.id} ({job.record.style}, topic {topic})")
    print(f"  with examples ({used}): {_share(ours)}")
    print(f"  without examples: {_share(bare)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
