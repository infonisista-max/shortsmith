# 074 — Self-inventory: every delivered short goes through the reference tool, and the job page compares it with the references by numbers

## Type

AFK — no new packages (httpx already speaks to Gemini).

## Parent PRD

`issues/prd.md`

## What to build

Operator decision (grill, 29 Sep 2026): our own output goes through the same inventory
tool as the references, so the two can be compared by numbers. It runs on **every
delivered job**, **advisory, never blocking**.

- **Local file input.** `GeminiAnalyser` today takes only a public YouTube link
  (`reference/gemini.py:104-110`, `fileData.fileUri`).
  - Add a path for a local file: a Gemini Files API resumable upload of
    `out/short.mp4`, then wait until the file is `ACTIVE`, then the same
    `generateContent` call with the uploaded file's URI.
  - The call uses the same v2 prompt (073), the same `REFERENCE_FPS` and the same
    schema, so the numbers are comparable.
  - The uploaded file is deleted from Gemini after the answer.
  - `ReferenceAnalyser` gains `analyse_file(path, prompt)`, and `FakeAnalyser`
    implements it.
- **The job step.** A new advisory step `inventory` runs after `qa` on a delivered job.
  - It writes `out/inventory.json` (a v2 card with `tier: own`, `video_id` the job id).
  - It reports its tokens to `ledger.py` as a `reference` step row; prices come from
    `prices.yaml`.
  - Any failure (no key, upload refused, malformed answer after one retry) writes
    `out/inventory.json` as `{"status": "not_analysed", "reason": ...}`. It logs the
    reason, and the job stays `delivered`.
  - The step never changes the short and never blocks delivery or the editorial gate.
- **The comparison table** on the job page, and in `out/meta.json`. Each row shows our
  number beside the median and range (min–max) of the v2 cards whose `styles` include
  the job's style. It is marked red when outside the range. Rows:
  - shots per 10 s, effects per 10 s, median clip length;
  - SFX per 10 s by kind, and the share of SFX on a visible event;
  - layout share (the top three layouts);
  - bed present, the mood per story part against the plan's moods (076 fills the
    plan's side; until then "—"), and a music change yes/no with its `how`;
  - match share: literal + named_entity + number, as a share of beats (077 uses it).

  A style with fewer than two v2 cards shows "not enough references" instead of a
  range. v1-only cards are skipped for the v2 rows.

## Acceptance criteria

- [ ] With an `httpx.MockTransport`: the upload request, the poll until `ACTIVE`, the
      `generateContent` body carrying the uploaded URI and `videoMetadata.fps`, and the
      delete call, all against recorded JSON under `tests/fixtures/`.
- [ ] Smoke passes T1–T13 with `FakeAnalyser`, and writes `out/inventory.json` and the
      comparison rows into `meta.json`.
- [ ] A failing analyser leaves the job `delivered` with `status: not_analysed` and the
      reason on the job page.
- [ ] Comparison: three fixture v2 cards for one style give the right median and range
      per row; an out-of-range value is marked red; a style with one card shows "not
      enough references".
- [ ] A ledger row is written for the step, with its token counts.
- [ ] Ruff, pyright and every test file are green in foreground chunks. No test reaches
      the network.
- [ ] Operator step, in the done note: the command to run the step on the run04 job
      directory with `.env` back, and what the table showed.

## Blocked by

- `issues/073-reference-card-v2.md`

## User stories addressed

- Operator, 29 Sep 2026 (grill): "our own output goes through the same inventory tool,
  so we can compare it with the references by numbers."
