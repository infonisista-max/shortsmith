"""Pick another bed for the reel on the job page (ticket 093; operator, 30 Sep 2026): "let
me pick a different bed for the reel from the approved library (the few that fit the
plan's mood, plus the facts default), with the same quick audio-only remix."

- **The choices** (`fitting_beds`, `choices`): the approved beds (088's heard set - the
  tracked catalogue, never one a search fetched) of any mood the sound story plans, the
  mood + flavour matches of every segment first, then the mood alone, then every
  `facts_default` bed (087). A CC BY bed with no author to credit is never offered: it
  would ship without its attribution. The bed now playing is marked.
- **One bed for the reel** (`pick`): the pick plays under the whole reel - a 076 change
  is replaced (`REPLACES_CHANGE`) - with the story's envelope, at the style's starting
  level plus the reel's slider offset (`sound.repick`), through 090's delivery
  (`level.deliver`): duck, premix, master, remux with the picture copied, T4 gate, atomic
  replace. No Remotion, planner or search call. The ear wins: never repaired.
- **Rights**: the old bed's rows are replaced by the new bed's, in the log and the
  credits the description carries (`rights.replace_music`).
- **Recorded**: `job.json` `bed_pick` (entry id, time), the ear notes on `music_level`,
  and one `bed pick:` line in `job.log`. 091's remembered level is the slider's alone.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from shortsmith import jobs, presenter, render, rights, sound
from shortsmith.contracts import AudioEntry, BalanceReport, PicturePlan, SoundStory
from shortsmith.jobs import Job
from shortsmith.sound import level

SWEPT_SENTENCE = (
    "The working files for this job were deleted 24 hours after upload, so its music bed "
    "can no longer be changed."
)
NO_BED_SENTENCE = "This short has no music bed to change."
NOT_OFFERED = "That bed is not one of the approved beds that fit this reel."
REPLACES_CHANGE = (
    "The plan changes the bed partway through; a picked bed plays under the whole reel "
    "and replaces the change."
)


class PickError(level.LevelError):
    """A pick could not be delivered (the message says why; the old short stays)."""


def unattributed(entry: AudioEntry) -> bool:
    """A CC BY bed with no author: its credits line would have no one to attribute."""
    words = entry.licence.lower().replace("-", " ").replace("_", " ").split()
    return "by" in words and not (entry.author or "").strip()


def fitting_beds(story: SoundStory | None, library: sound.Library) -> list[AudioEntry]:
    """The approved beds that fit the story's planned moods, in the page's order: every
    segment's mood + flavour matches (a segment with no flavour: its whole mood), then
    the mood alone, then every `facts_default` bed; once each, never an uncreditable one."""
    segments = story.bed if story is not None else []
    energy = story.bed_query.energy if story is not None else 3
    exact: list[AudioEntry] = []
    mood_only: list[AudioEntry] = []
    for segment in segments:
        for entry in sound.mood_beds(library, segment, energy=energy, first_stamp_s=0.0):
            flavoured = segment.flavour is None or segment.flavour in entry.tags.flavour
            (exact if flavoured else mood_only).append(entry)
    facts = sound.facts_default_beds(library, energy=energy, first_stamp_s=0.0)
    out: dict[str, AudioEntry] = {}
    for entry in (*exact, *mood_only, *facts):
        if entry.id not in out and not unattributed(entry):
            out[entry.id] = entry
    return list(out.values())


def playing(job: Job) -> list[str]:
    """The ids of the beds the delivered short plays: `balance.json`'s, or (a job mixed
    before 093) the music rows of its rights log."""
    balance = sound.balance_report(job.work_dir / "stems")
    if balance is not None and balance.beds:
        return list(balance.beds)
    return [r.id for r in rights.audio_rows(job.path) if r.kind == "music"]


@dataclass(frozen=True)
class Choice:
    entry: AudioEntry
    playing: bool


def story_of(job: Job) -> SoundStory | None:
    path = job.work_dir / "sound.json"
    if not path.is_file():
        return None
    return SoundStory.model_validate_json(path.read_text(encoding="utf-8"))


def choices(job: Job, library: sound.Library) -> list[Choice]:
    now = set(playing(job))
    return [Choice(e, e.id in now) for e in fitting_beds(story_of(job), library)]


def replaces_change(job: Job) -> bool:
    """The story plans a 076 bed change, so a pick replaces it (the page says so)."""
    story = story_of(job)
    return story is not None and story.change is not None and len(story.bed) > 1


def refusal(job: Job) -> str:
    """Why this job's bed cannot be changed, or "" when it can (090's reasons)."""
    why = level.refusal(job)
    if why == level.SWEPT_SENTENCE:
        return SWEPT_SENTENCE
    if why == level.NO_BED_SENTENCE:
        return NO_BED_SENTENCE
    return why


@dataclass(frozen=True)
class Picked:
    short: Path
    entry: AudioEntry
    balance: BalanceReport
    notes: list[str]


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def pick(
    job: Job, entry_id: str, *, library: sound.Library | None = None, now: Clock = _utc_now
) -> Picked:
    """`entry_id` under the whole reel (see the module note). Raises `PickError` with the
    old short, stems and rights untouched when it cannot deliver."""
    why = refusal(job)
    if why:
        raise PickError(why)
    library = library if library is not None else sound.load_catalogue()
    story = story_of(job)
    offered = {c.entry.id: c.entry for c in choices(job, library)}
    entry = offered.get(entry_id)
    if story is None or entry is None:
        raise PickError(NOT_OFFERED)
    was = playing(job)
    nums = render.loaded_styles()[job.record.style].sound
    started = job.record.music_level
    offset = started.offset_db if started is not None else 0.0
    plan = PicturePlan.model_validate_json(
        (job.work_dir / "plan.json").read_text(encoding="utf-8")
    )
    runtime = presenter.total_duration(presenter.cut_list(plan))
    try:
        balance = level.deliver(job, lambda stems, scratch: sound.repick(
            stems, scratch, entry=entry, library=library, story=story, nums=nums,
            runtime_s=runtime, offset_db=offset,
        ))  # fmt: skip
    except level.LevelError as exc:
        raise PickError(str(exc)) from exc
    rights.replace_music(job.path, [sound.bed_row(entry, library)])
    notes = level.ear_notes(balance, nums)
    stamp = now()
    kept = started or jobs.MusicLevel(
        offset_db=0.0, measure=level.MEASURE, set_by="default", set_at=stamp
    )
    jobs.amend(
        job, bed_pick=jobs.BedPick(entry_id=entry.id, set_at=stamp),
        music_level=kept.model_copy(update={"notes": notes}),
    )  # fmt: skip
    margin = balance.speech_band_margin_db
    jobs.note(
        job,
        f"bed pick: {entry.id} replaces {' + '.join(was) or 'no bed'} under the whole reel "
        f"at slider offset {offset:+g} dB ({level.MEASURE}), bed "
        f"{balance.bed_under_voice_db} dB under the voice, speech-band margin "
        f"{'none' if margin is None else f'{margin:.1f}'} dB"
        + (f"; {'; '.join(notes)}" if notes else ""),
        now=now,
    )
    return Picked(short=job.out_dir / "short.mp4", entry=entry, balance=balance, notes=notes)
