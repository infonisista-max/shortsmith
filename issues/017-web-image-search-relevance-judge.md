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

## Notes from 011

- Add `judge` and `search` to `ledger.providers_in_use` (they are in `REQUIRED_UNITS` and `prices.example.yaml` already: judge per 1k input/output tokens, search per query) once the config says which is on; record with `{"input_tokens", "output_tokens"}` and `{"queries": 1}`.

## Blocked by

- Blocked by `issues/016-asset-step-ladder-rights.md`

## Notes from 016

- Adapter shape: `assets.ImageSource` with `origin`, `search(query, n) -> list[Candidate]` and `fetch(candidate, dest) -> Path` (dest without suffix; return the written file). Register it in `assets.from_settings` under its `ASSET_SOURCES` name; today only `fake` maps to an adapter and every other configured name is skipped with a `job.log` note ("no image source adapter yet for: ...").
- The judge slots into `assets._search_cached`: it already asks for `CANDIDATES` (6) and caches the candidate list, the chosen one, the file and `fetched_at` in `work/assets/<sha256(query + source)>/result.json`; today the first candidate wins. `AssetRecord.judge` / `RightsRow.judge` (`JudgeVerdict`) exist and stay None until this ticket.
- Not built in 016: the 5.2 code-only hard rejects (short side < 800, aspect > 3:1, > 15 MB, non-image body) and the `budget.search_max_queries` count.
- Web images are always cards (`assets.classify(..., origin="web")`), so a web portrait asked as `photo` records `treatment_downgraded`.

## User stories addressed

- User story 17
- User story 20
- User story 35
- User story 36
