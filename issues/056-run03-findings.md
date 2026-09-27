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

- [ ] run03's own stems (a 10 s excerpt of `work/stems/voice.wav` and `music.wav`,
      committed as a small fixture): the repaired
      mix meets every 7.3 line; the log names the dip depth in dB; no exception reaches
      the pipeline. A bed that no repair can save yields a voice-and-hits master and a
      page warning, and the job reaches `qa`.
- [ ] run03's `input/refs.json` captions against run03's `work/plan.json` queries:
      `ref1` ("king saud image") no longer matches the Faisal beat; no reference matches
      on a title word alone; a caption that names the beat's subject still matches.
- [ ] run03's `work/assets.json`: the five ids sharing `ref1`'s `sha256` count as one
      image; no image is shown more than twice (carry-on beats and set pieces excluded);
      the third beat gets another candidate (test with a fake source) or a generated
      image; every style has `reuse_max: 2`.
- [ ] A stamp over a fixture image with a detected face is placed outside the face box
      (test on the geometry, not pixels); an image with no face keeps today's placement;
      T12 still passes.
- [ ] Every style's bed target is −14 dB under the voice with acceptance −15…−12; the
      balance report and T-checks use the new numbers; run03's stems mix inside them;
      each style's `version` bumped.
- [ ] A fake search that adopts a bed and an SFX leaves the tracked `catalog.yaml`
      byte-identical; both entries land in the fetched catalogue, and a second job finds
      them without a search call.
- [ ] ruff, pyright, every test file green in foreground chunks, smoke explainer and
      hitech T1–T13; `npm run typecheck` and `npm test` if `src/remotion/**` changes.
- [ ] Done note: what to check on the next real job, and the amendment lines for 7.2
      (the fetched catalogue), 7.3 (repair order and the −14 dB bed), 1.3 / 5.1 and the
      stamp placement for the operator to paste.

## Blocked by

- Nothing.

## User stories addressed

- run03 review, 27 Sep 2026: job failed at the last step; one portrait on eleven beats,
  one of them about King Faisal; stamps covering the king's face.
