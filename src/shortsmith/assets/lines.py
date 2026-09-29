"""The line finder (ticket 078): where a sentence sits on the owner's article screenshot.

A highlight (`Beat.highlight`) names the sentence to mark; the renderer needs its line
boxes on the image. One vision call through the judge model (5.2's `RELEVANCE_JUDGE_MODEL`,
Haiku 4.5 by default) is asked "return the line boxes of this sentence on this image" and
answers boxes as fractions of the image's width and height, in reading order. The call is
one `judge` ledger row at `sourcing`, checked against the hard cap before it is made, and
its answer is cached per asset and sentence in `work/lines.json`, so a retry of the step or
a re-render never pays twice.

`find_highlights` is the step's use of it: for each highlight of the validated plan whose
beat really shows the screenshot, the boxes, recorded as a `HighlightRecord`. No boxes, no
finder configured, a finder that cannot answer, or a beat the ladder gave another picture:
the highlight is dropped with a `job.log` line and the beat stays as it is. Like the judge,
the finder never fails the job.

`FakeLineFinder` (12.1) answers the boxes it was given per sentence and nothing else.
"""

from __future__ import annotations

import base64
import copy
import json
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Self, cast

import anthropic
from anthropic.types import ImageBlockParam, TextBlockParam
from pydantic import SecretStr, TypeAdapter, ValidationError

from shortsmith.assets.base import media_type
from shortsmith.assets.judge import (
    CHARS_PER_TOKEN,
    DEFAULT_MODEL,
    MAX_RETRIES,
    PROVIDER,
    STEP,
    TIMEOUT_S,
    Create,
    create_message,
)
from shortsmith.contracts import AssetManifest, HighlightRecord, LineBox, PicturePlan
from shortsmith.jobs import Job
from shortsmith.ledger import Ledger

MAX_TOKENS = 600  # a handful of `{left, top, right, bottom}` objects and nothing else
TOKENS_PER_IMAGE = 1600  # one screenshot's worth of image tokens, for the hard-cap estimate
CACHE_NAME = "lines.json"
IMAGE_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")

SYSTEM_PROMPT = (
    "You find text on a screenshot of an article or a document. You are given the image "
    "and one sentence. Return the box of every line of the image that the sentence "
    "occupies, top to bottom, each box tight around that line's words of the sentence. "
    "Give each box as fractions of the image's width and height (0 is the left or top "
    "edge, 1 the right or bottom edge). If the sentence is not on the image, return no "
    "boxes; never guess.\n"
    'Answer with JSON only: {"lines": [{"left": 0.1, "top": 0.3, "right": 0.9, '
    '"bottom": 0.35}]} and nothing else.'
)

_JSON = re.compile(r"\{.*\}", re.DOTALL)
_CACHE = TypeAdapter(dict[str, list[LineBox]])


class LineError(RuntimeError):
    """The finder could not answer (an API error, a refusal, an unreadable reply). The
    step drops the highlight with a log line; the job never fails for it."""


class LineFinder(ABC):
    """One call per screenshot and sentence: the sentence's line boxes, in reading order;
    an empty list when the sentence is not on the image."""

    model: str

    def bind(self, job: Job) -> Self:
        """The job a real finder writes its ledger row against; the fake ignores it."""
        return self

    @abstractmethod
    def find(self, image: bytes, sentence: str) -> list[LineBox]: ...


class FakeLineFinder(LineFinder):
    """12.1: answers the boxes it was given for a sentence and nothing for any other.
    `calls` counts the calls so tests can prove the cache."""

    def __init__(self, lines: Mapping[str, Sequence[LineBox]] | None = None) -> None:
        self.model = "fake"
        self.lines = dict(lines or {})
        self.calls = 0

    def find(self, image: bytes, sentence: str) -> list[LineBox]:
        self.calls += 1
        return list(self.lines.get(sentence, ()))


def parse_lines(reply: str) -> list[LineBox]:
    """The boxes of the model's JSON, each clamped into the image; a box that is empty
    once clamped, or not four numbers, is dropped."""
    match = _JSON.search(reply)
    if match is None:
        raise LineError("the line finder did not answer with JSON")
    try:
        body: object = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LineError(f"the line finder's JSON did not parse: {exc}") from None
    listed = cast("dict[str, object]", body).get("lines") if isinstance(body, dict) else None
    if not isinstance(listed, list):
        raise LineError("the line finder's JSON has no `lines` list")
    boxes: list[LineBox] = []
    for item in cast("list[object]", listed):
        if not isinstance(item, dict):
            continue
        edges = [cast("dict[str, object]", item).get(k) for k in ("left", "top", "right", "bottom")]
        if not all(isinstance(e, int | float) for e in edges):
            continue
        left, top, right, bottom = (min(max(float(cast(float, e)), 0.0), 1.0) for e in edges)
        try:
            boxes.append(LineBox(left=left, top=top, right=right, bottom=bottom))
        except ValidationError:
            continue
    return boxes


class VisionLineFinder(LineFinder):
    """One Messages call with the screenshot and the sentence (078), on the judge model."""

    def __init__(
        self,
        ledger: Callable[[], Ledger],
        *,
        api_key: SecretStr | None,
        model: str = DEFAULT_MODEL,
        create: Create | None = None,
        max_retries: int = MAX_RETRIES,
        timeout_s: float = TIMEOUT_S,
    ) -> None:
        self._ledger = ledger
        self._api_key = api_key
        self.model = model
        self._create = create
        self._max_retries = max_retries
        self._timeout_s = timeout_s
        self._job: Job | None = None

    def bind(self, job: Job) -> Self:
        bound = copy.copy(self)
        bound._job = job
        return bound

    def find(self, image: bytes, sentence: str) -> list[LineBox]:
        job = self._job
        if job is None:
            raise LineError("VisionLineFinder has no job: bind(job) before calling")
        if self._api_key is None:
            raise LineError("the line finder needs ANTHROPIC_API_KEY in .env")
        kind = media_type(image)
        if kind is None or kind not in IMAGE_TYPES:
            raise LineError("the screenshot is not a JPEG, PNG, GIF or WebP image")
        text = f'Sentence: "{sentence}"\nReturn the line boxes of this sentence on this image.'
        picture: ImageBlockParam = {
            "type": "image",
            "source": {"type": "base64", "media_type": kind,
                       "data": base64.b64encode(image).decode("ascii")},
        }  # fmt: skip
        content: list[TextBlockParam | ImageBlockParam] = [{"type": "text", "text": text}, picture]
        book = self._ledger()
        estimate = {
            "input_tokens": math.ceil((len(text) + len(SYSTEM_PROMPT)) / CHARS_PER_TOKEN)
            + TOKENS_PER_IMAGE,
            "output_tokens": MAX_TOKENS,
        }
        book.check_before_call(job, STEP, book.estimate(PROVIDER, estimate))
        create = self._create or create_message(
            self._api_key, max_retries=self._max_retries, timeout_s=self._timeout_s
        )
        system: TextBlockParam = {
            "type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"},
        }  # fmt: skip
        try:
            message = create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=[system],
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.APIStatusError as exc:
            raise LineError(f"the line finder answered {exc.status_code}") from None
        except anthropic.APIError as exc:
            raise LineError(f"the line finder could not be reached: {exc.message}") from None
        usage = message.usage
        book.record(
            job, STEP, PROVIDER, message.model,
            {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
        )  # fmt: skip
        if message.stop_reason == "refusal":
            raise LineError("the line finder call was refused by the model (stop_reason refusal)")
        return parse_lines("".join(b.text for b in message.content if b.type == "text"))


# --- the step's use of it --------------------------------------------------------------------


def cache_key(asset_id: str, sentence: str) -> str:
    return f"{asset_id}|{sentence}"


def _load_cache(path: Path) -> dict[str, list[LineBox]]:
    if not path.is_file():
        return {}
    try:
        return _CACHE.validate_json(path.read_text(encoding="utf-8"))
    except ValidationError:
        return {}


def find_highlights(
    plan: PicturePlan,
    manifest: AssetManifest,
    *,
    job_dir: Path,
    finder: LineFinder | None,
    log: Callable[[str], None],
) -> list[HighlightRecord]:
    """The line boxes of every highlight of `plan` whose beat shows its screenshot, one
    finder call per asset and sentence not yet in `work/lines.json`; every drop is one
    `highlight:` line in `log`."""
    cache_path = job_dir / "work" / CACHE_NAME
    cache = _load_cache(cache_path)
    records: list[HighlightRecord] = []
    for beat in plan.beats:
        lit = beat.highlight
        if lit is None:
            continue
        label = f"highlight: {beat.id}: {lit.sentence!r} on {lit.asset_id!r}"
        decided = manifest.beat(beat.id)
        record = manifest.asset(lit.asset_id)
        if decided is None or record is None or decided.asset_id != lit.asset_id:
            shown = decided.asset_id if decided is not None else None
            log(f"{label} dropped: the beat does not show the screenshot (it shows "
                f"{shown!r}) (078)")  # fmt: skip
            continue
        key = cache_key(lit.asset_id, lit.sentence)
        boxes = cache.get(key)
        if boxes is None:
            if finder is None:
                log(f"{label} dropped: no line finder is configured (RELEVANCE_JUDGE=none) (078)")
                continue
            try:
                boxes = finder.find((job_dir / record.file).read_bytes(), lit.sentence)
            except LineError as exc:
                log(f"{label} dropped: {exc} (078)")
                continue
            cache[key] = boxes
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            dumped = _CACHE.dump_json(cache, indent=2).decode("utf-8")
            cache_path.write_text(dumped, encoding="utf-8")
        if not boxes:
            log(f"{label} dropped: no line of the sentence was found on the image (078)")
            continue
        log(f"{label}: {len(boxes)} lines found (078)")
        records.append(HighlightRecord(beat_id=beat.id, asset_id=lit.asset_id,
                                       sentence=lit.sentence, lines=boxes))  # fmt: skip
    return records
