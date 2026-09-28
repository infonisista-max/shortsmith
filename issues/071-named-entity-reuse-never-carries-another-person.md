# 071 — A named-entity beat never carries the previous beat's picture of someone else

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Run04 (job `20260928-140620-f774e1`, vishva). Operator's phone verdict: "The Trump photo
carried forward to the wrong place once (on the King Saud line)." `out/rights.json`: b04
and b05 both show the Commons Trump portrait. b05 is the "किंग साऊद" lower-third beat.

The plan (`work/plan.json`):

- b04: `depicts: named_entity`, `query: "Donald Trump portrait"`, `asset_id: "trump"`,
  `source_intent: "search"`.
- b05: `depicts: named_entity`, `query: "King Saud bin Abdulaziz portrait"`,
  `asset_id: "ref1"`, `source_intent: "reuse"`.

Cause (`src/shortsmith/assets/__init__.py`, `source_assets`):

1. ref1, the owner portrait, was already at `broll.reuse_max` 2. The showings were b01,
   and b02's `saud_robes`, which `matching_reference` bound to the same file because
   "saud" is in its caption.
2. On b05, the planned ref and the caption match are both blocked (`:1290-1302`). That
   is the duplicate `reuse_max` log line.
3. `:1306-1310`: `source_intent == "reuse"` takes the carry-on branch meant for
   `number` / `quote` beats (`REUSING_KINDS`, `:263`). `walk.nearest()` is called with no
   subject and no `free_for`, so it returns the last image shown, b04's Trump. That image
   is shown at rung 0 with no judge.
4. The King Saud search is never asked. This breaks 056 (3): "a capped beat is sourced
   afresh".
5. Nothing downstream checks who is in a reused image. The judge and `name_evidence` run
   only on fresh search candidates. T8 and `grammar.py` count showings, and Trump's two
   are within the cap.

b07, b09, b13 and b15 hit the same cap through `matching_reference` only. Their
`source_intent` was `search`, so they fell through to the search and got correct King Saud
images.

What to change:

- **Only number and quote beats carry on the previous image.** Any other beat with
  `source_intent: "reuse"` whose planned asset is blocked is sourced afresh with its own
  `query` / `query_fallback`, as 056 (3) says. The log line names the blocked asset and
  says it searched.
- **A named-entity beat never borrows across entities.** The two late rescues are
  `walk.nearest(beat.subject_kind, …)` at the end of the ladder and any other `nearest`
  call that can reach a `named_entity` beat. They may only return an asset first sourced
  for the same entity: the same planned `asset_id` or owner ref, or a beat whose
  lower-third text or query names the same entity by `keywords()` overlap. Otherwise the
  beat takes the generated fallback or the gradient, as today, logged.
- **A test at the gate as well.** T8 adds a named-entity check. A `named_entity` beat
  showing an asset whose first showing was on a `named_entity` beat with a different
  lower-third fails T8, naming both beats. A number or quote carry-on is exempt.

## Acceptance criteria

- [ ] Run04's b01–b05 (copied into a test as plan JSON plus fake search results; no
      media) source b05 by searching "King Saud bin Abdulaziz portrait". It never shows
      `trump`. The job log line says the owner portrait was capped and the beat was
      searched.
- [ ] With every search failing, b05 gets the generated fallback or the gradient, never
      b04's image. A number beat after b04 still carries b04's image on.
- [ ] T8 fails on the run04 `assets.json` as it was, naming b04 and b05, and passes on the
      fixed sourcing. Smoke passes T1–T13 on explainer, vishva and fastfacts.
- [ ] Ruff, pyright and every test file are green in foreground chunks.
- [ ] Done note: the amendment line for 4.3 (a reuse on a named-entity beat never crosses
      entities; only number and quote beats carry on) for the operator to paste. Also
      what to check on run05: every named person's line shows that person.

## Blocked by

- Nothing.

## User stories addressed

- Operator, run04 QA (29 Sep 2026): "The Trump photo carried forward to the wrong place
  once (on the King Saud line)."
