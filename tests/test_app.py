"""app: upload form -> POST /jobs (2.1 validation, 2.2 layout) -> redirect to the job
page, which shows the 11.1 step list and re-polls the JSON every 3 s. Every user
string is HTML-escaped wherever it is interpolated. No passcode yet (ticket 040)."""

from __future__ import annotations

import html
import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shortsmith import app as app_module
from shortsmith import jobs
from shortsmith.config import Settings
from shortsmith.transcriber import FakeTranscriber
from tests.conftest import Media

GOOD_BRIEF = "Topic: why the sky is blue. Angle: Rayleigh scattering in one breath."
SCRIPT = "<script>alert(1)</script>"


def _settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, shortsmith_data_dir=tmp_path / "data")  # pyright: ignore[reportCallIssue]


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    return app_module.create_app(
        _settings(tmp_path), transcriber=FakeTranscriber(), start_worker=False
    )


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


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
    assert 'data-step="planning" class="step current"' in body
    assert client.get(f"{location}.json").json()["status"] == "planning"


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
    """The real worker thread via the lifespan: two uploads, both end at planning,
    and the second is still `uploaded` right after submission."""
    app = app_module.create_app(_settings(tmp_path), transcriber=FakeTranscriber())
    with TestClient(app) as client:
        first = _post(client, media.clip()).headers["location"]
        second = _post(client, media.clip()).headers["location"]
        assert client.get(f"{second}.json").json()["status"] in ("uploaded", "transcribing")
        deadline = time.monotonic() + 20
        statuses: set[str] = set()
        while time.monotonic() < deadline and statuses != {"planning"}:
            statuses = {client.get(f"{u}.json").json()["status"] for u in (first, second)}
            time.sleep(0.05)
        assert statuses == {"planning"}


def test_module_level_app_exists_for_uvicorn() -> None:
    assert isinstance(app_module.app, FastAPI)
