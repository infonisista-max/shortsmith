"""reference.own / reference.compare: every delivered short goes through the reference
tool, and the job page compares it with the references by numbers (ticket 074).

The Gemini adapter's local-file path on a mock transport (the resumable upload, the
poll until `ACTIVE`, `generateContent` on the uploaded URI at the configured fps, the
delete), the advisory `inventory` step (a v2 card with `tier: own`, its ledger row, a
failure that leaves the job delivered with `not_analysed`), the comparison against the
v2 cards of the job's style, `meta.json` and the job page. No network, no key.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr

from shortsmith import app, jobs, ledger, meta, pipeline, presenter, render
from shortsmith.config import Settings
from shortsmith.contracts import ComparisonRow, InventoryComparison
from shortsmith.jobs import Job
from shortsmith.ledger import Caps, Ledger, Prices
from shortsmith.planner import FakePlanner
from shortsmith.qa.critic import FakeCritic
from shortsmith.qa.gate import FakeGate
from shortsmith.reference import (
    PROMPT_VERSION,
    InventoryAnswerV2,
    ReferenceInventory,
    ReferenceInventoryV2,
    ReferenceLink,
    Tier,
    own,
    parse_answer,
)
from shortsmith.reference import __main__ as cli
from shortsmith.reference import compare as compare_module
from shortsmith.reference.gemini import AnalyserError, FakeAnalyser, GeminiAnalyser, Usage
from shortsmith.render import FakeRenderer
from shortsmith.transcriber import FakeTranscriber
from tests.test_pipeline import SPECS, _sourcing, _uploaded  # pyright: ignore[reportPrivateUsage]

FIXTURES = Path(__file__).parent / "fixtures" / "gemini"
KEY = "gemini-test-key-not-a-real-one"
REGISTRY = render.registry()
UPLOAD = "https://generativelanguage.googleapis.com/upload/v1beta/files"
FILE_URL = "https://generativelanguage.googleapis.com/v1beta/files/own-short-test"
GENERATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-test-video:generateContent"
)


def _files() -> dict[str, Any]:
    return json.loads((FIXTURES / "files.json").read_text(encoding="utf-8"))


def _generate() -> dict[str, Any]:
    return json.loads((FIXTURES / "inventory_v2.json").read_text(encoding="utf-8"))


def _answer_text() -> str:
    return _generate()["candidates"][0]["content"]["parts"][0]["text"]


# --- the Gemini adapter: a local file ----------------------------------------------------


class Tape:
    """The Files API and generateContent on one mock transport, from the recorded JSON."""

    def __init__(self, *, polls: tuple[str, ...] = ("processing", "active"),
                 generate_status: int = 200) -> None:  # fmt: skip
        self.files = _files()
        self.polls = list(polls)
        self.generate_status = generate_status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        command = request.headers.get("x-goog-upload-command", "")
        if url == UPLOAD and command == "start":
            return httpx.Response(200, headers=self.files["start"]["headers"])
        if url.startswith(UPLOAD) and "finalize" in command:
            return httpx.Response(200, json=self.files["finalize"])
        if url == FILE_URL and request.method == "GET":
            return httpx.Response(200, json=self.files[self.polls.pop(0)])
        if url == FILE_URL and request.method == "DELETE":
            return httpx.Response(200, json=self.files["delete"])
        if url == GENERATE:
            if self.generate_status >= 400:
                body = {"error": {"code": self.generate_status, "message": "overloaded"}}
                return httpx.Response(self.generate_status, json=body)
            return httpx.Response(200, json=_generate())
        return httpx.Response(404, json={"error": {"message": f"unexpected {url}"}})

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    def calls(self) -> list[tuple[str, str]]:
        return [(r.method, str(r.url).split("?")[0]) for r in self.requests]


def _gemini(tape: Tape) -> GeminiAnalyser:
    return GeminiAnalyser(
        api_key=SecretStr(KEY), model="gemini-test-video", fps=5.0, client=tape.client(),
        sleep=lambda _s: None,
    )  # fmt: skip


def _short(tmp_path: Path) -> Path:
    video = tmp_path / "short.mp4"
    video.write_bytes(b"\x00" * 2048)  # never media: bytes the mock transport receives
    return video


def test_a_local_file_is_uploaded_polled_until_active_analysed_and_deleted(
    tmp_path: Path,
) -> None:
    tape = Tape()
    answer = _gemini(tape).analyse_file(_short(tmp_path), "watch this")
    assert tape.calls() == [
        ("POST", UPLOAD),
        ("POST", UPLOAD),
        ("GET", FILE_URL),
        ("GET", FILE_URL),
        ("POST", GENERATE),
        ("DELETE", FILE_URL),
    ]
    start, finalize = tape.requests[0], tape.requests[1]
    assert start.headers["x-goog-upload-protocol"] == "resumable"
    assert start.headers["x-goog-upload-header-content-length"] == "2048"
    assert start.headers["x-goog-upload-header-content-type"] == "video/mp4"
    assert start.headers["x-goog-api-key"] == KEY
    assert "upload_id=test-upload-id" in str(finalize.url)
    assert finalize.headers["x-goog-upload-offset"] == "0"
    assert finalize.content == b"\x00" * 2048
    sent = json.loads(tape.requests[4].content.decode("utf-8"))
    parts = sent["contents"][0]["parts"]
    assert parts[0] == {
        "fileData": {"fileUri": FILE_URL, "mimeType": "video/mp4"},
        "videoMetadata": {"fps": 5.0},
    }
    assert parts[1] == {"text": "watch this"}
    assert sent["generationConfig"]["responseMimeType"] == "application/json"
    assert answer.text == _answer_text()
    assert (answer.usage.prompt_tokens, answer.usage.output_tokens) == (24800, 7100)
    assert answer.usage.thoughts_tokens == 1100


def test_the_uploaded_file_is_deleted_when_the_analysis_fails(tmp_path: Path) -> None:
    tape = Tape(polls=("active",), generate_status=503)
    with pytest.raises(AnalyserError) as raised:
        _gemini(tape).analyse_file(_short(tmp_path), "p")
    assert raised.value.status == 503
    assert tape.calls()[-1] == ("DELETE", FILE_URL)
    assert KEY not in str(raised.value)


def test_a_file_the_api_cannot_process_is_an_analyser_error_and_is_deleted(
    tmp_path: Path,
) -> None:
    tape = Tape(polls=("failed",))
    with pytest.raises(AnalyserError, match="could not be processed"):
        _gemini(tape).analyse_file(_short(tmp_path), "p")
    assert ("POST", GENERATE) not in tape.calls()
    assert tape.calls()[-1] == ("DELETE", FILE_URL)


def test_a_file_that_never_becomes_active_stops_after_the_wait(tmp_path: Path) -> None:
    tape = Tape(polls=("processing",) * 10)
    analyser = GeminiAnalyser(
        api_key=SecretStr(KEY), model="gemini-test-video", client=tape.client(),
        sleep=lambda _s: None, poll_s=1.0, active_timeout_s=3.0,
    )  # fmt: skip
    with pytest.raises(AnalyserError, match="ACTIVE"):
        analyser.analyse_file(_short(tmp_path), "p")
    assert [c for c in tape.calls() if c[0] == "GET"] == [("GET", FILE_URL)] * 3
    assert tape.calls()[-1] == ("DELETE", FILE_URL)


def test_a_local_file_without_a_key_names_the_setting_and_sends_nothing(
    tmp_path: Path,
) -> None:
    tape = Tape()
    analyser = GeminiAnalyser(api_key=None, model="m", client=tape.client())
    with pytest.raises(AnalyserError, match="GEMINI_API_KEY"):
        analyser.analyse_file(_short(tmp_path), "p")
    assert tape.requests == []


def test_the_fake_analyser_answers_a_file_and_records_it(tmp_path: Path) -> None:
    fake = FakeAnalyser(["{}"])
    video = _short(tmp_path)
    answer = fake.analyse_file(video, "prompt")
    assert answer.text == "{}"
    assert fake.calls == [(str(video), "prompt")]


# --- the step ----------------------------------------------------------------------------


def _delivered(data_dir: Path, *, style: str = "explainer") -> Job:
    job = jobs.create(data_dir, style=style, style_note=style)
    for status in (*jobs.STEPS, "delivered"):
        job = jobs.transition(job, status)
    (job.out_dir / "short.mp4").write_bytes(b"\x00" * 2048)
    return job


def _book() -> Ledger:
    return Ledger(
        Prices({"reference": {"input_tokens": 0.1, "output_tokens": 0.4}}),
        Caps(per_job=None, hard=None, per_day=500.0),
    )


def test_the_step_writes_a_v2_card_with_tier_own_and_the_job_id(tmp_path: Path) -> None:
    job = _delivered(tmp_path)
    fake = FakeAnalyser([_answer_text()], model="fake-video")
    result = own.SelfInventory(fake).run(job)
    assert isinstance(result, ReferenceInventoryV2)
    card = own.load(job)
    assert isinstance(card, ReferenceInventoryV2)
    assert (card.tier, card.video_id, card.styles) == ("own", job.id, ["explainer"])
    assert card.prompt_version == PROMPT_VERSION
    assert fake.calls[0][0] == str(job.out_dir / "short.mp4")
    assert (job.out_dir / own.NAME).is_file()
    assert jobs.load(job.path).status == "delivered"
    log = job.log_path.read_text(encoding="utf-8")
    assert "inventory: " in log
    assert all(" -> " not in line for line in log.splitlines() if "inventory" in line)


def test_the_step_records_a_reference_ledger_row_per_request(tmp_path: Path) -> None:
    job = _delivered(tmp_path)
    fake = FakeAnalyser(["not json", _answer_text()], model="fake-video")
    book = _book()
    own.SelfInventory(fake, ledger=lambda: book).run(job)
    rows = jobs.load(job.path).record.cost
    assert [(r.step, r.provider) for r in rows] == [("reference", "reference")] * 2
    assert set(rows[0].units) == {"input_tokens", "output_tokens"}
    assert rows[1].units["input_tokens"] > 0
    assert rows[1].inr > 0


def test_ledger_needs_a_reference_price_only_when_the_gemini_key_is_set() -> None:
    keyless = Settings(_env_file=None, transcriber="fake", planner="fake",  # pyright: ignore[reportCallIssue]
                       relevance_judge="none", critic="fake")  # fmt: skip
    assert "reference" not in ledger.providers_in_use(keyless)
    keyed = keyless.model_copy(update={"gemini_api_key": SecretStr(KEY)})
    assert "reference" in ledger.providers_in_use(keyed)
    assert ledger.REQUIRED_UNITS["reference"] == ("input_tokens", "output_tokens")


@pytest.mark.parametrize(
    "answers",
    [
        [AnalyserError("the analyser answered 403: upload refused", status=403)],
        ["not json", "still not json"],
        [],
    ],
)
def test_a_failing_analyser_leaves_the_job_delivered_and_not_analysed(
    tmp_path: Path, answers: list[str | AnalyserError]
) -> None:
    job = _delivered(tmp_path)
    result = own.SelfInventory(FakeAnalyser(list(answers))).run(job)
    assert isinstance(result, own.NotAnalysed)
    data = json.loads((job.out_dir / own.NAME).read_text(encoding="utf-8"))
    assert data["status"] == "not_analysed" and data["reason"]
    assert jobs.load(job.path).status == "delivered"
    assert "inventory: not analysed: " in job.log_path.read_text(encoding="utf-8")


def test_a_keyless_gemini_is_not_analysed_with_the_setting_named(tmp_path: Path) -> None:
    job = _delivered(tmp_path)
    result = own.SelfInventory(GeminiAnalyser(api_key=None)).run(job)
    assert isinstance(result, own.NotAnalysed)
    assert "GEMINI_API_KEY" in result.reason


def test_the_hard_cap_makes_the_step_not_analysed_never_a_failed_job(tmp_path: Path) -> None:
    job = _delivered(tmp_path)
    book = Ledger(Prices({"reference": {"input_tokens": 100.0, "output_tokens": 100.0}}),
                  Caps(per_job=None, hard=1.0, per_day=500.0))  # fmt: skip
    fake = FakeAnalyser([_answer_text()])
    result = own.SelfInventory(fake, ledger=lambda: book).run(job)
    assert isinstance(result, own.NotAnalysed)
    assert "budget exceeded" in result.reason
    assert fake.calls == []
    assert jobs.load(job.path).status == "delivered"


# --- the pipeline ------------------------------------------------------------------------


def _pipeline_run(job: Job, step: own.SelfInventory | None) -> Job:
    return pipeline.run_job(
        job, transcriber=FakeTranscriber(), planner=FakePlanner(), renderer=FakeRenderer(),
        gate=FakeGate(), sourcing=_sourcing(), specs=SPECS,
        detector=presenter.FakeFaceDetector(), critic=FakeCritic(), inventory=step,
    )  # fmt: skip


def test_the_pipeline_runs_the_step_after_qa_and_meta_carries_it(
    tmp_path: Path, fixture_clip: Path
) -> None:
    fake = FakeAnalyser([_answer_text()])
    done = _pipeline_run(_uploaded(tmp_path, fixture_clip), own.SelfInventory(fake))
    assert done.status == "delivered"
    assert fake.calls and fake.calls[0][0] == str(done.out_dir / "short.mp4")
    assert isinstance(own.load(done), ReferenceInventoryV2)
    recorded = meta.load(done)
    assert recorded is not None and recorded.inventory is not None
    assert recorded.inventory.status == "analysed"
    lines = [line.split(" ", 1)[1] for line in done.log_path.read_text("utf-8").splitlines()]
    first = next(i for i, line in enumerate(lines) if line.startswith("inventory: "))
    assert lines.index("qa -> delivered") < first


def test_a_failing_step_leaves_the_pipelines_job_delivered(
    tmp_path: Path, fixture_clip: Path
) -> None:
    step = own.SelfInventory(FakeAnalyser([AnalyserError("upload refused", status=400)]))
    done = _pipeline_run(_uploaded(tmp_path, fixture_clip), step)
    assert done.status == "delivered" and done.record.error is None
    recorded = meta.load(done)
    assert recorded is not None and recorded.inventory is not None
    assert recorded.inventory.status == "not_analysed"


def test_the_worker_default_is_a_keyless_gemini_that_sends_nothing(
    tmp_path: Path, fixture_clip: Path
) -> None:
    done = _pipeline_run(_uploaded(tmp_path, fixture_clip), None)
    found = own.load(done)
    assert isinstance(found, own.NotAnalysed) and "GEMINI_API_KEY" in found.reason


# --- the comparison ----------------------------------------------------------------------


def _card(vid: str, *, shots: int, duration: float = 60.0, tier: str = "A",
          styles: tuple[str, ...] = ("explainer",), bed: bool = True,
          layout: str = "full_footage") -> ReferenceInventoryV2:  # fmt: skip
    """A v2 card from the recorded answer with `shots` equal shots over `duration`."""
    answer = parse_answer(_answer_text(), registry=REGISTRY, version="v2")
    data = answer.model_dump()
    step = duration / shots
    data["duration_s"] = duration
    data["shots"] = [
        {"start_s": i * step, "end_s": (i + 1) * step, "layout": layout,
         "background": "moving_footage"}
        for i in range(shots)
    ]  # fmt: skip
    data["sound"]["bed"] = bed
    link = ReferenceLink(url=f"https://www.youtube.com/watch?v={vid}", video_id=vid,
                         tier=cast(Tier, tier))  # fmt: skip
    made = ReferenceInventory.from_answer(
        InventoryAnswerV2.model_validate(data), link=link, model="m", fps=5.0,
        usage=Usage(), analysed_on="2026-09-29", styles=styles,
    )  # fmt: skip
    assert isinstance(made, ReferenceInventoryV2)
    return made


def _row(table: InventoryComparison, name: str) -> ComparisonRow:
    found = [r for r in table.rows if r.name == name]
    assert found, [r.name for r in table.rows]
    return found[0]


def test_three_cards_give_the_median_and_range_per_row() -> None:
    cards = [_card("aaaaaaaaaaa", shots=10), _card("bbbbbbbbbbb", shots=20),
             _card("ccccccccccc", shots=30)]  # fmt: skip
    ours = _card("ownownownow", shots=4, duration=6.0, tier="own")
    table = compare_module.compare(ours, cards, style="explainer")
    assert table.references == 3 and table.enough
    shots = _row(table, "shots per 10 s")
    assert (shots.median, shots.low, shots.high) == (3.33, 1.67, 5.0)
    assert shots.ours == 6.67
    assert shots.outside is True  # red: above the references' range
    clip = _row(table, "median clip length (s)")
    assert (clip.median, clip.low, clip.high) == (3.0, 2.0, 6.0)
    assert clip.ours == 1.5 and clip.outside is True
    effects = _row(table, "effects per 10 s")
    assert effects.ours is not None and effects.median is not None
    match = _row(table, "match share (literal + named entity + number)")
    assert match.ours is not None and match.low is not None
    assert _row(table, "layout share: full_footage").ours == 1.0
    assert _row(table, "SFX on a visible event (share)").median is not None
    assert _row(table, "SFX per 10 s: whoosh").ours is not None
    bed = _row(table, "bed present")
    assert bed.ours == "yes" and "3 of 3" in bed.refs
    hook = _row(table, "mood: hook")
    assert hook.ours == "mysterious_curiosity" and hook.plan == "—"
    change = _row(table, "music change")
    assert str(change.ours).startswith("yes")


def test_a_value_inside_the_range_is_not_red() -> None:
    cards = [_card("aaaaaaaaaaa", shots=10), _card("bbbbbbbbbbb", shots=20),
             _card("ccccccccccc", shots=30)]  # fmt: skip
    ours = _card("ownownownow", shots=2, duration=6.0, tier="own")  # 3.33 per 10 s
    shots = _row(compare_module.compare(ours, cards, style="explainer"), "shots per 10 s")
    assert shots.outside is False


def test_a_style_with_one_card_shows_not_enough_references() -> None:
    ours = _card("ownownownow", shots=4, duration=6.0, tier="own")
    table = compare_module.compare(ours, [_card("aaaaaaaaaaa", shots=10)], style="explainer")
    assert table.references == 1 and not table.enough
    assert table.note == "not enough references"
    shots = _row(table, "shots per 10 s")
    assert shots.ours == 6.67 and shots.median is None and shots.outside is False


def test_references_for_reads_the_v2_cards_of_the_style_and_skips_v1_and_other_styles(
    tmp_path: Path,
) -> None:
    for card in (_card("aaaaaaaaaaa", shots=10), _card("bbbbbbbbbbb", shots=20),
                 _card("ddddddddddd", shots=5, styles=("vishva",))):  # fmt: skip
        (tmp_path / f"{card.video_id}.json").write_text(card.model_dump_json(), "utf-8")
    v1 = json.loads((tmp_path / "aaaaaaaaaaa.json").read_text("utf-8"))
    v1["prompt_version"] = "v1"
    for key in ("script", "parts", "music_changes", "beats", "styles"):
        v1.pop(key)
    for effect in v1["effects"]:
        effect.pop("motion")
    v1["sound"]["effects"] = []
    v1["video_id"] = "eeeeeeeeeee"
    (tmp_path / "eeeeeeeeeee.json").write_text(json.dumps(v1), "utf-8")
    found = compare_module.references_for("explainer", tmp_path)
    assert sorted(c.video_id for c in found) == ["aaaaaaaaaaa", "bbbbbbbbbbb"]


# --- the operator's command ----------------------------------------------------------------


def test_the_own_command_runs_the_step_on_a_job_directory_and_prints_the_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    job = _delivered(tmp_path / "data")
    code = cli.main(
        ["own", str(job.path), "--dir", str(_with_references(tmp_path))],
        analyser=FakeAnalyser([_answer_text()]),
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "shots per 10 s" in printed and "OUTSIDE" in printed
    assert isinstance(own.load(job), ReferenceInventoryV2)
    recorded = meta.load(job)
    assert recorded is not None and recorded.inventory is not None
    assert recorded.inventory.status == "analysed"


def test_the_own_command_says_why_when_not_analysed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    job = _delivered(tmp_path)
    code = cli.main(["own", str(job.path)], analyser=FakeAnalyser([AnalyserError("refused")]))
    assert code == 1
    err = capsys.readouterr().err
    assert f"{job.id}: not analysed: " in err and err.rstrip().endswith("refused")


# --- meta.json and the page ----------------------------------------------------------------


def _with_references(tmp_path: Path) -> Path:
    refs = tmp_path / "inventory"
    refs.mkdir()
    for card in (_card("aaaaaaaaaaa", shots=10), _card("bbbbbbbbbbb", shots=20),
                 _card("ccccccccccc", shots=30)):  # fmt: skip
        (refs / f"{card.video_id}.json").write_text(card.model_dump_json(), "utf-8")
    return refs


def test_meta_json_carries_the_comparison_rows(tmp_path: Path) -> None:
    job = _delivered(tmp_path / "data")
    own.SelfInventory(FakeAnalyser([_answer_text()])).run(job)
    recorded = meta.build(job, inventory_dir=_with_references(tmp_path))
    assert recorded.inventory is not None
    assert recorded.inventory.status == "analysed"
    table = recorded.inventory.comparison
    assert table is not None and table.references == 3
    assert _row(table, "shots per 10 s").median == 3.33


def test_meta_json_carries_the_reason_when_not_analysed(tmp_path: Path) -> None:
    job = _delivered(tmp_path)
    own.SelfInventory(FakeAnalyser([AnalyserError("upload refused")])).run(job)
    recorded = meta.build(job)
    assert recorded.inventory is not None
    assert recorded.inventory.status == "not_analysed"
    assert "upload refused" in recorded.inventory.reason
    assert recorded.inventory.comparison is None


def test_meta_json_has_no_inventory_before_the_step_ran(tmp_path: Path) -> None:
    assert meta.build(_delivered(tmp_path)).inventory is None


def test_the_job_page_shows_the_table_with_the_red_rows(tmp_path: Path) -> None:
    job = _delivered(tmp_path / "data")
    own.SelfInventory(FakeAnalyser([_answer_text()])).run(job)
    meta.write(job, inventory_dir=_with_references(tmp_path))
    page = app.render_job_page(jobs.load(job.path))
    assert '<table class="inventory">' in page
    assert "shots per 10 s" in page
    assert 'class="outside"' in page  # the recorded 59.7 s answer has 24 shots: above 5.0


def test_the_job_page_shows_the_reason_when_not_analysed(tmp_path: Path) -> None:
    job = _delivered(tmp_path)
    own.SelfInventory(FakeAnalyser([AnalyserError("upload refused")])).run(job)
    meta.write(job)
    page = app.render_job_page(jobs.load(job.path))
    assert "Not analysed: " in page and "upload refused" in page
