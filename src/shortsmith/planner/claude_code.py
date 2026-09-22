"""The `claude_code` planner: the `claude` CLI on the operator's subscription (8.3).

Each call writes the builder's prompt to the job's `work/planner/request_<call>.md`
(`request_<call>_retry.md` for the 8.2 retry, so both stay on disk), runs the CLI
non-interactively from that directory with the prompt on stdin, and keeps its JSON
envelope as `reply_<call>[_retry].json`. The CLI gets no tools (`--tools ""`), no MCP
servers, no CLAUDE.md, skills or hooks (`--safe-mode`), no saved session, and a system
prompt that asks for JSON only; with no tools it cannot touch the repo or a shell.
`ANTHROPIC_API_KEY` is removed from the child's environment so the subscription, not
an API key, pays for the call.

The envelope's `usage` becomes one ledger row per call at INR 0 (`provider
claude_code`, the model from `modelUsage`): input tokens include the cache writes and
reads, since the subscription consumed them all. The row is recorded before the reply
is parsed, so a reply the parser rejects is still counted. `result` goes through the
shared parser; a CLI that fails outright (non-zero exit, no envelope, `is_error`)
raises `PlannerError` and the job fails at `planning` with the CLI's own words.

The ledger is passed as a callable because the app loads it in its lifespan, after the
planner is built.
"""

from __future__ import annotations

import copy
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, ValidationError

from shortsmith import subproc
from shortsmith.contracts import PicturePlan, PlanFeedback, PlanRequest, SoundStory
from shortsmith.jobs import Job
from shortsmith.ledger import Ledger
from shortsmith.planner.base import Planner, PlannerError, PlannerUnavailable
from shortsmith.planner.parse import parse_reply
from shortsmith.planner.prompt import PROMPT_VERSION, Call, build_prompt

PROVIDER = "claude_code"
SYSTEM_PROMPT = (
    "You are the Shortsmith planner. You have no tools. Read the whole message and "
    "reply with JSON only: one object matching the schema it gives."
)
CLI_FLAGS: tuple[str, ...] = (
    "-p",
    "--output-format",
    "json",
    "--tools",
    "",
    "--safe-mode",
    "--strict-mcp-config",
    "--no-session-persistence",
    "--system-prompt",
    SYSTEM_PROMPT,
)
HIDDEN_ENV = ("ANTHROPIC_API_KEY",)

Runner = Callable[[list[str], str, Path, Mapping[str, str]], subprocess.CompletedProcess[bytes]]


def run_cli(
    argv: list[str], stdin: str, cwd: Path, env: Mapping[str, str]
) -> subprocess.CompletedProcess[bytes]:
    """The real runner: resolve the executable on PATH and run it under the job's
    watchdog (`subproc.run`)."""
    found = shutil.which(argv[0])
    if found is None:
        raise PlannerUnavailable(
            f"the {argv[0]!r} CLI is not on PATH: install Claude Code and log in, "
            "or set PLANNER=fake"
        )
    return subproc.run([found, *argv[1:]], input=stdin, cwd=cwd, env=env)


class ClaudeCodePlanner(Planner):
    def __init__(
        self,
        ledger: Callable[[], Ledger],
        *,
        run: Runner = run_cli,
        executable: str = "claude",
    ) -> None:
        self._ledger = ledger
        self._run = run
        self._executable = executable
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
            raise PlannerError("ClaudeCodePlanner has no job: bind(job) before calling")
        folder = job.work_dir / "planner"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{call}_retry" if retry else call
        (folder / f"request_{name}.md").write_text(text, encoding="utf-8", newline="\n")
        env = {k: v for k, v in os.environ.items() if k not in HIDDEN_ENV}
        done = self._run([self._executable, *CLI_FLAGS], text, folder, env)
        (folder / f"reply_{name}.json").write_bytes(done.stdout)
        envelope = _envelope(done)
        self._ledger().record(job, "planning", PROVIDER, envelope.model, envelope.units)
        if envelope.is_error:
            raise PlannerError(f"the claude CLI reported an error: {envelope.result}")
        return parse_reply(envelope.result, call, prompt_version=PROMPT_VERSION)


class CliUsage(BaseModel):
    """The token counts of `usage` in the CLI's JSON result; other keys are ignored."""

    input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0


class CliEnvelope(BaseModel):
    """What `claude -p --output-format json` prints: the reply text in `result`, the
    usage, and per-model usage keyed by model id. Other keys are ignored."""

    is_error: bool = False
    result: str = ""
    usage: CliUsage = CliUsage()
    model_usage: dict[str, object] = Field(default_factory=dict, alias="modelUsage")

    @property
    def model(self) -> str:
        return next(iter(self.model_usage), "unknown")

    @property
    def units(self) -> dict[str, float]:
        u = self.usage
        consumed = u.input_tokens + u.cache_creation_input_tokens + u.cache_read_input_tokens
        return {"input_tokens": consumed, "output_tokens": u.output_tokens}


def _envelope(done: subprocess.CompletedProcess[bytes]) -> CliEnvelope:
    stderr = done.stderr.decode("utf-8", errors="replace").strip()
    try:
        envelope = CliEnvelope.model_validate_json(done.stdout)
    except ValidationError:
        shown = stderr or done.stdout[:500].decode("utf-8", errors="replace")
        raise PlannerError(
            f"the claude CLI exited {done.returncode} without a JSON result: {shown}"
        ) from None
    if done.returncode != 0 and not envelope.is_error:
        raise PlannerError(f"the claude CLI exited {done.returncode}: {stderr}")
    return envelope
