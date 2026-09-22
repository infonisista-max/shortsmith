# 011 — Cost ledger, prices file, soft and hard caps

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The ledger that every paid adapter reports units to, priced from an operator-edited `prices.yaml`, with the soft cap that only flags, the hard cap that fails the job before the next paid call, and subscription tokens recorded as `tokens_estimated` and valued for display only. The job page shows the ledger rows and total. Per-step allowances come from style front matter under `budget`. The `planning` retry hook from 009 now writes rows.

Covers PRD `ledger`, `config` budget settings, the ledger part of `app`. Decisions 5.6, 8.3, 11.3.

## Acceptance criteria

- [x] `prices.example.yaml` at the repo root with keys for Groq per audio minute, Gemini per image, judge and planner per 1k input/output tokens, paid search per query, api-equivalent planner rate; `PRICES_FILE` setting defaults to `prices.yaml`; startup fails with a plain message when the file is missing or a price is missing for a provider in use.
- [x] `ledger.record(job, step, provider, model, units) -> Row` prices the row from the file and appends `{step, provider, model, units, inr, tokens_estimated}` to `job.json.cost`; adapters never compute INR.
- [x] `ledger.check_before_call(job, step, estimated_inr)` raises `BudgetExceeded` naming the step when cash total + estimate > `BUDGET_INR_HARD`; the pipeline marks the job `failed` with "budget exceeded at step X" and the ledger is shown on the page.
- [x] Cash total > `BUDGET_INR_PER_JOB` sets `job.json.over_soft_cap = true` and nothing else changes; no step is skipped or degraded for cost anywhere in the codebase (test greps for the flag's readers: only the page and contact sheet).
- [x] Only rows with `inr > 0` count toward caps; `tokens_estimated` rows are valued at the api-equivalent rate for display and never enter `inr`.
- [x] `BUDGET_INR_PER_DAY` is read; the daily closing of the form is ticket 044 (expose `ledger.cash_spent_today(now)` here).
- [x] Job page shows the ledger rows and the cash total.
- [x] Boundary tests, `tests/test_ledger.py`: soft cap flags only, hard cap fails before the paid call (the fake adapter records zero calls), subscription tokens never enter INR, missing price is a startup error.

## Session notes (done, 22 Sep 2026)

- Operator rider: the ticket names `BUDGET_INR_PER_JOB` / `BUDGET_INR_HARD` without numbers, so per decision 11.3 both ship unset (`None` = disabled); only `BUDGET_INR_PER_DAY=500` has a value. `.env.example` says to set the per-job caps from the p90 of the first 10 metered passing jobs. `PRICES_FILE` defaults to `prices.yaml`, which is git-ignored like `.env`; `prices.example.yaml` is committed. No new package (`pyyaml` from 008).
- OPERATOR ACTION: the real `.env` selects `claude_code` and carries a Groq key, so the server now refuses to start (a `LedgerError` naming the gap) until `prices.example.yaml` is copied to `prices.yaml`. The check runs in the app lifespan, like the passcode check, so `import shortsmith.app` never needs the file.
- `ledger.py`: `Prices` (provider -> unit -> INR; `*_tokens` per 1k), `Caps`, `Ledger.record(job, step, provider, model, units)` where `units` is a small dict (`{"audio_minutes": 2}`, `{"input_tokens": 1200, "output_tokens": 300}`) because one scalar cannot carry input and output tokens; `check_before_call(job, step, estimated_inr)` raises `BudgetExceeded` naming the step; `cash_spent_today(data_dir, now)` sums cash rows since midnight IST (044 wires it to the form). `providers_in_use(settings)`: api planner -> `planner`, claude_code -> `api_equivalent`, gemini -> `gemini`, Groq key -> `groq`; 017 adds `judge` and `search`. A row for an unpriced provider or unit is a `LedgerError`, never a silent zero.
- `jobs.CostRow` is `{step, provider, model, units, inr, tokens_estimated, inr_equivalent, at}`: `inr_equivalent` is the api-equivalent value of a subscription row, priced once at record time for the page and sheet, never in the cash total; `at` is what the daily sum filters on. `provider == "claude_code"` is the subscription case (`SUBSCRIPTION_PROVIDERS`).
- `job.json` gets a second writer inside a step, so `jobs.amend` re-reads the file, applies the change and writes; `transition` and `set_progress` go through it, and a row appended mid-step survives the next transition (tested). On Windows the on-access scan makes the first read after a rewrite cost about 10 ms, and a reader can hit a transient `PermissionError` inside the replace, so `jobs.load` retries the way `_write_json` already did.
- Pipeline: `BudgetExceeded` inside any step -> `failed` with "Budget exceeded at step X." and the rows so far kept (tested); adapters call the ledger themselves, taking it at construction (012, 014, 015, 017, 019), because `Planner.plan_picture(request)` has no job handle. The app builds one ledger in the lifespan (`app.state.ledger`) and `create_app(book=...)` accepts a test one.
- Job page: a `table.ledger` per row (step, provider, model, units, cash, tokens), the cash total, the subscription tokens with their api-equivalent value marked "not counted", and the soft-cap warning. The contact sheet summary row shows `ledger: INR x.xx cash [+ N tokens (INR y.yy equiv.)] [OVER SOFT CAP]`. A test greps `src/` so `over_soft_cap` is read only by `app.py` and `contact_sheet.py`.
- Loops: ruff clean, pyright strict clean, 362 tests pass, smoke `delivered` with T1-T4 pass (qa.json read; contact sheet's ledger line reads INR 0.00 cash on the fake-only job).

## Notes from 008

- `pyyaml==6.0.3` is declared (pinned). The per-step allowances live under `budget` on every spec (`styles.Budget`: `judge_max_calls`, `search_max_queries`, `gen_max_per_short`); read them from `PlanRequest.style.numbers["budget"]` or `styles.StyleSpec.budget`.

## Blocked by

- Blocked by `issues/008-style-specs-loader-resolver.md`

## User stories addressed

- User story 37
- User story 38
- User story 40
- User story 63
