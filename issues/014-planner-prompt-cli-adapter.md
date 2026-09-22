# 014 — Planner prompt builder, generated schema, CLI adapter, picture and sound calls

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The real planner path on the operator's Claude subscription. One prompt builder renders PlanRequest into fixed sections (spec numbers, spec prose, brief, style note, references as a captioned list, transcript) with the JSON schema generated from the Pydantic models appended, and instructs the planner on tiers, brief-fact stamping, `source_intent`, `hook.original_position`, the sound catalogue tags and the reason tags. The CLI adapter writes the identical prompt to the job's work directory and runs the `claude` CLI non-interactively with JSON output, no tools, no repo access; one shared parser validates the output; a ledger row at zero INR carries `tokens_estimated`. Two sequential calls per job: picture, then sound with the validated, snapped picture plan and the catalogue tags. Prompts are versioned files.

Covers PRD `planner` (prompt builder, CLI adapter, parser, versioning). Decisions 2.3, 4.1, 4.2, 5.1, 7.1, 7.2, 8.1, 8.2, 8.3.

## Acceptance criteria

- [ ] `src/shortsmith/planner/prompts/picture_v1.md` and `sound_v1.md` exist; `prompt_version` is recorded on every plan and in `job.json`.
- [ ] `planner.build_prompt(request, call) -> str` renders the six sections in the fixed order with the brief before the transcript, appends `PicturePlan.model_json_schema()` or `SoundStory.model_json_schema()`, and lists the tier-1 and tier-2 kinds from the spec; snapshot-tested against a recorded rendering.
- [ ] `ClaudeCodePlanner` writes `work/planner/request_<call>.md`, runs `claude -p --output-format json` with "reply with JSON only", no tools and no shell, reads the JSON, parses with the shared parser, and records a ledger row with `inr = 0` and `tokens_estimated` from the CLI usage output; tests use a stubbed subprocess with a recorded CLI response under `tests/fixtures/claude_cli/`.
- [ ] Shared parser: JSON extraction from the reply, Pydantic validation with `extra="forbid"`, a validation failure is a Violations result so the 009 retry applies; a second failure fails the job with the Pydantic errors on the page.
- [ ] The sound call receives the ValidatedPlan (snapped boundaries, landed events) and the catalogue tags (an empty tag list until 022; the fake catalogue tags in tests).
- [ ] `PLANNER=claude_code` is the default outside tests; startup fails with a config error unless `SHORTSMITH_SINGLE_OPERATOR=true` (11.3).
- [ ] `pipeline` runs picture → validate → sound → validate with one retry each and records each call and retry as a ledger row.
- [ ] Smoke still uses `fake`; a test proves `FakePlanner`, `ClaudeCodePlanner` and the parser return the same model classes.

## Notes from 011

- Subscription rows: `ledger.record(job, "planning", "claude_code", model, {"input_tokens": i, "output_tokens": o})` yields `inr` 0, `tokens_estimated` i+o and `inr_equivalent` at the file's `api_equivalent` rate (required at startup when `PLANNER=claude_code`). `Planner.plan_picture(request)` has no job handle: give the adapter the job (or a per-job meter) at call time so it can record; the pipeline builds nothing for it.

## Notes from 009

- Interface: `Planner.plan_picture(request, *, feedback: PlanFeedback | None = None)` and `plan_sound(request, picture, catalogue_tags=(), *, feedback=None)`. `feedback.previous` is the rejected output as JSON text and `feedback.violations` the list of `"<beat id> (<rule>): <message>"` lines; append both to the same prompt on the retry (8.2). The pipeline already runs picture -> validate -> retry once -> sound (with the snapped picture) -> validate -> retry once; the adapter only has to honour `feedback` and record its ledger row per call. `PlanRejected` fails the job with the list on the page; a Pydantic failure in the parser should raise into the same path (return-or-raise is this ticket's call; `grammar.Violations(items=[Violation(rule="8.2", message=...)])` is the shape the retry understands).
- `plan.raw.json` / `sound.raw.json` hold the planner's last output; the CLI adapter can write its own `work/planner/` files beside them.

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
