# 060 — Flash transition, and a capped whoosh a style may allow

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Reference inventory (036, 12 shorts, ESTIMATED): 5 of the 12 use a short bright flash
between two shots — Dhruv Rathee Shorts `S5j-2CWYYwM` at 17 s (yellow, about 0.3 s, four
times in 60 s, each one back to the presenter, each with a whoosh), `QjwDTLPLJ6c` at 6 s
(light flare), `VSJzviqMO7k` and `bL3rUtUPYsc` (flash-fade), `nBihHUlYOQk` at 29 s (flash
wipe). Whooshes are 47 of the 85 sound effects across the 12 and appear in every one of
them, the operator's own three included (median about 3.5 per 60 s). Today 7.3 bans them:
every style's `sound.forbidden` lists `whoosh` and T6 checks the SFX stem.

Operator decision, paired review 28 Sep 2026 (amends 9.4 transition vocabulary and 7.3;
the operator records the lines in `docs/grill-decisions.md` from the done note):

1. **A new transition `flash`:** a full-frame colour flash at the cut, peaking on the
   boundary, `transitions.flash.duration_s` long (0.3) in the style's `flash.color`
   (explainer's accent `#FFD60A`, or white). It covers the picture layers only: the PIP
   circle and the captions stay on top and never blink.
2. **Flash cap:** at most `broll.flash_max_per_60s` (5; the references use at most 4)
   and never on two consecutive beats. The grammar validator enforces both.
3. **Whoosh allowance, per style:** a style allows whooshes by leaving `whoosh` out of
   `sound.forbidden` and carrying `sound.whoosh: {max_per_60s: 6, min_gap_s: 3.0,
   max_len_s: 0.8, on: [flash, pop]}`. A whoosh cue is allowed only on a `flash`
   transition or on a pop-in (the enters of 061 text pop, 062 sticker, 063 bubble),
   within those limits. Sweeps, risers and rumble crescendos stay banned in every style.
   T6 keeps checking the whole SFX stem and fails a whoosh that breaks the limits or
   sits anywhere else.
4. **Existing styles unchanged:** explainer, educational, animated and hitech keep
   `whoosh` forbidden and do not enable `flash`. The recipe styles of 059 turn both on.
5. **Where whoosh files come from:** the same way as every other SFX (tagged library,
   then 054's Freesound ladder, CC0 / CC BY only). A file tagged `whoosh` is exempt from
   the adoption sweep check only for the whoosh intent and only when it is no longer
   than `max_len_s`.

## Acceptance criteria

- [ ] `flash` is in `registry.json` and `docs/components.md`; a fixture beat pair
      rendered with it: the boundary frame is dominated by the flash colour, frames
      0.3 s either side are the plain shots, the PIP circle and caption pixels are
      unchanged through the flash.
- [ ] A style listing `flash` in `enter_transitions` without a `transitions.flash` row
      fails `styles.load_all` with the spec name; six flashes in 60 s, or two on
      consecutive beats, fail the grammar validator naming the beat.
- [ ] Under a test style that allows whooshes: a whoosh cue on a flash passes T6; the
      same cue on a plain cut fails T6; a 1.5 s whoosh fails; a seventh whoosh in 60 s
      fails; a sweep still fails. Under explainer any whoosh still fails (unchanged).
- [ ] Planner prompt version bumped by one: use `flash` for a turn back to the presenter
      or a section change, whoosh only on a flash or a pop; the fake planner emits one
      flash with a whoosh under the test style.
- [ ] Smoke explainer and hitech pass T1–T13 unchanged; `npm run typecheck`, `npm test`,
      ruff, pyright, every test file green in foreground chunks.
- [ ] Done note: the amendment lines for 9.4 and 7.3 for the operator to paste.

## Blocked by

- Nothing.

## User stories addressed

- Operator, 27 Sep 2026 (run03): "transitions could be greater".
- Operator, 27 Sep 2026: the six facts references are the base for "transition effects
  and sound effects".
