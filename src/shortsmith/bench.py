"""`python -m shortsmith.bench`: seconds per frame for the explainer composition.

Renders the 12.1 fixture through the same spec builder and driver the pipeline uses
(fake transcriber and planner, real Remotion, concurrency 2) and prints one line:
seconds per frame, frames, render seconds, bundle seconds, total seconds. Ticket 007
records the figure per box in `docs/bench.md`; nothing is recorded here.

`python -m shortsmith.bench --treatments OUT [--image PATH]` (ticket 103) renders one
short beat per picture treatment (photo, crop_fill, backdrop, polaroid, card) of one
image over the fixture's presenter - `PATH`, or a generated test pattern - and saves each
beat's landed frame (two before its end) as `OUT/103_<treatment>.png`. The face
`crop_fill` frames is the 3.3 detector's, or a box round the image's upper middle where
it finds none.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from shortsmith import captions, ffmpeg, fixture, jobs, presenter, render
from shortsmith.contracts import (
    PICTURE_TREATMENTS,
    BeatSpec,
    Captions,
    Constraints,
    Crop,
    FaceBox,
    PicturePlan,
    PlanRequest,
    PlanStyle,
    VisualSpec,
)
from shortsmith.planner import FakePlanner
from shortsmith.render import DriverResult
from shortsmith.transcriber import FakeTranscriber

BRIEF = "Topic: the bench. Angle: seconds per frame on this box. Must-say: nothing."
# 103: frames per treatment beat - long enough for the polaroid's drop to land.
TREATMENT_FRAMES = 15
TEST_PATTERN = (870, 614)  # run05's red-card owner photo: a low-res landscape


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


def treatment_visual(name: str, src: str, size: tuple[int, int], *, face: FaceBox,
                     numbers: render.StyleNumbers, pip_top: int) -> VisualSpec:  # fmt: skip
    """103: `src` drawn as the treatment `name`, whatever the image allows."""
    w, h = size
    crop = Crop()
    match name:
        case "photo":
            return render.photo_visual(src, w, h, index=0, crop=crop, numbers=numbers)
        case "crop_fill":
            return render.crop_fill_visual(src, w, h, face=face, numbers=numbers)
        case "backdrop":
            return render.backdrop_visual(src, w, h, ring=False, crop=crop, numbers=numbers,
                                          pip_top=pip_top)  # fmt: skip
        case "polaroid":
            return render.polaroid_visual(src, w, h, label="polaroid 103", ring=False, use=1,
                                          crop=crop, numbers=numbers, pip_top=pip_top)  # fmt: skip
        case _:
            return render.card_visual(src, w, h, strip_text="card 103", ring=True, index=0,
                                      crop=Crop(focus_x=0.5, focus_y=0.45), numbers=numbers,
                                      pip_top=pip_top)  # fmt: skip


def treatment_beats(src: str, size: tuple[int, int], *, numbers: render.StyleNumbers,
                    pip_top: int, face: FaceBox) -> list[BeatSpec]:  # fmt: skip
    """103: one `TREATMENT_FRAMES`-frame `pip` beat per picture treatment, in order."""
    return [
        BeatSpec(
            id=f"t_{name}", start_frame=i * TREATMENT_FRAMES,
            end_frame=(i + 1) * TREATMENT_FRAMES, mode="pip", kind="photo",
            visual=treatment_visual(name, src, size, face=face, numbers=numbers,
                                    pip_top=pip_top),
        )
        for i, name in enumerate(PICTURE_TREATMENTS)
    ]  # fmt: skip


def _pattern(path: Path, size: tuple[int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run([ffmpeg.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i",
                f"testsrc2=s={size[0]}x{size[1]}", "-frames:v", "1", str(path)])  # fmt: skip
    return path


def _base_plan() -> PicturePlan:
    """A one-second plan of one `pip` photo beat, the base the treatment beats replace."""
    return PicturePlan.model_validate({
        "prompt_version": "bench", "cut": {"keep": [{"start": 0.0, "end": 1.0}]},
        "beats": [{"id": "b01", "start": 0.0, "end": 1.0, "mode": "pip", "kind": "photo"}],
        "finale": {"beat_id": "none", "text": ""}, "title": "bench", "description": "bench",
    })  # fmt: skip


def run_treatments(root: Path, out: Path, *, image: Path | None = None,
                   concurrency: int = render.CONCURRENCY) -> list[Path]:  # fmt: skip
    """103: renders `treatment_beats` over the fixture's presenter and saves each beat's
    landed frame as `out/103_<treatment>.png`; returns the PNGs."""
    clip = fixture.make_fixture(root / "fixture" / "fixture.mp4")
    if image is not None:  # the driver serves the presenter's and the images' common folder
        src = Path(shutil.copyfile(image, root / f"image{image.suffix}")).resolve()
    else:
        src = _pattern(root / "pattern.png", TEST_PATTERN).resolve()
    size = ffmpeg.video_size(src)
    face = presenter.HaarDetector().detect(src) or FaceBox(
        left=size[0] // 3, top=size[1] // 6, width=size[0] // 3, height=size[1] // 3
    )
    numbers = render.style_numbers("explainer")
    base = render.build_spec(
        _base_plan(), Captions(pages=[]), presenter=clip, source_size=ffmpeg.video_size(clip),
        duration_s=1.0, numbers=numbers,
    )  # fmt: skip
    beats = treatment_beats(str(src), size, numbers=numbers, pip_top=base.pip.top, face=face)
    spec = base.model_copy(update={"beats": beats, "frames": len(beats) * TREATMENT_FRAMES})
    work = root / "treatments"
    work.mkdir(parents=True, exist_ok=True)
    render.run_driver(spec, spec_path=work / "render_spec.json", out_path=work / "picture.mp4",
                      log_path=work / "render.log", concurrency=concurrency)  # fmt: skip
    out.mkdir(parents=True, exist_ok=True)
    stills: list[Path] = []
    for beat in beats:
        name = beat.id.removeprefix("t_")
        at_s = (beat.end_frame - 2) / spec.fps  # landed, clear of the file's last frame
        stills.append(ffmpeg.still(work / "picture.mp4", out / f"103_{name}.png", at_s=at_s))
    return stills


Args = tuple[int, Path | None, Path | None]


def parse_args(args: list[str]) -> Args | None:
    """(concurrency, treatments out dir, image), or None on a usage error."""
    concurrency, out, image = render.CONCURRENCY, None, None
    rest = list(args)
    while rest:
        flag = rest.pop(0)
        if not rest:
            return None
        value = rest.pop(0)
        if flag == "--concurrency" and value.isdigit():
            concurrency = int(value)
        elif flag == "--treatments":
            out = Path(value)
        elif flag == "--image":
            image = Path(value)
        else:
            return None
    if image is not None and out is None:
        return None
    return concurrency, out, image


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    parsed = parse_args(list(argv or []))
    if parsed is None:
        print("usage: python -m shortsmith.bench [--concurrency N] "
              "[--treatments OUT [--image PATH]]", file=sys.stderr)  # fmt: skip
        return 2
    concurrency, out, image = parsed
    try:
        if out is not None:
            with tempfile.TemporaryDirectory(prefix="shortsmith-bench-") as tmp:
                stills = run_treatments(root or Path(tmp), out, image=image,
                                        concurrency=concurrency)  # fmt: skip
            print(f"bench: {len(stills)} treatment stills in {out}")
            return 0
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
