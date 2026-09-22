# 015 — Planner API adapter, output-identical to the CLI, startup config checks

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The second real adapter: one Messages call per planner call through the Anthropic SDK already in the project, model from `PLANNER_MODEL`, prompt caching on the system prompt and spec sections, cost from the usage field to the ledger, output parsed by the same parser as the CLI adapter. Switching `PLANNER` changes cost and nothing else.

Covers PRD `planner` (API adapter), `config` startup errors. Decisions 8.3, 11.3, 12.1.

## Acceptance criteria

- [ ] `ApiPlanner` sends the identical prompt text as `ClaudeCodePlanner` (a test builds both and compares the strings) as system + user with cache-control markers on the system prompt and spec sections.
- [ ] Usage tokens go to the ledger as input/output units priced from `prices.yaml`; cached input tokens are recorded at their own price key.
- [ ] `PLANNER=api` without `ANTHROPIC_API_KEY` is a startup config error with a plain message; `PLANNER=claude_code` without `SHORTSMITH_SINGLE_OPERATOR=true` remains an error (from 014); `PLANNER=fake` needs neither.
- [ ] Recorded request and response JSON under `tests/fixtures/anthropic/`; tests assert request construction (model, cache markers, no tools) and response parsing; no network.
- [ ] A test feeds the same recorded planner reply through both adapters' parse path and asserts identical `PicturePlan` and `SoundStory` objects.
- [ ] `config` unit tests cover all three startup outcomes.

## Notes from 011

- Cash rows: `ledger.check_before_call(job, "planning", estimated_inr)` first, then `ledger.record(job, "planning", "planner", model, {"input_tokens": usage.input, "output_tokens": usage.output})`; the `planner` price (per 1k tokens) is required at startup when `PLANNER=api`.

## Notes from 014

- Prompt: `planner.prompt.build_prompt(request, call, *, picture=None, catalogue_tags=(), feedback=None)` is one string (instructions file, six 2.3 sections, the sound call's picture plan and tags, schema, retry block, the JSON-only line). For cache markers, split it at `## 1. Style numbers` / `## 3. Brief` rather than building a second prompt, so the strings stay identical.
- Parse: `planner.parse.parse_reply(text, call, prompt_version=prompt.PROMPT_VERSION)`; it raises `PlanInvalid` (the pipeline retries it once like a grammar rejection). A call that cannot answer at all (HTTP error, refusal) should raise `PlannerError`.
- Wiring: `planner.from_settings(settings, *, ledger)` takes a `Callable[[], Ledger]` (the app loads the ledger in its lifespan); `Planner.bind(job)` returns the per-job adapter the pipeline calls, which is where the ledger rows get their job. `config.check_startup(settings)` runs in the app lifespan; add the `api` key check there (`ConfigError`).
- The CLI adapter strips `ANTHROPIC_API_KEY` from the `claude` child env so the subscription pays; nothing else reads that variable yet.

## Blocked by

- Blocked by `issues/014-planner-prompt-cli-adapter.md`

## User stories addressed

- User story 41
- User story 59
- User story 64
