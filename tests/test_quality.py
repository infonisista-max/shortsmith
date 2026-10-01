"""112a: strict mode. A crash or a missing thing fails the job loudly, naming the beat,
the step or the check, where a rescue net would deliver a downgraded reel; forgiving
mode keeps every net. Each job stamps its mode; every finding is a row of the running
`data/quality-log.tsv`."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shortsmith import assets, grammar, jobs, pipeline, presenter, quality, render, sound, subproc
from shortsmith.app import render_job_page
from shortsmith.budgets import Budgets
from shortsmith.contracts import PicturePlan, Transcript, Violation
from shortsmith.planner import FakePlanner
from shortsmith.qa import technical
from shortsmith.qa.critic import FakeCritic
from shortsmith.qa.gate import FakeGate, Gate
from shortsmith.render import FakeRenderer, Renderer
from shortsmith.transcriber import FakeTranscriber
from tests.test_pipeline import BRIEF, SPECS

Progress = Callable[[int], None] | None


@pytest.fixture
def strict(monkeypatch: pytest.MonkeyPatch) -> str:
    """Strict whatever the operator's `.env` says (it is the default anyway)."""
    monkeypatch.setenv("QUALITY_MODE", "strict")
    return "strict"


def _uploaded(data_dir: Path, clip: Path) -> jobs.Job:
    job = jobs.create(data_dir, style="explainer", style_note="explainer, energetic")
    shutil.copyfile(clip, job.input_dir / "raw.mp4")
    (job.input_dir / "brief.md").write_text(BRIEF, encoding="utf-8")
    (job.input_dir / "refs.json").write_text("[]", encoding="utf-8")
    return job


def _sourcing() -> assets.Sourcing:
    return assets.Sourcing(sources={"web": assets.FakeImageSource("web")}, order=("web",))


def _run(job: jobs.Job, renderer: Renderer | None = None, gate: Gate | None = None,
         budgets: Budgets | None = None,
         clock: Callable[[], datetime] | None = None) -> jobs.Job:  # fmt: skip
    return pipeline.run_job(
        job, transcriber=FakeTranscriber(), planner=FakePlanner(),
        renderer=renderer or FakeRenderer(), gate=gate or FakeGate(), sourcing=_sourcing(),
        specs=SPECS, detector=presenter.FakeFaceDetector(), critic=FakeCritic(), budgets=budgets,
        clock=clock or (lambda: datetime.now(UTC)),
    )  # fmt: skip


class _Raises(FakeRenderer):
    """The full edit raises `exc` (after `before`, if given); the plain reel is the fake's."""

    def __init__(self, exc: Exception, before: Callable[[jobs.Job], None] | None = None) -> None:
        super().__init__()
        self.exc = exc
        self.before = before

    def render(self, job: jobs.Job, *, on_progress: Progress = None,
               library: sound.Library | None = None) -> Path:  # fmt: skip
        if self.before is not None:
            self.before(job)
        raise self.exc


def _log_rows(data_dir: Path) -> list[list[str]]:
    lines = (data_dir / quality.LOG_NAME).read_text(encoding="utf-8").splitlines()
    assert lines[0].split("\t") == list(quality.LOG_COLUMNS)
    return [line.split("\t") for line in lines[1:]]


def _assert_loud(done: jobs.Job, step: str, *, plain: list[Path]) -> jobs.QualityFinding:
    """Failed at `step` with one finding; no plain reel, no decision; job.log and the
    page name it."""
    assert done.status == "failed", done.record
    assert done.record.error is not None
    assert done.record.error.step == step
    assert plain == []
    assert done.record.plain_reel is None
    assert done.record.decisions == []
    assert done.record.replaced == [] and done.record.waived_checks == []
    findings = done.record.error.findings
    assert len(findings) == 1
    log = done.log_path.read_text(encoding="utf-8")
    assert f"strict stop: {findings[0].line()}" in log
    page = render_job_page(done)
    assert findings[0].cause in page or findings[0].cause.replace("'", "&#x27;") in page
    assert "<details" in page
    return findings[0]


# --- the setting and the stamp --------------------------------------------------------------


@pytest.mark.usefixtures("strict")
def test_a_job_stamps_strict_by_default_and_the_page_shows_it(tmp_path: Path) -> None:
    job = jobs.create(tmp_path)
    assert job.record.quality_mode == "strict"
    assert jobs.load(job.path).record.quality_mode == "strict"
    assert "Quality mode: strict" in render_job_page(job)


@pytest.mark.usefixtures("forgiving")
def test_a_job_stamps_forgiving_when_the_setting_says_so(tmp_path: Path) -> None:
    job = jobs.create(tmp_path)
    assert quality.mode_of(job) == "forgiving"
    assert "Quality mode: forgiving" in render_job_page(job)


def test_a_job_keeps_its_stamp_and_an_unstamped_job_reads_the_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QUALITY_MODE", "forgiving")
    stamped = jobs.create(tmp_path)
    old = jobs.amend(jobs.create(tmp_path), quality_mode=None)  # made before 112a
    monkeypatch.setenv("QUALITY_MODE", "strict")
    assert quality.mode_of(jobs.load(stamped.path)) == "forgiving"
    assert quality.mode_of(jobs.load(old.path)) == "strict"


# --- the helper -----------------------------------------------------------------------------


@pytest.mark.usefixtures("strict")
def test_strict_downgrade_raises_and_never_applies(tmp_path: Path) -> None:
    job = jobs.create(tmp_path)
    applied: list[str] = []
    with pytest.raises(quality.QualityStop) as stop:
        quality.downgrade(job, "b52", "its background is a video clip, but a wall draws a still",
                          "ValueError: clip on a wall", lambda: applied.append("x"),
                          kind="wall")  # fmt: skip
    assert applied == []
    [finding] = stop.value.findings
    assert (finding.beat, finding.kind) == ("b52", "wall")
    assert finding.line() == "beat b52 (wall): its background is a video clip, but a wall " \
        "draws a still"  # fmt: skip
    [row] = _log_rows(tmp_path)
    assert row[1:] == [job.id, "b52", "wall", "stop",
                       "its background is a video clip, but a wall draws a still"]  # fmt: skip
    datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.usefixtures("forgiving")
def test_forgiving_downgrade_applies_and_logs_a_repair(tmp_path: Path) -> None:
    job = jobs.create(tmp_path)
    assert quality.downgrade(job, None, "the rendering step failed", "boom", lambda: 7) == 7
    [row] = _log_rows(tmp_path)
    assert row[1:] == [job.id, "-", "-", "repair", "the rendering step failed"]


@pytest.mark.usefixtures("strict")
def test_a_stop_carries_every_finding_and_a_second_job_appends(tmp_path: Path) -> None:
    first, second = jobs.create(tmp_path), jobs.create(tmp_path)
    findings = [quality.Finding(beat=f"b{i}", kind="photo", cause=f"cause\t{i}\nmore")
                for i in (1, 2)]  # fmt: skip
    with pytest.raises(quality.QualityStop) as stop:
        quality.downgrade_all(first, findings, lambda: None)
    assert [f.beat for f in stop.value.findings] == ["b1", "b2"]
    with pytest.raises(quality.QualityStop):
        quality.downgrade(second, None, "a check failed", "", lambda: None)
    rows = _log_rows(tmp_path)
    assert [(r[1], r[2], r[5]) for r in rows] == [
        (first.id, "b1", "cause 1 more"), (first.id, "b2", "cause 2 more"),
        (second.id, "-", "a check failed"),
    ]  # fmt: skip


@pytest.mark.usefixtures("strict")
def test_a_pass_with_no_findings_goes_ahead_in_strict_mode(tmp_path: Path) -> None:
    """112b: a pass that found nothing (a check with only true fixes) never stops."""
    job = jobs.create(tmp_path)
    assert quality.downgrade_all(job, [], lambda: 7) == 7
    assert not quality.log_path(job).exists()


# --- the four cases, strict -----------------------------------------------------------------


@pytest.mark.usefixtures("strict")
def test_strict_a_render_failure_naming_a_beat_fails_loudly(
    tmp_path: Path, fixture_clip: Path
) -> None:
    renderer = _Raises(render.RenderError("b01: the map region 'Atlantis' is not in the gazetteer"))
    done = _run(_uploaded(tmp_path, fixture_clip), renderer)
    finding = _assert_loud(done, "rendering", plain=renderer.plain_jobs)
    assert finding.beat == "b01" and finding.kind
    assert "Atlantis" in finding.cause
    assert "beat b01" in done.record.error.message  # type: ignore[union-attr]
    assert len(renderer.jobs) == 0 and renderer.plain_jobs == []
    assert [r[4] for r in _log_rows(tmp_path)] == ["stop"]


@pytest.mark.usefixtures("strict")
def test_strict_a_mux_crash_fails_loudly_and_shows_the_picture_only(
    tmp_path: Path, fixture_clip: Path
) -> None:
    def picture(job: jobs.Job) -> None:
        (job.work_dir / "picture.mp4").write_bytes(b"picture")

    renderer = _Raises(render.RenderError("ffmpeg exited 1: mux: invalid argument"), picture)
    done = _run(_uploaded(tmp_path, fixture_clip), renderer)
    finding = _assert_loud(done, "rendering", plain=renderer.plain_jobs)
    assert finding.beat is None
    assert "render" in finding.cause
    assert "mux: invalid argument" in finding.detail
    page = render_job_page(done)
    assert "picture only, no sound" in page
    assert f'src="/jobs/{done.id}/picture-only.mp4"' in page


@pytest.mark.usefixtures("strict")
def test_strict_a_qa_failure_fails_loudly_and_shows_the_reel_rendered_not_passed(
    tmp_path: Path, fixture_clip: Path
) -> None:
    done = _run(_uploaded(tmp_path, fixture_clip), gate=FakeGate(fail="T3"))
    finding = _assert_loud(done, "qa", plain=[])
    assert "T3" in finding.cause
    page = render_job_page(done)
    assert "rendered, not passed" in page
    assert f'src="/jobs/{done.id}/short.mp4"' in page


@pytest.mark.usefixtures("strict")
def test_strict_a_step_budget_running_out_fails_loudly_naming_the_step(
    tmp_path: Path, fixture_clip: Path
) -> None:
    renderer = _Raises(subproc.Killed("node was stopped: its step ran past its time budget"))
    done = _run(_uploaded(tmp_path, fixture_clip), renderer)
    finding = _assert_loud(done, "rendering", plain=renderer.plain_jobs)
    assert "rendering" in finding.cause



@pytest.mark.usefixtures("strict")
def test_strict_a_render_net_giving_up_naming_no_beat_never_strips_the_overlays(
    tmp_path: Path, fixture_clip: Path
) -> None:
    renderer = _Raises(render.NetExhausted("node exited 1 with no frame", beats=(),
                                           unnamed=True))  # fmt: skip
    done = _run(_uploaded(tmp_path, fixture_clip), renderer)
    finding = _assert_loud(done, "rendering", plain=renderer.plain_jobs)
    assert "no beat was named" in finding.cause


@pytest.mark.usefixtures("strict")
def test_strict_a_render_net_giving_up_on_beats_never_delivers_the_plain_reel(
    tmp_path: Path, fixture_clip: Path
) -> None:
    renderer = _Raises(render.NetExhausted("b01 still failed drawn plain: boom",
                                           beats=("b01",), unnamed=False))  # fmt: skip
    done = _run(_uploaded(tmp_path, fixture_clip), renderer)
    finding = _assert_loud(done, "rendering", plain=renderer.plain_jobs)
    assert "render" in finding.cause

T0 = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
TIGHT = Budgets(
    transcribing_s=600, planning_s=600, sourcing_s=600, qa_s=600,
    render_base_s=60, render_seconds_per_frame=0.0, render_margin=1.0, stall_s=600,
)  # fmt: skip


class _Late(FakeRenderer):
    """Renders fine, but finishes two minutes past the rendering step's budget."""

    def __init__(self, now: list[datetime]) -> None:
        super().__init__()
        self.now = now

    def render(self, job: jobs.Job, *, on_progress: Progress = None,
               library: sound.Library | None = None) -> Path:  # fmt: skip
        out = super().render(job, on_progress=on_progress, library=library)
        self.now[0] += timedelta(seconds=180)
        return out


def _late(tmp_path: Path, clip: Path) -> jobs.Job:
    now = [T0]
    return _run(_uploaded(tmp_path, clip), _Late(now), budgets=TIGHT, clock=lambda: now[0])


@pytest.mark.usefixtures("strict")
def test_strict_a_step_that_finished_after_its_budget_stops_naming_the_step(
    tmp_path: Path, fixture_clip: Path
) -> None:
    done = _late(tmp_path, fixture_clip)
    finding = _assert_loud(done, "rendering", plain=[])
    assert "rendering step ran out of its 1-minute time budget" in finding.cause


@pytest.mark.usefixtures("forgiving")
def test_forgiving_a_step_that_finished_after_its_budget_carries_on(
    tmp_path: Path, fixture_clip: Path
) -> None:
    done = _late(tmp_path, fixture_clip)
    assert done.status == "delivered", done.record.error
    assert [r[4] for r in _log_rows(tmp_path)] == ["repair"]


# --- the other gated sites, strict ----------------------------------------------------------


@pytest.mark.usefixtures("strict")
def test_strict_a_missing_style_fails_loudly(tmp_path: Path, fixture_clip: Path) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    jobs.amend(job, style="retro")
    done = _run(jobs.load(job.path))
    finding = _assert_loud(done, "transcribing", plain=[])
    assert "retro" in finding.cause
    assert done.record.style == "retro"


def _boom(*_a: object, **_k: object) -> object:
    raise RuntimeError("the inventory card is not JSON")


def _planned(tmp_path: Path, clip: Path) -> jobs.Job:
    """A job up to its transcript (asr.json), so `build_plan_request` can run."""
    done = _run(_uploaded(tmp_path, clip))
    assert done.status == "delivered", done.record.error
    return done


@pytest.mark.parametrize("site", ["examples", "music"])
def test_strict_a_plan_request_without_examples_or_pairings_stops(
    tmp_path: Path, fixture_clip: Path, monkeypatch: pytest.MonkeyPatch, site: str
) -> None:
    job = _planned(tmp_path, fixture_clip)
    monkeypatch.setattr(getattr(pipeline, site), "for_job", _boom)
    with pytest.raises(quality.QualityStop) as stop:
        pipeline.build_plan_request(job, SPECS, tmp_path / "inventory")
    assert "not JSON" in stop.value.findings[0].detail


@pytest.mark.parametrize("site", ["examples", "music"])
def test_forgiving_a_plan_request_without_examples_or_pairings_is_noted(
    tmp_path: Path, fixture_clip: Path, monkeypatch: pytest.MonkeyPatch, site: str
) -> None:
    job = _planned(tmp_path, fixture_clip)
    monkeypatch.setenv("QUALITY_MODE", "forgiving")
    job = jobs.amend(job, quality_mode=None)
    monkeypatch.setattr(getattr(pipeline, site), "for_job", _boom)
    notes: list[str] = []
    request = pipeline.build_plan_request(job, SPECS, tmp_path / "inventory", note=notes.append)
    words = "worked examples" if site == "examples" else "music pairings"
    assert any(n.startswith(f"{words}: none (the inventory card is not JSON") for n in notes)
    assert (request.examples if site == "examples" else request.music) == []


@pytest.mark.usefixtures("strict")
def test_strict_a_plan_request_failure_fails_the_job_at_planning(
    tmp_path: Path, fixture_clip: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline.examples, "for_job", _boom)
    done = _run(_uploaded(tmp_path, fixture_clip))
    finding = _assert_loud(done, "planning", plain=[])
    assert "worked examples" in finding.cause


def _hard_check(beat_id: str) -> Callable[..., grammar.PictureCheck | grammar.Violations]:
    calls: list[PicturePlan] = []

    def check(
        plan: PicturePlan, *, keep_soft: bool = True
    ) -> grammar.PictureCheck | grammar.Violations:
        calls.append(plan)
        if len(calls) == 1:
            return grammar.Violations(items=[Violation(
                rule="5.1", beat_id=beat_id, message="names an asset nobody sourced", hard=True,
            )])  # fmt: skip
        return grammar.PictureCheck(picture=plan)

    return check


def _force(job: jobs.Job) -> tuple[str, grammar.PictureCheck | grammar.Violations]:
    plan = PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))
    transcript = Transcript.model_validate_json((job.work_dir / "asr.json").read_text("utf-8"))
    beat = next(b for b in plan.beats
                if b.kind not in ("photo", "finale") and b.id != plan.finale.beat_id)
    result = pipeline._force_hard(  # pyright: ignore[reportPrivateUsage]
        job, plan, _hard_check(beat.id), transcript, [], "planning", datetime.now,
    )  # fmt: skip
    return beat.id, result


@pytest.mark.usefixtures("strict")
def test_strict_a_hard_truth_is_never_forced_onto_a_plain_picture(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _planned(tmp_path, fixture_clip)
    with pytest.raises(quality.QualityStop) as stop:
        _force(job)
    [finding] = stop.value.findings
    assert finding.beat is not None and "nobody sourced" in finding.cause
    assert jobs.load(job.path).record.decisions == []


def test_forgiving_a_hard_truth_is_forced_as_before(
    tmp_path: Path, fixture_clip: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _planned(tmp_path, fixture_clip)
    monkeypatch.setenv("QUALITY_MODE", "forgiving")
    job = jobs.amend(job, quality_mode=None)
    beat_id, result = _force(job)
    assert isinstance(result, grammar.PictureCheck)
    assert beat_id in jobs.load(job.path).record.replaced
    assert [r[4] for r in _log_rows(tmp_path)] == ["repair"]


@pytest.mark.usefixtures("strict")
def test_strict_a_waived_check_is_not_delivered_as_warn(tmp_path: Path) -> None:
    job = jobs.amend(jobs.create(tmp_path), waived_checks=["T3"])
    with pytest.raises(quality.QualityStop) as stop:
        FakeGate(fail="T3").check(job)
    assert "T3" in stop.value.findings[0].cause
    report = technical.load_report(job)
    assert report is not None and report.failed is not None and report.failed.name == "T3"


@pytest.mark.usefixtures("forgiving")
def test_forgiving_a_waived_check_is_delivered_as_warn(tmp_path: Path) -> None:
    job = jobs.amend(jobs.create(tmp_path), waived_checks=["T3"])
    report = FakeGate(fail="T3").check(job)
    assert report.failed is None
    assert any(c.status == "warn" for c in report.checks)


def test_the_plain_reel_choice_is_never_a_strict_option() -> None:
    assert issubclass(quality.QualityStop, Exception)
    assert quality.QualityStop in pipeline.NOT_RESCUED
    assert not pipeline.rescuable("rendering", quality.QualityStop([]))


@pytest.mark.usefixtures("strict")
def test_strict_the_pre_render_gate_stop_heads_the_page_and_lists_every_beat(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """112b: the gate's one stop carries its own headline; the page and job.log list
    every settled beat with what it wanted, used and why."""
    headline = ("stopped before rendering: 2 of 4 picture beats settled for a gradient or a "
                "generated image")  # fmt: skip
    findings = [
        jobs.QualityFinding(beat="b01", kind="photo",
                            cause="settled for the gradient; wanted 'a dam'; why: no hits"),
        jobs.QualityFinding(beat="b03", kind="photo",
                            cause="settled for a generated image (g1); wanted 'a map'; why: x"),
    ]  # fmt: skip
    renderer = _Raises(quality.QualityStop(findings, headline=headline))

    done = _run(_uploaded(tmp_path, fixture_clip), renderer)

    assert done.status == "failed" and done.record.error is not None
    assert headline in done.record.error.message
    assert [f.beat for f in done.record.error.findings] == ["b01", "b03"]
    page = render_job_page(done)
    assert headline in page
    assert "wanted &#x27;a dam&#x27;; why: no hits" in page
    log = done.log_path.read_text(encoding="utf-8")
    assert "strict stop: beat b03 (photo): settled for a generated image" in log
