# 011 — Cost ledger, prices file, soft and hard caps

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The ledger that every paid adapter reports units to, priced from an operator-edited `prices.yaml`, with the soft cap that only flags, the hard cap that fails the job before the next paid call, and subscription tokens recorded as `tokens_estimated` and valued for display only. The job page shows the ledger rows and total. Per-step allowances come from style front matter under `budget`. The `planning` retry hook from 009 now writes rows.

Covers PRD `ledger`, `config` budget settings, the ledger part of `app`. Decisions 5.6, 8.3, 11.3.

## Acceptance criteria

- [ ] `prices.example.yaml` at the repo root with keys for Groq per audio minute, Gemini per image, judge and planner per 1k input/output tokens, paid search per query, api-equivalent planner rate; `PRICES_FILE` setting defaults to `prices.yaml`; startup fails with a plain message when the file is missing or a price is missing for a provider in use.
- [ ] `ledger.record(job, step, provider, model, units) -> Row` prices the row from the file and appends `{step, provider, model, units, inr, tokens_estimated}` to `job.json.cost`; adapters never compute INR.
- [ ] `ledger.check_before_call(job, step, estimated_inr)` raises `BudgetExceeded` naming the step when cash total + estimate > `BUDGET_INR_HARD`; the pipeline marks the job `failed` with "budget exceeded at step X" and the ledger is shown on the page.
- [ ] Cash total > `BUDGET_INR_PER_JOB` sets `job.json.over_soft_cap = true` and nothing else changes; no step is skipped or degraded for cost anywhere in the codebase (test greps for the flag's readers: only the page and contact sheet).
- [ ] Only rows with `inr > 0` count toward caps; `tokens_estimated` rows are valued at the api-equivalent rate for display and never enter `inr`.
- [ ] `BUDGET_INR_PER_DAY` is read; the daily closing of the form is ticket 044 (expose `ledger.cash_spent_today(now)` here).
- [ ] Job page shows the ledger rows and the cash total.
- [ ] Boundary tests, `tests/test_ledger.py`: soft cap flags only, hard cap fails before the paid call (the fake adapter records zero calls), subscription tokens never enter INR, missing price is a startup error.

## Notes from 008

- `pyyaml==6.0.3` is declared (pinned). The per-step allowances live under `budget` on every spec (`styles.Budget`: `judge_max_calls`, `search_max_queries`, `gen_max_per_short`); read them from `PlanRequest.style.numbers["budget"]` or `styles.StyleSpec.budget`.

## Blocked by

- Blocked by `issues/008-style-specs-loader-resolver.md`

## User stories addressed

- User story 37
- User story 38
- User story 40
- User story 63
