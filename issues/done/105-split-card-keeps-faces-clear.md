# 105 — Split cards keep faces clear: face-aware pane crop, and the text strip never on a face

## Type

AFK (touches `src/remotion`)

## Parent PRD

`issues/prd.md`

## Why

Run05 b16 (0:31-0:32):
- `render.py:1811-1839` `_stacked` puts the title band at a fixed spot between the panes.
- `split.tsx:63` crops each pane at the centre (`objectFit: cover`, no `objectPosition`).
- `SplitPane` (`contracts.py:1516`) has no focus field.
- The face detector (`face_on`) is never used on panes.

So the top portrait lost its face and the strip ran across the seam.

## What to build

- Per pane: detect the face and pass `focus_x/y` as `objectPosition`, so the face sits in
  the pane's upper third (front matter).
- The strip's position (seam, top or bottom) is chosen to miss both face boxes; if none
  fits, the strip shrinks. It is never across a face. The same face check applies to text
  pops and stamps on split panes.

## Acceptance criteria

- [x] Test: a portrait with a face near the top keeps the face inside the pane.
- [x] Test: the strip box never intersects a face box.
- [x] A Remotion test for `objectPosition`; smoke green.

## Blocked by

None.

## User stories addressed

Operator, 30 Sep 2026, finding 2: "the text strip runs across the photo near the man's
face."

## Done (30 Sep 2026)

- Face-aware pane crop: `build_spec` runs the 3.3 detector on every split pane's file
  once (`face_in`, src/shortsmith/render.py:2405) and hands it to `split_spec`
  (render.py:1953, via `set_piece` at 2599). `pane_focus` (render.py:1839) picks the
  `objectPosition` that puts the face's centre across the pane's middle at the style's
  `split.face_y` (0.3) of the picture, moved in just enough to keep a face that fits
  whole; `SplitPane.focus_x/focus_y/face_box` (src/shortsmith/contracts.py:1552) carry it
  and src/remotion/components/split.tsx:66 draws it. A pane where the detector finds no
  face is framed at `split.faceless_y` (0.1, the top: a split pane is a portrait, 5.2) -
  run05's second portrait (a turned head Haar misses) now shows the king's face; with no
  detector at all the centre crop stays (render.py:1989).
- The strip: `SPLIT_STRIPS` (render.py:1824) - stacked: seam, bottom, top; side: bottom,
  top. The first place whose band shares no rows with a face (the face as drawn, not
  clipped to its pane, so a face the pane edge cuts counts) wins; none fits -> the band
  shrinks step by step to the least that holds the minimum title font; still none -> the
  strip is left off (render.py:2010). Never across a face.
- Stamps and text pops on a split: `split_face_boxes` / `stamp_off_split`
  (render.py:2041, 2059) move a stamp off a pane's face to a free band (a picture's upper
  or lower third, between the two faces, under the card), wired at render.py:2605; the
  panes' faces join a text pop's blocked boxes (render.py:2453).
- Style keys (all five split styles; versions explainer 23, hitech 22, recipes 13):
  `split.face_y: 0.3`, `split.faceless_y: 0.1`.
- Tests: tests/test_split_faces.py (17), src/remotion/tests/registry.test.mjs:370.
  Run05 b16 re-laid with the real Haar detector: the top portrait's face (found at
  239,134 150x150) now sits in the pane's upper part with the strip at the seam, clear of
  it. Before/after stills in the session scratchpad (not committed).
