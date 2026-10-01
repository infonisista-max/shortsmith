# 112b — The renderer's downgrade repairs behind the switch, and the pre-render gate

## Type

AFK. Part of 112. Needs 112a (`quality.downgrade`, `QualityStop`, the per-job mode).
After this ticket, **stop**: the operator runs one fresh strict job before 112c/112d.

## What to build

- **Every log line names its real cause** (operator review of `render_check.fix()`, 2 Oct
  2026). Today the three `return None` paths (no alternate found, a frame grab that failed,
  a conversion that failed) return with no note. `dropped()` then logs all of them as
  "missing or unreadable -> the gradient", which gives the wrong cause.
  - Each path notes its own reason first: "missing and no other asset for this beat";
    "frame grab failed: <error>"; "conversion to JPG/H.264 failed: <error>".
  - `dropped()` only says what was done; it never guesses a cause.
  - Strict carries the same reason onto the page and into `data/quality-log.tsv` (112a).
    A test covers each of the three paths.
- **Collect everything, stop once.** `render_check.check()` already walks every beat with
  no early exit. In strict mode it records every downgrade it *would* make, as findings,
  and the job stops once with the whole list. In strict mode, the pre-render gate (below)
  first builds the spec and runs this check in record-only mode. Gate findings and check
  findings then come back as **one** stop before node, so one run shows all of a job's
  problems.
- **A browser-safe WebP is already real** (operator question on 111a). `media.is_real_still`
  accepts JPEG and PNG only, so intake and `normalise_refs` re-encoded a good `.webp` to
  JPEG at quality 92: an always-on lossy step nobody asked for. A WebP by content under a
  `.webp` name now counts as real and is kept byte for byte. Mislabelled files, AVIF and
  the rest are still converted, since the browser cannot draw them. Check that the face
  detector reads a WebP (OpenCV, else its Pillow fallback). Tests in `test_media.py` and
  `test_ingest.py`.
- **The 111b/111c repairs go through `quality.downgrade`** (strict → loud stop naming the
  beat and cause; forgiving → today's repair):
  - A clip in a still's slot becomes a frame grab: `render.still_path`/`asset_still` and
    its callers `_visuals` (including the drop to `pip` when no frame can be had),
    `card_sources`, `item_sources`, `badge_source` and `diagram_base`, plus
    `render_check` ~l.127-136.
  - A still in a clip's slot is drawn as a photo with a camera move (`render_check`
    ~l.137/167).
  - A missing or unreadable file takes another asset, or the gradient/`pip`; a wall cell,
    finale card or sticker is dropped; a split is left out over a bad pane; the badge is
    dropped; a diagram is left out; a row icon box is removed (`render_check` ~l.120-126
    (when not the same sha256), 160-163, 211-232, 250-257).
  - A face-read error treated as "no face" (`build_spec` `face_in`/`faces_all`/stamp
    ~l.3106-3163). After 111a this means a corrupt file, so in strict mode it is a loud
    stop naming the beat and the file.
- **These stay on in both modes (true fixes):** format conversion to JPG/PNG/H.264, a
  same-sha256 replacement, and a wall/list base playing its clip.
- **The 111d net.** The diagnosis always runs: the failing frame, its beat, and the
  per-beat stills pass. In strict mode the stills pass covers **every** beat, not only the
  ones near the failing frame. The job then stops once, naming every beat whose still
  failed, with Remotion's error message for each. It never simplifies. In forgiving mode
  it behaves as today.
- **The pre-render gate (strict only)**, run after sourcing and before rendering starts:
  - Count the b-roll beats (beats that wanted a picture or clip; presenter-only beats do
    not count) whose final visual is a gradient or a generated image, from `assets.json`
    and the sourcing decisions.
  - If `settled / b-roll beats` is above `STRICT_SETTLED_MAX_SHARE` (a new setting,
    default **0.25**), stop before rendering with `QualityStop`. The page shows "stopped
    before rendering: N of M picture beats settled for a gradient or a generated image",
    and the list underneath: per beat, what was wanted, what was used, and why (the
    sourcing log's reason). The same list goes to job.log.
  - At or under the line, rendering goes ahead; the list is written to job.log as
    `settled:` lines (112d puts it on the page).
  - Forgiving mode never runs the gate.
  - Why 0.25: a reel over a quarter fallbacks is far from the approved references
    (`docs/reference/README.md`); the share is a setting, so the operator can move it
    without code.
- **Tests:**
  - Strict: a clip in each still slot, a missing file and a corrupt face file each stop
    loudly, naming the beat. A mislabelled WebP and a same-sha replacement still deliver.
  - Strict: a render failure stops naming the beat after the diagnosis, with no re-render.
  - Strict: the gate stops at 0.26 and goes ahead at 0.25.
  - Forgiving: the 111f variants still deliver (`test_render_safety` pinned to forgiving),
    plus one strict variant of it in which the format case delivers and the clip/missing
    cases stop naming the beat.
  - Smoke runs in strict mode and must deliver and pass the gate. If the fixture trips the
    gate, fix the fixture's sourcing, never the threshold.

## Acceptance

- [x] In strict mode, today's b52 case (a clip under a still-only slot, a missing file) fails
  in seconds, before node, naming the beat. The wall/list clip case delivers.
- [x] A strict spec with three bad beats stops once, listing all three, each with its true cause.
- [x] A good WebP ref is not re-encoded.
- [x] The gate stops a job with too many fallbacks before rendering and shows the list.
- [x] Every test file is green; smoke delivers in strict mode; `npm` checks run if
  `src/remotion/` was touched.

## Files

`render.py`, `render_check.py`, `pipeline.py` (the gate between sourcing and rendering),
`config.py` (`STRICT_SETTLED_MAX_SHARE`), `app.py` (the stop page lists the beats), tests.

## Done (2 Oct 2026)

- Phase 1: the true cause on every `render_check` drop; a real WebP kept byte for byte;
  the 111b/111c repairs and the face-read error as findings (`render.recording()`,
  `check(record_only=True)`), one strict stop before node in `render_picture`.
- Phase 2: the 111d net in strict runs the diagnosis, then one still per beat over every
  beat, and stops once (`_Net.diagnose`) naming each failing beat with Remotion's error
  (`run_stills(errors=)`); it never simplifies or re-renders. `STRICT_SETTLED_MAX_SHARE`
  (default 0.25) and the strict pre-render gate (`prerender.py`), run inside
  `render_picture` after the check and before node: over the line, one `QualityStop`
  with the gate's list plus the build and check findings, headed "stopped before
  rendering: N of M picture beats settled for a gradient or a generated image"; at or
  under it, `settled:` job.log lines and `settled` quality-log rows. The smoke always
  runs strict and checks the gate (the fixture settles 0 of 8).
- The gate sits in `render_picture`, not `pipeline.py`: that is where the build and check
  findings exist, so the one stop can carry all three (after the cut and voice, still
  before node). See work/questions-for-shubham.md 9-12.
