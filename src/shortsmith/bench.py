"""`python -m shortsmith.bench`: seconds per frame for the explainer composition.

Renders the 12.1 fixture through the same spec builder and driver the pipeline uses
(fake transcriber and planner, real Remotion, concurrency 2) and prints one line:
seconds per frame, frames, render seconds, bundle seconds, total seconds. Ticket 007
records the figure per box in `docs/bench.md`; nothing is recorded here.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from shortsmith import captions, fixture, jobs, render
from shortsmith.contracts import Constraints, PlanRequest, PlanStyle
from shortsmith.planner import FakePlanner
from shortsmith.render import DriverResult
from shortsmith.transcriber import FakeTranscriber

BRIEF = "Topic: the bench. Angle: seconds per frame on this box. Must-say: nothing."


def report(result: DriverResult, *, concurrency: int) -> str:
    per_frame = result.render_s / max(1, result.frames)
    return (
        f"bench: {per_frame:.3f} s/frame, {result.frames} frames, "
        f"{result.render_s:.1f} s render, {result.bundle_s:.1f} s bundle, "
        f"{result.wall_s:.1f} s total, concurrency {concurrency}"
    )


def run_bench(root: Path, *, concurrency: int = render.CONCURRENCY) -> DriverResult:
    clip = fixture.make_fixture(root / "fixture" / "fixture.mp4")
    job = jobs.create(root / "data")
    shutil.copyfile(clip, job.input_dir / "raw.mp4")
    transcript = FakeTranscriber().transcribe(clip)
    request = PlanRequest(
        brief=BRIEF,
        style=PlanStyle(name="explainer"),
        style_note="explainer",
        transcript=transcript,
        references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=transcript.duration_s),
        asset_policy="any",
    )
    plan = FakePlanner().plan_picture(request)
    paged = captions.build(transcript, plan, render.loaded_styles()["explainer"])
    (job.work_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    (job.work_dir / "asr.json").write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    (job.work_dir / "captions.json").write_text(paged.model_dump_json(), encoding="utf-8")
    render.cut_presenter(job)  # the composition reads work/cut.mp4 (005); not timed
    out_dir = root / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    return render.run_driver(
        render.spec_for_job(job),
        spec_path=out_dir / "render_spec.json",
        out_path=out_dir / "picture.mp4",
        log_path=out_dir / "render.log",
        concurrency=concurrency,
    )


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    concurrency = render.CONCURRENCY
    args = list(argv or [])
    if len(args) == 2 and args[0] == "--concurrency" and args[1].isdigit():
        concurrency = int(args[1])
    elif args:
        print("usage: python -m shortsmith.bench [--concurrency N]", file=sys.stderr)
        return 2
    try:
        if root is not None:
            result = run_bench(root, concurrency=concurrency)
        else:
            with tempfile.TemporaryDirectory(prefix="shortsmith-bench-") as tmp:
                result = run_bench(Path(tmp), concurrency=concurrency)
    except Exception as exc:  # noqa: BLE001 - one line on stderr, non-zero exit
        print(f"bench FAILED: {exc}", file=sys.stderr)
        return 1
    print(report(result, concurrency=concurrency))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
