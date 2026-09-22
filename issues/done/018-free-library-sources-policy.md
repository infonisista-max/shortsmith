# 018 — Wikimedia Commons, Openverse, Pexels and Pixabay adapters, config-ordered

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The remaining searched sources in the 5.1 order, each one adapter behind `ImageSource`, with the licence text and author each API returns written into the rights row (recorded, not filtered). The order is the config list from 016; removing a misbehaving source is a config edit. Each adapter's candidates go through the same hard rejects and judge as the web adapter.

Covers PRD `assets` (library adapters). Decisions 5.1, 5.2, 5.4, 13.1.

## Acceptance criteria

- [x] `CommonsImageSource`, `OpenverseImageSource`, `PexelsImageSource`, `PixabayImageSource` implement `search` with direct HTTP, API keys from config where required, and map licence, author, `source_url` and `page_url` into Candidate.
- [x] Default `ASSET_SOURCES` is `owner, web, commons, openverse, pexels, pixabay, generate`; an unknown name is a startup config error. **`.env.example` NOT updated — the file is outside this session's permissions (same blocker as 017); see the note below.**
- [x] Rights rows from these sources carry `origin` matching the source name and `licence` text or `"unknown"`.
- [x] The judge and hard rejects apply unchanged; the ladder proceeds through sources in the configured order (test with fakes standing in for each adapter, asserting call order).
- [x] Recorded request/response JSON per adapter under `tests/fixtures/<source>/`; no network in tests.
- [x] Paid search queries (if any adapter is metered) are ledger rows under the style's `search_max_queries`. **No adapter here is metered** (web is scraped, Commons and Openverse are keyless, Pexels and Pixabay want a free key and charge nothing), so no `search` ledger row is written and `search` stays out of `ledger.providers_in_use`. `search_max_queries` is now counted by `assets.Searching` and reported on the manifest.

## Blocked by

- Blocked by `issues/017-web-image-search-relevance-judge.md`

## Notes from 016

- Each source is an `assets.ImageSource` (`search` / `fetch`, see 017's note) registered in `assets.from_settings` under its `ASSET_SOURCES` name (`commons`, `openverse`, `pexels`, `pixabay`); the order and the rights-safe removal of `web` already work (`assets.source_order`). Candidate `licence` / `author` / `page_url` flow into the rights row and the credit line ("Photo: <author or domain> via <page url>").

## Notes from 017

- `shortsmith.assets` is a package now. Put each adapter in its own module beside
  `assets/web.py` and re-export it from `assets/__init__.py`; the hard rejects and the
  `ImageSource` base live in `assets/base.py` (`reject_size`, `reject_body`,
  `media_type`, `MAX_BYTES`). `WebImageSource` is the worked example of the shape,
  including the optional `thumbnail(candidate) -> bytes | None` the judge reads (the
  base returns None, meaning "the judge sees the URL only").
- The judge is done and source-agnostic: `Judging.verdicts(...)` in `assets/judge.py`
  already runs for every source, so these adapters need no judge work — only real
  `Candidate` values with `width` / `height` filled in before the hard rejects.
- Ledger: `search` is still out of `REQUIRED_UNITS`'s in-use set because the 017 web
  adapter is scraped and free. The first metered adapter here must add `search` to
  `ledger.providers_in_use` (units `{"queries": 1}`) and count against
  `budget.search_max_queries`, which is still uncounted.
- `.env.example` is missing `RELEVANCE_JUDGE` and `RELEVANCE_JUDGE_MODEL` (017 could
  not write `.env*`); add them alongside this ticket's `ASSET_SOURCES` line.

## Notes from 018 (done)

- Four adapters, one module each beside `assets/web.py`: `assets/commons.py`,
  `assets/openverse.py`, `assets/pexels.py`, `assets/pixabay.py`. What they all share
  with `web` — the capped GET, the judge's thumbnail, the 5.2-checked download and the
  suffix-from-bytes rule — was lifted into `assets/http.py` (`HttpImageSource`), and
  `WebImageSource` now extends it; `web.py` lost its private copies.
- Commons sorts its generator pages by `index` (the API returns them unordered), and
  strips the HTML Commons stores in `extmetadata.Artist`. Openverse turns
  `license` + `license_version` into the stored line (`by-sa` + `4.0` → "CC BY-SA
  4.0"). Pexels carries its key in `Authorization`, Pixabay as a `key=` parameter (the
  API takes it no other way) and refuses a page under 3.
- Pixabay size trap, worth remembering for 019/021: a hit's `imageWidth/imageHeight`
  describe the *original* upload but the API only serves `largeImageURL`, capped at
  1280 px on its long side. The adapter reports the scaled size (`pixabay.scaled`) so
  the 5.2 hard rejects are not told a size the download cannot deliver.
- `ASSET_SOURCES` now spells the whole 5.1 ladder out; `owner` and `generate` are
  accepted names that build nothing (`assets.BOOKENDS`, dropped by `source_order`),
  so the config reads as the order in the decision. `config.check_startup` rejects any
  other name. A source whose free key is unset is skipped with a `Sourcing.notes` line
  the pipeline writes to `job.log` — not a startup error, since the key is optional.
- `assets.Searching` counts queries actually sent (a cache hit costs nothing and is
  not counted) against `budget.search_max_queries`, and reports
  `search_queries` / `search_max` on the manifest. Passing the allowance is a job-log
  note and nothing else: every source is free and 11.3 forbids trading quality for
  cost. A metered adapter is the one that must add the `search` ledger row and the
  `check_before_call`, the way `judge` does.

## Blocked / for the operator

- **`.env.example` is unwritable from the agent session** (`.env*` is denied by the
  permission settings), so it still lacks `ASSET_SOURCES`, `RELEVANCE_JUDGE`,
  `RELEVANCE_JUDGE_MODEL` (017's gap) and now `PEXELS_API_KEY` / `PIXABAY_API_KEY`.
  Lines to paste:

  ```
  ASSET_SOURCES=owner,web,commons,openverse,pexels,pixabay,generate
  RELEVANCE_JUDGE=api
  RELEVANCE_JUDGE_MODEL=claude-haiku-4-5-20251001
  PEXELS_API_KEY=
  PIXABAY_API_KEY=
  ```

  Both keys are free (pexels.com/api, pixabay.com/api/docs). With them unset the
  ladder just skips those two rungs and says so in the job log; nothing fails.
- Not done here, and not in this ticket's scope: a search line on the contact-sheet
  summary panel beside the judge line — that panel is ticket 035.

## User stories addressed

- User story 33
- User story 35
