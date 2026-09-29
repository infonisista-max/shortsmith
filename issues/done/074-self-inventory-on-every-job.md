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

- [x] With an `httpx.MockTransport`: the upload request, the poll until `ACTIVE`, the
      `generateContent` body carrying the uploaded URI and `videoMetadata.fps`, and the
      delete call, all against recorded JSON under `tests/fixtures/`.
- [x] Smoke passes T1–T13 with `FakeAnalyser`, and writes `out/inventory.json` and the
      comparison rows into `meta.json`.
- [x] A failing analyser leaves the job `delivered` with `status: not_analysed` and the
      reason on the job page.
- [x] Comparison: three fixture v2 cards for one style give the right median and range
      per row; an out-of-range value is marked red; a style with one card shows "not
      enough references".
- [x] A ledger row is written for the step, with its token counts.
- [x] Ruff, pyright and every test file are green in foreground chunks. No test reaches
      the network.
- [x] Operator step, in the done note: the command to run the step on the run04 job
      directory with `.env` back, and what the table showed.

## Done (29 Sep 2026, afk session)

- `GeminiAnalyser.analyse_file`: Files API resumable upload (`start`, then the bytes
  with `upload, finalize`), `files.get` polled every 2 s until `ACTIVE` (`FAILED` or
  not active within 300 s is an `AnalyserError`), `generateContent` with
  `fileData.fileUri` + `mimeType: video/mp4` and `videoMetadata.fps`, then `DELETE`
  whatever happened. The Files API shape in `tests/fixtures/gemini/files.json` is
  written from the documented API with no network: confirm it live with the step below.
- The step `reference.own.SelfInventory` runs in `pipeline.run_job` right after
  `qa -> delivered`, before the verdict and `meta.write`. It uses the same v2 prompt,
  fps and schema through `reference.inventory` (one retry). It writes `out/inventory.json`
  (`tier: own`, `video_id` = job id, `styles` = [job style], `url` = `out/short.mp4`).
  Any exception, including the hard cap, becomes `{"status": "not_analysed", "reason"}`
  plus a `job.log` line `inventory: not analysed: ...`. It never raises and never
  changes the status.
- Ledger: one `reference` row per request (`input_tokens` = prompt + video,
  `output_tokens` = answer + thinking). The hard cap is checked before each request
  with an estimate of 71 tokens per sampled frame. The `reference` provider is "in use"
  (so startup needs its price) whenever `GEMINI_API_KEY` is set.
- Worker default and app without a key: Gemini with no key → `not_analysed` naming
  `GEMINI_API_KEY`, nothing sent. The app passes `own.from_settings`
  (`REFERENCE_MODEL`/`REFERENCE_FPS`/`REFERENCE_ENDPOINT`).
- Comparison (`reference.compare`, in `meta.json.inventory` and on the job page as
  "Against the references (advisory)"). It covers shots, effects and SFX-by-kind per
  10 s, the median clip length, the SFX-on-visible-event share, the layout share of the
  references' top three layouts, bed present, mood per part (plan "—" until 076), music
  change + how, and the match share. Numbers come from the card lists (2 dp), not the
  1-dp `counts`. A number outside the min–max is red; with fewer than 2 v2 cards the
  table says "not enough references" and marks nothing red. The step skips v1 cards and
  `tier: own` cards.
- Operator command: `python -m shortsmith.reference own <job_dir> [--dir DIR]`.

### Operator step (needs `.env` back and network)

1. Add to your `prices.yaml` (startup now needs it whenever `GEMINI_API_KEY` is set),
   with your real Gemini numbers:
   ```yaml
   reference:
     input_tokens: <INR per 1k>
     output_tokens: <INR per 1k>
   ```
2. Run the step on the run04 job:
   `uv run python -m shortsmith.reference own data/jobs/<run04 job id>`
   It uploads `out/short.mp4`, analyses it, deletes the upload, writes
   `out/inventory.json`, adds the ledger rows, rewrites `out/meta.json` and prints the
   table. If the Files API answers differently from `tests/fixtures/gemini/files.json`
   (the upload header, the `file` wrapper, the state names), paste the error line back
   and the adapter and the fixture get fixed.
3. What the table showed: not run in this session (no network, `.env` parked). Until
   `inventory --all` has written v2 cards, every style reads "not enough references"
   (the committed cards are v1). The smoke's fixture short gives 16 rows under
   explainer. Once the v2 cards exist, re-run step 2 and look at the red rows.

## Blocked by

- `issues/073-reference-card-v2.md`

## User stories addressed

- Operator, 29 Sep 2026 (grill): "our own output goes through the same inventory tool,
  so we can compare it with the references by numbers."
