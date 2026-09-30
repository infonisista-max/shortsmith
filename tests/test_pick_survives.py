"""101: a change-box picture edit keeps the operator's slider level and bed pick.

A picture change re-runs the job from sourcing, so the mux mixes the sound again. With
`job.record.bed_pick` set, `sound_mix` plays that bed under the whole reel (as
`sound.repick` does) at the recorded slider level, and the rights log keeps its row - on
every re-render. A music-level change from the change box still overrides the level.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from shortsmith import jobs, render, rights, sound
from shortsmith.editor import change
from shortsmith.jobs import Job
from shortsmith.render import FakeRenderer
from shortsmith.sound import level, pick
from tests.conftest import Media
from tests.test_bed_pick import (
    CC_BY,
    PLAYING,
    _fake_library,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_change import _Scripted  # pyright: ignore[reportPrivateUsage]
from tests.test_pipeline import SPECS, _run, _uploaded  # pyright: ignore[reportPrivateUsage]
from tests.test_render import _synthetic_picture  # pyright: ignore[reportPrivateUsage]

EXPLAINER = render.loaded_styles()["explainer"].sound


class _Mixing(FakeRenderer):
    """The fake picture, then the real voice stem and mux: the sound a re-render makes."""

    def __init__(self, media: Media) -> None:
        super().__init__()
        self.media = media

    def render(
        self, job: Job, *, on_progress: Callable[[int], None] | None = None,
        library: sound.Library | None = None,
    ) -> Path:  # fmt: skip
        super().render(job, on_progress=on_progress, library=library)
        _synthetic_picture(job, self.media)
        render.voice_stem(job)
        return render.mux(job, library=library)


def _picked(tmp_path: Path, clip: Path, media: Media, fake: sound.Library) -> jobs.Job:
    """A delivered job whose slider is at +4 dB and whose bed the operator picked."""
    job = _run(_uploaded(tmp_path, clip), renderer=_Mixing(media), library=fake)
    assert job.status == "delivered"
    balance = sound.balance_report(job.work_dir / "stems")
    assert balance is not None and balance.beds == [PLAYING]  # the director's own pick
    level.remix(job, offset_db=4.0)
    pick.pick(jobs.load(job.path), CC_BY, library=fake)
    return jobs.load(job.path)


def _music_rows(job: jobs.Job) -> list[rights.RightsRow]:
    return [r for r in rights.load(job.path) or [] if r.kind == "music"]


def _change(
    job: jobs.Job, ops: list[dict[str, object]], media: Media, fake: sound.Library
) -> jobs.Job:
    planner = _Scripted({"ops": ops, "summary": "the operator's change"})
    planned = change.plan_change(job, "a picture change", planner)
    assert not planned.refused and planned.picture
    change.apply_change(job, planned, specs=SPECS)
    again = _run(jobs.load(job.path), renderer=_Mixing(media), library=fake)
    assert again.status == "delivered"
    return again


def test_a_picture_change_keeps_the_bed_pick_the_level_and_the_rights_row(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    fake = _fake_library(library)
    job = _picked(tmp_path, fixture_clip, media, fake)
    rows = _music_rows(job)
    assert [r.id for r in rows] == [CC_BY]
    again = _change(job, [{"op": "replace_visual", "beat": "b05"}], media, fake)
    balance = sound.balance_report(again.work_dir / "stems")
    assert balance is not None and balance.beds == [CC_BY]
    assert balance.bed_under_voice_db == pytest.approx(EXPLAINER.bed_db_under_voice + 4, abs=0.5)
    record = again.record
    assert record.bed_pick is not None and record.bed_pick.entry_id == CC_BY
    assert record.music_level is not None and record.music_level.offset_db == 4.0
    assert _music_rows(again) == rows
    credits = (again.out_dir / rights.CREDITS_NAME).read_text(encoding="utf-8")
    assert "Ana Composer" in credits
    assert f"bed pick: {CC_BY}" in again.log_path.read_text(encoding="utf-8")


def test_a_music_level_change_still_overrides_the_level_and_keeps_the_pick(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    fake = _fake_library(library)
    job = _picked(tmp_path, fixture_clip, media, fake)
    ops: list[dict[str, object]] = [{"op": "replace_visual", "beat": "b05"},
                                    {"op": "music_level", "offset_db": -3}]  # fmt: skip
    again = _change(job, ops, media, fake)
    balance = sound.balance_report(again.work_dir / "stems")
    assert balance is not None and balance.beds == [CC_BY]
    assert balance.bed_under_voice_db == pytest.approx(EXPLAINER.bed_db_under_voice - 3, abs=0.5)
    assert again.record.music_level is not None and again.record.music_level.offset_db == -3


def test_a_pick_no_longer_in_the_library_falls_back_to_the_director_with_a_line(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    fake = _fake_library(library)
    job = _picked(tmp_path, fixture_clip, media, fake)
    gone = sound.Library(root=fake.root, entries=tuple(e for e in fake.entries if e.id != CC_BY),
                         fetched=fake.fetched)  # fmt: skip
    again = _change(job, [{"op": "replace_visual", "beat": "b05"}], media, gone)
    balance = sound.balance_report(again.work_dir / "stems")
    assert balance is not None and balance.beds and CC_BY not in balance.beds
    assert "is not in the audio library" in again.log_path.read_text(encoding="utf-8")
