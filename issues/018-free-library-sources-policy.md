# 018 — Wikimedia Commons, Openverse, Pexels and Pixabay adapters, config-ordered

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The remaining searched sources in the 5.1 order, each one adapter behind `ImageSource`, with the licence text and author each API returns written into the rights row (recorded, not filtered). The order is the config list from 016; removing a misbehaving source is a config edit. Each adapter's candidates go through the same hard rejects and judge as the web adapter.

Covers PRD `assets` (library adapters). Decisions 5.1, 5.2, 5.4, 13.1.

## Acceptance criteria

- [ ] `CommonsImageSource`, `OpenverseImageSource`, `PexelsImageSource`, `PixabayImageSource` implement `search` with direct HTTP, API keys from config where required, and map licence, author, `source_url` and `page_url` into Candidate.
- [ ] Default `ASSET_SOURCES` is `owner, web, commons, openverse, pexels, pixabay, generate`; `.env.example` documents it; an unknown name is a startup config error.
- [ ] Rights rows from these sources carry `origin` matching the source name and `licence` text or `"unknown"`.
- [ ] The judge and hard rejects apply unchanged; the ladder proceeds through sources in the configured order (test with fakes standing in for each adapter, asserting call order).
- [ ] Recorded request/response JSON per adapter under `tests/fixtures/<source>/`; no network in tests.
- [ ] Paid search queries (if any adapter is metered) are ledger rows under the style's `search_max_queries`.

## Blocked by

- Blocked by `issues/017-web-image-search-relevance-judge.md`

## Notes from 016

- Each source is an `assets.ImageSource` (`search` / `fetch`, see 017's note) registered in `assets.from_settings` under its `ASSET_SOURCES` name (`commons`, `openverse`, `pexels`, `pixabay`); the order and the rights-safe removal of `web` already work (`assets.source_order`). Candidate `licence` / `author` / `page_url` flow into the rights row and the credit line ("Photo: <author or domain> via <page url>").

## User stories addressed

- User story 33
- User story 35
