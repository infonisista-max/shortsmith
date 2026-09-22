# 015 — Planner API adapter, output-identical to the CLI, startup config checks

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The second real adapter: one Messages call per planner call through the Anthropic SDK already in the project, model from `PLANNER_MODEL`, prompt caching on the system prompt and spec sections, cost from the usage field to the ledger, output parsed by the same parser as the CLI adapter. Switching `PLANNER` changes cost and nothing else.

Covers PRD `planner` (API adapter), `config` startup errors. Decisions 8.3, 11.3, 12.1.

## Acceptance criteria

- [x] `ApiPlanner` sends the identical prompt text as `ClaudeCodePlanner` (a test builds both and compares the strings) as system + user with cache-control markers on the system prompt and spec sections.
- [x] Usage tokens go to the ledger as input/output units priced from `prices.yaml`; cached input tokens are recorded at their own price key.
- [x] `PLANNER=api` without `ANTHROPIC_API_KEY` is a startup config error with a plain message; `PLANNER=claude_code` without `SHORTSMITH_SINGLE_OPERATOR=true` remains an error (from 014); `PLANNER=fake` needs neither.
- [x] Recorded request and response JSON under `tests/fixtures/anthropic/`; tests assert request construction (model, cache markers, no tools) and response parsing; no network.
- [x] A test feeds the same recorded planner reply through both adapters' parse path and asserts identical `PicturePlan` and `SoundStory` objects.
- [x] `config` unit tests cover all three startup outcomes.

## Done (22 Sep 2026)

- `planner/api.py`: `ApiPlanner` with `bind(job)` like the CLI adapter. `prompt.split_prompt` cuts the builder's text (never rebuilds it) into instructions / spec sections 1-2 / the request from `## 3. Brief` on; the three concatenate back to `build_prompt` exactly, which is what the identical-text test asserts against the CLI adapter's stdin. `SYSTEM_PROMPT` moved from `claude_code` to `prompt` so both adapters send the same one; cache markers sit on the system prompt and the spec block.
- Files: `work/planner/request_<call>[_retry].md` and `reply_<call>[_retry].json` (the reply as the SDK parsed it), the same names the CLI adapter writes.
- Ledger: `check_before_call` first, estimated at the prompt length (3 chars/token) plus the full `max_tokens`; then one `planner` row per call with `input_tokens`, `cache_write_input_tokens`, `cache_read_input_tokens`, `output_tokens` — cache writes and reads are priced apart from fresh input, so `REQUIRED_UNITS["planner"]` and `prices.example.yaml` grew the two keys. The row is recorded before the reply is parsed, so a rejected reply is still billed.
- Errors: `APIStatusError` / `APIError` → `PlannerError` with the API's own words (never the key); `stop_reason` `refusal` or `max_tokens` → `PlannerError` after the row; anything the parser rejects → `PlanInvalid`, so the 8.2 retry applies.
- config: `PLANNER_MODEL` (default `claude-sonnet-5`), and `check_startup` refuses `PLANNER=api` without `ANTHROPIC_API_KEY`. `from_settings` now returns `ApiPlanner`; `UnavailablePlanner` stays for the next not-yet-built adapter.
- OPERATOR ACTION: add `PLANNER_MODEL=claude-sonnet-5` to `.env.example` (and `.env` if the deployment overrides it), and copy the two new `planner.cache_*_input_tokens` keys from `prices.example.yaml` into `prices.yaml` with the vendor's current rates — with `PLANNER=api` the server refuses to start until they are priced. The agent does not touch `.env*`.
- Loops: ruff clean, pyright 0 errors, 647 pytest pass, smoke delivered with T1 T2 T3 T4 T8 T9 pass (`out/qa.json` read).
- No live Anthropic call was made; the fixtures under `tests/fixtures/anthropic/` are hand-built in the documented Messages shape (the reply text is the 014 CLI fixture's, so both adapters are proven to parse the same words). Replace them with a real reply from the first live job.

## Note: the SDK's HTTP client is not the test seam

`anthropic==1.6.0` runs on `httpx2`, which is a transitive package, not declared in `pyproject.toml`; the board rule (and the 008 pyyaml precedent) says a package is declared with `uv add` by the operator, so the tests do not import it. The seam is one Messages call instead (`api.Create`: keyword arguments in, the SDK's own `Message` out), and the recorded replies under `tests/fixtures/anthropic/` are read through `anthropic.types.Message`. That covers request construction, response parsing and error mapping without a transport. If the operator later runs `uv add httpx2` (or `uv add --dev httpx2`), the stub can be swapped for an `httpx2.MockTransport` like the Groq tests use, for byte-level request assertions.

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
