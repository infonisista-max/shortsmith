"""The fourth feedback loop: `python -m shortsmith.smoke`.

Walks the same path the tests walk, end to end, with every fake and no network:
generate the 12.1 fixture, ingest it the way the upload route does (`ingest.accept`,
not HTTP), run the job through the worker (`pipeline.Worker.run_next`, the same code
the web app's thread runs), assert `work/asr.json` and the job's
`uploaded -> transcribing -> planning` trail, print one summary line and exit 0. Any
failed assertion exits non-zero with the failing check on stderr. Later tickets extend
this walk step by step until it asserts T1-T13 (decision 12.1); over ninety seconds is
a bug.

The fixture is six seconds long, so smoke lowers only `Limits.min_duration_s`; every
other 2.1 limit stays at its default.

Everything happens in a temp directory that is removed afterwards.
"""

from __future__ import annotations

import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from shortsmith import fixture, ingest, jobs, pipeline
from shortsmith.contracts import Transcript
from shortsmith.ingest import Limits, VideoUpload
from shortsmith.transcriber import FakeTranscriber, Transcriber

EXPECTED_WORDS = 12
LAST_STATUS: jobs.Status = "planning"  # the first step with no implementation yet (003)
SMOKE_BRIEF = (
    "Topic: a six-second synthetic clip. Angle: prove the pipeline end to end. "
    "Must-say: twelve words on six tone bursts. Hook wish: none."
)
SMOKE_LIMITS = Limits(min_duration_s=fixture.DURATION_S)


class SmokeFailure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


@dataclass(frozen=True)
class SmokeResult:
    job_dir: Path
    summary: str


def run_smoke(root: Path, *, transcriber: Transcriber | None = None) -> SmokeResult:
    started = time.perf_counter()
    transcriber = transcriber or FakeTranscriber()

    clip = fixture.make_fixture(root / "fixture" / "fixture.mp4")
    check(clip.stat().st_size < 1_000_000, "fixture must be under 1 MB (12.1)")

    job = ingest.accept(
        root / "data",
        video=VideoUpload(path=clip, original_name="fixture.mp4"),
        brief=SMOKE_BRIEF,
        style_line="explainer",
        references=[],
        limits=SMOKE_LIMITS,
    )
    check(job.status == "uploaded", f"ingest left the job {job.status!r}, not 'uploaded'")
    check((job.input_dir / "raw.mp4").is_file(), "ingest did not write input/raw.mp4")
    check((job.input_dir / "brief.md").is_file(), "ingest did not write input/brief.md")
    check((job.input_dir / "refs.json").is_file(), "ingest did not write input/refs.json")

    worker = pipeline.Worker(transcriber=transcriber)
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
    log_lines = reloaded.log_path.read_text(encoding="utf-8").splitlines()
    trail = [line.split(" ", 1)[1] for line in log_lines]
    check(
        trail == ["created uploaded", "uploaded -> transcribing", "transcribing -> planning"],
        f"unexpected job.log trail {trail}",
    )

    elapsed = time.perf_counter() - started
    summary = (
        f"smoke ok: job {job.id} -> {reloaded.status}, {len(on_disk.words)} words in "
        f"work/asr.json, fixture {clip.stat().st_size // 1024} KiB, {elapsed:.1f}s"
    )
    return SmokeResult(job_dir=job.path, summary=summary)


def main(argv: list[str] | None = None, *, transcriber: Transcriber | None = None) -> int:
    with tempfile.TemporaryDirectory(prefix="shortsmith-smoke-") as tmp:
        try:
            result = run_smoke(Path(tmp), transcriber=transcriber)
        except Exception as exc:  # noqa: BLE001 - the smoke reports every failure the same way
            print(f"smoke FAILED: {exc}", file=sys.stderr)
            return 1
    print(result.summary)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
