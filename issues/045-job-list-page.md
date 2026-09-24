# 045 — Job list page: last fifty jobs with status, rating and cost

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

`/jobs` lists the last fifty jobs newest first with status, rating, cash cost, elapsed or finished time and a link to each job page, behind the passcode. Swept jobs show their retention state.

Covers PRD `app` (job list), `jobs.list_recent`. Decisions 11.1, 2.2.

## Acceptance criteria

- [ ] `jobs.list_recent(data_dir, n=50)` reads `job.json` files only, sorted by creation time, tolerant of a job directory mid-write.
- [ ] `GET /jobs` renders the table; jobs past 24 h show "inputs swept", past 7 days are absent.
- [ ] Test with the test client over sixty synthetic job directories shows exactly fifty.

## Notes from 044

- 044's criterion "running average shown on the job page and the job list" left the job list half to this ticket, because the list did not exist yet. Show `ledger.running_average(data_dir)` above the table. It returns `None` until a job has passed; otherwise it carries `passed`, `cash_inr` and `inr_equivalent`. The job page's `_ledger_block` in `app.py` has the wording.
- Use `ledger.cash_total(record)` for each job's cash cost. Tokens never go into cash.

## Blocked by

- Blocked by `issues/044-cost-panels-daily-budget.md`

## User stories addressed

- User story 54
