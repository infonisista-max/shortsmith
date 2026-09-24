# 044 — Cost panels: per-step cash and tokens side by side, running average, daily budget guard

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Cost measurement as a product feature. The job page shows the per-step cost breakdown with cash INR and subscription tokens (valued at the api-equivalent rate) side by side, the job total, the over-soft-cap flag, and a running average cost per passing short across jobs. `BUDGET_INR_PER_DAY` reached closes the upload form with "daily budget reached" until midnight IST.

Covers PRD `app` (cost panels), `ledger` (daily), `jobs` (running average). Decisions 11.3, 5.6, 8.3.

## Acceptance criteria

- [x] Job page cost table: one row per step with cash INR and tokens plus their api-equivalent INR, a total row, and the soft-cap flag when set.
- [x] Running average per passing short computed from all `passed` jobs' ledgers, shown on the job page and the job list. (Job page done. The job list does not exist yet, so that half is handed to 045 in a note.)
- [x] `ledger.cash_spent_today(now)` ≥ `BUDGET_INR_PER_DAY` → the upload form is closed with "daily budget reached" and reopens after midnight IST (fake clock test at 23:59 and 00:01 IST).
- [x] Tokens never appear in any cash total (test).

## Notes from 011

- `app.state.ledger.cash_spent_today(data_dir, now)` and `settings.budget_inr_per_day` (default 500) exist; the per-job caps default to `None` (disabled) per the operator's 11.3 rider and are set from the ledger data later. The job page already shows the rows, the cash total and the api-equivalent token value; the running average is this ticket's.

## Blocked by

- Blocked by `issues/011-ledger-prices-caps.md`
- Blocked by `issues/043-retry-from-step-error-strings.md`

## User stories addressed

- User story 38
- User story 40
- User story 42
