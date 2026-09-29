"""Re-mix one delivered job's audio with today's sound director (ticket 070's operator step).

    uv run python -m shortsmith.sound.remix data/jobs/<job_id> --out work/070

Reads the job's snapped plan (`work/plan.json`), its sound story (`work/sound.json`),
its style and its voice stem (`work/stems/voice.wav`), and runs `sound.build_mix` into
`--out` with the approved library (`assets/audio/catalog.yaml`) and, for the bed only,
the audio search `.env` configures. The job folder is never written. Leaves
`<out>/mix.wav` (the premix: voice, bed and cues) beside the stems, and prints one line
per placed cue - its time, its palette kind and its library file - for the phone check.
A story written before 070 names cues outside the palette; the director drops those
with a line and marks the pop-ins and transitions itself.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from shortsmith import config, jobs, presenter, render, sound
from shortsmith.sound import freesound

DEFAULT_OUT = Path("work") / "070"
MIX_NAME = "mix.wav"


def cue_lines(result: sound.MixResult) -> list[str]:
    """One line per placed cue: time, palette kind, source, beat and library file."""
    lines: list[str] = []
    for cue in result.cues:
        entry = result.library.entry(cue.entry_id)
        file = entry.file if entry is not None else cue.entry_id
        lines.append(
            f"{cue.at_s:6.2f} s  {sound.cue_kind(cue):<6}  {cue.source:<7}  {cue.beat_id:<4}  "
            f"{file}"
        )
    return lines


def remix(
    job_dir: Path,
    out: Path,
    *,
    library: sound.Library | None = None,
    search: sound.AudioSearch | None = None,
    log: bool = True,
) -> sound.MixResult:
    job = jobs.load(job_dir)
    story = render._load_story(job)  # pyright: ignore[reportPrivateUsage]
    if story is None:
        raise SystemExit(f"{job_dir}: no work/sound.json to re-mix")
    voice = job.work_dir / "stems" / "voice.wav"
    if not voice.is_file():
        raise SystemExit(f"{job_dir}: no work/stems/voice.wav to mix under")
    plan = render._load_plan(job)  # pyright: ignore[reportPrivateUsage]
    spec = render.loaded_styles()[job.record.style]
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(voice, out / "voice.wav")
    result = sound.build_mix(
        stems=out, voice=out / "voice.wav", plan=plan, story=story, nums=spec.sound,
        library=library if library is not None else sound.load_catalogue(),
        runtime_s=presenter.total_duration(presenter.cut_list(plan)), search=search,
        counter_land_s=render.counter_land_s(spec),
        log=(lambda line: print(f"sound: {line}")) if log else None,
    )  # fmt: skip
    shutil.copy(result.premix, out / MIX_NAME)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m shortsmith.sound.remix")
    parser.add_argument("job", type=Path, help="the job folder, e.g. data/jobs/<job_id>")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where the stems go")
    args = parser.parse_args(argv)
    result = remix(args.job, args.out, search=freesound.from_settings(config.load()))
    print(result.summary())
    print(f"{len(result.cues)} cues, mix at {args.out / MIX_NAME}:")
    for line in cue_lines(result):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
