"""093: pick a different bed for the reel on the job page - from the approved beds that
fit the story's planned moods (mood + flavour first, then mood alone) plus every
`facts_default` bed - with the same audio-only remix as 090's slider: the pick at the
style's starting level plus the reel's slider offset, the duck, the premix, the master and
the remux with the picture copied. The rights log and the credits follow the new bed."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from shortsmith import app as app_module
from shortsmith import ffmpeg, jobs, render, rights, sound
from shortsmith.contracts import (
    FACTS_DEFAULT,
    AssetManifest,
    AudioEntry,
    AudioTags,
    BedChange,
    BedSegment,
    Catalogue,
    SoundStory,
)
from shortsmith.planner import FakePlanner
from shortsmith.presenter import FakeFaceDetector
from shortsmith.qa import technical
from shortsmith.qa.gate import FakeGate
from shortsmith.render import FakeRenderer
from shortsmith.sound import level, pick, remembered
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
PLAYING = "bed_tech_curious"  # the fake explainer story's mysterious_curiosity bed
CC_BY = "bed_by_curious"
FACTS = "bed_facts_calm"
OFF_MOOD = "bed_tech_tense"
UNHEARD = "fetched_curious"
NAMELESS = "bed_by_nameless"


def _bed(
    library: sound.Library, source: str, new_id: str, mood: str, *, energy: int = 3,
    role: tuple[str, ...] = (), flavour: tuple[str, ...] = (), **update: object,
) -> AudioEntry:  # fmt: skip
    base = library.entry(source)
    assert base is not None
    return base.model_copy(update={
        "id": new_id, "file": str(library.file(base)), "energy": energy,
        "tags": AudioTags(mood=[mood], role=list(role), flavour=list(flavour)), **update,
    })  # fmt: skip


def _fake_library(library: sound.Library) -> sound.Library:
    """Closed-list tags only, as the tracked catalogue has: the playing bed, a CC BY bed
    of the same mood, a facts default of another mood, an off-mood bed, a fetched
    (unheard) bed of the planned mood, and a CC BY bed nobody can credit."""
    beds = (
        _bed(library, "bed_tech_curious", PLAYING, "mysterious_curiosity"),
        _bed(library, "bed_tech_tense", CC_BY, "mysterious_curiosity", energy=4,
             licence="CC-BY-4.0", author="Ana Composer",
             source_url="https://example.invalid/by/ana"),
        _bed(library, "bed_history_calm", FACTS, "calm_ambient", role=(FACTS_DEFAULT,)),
        _bed(library, "bed_tech_tense", OFF_MOOD, "tense_dramatic"),
        _bed(library, "bed_tech_curious", UNHEARD, "mysterious_curiosity"),
        _bed(library, "bed_tech_tense", NAMELESS, "mysterious_curiosity", energy=5,
             licence="CC-BY-4.0", author=None, credit=None,
             source_url="https://example.invalid/by/nameless"),
    )  # fmt: skip
    sfx = tuple(
        e.model_copy(update={"file": str(library.file(e))}) for e in library.sfx()
    )
    return sound.Library(
        root=library.root, entries=(*beds, *sfx), fetched=frozenset({UNHEARD})
    )


def _write_catalogue(root: Path, library: sound.Library) -> Path:
    """The tracked part of `library` as a catalogue file (the fetched bed beside it)."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / sound.CATALOGUE_NAME
    tracked = [e for e in library.entries if e.id not in library.fetched]
    fetched = [e for e in library.entries if e.id in library.fetched]
    for file, entries in ((path, tracked), (root / sound.FETCHED_DIR / sound.CATALOGUE_NAME,
                                             fetched)):  # fmt: skip
        file.parent.mkdir(parents=True, exist_ok=True)
        data = Catalogue(entries=entries).model_dump(mode="json", exclude_defaults=True)
        file.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _delivered(
    root: Path, clip: Path, media: Media, library: sound.Library,
    story: SoundStory | None = None,
) -> jobs.Job:  # fmt: skip
    """A job rendered through the real mux with `library`, its rights log written."""
    job = _job_with(root, clip)
    _synthetic_picture(job, media)
    story = story or FakePlanner().plan_sound(_plan_request(), _plan())
    (job.work_dir / "sound.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")
    render.voice_stem(job)
    render.mux(job, library=library)
    manifest = AssetManifest(assets=[], beats=[], runtime_s=6.0, rescued_max=0)
    rights.write(job.path, manifest, _plan())
    return jobs.amend(job, status="delivered")


def _stems(job: jobs.Job) -> Path:
    return job.work_dir / "stems"


def _no_render_or_mix(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("the pick must not run the picture or the sound director")

    monkeypatch.setattr(render, "render_picture", refuse)
    monkeypatch.setattr(render, "sound_mix", refuse)
    monkeypatch.setattr(sound, "build_mix", refuse)


# --- the choices ------------------------------------------------------------------------


def test_the_choices_put_mood_and_flavour_first_then_mood_then_the_facts_default(
    library: sound.Library,
) -> None:
    fake = _fake_library(library)
    flavoured = _bed(library, "bed_tech_tense", "bed_gulf", "tense_dramatic",
                     flavour=("middle_east",))  # fmt: skip
    lib = sound.Library(root=fake.root, entries=(*fake.entries, flavoured), fetched=fake.fetched)
    story = FakePlanner().plan_sound(_plan_request(), _plan()).model_copy(update={
        "bed": [BedSegment(part_from="hook", mood="mysterious_curiosity"),
                BedSegment(part_from="reveal", mood="tense_dramatic", flavour="middle_east")],
        "change": BedChange(at_beat="b07", how="crossfade"),
    })  # fmt: skip
    ids = [e.id for e in pick.fitting_beds(story, lib)]
    # mood + flavour matches (the hook names no flavour, so its whole mood matches), then
    # the reveal's mood alone, then the facts default; never unheard or uncreditable.
    assert ids == [PLAYING, CC_BY, "bed_gulf", OFF_MOOD, FACTS]


def test_the_list_holds_the_planned_moods_beds_and_the_facts_default(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    fake = _fake_library(library)
    job = _delivered(tmp_path, fixture_clip, media, fake)
    choices = pick.choices(job, fake)
    assert [(c.entry.id, c.playing) for c in choices] == [
        (PLAYING, True), (CC_BY, False), (FACTS, False),
    ]  # fmt: skip
    page = app_module.render_job_page(job, library=fake)
    block = page.split('class="bed-pick"')[1].split("</form>")[0]
    for shown in (PLAYING, CC_BY, FACTS):
        assert f'value="{shown}"' in block, shown
    for hidden in (OFF_MOOD, UNHEARD, NAMELESS):
        assert hidden not in block, hidden
    assert "now playing" in block.split(f'value="{PLAYING}"')[1].split("</li>")[0]
    assert "Ana Composer" in block and "CC-BY-4.0" in block and "mysterious_curiosity" in block
    assert f"/audio/beds/{CC_BY}" in block, "each row has a small player"


# --- the pick ---------------------------------------------------------------------------


def test_a_pick_plays_the_new_bed_at_the_offset_and_copies_the_picture(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    fake = _fake_library(library)
    job = _delivered(tmp_path / "data", fixture_clip, media, fake)
    level.remix(job, offset_db=4.0)
    saved = remembered.path(jobs.data_dir_of(job)).read_bytes()
    job = jobs.load(job.path)
    short = job.out_dir / "short.mp4"
    picture = ffmpeg.video_md5(short)
    _no_render_or_mix(monkeypatch)
    result = pick.pick(job, CC_BY, library=fake)
    balance = sound.balance_report(_stems(job))
    assert balance is not None and balance == result.balance
    assert balance.beds == [CC_BY]
    assert balance.bed_under_voice_db == pytest.approx(EXPLAINER.bed_db_under_voice + 4, abs=0.5)
    assert ffmpeg.video_md5(short) == picture, "the picture stream is copied, never re-encoded"
    assert technical.t4(ffmpeg.measure_loudness(short)).passed
    record = jobs.load(job.path).record
    assert record.bed_pick is not None and record.bed_pick.entry_id == CC_BY
    assert record.music_level is not None and record.music_level.offset_db == 4.0
    assert "bed pick: bed_by_curious" in job.log_path.read_text(encoding="utf-8")
    assert remembered.path(jobs.data_dir_of(job)).read_bytes() == saved, "only the slider"
    assert [c.entry.id for c in pick.choices(jobs.load(job.path), fake) if c.playing] == [CC_BY]
    # The slider after a pick moves the new bed from its own starting level.
    level.remix(jobs.load(job.path), offset_db=0.0)
    back = sound.balance_report(_stems(job))
    assert back is not None and back.beds == [CC_BY]
    assert back.bed_under_voice_db == pytest.approx(EXPLAINER.bed_db_under_voice, abs=0.5)
    assert not (job.out_dir / level.REMIX_NAME).exists()


def test_the_rights_log_and_the_credits_name_the_new_bed(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    fake = _fake_library(library)
    job = _delivered(tmp_path, fixture_clip, media, fake)
    before = rights.load(job.path)
    assert before is not None and PLAYING in {r.id for r in before if r.kind == "music"}
    sfx = [r for r in before if r.kind == "sfx"]
    pick.pick(job, CC_BY, library=fake)
    after = rights.load(job.path)
    assert after is not None
    music = [r for r in after if r.kind == "music"]
    assert [r.id for r in music] == [CC_BY]
    assert music[0].source_url == "https://example.invalid/by/ana"
    assert music[0].licence == "CC-BY-4.0" and music[0].author == "Ana Composer"
    assert [r.id for r in after if r.kind == "sfx"] == [r.id for r in sfx]
    assert [r.id for r in rights.audio_rows(job.path) if r.kind == "music"] == [CC_BY]
    credits = (job.out_dir / rights.CREDITS_NAME).read_text(encoding="utf-8")
    assert "Music: Ana Composer via https://example.invalid/by/ana (CC-BY-4.0)" in credits
    assert "example.invalid/fixture/bed_tech_curious" not in credits


def test_a_bed_without_its_attribution_is_refused(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    fake = _fake_library(library)
    job = _delivered(tmp_path, fixture_clip, media, fake)
    old = (job.out_dir / "short.mp4").read_bytes()
    for refused in (NAMELESS, OFF_MOOD, UNHEARD):
        with pytest.raises(pick.PickError):
            pick.pick(job, refused, library=fake)
    assert (job.out_dir / "short.mp4").read_bytes() == old


def test_a_two_bed_story_becomes_one_bed_with_the_page_notice(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library
) -> None:
    fake = _fake_library(library)
    story = FakePlanner().plan_sound(_plan_request(), _plan()).model_copy(update={
        "bed": [BedSegment(part_from="hook", mood="mysterious_curiosity"),
                BedSegment(part_from="reveal", mood="calm_ambient")],
        "change": BedChange(at_beat="b07", how="crossfade"),
    })  # fmt: skip
    job = _delivered(tmp_path, fixture_clip, media, fake, story)
    before = sound.balance_report(_stems(job))
    assert before is not None and len(before.beds) == 2 and before.windows
    page = app_module.render_job_page(job, library=fake)
    assert pick.REPLACES_CHANGE in page
    pick.pick(job, CC_BY, library=fake)
    after = sound.balance_report(_stems(job))
    assert after is not None and after.beds == [CC_BY] and after.windows == []
    assert not list(_stems(job).glob("music.[0-9].wav"))
    assert not list((_stems(job) / sound.START_DIR).glob("music.[0-9].wav"))
    music = [r.id for r in rights.load(job.path) or [] if r.kind == "music"]
    assert music == [CC_BY]


def test_a_failed_pick_keeps_the_old_file_stems_and_rights(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    fake = _fake_library(library)
    job = _delivered(tmp_path, fixture_clip, media, fake)
    kept = {
        path: path.read_bytes()
        for path in (job.out_dir / "short.mp4", _stems(job) / sound.BALANCE_NAME,
                     _stems(job) / "music.wav", job.out_dir / rights.RIGHTS_NAME,
                     job.out_dir / rights.CREDITS_NAME)
    }  # fmt: skip

    def quiet_master(source: Path, mix: Path) -> ffmpeg.Loudness:
        shutil.copyfile(source, mix)
        return ffmpeg.Loudness(integrated=-30.0, true_peak=-10.0, lra=1.0, threshold=-40.0,
                               offset=0.0)  # fmt: skip

    monkeypatch.setattr(render, "master", quiet_master)
    with pytest.raises(pick.PickError, match="T4"):
        pick.pick(job, CC_BY, library=fake)
    for path, data in kept.items():
        assert path.read_bytes() == data, path.name
    assert jobs.load(job.path).record.bed_pick is None
    assert not (job.out_dir / level.REMIX_NAME).exists()


def test_a_swept_job_shows_the_list_disabled(tmp_path: Path, library: sound.Library) -> None:
    fake = _fake_library(library)
    job = jobs.create(tmp_path)
    (job.out_dir / "short.mp4").write_bytes(b"")
    job = jobs.amend(job, status="delivered", swept_at=job.record.created_at)
    page = app_module.render_job_page(job, library=fake)
    block = page.split('class="bed-pick"')[1].split("</form>")[0]
    assert "disabled" in block
    assert pick.SWEPT_SENTENCE in page
    with pytest.raises(pick.PickError, match="deleted"):
        pick.pick(job, CC_BY, library=fake)


# --- the app ----------------------------------------------------------------------------


def test_the_page_pick_remixes_and_refuses_what_is_not_offered(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    fake = _fake_library(library)
    catalogue = _write_catalogue(tmp_path / "audio", fake)
    loaded = sound.load_catalogue(catalogue)
    job = _delivered(tmp_path / "data", fixture_clip, media, loaded)
    app = app_module.create_app(
        _settings(tmp_path), transcriber=FakeTranscriber(), planner=FakePlanner(),
        specs=SPECS, renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False, audio_catalogue=catalogue, audio_library=catalogue.parent,
    )  # fmt: skip
    with TestClient(app) as client:
        assert login(client).status_code == 303
        page = client.get(f"/jobs/{job.id}").text
        assert 'class="bed-pick"' in page and f'value="{CC_BY}"' in page
        heard = client.get(f"/audio/beds/{CC_BY}")
        assert heard.status_code == 200 and heard.content
        assert client.get(f"/audio/beds/{UNHEARD}").status_code == 404
        off = client.post(f"/jobs/{job.id}/bed-pick", data={"entry": OFF_MOOD})
        assert off.status_code == 422
        moved = client.post(f"/jobs/{job.id}/bed-pick", data={"entry": CC_BY},
                            follow_redirects=False)  # fmt: skip
        assert moved.status_code == 303
        record = jobs.load(job.path).record
        assert record.bed_pick is not None and record.bed_pick.entry_id == CC_BY
        short = job.out_dir / "short.mp4"
        old = short.read_bytes()

        def boom(*_: object, **__: object) -> None:
            raise pick.PickError("the remixed master missed T4: -30.0 LUFS")

        monkeypatch.setattr(pick, "pick", boom)
        failed = client.post(f"/jobs/{job.id}/bed-pick", data={"entry": FACTS})
        assert failed.status_code == 500 and "missed T4" in failed.text
        assert short.read_bytes() == old
        jobs.amend(job, swept_at=job.record.created_at)
        swept = client.post(f"/jobs/{job.id}/bed-pick", data={"entry": FACTS})
        assert swept.status_code == 409 and pick.SWEPT_SENTENCE in swept.text
