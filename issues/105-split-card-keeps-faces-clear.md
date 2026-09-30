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

- [ ] Test: a portrait with a face near the top keeps the face inside the pane.
- [ ] Test: the strip box never intersects a face box.
- [ ] A Remotion test for `objectPosition`; smoke green.

## Blocked by

None.

## User stories addressed

Operator, 30 Sep 2026, finding 2: "the text strip runs across the photo near the man's
face."
