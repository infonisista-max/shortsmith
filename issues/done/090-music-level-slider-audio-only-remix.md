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

- [x] App test (fixture job with stems): a remix at a louder setting gives a higher
      measured bed level and a smaller margin in `balance.json`. The picture stream is
      byte-identical to the one before (ffprobe stream hash). No Remotion driver call is
      made (the fake asserts it was not invoked).
- [x] The new master passes T4. A forced failure leaves the old file in place and shows
      the error.
- [x] An over-the-floor setting is delivered with the note, and no repair line is logged.
- [x] A swept job shows the slider disabled with its reason.
- [x] `level.yaml` loads, and a value off its range stops startup naming the key.
- [x] A remix of the 6 s fixture takes under 15 s on this machine. The done note gives the
      measured time for a 60 s job if one with stems is on disk.
- [x] Ruff, pyright and every test file are green in foreground chunks. The smoke passes
      T1–T13.

### Operator step, in the done note

On run05's King Saud re-render (079 step 4), within 24 h of its upload (the sweeper
then takes its stems; run04's are already due), move the slider, remix, and play the
file on the phone speaker.

## Done (afk, 30 Sep 2026)

- **Scale:** `assets/audio/level.yaml` has `min_db -12`, `max_db +8`, `step_db 2`, and the
  labels "barely there" / "up front". The quiet end is 12 dB past run04's not-heard level
  (offset 0 = −14). The loud end is 4.9 dB past run03's "a bit loud" (+3.1), which puts the
  bed at −6 under the voice. One notch is 2 dB, 089's "about one slider notch". The stated
  ranges are: min in [−24, 0), max in (0, 24], step in (0, 6], and 0 must sit on a notch.
  `sound.level.load_scale` runs in `create_app`. A value off its range stops startup, and
  the error names the key.
- **Remix** (`sound.level.remix`, `sound.relevel`): the first remix copies the delivered
  bed stems (`music.wav` and 076's `music.N.wav`) into `work/stems/start/`. Every remix
  starts from those copies. One gain puts the bed at `bed_db_under_voice + offset`
  (full-band median), so offsets never add up and the segments, envelope and dip keep
  their relative levels. Then come the duck, the premix with the existing `sfx.wav`,
  `render.master`, and `render.remux` (the `-c:v copy` mux, now shared with `mux`). All of
  it is built in `work/stems/remix/` and `out/short.remix.mp4`. The stems and
  `balance.json` move in, and the short is renamed over the old one, only after T4 passes
  on the new file. Any failure leaves the old files in place.
- **Ear wins:** `balance.json` is re-measured and written with its problems as measured
  (the critic reads it). The repair ladder never runs, and the carried-over `repairs` and
  `dip_db` describe the starting mix. The plain notes ("may cover your voice here" / "may
  be hard to hear on a phone speaker") come from the lowest and highest speech-band
  margins, whole stem and windows. They are stored in `job.json` `music_level.notes` and
  shown under the slider.
- **Recorded:** `mux` writes `music_level` (0, `full_band`, `default`) when a bed plays.
  A remix writes (offset, `full_band`, `slider`, time, notes) and one
  `music level: slider offset +N dB (full_band), bed …, speech-band margin …` line in
  `job.log`.
- **Page/route:** `POST /jobs/<id>/music-level` (field `offset`). A swept job or one with
  no bed gets 409, and the slider is disabled with the same sentence. An offset off the
  scale gets 422. A failed remix gets 500 with the error, and the old short stays. The
  control shows no dB.
- **Timing:** the 6 s fixture remixes in well under 15 s (the test asserts it). A copy of
  run04 (59.5 s, the only job with stems on disk; copied to `work/090/job`, the
  operator's job untouched) took **14.0 s** per remix (`work/090/time_remix.py`,
  git-ignored). On that copy, +4 put the bed at −10.0 and −6 at −20.0. Both got the
  "hard to hear on a phone speaker" note (run04's exhaust, margin 24.7 / 34.8), which
  matches 069.
- Not done here (by design): `qa.json` keeps the T4 of the original render. The remix
  runs its own T4 gate on the new file before it replaces the short. No `src/remotion`
  change.

### Operator step

On run05's King Saud re-render (079 step 4), within 24 h of upload (the sweeper then
takes its stems), move the slider, press "Remix audio", and play the file on the phone
speaker.

## Blocked by

None - can start immediately. Offsets carry the name of their level measure, so a later
089 does not misread them.

## User stories addressed

- Operator, 30 Sep 2026: "a music-volume slider on the job page that sets the bed level
  for the whole reel, remixes only the audio so it is quick".
