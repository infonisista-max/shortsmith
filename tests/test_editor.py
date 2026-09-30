"""097 editor rescue: the pure repairs, the closed options and their code fallback, the
editor's one prompt per round (a listed id is honoured, anything else falls back), and
the pipeline's rescues - a render failure naming a beat, the same failure twice, a
failing check - that deliver instead of failing."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from shortsmith import editor, geo, jobs, pipeline, sound
from shortsmith.contracts import (
    Constraints,
    MapMarker,
    MapPlan,
    PicturePlan,
    PlanRequest,
    PlanStyle,
    Span,
    Transcript,
)
from shortsmith.editor import DELIVER, KEEP, REPLACE, Editor, Snag, make_snag, repairs
from shortsmith.planner import FakePlanner
from shortsmith.qa import technical
from shortsmith.qa.gate import FakeGate
from shortsmith.qa.technical import QaCheck, QaReport
from shortsmith.render import FakeRenderer, RenderError
from shortsmith.transcriber import FakeTranscriber
from tests.test_pipeline import SPECS, _run, _uploaded  # pyright: ignore[reportPrivateUsage]

GAZETTEER_MISS = (
    "b05: the map region 'Atlantis' is not in the gazetteer (and no fallback answered); "
    "a marker is never placed by a guess (9.3)"
)


def _transcript() -> Transcript:
    return FakeTranscriber().transcribe(Path("unused.mp4"))


def _plan() -> PicturePlan:
    """The fake planner's eleven beats: b05 is the India map (Delhi -> Mumbai), b07 the
    infographic whose asset a6 set-piece items share, b04 the clip."""
    spec = SPECS["explainer"]
    transcript = _transcript()
    request = PlanRequest(
        brief="Topic: nothing.",
        style=PlanStyle(name=spec.name, numbers=spec.numbers(), prose=spec.prose),
        style_note="",
        transcript=transcript,
        references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=transcript.duration_s),
        asset_policy="any",
    )
    return FakePlanner().plan_picture(request)


def _beat(plan: PicturePlan, beat_id: str):  # noqa: ANN202 - a Beat
    return repairs.beat_of(plan, beat_id)


# --- the pure repairs -------------------------------------------------------------------


def test_drop_layer_is_pure_and_touches_only_that_beat() -> None:
    plan = _plan()
    before = plan.model_dump()
    dropped = repairs.drop_layer(plan, "b04", "bubbles")
    assert plan.model_dump() == before  # the input is never changed
    assert _beat(dropped, "b04").bubbles == []
    assert _beat(dropped, "b04").event == _beat(plan, "b04").event
    assert [b for b in dropped.beats if b.id != "b04"] == [
        b for b in plan.beats if b.id != "b04"
    ]
    event_off = repairs.drop_layer(plan, "b04", "event")
    assert _beat(event_off, "b04").event.kind == "none"
    counter_off = repairs.drop_layer(plan, "b06", "counter")
    assert _beat(counter_off, "b06").counter is None
    assert "counter" not in _beat(counter_off, "b06").overlays


def test_drop_route_keeps_the_markers_and_the_pins() -> None:
    b05 = _beat(repairs.drop_route(_plan(), "b05"), "b05")
    assert b05.map is not None and b05.map.route == [] and b05.map.object is None
    assert [m.name for m in b05.map.markers] == ["Delhi", "Mumbai"]
    assert b05.overlays == ["pin_drop"]


def test_replace_visual_makes_a_plain_photo_the_ladder_re_sources() -> None:
    plan = _plan()
    b05 = _beat(repairs.replace_visual(plan, "b05"), "b05")
    assert (b05.kind, b05.map, b05.overlays, b05.asset_id) == ("photo", None, [], None)
    assert b05.motion == "ken_burns_in"  # `travel` is not a photo motion
    assert b05.query == "Delhi to Mumbai route" and b05.subject_kind == "entity"
    # a6 is shared by b08's and b10's items: the id stays planned so they still resolve
    b07 = _beat(repairs.replace_visual(plan, "b07"), "b07")
    assert b07.kind == "photo" and b07.labels == [] and b07.asset_id == "a6"
    assert b07.motion == "ken_burns_in"
    b06 = _beat(repairs.replace_visual(plan, "b06"), "b06")
    assert (b06.chart_form, b06.series, b06.counter, b06.set_piece_title) == (None, [], None, "")


def test_no_cut_place_reference_retile_and_strip() -> None:
    plan, transcript = _plan(), _transcript()
    whole = repairs.no_cut(plan, transcript)
    assert whole.cut.keep == [Span(start=0.0, end=transcript.duration_s)] and not whole.cut.drop
    assert _beat(repairs.place_reference(plan, "b01", "ref1"), "b01").asset_id == "ref1"
    beats = list(plan.beats)
    beats[2] = beats[2].model_copy(update={"start": 1.1})  # a gap after b02
    beats[4] = beats[4].model_copy(update={"start": 1.9})  # an overlap with b04
    tiled = repairs.retile(plan.model_copy(update={"beats": beats}), 6.0)
    assert tiled.beats[0].start == 0.0 and tiled.beats[-1].end == 6.0
    assert all(a.end == b.start for a, b in zip(tiled.beats, tiled.beats[1:], strict=False))
    assert tiled.beats[1].end == 1.1 and tiled.beats[3].end == 1.9
    bare = repairs.strip_overlays(plan)
    for b in bare.beats:
        assert not (b.text_pops or b.bubbles or b.stickers or b.overlays or b.highlight)
        assert b.event.kind == "none" and b.counter is None
    assert _beat(bare, "b05").map == _beat(plan, "b05").map  # the data itself stays


# --- frame_markers: real coordinates only -------------------------------------------------


def test_frame_markers_frames_the_markers_real_coordinates() -> None:
    coder = geo.FakeGeocoder()
    framed = _beat(repairs.frame_markers(_plan(), "b05", coder), "b05")
    delhi, mumbai = coder.lookup("Delhi"), coder.lookup("Mumbai")
    assert delhi is not None and mumbai is not None
    assert framed.map is not None and framed.map.region == ""
    assert framed.map.bbox == (mumbai.lon, mumbai.lat, delhi.lon, delhi.lat)


def test_one_marker_is_framed_a_city_span_across() -> None:
    plan = _plan()
    one = MapPlan(region="Nowhere", markers=[MapMarker(name="Tokyo")])
    beats = [b.model_copy(update={"map": one, "overlays": []}) if b.id == "b05" else b
             for b in plan.beats]  # fmt: skip
    framed = _beat(repairs.frame_markers(plan.model_copy(update={"beats": beats}), "b05",
                                         geo.FakeGeocoder()), "b05")  # fmt: skip
    assert framed.map is not None and framed.map.bbox is not None
    west, south, east, north = framed.map.bbox
    assert east - west == pytest.approx(3.0) and north - south == pytest.approx(3.0)
    assert (west + east) / 2 == pytest.approx(139.751)
    assert (south + north) / 2 == pytest.approx(35.685)


def test_frame_markers_is_only_offered_when_every_name_resolves() -> None:
    plan = _plan()
    ids = [o.id for o in editor.beat_options(plan, "b05", hard=True, geocoder=geo.FakeGeocoder())]
    assert "frame_markers" in ids and "drop_route" in ids and ids[-1] == REPLACE
    lost = MapPlan(region="Atlantis", markers=[MapMarker(name="Delhi"), MapMarker(name="Atlantis")])
    beats = [b.model_copy(update={"map": lost, "overlays": ["pin_drop"]}) if b.id == "b05" else b
             for b in plan.beats]  # fmt: skip
    options = editor.beat_options(plan.model_copy(update={"beats": beats}), "b05", hard=True,
                                  geocoder=geo.FakeGeocoder())  # fmt: skip
    assert "frame_markers" not in [o.id for o in options]
    assert editor.fallback_for(GAZETTEER_MISS, options, hard=True) == REPLACE
    with pytest.raises(repairs.RepairError):
        repairs.frame_markers(plan.model_copy(update={"beats": beats}), "b05", geo.FakeGeocoder())


def test_the_fallback_is_the_most_targeted_fix_the_problem_names() -> None:
    plan = _plan()
    coder = geo.FakeGeocoder()
    b05 = editor.beat_options(plan, "b05", hard=True, geocoder=coder)
    assert editor.fallback_for(GAZETTEER_MISS, b05, hard=True) == "frame_markers"
    route = "b05: the map route point 'Pune' is not in the gazetteer"
    assert editor.fallback_for(route, b05, hard=True) == "drop_route"
    b04 = editor.beat_options(plan, "b04", hard=False)
    assert editor.fallback_for("stamp 'NOTHING' has no spot", b04, hard=False) == "drop_event"
    assert editor.fallback_for("bubble 'hi' does not fit", b04, hard=False) == KEEP  # none on b04
    assert editor.fallback_for("beat is 0.4 s, under beats.min_s", b04, hard=False) == KEEP
    assert editor.fallback_for("the during string rings", b04, hard=True) == REPLACE
    assert KEEP not in [o.id for o in editor.beat_options(plan, "b04", hard=True)]
    assert REPLACE not in [o.id for o in editor.beat_options(plan, "b11", hard=True)]


# --- the editor: one prompt, listed ids only ----------------------------------------------


class _Scripted(FakePlanner):
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.asks: list[tuple[str, str, str, str]] = []

    def ask(self, name: str, system: str, text: str, *, step: str) -> str:
        self.asks.append((name, system, text, step))
        return self.reply


def _job(tmp_path: Path) -> jobs.Job:
    job = jobs.create(tmp_path, style="explainer", style_note="")
    (job.input_dir / "brief.md").write_text("Topic: a map of India.", encoding="utf-8")
    return job


def _snag(plan: PicturePlan) -> Snag:
    options = editor.beat_options(plan, "b05", hard=True, geocoder=geo.FakeGeocoder(), keep=False)
    return make_snag("s1", "rendering", "b05", GAZETTEER_MISS, hard=True, options=options)


def test_a_listed_option_the_editor_picks_is_honoured_and_recorded(tmp_path: Path) -> None:
    job, plan = _job(tmp_path), _plan()
    reply = {"choices": [{"snag": "s1", "option": "drop_route",
                          "reason": "the line only names the two cities"}]}  # fmt: skip
    planner = _Scripted("Sure:\n```json\n" + json.dumps(reply) + "\n```")
    (choice,) = Editor(planner).pick(job, [_snag(plan)], step="rendering", plan=plan,
                                     transcript=_transcript())  # fmt: skip
    assert choice.option.id == "drop_route" and choice.decision.by == "editor"
    assert choice.decision.reason == "the line only names the two cities"
    ((name, system, text, step),) = planner.asks
    assert step == "rendering" and name.startswith("rendering_1_")
    assert "only pick one of the option ids listed" in system and "Say why like an editor" in system
    assert "Topic: a map of India." in text and "What failed: " + GAZETTEER_MISS in text
    assert "`frame_markers`" in text and "Beats around it: b04, b05, b06" in text
    record = jobs.load(job.path).record
    assert [d.choice for d in record.decisions] == [choice.option.label]
    assert "editor: rendering b05: " in job.log_path.read_text("utf-8")


@pytest.mark.parametrize(
    "reply",
    [
        '{"choices":[{"snag":"s1","option":"paint_new_map","reason":"x"}]}',
        "I would frame it on the markers.",
        '{"choices": "frame_markers"}',
    ],
)
def test_an_unknown_id_or_a_bad_reply_takes_the_code_fallback(tmp_path: Path, reply: str) -> None:
    job, plan = _job(tmp_path), _plan()
    (choice,) = Editor(_Scripted(reply)).pick(job, [_snag(plan)], step="rendering")
    assert choice.option.id == "frame_markers" and choice.decision.by == "fallback"


def test_the_fake_planner_answers_every_snag_with_its_fallback(tmp_path: Path) -> None:
    job, plan = _job(tmp_path), _plan()
    decisions = Editor(FakePlanner()).choose(job, [_snag(plan)], step="rendering")
    assert [d.by for d in decisions] == ["fallback"]
    assert "PlannerUnavailable" in decisions[0].reason


# --- the pipeline's rescues ----------------------------------------------------------------


class _FailsOnce(FakeRenderer):
    """Raises `messages` in turn on the first renders, then renders like the fake."""

    def __init__(self, *messages: str) -> None:
        super().__init__()
        self.messages = list(messages)

    def render(
        self, job: jobs.Job, *, on_progress: Callable[[int], None] | None = None,
        library: sound.Library | None = None,
    ) -> Path:  # fmt: skip
        if self.messages:
            raise RenderError(self.messages.pop(0))
        return super().render(job, on_progress=on_progress, library=library)


def _trail(job: jobs.Job) -> list[str]:
    return [line.split(" ", 1)[1] for line in job.log_path.read_text("utf-8").splitlines()]


def test_a_render_failure_naming_a_map_beat_is_rescued_and_delivered(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """run05's failure (b09: 'Middle East' not in the gazetteer), on the fake plan's map:
    the fallback frames b05 on its markers, the plan files are patched, the job rewinds
    to sourcing and is delivered."""
    job = _uploaded(tmp_path, fixture_clip)
    renderer = _FailsOnce(GAZETTEER_MISS)
    done = _run(job, renderer=renderer)
    assert done.status == "delivered" and done.record.error is None
    (decision,) = done.record.decisions
    assert (decision.step, decision.beat_id, decision.by) == ("rendering", "b05", "fallback")
    assert decision.choice.startswith("frame the map on its markers (Delhi, Mumbai)")
    for name in ("plan.json", "plan.validated.json"):
        text = (job.work_dir / name).read_text("utf-8")
        plan = PicturePlan.model_validate(json.loads(text).get("picture", json.loads(text)))
        b05 = repairs.beat_of(plan, "b05")
        assert b05.map is not None and b05.map.region == "" and b05.map.bbox is not None
    trail = _trail(job)
    assert "rescue 1/12: rendering: " + GAZETTEER_MISS in trail
    assert "rendering -> sourcing rewind: the editor fixed b05 (frame_markers)" in trail
    assert "qa -> delivered" in trail
    assert trail.count("planning -> sourcing") == 2  # the rewind re-enters sourcing


def test_the_same_beat_failing_twice_is_replaced_and_marked_for_the_ladder(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    problem = "b04: stamp 'NOTHING' has no spot clear of the face (056)"
    done = _run(job, renderer=_FailsOnce(problem, problem))
    assert done.status == "delivered"
    first, second = done.record.decisions
    assert first.choice == "drop this beat's landed event (stamp, ring or lower-third)"
    assert second.choice.startswith("replace this beat's visual") and second.by == "fallback"
    assert second.reason == "the same problem came back after the first fix"
    assert done.record.replaced == ["b04"]
    plan = PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))
    assert repairs.beat_of(plan, "b04").kind == "photo"


def test_a_render_engine_that_is_missing_still_fails_the_job(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job, renderer=_FailsOnce("node is not on PATH; the picture engine needs Node"))
    assert done.status == "failed" and done.record.decisions == []


class _FailsCheckOnce(FakeGate):
    """T8 fails naming b04 on the first run only."""

    def check(self, job: jobs.Job) -> QaReport:
        if self.jobs:
            return super().check(job)
        self.jobs.append(job.path)
        rows = [QaCheck(name=n, passed=True, detail="ok") for n in technical.CHECK_ORDER[:7]]
        rows.append(QaCheck(name="T8", passed=False, detail="b04: 2 rescued beats over the limit"))
        report = technical.report(rows)
        technical.write_report(job, report)
        return report


def test_a_check_naming_a_beat_offers_its_options_and_falls_back_to_a_note(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job, gate=_FailsCheckOnce())
    assert done.status == "delivered"
    (decision,) = done.record.decisions
    assert decision.beat_id == "b04" and decision.choice.startswith("deliver with a note")
    assert done.record.waived_checks == ["T8"]


def test_the_worker_builds_the_editor_on_its_planner_and_renderers_geocoder() -> None:
    coder = geo.FakeGeocoder()
    from shortsmith.render import RemotionRenderer

    worker = pipeline.Worker(transcriber=FakeTranscriber(), planner=FakePlanner(),
                             renderer=RemotionRenderer(geocoder=coder))  # fmt: skip
    built = worker._editor  # pyright: ignore[reportPrivateUsage]
    assert isinstance(built.planner, FakePlanner) and built.geocoder is coder
    assert DELIVER == "deliver_with_note"
