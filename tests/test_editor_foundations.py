"""094 foundations: hard violations, `keep_soft` validation, the editor's job record
(`decide`, `rewind`, `rework`) and QA checks the editor waived (`warn`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shortsmith import grammar, jobs, styles
from shortsmith.contracts import EditorDecision, MoodPoint, PicturePlan
from shortsmith.jobs import Clock, IllegalTransition, Status
from shortsmith.qa import technical
from shortsmith.qa.technical import QaCheck
from shortsmith.styles import StyleSpec
from tests.conftest import Media
from tests.test_grammar import (
    _items,  # pyright: ignore[reportPrivateUsage]
    _piece,  # pyright: ignore[reportPrivateUsage]
    as_clip,
    make_plan,
    no_variety,
    picture,
    story_for,
    transcript_for,
)
from tests.test_qa_technical import (
    ALL_CHECKS,
    _good_plan,  # pyright: ignore[reportPrivateUsage]
    _job_with,  # pyright: ignore[reportPrivateUsage]
)


@pytest.fixture(scope="module")
def spec() -> StyleSpec:
    from shortsmith import render

    return no_variety(styles.load_all(render.registry())["explainer"])  # 110b: test_variety


@pytest.fixture
def clock() -> Clock:
    t = [datetime(2026, 9, 30, 9, 0, 0, tzinfo=UTC)]

    def now() -> datetime:
        t[0] += timedelta(seconds=1)
        return t[0]

    return now


# --- grammar: hard violations and keep_soft ------------------------------------------------


def _short_b05() -> PicturePlan:
    lengths = [2.5] * 20
    lengths[2] = 0.69  # b05 under beats.min_s: a soft style rule
    return make_plan(body_lengths=lengths)


def test_hard_truths_are_flagged_and_style_rules_are_not(spec: StyleSpec) -> None:
    bad_item = picture(_piece(make_plan(), "b05", "wall", _items(4, asset="nope")), spec)
    assert isinstance(bad_item, grammar.Violations)
    assert [v.hard for v in bad_item.items if v.rule == "4.3"] == [True] * 4
    named_clip = picture(as_clip(make_plan(), "b06"), spec)
    assert isinstance(named_clip, grammar.Violations)
    assert any(v.hard and "named entity" in v.message for v in named_clip.items)
    must = picture(make_plan(), spec, must_use=["ref_missing"])
    assert isinstance(must, grammar.Violations)
    assert [(v.rule, v.hard) for v in must.items] == [("2.3", True)]
    soft = picture(_short_b05(), spec)
    assert isinstance(soft, grammar.Violations)
    assert soft.items and not any(v.hard for v in soft.items)
    # str() is unchanged by the flag
    assert str(bad_item.items[0]).startswith("b05 (")


def test_keep_soft_turns_a_style_break_into_a_warning(spec: StyleSpec) -> None:
    plan = _short_b05()
    default = picture(plan, spec)
    assert isinstance(default, grammar.Violations)
    kept = grammar.validate_picture(plan, transcript_for(plan), spec, keep_soft=True)
    assert isinstance(kept, grammar.PictureCheck)
    assert [f"kept by the editor: {v}" for v in default.items] == [
        w for w in kept.warnings if w.startswith("kept by the editor: ")
    ]
    assert any("b05 (3.1)" in w for w in kept.warnings)


def test_keep_soft_still_rejects_a_hard_truth(spec: StyleSpec) -> None:
    plan = _piece(_short_b05(), "b07", "wall", _items(4, asset="nope"))
    result = grammar.validate_picture(plan, transcript_for(plan), spec, keep_soft=True)
    assert isinstance(result, grammar.Violations)
    assert result.items and all(v.hard for v in result.items)
    assert {(v.beat_id, v.rule) for v in result.items} == {("b07", "4.3")}


def test_validate_carries_sound_warnings_into_the_validated_plan(spec: StyleSpec) -> None:
    plan = _short_b05()
    curve = [MoodPoint(t=0.0, level=0.0), MoodPoint(t=999.0, level=0.0)]
    story = story_for(plan, curve=curve)
    tr = transcript_for(plan)
    assert isinstance(grammar.validate(plan, story, tr, spec), grammar.Violations)
    sound = grammar.validate_sound(story, plan, spec)
    assert isinstance(sound, grammar.Violations)
    out = grammar.validate(plan, story, tr, spec, keep_soft=True)
    assert isinstance(out, grammar.ValidatedPlan)
    assert any("b05 (3.1)" in w for w in out.warnings)
    assert out.warnings[-1] == f"kept by the editor: {sound.items[-1]}"
    assert "mood point at 999 s" in out.warnings[-1]


# --- jobs: decide, rewind, rework -----------------------------------------------------------


def _walk(job: jobs.Job, to: Status, clock: Clock) -> jobs.Job:
    for status in jobs.STATUS_ORDER[1 : jobs.STATUS_ORDER.index(to) + 1]:
        job = jobs.transition(job, status, now=clock)
    return job


def _log(job: jobs.Job) -> list[str]:
    return job.log_path.read_text(encoding="utf-8").splitlines()


def test_decide_records_the_decision_and_logs_it(tmp_path: Path, clock: Clock) -> None:
    job = _walk(jobs.create(tmp_path, now=clock), "sourcing", clock)
    decision = EditorDecision(
        at=clock(), step="sourcing", beat_id="b04", problem="no photo found",
        choice="replace the visual", reason="nothing else fits", by="fallback",
    )  # fmt: skip
    job = jobs.decide(job, decision, now=clock)
    assert job.status == "sourcing"
    assert jobs.load(job.path).record.decisions == [decision]
    assert _log(job)[-1].endswith(
        "editor: sourcing b04: no photo found -> replace the visual (fallback: nothing else fits)"
    )
    plan_level = decision.model_copy(update={"beat_id": None, "by": "editor"})
    jobs.decide(job, plan_level, now=clock)
    assert " editor: sourcing plan: " in _log(job)[-1]
    assert len(jobs.load(job.path).record.decisions) == 2


def test_rewind_goes_back_and_the_pipeline_walks_forward_again(
    tmp_path: Path, clock: Clock
) -> None:
    job = _walk(jobs.create(tmp_path, now=clock), "rendering", clock)
    job = jobs.rewind(job, "sourcing", "b04: bad map", now=clock)
    assert job.status == "planning"
    assert _log(job)[-1].endswith("rendering -> sourcing rewind: b04: bad map")
    job = jobs.transition(job, "sourcing", now=clock)
    job = jobs.transition(job, "rendering", now=clock)
    # the same step again, and back to the first step
    job = jobs.rewind(job, "rendering", "strip overlays", now=clock)
    assert job.status == "sourcing"
    job = jobs.rewind(jobs.transition(job, "rendering", now=clock), "transcribing", "x", now=clock)
    assert job.status == "uploaded"
    assert jobs.transition(job, "transcribing", now=clock).status == "transcribing"


def test_rewind_refuses_a_later_step_or_a_settled_job(tmp_path: Path, clock: Clock) -> None:
    job = _walk(jobs.create(tmp_path, now=clock), "sourcing", clock)
    with pytest.raises(IllegalTransition):
        jobs.rewind(job, "rendering", "ahead", now=clock)
    with pytest.raises(IllegalTransition):
        jobs.rewind(job, "delivered", "not a step", now=clock)
    done = _walk(jobs.create(tmp_path, now=clock), "delivered", clock)
    with pytest.raises(IllegalTransition):
        jobs.rewind(done, "sourcing", "settled", now=clock)


def test_rework_reopens_a_settled_short_from_a_step(tmp_path: Path, clock: Clock) -> None:
    job = _walk(jobs.create(tmp_path, now=clock), "delivered", clock)
    job = jobs.rate(job, 6, "fine", now=clock)
    job = jobs.rework(job, "sourcing", "change: new image on b04", now=clock)
    assert job.status == "uploaded"
    assert job.record.retry_from == "sourcing" and job.record.error is None
    assert job.record.rating is not None and job.record.rating.score == 6
    assert _log(job)[-1].endswith(
        "delivered -> uploaded retry_from=sourcing rework: change: new image on b04"
    )
    assert jobs.transition(job, "sourcing", now=clock).status == "sourcing"
    in_flight = _walk(jobs.create(tmp_path, now=clock), "rendering", clock)
    with pytest.raises(IllegalTransition):
        jobs.rework(in_flight, "sourcing", "not settled", now=clock)


# --- qa: warn ---------------------------------------------------------------------------------


def test_a_warn_check_passes_the_report() -> None:
    warn = QaCheck(name="T8", passed=True, status="warn", detail="kept by the editor: x")
    assert warn.status == "warn"
    every = [QaCheck(name=n, passed=True, detail="x") for n in ALL_CHECKS]
    every[7] = warn
    report = technical.report(every)
    assert report.passed and report.failed is None
    with pytest.raises(ValueError):
        QaCheck(name="T8", passed=False, status="warn", detail="x")


def test_a_waived_check_is_delivered_as_warn_and_the_run_goes_on(
    media: Media, tmp_path: Path
) -> None:
    job = _job_with(
        tmp_path, media.clip(duration_s=2.0, width=720, height=1280, ext=".mp4"), _good_plan()
    )
    first = technical.run(job)
    assert [c.name for c in first.checks] == ["T1"] and first.checks[0].status == "fail"
    jobs.amend(job, waived_checks=["T1"])
    again = technical.run(job)
    t1 = again.checks[0]
    assert t1.status == "warn" and t1.passed
    assert t1.detail == "kept by the editor: " + first.checks[0].detail
    assert len(again.checks) > 1
