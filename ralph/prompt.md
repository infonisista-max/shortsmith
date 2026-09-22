# ISSUES

Read every open issue file in `issues/` (ignore `issues/done/`).

You will work on the AFK issues only, not the HITL ones.

Run `git log -n 5` to review recent work.

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
- `uv run pytest -q` to run the tests
- `uv run python -m shortsmith.smoke` to render the fixture clip end-to-end with the fake transcriber and fake planner

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

# SELF-CHECK BEFORE DONE

After the feedback loops pass, if your ticket touched the pipeline or
rendering: run the smoke, then READ out/qa.json yourself. If any T1-T4
check fails, diagnose and fix it before declaring the ticket done —
never report done with a failing T. You may also Read the contact-sheet
frame (contact.jpg) and compare PIP position, safe areas and caption
anchor against the numbers in the loaded style spec.

Objective checks are yours to consume. Taste verdicts are the operator's —
never rate your own output as good-looking.
