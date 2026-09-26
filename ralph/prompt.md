# ISSUES

Read every open issue file in `issues/` (ignore `issues/done/`).

You will work on the AFK issues only, not the HITL ones.

Run `git log -n 5` to review recent work.

Run `git status`. If tracked files are modified, a previous session was
killed mid-ticket. Do NOT select a new ticket. Work out which ticket the
changes belong to from the issue files and `git log`, verify the work
against that ticket's acceptance criteria, finish it, and commit it.
Finishing it counts as this session's one ticket. If the changes match no
ticket, stop and report — never commit work you cannot attribute.

If all AFK tasks are complete, output <promise>NO MORE TASKS</promise>.

# TASK SELECTION

Pick the next task. Prioritize tasks in this order:

1. Critical bugfixes
2. Development infrastructure

Getting development infrastructure like tests and types and dev scripts ready is an important precursor to building features.

3. Tracer bullets for new features

Tracer bullets are small slices of functionality that go through all layers of the system, allowing you to test and validate your approach early. This helps in identifying potential issues and ensures that the overall architecture is sound before investing significant time in development.

TL;DR - build a tiny, end-to-end slice of the feature first, then expand it out.

4. Polish and quick wins
5. Refactors

# EXPLORATION

Explore the repo.

# IMPLEMENTATION

Implement with strict TDD: write a failing test first, run it and watch it fail, write the minimal code to pass, refactor, repeat.

# FEEDBACK LOOPS

Before committing, run the feedback loops, in this order, and fix everything they report:

- `uv run ruff check .` to lint
- `uv run pyright` to type-check
- `uv run pytest -q <test files>` to run the tests, in foreground chunks of under 8 minutes each (group by test file); never one full-suite run: it outlives the 10-minute tool ceiling, and a backgrounded suite ends a -p session with work uncommitted
- `uv run python -m shortsmith.smoke` to render the fixture clip end-to-end with the fake transcriber and fake planner

If anything under `src/remotion/**` changed in this session — any file, any
edit, including a comment-only edit — two more loops are mandatory, run
after the four above and before the commit:

- `npm run typecheck`
- `npm test`

"Only a comment changed" is not a reason to skip them.

# COMMIT

Make a git commit. The commit message must:

1. Include key decisions made
2. Include files changed
3. Blockers or notes for next iteration

# THE ISSUE

If the task is complete, move the issue file to `issues/done/`.

If the task is not complete, add a note to the issue file with what was done.

# FINAL RULES

ONLY WORK ON A SINGLE TASK.

Never read, print, or commit the `.env` file. Never call a paid API inside tests or smoke; tests use the Fake implementations.

Dependencies only via `uv add`. If a task needs a new dependency that is not already in pyproject.toml, add a note to the issue and mark it HITL instead of installing it.

## Session discipline
- One ticket per session. After the done-commit, STOP. Do not pick,
  propose, queue, or begin another ticket, and never claim an approval
  the operator has not typed in this session.
- Tickets marked HITL are never self-selected. Work a HITL ticket only
  when the session's launch prompt names it.
- If your ticket needs a package that is not installed, do not install
  it: add a BLOCKED note to the ticket and stop.
- Never stop with work in limbo. Before you stop for any reason — done,
  blocked, or no tasks left — wait for any running feedback loop to
  return, then either commit (only with every loop green) or leave the
  tree dirty AND write its exact state into the ticket file.
  Dirty-and-silent is the one forbidden ending.
- Never commit merely to satisfy that rule. Red loops plus a dirty tree
  is a correct ending — it is the signal the next session needs.
- In afk / `-p` mode every loop (the four above, and the two npm loops
  when they apply) runs in the FOREGROUND: never as a background task,
  never with run_in_background, never detached to a log you read later.
  A loop whose result you did not see did not run. If a loop's result is
  not in front of you — it ran in the background, the output was cut
  off, the task was lost — the session does not end: re-run that loop in
  the foreground and read its result. Only a seen result counts toward
  "every loop green".

# SELF-CHECK BEFORE DONE

After the feedback loops pass, if your ticket touched the pipeline or
rendering: run the smoke, then READ out/qa.json yourself. If any T1-T4
check fails, diagnose and fix it before declaring the ticket done —
never report done with a failing T. You may also Read the contact-sheet
frame (contact.jpg) and compare PIP position, safe areas and caption
anchor against the numbers in the loaded style spec.

Objective checks are yours to consume. Taste verdicts are the operator's —
never rate your own output as good-looking.
