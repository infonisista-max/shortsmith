"""qa.critic: the editorial gate (decisions 10.2, 10.3, 12.1; ticket 033).

The `CriticReport` contract (E1-E10 with one reason each, overall, up to five fix
notes, model, advisory), the fake with fixed scores, the input assembly over a job's
files (contact sheet, PIP strip, hook strip, plan summary, stem balance, transcript,
the approved-shorts anchors and the category's pattern data), the vision adapter's one
Messages call on the recorded reply under `tests/fixtures/critic/` with its ledger row
and hard-cap check, and the step that writes the report into `out/qa.json` and never
blocks delivery while advisory. No network, no key."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from anthropic import APIStatusError
from anthropic.types import Message
from PIL import Image
from pydantic import SecretStr, ValidationError

from shortsmith import assets, jobs, pipeline, presenter
from shortsmith.config import Settings
from shortsmith.contracts import CATEGORIES, CRITIC_LINES, CriticLine, CriticReport, PicturePlan
from shortsmith.ledger import BudgetExceeded, Caps, Ledger, Prices
from shortsmith.planner import FakePlanner
from shortsmith.qa import calibration, critic, technical
from shortsmith.qa.critic import Critic, CriticError, FakeCritic, Inputs, VisionCritic
from shortsmith.qa.gate import FakeGate
from shortsmith.render import FakeRenderer
from shortsmith.transcriber import FakeTranscriber
from tests.test_pipeline import BRIEF, SPECS

FIXTURES = Path(__file__).parent / "fixtures" / "critic"
KEY = "sk-ant-test-not-real"
PRICES = Prices(
    {
        "critic": {
            "input_tokens": 0.25,
            "cache_write_input_tokens": 0.3125,
            "cache_read_input_tokens": 0.025,
            "output_tokens": 1.25,
        }
    }
)
FIXTURE_SCORES = [7, 6, 8, 7, 8, 6, 7, 5, 9, 9]


def _jpeg(width: int = 40, height: int = 30) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), (9, 9, 9)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _reply(name: str) -> Message:
    return Message.model_validate(json.loads((FIXTURES / f"{name}.json").read_text("utf-8")))


def _reply_text(name: str = "reply") -> str:
    return "".join(block.text for block in _reply(name).content if block.type == "text")


def _inputs(**changes: Any) -> Inputs:
    given: dict[str, Any] = {
        "contact_sheet": _jpeg(),
        "pip_strip": _jpeg(),
        "hook_strip": _jpeg(),
        "plan_summary": "Runtime: 6.0 s, 11 beats",
        "balance": "bed 10.5 dB under the voice",
        "transcript": "en, 6.0 s, 12 words: one two",
        "anchors": "## The bar\nGLOBAL: top YouTube Shorts",
        "pattern_data": "",
        "category": "science",
        "notes": ("no reference data for science",),
    }
    given.update(changes)
    return Inputs(**given)


@dataclass
class StubApi:
    """Answers with the queued replies (or raises them) and records every call."""

    replies: list[Message | Exception]
    requests: list[dict[str, Any]] = field(default_factory=lambda: [])

    def __call__(self, **params: Any) -> Message:
        self.requests.append(params)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def body(self, index: int = 0) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(json.dumps(self.requests[index])))


@pytest.fixture
def job(tmp_path: Path) -> jobs.Job:
    return jobs.create(tmp_path, style="explainer", style_note="explainer")


def _book(hard: float | None = None) -> Ledger:
    return Ledger(PRICES, Caps(per_job=None, hard=hard, per_day=500))


def _sourcing() -> assets.Sourcing:
    """The fake web source plus the fake generator, so the plan's `generate` beats are
    made rather than rescued and the summary has both origins to name."""
    return assets.Sourcing(
        sources={"web": assets.FakeImageSource("web")},
        order=("web",),
        generator=assets.FakeImageGenerator(),
    )


def _delivered(tmp_path: Path, fixture_clip: Path) -> jobs.Job:
    """A job the fakes ran to `delivered` (the pipeline test's path: fake renderer,
    fake gate, fake detector, the fixture-shaped specs), for the critic to read."""
    import shutil

    job = jobs.create(tmp_path, style="explainer", style_note="explainer, energetic")
    shutil.copyfile(fixture_clip, job.input_dir / "raw.mp4")
    (job.input_dir / "brief.md").write_text(BRIEF, encoding="utf-8")
    (job.input_dir / "refs.json").write_text("[]", encoding="utf-8")
    done = pipeline.run_job(
        job,
        transcriber=FakeTranscriber(),
        planner=FakePlanner(),
        renderer=FakeRenderer(),
        gate=FakeGate(),
        sourcing=_sourcing(),
        specs=SPECS,
        detector=presenter.FakeFaceDetector(),
        critic=FakeCritic(),
    )
    assert done.status == "delivered"
    return job


def _critic(api: StubApi, job: jobs.Job, *, book: Ledger | None = None) -> VisionCritic:
    ledger = book or _book()
    return VisionCritic(
        lambda: ledger, api_key=SecretStr(KEY), model="claude-sonnet-5", create=api
    ).bind(job)


# --- the contract (10.2, 10.3) ------------------------------------------------------------


def test_the_ten_lines_are_the_rubric_in_order() -> None:
    assert [name for name, _ in CRITIC_LINES] == [f"E{n}" for n in range(1, 11)]
    assert [label for _, label in CRITIC_LINES] == [
        "hook", "broll_relevance", "mode_variation", "density", "captions", "pip_framing",
        "sound", "payoff", "integrity", "embarrassment",
    ]  # fmt: skip


def test_a_scored_report_carries_every_line_in_order_an_overall_and_at_most_five_notes() -> None:
    lines = [
        CriticLine(name=name, label=label, score=7, reason="fine")
        for name, label in CRITIC_LINES
    ]
    report = CriticReport(lines=lines, overall=7, fix_notes=["a"], model="m")
    assert report.status == "scored" and report.advisory is True
    with pytest.raises(ValidationError, match="E1"):
        CriticReport(lines=lines[1:], overall=7, model="m")
    with pytest.raises(ValidationError, match="overall"):
        CriticReport(lines=lines, overall=None, model="m")
    with pytest.raises(ValidationError):
        CriticReport(lines=lines, overall=7, fix_notes=list("abcdef"), model="m")
    with pytest.raises(ValidationError):
        CriticLine(name="E1", label="hook", score=0, reason="")
    with pytest.raises(ValidationError):
        CriticLine(name="E1", label="hook", score=11, reason="")


def test_an_unavailable_report_has_no_lines_and_says_why() -> None:
    report = critic.unavailable("m", "the critic could not be reached", category="science")
    assert report.status == "unavailable" and report.lines == [] and report.overall is None
    assert report.notes == ["the critic could not be reached"]
    assert report.category == "science"
    with pytest.raises(ValidationError, match="unavailable"):
        CriticReport(status="unavailable", overall=7, model="m")


def test_the_category_list_is_fixed_and_the_plan_carries_one() -> None:
    """10.3: the planner sets the category from a fixed list; the fake plan names one
    of them, and a plan that names none reads `other`."""
    for name in ("history", "geopolitics", "finance", "product", "motivation", "science"):
        assert name in CATEGORIES
    assert "other" in CATEGORIES
    plan = FakePlanner().plan_picture(_request())
    assert plan.category in CATEGORIES and plan.category != "other"
    bare = PicturePlan.model_validate(
        {k: v for k, v in plan.model_dump().items() if k != "category"}
    )
    assert bare.category == "other"


def _request() -> Any:
    from shortsmith.contracts import Constraints, PlanRequest, PlanStyle
    from shortsmith.transcriber import FakeTranscriber

    return PlanRequest(
        brief="Topic: nothing.",
        style=PlanStyle(name="explainer"),
        style_note="",
        transcript=FakeTranscriber().transcribe(Path("unused.mp4")),
        references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=6.0),
        asset_policy="any",
    )


# --- the fake (12.1) ----------------------------------------------------------------------


def test_the_fake_returns_fixed_scores_and_records_its_inputs() -> None:
    fake = FakeCritic()
    given = _inputs()
    report = fake.score(given)
    assert [line.name for line in report.lines] == [name for name, _ in CRITIC_LINES]
    assert [line.label for line in report.lines] == [label for _, label in CRITIC_LINES]
    assert [line.score for line in report.lines] == list(FakeCritic.SCORES)
    assert all(line.reason for line in report.lines)
    assert report.overall == FakeCritic.OVERALL and report.model == "fake"
    assert 1 <= len(report.fix_notes) <= 5
    assert report.category == "science" and report.notes == ["no reference data for science"]
    assert fake.calls == 1 and fake.inputs == [given]


def test_the_fake_ignores_the_job_it_is_bound_to(job: jobs.Job) -> None:
    fake = FakeCritic()
    assert fake.bind(job) is fake


def test_the_fake_can_be_told_its_overall_for_the_calibration_tests() -> None:
    low = FakeCritic(overall=4).score(_inputs())
    assert low.overall == 4


# --- the parser ---------------------------------------------------------------------------


def test_the_recorded_reply_becomes_ten_lines_an_overall_and_the_notes() -> None:
    report = critic.parse_reply(_reply_text(), model="claude-sonnet-5", category="science")
    assert [line.score for line in report.lines] == FIXTURE_SCORES
    assert report.lines[0].label == "hook"
    assert report.lines[7].reason.startswith("The finale word repeats the title")
    assert report.overall == 7
    assert len(report.fix_notes) == 3 and report.fix_notes[0].startswith("Lower the PIP")
    assert report.model == "claude-sonnet-5" and report.category == "science"


def _lines(scores: list[int], *, skip: str | None = None) -> list[dict[str, Any]]:
    return [
        {"name": name, "score": score, "reason": f"because {name}"}
        for (name, _), score in zip(CRITIC_LINES, scores, strict=True)
        if name != skip
    ]


def test_the_parser_survives_what_a_model_actually_sends() -> None:
    """Scores are clamped to 1-10, a missing overall is the rounded mean, more than
    five notes are cut to five, prose around the JSON is ignored."""
    wild = {"lines": _lines([0, 12, 7, 7, 7, 7, 7, 7, 7, 7]), "fix_notes": list("abcdefg")}
    report = critic.parse_reply(f"Here you go:\n{json.dumps(wild)}\nHope it helps", model="m",
                                category="other")  # fmt: skip
    assert [line.score for line in report.lines][:2] == [1, 10]
    assert report.overall == round((1 + 10 + 7 * 8) / 10)
    assert report.fix_notes == list("abcde")


def test_a_reply_missing_a_line_or_the_json_is_a_critic_error() -> None:
    with pytest.raises(CriticError, match="E4"):
        critic.parse_reply(json.dumps({"lines": _lines([7] * 10, skip="E4"), "overall": 7}),
                           model="m", category="other")  # fmt: skip
    with pytest.raises(CriticError, match="did not answer with JSON"):
        critic.parse_reply("I cannot see the images.", model="m", category="other")
    with pytest.raises(CriticError, match="lines"):
        critic.parse_reply('{"scores": []}', model="m", category="other")


# --- the vision adapter (10.2) ------------------------------------------------------------


def test_one_messages_call_carries_the_rubric_the_anchors_the_texts_and_the_images(
    job: jobs.Job,
) -> None:
    api = StubApi([_reply("reply")])
    report = _critic(api, job).score(_inputs())
    assert [line.score for line in report.lines] == FIXTURE_SCORES

    body = api.body()
    assert body["model"] == "claude-sonnet-5"
    rubric, anchors = body["system"]
    assert rubric["cache_control"] == {"type": "ephemeral"}
    assert all(label in rubric["text"] for _, label in CRITIC_LINES)
    assert "JSON" in rubric["text"] and "1" in rubric["text"] and "10" in rubric["text"]
    assert anchors["cache_control"] == {"type": "ephemeral"}
    assert "top YouTube Shorts" in anchors["text"]
    (message,) = body["messages"]
    texts = [block["text"] for block in message["content"] if block["type"] == "text"]
    joined = "\n".join(texts)
    assert "11 beats" in joined and "10.5 dB under the voice" in joined and "12 words" in joined
    assert "no reference data for science" in joined
    images = [block for block in message["content"] if block["type"] == "image"]
    assert len(images) == 3
    assert {block["source"]["media_type"] for block in images} == {"image/jpeg"}
    # Every image is introduced by the text block before it, so the model knows
    # which strip it is looking at.
    kinds = [block["type"] for block in message["content"]]
    for i, kind in enumerate(kinds):
        if kind == "image":
            assert kinds[i - 1] == "text"


def test_the_built_request_is_the_recorded_one(job: jobs.Job) -> None:
    """12.1: the whole request body against `fixtures/critic/request.json`, recorded
    from the code's own builder on these inputs: the rubric and the anchors as the two
    cached system blocks, the texts in order, then each strip after its label. Only the
    image data is masked, since the JPEG bytes are the test's."""
    api = StubApi([_reply("reply")])
    _critic(api, job).score(_inputs())
    sent = api.body()
    for block in sent["messages"][0]["content"]:
        if block["type"] == "image":
            block["source"]["data"] = "<jpeg base64>"
    expected = json.loads((FIXTURES / "request.json").read_text(encoding="utf-8"))
    assert sent == expected


def test_a_missing_strip_is_left_out_and_said_so(job: jobs.Job) -> None:
    api = StubApi([_reply("reply")])
    _critic(api, job).score(_inputs(hook_strip=None, notes=("hook strip: no short to read",)))
    (message,) = api.body()["messages"]
    images = [block for block in message["content"] if block["type"] == "image"]
    assert len(images) == 2
    texts = "\n".join(b["text"] for b in message["content"] if b["type"] == "text")
    assert "hook strip: no short to read" in texts


def test_every_call_is_one_critic_ledger_row_in_the_qa_step(job: jobs.Job) -> None:
    api = StubApi([_reply("reply")])
    _critic(api, job).score(_inputs())
    (row,) = jobs.load(job.path).record.cost
    assert (row.step, row.provider, row.model) == ("qa", "critic", "claude-sonnet-5")
    assert row.units == {
        "input_tokens": 6120.0,
        "cache_write_input_tokens": 1830.0,
        "cache_read_input_tokens": 0.0,
        "output_tokens": 410.0,
    }
    assert row.inr == pytest.approx(
        6120 * 0.25 / 1000 + 1830 * 0.3125 / 1000 + 410 * 1.25 / 1000
    )


def test_the_hard_cap_stops_the_call_before_it_is_made(job: jobs.Job) -> None:
    """11.3: the call never happens, so it is never billed."""
    api = StubApi([_reply("reply")])
    with pytest.raises(BudgetExceeded, match="qa"):
        _critic(api, job, book=_book(hard=0.0001)).score(_inputs())
    assert api.requests == []
    assert jobs.load(job.path).record.cost == []


def test_an_api_error_is_a_critic_error_in_the_apis_own_words(job: jobs.Job) -> None:
    response = SimpleNamespace(status_code=529, headers={}, request=None)
    error = APIStatusError(
        "boom", response=cast(Any, response), body={"error": {"message": "overloaded"}}
    )
    with pytest.raises(CriticError, match="529: overloaded"):
        _critic(StubApi([error]), job).score(_inputs())
    assert KEY not in str(jobs.load(job.path).record)


def test_a_refusal_is_a_critic_error_after_the_row(job: jobs.Job) -> None:
    with pytest.raises(CriticError, match="refused"):
        _critic(StubApi([_reply("refusal")]), job).score(_inputs())
    assert len(jobs.load(job.path).record.cost) == 1  # the answered call is still billed


def test_an_unbound_critic_or_a_missing_key_says_so(job: jobs.Job) -> None:
    api = StubApi([_reply("reply")])
    unbound = VisionCritic(_book, api_key=SecretStr(KEY), create=api)
    with pytest.raises(CriticError, match="bind"):
        unbound.score(_inputs())
    keyless = VisionCritic(_book, api_key=None, create=api).bind(job)
    with pytest.raises(CriticError, match="ANTHROPIC_API_KEY"):
        keyless.score(_inputs())


def test_the_config_selects_the_fake_or_the_vision_critic_on_the_configured_model(
    tmp_path: Path,
) -> None:
    def settings(**overrides: Any) -> Settings:
        return Settings(_env_file=None, shortsmith_data_dir=tmp_path, **overrides)  # pyright: ignore[reportCallIssue]

    assert isinstance(critic.from_settings(settings(critic="fake"), ledger=_book), FakeCritic)
    vision = critic.from_settings(
        settings(critic="api", critic_model="claude-opus-5"), ledger=_book
    )
    assert isinstance(vision, VisionCritic) and vision.model == "claude-opus-5"


# --- the anchors and the category pattern data (10.3) -------------------------------------


def test_the_anchors_are_the_bar_and_the_two_approved_shorts_from_the_reference_readme(
    tmp_path: Path,
) -> None:
    text = critic.anchors_text(critic.REFERENCE_README)
    assert text.startswith("## The bar")
    assert "NeemKaroliBaba_Short_v4.mp4" in text and "DysonToothbrush_Short_v1.mp4" in text
    assert "## Evidence" not in text and "ffmpeg" not in text
    assert critic.anchors_text(tmp_path / "missing.md") == critic.NO_REFERENCE_PACK


def test_the_category_readme_is_read_when_it_exists_and_noted_when_it_does_not(
    tmp_path: Path,
) -> None:
    (tmp_path / "finance").mkdir()
    (tmp_path / "finance" / "README.md").write_text("# finance\ncuts per 10 s: 9", "utf-8")
    found, note = critic.pattern_data("finance", reference_dir=tmp_path)
    assert "cuts per 10 s: 9" in found and note is None
    missing, note = critic.pattern_data("science", reference_dir=tmp_path)
    assert missing == "" and note == "no reference data for science"


# --- the inputs over a job's files (10.3) --------------------------------------------------


def test_build_inputs_assembles_the_texts_and_the_images_from_the_job(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """On a job the fakes ran: the contact sheet is the gate's file, the PIP strip is
    composed from the eight measured stills, the hook strip cannot be read from the
    fake's empty short and says so, and the plan summary carries the 10.3 numbers."""
    job = _delivered(tmp_path, fixture_clip)
    inputs = critic.build_inputs(job, reference_dir=tmp_path / "no-such-dir")
    assert inputs.contact_sheet == (job.out_dir / "contact.jpg").read_bytes()
    assert inputs.pip_strip is not None
    with Image.open(BytesIO(inputs.pip_strip)) as strip:
        assert strip.format == "JPEG" and strip.width > strip.height
    assert inputs.hook_strip is None
    assert any(note.startswith("hook strip:") for note in inputs.notes)
    assert inputs.category == "science" and "no reference data for science" in inputs.notes
    summary = inputs.plan_summary
    assert "11 beats" in summary and "runtime 6.0 s" in summary
    assert "full 8%" in summary and "pip 33%" in summary and "off 58%" in summary
    assert "mean beat 0.55 s" in summary and "longest beat 1.00 s" in summary
    assert "1 clamp" in summary and "(6.1)" in summary
    assert "0 rescued" in summary
    assert "origins: " in summary and "web: " in summary and "generated: " in summary
    assert "hook title: A Short About Nothing" in summary
    assert "finale word: Made from nothing" in summary
    assert "category: science" in summary
    assert inputs.balance == critic.NO_BALANCE
    assert inputs.transcript.startswith("Language en, 6.0 s, 12 words:\nhello there")
    # The anchors come from the same pack directory as the category data.
    assert inputs.anchors == critic.NO_REFERENCE_PACK
    assert critic.build_inputs(job).anchors.startswith("## The bar")


def test_build_inputs_reads_the_balance_report_and_the_category_data_when_present(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _delivered(tmp_path, fixture_clip)
    stems = job.work_dir / "stems"
    stems.mkdir(exist_ok=True)
    (stems / "balance.json").write_text(
        json.dumps({
            "voice_db": -19.0, "bed_median_db": -30.0, "bed_under_voice_db": -11.0,
            "duck_db": 2.5, "speech_band_margin_db": 24.0, "bed_accept_db": [-12, -9],
            "speech_band_margin_min_db": 20.0, "duck_max_db": 4.0, "cues": 5,
            "problems": [],
        }),  # fmt: skip
        encoding="utf-8",
    )
    reference = tmp_path / "reference"
    (reference / "science").mkdir(parents=True)
    (reference / "science" / "README.md").write_text("# science\ncuts per 10 s: 7", "utf-8")
    (reference / "README.md").write_text(
        "# Pack\n\n## The bar\n\nthe test bar\n\n## Evidence\n\nffmpeg\n", "utf-8"
    )
    inputs = critic.build_inputs(job, reference_dir=reference)
    assert inputs.anchors == "## The bar\n\nthe test bar"
    assert "bed -11.0 dB relative to the voice (accept -12 to -9)" in inputs.balance
    assert "duck 2.5 dB" in inputs.balance and "5 cues" in inputs.balance
    assert "inside the 7.3 band" in inputs.balance
    assert "cuts per 10 s: 7" in inputs.pattern_data
    assert "no reference data for science" not in inputs.notes


# --- the step: build, score, write into qa.json (10.2) -------------------------------------


def test_run_writes_the_report_into_qa_json_advisory_and_notes_the_log(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _delivered(tmp_path, fixture_clip)
    fake = FakeCritic()
    written = critic.run(job, fake, reference_dir=tmp_path / "none")
    report = technical.load_report(job)
    assert report is not None and report.passed and report.critic == written
    assert written.status == "scored" and written.advisory is True
    assert written.category == "science" and written.model == "fake"
    assert fake.calls == 1
    log = job.log_path.read_text("utf-8")
    assert f"critic: overall {written.overall}/10 advisory (fake)" in log


def test_run_writes_the_summary_onto_job_json_for_the_verdict_and_the_calibration(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """034: `job.json.critic` carries the overall, the status and the mode the critic
    ran under, so the verdict and `calibration.json` read one file."""
    job = _delivered(tmp_path, fixture_clip)
    critic.run(job, FakeCritic(overall=8), reference_dir=tmp_path / "none")
    summary = jobs.load(job.path).record.critic
    assert summary is not None
    assert summary.status == "scored" and summary.overall == 8 and summary.advisory is True
    assert summary.model == "fake"


def test_run_is_blocking_once_the_calibration_streak_says_so(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """10.2: the mode comes from `<data_dir>/calibration.json` (four of the last five
    rated jobs matched), never from a constant; the report and the log both say so."""
    job = _delivered(tmp_path, fixture_clip)
    calibration.save(tmp_path, _streak(matches=4))
    written = critic.run(job, FakeCritic(overall=8), reference_dir=tmp_path / "none")
    assert written.advisory is False
    summary = jobs.load(job.path).record.critic
    assert summary is not None and summary.advisory is False
    assert "critic: overall 8/10 blocking (fake)" in job.log_path.read_text("utf-8")
    calibration.save(tmp_path, _streak(matches=3))
    assert critic.run(job, FakeCritic(), reference_dir=tmp_path / "none").advisory is True


def _streak(*, matches: int) -> calibration.Calibration:
    entries = [
        calibration.Entry(
            job_id=f"20260926-09000{i}-abcdef", critic_overall=8, critic_pass=True, rating=7,
            phone_pass=True, matched=i < matches, at=datetime(2026, 9, 26, tzinfo=UTC),
        )  # fmt: skip
        for i in range(5)
    ]
    return calibration.Calibration(entries=entries)


class _Broken(FakeCritic):
    def score(self, inputs: Inputs) -> CriticReport:
        raise CriticError("the critic could not be reached: boom")


def test_a_critic_that_cannot_answer_leaves_the_report_unavailable_not_the_job_failed(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _delivered(tmp_path, fixture_clip)
    written = critic.run(job, _Broken(), reference_dir=tmp_path / "none")
    assert written.status == "unavailable"
    summary = jobs.load(job.path).record.critic
    assert summary is not None and summary.status == "unavailable" and summary.overall is None
    # The reason first, then what the inputs lacked, so the page can say both.
    assert written.notes[0] == "the critic could not be reached: boom"
    assert "no reference data for science" in written.notes
    report = technical.load_report(job)
    assert report is not None and report.passed and report.critic == written
    assert "critic: unavailable: the critic could not be reached: boom" in job.log_path.read_text(
        "utf-8"
    )


class _OverBudget(FakeCritic):
    def score(self, inputs: Inputs) -> CriticReport:
        raise BudgetExceeded("qa", spent_inr=70.0, estimated_inr=20.0, hard_inr=80.0)


def test_the_hard_cap_is_not_an_api_failure_and_reaches_the_pipeline(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """11.3: a refused paid call fails the job visibly; it is never a quiet unavailable."""
    job = _delivered(tmp_path, fixture_clip)
    with pytest.raises(BudgetExceeded):
        critic.run(job, _OverBudget(), reference_dir=tmp_path / "none")


def test_the_interface_binds_and_scores() -> None:
    assert issubclass(FakeCritic, Critic) and issubclass(VisionCritic, Critic)
