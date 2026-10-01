# 112a — The switch, and a loud failure instead of the rescue nets

## Type

AFK. Part of 112 (read it for the line between strict and forgiving).

## What to build

- **The setting.** Add `QUALITY_MODE` to `config.Settings`, with the values `strict` |
  `forgiving` and the default `strict`. Agents never edit `.env`/`.env.example`; list the
  key for the operator in the commit message.
- **The mode belongs to each job.** It is stamped on `job.json` (`quality_mode`) when the
  job is created, and every layer reads it from the job record. The job page shows the mode
  under the status. A job with no stamp (made before 112a) reads the current setting.
- **One helper and one error.** For example, `quality.downgrade(job, beat, cause,
  detail, apply)`:
  - **strict:** raises `QualityStop(beat, cause, detail)`.
  - **forgiving:** runs `apply` (today's repair), logs it, and records the decision exactly
    as today.

  Every gated site in 112a-112c calls it, so a site never has its own `if strict`.
- **A stop carries a list, not one problem.** `QualityStop` holds a list of findings,
  each with the beat, the beat kind, the cause and the detail. A pass that walks many
  beats (112b's check and gate) records every finding and stops once with the whole list.
  The page shows all of them.
- **One running file across jobs.** The helper appends every finding, in both modes, to
  `data/quality-log.tsv` (git-ignored; check `.gitignore`). Its columns are UTC date,
  job id, beat, beat kind, outcome (`stop` | `repair` | `settled`) and cause, the same
  words the page shows. Nothing ever rewrites or rotates it. After a few test jobs, the
  operator sorts it to see what breaks most often.
- **A reel that rendered is always shown.** When a strict stop comes after a reel exists
  (a QA check failing, or anything after the mux), the failure page still shows the
  player and the download for `out/` next to the loud failure and its cause. It is
  labelled "rendered, not passed". If only the picture rendered (the mux crashed), the
  page shows that file, labelled "picture only, no sound". It is still a failure; the
  operator just gets to watch what the system made.
- **The loud failure.**
  - `QualityStop` is never rescued: add it to `NOT_RESCUED` and the plain-reel path.
  - The job ends `failed` at the step it was in. The job page shows the beat (e.g.
    "beat 52"), the cause in plain words (e.g. "its background is a video clip, but a wall
    draws a still"), and the technical error under a details fold. The same lines go to
    job.log as `strict stop:`.
  - Retry works as today.
- **Gate the pipeline and editor nets (group 1 of the inventory)** behind the helper:
  - 097 `Rescue.attempt` editor options: `replace_visual`, `new_picture`, `drop_layer`,
    `plain_cut`, `drop_route`, `keep`, `_force_hard` (`replace_visual` / `no_cut` / the
    safest beat for a must-use reference), and the gradient on the third repeat.
  - The 097 strip-all-overlays (`Rescue._net_exhausted` / `_strip`).
  - The 111g plain reel (`run_job` → `_plain_reel`, `render_plain` with its ffmpeg-only
    and voice-only branches), and `_plain_qa`.
  - The "step finished after its budget ran out carries on" branch (pipeline ~l.379). In
    strict mode an expired step budget is a loud stop that names the step.
  - A waived QA check delivered as warn (`qa/gate.py` ~l.53-60, `Rescue._qa` "deliver with
    a note"). In strict mode, a failed check stops the job and names the check.
  - A missing style replaced by the default (`style_of` ~l.488-501), and a plan request
    built without its worked examples or music pairings (`build_plan_request` ~l.525/530).
  - `keep_soft`: soft grammar rules are **not** gated. They are the planner's own taste
    rules, a "kept, listed" case. Leave them as they are.
  - Leave 095's transient retry (same model, once) alone. Its failover to another model is
    112c.
- **Tests stay honest.** Every existing test that relies on a net (`test_editor`,
  `test_plain_reel`, `test_pipeline`, `test_app`, `test_render_safety`, …) sets
  `forgiving` explicitly and keeps passing unchanged in meaning. Each gated site gets a
  strict-mode test: the job fails, and the page and job.log name the beat (or step or
  check) and the cause. Smoke runs in the default (strict) mode and must deliver. If it
  does not, fix the cause, never the mode.

## Acceptance

- [x] `QUALITY_MODE` defaults to strict; a job stamps its mode, and the page shows it.
- [x] Strict: a stubbed render failure, a mux crash, a QA failure and an expired step budget
  each fail loudly, naming the beat or step or check. No plain reel is made and no beat is
  simplified.
- [x] Forgiving: the same four cases behave exactly as on `9e28146`.
- [x] A strict QA failure shows the rendered reel on the failure page, labelled.
- [x] Each case appends its rows to `data/quality-log.tsv`; a second job appends, never overwrites.
- [x] Every test file is green; smoke delivers in strict mode.

## Files

`config.py`, `quality.py` (new), `jobs.py`, `app.py` (job page), `pipeline.py`,
`editor/` (repairs and the fallback), `qa/gate.py`, tests.

## Done (2 Oct 2026)

- `config.Settings.quality_mode` (`QUALITY_MODE`, default `strict`). `jobs.create` stamps
  `job.json.quality_mode`, and a job with no stamp reads the setting (`quality.mode_of`). The job
  page shows "Quality mode: ..." under the status.
- `src/shortsmith/quality.py`: `downgrade` / `downgrade_all` / `stop`, `QualityStop` (a list of
  `jobs.QualityFinding`: beat, kind, cause, detail), and the append-only `data/quality-log.tsv`
  (header written once; columns date_utc, job, beat, beat_kind, outcome, cause).
- The loud failure is `pipeline.strict_stop`. The job fails at its step, with `error.findings`
  and one `strict stop:` job.log line per finding. The page lists every finding with a
  details fold. A stop at rendering or qa shows `out/short.mp4` ("rendered, not passed"),
  or `work/picture.mp4` through `/jobs/{id}/picture-only.mp4` ("picture only, no sound").
- Gated: `Rescue.attempt`, which covers every editor option, the second-time replace_visual,
  the third-time gradient, the strip-all-overlays and QA's "deliver with a note";
  the 111g plain reel; the late-finishing step; `style_of`'s default style;
  `build_plan_request` (examples and pairings); `_force_hard`; and the waived check in
  `technical.waive`, used by both `technical.run` and `FakeGate`. `QualityStop` is in
  `NOT_RESCUED`.
- Not gated, as the ticket says: `keep_soft`, 095's transient retry and `_rescue_sound`
  (112c). The planning editor's rounds are left for 112c too (questions file, item 6).
- Tests: `tests/test_quality.py` (25) and one route test in `test_app.py`. Every test file is
  green, in chunks; smoke delivers in strict mode.
