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

## Done note (2026-09-27)

Root cause of F1's silence, beyond the ticket's three points: `render.sound_mix` returned
before the director ran whenever the catalogue had no entries (`if not library.entries`),
so with the empty shipped `catalog.yaml` the Freesound search was never asked at all and
nothing was logged. Now the director runs whenever a story exists and either the library
has entries or a search is configured.

What landed:

- `sound.bed_queries` / `sound.sfx_queries`: the ladders. Bed: theme[:3]+mood[:3] words,
  theme[:2]+mood[:1], mood[:3], mood[:1], then `sound.default_bed_query`; every rung at
  most `QUERY_MAX_WORDS` (6), stopwords and repeats gone, stop at the first adoption. SFX:
  a floor class asks "<class> hit" then the class word; a planner intent asks its words and
  then falls back to the beat's floor class as before. Floor classes are resolved first
  (drum, bass, thump, changeover) so the guaranteed floor is what the search goes to first.
- `AudioSearch` is now `bed(words, query, library)` / `sfx(words, intent, library)`, each
  returning a `SearchOutcome` (source, kind, query, HTTP status or `timeout`, Freesound's
  hit count, adopted entry, one note per skipped candidate). `FakeAudioSearch(shelf=...)`
  answers from a shelf of catalogue entries and records `calls` / `sfx_calls`.
- Freesound: `LICENCE_FILTER` (`license:("Attribution" OR "Creative Commons 0")`) on every
  request, `licence_allowed` re-checked on every result before any download; a candidate
  rejected once (unreadable, sweep hit) is remembered by id for the process. Adopted beds
  are tagged with the query's theme and mood keywords (lists), not the sentences.
- `build_mix(log=...)` hands every line to `job.log` as it is made (`sound: ` prefix), then
  `place_cues` adds one line per cue placed, fallen back or dropped, then the summary.
  `MixResult.library` is the grown library; `rights_rows(result)` reads it.
- Voice-only page notice: `render._voice_only` appends one line to `job.json.warnings`
  ("voice only: no audio search configured ..." or "... every audio search came back
  empty ...") once; the job page already renders `warnings`.
- `sound.default_bed_query` in all four styles, `version` bumped to "2": explainer
  "cinematic ambient documentary", hitech "electronic ambient technology", animated
  "upbeat playful ambient", educational "calm ambient piano" (agent-chosen last-resort
  words; the operator may change them, they are front matter).
- `credits.md` audio lines now end with the licence in brackets:
  `Music: <author> via <url> (CC BY 4.0)`.

What the operator should hear and check on the next real job (with `FREESOUND_API_KEY`):

- A bed under the voice from the first spoken word, ducking under speech, fading out at
  the end; floor hits on every stamp and reveal (bass), on the money reveal and the finale
  word (drum), on card fly-ins (thump).
- `job.log`: `sound: audio search freesound bed '<words>': status 200, N hits, adopted
  freesound_<id>` lines walking the ladder, then one line per SFX search, then one line
  per cue placed, then `sound: bed freesound_<id>, N cues (...)`. A 403 (bad key) or a
  timeout shows as `status 403, 0 hits` / `status timeout, 0 hits` on every rung.
- `work/audio_rights.json` (and `out/rights.json`): every row's `licence` is `CC0 x` or
  `CC BY x`, `source_url` a freesound.org page, `author` filled; `out/credits.md` shows
  the licence in brackets on the Music/Sound lines.
- If the short still goes out voice-only, the job page shows one warning line saying why.
- Caveat to listen for: the ladder guarantees *a* bed, not a good one; the last rungs
  ("mysterious", "cinematic ambient documentary") are broad. If the fit is poor, the fix
  is 025's hand-seeded library (which is searched first), not the ladder.

Amendment line for 7.2 (operator pastes into `docs/grill-decisions.md`):

> 7.2 amendment (054, 27 Sep 2026): the runtime search is asked with plain keywords,
> specific to broad - theme and mood words, fewer of them, the mood alone, one mood word,
> then the style's `sound.default_bed_query` - each query at most six words, stopping at
> the first adoption; it is also asked for any SFX intent or floor class the catalogue
> lacks (floor classes first), every fetched SFX passing the 7.3 detector before adoption.
> Only CC0 and CC BY files are adopted, beds and SFX alike (filtered in the request and
> checked again on the result); licence and author stay in the rights row and in
> `credits.md`. Every search (source, query, HTTP status, hit count) and every sound
> decision is a line in `job.log`; a voice-only short says why on the job page.
