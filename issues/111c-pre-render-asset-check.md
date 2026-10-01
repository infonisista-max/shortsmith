# 111c — The pre-render check: every asset fits its component before node starts

## Type

AFK. Part of 111. Needs 111a and 111b.

## What to build

- **New `render_check.py`, run once on the finished spec**, after `build_spec` and before
  node (in `run_driver`, render.py:3407-3418). It walks every `src` in the spec (base
  visuals, items, badges, cards, stickers, icons, infographic bases) and checks it with
  `media.probe` against what its slot can draw (image or video).
- **Repairs, in order. Each is one job.log line (`check: bNN: <what> -> <repair>`) and
  never a failure:**
  1. A wrong type: a clip in an image slot → frame grab. An image in a video slot →
     still treatment (photo with the beat's camera move).
  2. A browser-unsafe format (gif/bmp/tiff/avif/heic/webm/non-H.264) → `media.as_still`
     or `as_clip`, cached next to the asset.
  3. Missing or unreadable → the beat's next asset in `assets.json` that probes good;
     else the gradient (the 096 rung 4) for a base, or the slot is dropped for an
     item/sticker/badge.
- Repairs add one plain-words line to `JobRecord.warnings` in total, with a count (e.g.
  "3 pictures were swapped for safe versions before rendering").
- It is pure over (spec, files) apart from the conversions, so most tests need no node.

## Acceptance

- Unit tests: a spec with a clip in each image slot, a mislabelled WebP, a .gif, a
  missing file, and a zero-byte file. The check returns a spec in which every src
  probes as its slot's type, plus the log lines.
- Today's job: run `render_check` as a script over its `work/render_spec.json` (read-only
  on the job, output in the scratchpad). It repairs b52.

## Files

`render_check.py` (new), one call in `render.py`, `tests/test_render_check.py`.
