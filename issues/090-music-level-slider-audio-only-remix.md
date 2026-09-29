# 090 — A music-level slider on the job page: the whole reel's bed, remixed audio-only in seconds

## Type

AFK — no network, no keys, no new packages. No `src/remotion` change.

## Parent PRD

`issues/prd.md`

## Why

Operator, 30 Sep 2026: "Put a music-volume slider on the job page that sets the bed level
for the whole reel, remixes only the audio so it is quick, and remembers my setting." The
ear is the judge (CLAUDE.md), so the ear gets a control. Until now the only fix for a bed
that is too loud or too quiet was a new ticket and a full re-render.

Operator's taste answers (30 Sep 2026): **a wide range**, from "barely there" to "up front
with the voice", and **the ear wins**. A setting the voice checks dislike is applied
anyway, with a note.

## What to build

- **The slider.** On a delivered job's page, beside the player and the rating slider: one
  slider for the bed level of the whole reel. The ends are labelled in words ("barely
  there" … "up front"), with a mark at the job's starting level. No dB appears on the
  control; the existing balance line keeps its numbers for the reviewer.
  - The range and step are data, not code: a new `assets/audio/level.yaml`, validated at
    startup. One file for all styles (the operator's answer in 091). The value is an offset
    in dB from the style's **starting level**. That is `bed_db_under_voice` full-band today,
    or 089's target on its measure if 089 has landed, so the slider does not wait on 089.
    The ends come from the ear evidence in 089's table. The quiet end goes past run04's
    not-heard level. The loud end goes past run03's "a bit loud" (3.1 dB over its asked
    level), because the range is wide. The comments say so. Pick a step small enough to
    hear one notch as a small change.
- **The audio-only remix.** Moving the slider and pressing "Remix audio" rebuilds only the
  bed at the new level (076's segments keep their relative levels), then the duck, the
  premix, the master (two-pass loudnorm as in `mux`), and the remux with the picture stream
  copied (`-c:v copy`, as `mux` already does). No Remotion, no planner, no asset calls.
  - It works from the stems under `work/stems/`. A swept job (`swept_at` set) shows the
    slider disabled, with the reason.
  - The delivered file is replaced only after the new master passes T4. On any failure the
    old file stays and the page shows the error. The replacement is atomic (write beside,
    then rename).
  - `balance.json` is re-measured and the critic's balance input reads the new one. The
    rights log is unchanged, since the bed is the same.
- **The ear wins.** A slider setting is never repaired (no dip, no lowering) and never
  refused. If the re-measured margin is under the floor or over the ceiling, the job page
  shows a plain note: "the check thinks the music may cover your voice here" or "may be hard
  to hear on a phone speaker". The file is still delivered.
- **Recorded.** `job.json` gets `music_level`: the offset, the name of the level measure
  it is relative to (`full_band` today), `set_by` (`default` | `slider`), and when it was
  set. The job log gets one line per remix with the offset and the
  re-measured margin.

## Acceptance criteria

- [ ] App test (fixture job with stems): a remix at a louder setting gives a higher
      measured bed level and a smaller margin in `balance.json`. The picture stream is
      byte-identical to the one before (ffprobe stream hash). No Remotion driver call is
      made (the fake asserts it was not invoked).
- [ ] The new master passes T4. A forced failure leaves the old file in place and shows
      the error.
- [ ] An over-the-floor setting is delivered with the note, and no repair line is logged.
- [ ] A swept job shows the slider disabled with its reason.
- [ ] `level.yaml` loads, and a value off its range stops startup naming the key.
- [ ] A remix of the 6 s fixture takes under 15 s on this machine. The done note gives the
      measured time for a 60 s job if one with stems is on disk.
- [ ] Ruff, pyright and every test file are green in foreground chunks. The smoke passes
      T1–T13.

### Operator step, in the done note

On run05's King Saud re-render (079 step 4), within 24 h of its upload (the sweeper
then takes its stems; run04's are already due), move the slider, remix, and play the
file on the phone speaker.

## Blocked by

None - can start immediately. Offsets carry the name of their level measure, so a later
089 does not misread them.

## User stories addressed

- Operator, 30 Sep 2026: "a music-volume slider on the job page that sets the bed level
  for the whole reel, remixes only the audio so it is quick".
