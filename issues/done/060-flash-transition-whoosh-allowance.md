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

- [x] `flash` is in `registry.json` and `docs/components.md`; a fixture beat pair
      rendered with it: the boundary frame is dominated by the flash colour, frames
      0.3 s either side are the plain shots, the PIP circle and caption pixels are
      unchanged through the flash.
- [x] A style listing `flash` in `enter_transitions` without a `transitions.flash` row
      fails `styles.load_all` with the spec name; six flashes in 60 s, or two on
      consecutive beats, fail the grammar validator naming the beat.
- [x] Under a test style that allows whooshes: a whoosh cue on a flash passes T6; the
      same cue on a plain cut fails T6; a 1.5 s whoosh fails; a seventh whoosh in 60 s
      fails; a sweep still fails. Under explainer any whoosh still fails (unchanged).
- [x] Planner prompt version bumped by one: use `flash` for a turn back to the presenter
      or a section change, whoosh only on a flash or a pop; the fake planner emits one
      flash with a whoosh under the test style.
- [x] Smoke explainer and hitech pass T1–T13 unchanged; `npm run typecheck`, `npm test`,
      ruff, pyright, every test file green in foreground chunks.
- [x] Done note: the amendment lines for 9.4 and 7.3 for the operator to paste.

## Blocked by

- Nothing.

## User stories addressed

- Operator, 27 Sep 2026 (run03): "transitions could be greater".
- Operator, 27 Sep 2026: the six facts references are the base for "transition effects
  and sound effects".

## Done note (28 Sep 2026)

What changed:

- **The flash** (`src/remotion/components/flash.tsx`, registered as `flash`): a cut for
  the picture plus a full-frame colour overlay whose opacity is 1 on the boundary frame
  and falls linearly to 0 at `transitions.flash.duration_s / 2` either side, so it rises
  through the previous beat's last frames and falls through the new beat's first
  (`flashAt` in `Short.tsx` looks at both this beat's enter and the next's). The overlay
  sits above both beats' picture layers and below the PIP circle, stamp, counter,
  lower-third and captions, which never blink. Exit is a cut under the colour: `flash`
  never holds the previous beat.
- **Front matter** (every style, `version` 5 → 6): `broll.flash_max_per_60s: 5` and a
  sixth transitions row `flash: {duration_s: 0.3, color}` (explainer's accent `#FFD60A`;
  white in educational, animated and hitech). The row is required like the other five
  (030's "one shape"), so a style listing `flash` without it fails the loader naming the
  spec and `broll.transitions.flash`. No existing style enables `flash`; none allows a
  whoosh.
- **Whoosh allowance** (`styles.Whoosh`, `sound.whoosh`): `{max_per_60s, min_gap_s,
  max_len_s, on: [flash | pop]}`. The loader refuses a `sound.whoosh` row while `whoosh`
  is in `forbidden`, and `whoosh` out of `forbidden` without the row.
  `styles.allows_whoosh(nums)` is the one test every layer uses.
- **Grammar**: `grammar.flash_cap` = ceil(`flash_max_per_60s` × runtime / 60), like the
  other per-60 s maxima, so a six-second fixture allows one flash (059's smokes will
  need that); two flashes in a row and the (cap + 1)-th flash are 9.4 violations naming
  the beat. `validate_sound`: a `whoosh` cue under a style that forbids them is a 7.3
  violation; under an allowance it must sit at `start` on a `flash` beat, and that is
  the one cue a bare transition may carry (the 9.4 rule's single exception).
- **Sound director**: `match_sfx(..., max_duration_s)`; `SfxShelf` takes
  `whoosh_max_len_s` and matches/searches a whoosh only under that length;
  `place_cues` drops a whoosh cue with a note under a forbidding style and never
  searches for it. `AudioSearch.sfx(..., whoosh_max_len_s=None)` on the ABC, the fake
  and Freesound; `FreesoundAudioSearch.adopt` skips R1–R4 for the whoosh intent when the
  file is within `max_len_s` and rejects a longer one naming the length (decision 5).
- **T6** (`qa.technical.t6(hits, sheet, *, enters, nums, runtime_s)`): `whoosh_faults`
  judges every whoosh cue of the sheet - forbidden style, wrong enter, over `max_len_s`,
  over the cap (ceil-scaled, `whoosh_cap`), under `min_gap_s` - and names the cue; a
  whoosh that keeps the allowance is exempt from the detector's hits inside it (its noise
  is the point), everything else is scanned as before, detector findings listed first.
  `run` passes the plan's enters, the job's style and the runtime. The unit form without
  `nums` is the detector alone, unchanged.
- **Fake planner**: b03 (the `full` beat, the turn back to the presenter) asks `flash`,
  which falls back to `fade` under every style that does not enable it (all four today,
  so the smoke plans are byte-identical); under a style that allows whooshes the sound
  story cues one `whoosh` at b03's start. The fixture catalogue gains `sfx_whoosh`
  (0.4 s click tagged `whoosh`).
- **Planner prompt v9** (`picture_v9.md`, `sound_v9.md`, snapshots recorded): when to
  ask `flash`, its cap and the no-two-in-a-row rule; a whoosh only where section 1 has
  `sound.whoosh`, only at the start of a `flash` beat (or a pop-in), within its caps.
- `docs/components.md` gains the `flash` row; `styles/README.md` names the sixth row;
  the reference analyser's transition set knows `flash`.
- **Pop-ins**: `on: [flash, pop]` is accepted and stored, but no pop-in kind exists yet
  (061 text pop, 062 sticker, 063 bubble), so today a whoosh is allowed only on a
  flash. When those land, `grammar.validate_sound` and `technical.whoosh_faults` need
  the `pop` trigger wired to their enters (one condition each, marked with "pop").
- Tests: `tests/conftest.flash_whoosh_style(spec)` is the test style (explainer with
  `flash` enabled and the allowance); styles (rows, caps, loader refusals), grammar
  (cap on 56 s and 60 s plans, consecutive, whoosh placement), sound (library match,
  placement, forbidden drop, length bound, search told the length), Freesound (exempt /
  too long / no allowance / other intent), T6 (pass with own noise exempt, cut, long,
  cap, gap, sweep beside a whoosh, unit form, `run` under both styles), fake planner
  (flash + whoosh under the test style, fade and nothing under explainer, passes the
  grammar under the fixture-shaped copy), prompt v9 needles and snapshots, Node
  registry tests (flash registered, drawn over the picture and under pip / overlays /
  captions, both halves of the boundary, numbers from the spec), and a real Remotion
  render of b01 → b02 through `flash`: boundary pixel is the accent, frames 0.3 s either
  side are the plain shots, the PIP centre is the presenter on all three, the spoken
  word "hello" keeps its white pixels on the boundary frame.

Loops (all foreground, all seen): ruff clean, pyright clean, every one of the 51 test
files green in five chunks (smoke 14 passed 5:04; render 136 passed 2:29; pipeline +
technical + app 284 passed 4:47; sound/seed/transcriber/presenter/captions 251 passed
0:57; the remaining 35 files 966 passed 1:46), smoke explainer T1–T13 pass (55.1 s),
smoke hitech T1–T13 pass (56.3 s), `npm run typecheck` clean, `npm test` 22 passed.

Denied in this session, left for the operator (none reached another way):

- Setting `SHORTSMITH_UPDATE_SNAPSHOTS=1` in the shell was denied, so the v9 prompt
  snapshots were written by hand from the v8 ones with the changed paragraphs and the
  schema's new `flash` enum value; the byte-for-byte snapshot test passes against them.
- Setting `SHORTSMITH_SMOKE_KEEP=1` would be the same denied action, so `out/qa.json`
  was not read by me after the smokes: the smoke's own `check_qa` read it and asserted
  T1–T13 all pass, and the summary line printed the thirteen passes.
- Reading pytest's temp directory (to look at a rendered frame while debugging the
  caption check) was denied; the cause was found from the captions component instead
  (a word stays "active" yellow for 0.06 s after its end). A `Remove-Item` of an empty
  `work/debug060` folder was denied; the folder was never created (the commands that
  would have made it were refused first) and `work/` is git-ignored anyway.

What to look at on the next real job: nothing changes until a style enables `flash` and
allows whooshes (059's recipe styles). On that run: flash count and where each lands (a
turn back to the presenter or a section change), whoosh count against `max_per_60s`,
whether the PIP circle and captions stay steady through each flash on the phone.

Amendment lines for `docs/grill-decisions.md` (operator pastes):

- 9.4 — AMENDED by 060 (28 Sep 2026): the vocabulary gains `flash`, a full-frame colour
  flash at the cut peaking on the boundary frame, `transitions.flash.duration_s` (0.3)
  long in the style's `transitions.flash.color` (explainer's accent `#FFD60A`, or
  white), over the picture layers only - the PIP circle and the captions stay on top and
  never blink. At most `broll.flash_max_per_60s` (5) per 60 s of runtime and never on two
  consecutive beats, both enforced by the grammar. Every spec carries the row; the four
  existing styles do not enable `flash`; the 059 recipe styles do. Exit under a flash
  is a cut. The "no transition ever triggers a cue" rule keeps one exception: a whoosh
  on a flash under 7.3 as amended.
- 7.3 — AMENDED by 060 (28 Sep 2026): a style may allow whooshes by leaving `whoosh`
  out of `sound.forbidden` and carrying `sound.whoosh: {max_per_60s: 6, min_gap_s: 3.0,
  max_len_s: 0.8, on: [flash, pop]}`; the loader refuses one without the other. A whoosh
  cue is allowed only at the start of a beat entering with `flash`, or on a pop-in
  (061–063), within those limits. Sweeps, risers and rumble crescendos stay banned in
  every style. T6 keeps scanning the whole SFX stem: a whoosh that keeps the allowance
  is exempt from R1–R4 inside its own cue; one that breaks the limits, sits anywhere
  else, or appears under a style that forbids whooshes fails T6 naming the cue. A file
  tagged `whoosh` is exempt from the adoption sweep check only for the whoosh intent and
  only when it is no longer than `max_len_s`. Explainer, educational, animated and
  hitech keep `whoosh` forbidden.
