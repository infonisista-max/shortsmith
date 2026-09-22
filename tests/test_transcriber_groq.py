"""transcriber.groq: the real transcriber (decisions 6.1, 12.1, 13.1). It extracts the
job's audio with ffmpeg (16 kHz mono MP3 at 64 kbps, research §6), makes one direct
Groq Whisper call with word and segment timestamps, maps `verbose_json` to a
Transcript with per-segment confidence flags, re-runs the tail when the research §6
check fires, applies the fix pass, and records one ledger row per call in audio
minutes. The groq SDK talks to an httpx MockTransport serving the recorded replies in
`tests/fixtures/groq/`; no network, no key."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from shortsmith import ffmpeg, jobs
from shortsmith.config import Settings
from shortsmith.jobs import Job
from shortsmith.ledger import BudgetExceeded, Caps, Ledger, Prices
from shortsmith.transcriber import (
    FakeTranscriber,
    GroqTranscriber,
    TranscriberError,
    from_settings,
)

GROQ = Path(__file__).parent / "fixtures" / "groq"
KEY = "gsk-test-not-real"
PRICES = Prices({"groq": {"audio_minutes": 0.5}})


def _reply(name: str) -> dict[str, Any]:
    return json.loads((GROQ / f"{name}.json").read_text(encoding="utf-8"))


@dataclass
class Part:
    headers: dict[str, str]
    body: bytes


def _multipart(request: httpx.Request) -> dict[str, list[Part]]:
    match = re.search(r"boundary=([^;]+)", request.headers["content-type"])
    assert match is not None
    boundary = b"--" + match.group(1).encode("ascii")
    parts: dict[str, list[Part]] = {}
    for chunk in request.content.split(boundary)[1:-1]:
        head, _, body = chunk.strip(b"\r\n").partition(b"\r\n\r\n")
        headers: dict[str, str] = {}
        for line in head.decode("utf-8").split("\r\n"):
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        name_match = re.search(r'name="([^"]+)"', headers["content-disposition"])
        assert name_match is not None
        parts.setdefault(name_match.group(1), []).append(Part(headers, body))
    return parts


@dataclass
class StubGroq:
    """Serves the queued replies in order and records every request."""

    replies: list[httpx.Response]
    requests: list[httpx.Request] = field(default_factory=lambda: [])

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        return self.replies.pop(0)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def _ok(name: str) -> httpx.Response:
    return httpx.Response(200, json=_reply(name))


@pytest.fixture
def job(tmp_path: Path) -> Job:
    return jobs.create(tmp_path, style="explainer", style_note="explainer")


def _book(hard: float | None = None) -> Ledger:
    return Ledger(PRICES, Caps(per_job=None, hard=hard, per_day=500))


def _transcriber(stub: StubGroq, book: Ledger, **kwargs: Any) -> GroqTranscriber:
    return GroqTranscriber(
        lambda: book, api_key=SecretStr(KEY), http_client=stub.client(), max_retries=0, **kwargs
    )


def test_one_call_per_run_with_the_recorded_request_shape(
    job: Job, fixture_clip: Path
) -> None:
    stub = StubGroq([_ok("main"), _ok("tail")])
    _transcriber(stub, _book()).bind(job).transcribe(fixture_clip)
    expected = _reply("request")
    assert len(stub.requests) == 2  # the main call and the tail re-run
    for request in stub.requests:
        assert request.method == expected["method"]
        assert str(request.url) == expected["url"]
        assert request.headers["authorization"] == f"Bearer {KEY}"
        assert request.headers["accept"] == expected["headers"]["accept"]
        assert request.headers["content-type"].startswith(expected["headers"]["content-type"])
        parts = _multipart(request)
        fields = {
            name: [p.body.decode("utf-8") for p in found]
            for name, found in parts.items()
            if name != expected["file"]["field"]
        }
        assert fields == expected["fields"]
        (upload,) = parts[expected["file"]["field"]]
        assert upload.headers["content-type"] == expected["file"]["content_type"]
    main_upload = _multipart(stub.requests[0])["file"][0]
    assert main_upload.body == (job.work_dir / "asr" / "audio.mp3").read_bytes()
    assert 'filename="audio.mp3"' in main_upload.headers["content-disposition"]
    tail_upload = _multipart(stub.requests[1])["file"][0]
    assert tail_upload.body == (job.work_dir / "asr" / "tail.mp3").read_bytes()


def test_the_audio_sent_is_16_khz_mono_mp3_at_64_kbps(job: Job, fixture_clip: Path) -> None:
    stub = StubGroq([_ok("main"), _ok("tail")])
    _transcriber(stub, _book()).bind(job).transcribe(fixture_clip)
    (stream,) = ffmpeg.probe(job.work_dir / "asr" / "audio.mp3")["streams"]
    assert stream["codec_name"] == "mp3"
    assert stream["sample_rate"] == "16000"
    assert stream["channels"] == 1
    assert int(stream["bit_rate"]) == 64000


def test_the_reply_maps_to_the_fixed_transcript(job: Job, fixture_clip: Path) -> None:
    stub = StubGroq([_ok("main"), _ok("tail")])
    t = _transcriber(stub, _book()).bind(job).transcribe(fixture_clip)
    assert t.language == "hi"
    assert t.duration_s == pytest.approx(6.0, abs=0.1)  # the extracted audio's length
    # Tail words spliced after the main list's last end (4.45 s, cut at 1.0 s); the fix
    # map turned डाइसन into Dyson; the overlap clamp moved "is" to the previous end.
    assert [w.text for w in t.words] == [
        "hello", "there.", "Dyson", "is", "a", "short",
        "about", "nothing", "made", "by", "ffmpeg", "alone.",
    ]  # fmt: skip
    by_text = {w.text: w for w in t.words}
    assert (by_text["is"].start, by_text["is"].end) == (1.34, 1.5)
    assert (by_text["ffmpeg"].start, by_text["ffmpeg"].end) == (5.2, 5.34)
    assert (by_text["alone."].start, by_text["alone."].end) == (5.36, 5.5)
    for a, b in zip(t.words, t.words[1:], strict=False):
        assert b.start >= a.end - 0.05, (a, b)
    # Segment flags: -1.4 is below Whisper's -1.0 log-prob threshold, 0.7 above its
    # 0.6 no-speech threshold; the tail's last segment joins the list.
    assert [(s.start, s.end) for s in t.segments] == [
        (0.2, 0.5), (1.2, 1.5), (2.2, 2.5), (3.2, 3.5), (4.2, 4.45), (5.2, 5.5),
    ]  # fmt: skip
    assert [s.low_confidence for s in t.segments] == [False, False, True, False, False, False]
    assert [s.no_speech for s in t.segments] == [False, False, False, True, False, False]
    assert t.segments[2].avg_logprob == -1.4
    assert [w.segment for w in t.words] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_the_raw_replies_stay_on_disk_and_the_fixes_are_logged(
    job: Job, fixture_clip: Path
) -> None:
    stub = StubGroq([_ok("main"), _ok("tail")])
    _transcriber(stub, _book()).bind(job).transcribe(fixture_clip)
    folder = job.work_dir / "asr"
    assert json.loads((folder / "main.json").read_text(encoding="utf-8")) == _reply("main")
    assert json.loads((folder / "tail.json").read_text(encoding="utf-8")) == _reply("tail")
    log = (job.path / "job.log").read_text(encoding="utf-8")
    assert "tail re-run from 1.0 s" in log
    assert "overlap clamp moved 1 word" in log
    assert "fix map changed 1 word" in log


def test_one_ledger_row_per_call_in_audio_minutes(job: Job, fixture_clip: Path) -> None:
    stub = StubGroq([_ok("main"), _ok("tail")])
    _transcriber(stub, _book()).bind(job).transcribe(fixture_clip)
    rows = jobs.load(job.path).record.cost
    assert [(r.step, r.provider, r.model) for r in rows] == [
        ("transcribing", "groq", "whisper-large-v3"),
        ("transcribing", "groq", "whisper-large-v3"),
    ]
    main_min = ffmpeg.duration_s(job.work_dir / "asr" / "audio.mp3") / 60
    tail_min = ffmpeg.duration_s(job.work_dir / "asr" / "tail.mp3") / 60
    assert rows[0].units == {"audio_minutes": pytest.approx(main_min, abs=1e-4)}
    assert rows[1].units == {"audio_minutes": pytest.approx(tail_min, abs=1e-4)}
    assert rows[0].inr == pytest.approx(main_min * 0.5, abs=1e-4)


def test_no_tail_rerun_when_the_words_reach_the_end(job: Job, fixture_clip: Path) -> None:
    full = _reply("main")
    full["words"].append({"word": " ffmpeg", "start": 5.2, "end": 5.5})
    stub = StubGroq([httpx.Response(200, json=full)])
    t = _transcriber(stub, _book()).bind(job).transcribe(fixture_clip)
    assert len(stub.requests) == 1
    assert t.words[-1].text == "ffmpeg"
    assert len(jobs.load(job.path).record.cost) == 1


def test_auto_language_uses_the_reply_language_and_sends_none(
    job: Job, fixture_clip: Path
) -> None:
    stub = StubGroq([_ok("main"), _ok("tail")])
    t = _transcriber(stub, _book(), language=None).bind(job).transcribe(fixture_clip)
    assert "language" not in _multipart(stub.requests[0])
    assert t.language == "hi"  # "Hindi" in the reply, so the Hindi fix map still applies
    assert "Dyson" in [w.text for w in t.words]


def test_the_hard_cap_stops_before_the_call(job: Job, fixture_clip: Path) -> None:
    stub = StubGroq([_ok("main")])
    with pytest.raises(BudgetExceeded):
        _transcriber(stub, _book(hard=0.01)).bind(job).transcribe(fixture_clip)
    assert stub.requests == []
    assert jobs.load(job.path).record.cost == []


def test_an_http_error_is_a_transcriber_error_without_the_key(
    job: Job, fixture_clip: Path
) -> None:
    stub = StubGroq([httpx.Response(401, json={"error": {"message": "Invalid API Key"}})])
    with pytest.raises(TranscriberError, match="401") as caught:
        _transcriber(stub, _book()).bind(job).transcribe(fixture_clip)
    assert KEY not in str(caught.value)
    assert jobs.load(job.path).record.cost == []  # a refused call is not billed


def test_a_reply_that_is_not_verbose_json_is_a_transcriber_error(
    job: Job, fixture_clip: Path
) -> None:
    stub = StubGroq([httpx.Response(200, json={"text": "no timestamps"})])
    with pytest.raises(TranscriberError, match="words"):
        _transcriber(stub, _book()).bind(job).transcribe(fixture_clip)


def test_an_unbound_transcriber_refuses(fixture_clip: Path) -> None:
    stub = StubGroq([])
    with pytest.raises(TranscriberError, match="bind"):
        _transcriber(stub, _book()).transcribe(fixture_clip)


def test_a_missing_key_is_a_transcriber_error(job: Job, fixture_clip: Path) -> None:
    book = _book()
    transcriber = GroqTranscriber(lambda: book, api_key=None).bind(job)
    with pytest.raises(TranscriberError, match="GROQ_API_KEY"):
        transcriber.transcribe(fixture_clip)


# --- selection ------------------------------------------------------------------------


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)  # pyright: ignore[reportCallIssue]


def test_from_settings_selects_by_transcriber() -> None:
    book = _book()
    assert isinstance(from_settings(_settings(transcriber="fake"), ledger=lambda: book),
                      FakeTranscriber)
    groq = from_settings(
        _settings(transcriber="groq", groq_api_key=KEY, transcriber_language="hi"),
        ledger=lambda: book,
    )
    assert isinstance(groq, GroqTranscriber)
    assert groq.model == "whisper-large-v3"
    assert groq.language == "hi"
    auto = from_settings(_settings(transcriber="groq", transcriber_language=""),
                         ledger=lambda: book)
    assert isinstance(auto, GroqTranscriber)
    assert auto.language is None
