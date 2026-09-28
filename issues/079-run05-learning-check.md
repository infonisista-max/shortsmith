# 079 — Run05: does the learning work? The run04 recording again, plus one new recording, judged on the phone

## Type

HITL — operator steps with `.env` in place and network. The agent's part is preparing
commands and reading the outputs.

## Parent PRD

`issues/prd.md`

## What to build

The gate for the learning work agreed in the grill of 29 Sep 2026. New reference URLs are
added (081) only after this run shows the worked examples help.

### Operator steps, in order

1. `uv run python -m shortsmith.sound.seed retag` (068), if not already run.
2. Re-analyse the 12 references with prompt v2 (073's done note gives the command). Check
   two cards by eye.
3. Build the audio shortlist (075), put any drop-folder files in, and say yes/no on the
   listening page.
4. **Re-render the run04 recording** (King Saud, vishva, job `20260928-140620-f774e1`) as
   a new job. The script and footage are the same, so any difference comes from the
   learning.
5. `uv run python -m shortsmith.compare_plan <new job id>` (077): match share with and
   without examples.
6. **Record and run one new short** on a different topic. It also counts toward the
   day-14 gate (it runs through the normal job path, nothing special).
7. Phone verdict on both.

### Pass line (the operator's phone verdict decides; the numbers explain)

- For each run04 complaint, fixed / not fixed:
  - background music heard and fits the story;
  - a soft tick or short whoosh marks pop-ups and transitions, not every one;
  - nothing sounds unrelated to the screen (no ring);
  - pictures match what is said.
- Overall rating **≥ run04's rating + 1, and at least 7**. run04 was rated **4.5/10**
  (operator, 29 Sep 2026), so +1 gives 5.5 and the floor of 7 is the line that applies:
  **each run05 short must rate at least 7**.
- **"The examples help"** = both of:
  - the match share with examples is higher than without (step 5);
  - the operator does not mark "pictures don't match what I say".
- The comparison table (074) explains, it does not decide:
  - a red row whose effect the operator also heard becomes a ticket;
  - a red row nobody noticed is only logged here.

## Acceptance criteria

- [ ] Both jobs delivered, with `out/inventory.json` and the comparison table present.
- [ ] The phone verdict per complaint and the overall ratings recorded in this file and
      in `job.json.rating`.
- [ ] The `compare_plan` output recorded here.
- [ ] Decision recorded: go / no-go for 080–085, with the reason. A no-go names the
      tickets to write first.

## Blocked by

- 068, 069, 070, 071, 072, 073, 074, 075, 076, 077, 078

## User stories addressed

- Operator, 29 Sep 2026 (grill): measure that learning from the references worked; the new
  run05 recording counts toward the day-14 gate.
