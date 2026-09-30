"""The music-level slider (ticket 090; operator, 30 Sep 2026): "a music-volume slider on
the job page that sets the bed level for the whole reel, remixes only the audio so it is
quick".

- **The scale** (`assets/audio/level.yaml`, `load_scale`): the slider's ends, its step
  and the words at its ends, one file for all styles, checked at startup. A value is an
  offset in dB from the style's starting level on the `MEASURE` level measure.
- **The remix** (`remix`): from the job's stems alone - the delivered bed at the style's
  starting level plus the offset (`sound.relevel`), the duck, the premix, the master
  (`render.master`) and the remux with the picture stream copied (`render.remux`). No
  Remotion, no planner, no asset call. Everything is built in `work/stems/remix/` and
  beside `out/short.mp4`; the stems and the short are replaced only once the new file
  passes T4, the short by a rename. On any failure the old files stay.
- **The ear wins** (`ear_notes`): a setting is never repaired and never refused. A
  re-measured margin under the floor or over the ceiling is a plain note on the page.
- **Recorded**: `job.json` `music_level` (offset, measure, `slider`, time, notes) and one
  `music level:` line in `job.log` per remix. 091: every delivered remix is also the
  operator's remembered level (`sound.remembered`) the next job starts at.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml

from shortsmith import ffmpeg, jobs, render, sound, styles
from shortsmith.contracts import BalanceReport
from shortsmith.jobs import Job
from shortsmith.qa import technical
from shortsmith.sound import remembered

LEVEL_PATH = Path(__file__).resolve().parents[3] / "assets" / "audio" / "level.yaml"
MEASURE = render.LEVEL_MEASURE
SCRATCH_DIR = "remix"
REMIX_NAME = "short.remix.mp4"
# What the stems move back from `SCRATCH_DIR` once the new short passes T4.
REMIX_STEMS = ("music.wav", "music.ducked.wav", "premix.wav", "mix.wav", sound.BALANCE_NAME)

# The stated ranges (the comments in level.yaml say the same).
MIN_DB_RANGE = (-24.0, 0.0)  # the quiet end: under 0, not under -24
MAX_DB_RANGE = (0.0, 24.0)  # the loud end: over 0, not over 24
STEP_DB_MAX = 6.0

COVER_NOTE = "the check thinks the music may cover your voice here"
QUIET_NOTE = "the check thinks the music may be hard to hear on a phone speaker"
SWEPT_SENTENCE = (
    "The working files for this job were deleted 24 hours after upload, so its music "
    "level can no longer be changed."
)
NO_BED_SENTENCE = "This short has no music bed to set a level for."


class LevelError(ValueError):
    """`level.yaml` is malformed (the message names the key), or a remix could not be
    delivered (the message says why; the old short stays)."""


@dataclass(frozen=True)
class LevelScale:
    min_db: float
    max_db: float
    step_db: float
    quiet_label: str
    loud_label: str

    def contains(self, offset_db: float) -> bool:
        return self.min_db - 1e-9 <= offset_db <= self.max_db + 1e-9


KEYS = ("min_db", "max_db", "step_db", "quiet_label", "loud_label")


def _number(value: object, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise LevelError(f"{key} is not a number of dB")
    return float(value)


def _label(value: object, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LevelError(f"{key} is not a word or two for the slider's end")
    return value.strip()


def parse_scale(text: str, *, name: str) -> LevelScale:
    loaded: object = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise LevelError(f"{name}: not a mapping")
    data = cast(dict[str, Any], loaded)
    unknown = set(data) - set(KEYS)
    if unknown:
        raise LevelError(f"{name}: unknown key(s) {', '.join(sorted(unknown))}")
    missing = set(KEYS) - set(data)
    if missing:
        raise LevelError(f"{name}: missing key(s) {', '.join(sorted(missing))}")
    try:
        low = _number(data["min_db"], "min_db")
        if not MIN_DB_RANGE[0] <= low < MIN_DB_RANGE[1]:
            raise LevelError(f"min_db {low:g} is off its range: under 0, not under -24")
        high = _number(data["max_db"], "max_db")
        if not MAX_DB_RANGE[0] < high <= MAX_DB_RANGE[1]:
            raise LevelError(f"max_db {high:g} is off its range: over 0, not over 24")
        step = _number(data["step_db"], "step_db")
        if not 0 < step <= STEP_DB_MAX:
            raise LevelError(f"step_db {step:g} is off its range: over 0, at most {STEP_DB_MAX:g}")
        notches = -low / step
        if abs(notches - round(notches)) > 1e-9:
            raise LevelError(f"step_db {step:g} does not put 0 on a notch from min_db {low:g}")
        return LevelScale(
            min_db=low, max_db=high, step_db=step,
            quiet_label=_label(data["quiet_label"], "quiet_label"),
            loud_label=_label(data["loud_label"], "loud_label"),
        )  # fmt: skip
    except LevelError as exc:
        raise LevelError(f"{name}: {exc}") from None


def load_scale(path: Path = LEVEL_PATH) -> LevelScale:
    """The committed scale, checked; a missing file is a `LevelError`."""
    if not path.is_file():
        raise LevelError(f"{path.name}: not found at {path}")
    return parse_scale(path.read_text(encoding="utf-8"), name=path.name)


def ear_notes(balance: BalanceReport, nums: styles.Sound) -> list[str]:
    """The plain notes a slider setting gets instead of a repair: the lowest margin
    under the floor, the highest over the ceiling (the whole stem's and each window's)."""
    low, high = sound.speech_margins(balance)
    notes: list[str] = []
    if low is not None and low + 1e-9 < nums.speech_band_margin_db:
        notes.append(COVER_NOTE)
    if high is not None and sound.inaudible(high, nums):
        notes.append(QUIET_NOTE)
    return notes


def refusal(job: Job) -> str:
    """Why this job's level cannot be changed, or "" when it can: the page disables the
    slider for the same reason the route refuses."""
    if job.record.swept_at is not None:
        return SWEPT_SENTENCE
    stems = job.work_dir / "stems"
    beds = (stems / "music.wav", stems / sound.START_DIR / "music.wav")
    if not any(path.is_file() for path in beds):
        return NO_BED_SENTENCE
    return ""


@dataclass(frozen=True)
class Remixed:
    short: Path
    balance: BalanceReport
    notes: list[str]


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


Mixer = Callable[[Path, Path], tuple[Path, BalanceReport]]


def deliver(job: Job, mix: Mixer) -> BalanceReport:
    """The audio-only delivery 090's slider and 093's pick share: `mix(stems, scratch)`
    writes the new bed stems, the premix and `balance.json` into the scratch folder, then
    the master and the remux with the picture copied go beside the short. Only once the
    new file passes T4 do the stems move in and the short get renamed over; a mix that
    brings its own `START_DIR` (a new bed) replaces the old bed's, and the old bed's
    segment stems go. Raises `LevelError` with the old short and stems untouched."""
    why = refusal(job)
    if why:
        raise LevelError(why)
    stems = job.work_dir / "stems"
    picture = job.work_dir / "picture.mp4"
    for needed in (stems / "voice.wav", picture):
        if not needed.is_file():
            raise LevelError(f"{needed.relative_to(job.path).as_posix()} is missing")
    scratch = stems / SCRATCH_DIR
    shutil.rmtree(scratch, ignore_errors=True)
    staged = job.out_dir / REMIX_NAME
    try:
        try:
            premix, balance = mix(stems, scratch)
        except sound.SoundError as exc:
            raise LevelError(str(exc)) from exc
        render.master(premix, scratch / "mix.wav")
        render.remux(picture, scratch / "mix.wav", staged)
        check = technical.t4(ffmpeg.measure_loudness(staged))
        if not check.passed:
            raise LevelError(
                f"the remixed master missed T4 ({check.detail}); the short is unchanged"
            )
        if (scratch / sound.START_DIR).is_dir():
            shutil.rmtree(stems / sound.START_DIR, ignore_errors=True)
            for path in stems.glob("music.[0-9].wav"):
                path.unlink()
            os.replace(scratch / sound.START_DIR, stems / sound.START_DIR)
        for name in REMIX_STEMS:
            if (scratch / name).is_file():
                os.replace(scratch / name, stems / name)
        for path in sorted(scratch.glob("music.[0-9].wav")):
            os.replace(path, stems / path.name)
        os.replace(staged, job.out_dir / "short.mp4")
    finally:
        staged.unlink(missing_ok=True)
        shutil.rmtree(scratch, ignore_errors=True)
    return balance


def remix(job: Job, *, offset_db: float, now: Clock = _utc_now) -> Remixed:
    """The audio-only remix at `offset_db` (see the module note). Raises `LevelError`
    with the old short and stems untouched when it cannot deliver."""
    nums = render.loaded_styles()[job.record.style].sound
    balance = deliver(
        job, lambda stems, scratch: sound.relevel(stems, scratch, nums=nums, offset_db=offset_db)
    )
    notes = ear_notes(balance, nums)
    started = job.record.music_level
    stamp = now()
    jobs.amend(job, music_level=jobs.MusicLevel(
        offset_db=offset_db, measure=MEASURE, set_by="slider", set_at=stamp, notes=notes,
        from_job=started.from_job if started is not None else None,
        start_db=started.start_db if started is not None else 0.0,
    ))  # fmt: skip
    # 091: the next job starts here, whatever its style.
    remembered.save(jobs.data_dir_of(job), remembered.Remembered(
        offset_db=offset_db, measure=MEASURE, job_id=job.id, set_at=stamp,
    ))  # fmt: skip
    margin = balance.speech_band_margin_db
    jobs.note(
        job,
        f"music level: slider offset {offset_db:+g} dB ({MEASURE}), bed "
        f"{balance.bed_under_voice_db} dB under the voice, speech-band margin "
        f"{'none' if margin is None else f'{margin:.1f}'} dB"
        + (f"; {'; '.join(notes)}" if notes else ""),
        now=now,
    )
    return Remixed(short=job.out_dir / "short.mp4", balance=balance, notes=notes)
