# 111 — A small problem in one beat never fails a job, rendering included

## Type

Parent (split into 111a-111g under the context-budget rule). Operator brief, 1 Oct 2026.

## Why

Job 20261001-082005-826f78 failed at rendering. b52 is a `wall` beat; sourcing gave its
background a stock clip (clip-1.mp4), but `render.py:1112-1127` sends list/wall bases through
`base_visual()` (render.py:686-696), which hard-codes `treatment="photo"`. Chrome cannot
decode an .mp4 in `<Img>`, and the render died at frame 1687 of 1776. The 097 rescue only
knows beats a message names (`bNN:`). A raw driver error names none, so it stripped every
overlay once and then failed. Separately, the first render was killed by the single
30-minute job watchdog (pipeline.py:298) after about 18 min of planning, sourcing and
rescue. `input/refs/7_sei-sei-ravi-shankar.jpg` is not a real JPG, so OpenCV skips it.

Operator's goal: end users will never have a developer to call. Fix the whole class, not
just b52.

## Parts (in order)

- 111a: a `media` probe, and every uploaded photo becomes a real JPG/PNG at intake
- 111b: wall/list clip backgrounds move; a sweep of every media-type assumption in the renderer
- 111c: the pre-render check repairs every asset mismatch before node starts
- 111d: the render-time net finds the failing beat, simplifies it, and renders again
- 111e: time budgets per step scaled to length, a retry gets its own, and render.log has timestamps
- 111g: the last rung: any failure after planning delivers the plain reel with a warning
- 111f: the test that would have caught today (runs last, after 111g)
