"""090: the music-level slider - `assets/audio/level.yaml` (range and step, checked at
startup) and the audio-only remix of a delivered job from its stems: the bed rebuilt at
the style's starting level plus the offset, the duck, the premix, the master and the
remux with the picture stream copied. No Remotion, no planner, no asset call. The ear
wins: a setting the balance dislikes is delivered with a plain note, never repaired."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shortsmith import app as app_module
from shortsmith import ffmpeg, jobs, render, sound
from shortsmith.contracts import BalanceReport
from shortsmith.planner import FakePlanner
from shortsmith.presenter import FakeFaceDetector
from shortsmith.qa import technical
from shortsmith.qa.gate import FakeGate
from shortsmith.render import FakeRenderer
from shortsmith.sound import level
from shortsmith.transcriber import FakeTranscriber
from tests.conftest import Media
from tests.test_app import (
    SPECS,
    _settings,  # pyright: ignore[reportPrivateUsage]
    login,
)
from tests.test_render import (
    _job_with,  # pyright: ignore[reportPrivateUsage]
    _plan,  # pyright: ignore[reportPrivateUsage]
    _plan_request,  # pyright: ignore[reportPrivateUsage]
    _synthetic_picture,  # pyright: ignore[reportPrivateUsage]
)

EXPLAINER = render.loaded_styles()["explainer"].sound


# --- level.yaml -------------------------------------------------------------------------


def test_the_shipped_scale_is_wide_and_has_its_start_on_a_notch() -> None:
    """The quiet end goes past run04's not-heard level (offset 0, the style's -14) and
    the loud end past run03's "a bit loud" (+3.1); 0 is a notch, so the mark sits on one."""
    scale = level.load_scale()
    assert scale.min_db < 0 < 3.1 < scale.max_db
    assert scale.step_db > 0
    assert scale.quiet_label and scale.loud_label
    assert (0 - scale.min_db) / scale.step_db == pytest.approx(
        round((0 - scale.min_db) / scale.step_db)
    )
    assert scale.contains(0.0) and not scale.contains(scale.max_db + scale.step_db)


GOOD = """\
min_db: -12
max_db: 8
step_db: 2
quiet_label: barely there
loud_label: up front
"""


@pytest.mark.parametrize(
    ("key", "line"),
    [
        ("min_db", "min_db: 3"),
        ("max_db", "max_db: -1"),
        ("step_db", "step_db: 0"),
        ("step_db", "step_db: 30"),
        ("quiet_label", "quiet_label: ''"),
    ],
)
def test_a_value_off_its_range_names_the_key(key: str, line: str) -> None:
    text = "\n".join(
        line if row.startswith(f"{key}:") else row for row in GOOD.splitlines()
    )
    with pytest.raises(level.LevelError, match=key):
        level.parse_scale(text, name="level.yaml")


def test_an_unknown_or_missing_key_is_refused() -> None:
    with pytest.raises(level.LevelError, match="loud_label"):
        level.parse_scale(GOOD.replace("loud_label: up front\n", ""), name="level.yaml")
    with pytest.raises(level.LevelError, match="colour"):
        level.parse_scale(GOOD + "colour: red\n", name="level.yaml")


def test_a_broken_level_file_stops_the_app_naming_the_key(tmp_path: Path) -> None:
    bad = tmp_path / "level.yaml"
    bad.write_text(GOOD.replace("step_db: 2", "step_db: -1"), encoding="utf-8")
    with pytest.raises(level.LevelError, match="step_db"):
        app_module.create_app(
            _settings(tmp_path), transcriber=FakeTranscriber(), planner=FakePlanner(),
            specs=SPECS, renderer=FakeRenderer(), gate=FakeGate(),
            detector=FakeFaceDetector(), start_worker=False, music_levels=bad,
        )  # fmt: skip


# --- the ear's notes --------------------------------------------------------------------


def _report(margin: float | None, *windows: float) -> BalanceReport:
    return BalanceReport.model_validate({
        "voice_db": -20.0, "bed_accept_db": (-15, -12), "speech_band_margin_min_db": 12,
        "speech_band_margin_max_db": 20, "duck_max_db": 6,
        "speech_band_margin_db": margin,
        "windows": [{"name": f"w{i}", "start_s": 0, "end_s": 1, "speech_band_margin_db": m}
                    for i, m in enumerate(windows)],
    })  # fmt: skip


def test_the_ear_notes_are_plain_words_for_each_side_of_the_band() -> None:
    assert level.ear_notes(_report(15.0), EXPLAINER) == []
    assert level.ear_notes(_report(9.0), EXPLAINER) == [level.COVER_NOTE]
    assert level.ear_notes(_report(25.0), EXPLAINER) == [level.QUIET_NOTE]
    assert level.ear_notes(_report(15.0, 9.0, 25.0), EXPLAINER) == [
        level.COVER_NOTE, level.QUIET_NOTE,
    ]  # fmt: skip
    assert level.ear_notes(_report(None), EXPLAINER) == []


# --- the remix --------------------------------------------------------------------------


def _delivered(root: Path, clip: Path, media: Media, library: sound.Library) -> jobs.Job:
    """A job rendered through the real mux (voice, bed, cues, master), then delivered."""
    job = _job_with(root, clip)
    _synthetic_picture(job, media)
    story = FakePlanner().plan_sound(_plan_request(), _plan())
    (job.work_dir / "sound.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")
    render.voice_stem(job)
    render.mux(job, library=library)
    return jobs.amend(job, status="delivered")


def _no_render_or_mix(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("the remix must not run the picture or the sound director")

    monkeypatch.setattr(render, "render_picture", refuse)
    monkeypatch.setattr(render, "sound_mix", refuse)
    monkeypatch.setattr(sound, "build_mix", refuse)


def _stems(job: jobs.Job) -> Path:
    return job.work_dir / "stems"


def test_a_louder_setting_raises_the_bed_and_copies_the_picture(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    job = _delivered(tmp_path, fixture_clip, media, library)
    short = job.out_dir / "short.mp4"
    picture = ffmpeg.video_md5(short)
    before = sound.balance_report(_stems(job))
    assert before is not None and before.bed_under_voice_db is not None
    assert before.speech_band_margin_db is not None
    _no_render_or_mix(monkeypatch)
    started = time.monotonic()
    result = level.remix(job, offset_db=6.0)
    took = time.monotonic() - started
    assert took < 15.0, f"the 6 s fixture remixed in {took:.1f} s"
    after = sound.balance_report(_stems(job))
    assert after is not None and after == result.balance
    assert after.bed_under_voice_db is not None and after.speech_band_margin_db is not None
    assert after.bed_under_voice_db > before.bed_under_voice_db + 4
    assert after.bed_under_voice_db == pytest.approx(EXPLAINER.bed_db_under_voice + 6, abs=0.5)
    assert after.speech_band_margin_db < before.speech_band_margin_db
    assert ffmpeg.video_md5(short) == picture, "the picture stream is copied, never re-encoded"
    assert technical.t4(ffmpeg.measure_loudness(short)).passed
    record = jobs.load(job.path).record
    assert record.music_level is not None
    assert record.music_level.offset_db == 6.0
    assert record.music_level.measure == level.MEASURE == "full_band"
    assert record.music_level.set_by == "slider"
    log = job.log_path.read_text(encoding="utf-8")
    assert "music level: slider offset +6 dB (full_band)" in log
    # The offset is from the starting level, never from the last remix.
    level.remix(job, offset_db=0.0)
    back = sound.balance_report(_stems(job))
    assert back is not None and back.bed_under_voice_db is not None
    assert back.bed_under_voice_db == pytest.approx(before.bed_under_voice_db, abs=0.5)
    assert not (job.out_dir / level.REMIX_NAME).exists(), "nothing is left beside the short"


def test_a_setting_the_floor_dislikes_is_delivered_with_a_note_and_never_repaired(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    job = _delivered(tmp_path, fixture_clip, media, library)
    lines_before = job.log_path.read_text(encoding="utf-8").count("\n")
    scale = level.load_scale()
    result = level.remix(job, offset_db=scale.max_db)
    margin = result.balance.speech_band_margin_db
    assert margin is not None and margin < EXPLAINER.speech_band_margin_db, (
        "the loud end must reach past the floor on the fixture bed"
    )
    assert result.notes == [level.COVER_NOTE]
    record = jobs.load(job.path).record
    assert record.music_level is not None and record.music_level.notes == [level.COVER_NOTE]
    tail = job.log_path.read_text(encoding="utf-8").splitlines()[lines_before:]
    assert not [line for line in tail if "dipped" in line or "lowered" in line]
    assert result.balance.bed_under_voice_db == pytest.approx(
        EXPLAINER.bed_db_under_voice + scale.max_db, abs=0.5
    )
    page = app_module.render_job_page(jobs.load(job.path))
    assert level.COVER_NOTE in page


def test_a_failed_master_keeps_the_old_file_and_stems(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    job = _delivered(tmp_path, fixture_clip, media, library)
    short = job.out_dir / "short.mp4"
    old = short.read_bytes()
    balance = (_stems(job) / sound.BALANCE_NAME).read_bytes()
    music = (_stems(job) / "music.wav").read_bytes()

    def quiet_master(source: Path, mix: Path) -> ffmpeg.Loudness:
        shutil.copyfile(source, mix)
        return ffmpeg.Loudness(integrated=-30.0, true_peak=-10.0, lra=1.0, threshold=-40.0,
                               offset=0.0)  # fmt: skip

    monkeypatch.setattr(render, "master", quiet_master)
    with pytest.raises(level.LevelError, match="T4"):
        level.remix(job, offset_db=4.0)
    assert short.read_bytes() == old
    assert (_stems(job) / sound.BALANCE_NAME).read_bytes() == balance
    assert (_stems(job) / "music.wav").read_bytes() == music
    assert not (job.out_dir / level.REMIX_NAME).exists()
    recorded = jobs.load(job.path).record.music_level
    assert recorded is not None and recorded.set_by == "default"


def test_a_delivered_mix_records_its_default_level(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    job = _delivered(tmp_path, fixture_clip, media, library)
    recorded = jobs.load(job.path).record.music_level
    assert recorded is not None
    assert (recorded.offset_db, recorded.measure, recorded.set_by) == (0.0, "full_band", "default")


def test_a_swept_job_refuses_the_remix_with_its_reason(tmp_path: Path) -> None:
    job = jobs.create(tmp_path)
    job = jobs.amend(job, status="delivered", swept_at=job.record.created_at)
    with pytest.raises(level.LevelError, match="deleted"):
        level.remix(job, offset_db=2.0)
    assert level.refusal(job) == level.SWEPT_SENTENCE


def test_a_job_without_a_bed_has_no_slider(tmp_path: Path) -> None:
    job = jobs.amend(jobs.create(tmp_path), status="delivered")
    assert level.refusal(job) == level.NO_BED_SENTENCE


def test_a_two_bed_reel_keeps_its_segments_relative_levels(
    tmp_path: Path, voice: Path, library: sound.Library
) -> None:
    """076: across a bed change every bed stem takes one gain, and each window is
    measured again on its own stem."""
    from tests.test_bed_changes import _mix  # pyright: ignore[reportPrivateUsage]

    _, stems, nums = _mix(tmp_path, voice, library, "crossfade")
    before = sound.balance_report(stems)
    assert before is not None and len(before.windows) == 3
    out = stems / level.SCRATCH_DIR
    _, after = sound.relevel(stems, out, nums=nums, offset_db=4.0)
    assert [w.name for w in after.windows] == [w.name for w in before.windows]
    for old, new in zip(before.windows, after.windows, strict=True):
        assert old.bed_under_voice_db is not None and new.bed_under_voice_db is not None
        assert new.bed_under_voice_db - old.bed_under_voice_db == pytest.approx(
            after.bed_under_voice_db - before.bed_under_voice_db, abs=0.3  # type: ignore[operator]
        ), old.name
    for name in ("music.1.wav", "music.2.wav", "music.wav", "music.ducked.wav"):
        assert (out / name).is_file(), name
    assert (stems / sound.START_DIR / "music.1.wav").is_file()


# --- the job page -----------------------------------------------------------------------


def test_a_swept_job_page_shows_the_slider_disabled_with_its_reason(tmp_path: Path) -> None:
    job = jobs.create(tmp_path)
    (job.out_dir / "short.mp4").write_bytes(b"")
    job = jobs.amend(job, status="delivered", swept_at=job.record.created_at)
    page = app_module.render_job_page(job)
    assert 'name="offset"' in page and "disabled" in page
    assert level.SWEPT_SENTENCE in page


def test_the_page_slider_remixes_and_shows_the_setting(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    data = tmp_path / "data"
    job = _delivered(data, fixture_clip, media, library)
    app = app_module.create_app(
        _settings(tmp_path), transcriber=FakeTranscriber(), planner=FakePlanner(),
        specs=SPECS, renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False,
    )  # fmt: skip
    scale = level.load_scale()
    with TestClient(app) as client:
        assert login(client).status_code == 303
        page = client.get(f"/jobs/{job.id}").text
        assert 'name="offset"' in page and scale.quiet_label in page and scale.loud_label in page
        assert " dB" not in page.split('class="music-level"')[1].split("</form>")[0], (
            "no dB on the control"
        )
        moved = client.post(f"/jobs/{job.id}/music-level", data={"offset": "-4"},
                            follow_redirects=False)  # fmt: skip
        assert moved.status_code == 303
        assert jobs.load(job.path).record.music_level.offset_db == -4.0  # type: ignore[union-attr]
        assert 'value="-4"' in client.get(f"/jobs/{job.id}").text
        off = client.post(f"/jobs/{job.id}/music-level", data={"offset": "99"})
        assert off.status_code == 422
        # A failure shows its error and keeps the file.
        short = job.out_dir / "short.mp4"
        old = short.read_bytes()

        def boom(*_: object, **__: object) -> None:
            raise level.LevelError("the master missed T4: -30.0 LUFS")

        monkeypatch.setattr(level, "remix", boom)
        failed = client.post(f"/jobs/{job.id}/music-level", data={"offset": "2"})
        assert failed.status_code == 500 and "the master missed T4" in failed.text
        assert short.read_bytes() == old
        jobs.amend(job, swept_at=job.record.created_at)
        swept = client.post(f"/jobs/{job.id}/music-level", data={"offset": "2"})
        assert swept.status_code == 409 and level.SWEPT_SENTENCE in swept.text
