"""The fourth feedback loop: `python -m shortsmith.smoke`.

Walks the same path the tests walk, end to end, with every fake and no network:
generate the 12.1 fixture, ingest it the way the upload route does (`ingest.accept`,
not HTTP), run the job through the worker (`pipeline.Worker.run_next`, the same code
the web app's thread runs) with the fake transcriber, the fake planner and the real
Remotion renderer, assert `work/asr.json`, `work/plan.json`, `work/sound.json`,
`work/captions.json`, `work/picture.mp4` (H.264, 1080x1920, round(6 x 30) frames,
silent), `out/short.mp4`, `out/qa.json` with T1-T4 passing, `out/contact.jpg` under
2 MB at the sheet's width, and the job's `uploaded -> ... -> qa -> delivered` trail,
print one summary line and exit 0. Any failed assertion exits non-zero with the
failing check on stderr. Later tickets extend this walk until it asserts T1-T13
(decision 12.1); over ninety seconds is a bug.

The fixture is six seconds long, so smoke lowers only `Limits.min_duration_s`; every
other 2.1 limit stays at its default.

Everything happens in a temp directory that is removed afterwards, unless
`SHORTSMITH_SMOKE_KEEP=1` (ticket 049): then the run lands under `work/smoke/` beneath
the current directory, survives, and the summary line ends with the absolute path of
`picture.mp4` so the operator can watch the render. `work/` is git-ignored.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pydantic import TypeAdapter

from shortsmith import contact_sheet, ffmpeg, fixture, ingest, jobs, pipeline, render, styles
from shortsmith.contracts import TIER1_KINDS, CaptionPage, PicturePlan, SoundStory, Transcript
from shortsmith.ingest import Limits, VideoUpload
from shortsmith.planner import FakePlanner, Planner, kinds_named
from shortsmith.qa import technical
from shortsmith.render import Renderer
from shortsmith.transcriber import FakeTranscriber, Transcriber

EXPECTED_WORDS = 12
EXPECTED_FRAMES = round(fixture.DURATION_S * fixture.FPS)
LAST_STATUS: jobs.Status = "delivered"
TRAIL = [
    "created uploaded",
    "uploaded -> transcribing",
    "transcribing -> planning",
    "planning -> sourcing",
    "sourcing -> rendering",
    "rendering -> qa",
    "qa -> delivered",
]
TECHNICAL_CHECKS = ("T1", "T2", "T3", "T4")  # grows with the gate tickets
_PAGES = TypeAdapter(list[CaptionPage])
SMOKE_BRIEF = (
    "Topic: a six-second synthetic clip. Angle: prove the pipeline end to end. "
    "Must-say: twelve words on six tone bursts. Hook wish: none."
)
SMOKE_STYLE_LINE = "explainer, energetic"
SMOKE_LIMITS = Limits(min_duration_s=fixture.DURATION_S)


class SmokeFailure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


KEEP_ENV = "SHORTSMITH_SMOKE_KEEP"
KEEP_DIR = Path("work") / "smoke"
TMP_PREFIX = "shortsmith-smoke-"


@dataclass(frozen=True)
class SmokeResult:
    job_dir: Path
    summary: str
    picture: Path


def run_smoke(
    root: Path,
    *,
    transcriber: Transcriber | None = None,
    planner: Planner | None = None,
    renderer: Renderer | None = None,
) -> SmokeResult:
    started = time.perf_counter()
    transcriber = transcriber or FakeTranscriber()
    planner = planner or FakePlanner()

    clip = fixture.make_fixture(root / "fixture" / "fixture.mp4")
    check(clip.stat().st_size < 1_000_000, "fixture must be under 1 MB (12.1)")

    # 008: every spec loads against the registry, and the style line resolves in code.
    specs = styles.load_all(render.registry())
    check(styles.shipped(specs) == ["explainer"], f"shipped styles: {styles.shipped(specs)}")
    resolution = styles.resolve(SMOKE_STYLE_LINE, specs)
    check(resolution.name == "explainer" and resolution.notice == "", f"resolved {resolution}")

    job = ingest.accept(
        root / "data",
        video=VideoUpload(path=clip, original_name="fixture.mp4"),
        brief=SMOKE_BRIEF,
        style=resolution,
        references=[],
        limits=SMOKE_LIMITS,
    )
    check(job.status == "uploaded", f"ingest left the job {job.status!r}, not 'uploaded'")
    check(
        (job.record.style, job.record.style_note) == ("explainer", SMOKE_STYLE_LINE),
        "job.json does not carry the resolved style and note",
    )
    check((job.input_dir / "raw.mp4").is_file(), "ingest did not write input/raw.mp4")
    check((job.input_dir / "brief.md").is_file(), "ingest did not write input/brief.md")
    check((job.input_dir / "refs.json").is_file(), "ingest did not write input/refs.json")

    worker = pipeline.Worker(
        transcriber=transcriber, planner=planner, renderer=renderer, specs=specs
    )
    worker.submit(job.path)
    check(worker.run_next(), "the worker had nothing to run")

    # Assertions: re-read from disk, the way the next step will.
    reloaded = jobs.load(job.path)
    if reloaded.record.error is not None:
        err = reloaded.record.error
        raise SmokeFailure(f"job failed at {err.step}: {err.message} ({err.detail.strip()})")
    check(reloaded.status == LAST_STATUS, f"job status is {reloaded.status}")
    asr_path = job.work_dir / "asr.json"
    check(asr_path.is_file(), "worker did not write work/asr.json")
    on_disk = Transcript.model_validate_json(asr_path.read_text(encoding="utf-8"))
    check(
        len(on_disk.words) == EXPECTED_WORDS,
        f"expected {EXPECTED_WORDS} words in work/asr.json, got {len(on_disk.words)}",
    )
    for i, burst_start in enumerate(fixture.BURST_TIMES):
        burst_end = burst_start + fixture.BURST_LEN_S
        for w in on_disk.words[2 * i : 2 * i + 2]:
            check(
                burst_start <= w.start < w.end <= burst_end + 1e-9,
                f"word {w.text!r} [{w.start}, {w.end}] is outside burst {i} "
                f"[{burst_start}, {burst_end}]",
            )
    plan_path, sound_path, captions_path = (
        job.work_dir / name for name in ("plan.json", "sound.json", "captions.json")
    )
    for path in (plan_path, sound_path, captions_path):
        check(path.is_file(), f"planning did not write work/{path.name}")
    plan = PicturePlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    story = SoundStory.model_validate_json(sound_path.read_text(encoding="utf-8"))
    pages = _PAGES.validate_json(captions_path.read_text(encoding="utf-8"))
    check(
        plan.beats[0].start == 0.0 and plan.beats[-1].end == fixture.DURATION_S,
        "plan beats do not tile the fixture",
    )
    check(
        all(a.end == b.start for a, b in zip(plan.beats, plan.beats[1:], strict=False)),
        "plan beats have a gap or overlap",
    )
    missing = set(TIER1_KINDS) - kinds_named(plan)
    check(not missing, f"plan does not name every tier-1 kind: {sorted(missing)}")
    beat_ids = {b.id for b in plan.beats}
    check(all(c.beat_id in beat_ids for c in story.cues), "a sound cue names an unknown beat")
    check(all(2 <= len(p.word_indices) <= 4 for p in pages), "a caption page is not 2-4 words")
    check(
        sum(len(p.word_indices) for p in pages) == EXPECTED_WORDS,
        "caption pages do not cover every word",
    )
    picture = job.work_dir / "picture.mp4"
    check(picture.is_file(), "rendering did not write work/picture.mp4")
    check((job.work_dir / "render_spec.json").is_file(), "rendering did not write render_spec.json")
    check((job.work_dir / "render.log").is_file(), "rendering did not keep work/render.log")
    frames = check_picture(picture)
    check_cut(job.work_dir / "cut.mp4")
    for stem in ("voice.wav", "mix.wav"):
        check((job.work_dir / "stems" / stem).is_file(), f"rendering did not write stems/{stem}")
    short = job.out_dir / "short.mp4"
    check(short.is_file(), "rendering did not write out/short.mp4")
    short_s, short_lufs = check_short(short, picture)
    check_qa(reloaded)
    sheet = job.out_dir / "contact.jpg"
    check_contact_sheet(sheet)
    log_lines = reloaded.log_path.read_text(encoding="utf-8").splitlines()
    trail = [line.split(" ", 1)[1] for line in log_lines]
    check(trail == TRAIL, f"unexpected job.log trail {trail}")

    elapsed = time.perf_counter() - started
    summary = (
        f"smoke ok: job {job.id} -> {reloaded.status}, {len(on_disk.words)} words, "
        f"{len(plan.beats)} beats, {len(story.cues)} cues, {len(pages)} caption pages, "
        f"picture {frames} frames {picture.stat().st_size // 1024} KiB, "
        f"short {short_s:.1f} s {short_lufs:.1f} LUFS {short.stat().st_size // 1024} KiB, "
        f"{TECHNICAL_CHECKS[0]}-{TECHNICAL_CHECKS[-1]} pass, "
        f"contact {sheet.stat().st_size // 1024} KiB, "
        f"fixture {clip.stat().st_size // 1024} KiB, {elapsed:.1f}s"
    )
    return SmokeResult(job_dir=job.path, summary=summary, picture=picture)


def check_qa(job: jobs.Job) -> None:
    """`out/qa.json` per ticket 006: T1-T4 ran in order and every one passed (10.1)."""
    report = technical.load_report(job)
    check(report is not None, "qa did not write out/qa.json")
    assert report is not None
    names = [c.name for c in report.checks]
    check(names == list(TECHNICAL_CHECKS), f"qa.json lists {names}, expected {TECHNICAL_CHECKS}")
    for c in report.checks:
        check(c.passed, f"{c.name} failed: {c.detail}")
    check(report.passed, "qa.json says the report failed although every check passed")


def check_contact_sheet(sheet: Path) -> None:
    """`out/contact.jpg` per 10.4: a JPEG at the sheet width, under 2 MB, laid out for
    the fixture's eight hook frames and six per-second frames."""
    check(sheet.is_file(), "qa did not write out/contact.jpg")
    check(sheet.stat().st_size < contact_sheet.MAX_BYTES, "contact.jpg is 2 MB or more")
    expected = contact_sheet.layout(contact_sheet.HOOK_FRAMES, round(fixture.DURATION_S))
    with Image.open(sheet) as image:
        check(image.format == "JPEG", f"contact.jpg is {image.format}, not JPEG")
        check(
            image.size == (expected.width, expected.height),
            f"contact.jpg is {image.size[0]}x{image.size[1]}, "
            f"expected {expected.width}x{expected.height}",
        )


def check_cut(cut: Path) -> None:
    """`work/cut.mp4` per ticket 005: CFR 30 fps H.264 with no B-frames, plus audio."""
    check(cut.is_file(), "rendering did not write work/cut.mp4")
    streams = ffmpeg.probe(cut)["streams"]
    kinds = [s.get("codec_type") for s in streams]
    check(kinds == ["video", "audio"], f"cut.mp4 streams are {kinds}, expected video + audio")
    video = streams[0]
    check(video.get("codec_name") == "h264", f"cut.mp4 codec is {video.get('codec_name')}")
    check(int(video.get("has_b_frames", 1)) == 0, "cut.mp4 has B-frames")
    rates = (video.get("r_frame_rate"), video.get("avg_frame_rate"))
    check(rates == ("30/1", "30/1"), f"cut.mp4 is not constant 30 fps: {rates}")
    frames = int(video.get("nb_frames", 0))
    check(frames == EXPECTED_FRAMES, f"cut.mp4 has {frames} frames, expected {EXPECTED_FRAMES}")


def check_short(short: Path, picture: Path) -> tuple[float, float]:
    """`out/short.mp4` per ticket 005: the picture stream copied bit-for-bit, audio
    present, the fixture's length, the master near -14 LUFS (T4 proper is 006)."""
    info = ffmpeg.probe(short)
    kinds = sorted(s.get("codec_type") for s in info["streams"])
    check(kinds == ["audio", "video"], f"short.mp4 streams are {kinds}, expected video + audio")
    check(
        ffmpeg.video_md5(short) == ffmpeg.video_md5(picture),
        "short.mp4 video stream differs from picture.mp4 (mux re-encoded the picture)",
    )
    duration = float(info["format"]["duration"])
    check(
        abs(duration - fixture.DURATION_S) <= 0.1,
        f"short.mp4 is {duration:.2f} s, expected {fixture.DURATION_S:g} s",
    )
    lufs = ffmpeg.measure_loudness(short).integrated
    check(abs(lufs + 14.0) <= 1.0, f"short.mp4 master is {lufs:.1f} LUFS, expected about -14")
    return duration, lufs


def check_picture(picture: Path) -> int:
    """`work/picture.mp4` per ticket 004: silent H.264, 1080x1920, round(6 x 30) frames."""
    streams = ffmpeg.probe(picture)["streams"]
    kinds = [s.get("codec_type") for s in streams]
    check(kinds == ["video"], f"picture.mp4 streams are {kinds}, expected one silent video")
    video = streams[0]
    check(video.get("codec_name") == "h264", f"picture.mp4 codec is {video.get('codec_name')}")
    size = (int(video.get("width", 0)), int(video.get("height", 0)))
    check(size == (fixture.WIDTH, fixture.HEIGHT), f"picture.mp4 is {size[0]}x{size[1]}")
    frames = int(video.get("nb_frames", 0))
    check(frames == EXPECTED_FRAMES, f"picture.mp4 has {frames} frames, expected {EXPECTED_FRAMES}")
    return frames


def keep_requested() -> bool:
    return os.environ.get(KEEP_ENV) == "1"


@contextmanager
def workspace(keep: bool) -> Generator[Path]:
    """The smoke's root: a system temp directory removed on exit, or, in keep mode,
    a fresh directory under `work/smoke/` that is never removed."""
    if keep:
        KEEP_DIR.mkdir(parents=True, exist_ok=True)
        yield Path(tempfile.mkdtemp(prefix=TMP_PREFIX, dir=KEEP_DIR))
        return
    with tempfile.TemporaryDirectory(prefix=TMP_PREFIX) as tmp:
        yield Path(tmp)


def main(
    argv: list[str] | None = None,
    *,
    transcriber: Transcriber | None = None,
    planner: Planner | None = None,
) -> int:
    keep = keep_requested()
    with workspace(keep) as root:
        try:
            result = run_smoke(root, transcriber=transcriber, planner=planner)
        except Exception as exc:  # noqa: BLE001 - the smoke reports every failure the same way
            print(f"smoke FAILED: {exc}", file=sys.stderr)
            return 1
    summary = result.summary
    if keep:
        summary += f", kept {result.picture.resolve()}"
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
