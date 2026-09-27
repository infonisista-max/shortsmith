# 054 — Music and hits are always present, licence-safe, and the log says why

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

F1 (job `20260927-041728-656506`) went out with no bed and no cues: `work/sound.json`
asked for a bed ("Himalayan spiritual documentary, tanpura drone with soft tabla pulse and
low synth" / "mysterious, contemplative, quietly insistent, investigative"), yet
`work/audio_rights.json` is `[]` and T6 reports no SFX stem. The reason was written
nowhere: the mix notes never reach `job.log` or `render.log`. From the code:

- `FreesoundAudioSearch.beds` searches with the whole theme sentence plus the whole mood
  sentence as one query, which a text search is unlikely to match; an HTTP error is
  swallowed into "no hits".
- The runtime search covers beds only. SFX come only from the local catalogue, which is
  empty until 025 seeds it, so a short has no floor hits and no cues.
- Freesound results are adopted whatever their licence; a CC BY-NC track on a monetized
  channel is not safe.

Operator decisions, 27 Sep 2026 (amend 7.2; `docs/grill-decisions.md` is updated by the
operator from the done note):

1. Every job's sound decisions are in `job.log`: the bed chosen and from where, or why
   none; each cue placed, fell back or dropped; each search query, its HTTP status and
   hit count.
2. The bed search goes from specific to broad until something is adopted: a few plain
   keywords drawn from the bed query's theme and mood (not the full sentences), then mood
   words only, then the style's default bed words (a new `sound.default_bed_query` in
   each style's front matter; explainer e.g. "cinematic ambient documentary"). Stop at
   the first adoption.
3. SFX are searched the same way when the catalogue has no match for an intent or a
   floor hit (bass, drum, thump first), and every fetched SFX passes the 7.3 sweep
   detector before adoption; a hit is rejected and the next candidate tried.
4. Only CC0 and CC BY are adopted, for beds and SFX alike (filter in the request and
   checked again on the result). The licence and author stay in the rights row and in
   `out/credits.md`.
5. A short that goes out voice-only (no key configured, every search empty) says why in
   one line on the job page, not only in the log.

## Acceptance criteria

- [ ] With a fake search that records its calls: the queries run specific to broad,
      each is at most six words, and the style default is the last try.
- [ ] A request to Freesound carries the CC0 / CC BY licence filter; a result with any
      other licence is never adopted even if the API returns it.
- [ ] An empty SFX catalogue plus a working search still yields the floor hits and the
      matched cues, each SFX having passed the sweep detector (a fake SFX that trips R1
      is rejected and the next taken).
- [ ] `job.log` holds one line per search (source, query, status, hit count) and one per
      sound decision; a 403 or timeout is logged, not swallowed silently.
- [ ] No key configured: the job completes voice-only, and both `job.log` and the job
      page say "no audio search configured".
- [ ] Tests never reach the network; ruff, pyright, all test files green in foreground
      chunks, smoke explainer and hitech T1–T13.
- [ ] Done note: what the operator should hear and check on the next real job (a bed
      under the voice, floor hits on stamps and reveals, `audio_rights.json` rows all
      CC0 / CC BY), and the amendment line for 7.2 for the operator to paste.

## Blocked by

- Nothing. 025 (hand-seeded library) stays open as the quality path; this ticket makes
  sure a short is never silent while the library is empty.

## User stories addressed

- Operator's F1 verdict, 27 Sep 2026: no music and no sound effects.
