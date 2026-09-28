# 065 — Planner failures keep their evidence, a spent quota says so, and the CLI's model is pinned

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Run04 (job `20260928-140620-f774e1`) failed at `planning` the first time because the
`claude` CLI replied that its usage credits were spent. The adapter handled that
correctly: `claude_code.py` raised `PlannerError` with the CLI's words, and they went
into `job.json.error.detail`. Nothing on disk keeps them now:

- `jobs.transition` writes `failed step=planning message='We could not plan the short.'`
  to `job.log`, which is only the fixed sentence. The detail never reaches the log.
- The retry (`jobs.requeue`) clears `job.json.error`. Its docstring says "job.log keeps
  it", and it doesn't.
- Run 2 wrote over `work/planner/reply_picture.json`, which held the CLI's reply, and
  run 3 then wrote over run 2's files. That also cost us run 2's rejected retry, which
  066's diagnosis needed.

The page showed the generic "We could not plan the short.", so the operator could not
tell a spent quota from a planner bug. The failed call also left a ledger row with
model `unknown` and 0 tokens.

The CLI also chooses its own default model. Operator decision (QA review, 28 Sep
2026): the planner never relies on that default.

1. **Evidence.** Every `-> failed` line in `job.log` carries the first line of the
   failure's detail (the exception text, never the traceback), for every step. Each
   pipeline run of `planning` writes its request and reply files under
   `work/planner/run<n>/` (n = 1, 2, 3 …), with the 8.2 `_retry` names unchanged
   inside it. A later run never writes over an earlier run's files. This applies to
   both real adapters (`claude_code`, `api`).
2. **Quota.** When the CLI's reply is a usage limit (spent credits or a reached
   limit), the adapter raises its own error. Run04's reply is saved at
   `tests/fixtures/claude_cli/quota.json`. It has `is_error: true`,
   `api_error_status: 429`, empty `modelUsage`, 0 tokens, and `result` "You're out of
   usage credits. Switch to another model, or manage usage credits at …". Status 429
   is the main signal, and the phrases are the fallback. The job fails at `planning` with this page
   sentence: "The planner's Claude usage is spent. Set PLANNER_CLI_MODEL to another
   model and press Retry." The CLI's own words stay in `detail` and, through (1), in
   `job.log`. The recognised phrases live in one tuple in `claude_code.py`. Any other
   CLI error keeps today's sentence.
3. **No empty ledger row.** A CLI error that reports 0 input and 0 output tokens
   writes no ledger row. A call that consumed tokens still writes its row, as today,
   including one whose reply the parser rejects.
4. **Pinned model.** A new setting, `PLANNER_CLI_MODEL` (in `.env` and documented in
   `.env.example`), is passed to the CLI as `--model` on every call. Its default is
   `claude-opus-5-5`, the model run04's CLI actually used. The setting is read when each
   job's planning step starts, so after an edit to `.env`, Retry uses the new model
   without an app restart. Each call adds one line to `job.log`:
   `planner: <call> asked <PLANNER_CLI_MODEL>, used <model from modelUsage>`. When the
   two differ, the line ends with `(differs)`.

## Acceptance criteria

- [ ] A step that raises `X("boom")` writes a `job.log` failure line ending in
      `detail='boom'`, with no traceback. A requeue followed by a second failure leaves
      both lines in the log.
- [ ] Planning run twice on one job (fail, requeue, run again) leaves
      `work/planner/run1/` and `work/planner/run2/` side by side, and run1's reply is
      byte-identical afterwards. Tested for both adapters with fake runners.
- [ ] A fake runner that prints `tests/fixtures/claude_cli/quota.json` (run04's real
      reply, unchanged) fails the job with the quota sentence, and `detail` holds the
      CLI's `result` words. The same envelope with `api_error_status` removed is still
      recognised by its phrase. Any other `is_error` envelope
      (`tests/fixtures/claude_cli/error.json`) keeps "We could not plan the short.".
- [ ] A 0-token error envelope (`quota.json`) writes no ledger row. A rejected reply with tokens still
      writes one.
- [ ] The fake runner receives `--model <PLANNER_CLI_MODEL>` on both calls, including
      retries. A changed setting reaches the next job without a restart. The `asked /
      used` log line is written, with `(differs)` when the models differ.
- [ ] `.env.example` documents `PLANNER_CLI_MODEL`, and the `claude_code.py` docstring
      describes the flag, the run folders and the quota path.
- [ ] Smoke passes T1–T13 (fake planner, so no new paid call). Ruff, pyright and every
      test file are green in foreground chunks.
- [ ] Done note: the amendment line for 8.3 for the operator to paste (the pinned model,
      the quota sentence), and what to check on run05: after a planning failure,
      `job.log` still says why after a retry.

## Blocked by

- Nothing.

## Done (29 Sep 2026)

All criteria met except one line of `.env.example`. That file is permission-denied to
the agent (same as for 020, 033 and 052), so the operator pastes it. The `PLANNER_CLI_MODEL`
setting itself works now. `tests/test_config.py` clears it and checks its default, and
`test_every_example_key_is_a_setting` still holds once the line is pasted.

**For the operator: paste into `.env.example`** (under `PLANNER_MODEL`):

```
# 065: PLANNER=claude_code's model, passed to the claude CLI as --model on every call
# (never the CLI's own default). Read when each job's planning starts, so after an edit
# here Retry uses the new model without restarting the app.
PLANNER_CLI_MODEL=claude-opus-5-5
```

**Amendment line for 8.3** (to paste into the grill decisions):

> 8.3 (amended 29 Sep 2026, 065): the `claude_code` planner pins its model with
> `PLANNER_CLI_MODEL` (default `claude-opus-5-5`), passed as `--model` on every call and
> re-read at each job's planning step; it never relies on the CLI's default. When the
> CLI answers that the usage is spent (status 429, or a spent-credits / limit phrase),
> the job fails at `planning` with "The planner's Claude usage is spent. Set
> PLANNER_CLI_MODEL to another model and press Retry." The CLI's words stay in the
> detail and in `job.log`.

What was built:
- `jobs.transition`: every `-> failed` line ends with `detail='<first line>'` (the
  exception text, never the traceback). The `requeue` docstring is now true.
- `planner.base.run_folder`: each `bind` (once per pipeline run of `planning`) takes
  `work/planner/run<n>/`, one past the highest on disk. Both `claude_code` and `api`
  write there with the 8.2 `_retry` names unchanged.
- `claude_code`: `QuotaSpent(PlannerError)` on `api_error_status` 429, with
  `QUOTA_PHRASES` (one tuple) as the fallback. `pipeline.failure_message` maps it to
  `QUOTA_SENTENCE`. An `is_error` envelope with 0 tokens writes no ledger row.
  `--model` goes on every call, and a `planner: <call> asked X, used Y[ (differs)]` line
  is logged per call (`<call>` is `picture`, `picture_retry`, `sound` or `sound_retry`).
- `from_settings(..., reload=)`. The app passes `config.load` when it loaded the
  settings itself, so an edited `.env` reaches the next job's bind.
- `tests/fixtures/claude_cli/error.json`: its `result` was "Claude AI usage limit
  reached|…", which is itself a limit message and would be (rightly) read as quota. It
  is now a plain `API Error: 500 … Internal server error` envelope, which keeps the
  ticket's "any other `is_error` envelope" intent. The old wording is still tested as a
  recognised quota phrase.

What to check on run05: after a planning failure and Retry, `job.log` still has the
`-> failed … detail='…'` line naming why, `work/planner/run1/` and `run2/` both exist,
and each call has its `planner: … asked claude-opus-5-5, used …` line with no
`(differs)`.

## User stories addressed

- Operator, run04 QA (28 Sep 2026): planning failed once with the CLI out of usage
  credits, and the page said only "We could not plan the short."
- Operator, 28 Sep 2026: pin the model with `PLANNER_CLI_MODEL`, never the CLI's
  default. The quota message says to switch it and press Retry.
