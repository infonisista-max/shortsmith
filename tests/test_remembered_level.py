"""091: the next job's music starts at the operator's last slider setting - one
`<data_dir>/music_level.json`, written by a delivered slider remix (090) whatever the
style, read at mux by every new job. It is the pipeline's choice, so 069's repair ladder
still applies; a retry keeps the job's recorded level; a remembered offset under another
level measure is ignored with its line."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shortsmith import app as app_module
from shortsmith import jobs, render, sound
from shortsmith.sound import level, remembered
from tests.conftest import Media
from tests.test_music_level import _delivered  # pyright: ignore[reportPrivateUsage]

EXPLAINER = render.loaded_styles()["explainer"].sound


def _bed_under(job: jobs.Job) -> float:
    report = sound.balance_report(job.work_dir / "stems")
    assert report is not None and report.bed_under_voice_db is not None
    return report.bed_under_voice_db


def _remember(
    data: Path, offset_db: float, *, job_id: str = "earlier", measure: str = level.MEASURE
) -> None:
    remembered.save(data, remembered.Remembered(
        offset_db=offset_db, measure=measure, job_id=job_id, set_at=datetime.now(UTC),
    ))  # fmt: skip


def test_a_slider_move_on_a_vishva_job_starts_the_next_explainer_job_there(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    data = tmp_path / "data"
    first = _delivered(data, fixture_clip, media, library)
    first = jobs.amend(first, style="vishva")
    assert remembered.load(data) is None, "a default mix remembers nothing"
    level.remix(first, offset_db=2.0)
    kept = remembered.load(data)
    assert kept is not None
    assert (kept.offset_db, kept.measure, kept.job_id) == (2.0, level.MEASURE, first.id)
    second = _delivered(data, fixture_clip, media, library)
    assert second.record.style == "explainer"
    assert _bed_under(second) == pytest.approx(EXPLAINER.bed_db_under_voice + 2.0, abs=0.5)
    record = jobs.load(second.path).record.music_level
    assert record is not None
    assert (record.offset_db, record.set_by, record.from_job) == (2.0, "remembered", first.id)
    log = second.log_path.read_text(encoding="utf-8")
    assert f"music level: remembered offset +2 dB from job {first.id}" in log
    page = app_module.render_job_page(jobs.load(second.path))
    assert f"your last setting (from job {first.id})" in page


def test_no_file_starts_at_offset_zero(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    job = _delivered(tmp_path, fixture_clip, media, library)
    record = jobs.load(job.path).record.music_level
    assert record is not None
    assert (record.offset_db, record.set_by, record.from_job) == (0.0, "default", None)
    assert "remembered" not in job.log_path.read_text(encoding="utf-8")
    assert "your last setting" not in app_module.render_job_page(jobs.load(job.path))


def test_a_remembered_level_that_crowds_the_voice_is_repaired(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    """The ear-wins rule is the slider's alone: the pipeline's own start is repaired."""
    loud = level.load_scale().max_db
    _remember(tmp_path, loud)
    job = _delivered(tmp_path, fixture_clip, media, library)
    report = sound.balance_report(job.work_dir / "stems")
    assert report is not None and report.repairs, "the loud end crowds the fixture voice"
    assert not report.problems
    log = job.log_path.read_text(encoding="utf-8")
    assert "dipped" in log or "lowered" in log
    record = jobs.load(job.path).record.music_level
    assert record is not None and (record.offset_db, record.set_by) == (loud, "remembered")


def test_a_retry_keeps_its_recorded_level_after_the_file_changes(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    _remember(tmp_path, 2.0, job_id="first")
    job = _delivered(tmp_path, fixture_clip, media, library)
    _remember(tmp_path, -6.0, job_id="later")
    render.mux(jobs.load(job.path), library=library)  # a retry re-entering at rendering
    assert _bed_under(job) == pytest.approx(EXPLAINER.bed_db_under_voice + 2.0, abs=0.5)
    record = jobs.load(job.path).record.music_level
    assert record is not None and (record.offset_db, record.from_job) == (2.0, "first")


def test_a_remembered_offset_under_another_measure_is_ignored_with_its_line(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    _remember(tmp_path, 4.0, job_id="first", measure="phone_band")
    job = _delivered(tmp_path, fixture_clip, media, library)
    record = jobs.load(job.path).record.music_level
    assert record is not None and (record.offset_db, record.set_by) == (0.0, "default")
    log = job.log_path.read_text(encoding="utf-8")
    assert "remembered offset +4 dB from job first is on measure phone_band" in log
    assert "ignored" in log


def test_a_failed_remix_remembers_nothing(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    job = _delivered(tmp_path, fixture_clip, media, library)

    def boom(*_: object, **__: object) -> None:
        raise sound.SoundError("broken stem")

    monkeypatch.setattr(sound, "relevel", boom)
    with pytest.raises(level.LevelError):
        level.remix(job, offset_db=4.0)
    assert remembered.load(tmp_path) is None


def test_the_smoke_never_reads_the_operators_file(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    """The file lives in the job's own data directory (the smoke's is a fresh temp one),
    never at a `data/` the working directory happens to hold."""
    monkeypatch.chdir(tmp_path)
    _remember(Path("data"), 6.0, job_id="operator")
    assert (tmp_path / "data" / remembered.FILE).is_file()
    job = _delivered(tmp_path / "smoke" / "data", fixture_clip, media, library)
    record = jobs.load(job.path).record.music_level
    assert record is not None and (record.offset_db, record.set_by) == (0.0, "default")
    used = remembered.path(jobs.data_dir_of(job))
    assert os.fspath(used) != os.fspath(Path("data") / remembered.FILE)
