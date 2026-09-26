"""pipeline: the worker runs a job's steps in order (11.1), one job at a time in
submission order (9.1). Transcribing, planning, sourcing (016), rendering and the
technical gate exist; a job that passes the gate with its deliverables on disk is
`delivered` (10.4). A failing step marks the job `failed` with the step named and a
fixed message; a failed check names itself in the message. Tests source through the
fake web source, render through `FakeRenderer` and gate through `FakeGate`; the real
paths are covered by test_render, test_qa_technical, test_contact_sheet and smoke."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shortsmith import (
    assets,
    fixture,
    jobs,
    pipeline,
    presenter,
    render,
    rights,
    sound,
    styles,
    subproc,
)
from shortsmith.contracts import (
    CRITIC_LINES,
    Candidate,
    CaptionPage,
    Captions,
    CriticReport,
    Cue,
    PicturePlan,
    PlanFeedback,
    PlanRequest,
    RenderSpec,
    SoundStory,
    Transcript,
    ValidatedPlan,
)
from shortsmith.ledger import BudgetExceeded, Caps, Ledger, Prices
from shortsmith.planner import (
    ClaudeCodePlanner,
    FakePlanner,
    Planner,
    PlannerUnavailable,
    UnavailablePlanner,
    prompt,
)
from shortsmith.qa import calibration, technical
from shortsmith.qa import critic as critic_module
from shortsmith.qa.critic import Critic, FakeCritic
from shortsmith.qa.gate import FakeGate, Gate
from shortsmith.render import FakeRenderer, Renderer
from shortsmith.transcriber import FakeTranscriber, Transcriber
from tests.conftest import Media

BRIEF = "Topic: nothing. Angle: prove the pipeline. Must-say: twelve words. Hook wish: none."
# 009: the fake plan is judged by the fixture-shaped rule set (see fixture.smoke_specs).
SPECS = fixture.smoke_specs(styles.load_all(render.registry()))
TRAIL = [
    "created uploaded",
    "uploaded -> transcribing",
    "transcribing -> planning",
    "planning -> sourcing",
    "sourcing -> rendering",
    "rendering -> qa",
    "qa -> delivered",
]


def _uploaded(data_dir: Path, clip: Path) -> jobs.Job:
    job = jobs.create(data_dir, style="explainer", style_note="explainer, energetic")
    shutil.copyfile(clip, job.input_dir / "raw.mp4")
    (job.input_dir / "brief.md").write_text(BRIEF, encoding="utf-8")
    (job.input_dir / "refs.json").write_text("[]", encoding="utf-8")
    return job


def _sourcing() -> assets.Sourcing:
    """016: the fake web source, the only configured source (so no adapter note)."""
    return assets.Sourcing(sources={"web": assets.FakeImageSource("web")}, order=("web",))


def _run(job: jobs.Job, *, transcriber: Transcriber | None = None,
         planner: Planner | None = None, renderer: Renderer | None = None,
         gate: Gate | None = None,
         sourcing: assets.Sourcing | None = None,
         detector: presenter.FaceDetector | None = None,
         critic: Critic | None = None) -> jobs.Job:  # fmt: skip
    # 013: the fake detector, so the suite never waits on the cascade; the real one is
    # exercised below on the fixture and its faceless twin, and by the smoke.
    return pipeline.run_job(
        job,
        transcriber=transcriber or FakeTranscriber(),
        planner=planner or FakePlanner(),
        renderer=renderer or FakeRenderer(),
        gate=gate or FakeGate(),
        sourcing=sourcing or _sourcing(),
        specs=SPECS,
        detector=detector or presenter.FakeFaceDetector(),
        critic=critic or FakeCritic(),  # 033: the fake scores every delivered job
    )


def _worker(transcriber: Transcriber | None = None, **kwargs: object) -> pipeline.Worker:
    return pipeline.Worker(
        transcriber=transcriber or FakeTranscriber(), planner=FakePlanner(),
        renderer=FakeRenderer(), gate=FakeGate(), sourcing=_sourcing(), specs=SPECS,
        detector=presenter.FakeFaceDetector(),
        **kwargs,  # pyright: ignore[reportArgumentType]
    )  # fmt: skip


def _pages(job: jobs.Job) -> list[CaptionPage]:
    return Captions.model_validate_json(
        (job.work_dir / "captions.json").read_text(encoding="utf-8")
    ).pages


def test_run_job_transcribes_plans_renders_gates_and_delivers(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job)
    assert done.status == "delivered"
    assert (job.out_dir / "qa.json").is_file()
    assert (job.out_dir / "contact.jpg").is_file()
    asr = Transcript.model_validate_json((job.work_dir / "asr.json").read_text(encoding="utf-8"))
    assert len(asr.words) == 12
    # 033: the critic's note sits inside the `qa` step; the status trail is the rest.
    assert _trail(job) == TRAIL
    log = [line.split(" ", 1)[1] for line in job.log_path.read_text("utf-8").splitlines()]
    assert len(log) == len(TRAIL) + 1 and log[-2].startswith("critic: overall ")


class _Watching(FakeRenderer):
    """Reads job.json while progress is reported, the way the job page's poll does."""

    def __init__(self) -> None:
        super().__init__()
        self.on_disk: list[int | None] = []

    def render(
        self, job: jobs.Job, *, on_progress: Callable[[int], None] | None = None,
        library: sound.Library | None = None,
    ) -> Path:  # fmt: skip
        def spy(pct: int) -> None:
            if on_progress is not None:
                on_progress(pct)
            self.on_disk.append(jobs.load(job.path).record.progress)

        return super().render(job, on_progress=spy, library=library)


def test_rendering_step_reports_progress_into_job_json(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    renderer = _Watching()
    done = _run(job, renderer=renderer)
    assert done.status == "delivered"
    assert renderer.jobs == [job.path]
    assert renderer.on_disk == [0, 50, 100]  # each report landed in job.json before the next
    assert jobs.load(job.path).record.status == "delivered"
    assert (job.work_dir / "picture.mp4").is_file()
    # 005: the fake stands in for the whole step, so every file the step leaves exists.
    assert (job.work_dir / "cut.mp4").is_file()
    assert (job.work_dir / "stems" / "voice.wav").is_file()
    assert (job.work_dir / "stems" / "mix.wav").is_file()
    assert (job.out_dir / "short.mp4").is_file()


class _BrokenRenderer(FakeRenderer):
    def render(
        self, job: jobs.Job, *, on_progress: Callable[[int], None] | None = None,
        library: sound.Library | None = None,
    ) -> Path:  # fmt: skip
        raise render.RenderError("remotion driver exited 1:\nno frame found")


def test_a_failing_render_fails_the_job_at_rendering(tmp_path: Path, fixture_clip: Path) -> None:
    done = _run(_uploaded(tmp_path, fixture_clip), renderer=_BrokenRenderer())
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "rendering"
    assert done.record.error.message == pipeline.ERROR_TEXT["rendering"]
    assert "no frame found" in done.record.error.detail


def test_sourcing_writes_the_manifest_rights_and_credits(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job)
    assert done.status == "delivered"
    manifest = assets.load_manifest(job.path)
    assert manifest is not None
    plan = PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))
    sourced = [
        b.id for b in plan.beats
        if b.subject_kind is not None and b.kind not in assets.NOT_SOURCED  # 020: no map picture
    ]  # fmt: skip
    assert [b.beat_id for b in manifest.beats] == sourced
    rows = rights.load(job.path)
    assert rows is not None and [r.id for r in rows] == [a.id for a in manifest.assets]
    assert (job.out_dir / "credits.md").is_file()
    assert rights.completeness(rows, manifest, plan) == []


def test_sources_without_an_adapter_are_noted_in_the_job_log(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    sourcing = assets.Sourcing(sources={"web": assets.FakeImageSource("web")},
                               order=("web", "commons", "pexels"))  # fmt: skip
    _run(job, sourcing=sourcing)
    log = job.log_path.read_text("utf-8")
    assert "no image source for: commons, pexels; those rungs are skipped" in log


def test_rights_safe_policy_reaches_the_step(tmp_path: Path, fixture_clip: Path) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    web = assets.FakeImageSource("web")
    commons = assets.FakeImageSource("commons")
    sourcing = assets.Sourcing(sources={"web": web, "commons": commons},
                               order=("web", "commons"), policy="rights_safe")  # fmt: skip
    assert _run(job, sourcing=sourcing).status == "delivered"
    assert web.searches == 0 and commons.searches > 0


def test_a_missing_reference_file_fails_the_job_at_sourcing(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    ref = {"id": "r1", "file": "refs/1_gone.png", "kind": "image",
           "caption": "slow colour gradient sky", "original_name": "gone.png",
           "width": 1080, "height": 1920, "size_bytes": 1}  # fmt: skip
    (job.input_dir / "refs.json").write_text(json.dumps([ref]), encoding="utf-8")
    done = _run(job)
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "sourcing"
    assert done.record.error.message == pipeline.ERROR_TEXT["sourcing"]
    assert "refs/1_gone.png is missing" in done.record.error.detail


class _RightslessGate(FakeGate):
    def contact_sheet(self, job: jobs.Job) -> Path:
        (job.out_dir / "rights.json").unlink()
        return super().contact_sheet(job)


def test_delivered_requires_rights_and_credits(tmp_path: Path, fixture_clip: Path) -> None:
    assert pipeline.DELIVERABLES == ("short.mp4", "contact.jpg", "rights.json", "credits.md")
    done = _run(_uploaded(tmp_path, fixture_clip), gate=_RightslessGate())
    assert done.status == "failed"
    assert done.record.error is not None
    assert "rights.json" in done.record.error.detail


def test_a_failed_check_fails_the_job_at_qa_and_names_the_check(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job, gate=FakeGate(fail="T2"))
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "qa"
    assert done.record.error.message == "The short failed a technical check (T2)."
    assert (job.out_dir / "qa.json").is_file()  # the report is written either way (10.1)
    assert not (job.out_dir / "contact.jpg").exists()  # no sheet from a failed short
    log = [line.split(" ", 1)[1] for line in job.log_path.read_text("utf-8").splitlines()]
    assert log[-1].startswith("qa -> failed step=qa")


class _SheetlessGate(FakeGate):
    def contact_sheet(self, job: jobs.Job) -> Path:
        return job.out_dir / "contact.jpg"  # never written


def test_missing_deliverables_fail_the_job_at_qa(tmp_path: Path, fixture_clip: Path) -> None:
    done = _run(_uploaded(tmp_path, fixture_clip), gate=_SheetlessGate())
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "qa"
    assert "contact.jpg" in done.record.error.detail


def test_the_worker_gates_through_the_technical_gate_by_default() -> None:
    from shortsmith.qa.gate import TechnicalGate

    worker = pipeline.Worker(transcriber=FakeTranscriber(), planner=FakePlanner())
    assert isinstance(worker._gate, TechnicalGate)  # pyright: ignore[reportPrivateUsage]


# --- the critic (10.2; ticket 033) --------------------------------------------------------


def test_the_qa_step_runs_the_critic_after_the_gate_and_the_job_is_delivered(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """10.2: the critic scores every delivered job; its report sits in `out/qa.json`
    beside T1-T13, advisory, and its line is in `job.log` inside the `qa` step."""
    job = _uploaded(tmp_path, fixture_clip)
    fake = FakeCritic()
    done = _run(job, critic=fake)
    assert done.status == "delivered"
    report = technical.load_report(job)
    assert report is not None and report.passed and report.critic is not None
    assert report.critic.status == "scored" and report.critic.advisory is True
    assert [line.name for line in report.critic.lines] == [n for n, _ in CRITIC_LINES]
    assert report.critic.category == "science"
    assert fake.calls == 1
    (shown,) = fake.inputs
    assert shown.contact_sheet is not None and shown.pip_strip is not None
    assert "11 beats" in shown.plan_summary
    noted = [line.split(" ", 1)[1] for line in job.log_path.read_text("utf-8").splitlines()]
    (critic_line,) = [line for line in noted if line.startswith("critic: ")]
    assert noted.index("rendering -> qa") < noted.index(critic_line) < noted.index(
        "qa -> delivered"
    )


def test_the_sheet_is_composed_again_once_the_critic_has_scored(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """035 / 10.4: the critic scores the sheet without its own scores on it, then the
    gate composes it once more so the summary panel carries E1-E10 and the notes."""

    class _Recording(FakeGate):
        def __init__(self) -> None:
            super().__init__()
            self.seen: list[bool] = []

        def contact_sheet(self, job: jobs.Job) -> Path:
            report = technical.load_report(job)
            self.seen.append(report is not None and report.critic is not None)
            return super().contact_sheet(job)

    gate = _Recording()
    done = _run(_uploaded(tmp_path, fixture_clip), gate=gate)
    assert done.status == "delivered"
    assert gate.seen == [False, True]


class _UnreachableCritic(FakeCritic):
    def score(self, inputs: critic_module.Inputs) -> CriticReport:
        raise critic_module.CriticError("the critic could not be reached: boom")


def test_a_critic_failure_never_blocks_delivery_while_advisory(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job, critic=_UnreachableCritic())
    assert done.status == "delivered"
    report = technical.load_report(job)
    assert report is not None and report.critic is not None
    assert report.critic.status == "unavailable"
    assert report.critic.notes[0] == "the critic could not be reached: boom"


def _blocking(data_dir: Path) -> None:
    """A calibration file whose last five rated jobs all matched (10.2)."""
    calibration.save(
        data_dir,
        calibration.Calibration(
            entries=[
                calibration.Entry(
                    job_id=f"20260926-09000{i}-abcdef", critic_overall=8, critic_pass=True,
                    rating=7, phone_pass=True, matched=True, at=datetime(2026, 9, 26, tzinfo=UTC),
                )  # fmt: skip
                for i in range(5)
            ]
        ),
    )


@pytest.mark.parametrize(("overall", "expected"), [(7, "passed"), (6, "rejected")])
def test_a_blocking_critic_settles_an_unrated_job_at_delivery(
    tmp_path: Path, fixture_clip: Path, overall: int, expected: str
) -> None:
    """10.4 / 034: once blocking, `passed` needs critic >= 7 and `rejected` is the
    critic under it; the job went through `delivered` first and keeps its files."""
    _blocking(tmp_path)
    done = _run(_uploaded(tmp_path, fixture_clip), critic=FakeCritic(overall=overall))
    assert done.status == expected
    report = technical.load_report(done)
    assert report is not None and report.critic is not None and report.critic.advisory is False
    assert (done.out_dir / "short.mp4").is_file()
    trail = [line.split(" ", 1)[1] for line in done.log_path.read_text("utf-8").splitlines()]
    assert "qa -> delivered" in trail
    assert trail[-1] == f"delivered -> {expected} by critic {overall}/10 blocking"


def test_an_unavailable_critic_leaves_a_job_delivered_even_while_blocking(
    tmp_path: Path, fixture_clip: Path
) -> None:
    _blocking(tmp_path)
    done = _run(_uploaded(tmp_path, fixture_clip), critic=_UnreachableCritic())
    assert done.status == "delivered"


def test_while_advisory_the_critic_settles_nothing(tmp_path: Path, fixture_clip: Path) -> None:
    done = _run(_uploaded(tmp_path, fixture_clip), critic=FakeCritic(overall=2))
    assert done.status == "delivered"


class _OverBudgetCritic(FakeCritic):
    def score(self, inputs: critic_module.Inputs) -> CriticReport:
        raise BudgetExceeded("qa", spent_inr=70.0, estimated_inr=20.0, hard_inr=80.0)


def test_the_critics_hard_cap_fails_the_job_at_qa_like_any_refused_paid_call(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """11.3: the hard cap is not an API failure; the job fails visibly at `qa`."""
    done = _run(_uploaded(tmp_path, fixture_clip), critic=_OverBudgetCritic())
    assert done.status == "failed"
    assert done.record.error is not None and done.record.error.step == "qa"
    assert done.record.error.message == "Budget exceeded at step qa."


def test_a_failed_check_never_reaches_the_critic(tmp_path: Path, fixture_clip: Path) -> None:
    fake = FakeCritic()
    done = _run(_uploaded(tmp_path, fixture_clip), gate=FakeGate(fail="T2"), critic=fake)
    assert done.status == "failed" and fake.calls == 0


def test_the_worker_scores_through_the_fake_critic_unless_told_otherwise() -> None:
    worker = pipeline.Worker(transcriber=FakeTranscriber(), planner=FakePlanner())
    assert isinstance(worker._critic, FakeCritic)  # pyright: ignore[reportPrivateUsage]


def test_the_worker_renders_through_remotion_by_default() -> None:
    worker = pipeline.Worker(transcriber=FakeTranscriber(), planner=FakePlanner())
    assert isinstance(worker._renderer, render.RemotionRenderer)  # pyright: ignore[reportPrivateUsage]


def test_planning_writes_plan_sound_and_captions(tmp_path: Path, fixture_clip: Path) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    _run(job)
    plan = PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))
    story = SoundStory.model_validate_json((job.work_dir / "sound.json").read_text("utf-8"))
    assert plan.beats[-1].end == 6.0 and story.cues
    pages = _pages(job)
    # 010: every tone burst is its own page (0.7 s silences break); the finale beat
    # (5.0 s on) hides the last burst, and the last page ends where the finale starts.
    assert [p.word_indices for p in pages] == [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9]]
    assert pages[-1].end == 5.0
    assert all(p.lines == 1 and len(p.words) == 2 for p in pages)


class _Recording(FakePlanner):
    def __init__(self) -> None:
        self.requests: list[PlanRequest] = []

    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        self.requests.append(request)
        return super().plan_picture(request, feedback=feedback)


def test_plan_request_is_built_from_the_job_files(
    tmp_path: Path, fixture_clip: Path, media: Media
) -> None:
    """2.3: brief verbatim, the loaded style spec (numbers + prose, 1.2), the style
    line as the note, the fixed transcript, references as captioned lines, constraints,
    asset policy."""
    job = _uploaded(tmp_path, fixture_clip)
    ref = media.image(width=1200, height=1600)
    (job.input_dir / "refs").mkdir()
    shutil.copyfile(ref, job.input_dir / "refs" / "1_product.png")
    (job.input_dir / "refs.json").write_text(json.dumps([{
        "id": "ref1", "file": "refs/1_product.png", "kind": "image", "caption": "my product",
        "original_name": "product.png", "width": 1200, "height": 1600, "size_bytes": 10,
        "rights": "owner_supplied",
    }]), encoding="utf-8")  # fmt: skip
    planner = _Recording()
    _run(job, planner=planner)
    (req,) = planner.requests
    assert req.brief == BRIEF
    assert req.style.name == "explainer" and req.style.status == "shipped"
    assert "## Beat grammar" in req.style.prose and "7.1" in req.style.prose
    numbers = req.style.numbers
    # The beat minimum is the fixture rule set's (009); the untouched numbers are explainer's.
    assert numbers["beats"]["min_s"] == fixture.SMOKE_BEATS["min_s"]  # type: ignore[index]
    assert numbers["presenter"]["pip_max_run"] == 6  # type: ignore[index]
    assert numbers["sound"]["forbidden"] == ["sweep", "riser", "rumble_crescendo", "whoosh"]  # type: ignore[index]
    assert req.style_note == "explainer, energetic"
    assert len(req.transcript.words) == 12
    assert [(r.id, r.kind, r.caption, r.width) for r in req.references] == [
        ("ref1", "image", "my product", 1200)
    ]
    assert req.constraints.max_duration_s == 60.0
    assert req.constraints.target_duration_s == 6.0
    assert req.asset_policy in ("any", "rights_safe")


def test_a_job_whose_style_is_unknown_fails_at_planning_naming_it(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    record = job.record.model_copy(update={"style": "retro"})
    job.json_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    done = _run(jobs.load(job.path))
    assert done.status == "failed"
    assert done.record.error is not None and done.record.error.step == "planning"
    assert "retro" in done.record.error.detail


def test_the_pager_reads_words_per_page_from_the_style(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """6.1: `captions.words_per_page` / `prefer` / `gap_break_s` come from front matter,
    not code (a 0.8 s gap break lets the fixture's 0.7 s silences join pages)."""
    job = _uploaded(tmp_path, fixture_clip)
    wide = SPECS["explainer"].model_copy(deep=True)
    wide.captions.words_per_page = (2, 6)
    wide.captions.prefer = 6
    wide.captions.gap_break_s = 0.8
    pipeline.run_job(
        job, transcriber=FakeTranscriber(), planner=FakePlanner(), renderer=FakeRenderer(),
        gate=FakeGate(), specs={"explainer": wide}, detector=presenter.FakeFaceDetector(),
    )  # fmt: skip
    assert [len(p.word_indices) for p in _pages(job)] == [6, 4]  # the finale hides two


# --- ticket 009: the grammar in the planning step (decision 8.2) ----------------------


def test_planning_validates_the_plan_and_writes_the_validated_files(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """plan.raw.json keeps the planner's output, plan.json / sound.json are the snapped
    and clamped plans the renderer reads, plan.validated.json carries the clamps."""
    job = _uploaded(tmp_path, fixture_clip)
    assert _run(job).status == "delivered"
    work = job.work_dir
    raw = PicturePlan.model_validate_json((work / "plan.raw.json").read_text("utf-8"))
    plan = PicturePlan.model_validate_json((work / "plan.json").read_text("utf-8"))
    validated = ValidatedPlan.model_validate_json((work / "plan.validated.json").read_text("utf-8"))
    assert raw.keywords == [5, 10, 1, 7]  # the fake asks for four
    assert plan.keywords == [5, 10, 1]  # 6.1: 12 words x 0.25 = 3
    assert validated.picture == plan
    assert [c.rule for c in validated.clamps] == ["6.1"]
    assert validated.warnings == []
    story = SoundStory.model_validate_json((work / "sound.json").read_text("utf-8"))
    assert validated.sound == story
    pages = _pages(job)
    # 7 was trimmed; 10 ("ffmpeg") is in the finale, where captions are hidden (010).
    assert [p.keyword for p in pages] == [1, None, 5, None, None]


class _RetryPlanner(FakePlanner):
    """Rejected `bad_picture` / `bad_sound` times, then the canned plan; records what
    it was re-sent with."""

    def __init__(self, *, bad_picture: int = 0, bad_sound: int = 0) -> None:
        self.bad_picture = bad_picture
        self.bad_sound = bad_sound
        self.picture_feedback: list[PlanFeedback | None] = []
        self.sound_feedback: list[PlanFeedback | None] = []

    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        self.picture_feedback.append(feedback)
        plan = super().plan_picture(request)
        if len(self.picture_feedback) <= self.bad_picture:
            b03 = plan.beats[2].model_copy(update={"motion": None, "enter": "wipe"})
            return plan.model_copy(update={"beats": [*plan.beats[:2], b03, *plan.beats[3:]]})
        return plan

    def plan_sound(
        self,
        request: PlanRequest,
        picture: PicturePlan,
        catalogue_tags: Sequence[str] = (),
        *,
        feedback: PlanFeedback | None = None,
    ) -> SoundStory:
        self.sound_feedback.append(feedback)
        story = super().plan_sound(request, picture)
        if len(self.sound_feedback) <= self.bad_sound:
            ghost = Cue(beat_id="b99", intent="hit", at="start")
            return story.model_copy(update={"cues": [*story.cues, ghost]})
        return story


GHOST_CUE = "b99 (8.2): cue 'hit' names a beat that is not in the plan"


def test_a_rejected_picture_plan_is_resent_once_with_the_violations(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    planner = _RetryPlanner(bad_picture=1)
    assert _run(job, planner=planner).status == "delivered"
    first, second = planner.picture_feedback
    assert first is None and second is not None
    assert PicturePlan.model_validate_json(second.previous).beats[2].motion is None
    assert second.violations == [
        "b03 (4.1): non-presenter beat (photo) has no motion; "
        "every non-presenter beat has exactly one",
        "b03 (9.4): enter 'wipe' is not in broll.enter_transitions "
        "['cut', 'fade', 'whip', 'zoom', 'spring']",
    ]
    assert planner.sound_feedback == [None]
    plan = PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))
    assert plan.beats[2].motion == "ken_burns_in"
    log = job.log_path.read_text("utf-8")
    assert "picture plan rejected" in log and "b03 (4.1)" in log


def test_a_rejected_sound_story_is_resent_once(tmp_path: Path, fixture_clip: Path) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    planner = _RetryPlanner(bad_sound=1)
    assert _run(job, planner=planner).status == "delivered"
    assert planner.picture_feedback == [None]
    first, second = planner.sound_feedback
    assert first is None and second is not None
    assert second.violations == [GHOST_CUE]
    story = SoundStory.model_validate_json((job.work_dir / "sound.json").read_text("utf-8"))
    assert all(c.beat_id != "b99" for c in story.cues)


@pytest.mark.parametrize("call", ["picture", "sound"])
def test_a_plan_rejected_twice_fails_the_job_at_planning_with_the_list(
    tmp_path: Path, fixture_clip: Path, call: str
) -> None:
    """8.2: exactly one retry; the second rejection fails the job with the violation
    list in job.json (and on the page), and nothing is rendered."""
    job = _uploaded(tmp_path, fixture_clip)
    bad = {"picture": (9, 0), "sound": (0, 9)}[call]
    planner = _RetryPlanner(bad_picture=bad[0], bad_sound=bad[1])
    done = _run(job, planner=planner)
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "planning"
    assert done.record.error.message == pipeline.ERROR_TEXT["planning"]
    if call == "picture":
        assert len(planner.picture_feedback) == 2 and planner.sound_feedback == []
        assert done.record.error.violations[0].startswith("b03 (4.1)")
    else:
        assert len(planner.picture_feedback) == 1 and len(planner.sound_feedback) == 2
        assert done.record.error.violations == [GHOST_CUE]
    assert all(line in done.record.error.detail for line in done.record.error.violations)
    assert f"{call} plan was rejected twice" in done.record.error.detail
    assert not (job.work_dir / "plan.json").exists()
    assert not (job.work_dir / "plan.validated.json").exists()
    assert (job.work_dir / "plan.raw.json").is_file()  # the rejected output stays on disk
    assert jobs.load(job.path).record.error == done.record.error


# --- ticket 014: the CLI adapter through the planning step (decisions 8.1-8.3) -------


CLI_REPLIES = Path(__file__).parent / "fixtures" / "claude_cli"
EQUIVALENT = Prices({"api_equivalent": {"input_tokens": 0.25, "output_tokens": 1.25}})


class _Cli:
    """Stubbed `claude` CLI: answers each call with the next queued envelope."""

    def __init__(self, *names: str, first_reply: str | None = None) -> None:
        self.replies = [(CLI_REPLIES / f"{n}.json").read_bytes() for n in names]
        if first_reply is not None:
            envelope = json.loads(self.replies[0])
            envelope["result"] = first_reply
            self.replies[0] = json.dumps(envelope).encode()
        self.stdins: list[str] = []

    def __call__(
        self, argv: list[str], stdin: str, cwd: Path, env: Mapping[str, str]
    ) -> subprocess.CompletedProcess[bytes]:
        self.stdins.append(stdin)
        return subprocess.CompletedProcess(argv, 0, self.replies.pop(0), b"")


def _cli_planner(cli: _Cli) -> ClaudeCodePlanner:
    book = Ledger(EQUIVALENT, Caps(per_job=None, hard=None, per_day=500))
    return ClaudeCodePlanner(lambda: book, run=cli)


def test_the_cli_planner_plans_a_job_picture_then_sound_with_a_row_per_call(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """8.1 / 8.3: the pipeline binds the adapter to the job; the sound call carries the
    snapped picture plan and the catalogue tags (none until 022); the prompt version
    lands on the plans and in job.json."""
    job = _uploaded(tmp_path, fixture_clip)
    cli = _Cli("picture", "sound")
    done = _run(job, planner=_cli_planner(cli))
    assert done.status == "delivered", done.record.error
    picture_prompt, sound_prompt = cli.stdins
    assert "## JSON schema (PicturePlan)" in picture_prompt
    snapped = PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))
    assert snapped.model_dump_json(indent=2) in sound_prompt
    assert "(no catalogue yet" in sound_prompt
    assert (job.work_dir / "planner" / "request_picture.md").is_file()
    assert (job.work_dir / "planner" / "request_sound.md").is_file()
    record = jobs.load(job.path).record
    assert [(r.step, r.provider, r.inr) for r in record.cost] == [
        ("planning", "claude_code", 0.0),
        ("planning", "claude_code", 0.0),
    ]
    assert record.prompt_version == prompt.PROMPT_VERSION
    assert snapped.prompt_version == prompt.PROMPT_VERSION


def test_a_reply_that_fails_the_models_is_retried_once_like_a_grammar_rejection(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """8.2: a Pydantic failure takes the same single retry, with the reply as the
    previous output; the retry is its own ledger row."""
    job = _uploaded(tmp_path, fixture_clip)
    cli = _Cli("picture", "picture", "sound", first_reply='{"beats": "soon"}')
    assert _run(job, planner=_cli_planner(cli)).status == "delivered"
    retry = cli.stdins[1]
    assert "## Your previous reply was rejected" in retry
    assert '{"beats": "soon"}' in retry
    assert "- plan (8.2): beats: Input should be a valid list" in retry
    assert len(jobs.load(job.path).record.cost) == 3
    assert "picture plan rejected" in job.log_path.read_text("utf-8")


def test_a_reply_that_fails_the_models_twice_fails_the_job_with_the_errors(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    cli = _Cli("picture", "picture", first_reply="no plan today")
    cli.replies[1] = cli.replies[0]
    done = _run(job, planner=_cli_planner(cli))
    assert done.status == "failed"
    assert done.record.error is not None and done.record.error.step == "planning"
    assert done.record.error.violations == ["plan (8.2): the reply holds no JSON object"]
    assert len(done.record.cost) == 2
    assert not (job.work_dir / "plan.json").exists()


def test_the_fake_plans_prompt_version_is_recorded_in_job_json(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    assert _run(job).record.prompt_version == FakePlanner.PROMPT_VERSION


def test_unavailable_planner_fails_the_job_at_planning_naming_the_ticket(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job, planner=UnavailablePlanner("claude_code", "014"))
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "planning"
    assert done.record.error.message == pipeline.ERROR_TEXT["planning"]
    assert "014" in done.record.error.detail
    assert PlannerUnavailable.__name__ in done.record.error.detail
    assert (job.work_dir / "asr.json").is_file()
    assert not (job.work_dir / "plan.json").exists()


# --- 013: the face is measured at `transcribing`, before the transcriber (3.3) ----------


def test_transcribing_measures_the_face_onto_job_json_and_the_render_reads_it(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    detector = presenter.FakeFaceDetector()
    done = _run(job, detector=detector)
    assert done.status == "delivered"
    assert len(detector.seen) == 8
    measured = done.record.presenter
    assert measured is not None
    assert measured.face == detector.box and all(f == detector.box for f in measured.faces)
    assert measured.pip == presenter.pip_geometry(detector.box, (1080, 1920), SPECS["explainer"])
    stills = sorted(p.name for p in (job.work_dir / "frames").glob("strip_*.jpg"))
    assert stills == [f"strip_{n}.jpg" for n in range(1, 9)]
    spec = RenderSpec.model_validate_json(
        (job.work_dir / "render_spec.json").read_text(encoding="utf-8")
    )
    assert spec.pip == measured.pip  # the composition crops through the measured window


def test_cards_and_the_split_clear_the_large_face_circle_the_job_measured(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """051: the fake detector's box is 520 px tall, over 45 % of the cut (3.3), so the
    job draws the 340 px circle with its top at 920; every card and split beat in the
    RenderSpec ends `PIP_GAP_PX` above that top, never against the style's fixed 960."""
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job, detector=presenter.FakeFaceDetector())
    assert done.status == "delivered"
    spec = RenderSpec.model_validate_json(
        (job.work_dir / "render_spec.json").read_text(encoding="utf-8")
    )
    assert (spec.pip.diameter, spec.pip.top) == (340, 920)
    limit = spec.pip.top - render.PIP_GAP_PX
    cards = [b.visual for b in spec.beats if b.visual is not None and b.visual.card is not None]
    splits = [b.split for b in spec.beats if b.split is not None]
    assert cards and splits
    assert all(render.card_bottom(v) <= limit + 1e-6 for v in cards)
    assert all(render.split_bottom(s) <= limit + 1e-6 for s in splits)


def test_a_recording_with_no_face_fails_at_transcribing_before_the_transcriber(
    tmp_path: Path, faceless_clip: Path
) -> None:
    """The real cascade on the fixture with its ellipse left out: the job fails with the
    3.3 sentence, at `transcribing`, and nothing was transcribed."""
    job = _uploaded(tmp_path, faceless_clip)
    transcriber = _Binding()
    done = _run(job, transcriber=transcriber, detector=presenter.HaarDetector())
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "transcribing"
    assert done.record.error.message == presenter.NO_FACE_TEXT
    assert done.record.error.message != pipeline.ERROR_TEXT["transcribing"]
    assert "NoFace" in done.record.error.detail
    assert transcriber.heard == [] and not (job.work_dir / "asr.json").exists()
    assert done.record.presenter is None


def test_five_of_eight_stills_with_a_face_is_the_same_early_failure(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job, detector=presenter.FakeFaceDetector(found=5))
    assert done.status == "failed"
    assert done.record.error is not None and done.record.error.step == "transcribing"
    assert done.record.error.message == presenter.NO_FACE_TEXT


class _Broken(Transcriber):
    def transcribe(self, audio: Path) -> Transcript:
        raise RuntimeError("groq said no")


def test_step_exception_marks_the_job_failed_at_that_step(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job, transcriber=_Broken())
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "transcribing"
    assert done.record.error.message == pipeline.ERROR_TEXT["transcribing"]
    assert "groq said no" in done.record.error.detail
    assert jobs.load(job.path).status == "failed"


class _Binding(FakeTranscriber):
    """Records the job it was bound to and the audio path it was handed."""

    def __init__(self) -> None:
        self.bound: list[str] = []
        self.heard: list[Path] = []

    def bind(self, job: jobs.Job) -> _Binding:
        self.bound.append(job.id)
        return self

    def transcribe(self, audio: Path) -> Transcript:
        self.heard.append(audio)
        return super().transcribe(audio)


def test_the_transcriber_is_bound_to_the_job_before_it_transcribes(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """012: a real transcriber writes under `work/asr/` and records ledger rows, so it
    gets the job first, as the planner does (014)."""
    job = _uploaded(tmp_path, fixture_clip)
    transcriber = _Binding()
    done = _run(job, transcriber=transcriber)
    assert done.status == "delivered"
    assert transcriber.bound == [job.id]
    assert transcriber.heard == [job.input_dir / "raw.mp4"]


def test_run_job_refuses_a_job_that_is_not_uploaded(tmp_path: Path, fixture_clip: Path) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    job = jobs.transition(job, "transcribing")
    with pytest.raises(pipeline.NotRunnable):
        _run(job)


def test_worker_runs_submissions_in_order_one_at_a_time(
    tmp_path: Path, fixture_clip: Path
) -> None:
    first = _uploaded(tmp_path, fixture_clip)
    second = _uploaded(tmp_path, fixture_clip)
    worker = _worker()
    worker.submit(first.path)
    worker.submit(second.path)
    assert worker.pending() == [first.path, second.path]

    assert worker.run_next() is True
    assert jobs.load(first.path).status == "delivered"
    assert jobs.load(second.path).status == "uploaded"
    assert worker.pending() == [second.path]

    assert worker.run_next() is True
    assert jobs.load(second.path).status == "delivered"
    assert worker.run_next() is False


class _Blocking(Transcriber):
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def transcribe(self, audio: Path) -> Transcript:
        self.started.set()
        assert self.release.wait(timeout=10)
        return FakeTranscriber().transcribe(audio)


def test_worker_thread_keeps_the_second_job_uploaded_while_the_first_runs(
    tmp_path: Path, fixture_clip: Path
) -> None:
    transcriber = _Blocking()
    worker = _worker(transcriber=transcriber)
    first = _uploaded(tmp_path, fixture_clip)
    second = _uploaded(tmp_path, fixture_clip)
    worker.start()
    try:
        worker.submit(first.path)
        worker.submit(second.path)
        assert transcriber.started.wait(timeout=10)
        assert jobs.load(first.path).status == "transcribing"
        assert jobs.load(second.path).status == "uploaded"
        transcriber.release.set()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and jobs.load(second.path).status != "delivered":
            time.sleep(0.05)
        assert jobs.load(first.path).status == "delivered"
        assert jobs.load(second.path).status == "delivered"
    finally:
        transcriber.release.set()
        worker.stop()


def test_worker_survives_a_failing_job(tmp_path: Path, fixture_clip: Path) -> None:
    worker = _worker(transcriber=_Broken())
    job = _uploaded(tmp_path, fixture_clip)
    worker.submit(job.path)
    assert worker.run_next() is True
    assert jobs.load(job.path).status == "failed"


def test_worker_skips_a_job_that_vanished(tmp_path: Path) -> None:
    worker = _worker()
    worker.submit(tmp_path / "jobs" / "20260920-090000-abcdef")
    assert worker.run_next() is True
    assert worker.pending() == []


# --- ticket 041: queue depth, positions, job-minute kill (decisions 9.1, 11.2) -----


def test_fourth_submission_is_refused_at_max_queue_three(
    tmp_path: Path, fixture_clip: Path
) -> None:
    worker = _worker(max_queue=3)
    submitted = [_uploaded(tmp_path, fixture_clip) for _ in range(4)]
    for job in submitted[:3]:
        worker.submit(job.path)
    with pytest.raises(pipeline.QueueFull):
        worker.submit(submitted[3].path)
    assert worker.pending() == [j.path for j in submitted[:3]]
    assert worker.run_next() is True
    worker.submit(submitted[3].path)  # a slot is free again
    assert worker.pending() == [j.path for j in submitted[1:]]


def test_a_reservation_counts_toward_the_depth_until_released(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """The upload route reserves before it reads the body so a refused upload costs
    nothing; a rejected upload releases, an accepted one hands the slot to submit."""
    worker = _worker(max_queue=2)
    worker.reserve()
    worker.reserve()
    with pytest.raises(pipeline.QueueFull):
        worker.reserve()
    job, other = _uploaded(tmp_path, fixture_clip), _uploaded(tmp_path, fixture_clip)
    worker.submit(job.path, reserved=True)  # one reservation became a waiting job
    assert worker.depth() == 2
    with pytest.raises(pipeline.QueueFull):
        worker.submit(other.path)
    worker.release()  # the other upload was rejected
    worker.submit(other.path)
    assert worker.pending() == [job.path, other.path]
    assert worker.depth() == 2


def test_waiting_jobs_know_their_position_and_it_moves_as_jobs_finish(
    tmp_path: Path, fixture_clip: Path
) -> None:
    worker = _worker()
    first, second, third = (_uploaded(tmp_path, fixture_clip) for _ in range(3))
    for job in (first, second, third):
        worker.submit(job.path)
    assert [worker.position(j.path) for j in (first, second, third)] == [1, 2, 3]
    assert worker.run_next() is True
    assert worker.position(first.path) is None
    assert [worker.position(j.path) for j in (second, third)] == [1, 2]
    assert worker.run_next() is True
    assert worker.position(third.path) == 1


def test_the_running_job_has_no_position_but_still_counts_toward_the_depth(
    tmp_path: Path, fixture_clip: Path
) -> None:
    transcriber = _Blocking()
    worker = _worker(transcriber=transcriber, max_queue=3)
    first, second, third, fourth = (_uploaded(tmp_path, fixture_clip) for _ in range(4))
    worker.start()
    try:
        worker.submit(first.path)
        assert transcriber.started.wait(timeout=10)
        worker.submit(second.path)
        worker.submit(third.path)
        assert worker.position(first.path) is None
        assert [worker.position(j.path) for j in (second, third)] == [1, 2]
        with pytest.raises(pipeline.QueueFull):
            worker.submit(fourth.path)
    finally:
        transcriber.release.set()
        worker.stop()


T0 = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)


class _JumpingClock:
    """T0 until `jump` is set, then T0 plus `minutes`: the fake clock for the kill."""

    def __init__(self, minutes: float) -> None:
        self.jump = threading.Event()
        self.after = T0 + timedelta(minutes=minutes)

    def __call__(self) -> datetime:
        return self.after if self.jump.is_set() else T0


class _SleepsInAChild(Transcriber):
    """A step that spends its time in a subprocess, the way ffmpeg and Remotion will."""

    def __init__(self, clock: _JumpingClock) -> None:
        self.clock = clock
        self.outcome: str = "not run"

    def transcribe(self, audio: Path) -> Transcript:
        self.clock.jump.set()
        try:
            subproc.run([sys.executable, "-c", "import time; time.sleep(60)"])
        except subproc.Killed:
            self.outcome = "killed"
            raise
        self.outcome = "finished"
        return FakeTranscriber().transcribe(audio)


def test_past_max_job_minutes_the_step_process_is_killed_and_the_next_job_starts(
    tmp_path: Path, fixture_clip: Path
) -> None:
    clock = _JumpingClock(minutes=31)
    transcriber = _SleepsInAChild(clock)
    worker = _worker(
        transcriber=transcriber, max_job_minutes=30, clock=clock, watchdog_interval_s=0.02
    )
    first, second = _uploaded(tmp_path, fixture_clip), _uploaded(tmp_path, fixture_clip)
    worker.submit(first.path)
    worker.submit(second.path)

    started = time.monotonic()
    assert worker.run_next() is True
    assert time.monotonic() - started < 20  # the child slept for 60 s; it was killed
    assert transcriber.outcome == "killed"
    failed = jobs.load(first.path)
    assert failed.status == "failed"
    assert failed.record.error is not None
    assert failed.record.error.step == "transcribing"
    assert "job exceeded 30 minutes" in failed.record.error.message

    worker._transcriber = FakeTranscriber()  # pyright: ignore[reportPrivateUsage]
    assert worker.run_next() is True
    assert jobs.load(second.path).status == "delivered"


class _SlowInProcess(Transcriber):
    """A step with no subprocess cannot be interrupted; it fails on return."""

    def __init__(self, clock: _JumpingClock) -> None:
        self.clock = clock

    def transcribe(self, audio: Path) -> Transcript:
        self.clock.jump.set()
        return FakeTranscriber().transcribe(audio)


def test_a_step_that_returns_after_the_deadline_still_fails_the_job(
    tmp_path: Path, fixture_clip: Path
) -> None:
    clock = _JumpingClock(minutes=30)  # exactly the limit counts as exceeded
    job = _uploaded(tmp_path, fixture_clip)
    result = pipeline.run_job(
        job,
        transcriber=_SlowInProcess(clock),
        planner=FakePlanner(),
        renderer=FakeRenderer(),
        detector=presenter.FakeFaceDetector(),
        max_job_minutes=30,
        clock=clock,
    )
    assert result.status == "failed"
    assert result.record.error is not None
    assert result.record.error.step == "transcribing"
    assert "job exceeded 30 minutes" in result.record.error.message
    assert not (job.work_dir / "plan.json").exists()


def test_a_job_within_the_limit_is_untouched(tmp_path: Path, fixture_clip: Path) -> None:
    clock = _JumpingClock(minutes=29.9)
    job = _uploaded(tmp_path, fixture_clip)
    result = pipeline.run_job(
        job, transcriber=_SlowInProcess(clock), planner=FakePlanner(), renderer=FakeRenderer(),
        gate=FakeGate(), specs=SPECS, detector=presenter.FakeFaceDetector(),
        max_job_minutes=30, clock=clock,
    )  # fmt: skip
    assert result.status == "delivered"


class _OverBudgetPlanner(FakePlanner):
    """A paid adapter whose pre-call check found the hard cap (011)."""

    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        raise BudgetExceeded("planning", spent_inr=79.0, estimated_inr=5.0, hard_inr=80.0)


def test_budget_exceeded_fails_the_job_at_the_step_with_the_ledger_intact(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    Ledger(Prices({"groq": {"audio_minutes": 0.5}}), Caps(per_job=None, hard=None, per_day=500)) \
        .record(job, "transcribing", "groq", "w", {"audio_minutes": 2})
    done = _run(job, planner=_OverBudgetPlanner())
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "planning"
    assert done.record.error.message == "Budget exceeded at step planning."
    assert "79.0" in done.record.error.detail and "80.0" in done.record.error.detail
    assert len(done.record.cost) == 1  # the rows so far stay on the page (5.6)
    assert not (job.work_dir / "plan.json").exists()


# --- ticket 043: retry from the failed step (decisions 11.1, 5.6, 9.1) ------------


def test_error_text_has_one_sentence_for_every_step() -> None:
    """043: the table the page reads is the whole of the user-facing error text, so a
    new step cannot arrive without a sentence of its own."""
    assert set(pipeline.ERROR_TEXT) == set(jobs.STEPS)
    assert all(text.endswith(".") for text in pipeline.ERROR_TEXT.values())


class _CountingPlanner(FakePlanner):
    """Counts the picture calls so a retry can prove it never planned again."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        self.calls += 1
        return super().plan_picture(request, feedback=feedback)


class _OnceBrokenPlanner(_CountingPlanner):
    """Fails the first picture call the way an adapter outage does, then works."""

    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        plan = super().plan_picture(request, feedback=feedback)
        if self.calls == 1:
            raise RuntimeError("claude said no")
        return plan


class _CountingTranscriber(FakeTranscriber):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def transcribe(self, audio: Path) -> Transcript:
        self.calls += 1
        return super().transcribe(audio)


class _FlakySource(assets.FakeImageSource):
    """Searches happily `fail_after` times, then goes down for the rest of the run."""

    def __init__(self, fail_after: int) -> None:
        super().__init__("web")
        self.fail_after = fail_after

    def search(self, query: str, n: int) -> list[Candidate]:
        if self.searches >= self.fail_after:
            raise RuntimeError("the image search is down")
        return super().search(query, n)


def _with_source(source: assets.ImageSource) -> assets.Sourcing:
    return assets.Sourcing(sources={"web": source}, order=("web",))


def _trail(job: jobs.Job) -> list[str]:
    """The status lines of job.log; the steps' own notes (the critic's, 033) sit
    between them and are left out here."""
    lines = [line.split(" ", 1)[1] for line in job.log_path.read_text("utf-8").splitlines()]
    return [line for line in lines if line == "created uploaded" or " -> " in line]


def test_retry_from_rendering_re_renders_and_calls_no_planner_and_no_source(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """The plan and the assets on disk are the retry's input: a render failure costs
    one more render, never a second plan or a second search (11.1, 5.6)."""
    job = _uploaded(tmp_path, fixture_clip)
    failed = _run(job, renderer=_BrokenRenderer())
    assert failed.record.error is not None and failed.record.error.step == "rendering"

    planner, web = _CountingPlanner(), assets.FakeImageSource("web")
    again = _run(jobs.requeue(failed), planner=planner, sourcing=_with_source(web))
    assert again.status == "delivered"
    assert planner.calls == 0
    assert web.searches == 0 and web.fetches == 0
    assert (job.out_dir / "short.mp4").is_file()
    assert _trail(job)[-4:] == [
        "failed -> uploaded retry_from=rendering",
        "uploaded -> rendering",
        "rendering -> qa",
        "qa -> delivered",
    ]


def test_retry_from_sourcing_searches_only_the_beats_the_cache_does_not_have(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """5.6: the per-job asset cache is what makes the retry cheap - the beats the first
    run already fetched are read off disk and only the rest are searched again."""
    job = _uploaded(tmp_path, fixture_clip)
    failed = _run(job, sourcing=_with_source(_FlakySource(fail_after=2)))
    assert failed.record.error is not None and failed.record.error.step == "sourcing"

    web, planner = assets.FakeImageSource("web"), _CountingPlanner()
    again = _run(jobs.requeue(failed), planner=planner, sourcing=_with_source(web))
    assert again.status == "delivered"
    assert planner.calls == 0  # planning is behind it
    whole = assets.FakeImageSource("web")
    other = _run(_uploaded(tmp_path, fixture_clip), sourcing=_with_source(whole))
    assert other.status == "delivered"
    assert 0 < web.searches == whole.searches - 2  # the two cached beats were not searched


def test_retry_from_planning_re_plans_without_transcribing_again(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    transcriber, planner = _CountingTranscriber(), _OnceBrokenPlanner()
    failed = _run(job, transcriber=transcriber, planner=planner)
    assert failed.record.error is not None and failed.record.error.step == "planning"
    assert transcriber.calls == 1

    again = _run(jobs.requeue(failed), transcriber=transcriber, planner=planner)
    assert again.status == "delivered"
    assert transcriber.calls == 1  # the transcript on disk is the retry's input
    assert planner.calls == 2
    assert (job.work_dir / "plan.json").is_file()


def test_a_retry_that_fails_again_keeps_both_failures_and_can_be_retried_once_more(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    failed = _run(job, renderer=_BrokenRenderer())
    again = _run(jobs.requeue(failed), renderer=_BrokenRenderer())
    assert again.status == "failed"
    assert again.record.error is not None and again.record.error.step == "rendering"
    assert _run(jobs.requeue(again)).status == "delivered"
    assert len([line for line in _trail(job) if "-> failed" in line]) == 2


class _PaidRenderer(FakeRenderer):
    """A render that costs money, so the retry's row can be told from the first one."""

    def __init__(self, book: Ledger) -> None:
        super().__init__()
        self.book = book

    def render(
        self, job: jobs.Job, *, on_progress: Callable[[int], None] | None = None,
        library: sound.Library | None = None,
    ) -> Path:  # fmt: skip
        self.book.record(job, "rendering", "groq", "w", {"audio_minutes": 1})
        return super().render(job, on_progress=on_progress, library=library)


def test_a_retry_adds_ledger_rows_and_keeps_the_ones_already_paid_for(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """5.6: what the failed run spent stays on the job and the retry's own calls are
    new rows beside it, so the page adds up to what the job really cost."""
    book = Ledger(
        Prices({"groq": {"audio_minutes": 0.5}}), Caps(per_job=None, hard=None, per_day=500)
    )
    job = _uploaded(tmp_path, fixture_clip)
    failed = _run(job, renderer=_BrokenRenderer())
    book.record(failed, "transcribing", "groq", "w", {"audio_minutes": 2})

    again = _run(jobs.requeue(jobs.load(job.path)), renderer=_PaidRenderer(book))
    assert again.status == "delivered"
    rows = [(r.step, r.inr) for r in again.record.cost]
    assert rows == [("transcribing", 1.0), ("rendering", 0.5)]


def test_the_worker_runs_a_requeued_job_from_its_step(tmp_path: Path, fixture_clip: Path) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    stopped = pipeline.Worker(
        transcriber=FakeTranscriber(), planner=FakePlanner(), renderer=FakeRenderer(),
        gate=FakeGate(fail="T3"), sourcing=_sourcing(), specs=SPECS,
        detector=presenter.FakeFaceDetector(),
    )  # fmt: skip
    stopped.submit(job.path)
    assert stopped.run_next() is True
    failed = jobs.load(job.path)
    assert failed.status == "failed"
    assert failed.record.error is not None and failed.record.error.step == "qa"

    worker = _worker()
    worker.submit(jobs.requeue(failed).path)
    assert worker.run_next() is True
    assert jobs.load(job.path).status == "delivered"
    assert "uploaded -> qa" in _trail(job)
