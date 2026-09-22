"""The relevance judge: the cheap filter above the searched sources (decision 5.2).

For one beat the step hands the judge up to six candidate thumbnails together with
the beat's query, its subject kind and the brief's topic line; the judge answers one
score per candidate, 0-3, with reasons drawn from a fixed list. Best >= 2 wins, ties
by the source's own order, everything under 2 means the next source and then the 4.4
ladder. The judge is a FILTER, not the quality bar: the branch-10 vision critic is the
real gate above it, so a judge that cannot answer never fails the job - the step just
carries on unjudged, as it did before this ticket.

`VisionJudge` is one Anthropic Messages call, model from `RELEVANCE_JUDGE_MODEL`
(5.2's default is Haiku 4.5, swappable without code when accepted images rate weak on
the contact sheet). Like the API planner, the seam tests replace is the one Messages
call, not the SDK's HTTP client. `FakeRelevanceJudge` (12.1) scores by looking for the
query in the candidate's own URL, which is what the fake source writes into it.

`Judging` is the per-job bookkeeping around whichever judge is configured (5.6, 11.3):
verdicts cached by candidate URL so a repeated candidate costs nothing, and the
style's `budget.judge_max_calls` as the call ceiling - once it is reached the ladder
continues with no judge at all, recorded on the beat and shown on the contact sheet.
Each real call is one `judge` ledger row in input and output tokens, checked against
the hard cap before it is made, so a refused call is never billed.
"""

from __future__ import annotations

import base64
import copy
import json
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Self, cast

import anthropic
from anthropic.types import ImageBlockParam, Message, MessageParam, TextBlockParam
from pydantic import SecretStr

from shortsmith.assets.base import media_type
from shortsmith.contracts import Candidate
from shortsmith.jobs import Job
from shortsmith.ledger import Ledger

PROVIDER = "judge"
STEP = "sourcing"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # 5.2: Haiku 4.5, swappable by config
MAX_TOKENS = 1000  # six `{index, score, reasons}` objects and nothing else
TIMEOUT_S = 120.0
MAX_RETRIES = 2
CHARS_PER_TOKEN = 3  # a generous token estimate for the hard-cap check only
TOKENS_PER_THUMB = 1600  # a thumbnail's worth of image tokens, for the same estimate

# 5.2: the fixed reason list. A reason the model invents is dropped, never stored.
REASONS: tuple[str, ...] = (
    "wrong_subject",
    "watermark",
    "text_heavy",
    "meme",
    "too_small",
    "nsfw",
    "logo_only",
)
MIN_SCORE = 2  # 5.2: best >= 2 wins; everything under 2 falls to the next source
MAX_SCORE = 3

SYSTEM_PROMPT = (
    "You screen candidate images for a 9:16 YouTube Short. You are a cheap filter, not "
    "the editor: you only say whether a picture shows what the beat asked for and is "
    "usable as a full-screen or card visual.\n"
    "Score every candidate 0-3:\n"
    "3 = clearly the asked-for subject, clean and usable as it is.\n"
    "2 = the right subject, usable after cropping or re-dressing.\n"
    "1 = related but not the subject, or unusable as a visual.\n"
    "0 = wrong subject, or unshowable.\n"
    f"Reasons must come from this list, and only for what you actually see: {', '.join(REASONS)}. "
    "A score of 3 usually has no reasons.\n"
    'Answer with JSON only: {"candidates": [{"index": 1, "score": 2, "reasons": ["watermark"]}]}, '
    "one object per candidate, in the order you were given them, and nothing else."
)

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_JSON = re.compile(r"\{.*\}", re.DOTALL)


class JudgeError(RuntimeError):
    """The judge could not answer (an API error, an unreadable reply). The step notes
    it and sources the beat unjudged; the job never fails for it (5.2)."""


@dataclass(frozen=True)
class Verdict:
    """One candidate's score with its reasons, already filtered to `REASONS`."""

    score: int
    reasons: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.score >= MIN_SCORE


@dataclass(frozen=True)
class Thumb:
    """One candidate as the judge sees it: the candidate and its thumbnail bytes,
    None when the source has no cheap image to show (the judge then reads its URL)."""

    candidate: Candidate
    body: bytes | None = None


class RelevanceJudge(ABC):
    """One vision call over up to six thumbnails (5.2). `score` returns one `Verdict`
    per thumb, in the order given."""

    model: str

    def bind(self, job: Job) -> Self:
        """The job a real judge writes its ledger row against; the fake ignores it."""
        return self

    @abstractmethod
    def score(
        self, query: str, subject_kind: str, topic: str, thumbs: Sequence[Thumb]
    ) -> list[Verdict]: ...


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) >= 3}


class FakeRelevanceJudge(RelevanceJudge):
    """12.1: scores by looking for the query in the candidate's own URL, which is what
    `FakeImageSource` writes into it. Every query word present is a 3; a partial match
    is a 2; nothing in common is a 0 with `wrong_subject`. `calls` counts the calls so
    tests can prove the per-URL cache."""

    def __init__(self, *, model: str = "fake", floor: int | None = None) -> None:
        self.model = model
        self.floor = floor  # a fixed score for every candidate, for the ladder tests
        self.calls = 0

    def score(
        self, query: str, subject_kind: str, topic: str, thumbs: Sequence[Thumb]
    ) -> list[Verdict]:
        self.calls += 1
        if self.floor is not None:
            return [Verdict(self.floor, () if self.floor >= MIN_SCORE else ("wrong_subject",))
                    for _ in thumbs]  # fmt: skip
        wanted = _words(query)
        verdicts: list[Verdict] = []
        for thumb in thumbs:
            found = _words(thumb.candidate.url.replace("-", " "))
            hit = wanted & found
            if wanted and hit == wanted:
                verdicts.append(Verdict(MAX_SCORE))
            elif hit:
                verdicts.append(Verdict(MIN_SCORE))
            else:
                verdicts.append(Verdict(0, ("wrong_subject",)))
        return verdicts


# The seam tests replace: what one Messages call is, keyword arguments in and the SDK's
# own `Message` out, exactly as the API planner defines it (015).
Create = Callable[..., Message]


def create_message(api_key: SecretStr, *, max_retries: int, timeout_s: float) -> Create:
    def create(
        *,
        model: str,
        max_tokens: int,
        system: list[TextBlockParam],
        messages: list[MessageParam],
    ) -> Message:
        client = anthropic.Anthropic(
            api_key=api_key.get_secret_value(), max_retries=max_retries, timeout=timeout_s
        )
        return client.messages.create(
            model=model, max_tokens=max_tokens, system=system, messages=messages
        )

    return create


def request_text(query: str, subject_kind: str, topic: str, thumbs: Sequence[Thumb]) -> str:
    """The one text block: what the beat asked for and what each candidate is."""
    lines = [
        f"Short topic: {topic or '(not given)'}",
        f"Beat query: {query}",
        f"Subject kind: {subject_kind or 'unknown'}",
        f"Candidates ({len(thumbs)}), in order:",
    ]
    for i, thumb in enumerate(thumbs, start=1):
        size = f"{thumb.candidate.width}x{thumb.candidate.height}" if thumb.candidate.width else "?"
        shown = "thumbnail below" if thumb.body is not None else "no thumbnail, URL only"
        lines.append(f"{i}. {size} · {shown} · {thumb.candidate.url}")
    return "\n".join(lines)


def parse_reply(reply: str, n: int) -> list[Verdict]:
    """`n` verdicts from the model's JSON, scores clamped to 0-3 and reasons filtered
    to `REASONS`; a candidate the model skipped scores 0."""
    match = _JSON.search(reply)
    if match is None:
        raise JudgeError("the judge did not answer with JSON")
    try:
        body: object = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeError(f"the judge's JSON did not parse: {exc}") from None
    listed = _field(body, "candidates")
    if not isinstance(listed, list):
        raise JudgeError("the judge's JSON has no `candidates` list")
    by_index: dict[int, Verdict] = {}
    for i, item in enumerate(cast("list[object]", listed), start=1):
        index = _field(item, "index")
        score = _field(item, "score")
        reasons = _field(item, "reasons")
        if score is None and reasons is None:
            continue
        listed_reasons = cast("list[object]", reasons) if isinstance(reasons, list) else []
        by_index[index if isinstance(index, int) else i] = Verdict(
            score=min(max(int(score), 0), MAX_SCORE) if isinstance(score, int | float) else 0,
            reasons=tuple(r for r in listed_reasons if isinstance(r, str) and r in REASONS),
        )
    return [by_index.get(i, Verdict(0, ("wrong_subject",))) for i in range(1, n + 1)]


class VisionJudge(RelevanceJudge):
    """One Messages call per beat with up to six thumbnails (5.2)."""

    def __init__(
        self,
        ledger: Callable[[], Ledger],
        *,
        api_key: SecretStr | None,
        model: str = DEFAULT_MODEL,
        create: Create | None = None,
        max_retries: int = MAX_RETRIES,
        timeout_s: float = TIMEOUT_S,
        max_tokens: int = MAX_TOKENS,
    ) -> None:
        self._ledger = ledger
        self._api_key = api_key
        self.model = model
        self._create = create
        self._max_retries = max_retries
        self._timeout_s = timeout_s
        self._max_tokens = max_tokens
        self._job: Job | None = None

    def bind(self, job: Job) -> Self:
        bound = copy.copy(self)
        bound._job = job
        return bound

    def score(
        self, query: str, subject_kind: str, topic: str, thumbs: Sequence[Thumb]
    ) -> list[Verdict]:
        job = self._job
        if job is None:
            raise JudgeError("VisionJudge has no job: bind(job) before calling")
        if self._api_key is None:
            raise JudgeError("RELEVANCE_JUDGE=api needs ANTHROPIC_API_KEY in .env")
        text = request_text(query, subject_kind, topic, thumbs)
        content: list[TextBlockParam | ImageBlockParam] = [{"type": "text", "text": text}]
        images = 0
        for thumb in thumbs:
            block = _image_block(thumb)
            if block is not None:
                content.append(block)
                images += 1

        book = self._ledger()
        estimate = {
            "input_tokens": math.ceil(len(text) / CHARS_PER_TOKEN) + images * TOKENS_PER_THUMB,
            "output_tokens": self._max_tokens,
        }
        book.check_before_call(job, STEP, book.estimate(PROVIDER, estimate))
        create = self._create or create_message(
            self._api_key, max_retries=self._max_retries, timeout_s=self._timeout_s
        )
        system: TextBlockParam = {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
        try:
            message = create(
                model=self.model,
                max_tokens=self._max_tokens,
                system=[system],
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.APIStatusError as exc:
            raise JudgeError(
                f"the judge answered {exc.status_code}: {_error_text(exc.body)}"
            ) from None
        except anthropic.APIError as exc:
            raise JudgeError(f"the judge could not be reached: {exc.message}") from None
        usage = message.usage
        book.record(
            job,
            STEP,
            PROVIDER,
            message.model,
            {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
        )
        if message.stop_reason == "refusal":
            raise JudgeError("the judge call was refused by the model (stop_reason refusal)")
        reply = "".join(block.text for block in message.content if block.type == "text")
        return parse_reply(reply, len(thumbs))


def _image_block(thumb: Thumb) -> ImageBlockParam | None:
    if thumb.body is None:
        return None
    kind = media_type(thumb.body)
    if kind is None or kind not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        return None
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": kind,
            "data": base64.b64encode(thumb.body).decode("ascii"),
        },
    }


def _field(value: object, name: str) -> object:
    return cast("dict[str, object]", value).get(name) if isinstance(value, dict) else None


def _error_text(body: object) -> str:
    """The API's own words from its error body; never the key, never a stack."""
    message = _field(_field(body, "error"), "message")
    return str(message)[:500] if message is not None else repr(body)[:500]


# --- the per-job bookkeeping (5.6, 11.3) ---------------------------------------------------


@dataclass
class Judging:
    """The judge as the step uses it: the per-URL verdict cache and the call ceiling.

    `verdicts` returns one verdict per candidate, or None when nothing judged them -
    no judge configured, the ceiling reached, or the judge could not answer. A beat
    sourced with None is recorded `judge_skipped`, and the ladder runs on the source's
    own order, exactly as it did before this ticket."""

    judge: RelevanceJudge | None = None
    max_calls: int = 0
    calls: int = 0
    capped: bool = False
    notes: list[str] = field(default_factory=lambda: [])
    cache: dict[str, Verdict] = field(default_factory=lambda: {})

    @property
    def model(self) -> str:
        return self.judge.model if self.judge is not None else ""

    def verdicts(
        self,
        query: str,
        subject_kind: str,
        topic: str,
        candidates: Sequence[Candidate],
        thumbnail: Callable[[Candidate], bytes | None],
    ) -> list[Verdict] | None:
        if self.judge is None or not candidates:
            return None
        unjudged = [c for c in candidates if c.url not in self.cache]
        if unjudged:
            if self.calls >= self.max_calls:
                if not self.capped:
                    self.capped = True
                    self.notes.append(
                        f"judge: the style's judge_max_calls ({self.max_calls}) is spent; "
                        "the remaining beats are sourced unjudged"
                    )
                return None
            thumbs = [Thumb(c, thumbnail(c)) for c in unjudged]
            self.calls += 1
            try:
                scored = self.judge.score(query, subject_kind, topic, thumbs)
            except JudgeError as exc:
                self.notes.append(f"judge: {exc}")
                return None
            for candidate, verdict in zip(unjudged, scored, strict=True):
                self.cache[candidate.url] = verdict
        return [self.cache[c.url] for c in candidates]
