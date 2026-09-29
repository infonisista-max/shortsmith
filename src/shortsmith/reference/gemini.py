"""The reference analyser: Gemini watching the YouTube link (ticket 036; decision 13.1).

`ReferenceAnalyser.analyse(url, prompt) -> Answer` is the seam: `GeminiAnalyser` is one
direct REST call to `REFERENCE_ENDPOINT` (`{model}` filled with `REFERENCE_MODEL`) whose
first part is the video by URL - `fileData.fileUri`, public videos only, nothing
downloaded - sampled at `REFERENCE_FPS` through `videoMetadata.fps`, and whose second
part is the prompt; the answer is asked for as JSON. The reply's text and its
`usageMetadata` (prompt, video, output, thinking and total tokens) come back as `Answer`
so the caller can log every request's tokens. A Qwen-VL adapter slots in behind the same
interface later (the operator's standing cost call); it would need the video file, so it
waits until volume makes the cost matter.

Spike of 27 Sep 2026 on the operator's key: `generateContent` on `gemini-3.8-flash` at
5 fps read a 58 s short for about 20.7k video tokens (about 355 tokens per second of
video), YouTube URL input being at no charge in the preview.

`analyse_file(path, prompt)` (ticket 074) reads a local video instead - our own
`out/short.mp4` - through the Files API: a resumable upload (`start`, then the bytes
with `upload, finalize`), `files.get` polled every `poll_s` until the file is `ACTIVE`
(`FAILED`, or not active within `active_timeout_s`, is an `AnalyserError`), then the same
`generateContent` body with the uploaded URI, so the numbers are comparable with a
reference's; the uploaded file is deleted afterwards whatever happened.

`FakeAnalyser` answers from a list of canned texts or errors and records every call, so
tests and the fixture path never reach the network.
"""

from __future__ import annotations

import math
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from pydantic import BaseModel, SecretStr

from shortsmith.assets.http import field as json_field
from shortsmith.assets.http import items, number
from shortsmith.assets.http import text as json_text

DEFAULT_MODEL = "gemini-3.8-flash"
# 5 fps: one frame every 0.2 s, so a 0.2 s whip lands in at least one sampled frame;
# the default 1 fps would miss four of five such transitions.
DEFAULT_FPS = 5.0
DEFAULT_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
TIMEOUT_S = 600.0  # a 60 s short at 5 fps answered in about a minute in the spike
# 074: the Files API, for a local video; `{name}` is the file's `files/<id>`.
DEFAULT_UPLOAD_ENDPOINT = "https://generativelanguage.googleapis.com/upload/v1beta/files"
DEFAULT_FILE_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/{name}"
VIDEO_MIME = "video/mp4"
POLL_S = 2.0
ACTIVE_TIMEOUT_S = 300.0


class AnalyserError(RuntimeError):
    """The analyser could not answer: an API error (with its HTTP `status`), an
    unreachable host, a reply with no text, or a missing key."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class Usage(BaseModel):
    """The tokens one request used, as the API reported them."""

    prompt_tokens: int = 0
    video_tokens: int = 0
    output_tokens: int = 0
    thoughts_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class Answer:
    text: str
    usage: Usage
    model: str


class ReferenceAnalyser(ABC):
    model: str
    fps: float

    @abstractmethod
    def analyse(self, url: str, prompt: str) -> Answer: ...

    @abstractmethod
    def analyse_file(self, path: Path, prompt: str) -> Answer: ...


@dataclass
class FakeAnalyser(ReferenceAnalyser):
    """Answers each call from `answers` in order (a text, or an `AnalyserError` to
    raise); `calls` records `(url, prompt)` for each, a file by its path."""

    answers: list[str | AnalyserError]
    model: str = "fake-video"
    fps: float = DEFAULT_FPS
    calls: list[tuple[str, str]] = field(default_factory=lambda: [])

    def analyse_file(self, path: Path, prompt: str) -> Answer:
        return self.analyse(str(path), prompt)

    def analyse(self, url: str, prompt: str) -> Answer:
        self.calls.append((url, prompt))
        if not self.answers:
            raise AnalyserError("the fake analyser has no answer left")
        answer = self.answers.pop(0)
        if isinstance(answer, AnalyserError):
            raise answer
        usage = Usage(
            prompt_tokens=1000 + len(prompt) // 4,
            video_tokens=1000,
            output_tokens=len(answer) // 4,
            total_tokens=1000 + len(prompt) // 4 + len(answer) // 4,
        )
        return Answer(answer, usage, self.model)


def request_body(
    url: str, prompt: str, fps: float, *, mime_type: str | None = None
) -> dict[str, object]:
    """The one JSON body: the video by URL at `fps`, the prompt, a JSON answer. An
    uploaded file's URI carries its `mime_type`."""
    data: dict[str, str] = {"fileUri": url}
    if mime_type is not None:
        data["mimeType"] = mime_type
    return {
        "contents": [
            {
                "parts": [
                    {"fileData": data, "videoMetadata": {"fps": fps}},
                    {"text": prompt},
                ]
            }
        ],
        "generationConfig": {"responseMimeType": "application/json"},
    }


def parse_reply(body: object, model: str) -> Answer:
    """The text parts of the first candidate joined, the usage and the model version."""
    texts: list[str] = []
    for candidate in items(body, "candidates"):
        for part in items(json_field(candidate, "content"), "parts"):
            if isinstance(json_field(part, "text"), str):
                texts.append(json_text(json_field(part, "text")))
        break
    if not any(texts):
        raise AnalyserError("the reply carried no text")
    return Answer(
        "".join(texts),
        usage_of(json_field(body, "usageMetadata")),
        json_text(json_field(body, "modelVersion")) or model,
    )


def usage_of(meta: object) -> Usage:
    video = 0
    for detail in items(meta, "promptTokensDetails"):
        if json_text(json_field(detail, "modality")) == "VIDEO":
            video += number(json_field(detail, "tokenCount"))
    return Usage(
        prompt_tokens=number(json_field(meta, "promptTokenCount")),
        video_tokens=video,
        output_tokens=number(json_field(meta, "candidatesTokenCount")),
        thoughts_tokens=number(json_field(meta, "thoughtsTokenCount")),
        total_tokens=number(json_field(meta, "totalTokenCount")),
    )


class GeminiAnalyser(ReferenceAnalyser):
    """One direct REST call per reference (13.1), `{model}` filled into the endpoint."""

    def __init__(
        self,
        *,
        api_key: SecretStr | None,
        model: str = DEFAULT_MODEL,
        fps: float = DEFAULT_FPS,
        endpoint: str = DEFAULT_ENDPOINT,
        client: httpx.Client | None = None,
        timeout_s: float = TIMEOUT_S,
        upload_endpoint: str = DEFAULT_UPLOAD_ENDPOINT,
        file_endpoint: str = DEFAULT_FILE_ENDPOINT,
        poll_s: float = POLL_S,
        active_timeout_s: float = ACTIVE_TIMEOUT_S,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.fps = fps
        self.endpoint = endpoint
        self._client = client
        self._timeout_s = timeout_s
        self.upload_endpoint = upload_endpoint
        self.file_endpoint = file_endpoint
        self._poll_s = poll_s
        self._active_timeout_s = active_timeout_s
        self._sleep = sleep

    def analyse(self, url: str, prompt: str) -> Answer:
        self._need_key()
        with self._session() as client:
            return self._generate(client, request_body(url, prompt, self.fps))

    def analyse_file(self, path: Path, prompt: str) -> Answer:
        """Upload `path`, wait until it is `ACTIVE`, analyse it, delete it (074)."""
        self._need_key()
        with self._session() as client:
            name, uri, state = self._upload(client, path)
            try:
                self._wait_active(client, name, state)
                body = request_body(uri, prompt, self.fps, mime_type=VIDEO_MIME)
                return self._generate(client, body)
            finally:
                self._delete(client, name)

    def _need_key(self) -> None:
        if self._api_key is None:
            raise AnalyserError("the reference tool needs GEMINI_API_KEY in .env")

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self._api_key.get_secret_value() if self._api_key else ""}

    @contextmanager
    def _session(self) -> Generator[httpx.Client]:
        """The injected client, or one owned for the whole exchange; a transport error
        anywhere inside is an `AnalyserError`, never the key."""
        try:
            if self._client is not None:
                yield self._client
            else:
                with httpx.Client(timeout=self._timeout_s) as owned:
                    yield owned
        except httpx.HTTPError as exc:
            raise AnalyserError(f"the analyser could not be reached: {exc}") from None

    def _generate(self, client: httpx.Client, body: Mapping[str, object]) -> Answer:
        url = self.endpoint.format(model=self.model)
        response = client.post(url, json=body, headers=self._headers())
        return parse_reply(_json_of(response, "the analyser"), self.model)

    def _upload(self, client: httpx.Client, path: Path) -> tuple[str, str, str]:
        """The resumable upload: the session, then the bytes; the file's name, URI and
        state as the API answered."""
        data = path.read_bytes()
        start = client.post(
            self.upload_endpoint,
            json={"file": {"display_name": path.name}},
            headers=self._headers() | {
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(len(data)),
                "X-Goog-Upload-Header-Content-Type": VIDEO_MIME,
            },
        )  # fmt: skip
        if start.status_code >= 400:
            _json_of(start, "the upload")  # raises with the API's own words
        session = start.headers.get("x-goog-upload-url")
        if not session:
            raise AnalyserError("the upload answered with no upload URL")
        done = client.post(
            session,
            content=data,
            headers=self._headers() | {
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            },
        )  # fmt: skip
        uploaded = json_field(_json_of(done, "the upload"), "file")
        name, uri = json_text(json_field(uploaded, "name")), json_text(json_field(uploaded, "uri"))
        if not name or not uri:
            raise AnalyserError("the upload answered with no file name or URI")
        return name, uri, json_text(json_field(uploaded, "state"))

    def _wait_active(self, client: httpx.Client, name: str, state: str) -> None:
        polls = max(1, math.ceil(self._active_timeout_s / self._poll_s))
        url = self.file_endpoint.format(name=name)
        for _ in range(polls):
            if state == "ACTIVE":
                return
            if state == "FAILED":
                break
            self._sleep(self._poll_s)
            found = _json_of(client.get(url, headers=self._headers()), "the file poll")
            state = json_text(json_field(found, "state"))
            if state == "FAILED":
                message = json_text(json_field(json_field(found, "error"), "message"))
                raise AnalyserError(f"the uploaded video is FAILED: {message or 'no reason'}")
        if state == "ACTIVE":
            return
        raise AnalyserError(
            f"the uploaded video was not ACTIVE after {self._active_timeout_s:g} s ({state})"
        )

    def _delete(self, client: httpx.Client, name: str) -> None:
        """Best effort: a delete that fails leaves the file to the API's own expiry."""
        with suppress(httpx.HTTPError):
            client.delete(self.file_endpoint.format(name=name), headers=self._headers())


def _json_of(response: httpx.Response, who: str) -> object:
    """The response's JSON; an HTTP error or a body that is not JSON is an
    `AnalyserError` with the status and the API's own words."""
    if response.status_code >= 400:
        raise AnalyserError(
            f"{who} answered {response.status_code}: {_error_text(response)}",
            status=response.status_code,
        )
    try:
        return response.json()
    except ValueError:
        raise AnalyserError(f"{who} did not answer with JSON") from None


def _error_text(response: httpx.Response) -> str:
    """The API's own words from its error body; never the key, never a stack."""
    try:
        body: object = response.json()
    except ValueError:
        return response.text[:500]
    message = json_field(json_field(body, "error"), "message")
    return str(message)[:500] if message is not None else response.text[:500]
