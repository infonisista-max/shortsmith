# 053 — F1 findings: real people, no stock watermarks, Commons answers, T11 per 3.3

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

The first real job with the real pipeline (F1, job `20260927-041728-656506`, readable
under `data/jobs/`) was rated below the old engine by the operator. The evidence is in
that job's own files:

- `job.log`: six real Neem Karoli Baba photos were found by web search and all lost —
  five to the 800 px short-side hard reject (584–768 px), one to a 403. Sourcing then
  fell through to Pexels, where the relevance judge scored "portrait of a man at a
  vibrant flower market" 3/3 for "Neem Karoli Baba portrait blanket"
  (`work/assets/*/result.json`). A stranger became the named person in four beats.
- `out/rights.json`: 4 of 15 images are `c8.alamy.com` comps and 1 is a Freepik premium
  image — watermarked stock previews. The judge scored them 3/3 from Bing thumbnails
  where the watermark is not visible.
- Every Commons and Openverse search returned zero candidates with no log line at all.
- T11 failed on 7 of 8 strip frames because it tests the four corners of the detector's
  square box against the circle. A square wider than window/√2 (764 px on a 1080 px
  window) can never pass, while the face itself sits inside the circle with 61–154 px
  to spare on every frame (inscribed-oval check on the job's `presenter` numbers).

Operator decisions, 27 Sep 2026 — they amend 5.1, 5.2 and 10.1 (T11). Where
`docs/grill-decisions.md` says otherwise, this ticket wins; the operator records the
amendment in that file.

1. A named person is never shown as a stranger. For a beat whose subject is a named
   entity (`generate.depicts_of` → `named_entity`), the stock libraries (Pexels,
   Pixabay) are neither searched nor accepted. The ladder goes owner refs → web →
   Commons → Openverse with `query`, then the same with `query_fallback`, then rung 2
   (the 5.5 stylised illustration), then the existing rungs.
2. Name evidence first. For named-entity beats, candidates whose page URL or file name
   carry the person's name rank ahead of those that don't; the judge still filters.
   Choose where the name comes from (the plan already knows its entities) and say so in
   the done note.
3. Stock-preview hosts are dropped before judging: alamy, freepik, stock.adobe.com /
   ftcdn.net, dreamstime, istockphoto, gettyimages, shutterstock, 123rf, depositphotos,
   pond5, canstockphoto (image host or page host). One constant, one `job.log` line per
   dropped candidate.
4. The size floor follows the slot, not a flat 800 px. A full-bleed photo keeps the 5.3
   requirement (cover 1080x1920 at ≤ 1.5x). A card, stamp, wall item or hook card
   accepts any image that fills its own slot at ≤ 1.5x. No real photo is lost to a floor
   stricter than where it will be shown.
5. Commons and Openverse say why they return nothing. Requests carry a descriptive
   User-Agent per Wikimedia's policy (project name + repo URL). A non-200 answer or an
   empty result writes one `job.log` line with the status and the query.
6. T11 checks the face, not the box corners: the oval inscribed in the detector box must
   sit inside the PIP circle (window scaled into it), and the existing chin rule stays
   (chin above 90 % of the window). Update the 10.1/T11 wording in the `qa.technical`
   docstring to match.

## Acceptance criteria

- [x] Fixture from F1's `work/assets/*/result.json` candidates: the named-entity beats'
      picks are never a Pexels or Pixabay URL; with the name rule, a candidate whose page
      URL contains `neem-karoli-baba` outranks one that doesn't.
- [x] Same fixture: no candidate from the stock-host list reaches the judge; each drop
      writes a `job.log` line.
- [x] Size floor by slot: a 600 px and a 768 px short-side image are accepted for a card
      beat and (see the done note) for a photo beat too, where 5.3 shows them as a card;
      the exact thresholds are derived from the render geometry constants, not typed twice.
- [x] Commons and Openverse requests send the descriptive User-Agent (test on the request
      headers); a 403 and an empty result each produce one `job.log` line naming source,
      status and query.
- [x] T11: F1's `job.json` presenter numbers pass (all 8 frames); a face whose oval
      leaves the circle by ≥ 10 % of its radius fails with the frame named; a chin below
      90 % still fails.
- [x] Every existing test that encoded the old rules is updated to the new ones, not
      deleted; ruff, pyright, all test files green in foreground chunks, smoke explainer
      and hitech T1–T13.
- [x] Done note: what the operator should look for on the next real job (Commons and
      Openverse candidate counts in `work/assets/*/result.json`, no stock host in
      `out/rights.json`, named people correct on the contact sheet), and the three
      amendment lines for `docs/grill-decisions.md` (5.1, 5.2, 10.1) for the operator
      to paste.

## Done note (27 Sep 2026)

What shipped, rule by rule:

1. **Named people never from stock.** `assets.source_assets` drops `STOCK_ORIGINS`
   (pexels, pixabay) from the ladder for any beat whose `generate.depicts_of` is
   `named_entity`, with one `job.log` line per beat naming the sources not searched.
   The ladder is then owner refs → web → Commons → Openverse with `query`, the same
   with `query_fallback`, rung 2 (illustration), rungs 3-4. Scene beats are unchanged.
2. **Name evidence first.** The name comes from the beat's own `query`: its
   capitalised words (stopwords out), falling back to `query_fallback`'s when the query
   has none (`assets.name_words`). F1's plan gives "Neem Karoli Baba", "Steve Jobs
   India", "Virat Kohli Kainchi Dham", "Mark Zuckerberg". A candidate whose page URL or
   file name carries at least half of those words as whole slug words
   (`assets.name_evidence`) ranks ahead of one that does not, judged or unjudged; the
   judge still filters what scores under 2. The plan's `name_runs` were not used: they
   index transcript words, which are Devanagari on F1 and never match a URL.
3. **Stock-preview hosts.** `base.STOCK_HOSTS` (alamy, freepik, stock.adobe.com,
   ftcdn.net, dreamstime, istockphoto, gettyimages, shutterstock, 123rf, depositphotos,
   pond5, canstockphoto); `base.reject_host` checks image host and page host by suffix
   and runs before the judge, one `sourcing: <url> rejected: stock preview host <h>`
   line per drop.
4. **Size floor by slot.** `MIN_SHORT_SIDE` (800 px) is gone. `base.reject_size` now
   asks whether the image fills the archival card the renderer would draw for its
   aspect at ≤ 1.5x, using `render.CARD_MAX_W`, `CARD_BASE_H`, `CARD_MAX_UPSCALE` and
   the style's card border (`assets.card_border`), so nothing is typed twice. Deviation
   from the AC as written: a `photo` beat is NOT rejected for an image that cannot
   cover 1080x1920. Under 5.3 such an image is shown as a card (`treatment_downgraded`),
   so the floor "where it will be shown" is the card's; rejecting it would have lost
   F1's 768x896 Baba photo on b08 to an illustration, the opposite of rule 4's last
   sentence, and would have rejected every landscape on every photo beat (the fixture's
   1600x1000 fakes included). The 5.3 cover rule still decides *treatment*, untouched.
   A list/wall base still (dimmed under rows or cells) uses the same card floor.
5. **Commons and Openverse say why.** Both send
   `shortsmith/<version> (https://github.com/infonisista-max/shortsmith) httpx/<v>`.
   `HttpImageSource.search` is now a template around each adapter's `_search`: a
   non-2xx answer, an unreachable host, unreadable JSON and a 2xx with zero candidates
   each leave one note (`ImageSource.note`) that the step writes as
   `sourcing: commons answered 403 for '<query>'` /
   `sourcing: openverse answered 200 with no candidates for '<query>'`. Pexels,
   Pixabay and web get the same notes for free.
6. **T11 checks the face.** `qa.technical._circle_overshoot` now takes the oval
   inscribed in the detector box, scaled into the circle, sampled every half degree;
   the chin rule is unchanged. F1's eight boxes (744-823 px in a 1080 window, 340 px
   circle) pass with the lowest chin at 89 %. Module and function docstrings updated.

What to look for on the next real job:

- `work/assets/*/result.json` for `commons` and `openverse`: `candidates` should be
  non-empty for at least some queries; if still empty, `job.log` now says why
  (`answered 403`, `answered 200 with no candidates`, `could not be reached`).
- `out/rights.json`: no `source_url` or `page_url` on a `STOCK_HOSTS` domain.
- `job.log`: `not searched: a named entity is never shown as a stock stranger` on every
  named-entity beat, and `rejected: stock preview host` lines.
- Contact sheet: named people are the person (name evidence favours URLs that carry the
  name; check b02/b03 Baba, b11 Jobs, b15 Zuckerberg, b19 Kohli, b20 Sehwag).
- `out/qa.json` T11: `every face oval inside the N px circle`.

Amendment lines for `docs/grill-decisions.md` (operator to paste):

- 5.1 — AMENDED by 053 (27 Sep 2026): for a beat whose subject is a named entity
  (`depicts: named_entity`), Pexels and Pixabay are neither searched nor accepted; the
  ladder is owner refs → web → Commons → Openverse with `query`, then with
  `query_fallback`, then the 5.5 stylised illustration, then the 4.4 rungs. Candidates
  whose page URL or file name carry the entity's name (the capitalised words of the
  beat's query) rank ahead of those that do not; the judge still filters. Commons and
  Openverse requests carry a descriptive User-Agent (project, version, repo URL).
- 5.2 — AMENDED by 053 (27 Sep 2026): the hard rejects are: aspect > 3:1, > 15 MB,
  non-image body, a stock-preview host (alamy, freepik, stock.adobe.com / ftcdn.net,
  dreamstime, istockphoto, gettyimages, shutterstock, 123rf, depositphotos, pond5,
  canstockphoto; image or page host), and a size floor that follows the slot: the
  image must fill the card the renderer would draw for its aspect at ≤ 1.5x. The flat
  "short side < 800 px" reject is withdrawn; a full-bleed photo keeps the 5.3 cover
  requirement for its *treatment*, and what cannot cover is a card, never a reject.
  A Commons or Openverse answer that is not 200, or is empty, writes one job-log line
  with the status and the query.
- 10.1 — AMENDED by 053 (27 Sep 2026): T11 PIP geometry checks the oval inscribed in
  the 3.3 detector box (the face), not the box corners: the oval sits fully inside the
  circle on the 8 strip frames, chin above 90 % of the window.

Loops: ruff, pyright, all test files green in three foreground chunks (1194 + 191 +
99 passed), smoke explainer and hitech T1-T13 pass; `out/qa.json` read after the smoke.

## Blocked by

- Nothing.

## User stories addressed

- Operator's F1 verdict, 27 Sep 2026: watermarked stock images, a stranger shown as
  Neem Karoli Baba, delivery blocked by T11 on a correctly framed face.
