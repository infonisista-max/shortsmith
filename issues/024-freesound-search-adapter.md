# 024 — Freesound search adapter: fetch, measure, add to the catalogue with a rights row

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

When the best catalogue bed scores below the threshold, search Freesound with the same tags, download the best result, measure it with the 023 script, run the sweep detector, add it to the catalogue with its licence and author, and give it a rights row. Direct HTTP with the API key from config; the fake returns seeded entries only. Tests on recorded JSON.

Covers PRD `sound` (audio search). Decisions 7.1, 7.2, 5.4, 12.1, 13.1.

## Acceptance criteria

- [ ] `AudioSearch` interface; `FreesoundAudioSearch.search(tags, kind) -> list[AudioCandidate]` with licence, author, page URL, preview and download URLs; `FreesoundAudioSearch.fetch(candidate) -> Path` downloads into `assets/audio/fetched/`.
- [ ] A fetched file is measured, passed through R1–R4 (rejected on a hit), scored like a local entry, and appended to `catalog.yaml` with `source: freesound` and licence text; the job's rights row records it.
- [ ] The search runs only when the local best is below `bed_score_threshold` (style front matter); `FakeAudioSearch` returns seeded catalogue entries and records whether it was called.
- [ ] Recorded request/response JSON under `tests/fixtures/freesound/`; tests assert request construction, parsing, the threshold gate and the detector rejection path.

## Blocked by

- Blocked by `issues/023-sweep-detector-t6-catalogue-measure.md`

## User stories addressed

- User story 29
- User story 33
