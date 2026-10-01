# 111b — A wall or list with a clip background moves; the renderer never assumes a media type

## Type

AFK. Part of 111. Needs 111a (`media.probe`, `media.as_still`).

## What to build

- **Wall/list base (`render.py:1112-1127`, `base_visual` 686-696).** When the base asset
  is a clip, it is drawn as the moving clip, dimmed and zoomed exactly as the still base
  is now. Fix `BASE_STILL_KINDS` (render.py:1033), which lists `clip`, where that is
  wrong. In TS, the wall/list background gets a video branch: reuse `clip.tsx`'s
  `<Video>` setup, with no new package.
- **Sweep: every other place that assumes a type** gets the same rule (clip → moving if
  the component can play it, else a frame grab via `media.as_still`; never an .mp4 in
  `<Img>`):
  - `badge_source` (render.py:2815-2828 → split.tsx:148): frame grab.
  - `diagram_base` (render.py:2854-2869 → infographic.tsx:31): frame grab.
  - `item_sources` (render.py:2794-2800): it raises `RenderError` on a clip today. Use a
    frame grab instead, logged.
  - The photo/card/crop_fill/backdrop/polaroid `<Img>` paths (photo.tsx:50 and its
    users), list icons (list.tsx:51), split panes (split.tsx:59), placed cards
    (hook_cards.tsx:52, wall, finale), and stickers (sticker.tsx:38): the Python side
    guarantees a still path (frame grab) before the spec is written.
  - `driver.mjs:35-43` MIME map: add .gif/.webm/.avif/.bmp as a backstop (111c makes
    sure only jpg/png/webp/mp4 reach it).
  - Faces on the still path (render.py:1153 → `HaarDetector`): an unreadable file logs
    and is treated as having no faces. It never raises.
- Write a short list of every site touched, with its rule, in the commit message.

## Acceptance

- A list beat and a wall beat whose base is a clip render a moving, dimmed, zoomed
  background (real driver, fixture clip, a short test spec).
- The split badge, infographic base and list item given a clip each render a frame grab.
- Before/after frames of a wall beat are checked against `docs/reference/README.md` (the
  dim and zoom match the still base).
- `npm run typecheck` and `npm test` pass.

## Files

`render.py` (the sites above), `src/remotion/components/{wall,list}.tsx` (or the shared
base they use), `driver.mjs` (MIME map), tests in `test_render.py` plus a TS test.
