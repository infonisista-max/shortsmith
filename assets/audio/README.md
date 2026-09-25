# The audio library (decision 7.2)

`catalog.yaml` is the library **as text**: the sound director reads it, scores beds by
tag overlap and energy, and matches cue intents to SFX by tag. The planner is shown only
the tag words (`## 8. Audio catalogue tags` in the sound prompt) and never names a track.

The audio files themselves live beside it (`beds/`, `sfx/`) and are **never committed** —
`*.mp3`, `*.wav` and `*.m4a` are git-ignored repo-wide. A clone therefore has the
catalogue but no files; an entry whose file is missing fails the mix step with its id, and
an empty catalogue simply leaves the short as the voice alone.

## Seeding it (ticket 025, operator-run)

Twelve beds (suspense, money, history, tech, calm, upbeat; two each) and twenty SFX by
intent, sourced by hand from the YouTube Audio Library and Mixkit — neither has an API.
Every file is hand-listened by Shubham and passed through the sweep detector (ticket 023)
before it is added, and its licence text is recorded in its `licence` field. `duration_s`,
`bpm`, `key` and `energy` are measured by script; `tags` are hand-written.

## Grown at runtime: `fetched/` (ticket 024)

When no catalogue bed clears the style's `sound.bed_score_threshold`, the sound director
asks the Freesound adapter (`sound.freesound`, enabled by `FREESOUND_API_KEY` in `.env`;
the key is free and the search is not metered) with the same theme and mood tags. The
best result's HQ preview is downloaded into `fetched/` (git-ignored like every audio
file), measured by the same script as a seeded entry, and appended to `catalog.yaml` with
`source: freesound`, its licence text and its author, tagged with the query it answered;
it is then an ordinary library entry with an ordinary rights row, and the next job finds
it without a call. A fetched SFX goes through the sweep detector first and is rejected on
any hit; beds do not (a bed is one sound longer than 5 s by definition). Without a key
the director has no search, says so in the job log, and the short goes without a bed.

## Tests and the smoke

Neither uses this catalogue. `shortsmith.fixture.make_catalogue` synthesises a temporary
one with ffmpeg (tone beds and click SFX) into a temp directory, the same way
`make_fixture` synthesises the clip; `tests/conftest.py` exposes it as the `library`
fixture and the smoke builds its own. No test reads or writes anything under this folder.
