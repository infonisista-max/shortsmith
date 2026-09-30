"""The `claude_code` planner: the `claude` CLI on the operator's subscription (8.3).

Each run of `planning` binds the adapter once and gets its own folder,
`work/planner/run<n>/` (n = 1, 2, 3 ... one past the highest on disk; 065), so a
retried job never writes over an earlier run's files. Each call writes the builder's
prompt there as `request_<call>.md` (`request_<call>_retry.md` for the 8.2 retry, so
both stay on disk), runs the CLI non-interactively from that folder with the prompt on
stdin, and keeps its JSON envelope as `reply_<call>[_retry].json`. The CLI gets no
tools (`--tools ""`), no MCP servers, no CLAUDE.md, skills or hooks (`--safe-mode`), no
saved session, and a system prompt that asks for JSON only; with no tools it cannot
touch the repo or a shell. `ANTHROPIC_API_KEY` is removed from the child's environment
so the subscription, not an API key, pays for the call.

The model is pinned, never the CLI's default (065): every call passes `--model
<PLANNER_CLI_MODEL>`, read by `model` when the job binds, which is when its planning
step starts, so a Retry after an edit to `.env` uses the new model without a restart.
Each call logs `planner: <call> asked <model>, used <modelUsage model>` in `job.log`,
ending in `(differs)` when the CLI answered on another model.

The envelope's `usage` becomes one ledger row per call at INR 0 (`provider
claude_code`, the model from `modelUsage`): input tokens include the cache writes and
reads, since the subscription consumed them all. The row is recorded before the reply
is parsed, so a reply the parser rejects is still counted; a CLI error that consumed
no tokens at all writes no row (065). `result` goes through the shared parser; a CLI
that fails outright (non-zero exit, no envelope, `is_error`) raises `PlannerError` and
the job fails at `planning` with the CLI's own words.

The quota path (065): an `is_error` envelope with `api_error_status` 429, or whose
`result` holds one of `QUOTA_PHRASES` (spent credits, a reached limit), raises
`QuotaSpent` instead; the page then says `QUOTA_SENTENCE` (switch the model and press
Retry), and the CLI's words stay in the detail and on the job.log failure line.

`ask(name, system, text, step=...)` (095) is the editor's free-text call on the same
transport: the same flags with its own `--system-prompt`, `request_<name>.md` and
`reply_<name>.json` under `work/editor/`, the ledger row at `step`, the same quota and
error handling, and the reply's `result` returned unparsed. Under `PLANNER=claude_code`
with `ANTHROPIC_API_KEY` set this adapter is the primary of a `FailoverPlanner`, so
`QuotaSpent` and a twice-failed call move to the API adapter instead of failing the job.

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

from shortsmith import jobs, subproc
from shortsmith.contracts import PicturePlan, PlanFeedback, PlanRequest, SoundStory
from shortsmith.jobs import Job
from shortsmith.ledger import Ledger
from shortsmith.planner.base import Planner, PlannerError, PlannerUnavailable, run_folder
from shortsmith.planner.parse import parse_reply
from shortsmith.planner.prompt import PROMPT_VERSION, SYSTEM_PROMPT, Call, build_prompt

PROVIDER = "claude_code"
# 095: every flag but the system prompt, shared by the plan calls and `ask`.
BASE_FLAGS: tuple[str, ...] = (
    "-p",
    "--output-format",
    "json",
    "--tools",
    "",
    "--safe-mode",
    "--strict-mcp-config",
    "--no-session-persistence",
)
CLI_FLAGS: tuple[str, ...] = (*BASE_FLAGS, "--system-prompt", SYSTEM_PROMPT)
EDITOR_DIR = "editor"  # 095: `ask` files live in `work/editor/`, beside no plan run
HIDDEN_ENV = ("ANTHROPIC_API_KEY",)
DEFAULT_MODEL = "claude-opus-5-5"  # 065: the model run04's CLI actually used
QUOTA_STATUS = 429
# 065: what the CLI says when the subscription's usage is spent or a limit is reached;
# the fallback when the envelope carries no `api_error_status`. Matched lower-cased.
QUOTA_PHRASES: tuple[str, ...] = (
    "out of usage credits",
    "usage limit",
    "hit your limit",
    "reached your limit",
    "limit reached",
)
QUOTA_SENTENCE = (
    "The planner's Claude usage is spent. Set PLANNER_CLI_MODEL to another model "
    "and press Retry."
)

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


class QuotaSpent(PlannerError):
    """The CLI answered that the subscription's usage is spent or a limit is reached;
    the job fails at `planning` with `QUOTA_SENTENCE` on the page."""


class ClaudeCodePlanner(Planner):
    def __init__(
        self,
        ledger: Callable[[], Ledger],
        *,
        run: Runner = run_cli,
        executable: str = "claude",
        model: Callable[[], str] = lambda: DEFAULT_MODEL,
    ) -> None:
        self._ledger = ledger
        self._run = run
        self._executable = executable
        self.cli_model = model
        self._job: Job | None = None
        self._folder: Path | None = None
        self._model = DEFAULT_MODEL

    def bind(self, job: Job) -> Self:
        bound = copy.copy(self)
        bound._job = job
        bound._folder = run_folder(job)
        bound._model = self.cli_model()
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
        """095: one free-text call with its own system prompt; files in `work/editor/`,
        the ledger row at `step`, the reply's `result` returned as it came."""
        job = self._job
        if job is None:
            raise PlannerError("ClaudeCodePlanner has no job: bind(job) before calling")
        return self._run_cli(job, job.work_dir / EDITOR_DIR, name, text, system, step=step)

    def _call(self, call: Call, text: str, *, retry: bool) -> PicturePlan | SoundStory:
        job, folder = self._job, self._folder
        if job is None or folder is None:
            raise PlannerError("ClaudeCodePlanner has no job: bind(job) before calling")
        name = f"{call}_retry" if retry else call
        result = self._run_cli(job, folder, name, text, SYSTEM_PROMPT, step="planning")
        return parse_reply(result, call, prompt_version=PROMPT_VERSION)

    def _run_cli(
        self, job: Job, folder: Path, name: str, text: str, system: str, *, step: str
    ) -> str:
        """Write `request_<name>.md`, run the CLI, keep `reply_<name>.json`, record the
        ledger row at `step` and return the envelope's `result`; an error envelope
        raises `QuotaSpent` or `PlannerError`."""
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"request_{name}.md").write_text(text, encoding="utf-8", newline="\n")
        env = {k: v for k, v in os.environ.items() if k not in HIDDEN_ENV}
        argv = [self._executable, *BASE_FLAGS, "--system-prompt", system, "--model", self._model]
        done = self._run(argv, text, folder, env)
        (folder / f"reply_{name}.json").write_bytes(done.stdout)
        envelope = _envelope(done)
        used = envelope.model
        differs = " (differs)" if used != self._model else ""
        jobs.note(job, f"planner: {name} asked {self._model}, used {used}{differs}")
        if not (envelope.is_error and not any(envelope.units.values())):
            self._ledger().record(job, step, PROVIDER, used, envelope.units)
        if envelope.is_error:
            if envelope.quota_spent:
                raise QuotaSpent(f"the claude CLI's usage is spent: {envelope.result}")
            raise PlannerError(f"the claude CLI reported an error: {envelope.result}")
        return envelope.result


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
    api_error_status: int | None = None
    usage: CliUsage = CliUsage()
    model_usage: dict[str, object] = Field(default_factory=dict, alias="modelUsage")

    @property
    def model(self) -> str:
        return next(iter(self.model_usage), "unknown")

    @property
    def quota_spent(self) -> bool:
        """065: status 429 first; the phrases when the status is missing."""
        if self.api_error_status == QUOTA_STATUS:
            return True
        words = self.result.lower()
        return any(phrase in words for phrase in QUOTA_PHRASES)

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
