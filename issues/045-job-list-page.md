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

## Blocked by

- Blocked by `issues/044-cost-panels-daily-budget.md`

## User stories addressed

- User story 54
