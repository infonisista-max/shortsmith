"""The `api` planner: one Anthropic Messages call per planner call (8.3, 12.1).

The builder's text is the prompt, exactly the one the CLI adapter sends on stdin, cut
(`prompt.split_prompt`) into three user blocks: instructions, spec sections 1-2 and
the request from the brief on. The shared system prompt and the spec block carry
`cache_control` markers, so a job's second call and its 8.2 retries read the style
from the cache. No tools; the model is `PLANNER_MODEL`. The text is written to
`work/planner/run<n>/request_<call>[_retry].md` and the reply to
`reply_<call>[_retry].json` as the CLI adapter does, so both leave the same files; each
run of `planning` binds its own `run<n>` (065), so a retried job keeps both runs.

`ask(name, system, text, step=...)` (095) is the editor's free-text call: one Messages
call with `system` as the system prompt and `text` as the one user block (no cache
markers), `request_<name>.md` / `reply_<name>.json` under `work/editor/`, the same hard
cap check and one cash row, both at `step`; a refusal or a `max_tokens` cut raises
`PlannerError`, and the reply's text comes back unparsed. This adapter is also the
backup of a `FailoverPlanner` under `PLANNER=claude_code` with `ANTHROPIC_API_KEY` set,
at `PLANNER_MODEL`, its rows landing in the ledger like any `PLANNER=api` job's.

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
from pathlib import Path
from typing import Self, cast

import anthropic
from anthropic.types import Message, MessageParam, TextBlockParam
from pydantic import SecretStr

from shortsmith.contracts import PicturePlan, PlanFeedback, PlanRequest, SoundStory
from shortsmith.jobs import Job
from shortsmith.ledger import Ledger
from shortsmith.planner.base import Planner, PlannerError, run_folder
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
EDITOR_DIR = "editor"  # 095: `ask` files live in `work/editor/`
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
        self._folder: Path | None = None

    def bind(self, job: Job) -> Self:
        bound = copy.copy(self)
        bound._job = job
        bound._folder = run_folder(job)
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

    def ask(self, name: str, system: str, text: str, *, step: str) -> str:
        """095: one free-text Messages call with `system` as the system prompt; files in
        `work/editor/`, the cash row at `step`, the reply's text returned unparsed."""
        job = self._job
        if job is None:
            raise PlannerError("ApiPlanner has no job: bind(job) before calling")
        message = self._message(
            job,
            job.work_dir / EDITOR_DIR,
            name,
            text,
            system=[_text(system)],
            content=[_text(text)],
            step=step,
            what=f"the {name} call",
        )
        return _reply_text(message)

    def _call(self, call: Call, text: str, *, retry: bool) -> PicturePlan | SoundStory:
        job, folder = self._job, self._folder
        if job is None or folder is None:
            raise PlannerError("ApiPlanner has no job: bind(job) before calling")
        name = f"{call}_retry" if retry else call
        instructions, spec, rest = split_prompt(text)
        message = self._message(
            job,
            folder,
            name,
            text,
            system=[_text(SYSTEM_PROMPT, cached=True)],
            content=[_text(instructions), _text(spec, cached=True), _text(rest)],
            step=STEP,
            what=f"the {call}",
        )
        return parse_reply(_reply_text(message), call, prompt_version=PROMPT_VERSION)

    def _message(
        self,
        job: Job,
        folder: Path,
        name: str,
        text: str,
        *,
        system: list[TextBlockParam],
        content: list[TextBlockParam],
        step: str,
        what: str,
    ) -> Message:
        """Write `request_<name>.md`, check the hard cap, make the one Messages call,
        keep `reply_<name>.json`, record the cash row at `step`; an HTTP error, a
        refusal or a reply cut off at `max_tokens` raises `PlannerError`."""
        if self._api_key is None:
            raise PlannerError("PLANNER=api needs ANTHROPIC_API_KEY in .env")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"request_{name}.md").write_text(text, encoding="utf-8", newline="\n")

        book = self._ledger()
        estimate = {
            "input_tokens": math.ceil(len(text) / CHARS_PER_TOKEN),
            "output_tokens": self._max_tokens,
        }
        book.check_before_call(job, step, book.estimate(PROVIDER, estimate))
        create = self._create or create_message(
            self._api_key, max_retries=self._max_retries, timeout_s=self._timeout_s
        )
        try:
            message = create(
                model=self.model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
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
        book.record(job, step, PROVIDER, message.model, _units(message))
        if message.stop_reason == "refusal":
            raise PlannerError(f"{what} call was refused by the model (stop_reason refusal)")
        if message.stop_reason == "max_tokens":
            raise PlannerError(
                f"{what} reply was cut off at max_tokens ({self._max_tokens}) "
                "before it was complete"
            )
        return message


def _reply_text(message: Message) -> str:
    return "".join(block.text for block in message.content if block.type == "text")


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
