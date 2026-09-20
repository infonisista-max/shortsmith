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
