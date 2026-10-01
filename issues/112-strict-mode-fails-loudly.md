# 112 — Strict mode: a job fails loudly instead of delivering a downgraded reel

## Type

Parent (split into 112a-112d under the context-budget rule). Operator, 2 Oct 2026.

## Why

The only output that counts is a reel the operator rates 6 or above. 111d and 111g (and
older nets from 094-098) optimise for "the job delivers". While the operator is testing,
they hide what he needs to see: with a simplified beat or a plain reel he cannot tell the
system's real quality from the net's downgrade. Delete nothing: every downgrade goes behind
one setting.

## The line (operator-approved, 2 Oct 2026)

- **A crash or a missing thing fails loudly in strict mode**, naming the beat and the cause.
  This covers rescue nets, asset repairs that substitute something worse, and the ladder
  steps that happen only because something crashed.
- **"Searched and found nothing better" is kept, and listed.** Sourcing not finding a good
  asset is the world, not a bug. The ladder (gradient, generated image, fallback bed,
  overlays dropped for want of a face-free spot) stays on in strict mode, but it is listed
  per beat as "what the system settled for".
- **A pre-render gate**: in strict mode, if too many beats settled for a gradient or a
  generated image, the job stops before rendering and shows the list (a fast stop with a
  reason beats a slow weak reel).
- **True fixes stay on in both modes**: format conversion (111a/111c), a byte-identical
  (same sha256) replacement, a wall/list playing its clip (111b), the 111e budgets and stall
  clock, and transient retries (095).

## Parts (in order)

- 112a: the switch, the per-job mode, the loud failure, and the rescue nets in the pipeline and editor
- 112b: the renderer's downgrade repairs (111b/111c/111d) behind the switch, and the pre-render gate
- **Stop here.** The operator runs one fresh job in strict mode before 112c/112d start.
- 112c: crash-caused fallbacks in sourcing, sound and the planner fail loudly in strict
- 112d: the "settled for" list on every job page, and both-mode tests across 111f

Sources for every site: the inventory of 2 Oct 2026, summarised in each part.
