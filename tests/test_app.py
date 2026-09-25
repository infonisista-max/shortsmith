"""app: upload form -> POST /jobs (2.1 validation, 2.2 layout) -> redirect to the job
page, which shows the 11.1 step list and re-polls the JSON every 3 s. Every user
string is HTML-escaped wherever it is interpolated. Every route but /health sits
behind the 11.2 passcode cookie; `client` is logged in, `anon` is not."""

from __future__ import annotations

import asyncio
import html
import json
import shutil
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import IO, Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from shortsmith import app as app_module
from shortsmith import auth, fixture, jobs, render, styles, sweeper
from shortsmith.config import ConfigError, Settings
from shortsmith.contracts import PicturePlan, PlanFeedback, PlanRequest
from shortsmith.ingest import MIB, Limits
from shortsmith.ledger import Caps, Ledger, LedgerError, Prices
from shortsmith.planner import ApiPlanner, ClaudeCodePlanner, FakePlanner
from shortsmith.presenter import FakeFaceDetector
from shortsmith.qa.gate import FakeGate
from shortsmith.render import FakeRenderer
from shortsmith.transcriber import FakeTranscriber, GroqTranscriber
from tests.conftest import Media
from tests.test_auth import Ticker

GOOD_BRIEF = "Topic: why the sky is blue. Angle: Rayleigh scattering in one breath."
SCRIPT = "<script>alert(1)</script>"
PASSCODE = "test-only-passcode"
T0 = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)
# 009: jobs planned by the fake are judged by the fixture-shaped rule set.
SPECS = fixture.smoke_specs(styles.load_all(render.registry()))


EXAMPLE_PRICES = Path(__file__).resolve().parents[1] / "prices.example.yaml"


def _settings(tmp_path: Path, passcode: str | None = PASSCODE, **overrides: Any) -> Settings:
    # The default planner is `claude_code`, which the ledger requires a priced
    # api-equivalent rate for at startup (5.6); the committed example file covers it.
    overrides.setdefault("prices_file", EXAMPLE_PRICES)
    # ...and a declared single operator (11.3), or the server refuses to start.
    overrides.setdefault("shortsmith_single_operator", True)
    # ...and the fake transcriber: `groq` (the default, 012) needs a key at startup.
    overrides.setdefault("transcriber", "fake")
    # ...and the fake relevance judge: `api` (the default, 5.2) needs one too (017).
    overrides.setdefault("relevance_judge", "fake")
    # ...and the fake image source: the default order's `web` is a real HTTP adapter
    # (017), and no test ever reaches the network (board rules).
    overrides.setdefault("asset_sources", "fake")
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        shortsmith_data_dir=tmp_path / "data",
        shortsmith_passcode=None if passcode is None else SecretStr(passcode),
        **overrides,
    )


def login(client: TestClient, passcode: str = PASSCODE, *, next_url: str = "") -> Any:
    data = {"passcode": passcode}
    if next_url:
        data["next"] = next_url
    return client.post("/passcode", data=data, follow_redirects=False)


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    return app_module.create_app(
        _settings(tmp_path),
        transcriber=FakeTranscriber(),
        planner=FakePlanner(), specs=SPECS,
        renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False,
    )


@pytest.fixture
def anon(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(anon: TestClient) -> TestClient:
    assert login(anon).status_code == 303
    return anon


def _files(video: Path, *refs: tuple[str, Path]) -> list[tuple[str, tuple[str, IO[bytes]]]]:
    out: list[tuple[str, tuple[str, IO[bytes]]]] = [("video", (video.name, video.open("rb")))]
    for field, path in refs:
        out.append((field, (path.name, path.open("rb"))))
    return out


def _post(client: TestClient, video: Path, *, brief: str = GOOD_BRIEF, style: str = "explainer",
          refs: list[tuple[str, Path]] | None = None, data: dict[str, str] | None = None) -> Any:
    form = {"brief": brief, "style": style, **(data or {})}
    files = _files(video, *(refs or []))
    try:
        return client.post("/jobs", data=form, files=files, follow_redirects=False)
    finally:
        for _, (_, fh) in files:
            fh.close()


def test_root_shows_the_upload_form(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    body = page.text
    assert 'name="video"' in body and 'name="brief"' in body and 'name="style"' in body
    assert "topic / angle / must-say facts / hook wish" in body
    assert "Sit about an arm and a half from the phone, face in the top third" in body
    for n in range(1, 9):
        assert f'name="ref_{n}"' in body and f'name="caption_{n}"' in body
    assert 'name="ref_9"' not in body
    assert body.count("<button") == 1


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"ok": True}


# --- style chips and live resolution (ticket 008, decisions 1.1, 1.4, 2.1) --------


def test_root_shows_a_chip_per_shipped_style_and_the_live_resolution_hook(
    client: TestClient,
) -> None:
    body = client.get("/").text
    assert 'data-chip="explainer"' in body
    for draft in ("educational", "animated", "hitech"):
        assert f'data-chip="{draft}"' not in body
    assert "/styles/resolve?line=" in body and "data-resolution" in body


def test_styles_resolve_returns_name_note_and_notice(client: TestClient) -> None:
    got = client.get("/styles/resolve", params={"line": "hitech please"})
    assert got.status_code == 200
    assert got.json() == {
        "name": "explainer",
        "note": "hitech please",
        "notice": "hitech not available yet, using explainer",
    }
    assert client.get("/styles/resolve", params={"line": "Explainer, punchy"}).json() == {
        "name": "explainer", "note": "Explainer, punchy", "notice": "",
    }  # fmt: skip
    assert client.get("/styles/resolve").json()["name"] == "explainer"


def test_styles_resolve_needs_the_cookie(anon: TestClient) -> None:
    got = anon.get("/styles/resolve", params={"line": "x"}, headers={"accept": "application/json"})
    assert got.status_code == 401 and got.json() == {"error": "passcode required"}


def test_a_broken_style_spec_stops_the_app_with_a_config_error(tmp_path: Path) -> None:
    broken = tmp_path / "styles"
    shutil.copytree(styles.STYLES_DIR, broken)
    path = broken / "explainer.md"
    path.write_text(path.read_text(encoding="utf-8").replace("\nsound:\n", "\nsounds:\n"), "utf-8")
    with pytest.raises(styles.StyleError, match="explainer.*missing key group 'sound'"):
        app_module.create_app(
            _settings(tmp_path),
            transcriber=FakeTranscriber(),
            planner=FakePlanner(),
            renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
            start_worker=False,
            styles_dir=broken,
        )


def test_accepted_upload_writes_input_and_redirects(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    logo = media.image(width=700, height=900)
    resp = _post(
        client,
        media.clip(),
        style="hitech please",
        refs=[("ref_1", logo)],
        data={"caption_1": "our logo"},
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.startswith("/jobs/")
    job_id = location.rsplit("/", 1)[1]
    job = jobs.find(app.state.data_dir, job_id)
    assert job is not None and job.status == "uploaded"
    assert (job.input_dir / "raw.mov").is_file()
    assert (job.input_dir / "brief.md").read_text(encoding="utf-8") == GOOD_BRIEF
    refs = json.loads((job.input_dir / "refs.json").read_text(encoding="utf-8"))
    assert [r["caption"] for r in refs] == ["our logo"]
    assert refs[0]["rights"] == "owner_supplied"
    # 1.1 / 1.4: resolved server-side and stored on job.json with the note and notice.
    assert job.record.style == "explainer"
    assert job.record.style_note == "hitech please"
    assert job.record.style_notice == "hitech not available yet, using explainer"
    on_disk = json.loads(job.json_path.read_text(encoding="utf-8"))
    assert (on_disk["style"], on_disk["style_note"], on_disk["style_notice"]) == (
        "explainer", "hitech please", "hitech not available yet, using explainer",
    )  # fmt: skip
    page = client.get(location).text
    assert "hitech not available yet, using explainer" in page and "hitech please" in page
    assert app.state.worker.pending() == [job.path]


def _assert_rejected(resp: Any, sentence: str, data_dir: Path) -> None:
    assert resp.status_code == 422
    assert sentence in resp.text
    assert 'name="video"' in resp.text  # the form again
    assert not (data_dir / "jobs").exists() or not any((data_dir / "jobs").iterdir())


def test_brief_39_rejects_40_accepts(client: TestClient, app: FastAPI, media: Media) -> None:
    clip = media.clip()
    _assert_rejected(
        _post(client, clip, brief="x" * 39),
        "The brief must be between 40 and 1500 characters.",
        app.state.data_dir,
    )
    assert _post(client, clip, brief="x" * 40).status_code == 303


def test_duration_19_9_rejects_20_accepts(client: TestClient, app: FastAPI, media: Media) -> None:
    _assert_rejected(
        _post(client, media.clip(duration_s=19.9)),
        "The recording must be between 20 seconds and 8 minutes long.",
        app.state.data_dir,
    )
    assert _post(client, media.clip(duration_s=20.0)).status_code == 303


def test_upscale_1_49_accepts_1_51_rejects(client: TestClient, app: FastAPI, media: Media) -> None:
    ok = media.clip(height=round(1920 / 1.49) // 2 * 2)  # 1288 -> 1.49x
    bad = media.clip(height=round(1920 / 1.51) // 2 * 2)  # 1270 -> 1.51x
    _assert_rejected(_post(client, bad), "record vertical or in 4K", app.state.data_dir)
    assert _post(client, ok).status_code == 303


def test_volume_minus_49_accepts_minus_51_rejects(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    # A sine of amplitude A has mean power 20*log10(A) - 3.01 dB.
    loud_enough = media.clip(amplitude=10 ** ((-49 + 3.01) / 20))
    too_quiet = media.clip(amplitude=10 ** ((-51 + 3.01) / 20))
    _assert_rejected(_post(client, too_quiet), "No speech found", app.state.data_dir)
    assert _post(client, loud_enough).status_code == 303


def test_no_audio_stream_rejects(client: TestClient, app: FastAPI, media: Media) -> None:
    _assert_rejected(
        _post(client, media.clip(audio=False)),
        "one video stream and one audio track",
        app.state.data_dir,
    )


def test_nine_references_reject_eight_accept(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    img = media.image(width=800, height=800)
    nine = [(f"ref_{n}", img) for n in range(1, 10)]
    _assert_rejected(
        _post(client, media.clip(), refs=nine),
        "At most 8 reference files are allowed.",
        app.state.data_dir,
    )
    assert _post(client, media.clip(), refs=nine[:8]).status_code == 303


def test_reference_short_side_599_rejects_600_accepts(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    _assert_rejected(
        _post(client, media.clip(), refs=[("ref_3", media.image(width=599, height=1200))]),
        "must be at least 600 px on its short side",
        app.state.data_dir,
    )
    resp = _post(client, media.clip(), refs=[("ref_3", media.image(width=600, height=1200))])
    assert resp.status_code == 303


def test_missing_video_rejects(client: TestClient, app: FastAPI) -> None:
    resp = client.post("/jobs", data={"brief": GOOD_BRIEF, "style": ""}, follow_redirects=False)
    _assert_rejected(resp, "Please choose a video file to upload.", app.state.data_dir)


def test_landscape_4k_is_accepted_with_the_pip_warning(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    resp = _post(client, media.clip(width=3840, height=2160))
    assert resp.status_code == 303
    page = client.get(resp.headers["location"])
    assert "Vertical works best for PIP" in page.text


def test_job_page_shows_steps_and_polls_json(client: TestClient, media: Media) -> None:
    location = _post(client, media.clip()).headers["location"]
    page = client.get(location)
    assert page.status_code == 200
    body = page.text
    for step in jobs.STATUS_ORDER:
        assert f'data-step="{step}"' in body
    assert 'data-step="uploaded" class="step current"' in body
    assert f'{location}.json' in body and "3000" in body
    assert "elapsed" in body.lower()
    as_json = client.get(f"{location}.json")
    assert as_json.status_code == 200
    assert as_json.json()["status"] == "uploaded"
    assert as_json.json()["id"] == location.rsplit("/", 1)[1]


def test_job_page_after_the_worker_ran_shows_the_delivered_short(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    location = _post(client, media.clip()).headers["location"]
    assert app.state.worker.run_next() is True
    body = client.get(location).text
    assert 'data-step="delivered" class="step current"' in body
    assert client.get(f"{location}.json").json()["status"] == "delivered"
    # 11.1 / 10.4: the short inline, the contact sheet, download links, the check results.
    assert f'<video controls playsinline src="{location}/short.mp4"' in body
    assert f'<img class="sheet" src="{location}/contact.jpg"' in body
    assert f'href="{location}/short.mp4?download=1"' in body
    assert f'href="{location}/contact.jpg?download=1"' in body
    for name in ("T1", "T2", "T3", "T4", "T6", "T8", "T9"):
        assert f'<li class="check pass">{name} pass' in body
    assert "FAIL" not in body


class _StillPlanner(FakePlanner):
    """A planner whose photo beat has no motion, retry or not (4.1: no static still)."""

    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        plan = super().plan_picture(request)
        b03 = plan.beats[2].model_copy(update={"motion": None})
        return plan.model_copy(update={"beats": [*plan.beats[:2], b03, *plan.beats[3:]]})


def test_job_page_lists_the_violations_when_the_planner_was_rejected_twice(
    tmp_path: Path, media: Media
) -> None:
    """8.2: the second rejection fails the job at `planning`; the page shows the list
    with beat id and rule, escaped like every other string."""
    app = app_module.create_app(
        _settings(tmp_path),
        transcriber=FakeTranscriber(),
        planner=_StillPlanner(),
        renderer=FakeRenderer(), gate=FakeGate(), specs=SPECS, detector=FakeFaceDetector(),
        start_worker=False,
    )  # fmt: skip
    with TestClient(app) as client:
        login(client)
        location = _post(client, media.clip()).headers["location"]
        assert app.state.worker.run_next() is True
        record = client.get(f"{location}.json").json()
        assert record["status"] == "failed" and record["error"]["step"] == "planning"
        (line,) = record["error"]["violations"]
        assert line.startswith("b03 (4.1): ")
        body = client.get(location).text
        assert "Failed at planning: We could not plan the short." in body
        assert '<ul class="violations">' in body
        assert f"<li>{html.escape(line)}</li>" in body


def test_delivered_files_are_served_from_out_only(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    location = _post(client, media.clip()).headers["location"]
    assert app.state.worker.run_next() is True
    short = client.get(f"{location}/short.mp4")
    assert short.status_code == 200
    assert short.headers["content-type"].startswith("video/mp4")
    assert "content-disposition" not in short.headers
    download = client.get(f"{location}/short.mp4?download=1")
    assert download.status_code == 200
    job_id = location.rsplit("/", 1)[1]
    assert download.headers["content-disposition"] == f'attachment; filename="{job_id}-short.mp4"'
    sheet = client.get(f"{location}/contact.jpg")
    assert sheet.status_code == 200 and sheet.headers["content-type"].startswith("image/jpeg")
    qa = client.get(f"{location}/qa.json")
    assert qa.status_code == 200
    assert [c["name"] for c in qa.json()["checks"]] == ["T1", "T2", "T3", "T4", "T6", "T8", "T9"]
    # 016: the rights evidence is downloadable beside the short.
    assert client.get(f"{location}/rights.json").headers["content-type"].startswith(
        "application/json"
    )
    assert client.get(f"{location}/credits.md").status_code == 200
    # Only the whitelisted deliverables: never job.json, the inputs or a path trick.
    assert client.get(f"{location}/job.json").status_code == 404
    assert client.get(f"{location}/raw.mov").status_code == 404
    assert client.get(f"{location}/..%2Fjob.json").status_code == 404
    assert client.get("/jobs/20260920-090000-abcdef/short.mp4").status_code == 404


def test_delivered_files_need_the_cookie(client: TestClient, app: FastAPI, media: Media) -> None:
    location = _post(client, media.clip()).headers["location"]
    assert app.state.worker.run_next() is True
    with TestClient(app) as other:
        assert other.get(f"{location}/short.mp4").status_code == 401
        assert other.get(f"{location}/contact.jpg").status_code == 401
        assert other.get(f"{location}/qa.json").status_code == 401


def test_files_are_404_before_the_short_exists(client: TestClient, media: Media) -> None:
    location = _post(client, media.clip()).headers["location"]
    assert client.get(f"{location}/short.mp4").status_code == 404
    assert "<video" not in client.get(location).text


def test_a_failed_check_shows_the_sentence_and_the_check_on_the_page(
    tmp_path: Path, media: Media
) -> None:
    app = app_module.create_app(
        _settings(tmp_path),
        transcriber=FakeTranscriber(),
        planner=FakePlanner(), specs=SPECS,
        renderer=FakeRenderer(), detector=FakeFaceDetector(),
        gate=FakeGate(fail="T3"),
        start_worker=False,
    )
    with TestClient(app) as client:
        login(client)
        location = _post(client, media.clip()).headers["location"]
        assert app.state.worker.run_next() is True
        body = client.get(location).text
        assert "Failed at qa: The short failed a technical check (T3)." in body
        assert 'data-step="qa" class="step failed"' in body
        assert '<li class="check fail">T3 FAIL' in body
        assert "<video" not in body and "contact.jpg" not in body


# --- ticket 043: retry from the failed step (decisions 11.1, 5.6, 9.1) ------------


class _HealingGate(FakeGate):
    """Fails T3 once, the way a flaky step does, and passes from then on."""

    def check(self, job: jobs.Job) -> Any:
        report = super().check(job)
        self.fail = None
        return report


def _retrying_app(tmp_path: Path, **kwargs: Any) -> FastAPI:
    return app_module.create_app(
        _settings(tmp_path, **kwargs),
        transcriber=FakeTranscriber(),
        planner=FakePlanner(), specs=SPECS,
        renderer=FakeRenderer(), detector=FakeFaceDetector(),
        gate=_HealingGate(fail="T3"),
        start_worker=False,
    )


def test_a_failed_job_offers_a_retry_that_re_runs_it_from_its_step(
    tmp_path: Path, media: Media
) -> None:
    """11.1: one button, the step it re-enters at named on it; the second run starts at
    `qa` and the job is delivered without transcribing, planning or sourcing again."""
    app = _retrying_app(tmp_path)
    with TestClient(app) as client:
        login(client)
        location = _post(client, media.clip()).headers["location"]
        assert app.state.worker.run_next() is True
        body = client.get(location).text
        assert f'action="{location}/retry"' in body
        assert "Retry from qa" in body

        resp = client.post(f"{location}/retry", follow_redirects=False)
        assert resp.status_code == 303 and resp.headers["location"] == location
        waiting = client.get(f"{location}.json").json()
        assert waiting["status"] == "uploaded"
        assert waiting["retry_from"] == "qa"
        assert waiting["error"] is None

        assert app.state.worker.run_next() is True
        assert client.get(f"{location}.json").json()["status"] == "delivered"
        page = client.get(location).text
        assert "/retry" not in page  # nothing to retry now
        assert f'<video controls playsinline src="{location}/short.mp4"' in page
        log = (app.state.data_dir / "jobs" / location.rsplit("/", 1)[1] / "job.log").read_text(
            encoding="utf-8"
        )
        assert "failed -> uploaded retry_from=qa" in log and "uploaded -> qa" in log


def test_retrying_a_job_that_did_not_fail_is_refused_and_changes_nothing(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    location = _post(client, media.clip()).headers["location"]
    before = client.get(f"{location}.json").json()
    resp = client.post(f"{location}/retry", follow_redirects=False)
    assert resp.status_code == 409
    assert "did not fail" in resp.text
    assert client.get(f"{location}.json").json() == before
    assert app.state.worker.depth() == 1  # the refused retry took no slot


def test_retrying_an_unknown_job_is_404(client: TestClient) -> None:
    assert client.post("/jobs/20260920-090000-abcdef/retry").status_code == 404
    assert client.post("/jobs/nope/retry").status_code == 404


def test_a_retry_is_refused_when_the_queue_is_full(tmp_path: Path, media: Media) -> None:
    """11.2 / 041: the retry is a queued job like any other, so it waits for a slot and
    the job stays failed until it has one."""
    app = _retrying_app(tmp_path, max_queue=2)
    with TestClient(app) as client:
        login(client)
        location = _post(client, media.clip()).headers["location"]
        assert app.state.worker.run_next() is True
        assert _post(client, media.clip()).status_code == 303
        assert _post(client, media.clip()).status_code == 303

        refused = client.post(f"{location}/retry", follow_redirects=False)
        assert refused.status_code == 503
        assert refused.headers["retry-after"] == "3600"
        assert client.get(f"{location}.json").json()["status"] == "failed"

        assert app.state.worker.run_next() is True
        assert client.post(f"{location}/retry", follow_redirects=False).status_code == 303


def test_a_swept_job_cannot_be_retried(tmp_path: Path, media: Media) -> None:
    """2.2: the retry re-runs a step from the files on disk, and the sweeper has taken
    them; the page says so instead of failing the job a second time."""
    app = _retrying_app(tmp_path)
    with TestClient(app) as client:
        login(client)
        location = _post(client, media.clip()).headers["location"]
        assert app.state.worker.run_next() is True
        job = jobs.find(app.state.data_dir, location.rsplit("/", 1)[1])
        assert job is not None
        jobs.amend(job, swept_at=T0)
        page = client.get(location).text
        assert "/retry" not in page
        resp = client.post(f"{location}/retry", follow_redirects=False)
        assert resp.status_code == 409
        assert client.get(f"{location}.json").json()["status"] == "failed"


def test_unknown_or_malformed_job_id_is_404(client: TestClient) -> None:
    assert client.get("/jobs/20260920-090000-abcdef").status_code == 404
    assert client.get("/jobs/20260920-090000-abcdef.json").status_code == 404
    assert client.get("/jobs/..%2F..%2Fetc").status_code == 404
    assert client.get("/jobs/nope.json").status_code == 404


def test_user_strings_are_escaped_everywhere(client: TestClient, media: Media) -> None:
    escaped = html.escape(SCRIPT)
    # Rejection re-render: the brief is too short, so the form comes back with it.
    resp = _post(client, media.clip(), brief=SCRIPT, style=SCRIPT, data={"caption_1": SCRIPT},
                 refs=[("ref_1", media.image(width=800, height=800))])
    assert resp.status_code == 422
    assert SCRIPT not in resp.text and escaped in resp.text
    assert resp.text.count(escaped) >= 3
    # Job page: brief, style line and caption all appear only escaped.
    brief = SCRIPT + " " + "x" * 40
    resp = _post(client, media.clip(), brief=brief, style=SCRIPT, data={"caption_1": SCRIPT},
                 refs=[("ref_1", media.image(width=800, height=800))])
    assert resp.status_code == 303
    page = client.get(resp.headers["location"]).text
    assert SCRIPT not in page and page.count(escaped) >= 3


def test_second_submission_waits_uploaded_while_the_first_runs(
    tmp_path: Path, media: Media
) -> None:
    """The real worker thread via the lifespan: two uploads, both end `delivered`,
    and the second is still `uploaded` right after submission."""
    app = app_module.create_app(
        _settings(tmp_path),
        transcriber=FakeTranscriber(),
        planner=FakePlanner(), specs=SPECS,
        renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
    )
    with TestClient(app) as client:
        login(client)
        first = _post(client, media.clip()).headers["location"]
        second = _post(client, media.clip()).headers["location"]
        assert client.get(f"{second}.json").json()["status"] in ("uploaded", "transcribing")
        deadline = time.monotonic() + 20
        statuses: set[str] = set()
        while time.monotonic() < deadline and statuses != {"delivered"}:
            statuses = {client.get(f"{u}.json").json()["status"] for u in (first, second)}
            time.sleep(0.05)
        assert statuses == {"delivered"}


def test_module_level_app_exists_for_uvicorn() -> None:
    assert isinstance(app_module.app, FastAPI)


def test_the_api_planner_from_settings_is_never_silently_the_fake(tmp_path: Path) -> None:
    """8.3 / 11.3: `PLANNER=api` builds the paid adapter on the loaded ledger, and
    startup refuses it without a key rather than planning with the fake."""
    keyless = app_module.create_app(
        _settings(tmp_path, planner="api"), transcriber=FakeTranscriber(),
        renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False,
    )  # fmt: skip
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"), TestClient(keyless):
        pass
    prices = tmp_path / "prices.yaml"
    prices.write_text(
        "planner:\n  input_tokens: 0.25\n  cache_write_input_tokens: 0.3125\n"
        "  cache_read_input_tokens: 0.025\n  output_tokens: 1.25\n",
        encoding="utf-8",
    )
    app = app_module.create_app(
        _settings(
            tmp_path, planner="api", prices_file=prices,
            anthropic_api_key=SecretStr("sk-ant-test-not-real"),
        ),
        transcriber=FakeTranscriber(), renderer=FakeRenderer(), gate=FakeGate(),
        detector=FakeFaceDetector(),
        start_worker=False,
    )  # fmt: skip
    with TestClient(app):
        worker_planner = app.state.worker._planner  # pyright: ignore[reportPrivateUsage]
        assert isinstance(worker_planner, ApiPlanner)
        assert worker_planner._ledger() is app.state.ledger  # pyright: ignore[reportPrivateUsage]


def test_the_default_planner_builds_the_cli_adapter_on_the_loaded_ledger(
    tmp_path: Path,
) -> None:
    """8.3: `PLANNER=claude_code` is the CLI adapter; its rows go to the ledger the
    lifespan loads."""
    app = app_module.create_app(
        _settings(tmp_path), transcriber=FakeTranscriber(), renderer=FakeRenderer(),
        gate=FakeGate(), detector=FakeFaceDetector(), start_worker=False,
    )  # fmt: skip
    with TestClient(app):
        worker_planner = app.state.worker._planner  # pyright: ignore[reportPrivateUsage]
        assert isinstance(worker_planner, ClaudeCodePlanner)
        assert worker_planner._ledger() is app.state.ledger  # pyright: ignore[reportPrivateUsage]


def test_transcriber_follows_the_settings_on_the_loaded_ledger(tmp_path: Path) -> None:
    """012: `TRANSCRIBER=groq` builds the Groq adapter, whose rows go to the ledger the
    lifespan loads; `fake` the fake."""
    settings = _settings(tmp_path, transcriber="groq", groq_api_key=SecretStr("gsk-test"))
    app = app_module.create_app(
        settings, planner=FakePlanner(), renderer=FakeRenderer(), gate=FakeGate(),
        detector=FakeFaceDetector(),
        start_worker=False,
    )  # fmt: skip
    with TestClient(app):
        worker_transcriber = app.state.worker._transcriber  # pyright: ignore[reportPrivateUsage]
        assert isinstance(worker_transcriber, GroqTranscriber)
        assert worker_transcriber._ledger() is app.state.ledger  # pyright: ignore[reportPrivateUsage]
    fake = app_module.create_app(
        _settings(tmp_path), planner=FakePlanner(), renderer=FakeRenderer(), gate=FakeGate(),
        detector=FakeFaceDetector(),
        start_worker=False,
    )  # fmt: skip
    assert isinstance(fake.state.worker._transcriber, FakeTranscriber)  # pyright: ignore[reportPrivateUsage]


def test_startup_refuses_the_groq_transcriber_without_a_key(tmp_path: Path) -> None:
    app = app_module.create_app(
        _settings(tmp_path, transcriber="groq"), planner=FakePlanner(),
        renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False,
    )  # fmt: skip
    with pytest.raises(ConfigError, match="GROQ_API_KEY"), TestClient(app):
        pass


def test_startup_refuses_the_subscription_planner_without_a_single_operator(
    tmp_path: Path,
) -> None:
    """11.3: subscription use is single-operator only, enforced when the server starts."""
    settings = _settings(tmp_path, shortsmith_single_operator=False)
    app = app_module.create_app(
        settings, transcriber=FakeTranscriber(), planner=FakePlanner(),
        renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False,
    )  # fmt: skip
    with pytest.raises(ConfigError, match="SHORTSMITH_SINGLE_OPERATOR"), TestClient(app):
        pass


# --- queue, day limit, job minutes, upload size (ticket 041, decision 11.2) ------


def _job_dirs(app: FastAPI) -> list[Path]:
    root = app.state.data_dir / "jobs"
    return sorted(root.iterdir()) if root.is_dir() else []


def test_fourth_submission_is_refused_with_try_in_an_hour(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    clip = media.clip()
    for _ in range(3):
        assert _post(client, clip).status_code == 303
    refused = _post(client, clip)
    assert refused.status_code == 503
    assert "try in an hour" in refused.text
    assert refused.headers["retry-after"] == "3600"
    assert len(_job_dirs(app)) == 3
    assert app.state.worker.depth() == 3  # the refused upload held no slot
    assert app.state.worker.run_next() is True
    assert _post(client, clip).status_code == 303


def test_waiting_job_page_shows_its_position_and_it_moves_as_jobs_finish(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    clip = media.clip()
    first, second, third = (_post(client, clip).headers["location"] for _ in range(3))
    assert "queued, position 1" in client.get(first).text
    assert "queued, position 3" in client.get(third).text
    assert client.get(f"{third}.json").json()["queue_position"] == 3
    assert app.state.worker.run_next() is True
    assert "queued, position 2" in client.get(third).text
    assert client.get(f"{third}.json").json()["queue_position"] == 2
    assert "queued" not in client.get(first).text
    assert client.get(f"{first}.json").json()["queue_position"] is None
    assert "queued, position 1" in client.get(second).text


def test_day_limit_closes_the_form_until_midnight_ist(tmp_path: Path, media: Media) -> None:
    clock = Ticker(T0)  # 12:00 UTC = 17:30 IST
    app = app_module.create_app(
        _settings(tmp_path, max_jobs_per_day=2),
        transcriber=FakeTranscriber(),
        planner=FakePlanner(), specs=SPECS,
        renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False,
        clock=clock,
    )
    with TestClient(app) as client:
        login(client)
        clip = media.clip()
        assert _post(client, clip).status_code == 303
        assert 'name="video"' in client.get("/").text
        assert _post(client, clip).status_code == 303
        closed = client.get("/")
        assert closed.status_code == 200
        assert 'name="video"' not in closed.text and "<form" not in closed.text
        assert "limit of 2 shorts" in closed.text and "midnight IST" in closed.text
        refused = _post(client, clip)
        assert refused.status_code == 503 and "midnight IST" in refused.text
        assert len(_job_dirs(app)) == 2
        clock.now = datetime(2026, 9, 21, 18, 29, 59, tzinfo=UTC)  # 23:59:59 IST
        assert 'name="video"' not in client.get("/").text
        clock.now = datetime(2026, 9, 21, 18, 30, 0, tzinfo=UTC)  # 00:00:00 IST next day
        assert 'name="video"' in client.get("/").text
        assert _post(client, clip).status_code == 303
        assert app.state.worker.depth() == 3


def test_max_job_minutes_reaches_the_worker_from_settings(tmp_path: Path) -> None:
    app = app_module.create_app(
        _settings(tmp_path, max_job_minutes=7, max_queue=2),
        transcriber=FakeTranscriber(),
        planner=FakePlanner(), specs=SPECS,
        renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False,
    )
    worker = app.state.worker
    assert worker._max_job_minutes == 7  # pyright: ignore[reportPrivateUsage]
    assert worker._max_queue == 2  # pyright: ignore[reportPrivateUsage]


SMALL = Limits(max_upload_bytes=MIB, max_reference_bytes=MIB // 8)


def _small_limits_app(tmp_path: Path) -> FastAPI:
    return app_module.create_app(
        _settings(tmp_path),
        transcriber=FakeTranscriber(),
        planner=FakePlanner(), specs=SPECS,
        renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        limits=SMALL,
        start_worker=False,
    )


def test_upload_past_the_limit_is_refused_mid_stream_before_any_probe(tmp_path: Path) -> None:
    """A 4 MB body against a 1 MB video limit: 413 with the form, no job directory, no
    ffprobe (the bytes are not a video), and the queue slot released."""
    app = _small_limits_app(tmp_path)
    big = tmp_path / "big.mp4"
    big.write_bytes(b"\0" * (4 * MIB))
    with TestClient(app) as client:
        login(client)
        resp = _post(client, big)
        assert resp.status_code == 413
        assert "The recording must be 1 MB or smaller." in resp.text
        assert 'name="video"' in resp.text
        assert _job_dirs(app) == []
        assert app.state.worker.depth() == 0


def test_content_length_past_the_limit_is_refused_before_the_body(tmp_path: Path) -> None:
    app = _small_limits_app(tmp_path)
    with TestClient(app) as client:
        login(client)
        resp = client.post(
            "/jobs",
            data={"brief": GOOD_BRIEF, "style": "explainer"},
            files=[("video", ("tiny.mp4", b"\0" * 16))],
            headers={"content-length": str(50 * MIB)},
            follow_redirects=False,
        )
        assert resp.status_code == 413
        assert "The recording must be 1 MB or smaller." in resp.text
        assert app.state.worker.depth() == 0


def test_limited_receive_stops_reading_once_the_limit_is_crossed() -> None:
    """The limiter raises on the chunk that crosses the limit and never asks the
    server for the chunks after it, so an oversized body is not buffered anywhere."""
    chunks = [b"x" * 1024] * 8
    pulled: list[int] = []

    async def receive() -> dict[str, Any]:
        pulled.append(len(pulled))
        body = chunks[len(pulled) - 1]
        return {"type": "http.request", "body": body, "more_body": len(pulled) < len(chunks)}

    limited = app_module.limited_receive(receive, limit=2560)

    async def drain() -> None:
        while True:
            message = await limited()
            if not message.get("more_body"):
                return

    with pytest.raises(app_module.BodyTooLarge):
        asyncio.run(drain())
    assert pulled == [0, 1, 2]


# --- passcode (ticket 040, decision 11.2) ----------------------------------------


def _guarded_app(
    tmp_path: Path, *, clock: Ticker, delays: list[float], passcode: str | None = PASSCODE
) -> FastAPI:
    async def delay(seconds: float) -> None:
        delays.append(seconds)

    return app_module.create_app(
        _settings(tmp_path, passcode),
        transcriber=FakeTranscriber(),
        planner=FakePlanner(), specs=SPECS,
        renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False,
        clock=clock,
        delay=delay,
    )


def test_root_without_a_cookie_shows_the_passcode_form_not_the_upload_form(
    anon: TestClient,
) -> None:
    page = anon.get("/")
    assert page.status_code == 200
    assert 'name="passcode"' in page.text and 'action="/passcode"' in page.text
    assert 'name="video"' not in page.text
    assert "set-cookie" not in page.headers


def test_correct_passcode_sets_a_signed_httponly_cookie_and_redirects_to_the_form(
    anon: TestClient,
) -> None:
    resp = login(anon)
    assert resp.status_code == 303 and resp.headers["location"] == "/"
    cookie = resp.headers["set-cookie"].lower()
    assert f"{auth.COOKIE_NAME}=" in cookie
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert f"max-age={7 * 24 * 3600}" in cookie
    value = anon.cookies[auth.COOKIE_NAME]
    assert auth.verify_cookie(value, PASSCODE, now=datetime.now(UTC))
    assert PASSCODE not in value
    assert 'name="video"' in anon.get("/").text


def test_every_route_but_health_needs_the_cookie(
    anon: TestClient, app: FastAPI, media: Media
) -> None:
    assert anon.get("/health").json() == {"ok": True}
    # HTML routes get the passcode form with 401; JSON gets 401 JSON. Nothing leaks.
    page = anon.get("/jobs/20260920-090000-abcdef")
    assert page.status_code == 401 and 'name="passcode"' in page.text
    as_json = anon.get("/jobs/20260920-090000-abcdef.json")
    assert as_json.status_code == 401 and as_json.json() == {"error": "passcode required"}
    assert anon.get("/jobs/x.json", headers={"accept": "text/html"}).status_code == 401
    assert _post(anon, media.clip()).status_code == 401
    assert not any((app.state.data_dir / "jobs").iterdir())


def test_a_shared_job_link_lands_on_the_job_after_the_passcode(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    location = _post(client, media.clip()).headers["location"]
    with TestClient(app) as other:
        page = other.get(location)
        assert page.status_code == 401
        assert f'name="next" value="{location}"' in page.text
        resp = login(other, next_url=location)
        assert resp.status_code == 303 and resp.headers["location"] == location
        assert other.get(location).status_code == 200
        assert other.get(f"{location}.json").json()["status"] == "uploaded"


def test_next_only_accepts_a_local_path(anon: TestClient) -> None:
    for evil in ("https://evil.example/", "//evil.example/x", "javascript:alert(1)", "jobs/x"):
        resp = login(anon, next_url=evil)
        assert resp.status_code == 303 and resp.headers["location"] == "/"


def test_wrong_passcode_delays_two_seconds_and_counts(tmp_path: Path) -> None:
    clock, delays = Ticker(T0), list[float]()
    with TestClient(_guarded_app(tmp_path, clock=clock, delays=delays)) as anon:
        resp = login(anon, "nope")
        assert resp.status_code == 401
        assert "Wrong passcode" in resp.text and 'name="passcode"' in resp.text
        assert "set-cookie" not in resp.headers
        assert delays == [2.0]
        assert 'name="video"' not in anon.get("/").text
        assert anon.get("/").status_code == 200


def test_eleventh_failure_in_ten_minutes_is_blocked_for_an_hour(tmp_path: Path) -> None:
    clock, delays = Ticker(T0), list[float]()
    with TestClient(_guarded_app(tmp_path, clock=clock, delays=delays)) as anon:
        for _ in range(10):
            assert login(anon, "nope").status_code == 401
            clock.advance(seconds=30)
        assert delays == [2.0] * 10
        # The tenth failure (at 4.5 min) started the hour; 30 s later 59.5 min remain.
        blocked = login(anon, "nope")
        assert blocked.status_code == 429
        assert "Too many wrong passcodes" in blocked.text and "60 minutes" in blocked.text
        assert delays == [2.0] * 10  # a blocked attempt is refused, not delayed
        # The right passcode is refused too while the block lasts.
        assert login(anon).status_code == 429
        assert auth.COOKIE_NAME not in anon.cookies
        clock.advance(minutes=30)
        assert "30 minutes" in login(anon).text
        clock.advance(minutes=29, seconds=30)
        assert login(anon).status_code == 303
        assert anon.get("/").status_code == 200 and 'name="video"' in anon.get("/").text


def test_failures_are_counted_per_ip(tmp_path: Path) -> None:
    clock, delays = Ticker(T0), list[float]()
    app = _guarded_app(tmp_path, clock=clock, delays=delays)
    with (
        TestClient(app, client=("10.0.0.1", 5000)) as first,
        TestClient(app, client=("10.0.0.2", 5000)) as second,
    ):
        for _ in range(10):
            login(first, "nope")
        assert login(first, "nope").status_code == 429
        assert login(second, "nope").status_code == 401
        assert login(second).status_code == 303


def test_rotating_the_passcode_logs_everyone_out(tmp_path: Path) -> None:
    clock, delays = Ticker(T0), list[float]()
    with TestClient(_guarded_app(tmp_path, clock=clock, delays=delays)) as anon:
        anon.cookies.set(auth.COOKIE_NAME, auth.issue_cookie("the-old-passcode", now=T0))
        page = anon.get("/")
        assert 'name="passcode"' in page.text and 'name="video"' not in page.text
        assert anon.get("/jobs/x.json").status_code == 401
        # A cookie signed with the current passcode but older than 7 days is out too.
        anon.cookies.set(auth.COOKIE_NAME, auth.issue_cookie(PASSCODE, now=T0))
        assert 'name="video"' in anon.get("/").text
        clock.advance(days=7, seconds=1)
        assert 'name="video"' not in anon.get("/").text


@pytest.mark.parametrize("passcode", [None, ""])
def test_startup_refuses_to_run_without_a_passcode(tmp_path: Path, passcode: str | None) -> None:
    app = _guarded_app(tmp_path, clock=Ticker(T0), delays=list[float](), passcode=passcode)
    with pytest.raises(RuntimeError, match="SHORTSMITH_PASSCODE"), TestClient(app):
        pass


def test_passcode_form_escapes_next(anon: TestClient) -> None:
    page = anon.get("/jobs/" + SCRIPT)
    assert page.status_code == 401
    assert SCRIPT not in page.text and html.escape(SCRIPT) in page.text


def test_job_page_shows_the_ledger_rows_and_the_cash_total(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    location = _post(client, media.clip()).headers["location"]
    job = jobs.find(app.state.data_dir, location.rsplit("/", 1)[1])
    assert job is not None
    book = Ledger(
        Prices({"groq": {"audio_minutes": 0.5}, "api_equivalent": {"input_tokens": 0.25}}),
        Caps(per_job=1.0, hard=None, per_day=500),
    )
    book.record(job, "transcribing", "groq", "whisper-large-v3", {"audio_minutes": 3})  # 1.5
    book.record(job, "planning", "claude_code", "cli", {"input_tokens": 4000})  # tokens only
    body = client.get(location).text
    assert 'class="ledger"' in body
    assert "whisper-large-v3" in body and "claude_code" in body
    assert "audio_minutes 3" in body
    assert "INR 1.50" in body  # the cash total; tokens never enter it
    assert "4000 tokens" in body and "INR 1.00" in body  # api-equivalent value, display only
    assert "over the soft cap" in body


def test_job_page_without_rows_shows_no_ledger(client: TestClient, media: Media) -> None:
    location = _post(client, media.clip()).headers["location"]
    assert 'class="ledger"' not in client.get(location).text


def test_job_page_cost_table_has_one_row_per_step_and_a_total_row(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    """044: per step, cash beside the tokens and their api-equivalent value; one total."""
    location = _post(client, media.clip()).headers["location"]
    job = jobs.find(app.state.data_dir, location.rsplit("/", 1)[1])
    assert job is not None
    book = Ledger(
        Prices({"groq": {"audio_minutes": 0.5}, "api_equivalent": {"input_tokens": 0.25}}),
        Caps(per_job=None, hard=None, per_day=500),
    )
    book.record(job, "transcribing", "groq", "w", {"audio_minutes": 2})  # 1.00
    book.record(job, "transcribing", "groq", "w", {"audio_minutes": 1})  # 0.50
    book.record(job, "planning", "claude_code", "cli", {"input_tokens": 4000})  # 1.00 equiv
    body = client.get(location).text
    table = body.split('<table class="ledger">', 1)[1].split("</table>", 1)[0]
    assert table.count('<tr data-step="transcribing">') == 1
    assert table.count('<tr data-step="planning">') == 1
    step_row = table.split('<tr data-step="transcribing">', 1)[1].split("</tr>", 1)[0]
    assert "INR 1.50" in step_row
    planning_row = table.split('<tr data-step="planning">', 1)[1].split("</tr>", 1)[0]
    assert "4000 tokens" in planning_row and "INR 1.00" in planning_row
    total = table.split('<tr class="total">', 1)[1].split("</tr>", 1)[0]
    assert "INR 1.50" in total and "4000 tokens" in total and "INR 1.00" in total
    assert "over the soft cap" not in body


def test_job_page_shows_the_running_average_per_passing_short(
    client: TestClient, app: FastAPI, media: Media
) -> None:
    location = _post(client, media.clip()).headers["location"]
    assert "per passing short" not in client.get(location).text  # nothing has passed yet
    passed = jobs.create(app.state.data_dir, now=lambda: T0)
    for step in (*jobs.STATUS_ORDER[1:], "passed"):
        passed = jobs.transition(passed, step, now=lambda: T0)  # type: ignore[arg-type]
    book = Ledger(Prices({"groq": {"audio_minutes": 0.5}}), Caps(None, None, 500))
    book.record(passed, "transcribing", "groq", "w", {"audio_minutes": 5})  # 2.50
    body = client.get(location).text  # a fake-only job: no table, but the average
    assert 'class="ledger"' not in body
    assert "INR 2.50 per passing short" in body and "over 1 passed" in body


def test_daily_budget_closes_the_form_until_midnight_ist(tmp_path: Path, media: Media) -> None:
    """044: `cash_spent_today` at `BUDGET_INR_PER_DAY` closes the form; 00:01 IST opens it."""
    clock = Ticker(T0)  # 17:30 IST
    book = Ledger(Prices({"groq": {"audio_minutes": 0.5}}), Caps(None, None, 1.0), clock=clock)
    app = app_module.create_app(
        _settings(tmp_path),
        transcriber=FakeTranscriber(),
        planner=FakePlanner(), specs=SPECS,
        renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False, clock=clock, book=book,
    )  # fmt: skip
    with TestClient(app) as client:
        login(client)
        clip = media.clip()
        location = _post(client, clip).headers["location"]
        job = jobs.find(app.state.data_dir, location.rsplit("/", 1)[1])
        assert job is not None
        book.record(job, "transcribing", "groq", "w", {"audio_minutes": 2})  # INR 1.00
        closed = client.get("/")
        assert closed.status_code == 200
        assert 'name="video"' not in closed.text and "<form" not in closed.text
        assert "daily budget reached" in closed.text.lower() and "midnight IST" in closed.text
        refused = _post(client, clip)
        assert refused.status_code == 503 and "daily budget reached" in refused.text.lower()
        assert refused.headers["retry-after"] == str(6 * 3600 + 30 * 60)  # to midnight IST
        assert len(_job_dirs(app)) == 1 and app.state.worker.depth() == 1
        clock.now = datetime(2026, 9, 21, 18, 29, 0, tzinfo=UTC)  # 23:59 IST
        assert "daily budget reached" in client.get("/").text.lower()
        clock.now = datetime(2026, 9, 21, 18, 31, 0, tzinfo=UTC)  # 00:01 IST next day
        assert 'name="video"' in client.get("/").text
        assert _post(client, clip).status_code == 303


def test_startup_refuses_to_run_when_a_paid_provider_has_no_price(tmp_path: Path) -> None:
    """5.6: the prices file is checked at startup, in the lifespan like the passcode,
    so importing the module never needs it and the server stops with the gap named."""
    settings = _settings(
        tmp_path,
        planner="api",
        anthropic_api_key="sk-ant-test-not-real",  # noqa: S106 - test value
        prices_file=tmp_path / "prices.yaml",
    )
    app = app_module.create_app(
        settings, transcriber=FakeTranscriber(), planner=FakePlanner(),
        renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False,
    )  # fmt: skip
    with pytest.raises(LedgerError, match="prices.example.yaml"), TestClient(app):
        pass
    (tmp_path / "prices.yaml").write_text(
        "planner:\n  input_tokens: 0.25\n  cache_write_input_tokens: 0.3125\n"
        "  cache_read_input_tokens: 0.025\n  output_tokens: 1.25\n",
        encoding="utf-8",
    )
    with TestClient(app) as client:
        assert client.get("/health").json() == {"ok": True}
        assert app.state.ledger.prices.rate("planner", "output_tokens") == 1.25


# --- the sweeper and the disk guard (ticket 042, decisions 2.2, 11.2) ------------


def _old_job(app: FastAPI, *, created: datetime) -> Path:
    """A `delivered` job of the given age, with a file in every directory."""
    job = jobs.create(app.state.data_dir, now=lambda: created)
    for name in ("input", "work", "out"):
        (job.path / name / f"{name}.txt").write_text(name, encoding="utf-8")
    for step in jobs.STATUS_ORDER[1:]:
        job = jobs.transition(job, step, now=lambda: created)
    return job.path


def _sweeper_app(tmp_path: Path, free: list[int], **kwargs: Any) -> FastAPI:
    return app_module.create_app(
        _settings(tmp_path),
        transcriber=FakeTranscriber(),
        planner=FakePlanner(), specs=SPECS,
        renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False,
        clock=Ticker(T0),
        free_disk=lambda _: free[0],
        **kwargs,
    )  # fmt: skip


def test_low_disk_closes_the_form_and_sweeps_at_once(tmp_path: Path, media: Media) -> None:
    free = [sweeper.MIN_FREE_BYTES - 1]
    app = _sweeper_app(tmp_path, free, start_sweeper=False)
    job_dir = _old_job(app, created=T0 - timedelta(days=2))
    with TestClient(app) as client:
        login(client)
        closed = client.get("/")
        assert closed.status_code == 200
        assert 'name="video"' not in closed.text and "<form" not in closed.text
        assert "not enough disk" in closed.text.lower()
        # 11.2: the refusal runs the sweeper at once.
        assert not (job_dir / "input").exists() and not (job_dir / "work").exists()
        assert (job_dir / "out" / "out.txt").is_file()
        refused = _post(client, media.clip())
        assert refused.status_code == 503
        assert "not enough disk" in refused.text.lower()
        assert refused.headers["retry-after"] == str(sweeper.INTERVAL_S)
        assert _job_dirs(app) == [job_dir]
        assert app.state.worker.depth() == 0  # the refused upload held no slot
        free[0] = sweeper.MIN_FREE_BYTES
        assert 'name="video"' in client.get("/").text
        assert _post(client, media.clip()).status_code == 303


def test_the_background_task_sweeps_every_interval(tmp_path: Path) -> None:
    app = _sweeper_app(tmp_path, [sweeper.MIN_FREE_BYTES], sweep_interval_s=0.01)
    job_dir = _old_job(app, created=T0 - timedelta(days=2))
    with TestClient(app):
        deadline = time.monotonic() + 10
        while (job_dir / "work").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
    assert not (job_dir / "work").exists()
    assert (job_dir / "out" / "out.txt").is_file()


def test_a_swept_job_page_says_where_the_recording_went(tmp_path: Path) -> None:
    app = _sweeper_app(tmp_path, [sweeper.MIN_FREE_BYTES], start_sweeper=False)
    job_dir = _old_job(app, created=T0 - timedelta(days=2))
    with TestClient(app) as client:
        login(client)
        page = client.get(f"/jobs/{job_dir.name}")
        assert "deleted 24 hours after upload" not in page.text
        assert sweeper.sweep(app.state.data_dir, now=Ticker(T0))
        swept = client.get(f"/jobs/{job_dir.name}").text
        assert "deleted 24 hours after upload" in swept
        assert "stay for 7 days" in swept


def _list_rows(body: str) -> list[str]:
    return [row.split('"', 1)[0] for row in body.split('<tr data-job="')[1:]]


def test_job_list_shows_the_last_fifty_newest_first(tmp_path: Path) -> None:
    """045, 11.1: sixty jobs on disk, fifty rows, newest first, each linking its page."""
    app = _sweeper_app(tmp_path, [sweeper.MIN_FREE_BYTES], start_sweeper=False)
    made = [
        jobs.create(app.state.data_dir, now=lambda n=n: T0 - timedelta(minutes=n)).id
        for n in range(60)
    ]
    with TestClient(app) as client:
        login(client)
        page = client.get("/jobs")
        assert page.status_code == 200
        assert _list_rows(page.text) == made[:50]
        assert f'href="/jobs/{made[0]}"' in page.text
        assert made[50] not in page.text
        assert 'href="/jobs"' in client.get("/").text
        assert 'href="/jobs"' in client.get(f"/jobs/{made[0]}").text


def test_job_list_shows_status_cost_time_and_retention(tmp_path: Path) -> None:
    """045: status, cash cost (never tokens), elapsed for a running job and the finish
    time for a settled one; past 24 h "inputs swept", past 7 days absent."""
    app = _sweeper_app(tmp_path, [sweeper.MIN_FREE_BYTES], start_sweeper=False)
    data_dir = app.state.data_dir
    running = jobs.create(data_dir, now=lambda: T0 - timedelta(minutes=3, seconds=5))
    running = jobs.transition(running, "transcribing", now=lambda: T0)
    book = Ledger(Prices({"groq": {"audio_minutes": 0.5}}), Caps(None, None, 500))
    book.record(running, "transcribing", "groq", "w", {"audio_minutes": 3})  # INR 1.50
    day_old = _old_job(app, created=T0 - timedelta(days=2))
    week_old = _old_job(app, created=T0 - timedelta(days=8))
    with TestClient(app) as client:
        login(client)
        body = client.get("/jobs").text
    rows = dict(zip(_list_rows(body), body.split('<tr data-job="')[1:], strict=True))
    assert week_old.name not in rows
    live = rows[running.id]
    assert "transcribing" in live and "INR 1.50" in live and "3m 5s" in live
    assert "inputs swept" not in live
    old = rows[day_old.name]
    assert "delivered" in old and "inputs swept" in old
    assert "19 Sep 17:30 IST" in old  # finished: updated_at, shown in IST


def test_job_list_shows_the_running_average_and_needs_the_cookie(
    client: TestClient, anon: TestClient, app: FastAPI
) -> None:
    assert "per passing short" not in client.get("/jobs").text
    passed = jobs.create(app.state.data_dir, now=lambda: T0)
    for step in (*jobs.STATUS_ORDER[1:], "passed"):
        passed = jobs.transition(passed, step, now=lambda: T0)  # type: ignore[arg-type]
    book = Ledger(Prices({"groq": {"audio_minutes": 0.5}}), Caps(None, None, 500))
    book.record(passed, "transcribing", "groq", "w", {"audio_minutes": 5})  # 2.50
    assert "INR 2.50 per passing short" in client.get("/jobs").text
    anon.cookies.clear()
    refused = anon.get("/jobs")
    assert refused.status_code == 401 and 'name="passcode"' in refused.text


def test_without_the_background_task_nothing_is_swept(tmp_path: Path) -> None:
    app = _sweeper_app(tmp_path, [sweeper.MIN_FREE_BYTES], start_sweeper=False)
    job_dir = _old_job(app, created=T0 - timedelta(days=2))
    with TestClient(app) as client:
        login(client)
        assert 'name="video"' in client.get("/").text
        assert (job_dir / "work" / "work.txt").is_file()
