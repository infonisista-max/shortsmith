"""app: upload form -> POST /jobs (2.1 validation, 2.2 layout) -> redirect to the job
page, which shows the 11.1 step list and re-polls the JSON every 3 s. Every user
string is HTML-escaped wherever it is interpolated. Every route but /health sits
behind the 11.2 passcode cookie; `client` is logged in, `anon` is not."""

from __future__ import annotations

import html
import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from shortsmith import app as app_module
from shortsmith import auth, jobs
from shortsmith.config import Settings
from shortsmith.planner import FakePlanner
from shortsmith.transcriber import FakeTranscriber
from tests.conftest import Media
from tests.test_auth import Ticker

GOOD_BRIEF = "Topic: why the sky is blue. Angle: Rayleigh scattering in one breath."
SCRIPT = "<script>alert(1)</script>"
PASSCODE = "test-only-passcode"
T0 = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)


def _settings(tmp_path: Path, passcode: str | None = PASSCODE) -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        shortsmith_data_dir=tmp_path / "data",
        shortsmith_passcode=None if passcode is None else SecretStr(passcode),
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
        planner=FakePlanner(),
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
    assert job.record.style_line == "hitech please"
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


def test_job_page_after_the_worker_ran(client: TestClient, app: FastAPI, media: Media) -> None:
    location = _post(client, media.clip()).headers["location"]
    assert app.state.worker.run_next() is True
    body = client.get(location).text
    assert 'data-step="sourcing" class="step current"' in body
    assert client.get(f"{location}.json").json()["status"] == "sourcing"


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
    """The real worker thread via the lifespan: two uploads, both end at sourcing,
    and the second is still `uploaded` right after submission."""
    app = app_module.create_app(
        _settings(tmp_path), transcriber=FakeTranscriber(), planner=FakePlanner()
    )
    with TestClient(app) as client:
        login(client)
        first = _post(client, media.clip()).headers["location"]
        second = _post(client, media.clip()).headers["location"]
        assert client.get(f"{second}.json").json()["status"] in ("uploaded", "transcribing")
        deadline = time.monotonic() + 20
        statuses: set[str] = set()
        while time.monotonic() < deadline and statuses != {"sourcing"}:
            statuses = {client.get(f"{u}.json").json()["status"] for u in (first, second)}
            time.sleep(0.05)
        assert statuses == {"sourcing"}


def test_module_level_app_exists_for_uvicorn() -> None:
    assert isinstance(app_module.app, FastAPI)


def test_default_planner_from_settings_fails_the_job_visibly_not_silently(
    tmp_path: Path, media: Media
) -> None:
    """`PLANNER=claude_code` (the .env default) is ticket 014: until then a job fails at
    `planning` with the ticket named; nothing pretends the fake is the real planner."""
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        shortsmith_data_dir=tmp_path / "data",
        shortsmith_passcode=SecretStr(PASSCODE),
        planner="claude_code",
    )
    app = app_module.create_app(settings, transcriber=FakeTranscriber(), start_worker=False)
    with TestClient(app) as client:
        login(client)
        location = _post(client, media.clip()).headers["location"]
        assert app.state.worker.run_next() is True
        record = client.get(f"{location}.json").json()
        assert record["status"] == "failed"
        assert record["error"]["step"] == "planning"
        assert "014" in record["error"]["detail"]
        assert "Failed at planning" in client.get(location).text


# --- passcode (ticket 040, decision 11.2) ----------------------------------------


def _guarded_app(
    tmp_path: Path, *, clock: Ticker, delays: list[float], passcode: str | None = PASSCODE
) -> FastAPI:
    async def delay(seconds: float) -> None:
        delays.append(seconds)

    return app_module.create_app(
        _settings(tmp_path, passcode),
        transcriber=FakeTranscriber(),
        planner=FakePlanner(),
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
