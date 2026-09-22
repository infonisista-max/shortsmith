"""The `api` planner: one Anthropic Messages call per planner call (8.3, 12.1).

The builder's text is the prompt, exactly the one the CLI adapter sends on stdin, cut
(`prompt.split_prompt`) into three user blocks: instructions, spec sections 1-2 and
the request from the brief on. The shared system prompt and the spec block carry
`cache_control` markers, so a job's second call and its 8.2 retries read the style
from the cache. No tools; the model is `PLANNER_MODEL`. The text is written to
`work/planner/request_<call>[_retry].md` and the reply to `reply_<call>[_retry].json`
as the CLI adapter does, so both leave the same files.

One Messages call is the seam tests replace (`Create`), not the SDK's HTTP client: the
SDK ships its own httpx build, which the project does not declare, so nothing here
touches it. Recorded replies under `tests/fixtures/anthropic/` are fed through the
SDK's own `Message` model, and the reply is kept as the SDK parsed it in
`reply_<call>.json`.

Cost (5.6, 11.3): the call is checked against the hard cap first, estimated at the
prompt's length in tokens plus the full `max_tokens`; once the API answers, its
`usage` is one `planner` row with fresh, cache-write and cache-read input tokens at
their own price keys (cache writes and reads are priced differently from plain input).
The row is recorded before the reply is parsed, so a reply the parser rejects is still
billed, as it was. The reply text goes through the shared parser (`PlanInvalid`, the
8.2 retry applies); an HTTP error, a refusal or a reply cut off at `max_tokens` raises
`PlannerError` with the API's words, never the key, and the job fails at `planning`.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable, Sequence
from typing import Self, cast

import anthropic
from anthropic.types import Message, MessageParam, TextBlockParam
from pydantic import SecretStr

from shortsmith.contracts import PicturePlan, PlanFeedback, PlanRequest, SoundStory
from shortsmith.jobs import Job
from shortsmith.ledger import Ledger
from shortsmith.planner.base import Planner, PlannerError
from shortsmith.planner.parse import parse_reply
from shortsmith.planner.prompt import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    Call,
    build_prompt,
    split_prompt,
)

PROVIDER = "planner"
STEP = "planning"
DEFAULT_MODEL = "claude-sonnet-5"
MAX_TOKENS = 16000  # a full picture plan is a few thousand tokens; under the SDK's
# non-streaming ceiling, so one plain call suffices
TIMEOUT_S = 300.0
MAX_RETRIES = 2
CHARS_PER_TOKEN = 3  # a generous token estimate for the hard-cap check only

# The seam tests replace: what one Messages call is, keyword arguments in and the SDK's
# own `Message` out. The default builds the client from the key and makes the call; the
# SDK's httpx client is never touched here, so tests need no transport of their own.
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


def _text(text: str, *, cached: bool = False) -> TextBlockParam:
    if cached:
        return {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}
    return {"type": "text", "text": text}


class ApiPlanner(Planner):
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

    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        text = build_prompt(request, "picture", feedback=feedback)
        plan = self._call("picture", text, retry=feedback is not None)
        assert isinstance(plan, PicturePlan)
        return plan

    def plan_sound(
        self,
        request: PlanRequest,
        picture: PicturePlan,
        catalogue_tags: Sequence[str] = (),
        *,
        feedback: PlanFeedback | None = None,
    ) -> SoundStory:
        text = build_prompt(
            request, "sound", picture=picture, catalogue_tags=catalogue_tags, feedback=feedback
        )
        story = self._call("sound", text, retry=feedback is not None)
        assert isinstance(story, SoundStory)
        return story

    def _call(self, call: Call, text: str, *, retry: bool) -> PicturePlan | SoundStory:
        job = self._job
        if job is None:
            raise PlannerError("ApiPlanner has no job: bind(job) before calling")
        if self._api_key is None:
            raise PlannerError("PLANNER=api needs ANTHROPIC_API_KEY in .env")
        folder = job.work_dir / "planner"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{call}_retry" if retry else call
        (folder / f"request_{name}.md").write_text(text, encoding="utf-8", newline="\n")

        book = self._ledger()
        estimate = {
            "input_tokens": math.ceil(len(text) / CHARS_PER_TOKEN),
            "output_tokens": self._max_tokens,
        }
        book.check_before_call(job, STEP, book.estimate(PROVIDER, estimate))
        create = self._create or create_message(
            self._api_key, max_retries=self._max_retries, timeout_s=self._timeout_s
        )
        instructions, spec, rest = split_prompt(text)
        try:
            message = create(
                model=self.model,
                max_tokens=self._max_tokens,
                system=[_text(SYSTEM_PROMPT, cached=True)],
                messages=[
                    {
                        "role": "user",
                        "content": [_text(instructions), _text(spec, cached=True), _text(rest)],
                    }
                ],
            )
        except anthropic.APIStatusError as exc:
            raise PlannerError(
                f"the Anthropic API answered {exc.status_code}: {_error_text(exc.body)}"
            ) from None
        except anthropic.APIError as exc:
            raise PlannerError(f"the Anthropic API could not be reached: {exc.message}") from None
        (folder / f"reply_{name}.json").write_text(
            message.model_dump_json(indent=2), encoding="utf-8", newline="\n"
        )
        book.record(job, STEP, PROVIDER, message.model, _units(message))
        if message.stop_reason == "refusal":
            raise PlannerError(f"the {call} call was refused by the model (stop_reason refusal)")
        if message.stop_reason == "max_tokens":
            raise PlannerError(
                f"the {call} reply was cut off at max_tokens ({self._max_tokens}) "
                "before the plan was complete"
            )
        reply = "".join(block.text for block in message.content if block.type == "text")
        return parse_reply(reply, call, prompt_version=PROMPT_VERSION)


def _units(message: Message) -> dict[str, float]:
    usage = message.usage
    return {
        "input_tokens": usage.input_tokens,
        "cache_write_input_tokens": usage.cache_creation_input_tokens or 0,
        "cache_read_input_tokens": usage.cache_read_input_tokens or 0,
        "output_tokens": usage.output_tokens,
    }


def _error_text(body: object) -> str:
    """The API's own words from its error body; never the key, never a stack."""
    error = _key(body, "error")
    message = _key(error, "message")
    return str(message)[:500] if message is not None else repr(body)[:500]


def _key(value: object, name: str) -> object:
    return cast("dict[str, object]", value).get(name) if isinstance(value, dict) else None
