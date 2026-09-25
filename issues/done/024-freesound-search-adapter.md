# 024 — Freesound search adapter: fetch, measure, add to the catalogue with a rights row

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

When the best catalogue bed scores below the threshold, search Freesound with the same tags, download the best result, measure it with the 023 script, run the sweep detector, add it to the catalogue with its licence and author, and give it a rights row. Direct HTTP with the API key from config; the fake returns seeded entries only. Tests on recorded JSON.

Covers PRD `sound` (audio search). Decisions 7.1, 7.2, 5.4, 12.1, 13.1.

## Acceptance criteria

- [x] `AudioSearch` interface; `FreesoundAudioSearch.search(tags, kind) -> list[AudioCandidate]` with licence, author, page URL, preview and download URLs; `FreesoundAudioSearch.fetch(candidate) -> Path` downloads into `assets/audio/fetched/`.
- [x] A fetched file is measured, passed through R1–R4 (rejected on a hit), scored like a local entry, and appended to `catalog.yaml` with `source: freesound` and licence text; the job's rights row records it.
- [x] The search runs only when the local best is below `bed_score_threshold` (style front matter); `FakeAudioSearch` returns seeded catalogue entries and records whether it was called.
- [x] Recorded request/response JSON under `tests/fixtures/freesound/`; tests assert request construction, parsing, the threshold gate and the detector rejection path.

## Status (2026-09-25): done

## What was built

`src/shortsmith/sound/freesound.py` is the adapter; the director's gate is in `sound/__init__.py`.

- **Interface.** `sound.AudioSearch.beds(query, library) -> list[AudioEntry]` is what `choose_bed` calls under the threshold; the adapter is handed the library so what it finds is written into *that* catalogue (tests and the smoke run on temp catalogues, never the shipped one). `FreesoundAudioSearch.search(tags, kind)` and `.fetch(candidate, into=)` are the two HTTP calls the ticket names; `.adopt(candidate, library=, theme=, mood=, intent=)` is the 7.2 measure-check-score-append; `.beds` runs search → adopt over the results in Freesound's order and returns the first that is adopted, reusing an entry already in the catalogue without a download. `FakeAudioSearch()` takes no library any more: it returns the passed library's beds and records every query in `.calls`.
- **Threshold.** `sound.bed_score_threshold` is a new `styles.Sound` field on all four specs (0.5: a tag hit scores 1 and the energy distance at most 0.4, so "at least one tag matched"). The old `BED_SCORE_MIN` constant is gone; `select_bed` / `choose_bed` take `threshold=` and `build_mix` passes `nums.bed_score_threshold`.
- **What is fetched.** Freesound's original files need an OAuth2 grant; the previews need only the token. The adapter fetches the HQ mp3 preview (else the HQ ogg) into `<library>/fetched/freesound_<id>.<ext>` (audio is git-ignored repo-wide) and keeps the original's `download` URL on the `AudioCandidate` for the log. A hit with no preview is dropped. The key travels as `Authorization: Token …`, never in the URL. Searches filter on duration by kind (`duration:[20 TO 600]` for a bed, `[0 TO 5]` for a cue, the R3 line); no licence filter (v1, 5.1/5.2 rule).
- **Detector on cues only.** A fetched SFX goes through R1–R4 and is rejected on any hit (file removed, catalogue untouched). A bed is *not* run through it: a bed is one sound longer than 5 s by definition (R3) and swells by design (R2, R4), so the detector would reject every bed; this is the same split `seed check` already makes (SFX only). At runtime the director only ever searches for beds, so the rejection path is exercised by `adopt` on a cue in the tests.
- **Measured, not copied.** `duration_s`, `energy` (and `bpm`, `key` for a bed) come from `seed.measure_file`, not from Freesound's `duration`. `loop_ok` is read from Freesound's own tags (`loop`, `loopable`, `seamless`) since nothing measures a seam yet; `drop_points_s` stays empty. The entry's `tags` are the query it answered (theme, mood; or the intent for a cue), so `bed_score` on it clears the threshold like a local entry.
- **Catalogue append.** `seed.catalogue_text` / `seed.raw_entries` / `seed.entry_dict` are the one writer both `measure` and the adapter use (header comment kept, field order, validated before writing). `Library.catalogue` is `root / "catalog.yaml"`.
- **Rights.** Nothing new: the entry is an ordinary library entry, so `rights_rows` gives it the usual row (`origin: library`, `source_url` = the Freesound page, `licence` = "CC BY 4.0" style text from the licence URL, `author` = username, sha256 of the fetched file). `AudioEntry.source` is `freesound`; the `Origin` literal was left alone on purpose (the smoke and T9 read `library` for every audio row).
- **Wiring.** `RemotionRenderer(search=)` owns the adapter the way the asset step owns its sources, so `Renderer.render` and the pipeline are unchanged; `render.sound_mix` / `mux` / `render_short` take `search=`. `app.create_app` builds `freesound.from_settings(settings)` — `FREESOUND_API_KEY` set → the adapter, unset → no search and the director's "no audio search is configured" note. The smoke hands the renderer a `FakeAudioSearch` and asserts it was **not** asked (the fake plan's bed scores in the library), so the gate is proved shut, not just present.
- **Ledger.** No row: the Freesound key is free and the search is not metered (same footing as Pexels/Pixabay, 018). `ledger.REQUIRED_UNITS["search"]` still waits for the first metered adapter.

## Blocked / for the operator

- **`.env.example` is unwritable from the agent session** (`.env*` is denied by the permission settings, as 018 found). Line to paste:

  ```
  FREESOUND_API_KEY=
  ```

  The key is free (freesound.org/apiv2/apply). Unset, the sound director has no search; a bed query nothing local scores for leaves the short without a bed and says so in `job.log`.
- **`.gitignore` is unwritable from the agent session** (edit denied by the permission settings). `*.mp3` / `*.wav` / `*.m4a` are already ignored, but the adapter falls back to Freesound's HQ **ogg** preview when a hit has no mp3, and that suffix is not. Lines to paste under the media block:

  ```
  *.ogg
  # Audio the runtime search fetches into the catalogue (ticket 024)
  assets/audio/fetched/
  ```
- The worker loads the catalogue once at startup, so a bed fetched during a job is used by that job (and found again by the adapter through the on-disk catalogue), but the in-memory `Library.tags()` the planner is shown does not gain its tags until the next restart. Harmless in v1; a reload-on-append is a follow-up if the library grows fast.
- 025 (hand seed) should decide whether a fetched bed keeps `loop_ok` from Freesound's tags or gets a measured seam check.

## Blocked by

- Blocked by `issues/023-sweep-detector-t6-catalogue-measure.md`

## User stories addressed

- User story 29
- User story 33
