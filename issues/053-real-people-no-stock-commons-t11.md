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

- [ ] Fixture from F1's `work/assets/*/result.json` candidates: the named-entity beats'
      picks are never a Pexels or Pixabay URL; with the name rule, a candidate whose page
      URL contains `neem-karoli-baba` outranks one that doesn't.
- [ ] Same fixture: no candidate from the stock-host list reaches the judge; each drop
      writes a `job.log` line.
- [ ] Size floor by slot: a 600 px and a 768 px short-side image are accepted for a card
      beat and rejected for a full-bleed photo beat that they cannot cover at ≤ 1.5x;
      the exact thresholds are derived from the render geometry constants, not typed twice.
- [ ] Commons and Openverse requests send the descriptive User-Agent (test on the request
      headers); a 403 and an empty result each produce one `job.log` line naming source,
      status and query.
- [ ] T11: F1's `job.json` presenter numbers pass (all 8 frames); a face whose oval
      leaves the circle by ≥ 10 % of its radius fails with the frame named; a chin below
      90 % still fails.
- [ ] Every existing test that encoded the old rules is updated to the new ones, not
      deleted; ruff, pyright, all test files green in foreground chunks, smoke explainer
      and hitech T1–T13.
- [ ] Done note: what the operator should look for on the next real job (Commons and
      Openverse candidate counts in `work/assets/*/result.json`, no stock host in
      `out/rights.json`, named people correct on the contact sheet), and the three
      amendment lines for `docs/grill-decisions.md` (5.1, 5.2, 10.1) for the operator
      to paste.

## Blocked by

- Nothing.

## User stories addressed

- Operator's F1 verdict, 27 Sep 2026: watermarked stock images, a stranger shown as
  Neem Karoli Baba, delivery blocked by T11 on a correctly framed face.
