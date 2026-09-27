# 056 — run03 findings: never fail on the music balance, owner photos go to the right beat, no image on repeat, no stamp over a face, a 30 % quieter bed, no job edits a tracked file

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

run03 (job `20260927-140915-bbad1c`, readable under `data/jobs/`) rendered the whole
picture, found a bed and the hits (054 works), sourced the right people with no stock
watermarks (053 works) and opened in the speaker's order (055 works) — then failed at the
very end. Five findings, each from that job's own files:

1. **The job died on a music check at the end of a 20-minute job.** `work/stems/balance.json`:
   bed −11.0 dB under the voice (inside −12…−9), ducking 3.8 dB (inside 4) — but "the
   speech band 250–4000 Hz clears the bed by only 9.4 dB, under 20 dB", and `build_mix`
   raised, so the job failed with every other part done. The chosen Freesound bed
   ("middle eastern mysterious") is melodic inside the speech band.
2. **One owner photo took eleven beats, including a beat about another man.**
   `matching_reference` gives a beat the reference whose caption shares the most words
   with its query. The caption "king saud image" shares "king"/"saud" with nearly every
   query, so `work/assets.json` maps `ref1` to `saud_1953`, `saud_young`, `royal_court`,
   `saud_old` — and to `faisal` ("King Faisal bin Abdulaziz 1964 portrait" shares "king").
   The same portrait fills b01, b05, b06, b08, b10, b13, b15, b16, b17, b23 and b25, and
   the Faisal beat shows Saud.
3. **The same image repeats with no limit** (the eleven above, plus the wall and finale).
   `broll.reuse_max` (4) did not stop it because the 4.3 check counts per asset id, and
   `saud_1953`, `saud_young`, `royal_court`, `saud_old` and `faisal` are five ids for one
   file (same `sha256` as `ref1` in `work/assets.json`).
4. **Stamps sit on faces.** Every stamp over the portrait card (b05, b08, b15, b16, b17,
   b23, b25) covers the king's face.
5. **The job changed a tracked file.** Freesound adoptions are appended to
   `assets/audio/catalog.yaml` (`freesound.append_entry`), the hand-seeded catalogue in
   git, so after run03 `git status` showed it modified and the operator had to stash it
   before the next afk run.

Operator decisions, 27 Sep 2026 (amend 7.2, 7.3, 1.3 / 5.1 and the stamp placement rule;
the operator records them in `docs/grill-decisions.md` from the done note):

1. **A music check never fails the job.** When the balance misses a line, the mix
   repairs itself before giving up, in this order: a speech-band dip on the bed (EQ in
   250 Hz–4 kHz, depth chosen to reach the line), then a lower bed within the 7.3
   acceptance window, then the next bed candidate from the library or the search. Only
   if all of that fails does the short go out with the voice and hits alone, with one
   `sound:` line in `job.log` and one warning on the job page. Every repair is logged.
2. **An owner photo goes only to beats about what its caption names.** Title and
   generic words (king, prince, president, image, photo, with …) never create a match;
   a caption must share the beat's subject name. A beat about a named person never takes
   a reference whose caption names only someone else. If the caption is too vague to
   tell, the reference goes to the beats the planner named it for, not further.
3. **No image on repeat.** One image — counted by its file (`sha256`), so several asset
   ids pointing at one file are one image — is shown at most twice per short. A beat
   that carries on the previous beat's picture (4.2 number or quote) is part of the same
   showing; the wall and finale set pieces do not count. `broll.reuse_max` becomes 2 in
   every style and the 4.3 check counts by image. A third beat that wants it gets its
   next-best candidate or a generated image (5.5); never the same picture again.
4. **Stamps never cover a face.** When a stamp or counter sits over an image, the 3.3
   face detector runs on that image and the stamp moves to the largest face-free band
   (the card's lower or upper third, or below the card). No face found → today's
   placement.
5. **The bed is 30 % quieter.** Operator's phone verdict on run03 (score 6): music good,
   "a bit loud, reduce by 30 %". 30 % less amplitude is −3.1 dB, so the 7.3 bed target
   moves from −11 to −14 dB under the voice and the acceptance window from −12…−9 to
   −15…−12, in every style's front matter (explainer, educational, animated, hitech).
6. **A job never changes a tracked file.** Runtime adoptions go to a catalogue in the
   git-ignored `assets/audio/fetched/` (beside the files they describe); the director
   reads the tracked catalogue, then the fetched one; `seed` keeps writing the tracked
   one. The operator's stash of run03's adoptions (`git stash list`: "run03 freesound
   adoptions") is moved there by the operator after this ticket; the agent does not
   touch the stash.

## Acceptance criteria

- [x] run03's own stems: the repair ladder runs, the log names every dip depth in dB,
      no exception reaches the pipeline; a bed no repair can save yields a voice-and-hits
      master and a page warning. **Not committed as a fixture**: CLAUDE.md forbids
      committing audio, so the tests reproduce run03's shape with synthesised beds
      (`tests/test_sound.py`, `MELODIC` / `PURE`) and the real stems were run once by
      hand (see the done note for the numbers).
- [x] run03's `input/refs.json` captions against run03's queries: `ref1` ("king saud
      image") no longer matches the Faisal beat; no reference matches on a title word
      alone; a caption that names the beat's subject still matches; a vague caption
      ("with daughter") goes only where the planner named it.
- [x] Five ids sharing one `sha256` count as one image; no image is shown more than
      twice (carry-on beats and the wall / finale set pieces excluded); the third beat
      gets the next candidate of its own cached search, a generated image, or rung 4 -
      never the same picture; every style has `reuse_max: 2`; the grammar and gate T8
      count the same way.
- [x] A stamp (or counter) over a fixture image with a detected face is placed outside
      the face box on the geometry; no face keeps today's placement; T12 still passes.
- [x] Every style's bed target is −14 dB under the voice with acceptance −15…−12; the
      balance report and the T-checks read the style numbers; each style's `version` is
      "4".
- [x] A fake search that adopts a bed and an SFX leaves the tracked `catalog.yaml`
      byte-identical; both land in `assets/audio/fetched/catalog.yaml`, and a second
      load finds them with no search call.
- [x] ruff, pyright, every test file green in foreground chunks, smoke explainer and
      hitech T1–T13; `src/remotion/**` untouched, so the npm loops did not apply.
- [x] Done note below.

## Done note (28 Sep 2026)

### What was built

1. **A music check never fails the job** (`sound.build_mix`). The cues and the SFX stem
   are placed first; then every bed candidate (`sound.bed_candidates`: the library's beds
   over the threshold best first, then each search rung) is mixed and measured, and a
   miss is repaired in the operator's order (`_repaired_bed`): a speech-band dip on the
   bed (`dip_filter`: a peaking EQ centred on the band's geometric middle, as wide as the
   band; depths from `dip_depths`: shortfall + 1 dB, then doubling, never past 24 dB, each
   depth measured), then the bed lowered to the floor of `bed_accept_db` (plus the 0.3 dB
   convergence tolerance), then the next bed (at most 3 beds mixed), then the voice and
   the hits alone. Every repair is a `sound:` line in `job.log` and a row in
   `balance.json` (`repairs`, `dip_db`, `bed_dropped`); a dropped bed puts
   `sound.VOICE_AND_HITS_LINE` on the job page (`render._page_warning`). `SoundError` is
   no longer raised for a balance miss.
2. **Owner photos by subject name** (`assets.matching_reference(beat, refs)`): a caption
   must share a `subject_words` word with the beat (its capitalised name words, else its
   significant query words); `TITLE_WORDS` (king, prince, president, nizam, sir, …) and the
   generic `STOPWORDS` (image, photo, with, portrait, …) never match. Honorifics that are
   part of a name (Baba, Guru, Swami) stay name words. A caption with no significant
   word matches nothing.
3. **No image on repeat, counted by file** (`assets.is_showing`, `_Walk.showings` by
   `sha256`, `reuse_max` on the manifest): a planned reuse, an owner reference or a
   caption match past the cap is skipped with a log line and the beat is sourced afresh;
   `_search_cached` skips a saturated file and fetches the next ranked candidate into the
   same cache folder (`alternates` in `result.json`, so nothing is fetched twice); rung 3
   re-dresses only an image with a showing left. `grammar._assets` and gate T8
   (`assets.image_reuse_problems`) count showings the same way: a `number` / `quote` beat
   over the previous beat's asset carries that showing on; the wall's base and the
   finale's cards are set pieces.
4. **Stamps never cover a face** (`render.build_spec(detector=…)`): the 3.3 detector runs
   once per image file; `face_box_on` maps the face through the visual's geometry (cover
   fit, focus, zoom, the Ken Burns or the card push, both ends of the beat);
   `stamp_clear_of` moves the stamp or counter to the largest face-free band (the image's
   upper third, lower third, or below it), inside the style's top band and the 6.3 top
   zone (`render.SAFE_TOP_PX`, asserted equal to the gate's). No face, or no free band:
   today's placement. `RemotionRenderer` builds a Haar detector on first use; the fake
   renderer passes none.
5. **The bed is 30 % quieter**: `bed_db_under_voice: -14`, `bed_accept_db: [-15, -12]`,
   `reuse_max: 2` and `version: "4"` in explainer, educational, animated and hitech.
6. **A job never changes a tracked file**: `Library.fetched_catalogue`
   (`assets/audio/fetched/catalog.yaml`, git-ignored) is what `freesound.adopt` appends
   to; `sound.load_catalogue` reads the tracked file, then the fetched one; `seed` keeps
   writing the tracked one. The operator's stash "run03 freesound adoptions" was not
   touched.

### run03's own stems, run once by hand (not committed)

A 10 s excerpt of run03's `work/stems/voice.wav` with its Freesound bed
(`assets/audio/fetched/freesound_738836.mp3`, still on disk) under the new explainer
numbers: the plain mix measured the speech band clearing the bed by 11.9 dB (9.4 dB at
the old −11 dB target) and the duck at 4.3 dB; the ladder dipped the band by 10 dB (margin
→ 12.7) and 20 dB (→ 13.3), lowered the bed to −14.7 dB (→ 14.0), found no next
candidate (no search configured in the check) and shipped voice and hits, with
`balance.json` carrying the three repairs and `bed_dropped`. No exception. The dip gains
little on that bed because it is almost entirely inside the band: the level match puts
the bed back on its target, which puts most of the dipped energy back. That is the physics
of the operator's rung order, recorded here, not changed.

### What to check on the next real job

- `job.log`: the `sound:` lines for `misses the 7.3 band`, `dipped by N dB`, `lowered
  to`, `trying the next bed` and `voice and hits only`; the job must reach `qa` whatever
  the bed does. `work/stems/balance.json` now has `repairs`, `dip_db`, `bed_dropped`.
- Whether the 20 dB speech-band margin, measured on the un-ducked music stem, is
  reachable by any melodic bed at all (run03's was 6 dB short after every repair). If
  most real beds drop to voice-and-hits, the operator may want to decide whether the
  margin should be measured on the ducked stem (`music.ducked.wav`, the sidechain is what
  protects the speech) or the line lowered; both are one-line changes but neither is in
  this ticket.
- `work/assets.json`: `reuse_max` 2; no `sha256` on more than two showing beats;
  `sourcing: bNN: … already shown 2 times … the next candidate is tried (056)` lines
  where a third beat wanted a picture; `image-2.png` alternates under `work/assets/`.
- Owner references: the `faisal`-style beat must search rather than take the portrait;
  captions like "with daughter" must go only to the beat that names the reference id.
  If the operator's captions are terse, name the person in the caption.
- `stamp:` lines in `job.log` for every stamp moved off a face, and the phone check that
  no stamp sits on a face (Haar finds frontal faces only; a profile or a painting may
  still be missed - then today's placement).
- The bed at −14 dB on the phone (the operator asked for 30 % quieter).
- After the job, `git status` must be clean: adoptions land in
  `assets/audio/fetched/catalog.yaml`.

### Amendment lines for `docs/grill-decisions.md` (operator to paste)

- **7.2 (amended by 056):** runtime adoptions from the audio search are appended to
  `assets/audio/fetched/catalog.yaml`, git-ignored beside the fetched files; the director
  reads the tracked `catalog.yaml` and then the fetched one; `seed` writes only the
  tracked one. A job never changes a tracked file.
- **7.3 (amended by 056):** the bed target is −14 dB under the voice (run03 phone verdict:
  "a bit loud, reduce by 30 %" = −3.1 dB) with acceptance −15…−12 dB, in every style. A
  music check never fails the job: when the balance misses a line the mix repairs itself
  in this order - a speech-band dip on the bed (EQ in 250 Hz–4 kHz, depth escalating
  from the shortfall to reach the line, at most 24 dB), then the bed lowered to the floor
  of the acceptance window, then the next bed candidate from the library or the search
  (at most three beds mixed) - and only then the short goes out with the voice and the
  hits alone, with one `sound:` line in `job.log` and one warning on the job page. Every
  repair is logged and recorded in `balance.json`.
- **1.3 / 5.1 (amended by 056):** an owner reference goes only to beats about what its
  caption names: a caption must share the beat's subject name; titles and generic words
  (king, prince, president, image, photo, with, …) never create a match; a beat about a
  named person never takes a reference whose caption names only someone else; a caption
  too vague to name anyone goes only to the beats the planner named it for.
- **4.3 (amended by 056):** one image - counted by its file (`sha256`), however many
  asset ids point at it - is shown at most twice per short (`broll.reuse_max: 2` in every
  style). A `number` / `quote` beat carrying on the previous beat's picture is part of
  the same showing; the wall's base and the finale's cards do not count. A third beat
  that wants the picture gets its next-best candidate or a generated image, never the
  same picture; the grammar and gate T8 count by image.
- **Stamp placement (amended by 056, 3.3 / 4.1):** when a stamp or counter sits over an
  image, the 3.3 face detector runs on that image and the stamp moves to the largest
  face-free band - the image's upper or lower third, or below it - inside the style's
  top band and the 6.3 safe zones. No face found, or no free band: today's placement.

## Blocked by

- Nothing.

## User stories addressed

- run03 review, 27 Sep 2026: job failed at the last step; one portrait on eleven beats,
  one of them about King Faisal; stamps covering the king's face.
