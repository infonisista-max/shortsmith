# 112c — Crash-caused fallbacks in sourcing, sound and planning fail loudly in strict

## Type

AFK. Part of 112. Starts only after the operator's strict-mode job following 112b, and
may be re-scoped by what that job showed.

## What to build

These go through `quality.downgrade`. Each one happens because something crashed or went
missing, not because nothing better was found:
- Any exception on one beat → gradient (`assets/__init__.py` ~l.1648, 096).
- A judge error → candidates sourced unjudged (`assets/judge.py` ~l.452). A spent judge
  budget is "settled": list it, don't stop.
- A generator error → nothing generated, and the ladder goes on (`assets/generate.py`
  ~l.457).
- The picked bed is missing → the director picks (101, sound); the mix fails → voice only.
- The planner fails over from the Claude Code CLI to the API on another model (095). In
  strict mode, fail loudly; the same-model transient retry stays.

The searched-and-found-nothing rungs stay on and are listed (112d): the 096 ladder, the
opening/number beat gradient, the re-dress, a Freesound or facts bed, "voice and hits
only", and an unmeasurable clip motion that plays from its start.

## Acceptance

A strict test per site (fails, naming the beat or step and the cause); forgiving is
unchanged; every test file is green; smoke delivers.
