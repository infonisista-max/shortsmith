"""098 change box: the operator's words -> ops from the closed set (a scripted model),
every op checked against the real plan (anything unknown refuses the whole change), a
picture change patches the plans, keeps the short as the ONE previous version and
reworks the job from sourcing; a music change moves the mood curve and remixes the audio
only; the fake planner refuses with a sentence; the job page shows the box, the change
list, the previous version and the editor's decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shortsmith import app as app_module
from shortsmith import jobs, render, sound
from shortsmith.contracts import BalanceReport, MoodPoint, PicturePlan, SoundStory
from shortsmith.editor import change, repairs
from shortsmith.planner import FakePlanner
from shortsmith.presenter import FakeFaceDetector
from shortsmith.qa.gate import FakeGate
from shortsmith.render import FakeRenderer
from shortsmith.sound import level
from shortsmith.transcriber import FakeTranscriber
from tests.conftest import Media
from tests.test_app import (
    _post,  # pyright: ignore[reportPrivateUsage]
    _settings,  # pyright: ignore[reportPrivateUsage]
    login,
)
from tests.test_music_level import _delivered as mixed_job  # pyright: ignore[reportPrivateUsage]
from tests.test_pipeline import SPECS, _run, _uploaded  # pyright: ignore[reportPrivateUsage]

EXPLAINER = render.loaded_styles()["explainer"].sound


class _Scripted(FakePlanner):
    """The fake planner for the plans; `ask` answers with the canned reply."""

    def __init__(self, reply: object = None) -> None:
        self.reply = reply
        self.asks: list[tuple[str, str, str]] = []

    def ask(self, name: str, system: str, text: str, *, step: str) -> str:
        self.asks.append((system, text, step))
        if self.reply is None:
            return super().ask(name, system, text, step=step)
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def _delivered(tmp_path: Path, clip: Path) -> jobs.Job:
    done = _run(_uploaded(tmp_path, clip))
    assert done.status == "delivered"
    return done


def _plan(job: jobs.Job) -> PicturePlan:
    return PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))


def _layered(plan: PicturePlan) -> tuple[str, str]:
    """A beat (not the finale) and the first layer it carries."""
    for b in plan.beats:
        layers = repairs.layers_of(b)
        if layers and b.id != plan.finale.beat_id and b.kind != "map":
            return b.id, layers[0]
    raise AssertionError("the fake plan has no layered beat")


def _snapshot(job: jobs.Job) -> dict[str, bytes]:
    names = ["work/plan.json", "work/plan.validated.json", "work/captions.json",
             "work/sound.json", "out/short.mp4"]  # fmt: skip
    return {n: (job.path / n).read_bytes() for n in names if (job.path / n).is_file()}


# --- a picture change ---------------------------------------------------------------------


def test_a_picture_change_patches_the_plans_keeps_the_previous_short_and_reworks(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _delivered(tmp_path, fixture_clip)
    before = _plan(job)
    beat, layer = _layered(before)
    old_short = (job.out_dir / "short.mp4").read_bytes()
    planner = _Scripted({
        "ops": [{"op": "replace_visual", "beat": "b05"},
                {"op": "drop_layer", "beat": beat, "layer": layer}],
        "summary": "a plain picture for the map and one layer less",
    })  # fmt: skip
    planned = change.plan_change(job, "at 0:02 lose the map, and the clutter", planner)
    assert not planned.refused and planned.picture
    ((system, text, step),) = planner.asks
    assert step == "change" and "CLOSED list" in system and '"0:12"' in system
    assert "Topic: nothing." in text and "at 0:02 lose the map" in text
    assert "- b05 " in text and "@" in text and "mood curve" in text
    summary = change.apply_change(job, planned, specs=SPECS)
    assert summary.startswith("a plain picture for the map")
    for name in ("plan.json", "plan.validated.json"):
        data = json.loads((job.work_dir / name).read_text("utf-8"))
        plan = PicturePlan.model_validate(data.get("picture", data))
        assert repairs.beat_of(plan, "b05").kind == "photo"
        assert layer not in repairs.layers_of(repairs.beat_of(plan, beat))
    previous = job.out_dir / "previous" / "short.mp4"
    assert previous.read_bytes() == old_short
    record = jobs.load(job.path).record
    assert (record.status, record.retry_from) == ("uploaded", "sourcing")
    assert "b05" in record.replaced
    ops = [d for d in record.decisions if d.by == "operator"]
    assert [(d.step, d.beat_id) for d in ops] == [("change", "b05"), ("change", beat)]
    assert record.changes[-1].status == "running"
    log = job.log_path.read_text("utf-8")
    assert "change: asked: at 0:02 lose the map" in log
    assert "-> uploaded retry_from=sourcing rework: the operator's change" in log
    # the worker runs it on: delivered again, the change applied
    again = _run(jobs.load(job.path))
    assert again.status == "delivered"
    assert again.record.changes[-1].status == "applied"
    assert not (job.out_dir / "previous" / change.PENDING_NAME).exists()


@pytest.mark.parametrize(
    ("ops", "why"),
    [
        ([{"op": "replace_visual", "beat": "b99"}], "no beat 'b99'"),
        ([{"op": "paint", "beat": "b02"}], "'paint' is not a change"),
        ([{"op": "show_reference", "beat": "b02", "ref": "ref9"}], "not one of the owner's"),
        ([{"op": "drop_layer", "beat": "b02", "layer": "fireworks"}], "not a layer"),
        ([{"op": "replace_visual", "beat": "b02"}, {"op": "replace_visual", "beat": "b77"}],
         "no beat 'b77'"),
        ([{"op": "music", "from_s": 5, "to_s": 2, "db": -3}], "not a range"),
        ([{"op": "music_level", "offset_db": 99}], "music level must be"),
    ],
)
def test_an_unknown_op_beat_or_ref_refuses_the_whole_change_and_touches_nothing(
    tmp_path: Path, fixture_clip: Path, ops: list[dict[str, Any]], why: str
) -> None:
    job = _delivered(tmp_path, fixture_clip)
    files = _snapshot(job)
    planned = change.plan_change(job, "do something odd", _Scripted({"ops": ops}))
    assert why in planned.refused and not planned.ops
    with pytest.raises(change.ChangeRefused, match="refused"):
        change.apply_change(job, planned, specs=SPECS)
    assert _snapshot(job) == files
    record = jobs.load(job.path).record
    assert record.status == "delivered"
    assert record.changes[-1].status == "refused" and why in record.changes[-1].summary
    assert not [d for d in record.decisions if d.by == "operator"]
    assert not (job.out_dir / "previous").exists()


def test_the_fake_planner_refuses_with_a_sentence(tmp_path: Path, fixture_clip: Path) -> None:
    job = _delivered(tmp_path, fixture_clip)
    planned = change.plan_change(job, "make the map bigger", FakePlanner())
    assert planned.refused.startswith("the editor is not available: ")
    assert "change: refused: the editor is not available" in job.log_path.read_text("utf-8")


def test_a_refusal_the_model_gives_is_recorded(tmp_path: Path, fixture_clip: Path) -> None:
    job = _delivered(tmp_path, fixture_clip)
    planned = change.plan_change(job, "add a dancing cat", _Scripted({"refuse": "no such op"}))
    assert planned.refused == "the editor cannot do this: no such op"


# --- a music change -------------------------------------------------------------------------


def test_shift_curve_moves_only_the_range_with_ramps_and_clips() -> None:
    points = [MoodPoint(t=0.0, level=0.0), MoodPoint(t=10.0, level=2.0),
              MoodPoint(t=20.0, level=0.0)]  # fmt: skip
    out = change.shift_curve(points, from_s=8.0, to_s=12.0, db=-4.0, nums=EXPLAINER,
                             runtime_s=20.0)  # fmt: skip
    got = {p.t: p.level for p in out}
    ramp = EXPLAINER.ramp_min_s
    assert got[0.0] == 0.0 and got[20.0] == 0.0  # outside untouched
    assert got[8.0 - ramp] == pytest.approx((8.0 - ramp) / 10 * 2.0, abs=1e-3)
    assert got[8.0] == pytest.approx(1.6 - 4.0) and got[10.0] == -2.0
    assert got[12.0] == pytest.approx(1.6 - 4.0)
    assert got[12.0 + ramp] == pytest.approx(2.0 - (2.0 + ramp) / 10 * 2.0, abs=1e-3)
    loud = change.shift_curve(points, from_s=8.0, to_s=12.0, db=9.0, nums=EXPLAINER,
                              runtime_s=20.0)  # fmt: skip
    assert max(p.level for p in loud) == EXPLAINER.swell_max_db
    assert [p.t for p in loud] == sorted(p.t for p in loud)


def test_a_music_range_changes_the_mood_curve_and_remixes_the_audio_only(
    tmp_path: Path, fixture_clip: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _delivered(tmp_path, fixture_clip)
    story = SoundStory.model_validate_json((job.work_dir / "sound.json").read_text("utf-8"))
    old_short = (job.out_dir / "short.mp4").read_bytes()
    plan_before = (job.work_dir / "plan.json").read_bytes()
    mixed: list[SoundStory] = []

    def fake_deliver(job: jobs.Job, mix: Any) -> BalanceReport:
        # the recurve mixer is what the delivery runs; the stems are the real test's
        calls = mix.__code__.co_names
        assert "recurve" in calls
        mixed.append(SoundStory.model_validate_json(
            (job.work_dir / "sound.json").read_text("utf-8")))  # fmt: skip
        (job.out_dir / "short.mp4").write_bytes(b"remixed")
        return BalanceReport.model_validate({
            "voice_db": -20, "bed_accept_db": (-15, -12), "speech_band_margin_min_db": 12,
            "duck_max_db": 6,
        })  # fmt: skip

    def no_refusal(job: jobs.Job) -> str:
        return ""

    monkeypatch.setattr(level, "refusal", no_refusal)
    monkeypatch.setattr(level, "deliver", fake_deliver)
    planned = change.plan_change(
        job, "music quieter from 0:01 to 3s",
        _Scripted({"ops": [{"op": "music", "from_s": "0:01", "to_s": "3s", "db": -4}]}),
    )  # fmt: skip
    assert not planned.refused and not planned.picture
    change.apply_change(job, planned, specs=SPECS)
    assert len(mixed) == 1 and mixed[0] == story, "the story is written once the mix delivered"
    after = SoundStory.model_validate_json((job.work_dir / "sound.json").read_text("utf-8"))
    assert after.mood_curve != story.mood_curve
    moved = {p.t: p.level for p in after.mood_curve}
    assert 1.0 in moved and 3.0 in moved
    assert all(EXPLAINER.drop_min_db <= p.level <= EXPLAINER.swell_max_db
               for p in after.mood_curve)  # fmt: skip
    validated = json.loads((job.work_dir / "plan.validated.json").read_text("utf-8"))
    assert validated["sound"]["mood_curve"] == json.loads(after.model_dump_json())["mood_curve"]
    assert (job.work_dir / "plan.json").read_bytes() == plan_before
    assert (job.out_dir / "previous" / "short.mp4").read_bytes() == old_short
    record = jobs.load(job.path).record
    assert record.status == "delivered" and record.changes[-1].status == "applied"
    assert [d.choice for d in record.decisions if d.by == "operator"] == [
        "music -4 dB from 1 s to 3 s"
    ]


def test_recurve_rebuilds_the_bed_stem_with_the_new_curve(
    tmp_path: Path, fixture_clip: Path, media: Media, library: sound.Library,
) -> None:  # fmt: skip
    """The real audio path: the delivered bed rendered again through the renderer's own
    `_music_stem` with the moved curve reaches the stem - the range is quieter against the
    rest by about the shift."""
    job = mixed_job(tmp_path, fixture_clip, media, library)
    stems = job.work_dir / "stems"
    story = SoundStory.model_validate_json((job.work_dir / "sound.json").read_text("utf-8"))
    plan = _plan(job)
    runtime = change.runtime_of(job, plan)

    def median(path: Path, start: float, end: float) -> float:
        got = sound._median_db(path, prefilter=sound.trim(start, end))  # pyright: ignore[reportPrivateUsage]
        assert got is not None
        return got

    inside, outside = (runtime - 1.8, runtime - 1.3), (0.7, 1.2)
    music = stems / "music.wav"
    before_in, before_out = median(music, *inside), median(music, *outside)
    curve = change.shift_curve(story.mood_curve, from_s=runtime - 2.5, to_s=runtime, db=-8.0,
                               nums=EXPLAINER, runtime_s=runtime)  # fmt: skip
    moved = story.model_copy(update={"mood_curve": curve})
    level.deliver(job, lambda s, scratch: sound.recurve(
        s, scratch, library=library, story=moved, plan=plan, nums=EXPLAINER, runtime_s=runtime,
        offset_db=0.0,
    ))  # fmt: skip
    after_in, after_out = median(music, *inside), median(music, *outside)
    assert (stems / sound.START_DIR / "music.wav").is_file(), "the slider's base is the new curve"
    relative = (before_in - after_in) - (before_out - after_out)
    assert relative > 3.0, f"the range moved only {relative:.1f} dB against the rest"


# --- the job page ---------------------------------------------------------------------------


def _app(tmp_path: Path, planner: FakePlanner) -> FastAPI:
    return app_module.create_app(
        _settings(tmp_path), transcriber=FakeTranscriber(), planner=planner, specs=SPECS,
        renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False,
    )  # fmt: skip


def test_the_page_offers_the_box_and_a_change_runs_on_the_worker(
    tmp_path: Path, media: Media
) -> None:
    planner = _Scripted()
    app = _app(tmp_path, planner)
    with TestClient(app) as client:
        login(client)
        location = _post(client, media.clip()).headers["location"]
        assert app.state.worker.run_next() is True
        body = client.get(location).text
        assert "<h2>Change this reel</h2>" in body
        assert f'action="{location}/change"' in body and 'name="text"' in body
        assert "Previous version" not in body
        planner.reply = {"ops": [{"op": "replace_visual", "beat": "b05"}],
                         "summary": "a plain picture for the map"}  # fmt: skip
        resp = client.post(f"{location}/change", data={"text": "no map at 0:02"},
                           follow_redirects=False)  # fmt: skip
        assert resp.status_code == 303 and resp.headers["location"] == location
        assert client.get(f"{location}.json").json()["status"] == "uploaded"
        assert app.state.worker.run_next() is True
        body = client.get(location).text
        assert 'data-step="delivered" class="step current"' in body
        assert "<h2>Previous version</h2>" in body
        assert f'src="{location}/previous/short.mp4"' in body
        assert client.get(f"{location}/previous/short.mp4").status_code == 200
        assert '<li class="change-row applied"><strong>applied</strong>' in body
        assert "&ldquo;no map at 0:02&rdquo;" in body
        assert "<h2>Editor&#x27;s decisions</h2>" in body or "<h2>Editor's decisions</h2>" in body
        assert '<li class="decision operator"><strong>change b05</strong>' in body
        # a refused change is a row with its reason; nothing re-runs
        planner.reply = {"ops": [{"op": "replace_visual", "beat": "b99"}]}
        resp = client.post(f"{location}/change", data={"text": "fix b99"}, follow_redirects=False)
        assert resp.status_code == 303
        assert client.get(f"{location}.json").json()["status"] == "delivered"
        page = client.get(location).text
        assert '<li class="change-row refused"><strong>refused</strong>' in page


def test_the_change_route_refuses_without_a_short_or_words(tmp_path: Path, media: Media) -> None:
    app = _app(tmp_path, _Scripted())
    with TestClient(app) as client:
        login(client)
        location = _post(client, media.clip()).headers["location"]
        resp = client.post(f"{location}/change", data={"text": "anything"})
        assert resp.status_code == 409 and "no finished short to change" in resp.text
        assert "Change this reel" not in client.get(location).text
        assert client.get(f"{location}/previous/short.mp4").status_code == 404
        assert app.state.worker.run_next() is True
        resp = client.post(f"{location}/change", data={"text": "   "})
        assert resp.status_code == 422
        assert client.post("/jobs/20260101-000000-abcdef/change",
                           data={"text": "x"}).status_code == 404  # fmt: skip

