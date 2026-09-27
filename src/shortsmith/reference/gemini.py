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

`FakeAnalyser` answers from a list of canned texts or errors and records every call, so
tests and the fixture path never reach the network.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field

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


@dataclass
class FakeAnalyser(ReferenceAnalyser):
    """Answers each call from `answers` in order (a text, or an `AnalyserError` to
    raise); `calls` records `(url, prompt)` for each."""

    answers: list[str | AnalyserError]
    model: str = "fake-video"
    fps: float = DEFAULT_FPS
    calls: list[tuple[str, str]] = field(default_factory=lambda: [])

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


def request_body(url: str, prompt: str, fps: float) -> dict[str, object]:
    """The one JSON body: the video by URL at `fps`, the prompt, a JSON answer."""
    return {
        "contents": [
            {
                "parts": [
                    {"fileData": {"fileUri": url}, "videoMetadata": {"fps": fps}},
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
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.fps = fps
        self.endpoint = endpoint
        self._client = client
        self._timeout_s = timeout_s

    def analyse(self, url: str, prompt: str) -> Answer:
        if self._api_key is None:
            raise AnalyserError("the reference tool needs GEMINI_API_KEY in .env")
        response = self._post(request_body(url, prompt, self.fps))
        if response.status_code >= 400:
            raise AnalyserError(
                f"the analyser answered {response.status_code}: {_error_text(response)}",
                status=response.status_code,
            )
        try:
            body: object = response.json()
        except ValueError:
            raise AnalyserError("the analyser did not answer with JSON") from None
        return parse_reply(body, self.model)

    def _post(self, body: Mapping[str, object]) -> httpx.Response:
        url = self.endpoint.format(model=self.model)
        headers = {"x-goog-api-key": self._api_key.get_secret_value() if self._api_key else ""}
        try:
            client = self._client
            if client is not None:
                return client.post(url, json=body, headers=headers)
            with httpx.Client(timeout=self._timeout_s) as owned:
                return owned.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise AnalyserError(f"the analyser could not be reached: {exc}") from None


def _error_text(response: httpx.Response) -> str:
    """The API's own words from its error body; never the key, never a stack."""
    try:
        body: object = response.json()
    except ValueError:
        return response.text[:500]
    message = json_field(json_field(body, "error"), "message")
    return str(message)[:500] if message is not None else response.text[:500]
