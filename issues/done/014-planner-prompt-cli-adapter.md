# 014 — Planner prompt builder, generated schema, CLI adapter, picture and sound calls

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The real planner path on the operator's Claude subscription. One prompt builder renders PlanRequest into fixed sections (spec numbers, spec prose, brief, style note, references as a captioned list, transcript) with the JSON schema generated from the Pydantic models appended, and instructs the planner on tiers, brief-fact stamping, `source_intent`, `hook.original_position`, the sound catalogue tags and the reason tags. The CLI adapter writes the identical prompt to the job's work directory and runs the `claude` CLI non-interactively with JSON output, no tools, no repo access; one shared parser validates the output; a ledger row at zero INR carries `tokens_estimated`. Two sequential calls per job: picture, then sound with the validated, snapped picture plan and the catalogue tags. Prompts are versioned files.

Covers PRD `planner` (prompt builder, CLI adapter, parser, versioning). Decisions 2.3, 4.1, 4.2, 5.1, 7.1, 7.2, 8.1, 8.2, 8.3.

## Acceptance criteria

- [x] `src/shortsmith/planner/prompts/picture_v1.md` and `sound_v1.md` exist; `prompt_version` is recorded on every plan and in `job.json`.
- [x] `planner.build_prompt(request, call) -> str` renders the six sections in the fixed order with the brief before the transcript, appends `PicturePlan.model_json_schema()` or `SoundStory.model_json_schema()`, and lists the tier-1 and tier-2 kinds from the spec; snapshot-tested against a recorded rendering.
- [x] `ClaudeCodePlanner` writes `work/planner/request_<call>.md`, runs `claude -p --output-format json` with "reply with JSON only", no tools and no shell, reads the JSON, parses with the shared parser, and records a ledger row with `inr = 0` and `tokens_estimated` from the CLI usage output; tests use a stubbed subprocess with a recorded CLI response under `tests/fixtures/claude_cli/`.
- [x] Shared parser: JSON extraction from the reply, Pydantic validation with `extra="forbid"`, a validation failure is a Violations result so the 009 retry applies; a second failure fails the job with the Pydantic errors on the page.
- [x] The sound call receives the ValidatedPlan (snapped boundaries, landed events) and the catalogue tags (an empty tag list until 022; the fake catalogue tags in tests).
- [x] `PLANNER=claude_code` is the default outside tests; startup fails with a config error unless `SHORTSMITH_SINGLE_OPERATOR=true` (11.3).
- [x] `pipeline` runs picture → validate → sound → validate with one retry each and records each call and retry as a ledger row.
- [x] Smoke still uses `fake`; a test proves `FakePlanner`, `ClaudeCodePlanner` and the parser return the same model classes.

## Done (22 Sep 2026)

- Package: `planner/{base,fake,prompt,parse,claude_code}.py` plus `prompts/{picture,sound}_v1.md`. `planner.build_prompt` is `planner.prompt.build_prompt(request, call, *, picture=None, catalogue_tags=(), feedback=None)`; `PROMPT_VERSION = "v1"`, and the files are `string.Template`s (`$tiers`, `$full_reasons`, `$style_name`, `$prompt_version`).
- Prompt layout: instructions, then sections 1-6 (spec numbers as YAML plus a `job:` block with the constraints and asset policy; spec prose with its headings pushed two levels down; brief; style note; `- id (kind, WxH): caption` references; `[i] start-end text` transcript plus the flagged segments), then for sound `## 7.` the snapped picture plan JSON and `## 8.` the catalogue tags, then the schema, then the retry block, and last the JSON-only line. Tier 2 lists every `TIER2_KINDS` entry, split into allowed (the spec's `tier2_kinds`) and refused.
- Snapshots: `tests/fixtures/planner/{picture,sound}_v1.snapshot.md`, rendered from a fixed synthetic request (not the live spec, so editing a spec does not break them). To re-record deliberately, run pytest with `SHORTSMITH_UPDATE_SNAPSHOTS=1`.
- Parser: `parse_reply(text, call, prompt_version=...)` finds a fenced block, a bare object or the outermost `{...}` and validates it with the forbid models. Code stamps `prompt_version`; the model's own value is never trusted. Failures raise `PlanInvalid` with `plan (8.2): <loc>: <msg>` lines, and the pipeline's `_with_one_retry` treats them exactly like grammar violations (the reply text becomes `feedback.previous`).
- CLI: `claude -p --output-format json --tools "" --safe-mode --strict-mcp-config --no-session-persistence --system-prompt "<JSON only>"`, with the prompt on stdin (it can exceed Windows' command-line limit) and cwd `work/planner/`. `ANTHROPIC_API_KEY` is removed from the child env so the subscription pays. `--bare` was rejected because it disables OAuth, i.e. the subscription. Files: `request_<call>[_retry].md` and `reply_<call>[_retry].json`. The ledger row is `claude_code`, the model is the first `modelUsage` key, and input tokens = input + cache creation + cache read. It is recorded before parsing, so a bad reply still counts. `is_error`, a non-zero exit or no JSON raises `PlannerError`: the job fails at planning with the CLI's text, and there is no 8.2 retry.
- `subproc.run` gained `input`, `cwd` and `env`, so the CLI stays under the job watchdog.
- Wiring: `Planner.bind(job)` is called in `_plan`. `planner.from_settings(settings, *, ledger: Callable[[], Ledger])`, because the app loads the ledger in its lifespan. `config.check_startup` plus `ConfigError` run in the lifespan after the passcode check. There is a new `Settings.shortsmith_single_operator` (default false) and `JobRecord.prompt_version`. `pipeline.CATALOGUE_TAGS = ()` until 022.
- OPERATOR ACTION: add `SHORTSMITH_SINGLE_OPERATOR=true` to `.env` (the server now refuses to start with `PLANNER=claude_code` without it), and add the key with a comment to `.env.example`. The agent's permissions deny reading or editing `.env*` files, so neither was touched.
- OPERATOR CHECK: the CLI envelopes under `tests/fixtures/claude_cli/` follow the documented `--output-format json` shape (their `result` is the fake plan) but were written by hand, not recorded, because no subscription call was made from this session. Replace them with a real `reply_picture.json` / `reply_sound.json` from the first real job, and read the prompt text in `work/planner/request_picture.md` against the reference beat tables before rating that short.
- Not verified here: a live `claude` run (flags from `claude --help` on this machine). Prompt taste (wording and rules emphasis) is the operator's call against the reference shorts.

## Notes from 011

- Subscription rows: `ledger.record(job, "planning", "claude_code", model, {"input_tokens": i, "output_tokens": o})` yields `inr` 0, `tokens_estimated` i+o and `inr_equivalent` at the file's `api_equivalent` rate (required at startup when `PLANNER=claude_code`). `Planner.plan_picture(request)` has no job handle: give the adapter the job (or a per-job meter) at call time so it can record; the pipeline builds nothing for it.

## Notes from 009

- Interface: `Planner.plan_picture(request, *, feedback: PlanFeedback | None = None)` and `plan_sound(request, picture, catalogue_tags=(), *, feedback=None)`. `feedback.previous` is the rejected output as JSON text and `feedback.violations` the list of `"<beat id> (<rule>): <message>"` lines; append both to the same prompt on the retry (8.2). The pipeline already runs picture -> validate -> retry once -> sound (with the snapped picture) -> validate -> retry once; the adapter only has to honour `feedback` and record its ledger row per call. `PlanRejected` fails the job with the list on the page; a Pydantic failure in the parser should raise into the same path (return-or-raise is this ticket's call; `grammar.Violations(items=[Violation(rule="8.2", message=...)])` is the shape the retry understands).
- `plan.raw.json` / `sound.raw.json` hold the planner's last output; the CLI adapter can write its own `work/planner/` files beside them.

## Notes from 010

- The prompt must ask for `name_runs` (new `PicturePlan` field: `[{first, last}]` word indices, inclusive) for every multi-word name or number, so the pager never splits them (6.1); the generated schema already includes it.

## Blocked by

- Blocked by `issues/009-grammar-validator.md`
- Blocked by `issues/011-ledger-prices-caps.md`

## User stories addressed

- User story 6
- User story 9
- User story 10
- User story 41
- User story 59
- User story 64
