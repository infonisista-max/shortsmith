# 089 — The bed is levelled by what a phone speaker plays: one measure that puts both ear-approved beds at the same place, or a stop

## Type

AFK — no network, no keys, no new packages. Every file it needs is on disk under
`work/089/` (git-ignored) before the run (see "Files").

## Parent PRD

`issues/prd.md`

## Why

The operator's ear gives two levels that were right and one that was not heard.
Speech-band margins are those of today's `sound.audibility` (250–4000 Hz):

| Point | Bed | Level the ear called right | 250–4000 Hz margin there | Ear |
|---|---|---|---|---|
| A: run03 (`20260927-140915-bbad1c`) | `freesound_738836`, "middle eastern mysterious" | run03's level minus 3.1 dB (the operator's "30 % quieter", which 056 applied: −14 full-band) | about 12.5 (9.4 measured + 3.1) | "a bit loud" before, so this is the asked level |
| B: Dyson v2 (old engine) | Trap Hamza (Mixkit 267), 77–79 % sub-bass | about −10.4 full-band under the voice | about 21.8 (25.4 at −14, minus 3.6) | "heard clearly", a normal level |
| C: run04 (`20260928-140620-f774e1`) | `freesound_557546`, a car exhaust (not music) | none: −14 full-band was not heard | 28.7 | not heard |

A and B are both "right", yet in the 250–4000 Hz band they sit about 9 dB apart. So that
band does not describe what the ear hears. Levelling every bed to B's 21.8 would put an A-like
bed about 9 dB under the asked level, which is run04's "not heard" again. The likely miss
(operator, 30 Sep 2026): what a phone plays of a trap bed is its hats and the 808's upper
edges, above 4 kHz, which the band cuts off.

Operator, 30 Sep 2026: "a normal level that never covers my voice and keeps the viewer
engaged". No dB number is chosen by the operator.

## Files (the check runs on the real beds, not on synthetic ones)

- **Voice:** `work/089/run04_voice.wav`, copied on 30 Sep 2026 from run04's
  `work/stems/voice.wav`. run04 is past the sweeper's 24 h, so its `work/` goes on the
  next sweep. run03 was swept on 28 Sep, so its own voice stem is gone. Same presenter,
  same 7.3 voice chain. The done note states this substitution.
- **A's bed:** `work/089/freesound_738836.mp3`, the HQ mp3 preview, which is the variant
  `sound.freesound` fetched for run03 (preview-hq-mp3 first). The operator saves it with
  the adapter before the run (https://freesound.org/s/738836/; run03's `out/rights.json`
  has no audio rows, so there is no hash to check it against).
- **B's bed:** `assets/audio/inbox/mixkit-trap-hamza-267.mp3` (operator, 30 Sep 2026).
- **C's bed:** `work/089/run04_music.wav`, copied from run04's `work/stems/music.wav` (the
  car recording, already levelled at −14).
- If any of the four is missing: **stop before any code change**, add a note naming the
  missing file, and commit only the note.

## What to build

1. **Declare the candidate measures before measuring.** This keeps the choice from fitting
   two points after the fact. Each measure compares the bed with the voice after one
   filter:
   1. today's 250–4000 Hz band (expected to fail; it is the baseline);
   2. a phone-speaker band: a high-pass at **300 Hz** and **no** upper cutoff below
      16 kHz. 300 Hz is the commonly quoted lower limit of a phone's built-in speaker. It
      is an approximation, fixed here in the ticket so it cannot be tuned to the two
      points (the run is offline, so there is no lookup);
   3. K-weighted loudness (ffmpeg `ebur128`, already used by `loudnorm`) after the same
      phone high-pass.
   No new package. Numpy and ffmpeg filters only.
2. **Measure A and B on each candidate** at their ear-approved levels (A: `freesound_738836`
   levelled to −14 full-band under the voice; B: Trap Hamza levelled to −10.4). Also
   measure C at its −14. Write the table (every candidate × A, B, C) into the done note, or
   into the stop note.
3. **The pass line for a measure:**
   - A and B land within 2 dB of each other. That is the agent's engineering tolerance,
     about one slider notch, not a taste number.
   - C lands further under than both, by more than that tolerance.
   - If several pass, take the first in the declared order. If **none** passes: **stop.**
     Change no level code and no front matter, leave the ticket open with the table and
     what it suggests, and commit only that note. The operator decides the next step. No
     target ships on a measure the ear contradicts.
4. **If one passes, it becomes the control.**
   - The target is the mean of A and B on that measure. It goes into all seven styles'
     `sound` front matter as a new number, with a comment naming the measure, the files, the
     levels and the date.
   - The director levels each bed (and each 076 segment's bed) to the target on that
     measure. Ducking, swells and drops still move relative to that level.
   - The floor and ceiling are re-expressed on the same measure. The floor sits between the
     target and run03's "a bit loud" level (A + 3.1 dB louder). The ceiling, which 088
     applies only to unheard beds, sits between the target and C. Each value's comment
     gives its evidence row.
   - The full-band window `bed_accept_db` stops being a pass/fail on level. What remains is
     one upper guard (no bed louder full-band than B's −10.4 plus a stated headroom), so a
     huge sub-bass bed cannot eat the master's loudness budget in `mux`.
   - `styles.load_all` refuses floor ≥ target or target ≥ ceiling. `balance.json` and the
     job page show the measure's name and the target beside the measured value.
   - 091's remembered offset: if it is already built, a remembered offset recorded under a
     different level measure is ignored, with a log line (091 stores the measure's name).
   - A bed that cannot reach the target (silent on the measure, or needing a full-band
     level over the guard) walks to the next candidate as in 056/069, with a line naming
     both numbers.
5. **Listening files for the operator:** write `work/089/A_738836_under_run04.wav` and
   `work/089/B_trap_hamza_under_run04.wav`, each bed under run04's voice at the level the
   new measure sets. On a stop, write them at the ear-approved levels from step 2 instead,
   so the operator can confirm the two points themselves.

## Acceptance criteria

- [ ] The measures are exactly the three declared above, and no cutoff is changed.
- [ ] A test measures A, B and C on the real files (skipped with a reason when the
      git-ignored files are absent, so CI and the smoke never depend on them). On the
      chosen measure it asserts A and B within 2 dB and C under both by more than 2 dB.
- [ ] If none passes: no source or front-matter change, the table is in the ticket, and
      the ticket stays open.
- [ ] If one passes: synthetic ffmpeg beds in the unit tests (a sub-bass drone with hats
      above 4 kHz, and a mid-band pad) both come out at the target within 0.5 dB. A 076
      two-bed reel is levelled per segment. All seven styles carry the target, floor,
      ceiling and guard with evidence comments, bumped versions and updated pins.
      `load_all` refuses the orderings above.
- [ ] Ruff, pyright and every test file are green in foreground chunks. The smoke passes
      T1–T13 on explainer, vishva and fastfacts (T4: the master still hits −14 LUFS).

### Operator step, in the done note

Play the two `work/089/` files on the phone speaker. These are beds the operator has
judged: run03's bed and the Dyson bed, not run04's exhaust. Both should sound like "a
normal level, clearly there, never over my voice". After 088's Trap Hamza approval, 093's
picker puts Trap Hamza under run05's King Saud re-render (079 step 4) on its job page for
the full-reel check.

## STOPPED (afk, 30 Sep 2026): no declared measure passes; no target ships

All four files were on disk. The three measures were declared as written above (no
cutoff changed) and run once on the real files. **None passes**, so no level code, front
matter, test or style changed. This note is the only commit. The operator decides the
next step.

**How it was measured** (`work/089/measure.py`, git-ignored, re-runnable with
`uv run python work/089/measure.py`):
- Voice is `run04_voice.wav` (59.5 s, mono, mean −19.10 dB). run03's own voice stem was
  swept, so run04's stands in: same presenter, same 7.3 chain.
- Each bed was looped/trimmed to the voice length and kept in its own channel layout, as
  `_bed_stem` does (A and B are stereo, C is mono). Its gain was converged until the median
  of its 1 s RMS windows sat at the ear level under the voice mean (the 7.3 yardstick):
  A −14.00, B −10.40, C −14.00.
- Margin = voice − bed on each measure. Measures 1 and 2 use `volumedetect` mean after the
  filter. Measure 3 uses integrated loudness from ffmpeg's R128 (`loudnorm` analysis) after
  `highpass=f=300`.
- Cross-check: B on measure 1 is 21.7 and C is 28.7, matching the ticket's 21.8 and 069's
  28.7. A is 14.0, not the ticket's ~12.5, because run04's voice replaces run03's.

| Measure (margin, dB) | A 738836 @ −14 | B Trap Hamza @ −10.4 | C exhaust @ −14 | \|A−B\| (pass ≤ 2) | C − max(A,B) (pass > 2) | Pass |
|---|---|---|---|---|---|---|
| 1. 250–4000 Hz band | 14.0 | 21.7 | 28.7 | 7.7 | 7.0 | no |
| 2. phone band, high-pass 300 Hz | 13.9 | 21.3 | 30.0 | 7.4 | 8.7 | no |
| 3. K-weighted, after high-pass 300 Hz | 11.1 | 18.0 | 28.9 | 7.0 | 10.9 | no |

**What the table suggests (for the operator, not acted on):**
- Removing the 4 kHz cutoff barely moves B (21.7 → 21.3). So what separates A and B is
  **not** energy above 4 kHz, which was the ticket's hypothesis. K-weighting closes only
  0.7 dB of the gap. On all three measures, B sits about 7 dB further under the voice than
  A, yet both were called right.
- C is separated on every measure, including today's band. So the ceiling side works. It
  is the target that no mean-energy measure puts in one place.
- Possible readings, none tested here (that would mean fitting a fourth measure to two
  points): (a) the ear follows transients, like trap hats and 808 attacks, more than mean
  energy, so a peak or upper-percentile window measure might line up where a mean does
  not; (b) the two verdicts were given in different settings (A: this engine, run03's
  voice, a full reel; B: the old engine's Dyson master), so they may not be one scale;
  (c) "right" covers a range, and A and B are its two ends. That would mean a window
  (floor under A, ceiling over B), not a single target.
- Side finding: folded to mono first (as most phone speakers play) and re-levelled to the
  same full-band median, B's measure 1 margin is 24.5 instead of 21.7. A's barely moves
  (13.9). Trap Hamza's mid and high stereo content partly cancels in the fold, while its
  centred sub-bass does not. A phone-speaker measure may need the mono fold
  as well as the high-pass. That would be a new declared measure for the operator to
  approve, not something to pick after the fact.

**Listening files (step 5, stop branch: the ear-approved levels from step 2):** both are
stereo, 48 kHz, 59.5 s, with the bed under run04's voice, in `work/089/`:
- `A_738836_under_run04.wav`: A at −14.
- `B_trap_hamza_under_run04.wav`: B at −10.4.
- Also `C_exhaust_under_run04.wav` (C at −14) for comparison, and the levelled beds alone
  as `{A,B,C}_bed_levelled.wav`.

**Operator step:** play A and B on the phone speaker. If both sound like "a normal level,
clearly there, never over my voice", the two points hold and a new measure has to be
declared (see the readings above). If one of them no longer sounds right at this level,
correct that point by ear. The run can then be repeated with the corrected level on the
same three measures, without changing any code.

Acceptance status: the first box (exactly the three measures) and the third box (stop
branch: no source or front-matter change, the table is here, the ticket stays open) are
met. The second box (a real-file test on the chosen measure) and the fourth box (build)
do not apply, because no measure was chosen. 090 is not blocked by this ticket (its
offsets carry their measure's name).

## Blocked by

- `issues/088-ear-approved-beds-pass-the-ceiling.md` (same functions and front matter;
  088 changes the ceiling's scope, this ticket its measure and value).

## User stories addressed

- Operator, 30 Sep 2026: "a normal level that never covers my voice and keeps the viewer
  engaged … run03 a bit loud, run04 not heard."
- Operator, 30 Sep 2026 (review of this ticket): both ear points must land near the
  levels the ear approved, or the afk run stops and reports instead of shipping a target.
