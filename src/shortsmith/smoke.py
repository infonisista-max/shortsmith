"""The fourth feedback loop: `python -m shortsmith.smoke`.

Walks the same path the tests walk, end to end, with every fake and no network:
generate the 12.1 fixture, create a job, copy the clip to `input/raw.mp4`, run the
fake transcriber, write `work/asr.json`, move `uploaded -> transcribing -> planning`,
assert the transcript, print one summary line and exit 0. Any failed assertion exits
non-zero with the failing check on stderr. Later tickets extend this walk step by
step until it asserts T1-T13 (decision 12.1); over ninety seconds is a bug.

Everything happens in a temp directory that is removed afterwards.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from shortsmith import fixture, jobs
from shortsmith.contracts import Transcript
from shortsmith.transcriber import FakeTranscriber, Transcriber

EXPECTED_WORDS = 12
NEXT_STATUS_AFTER_TRANSCRIBING: jobs.Status = "planning"


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

    job = jobs.create(root / "data", style_line="explainer")
    raw = job.input_dir / "raw.mp4"
    shutil.copyfile(clip, raw)

    job = jobs.transition(job, "transcribing")
    transcript = transcriber.transcribe(raw)
    asr_path = job.work_dir / "asr.json"
    asr_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    job = jobs.transition(job, NEXT_STATUS_AFTER_TRANSCRIBING)

    # Assertions: re-read from disk, the way the next step will.
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
    reloaded = jobs.load(job.path)
    check(reloaded.status == NEXT_STATUS_AFTER_TRANSCRIBING, f"job status is {reloaded.status}")
    log_lines = reloaded.log_path.read_text(encoding="utf-8").splitlines()
    check(len(log_lines) == 3, f"expected 3 job.log lines, got {len(log_lines)}")

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
