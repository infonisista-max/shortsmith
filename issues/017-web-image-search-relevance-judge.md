# 017 — Web image search adapter and the relevance judge

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The first real source in the 5.1 order and the cheap filter above it. The web adapter does a direct HTTP image search with page follow, fetches up to six candidate thumbnails, applies the code-only hard rejects, and hands the candidates to the `RelevanceJudge`: one vision call over the thumbnails with query, subject kind and the brief's topic line, scoring 0–3 with reasons from the fixed list, model from `RELEVANCE_JUDGE_MODEL`. Best ≥ 2 wins, ties by source order, all < 2 → next source. Judge verdicts cached by URL; every call is a ledger row under `judge_max_calls`. Real adapters are tested on recorded JSON only; `httpx` moves from the dev group to main dependencies (already in `pyproject.toml`).

Covers PRD `assets` (web adapter, judge). Decisions 5.1, 5.2, 5.6, 12.1, 13.1.

## Acceptance criteria

- [ ] `WebImageSource.search` performs the search request, follows result pages to the image URL, records `source_url` and `page_url`, downloads with size and content-type checks; recorded fixtures under `tests/fixtures/web/`.
- [ ] Hard rejects in code before the judge: short side < 800 px, aspect > 3:1, > 15 MB, non-image body; a rejection is of the candidate, never of the beat.
- [ ] `RelevanceJudge` interface; `VisionJudge` sends one Messages call with up to six thumbnails and returns per-candidate `{score, reasons}` with reasons from {wrong_subject, watermark, text_heavy, meme, too_small, nsfw, logo_only}; `FakeRelevanceJudge` scores by substring match of the query in the fake filename.
- [ ] Selection: best ≥ 2 wins, ties by source order, all < 2 → next source in the list → ladder.
- [ ] Verdicts cached per job by candidate URL; judge calls recorded to the ledger; the style's `judge_max_calls` stops further judge calls and the ladder continues without them (recorded on the beat, shown on the sheet).
- [ ] Rights rows carry `judge: {model, score, reasons}` and the web origin with both URLs; web images are always rendered as `card` (re-dressed), never raw `photo`.
- [ ] `ASSET_POLICY=rights_safe` removes the web adapter with no other change (test on the source list).
- [ ] Tests: request construction and response parsing on recorded JSON for search, page follow and the judge; hard-reject boundaries at 799/800 px and 3.01:1; cache hit makes zero judge calls.

## Blocked by

- Blocked by `issues/016-asset-step-ladder-rights.md`

## User stories addressed

- User story 17
- User story 20
- User story 35
- User story 36
