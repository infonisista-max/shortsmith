"""The one parser every planner adapter shares (decisions 8.1, 8.2, 8.3).

`parse_reply(reply, call, prompt_version=...)` finds the JSON object in the reply
text (bare, in a code fence, or with a sentence around it), validates it with the
call's `extra="forbid"` model (the same model the prompt's schema is generated from)
and stamps `prompt_version` with the version the builder sent: the version on a plan
is a fact code knows, not something the model is trusted to echo. Anything else raises
`PlanInvalid` carrying the reply and one `plan (8.2): <message>` line per problem, the
grammar's violation shape, so the pipeline's one retry applies to it (8.2).
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from shortsmith.contracts import PicturePlan, SoundStory, Violation
from shortsmith.planner.base import PlanInvalid
from shortsmith.planner.prompt import MODELS, Call

_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)


def parse_reply(reply: str, call: Call, *, prompt_version: str) -> PicturePlan | SoundStory:
    text = _json_text(reply)
    if text is None:
        raise _invalid(call, reply, ["the reply holds no JSON object"])
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _invalid(call, reply, [f"the reply is not valid JSON: {exc}"]) from exc
    if not isinstance(data, dict):
        kind = type(data).__name__
        raise _invalid(call, reply, [f"the reply is JSON but not an object ({kind})"])
    data["prompt_version"] = prompt_version
    try:
        return MODELS[call].model_validate(data)
    except ValidationError as exc:
        raise _invalid(call, reply, [_line(error) for error in exc.errors()]) from exc


def _json_text(reply: str) -> str | None:
    fenced = _FENCE.search(reply)
    if fenced is not None:
        return fenced.group(1).strip()
    stripped = reply.strip()
    if stripped.startswith(("{", "[")):
        return stripped
    start, end = reply.find("{"), reply.rfind("}")
    return reply[start : end + 1] if 0 <= start < end else None


def _line(error: ErrorDetails) -> str:
    loc = ".".join(str(part) for part in error["loc"]) or "(root)"
    return f"{loc}: {error['msg']}"


def _invalid(call: Call, reply: str, messages: list[str]) -> PlanInvalid:
    return PlanInvalid(call, reply, [str(Violation(rule="8.2", message=m)) for m in messages])
