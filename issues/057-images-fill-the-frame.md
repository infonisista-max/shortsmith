# 057 — More full-screen images: a portrait image that fills the frame at ≤ 2.0x goes full-bleed, web images included

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Operator's phone verdict on run03 (job `20260927-140915-bbad1c`, score 6, "can upload"):
"pop-up images are small; a lot of the screen is unused; every video has the same style."

What the job's own files show (`work/assets.json`): 24 image beats, 23 drawn as a card,
1 full-bleed. Eight of the cards were beats the planner asked to be `photo`
(`treatment_downgraded: true`). The card itself cannot grow: it already runs from about
y 195 to the line `PIP_GAP_PX` above the PIP circle (y 928); the space left unused is the
blurred cover around a portrait card and the area beside the circle.

Why so few full-bleed images, from the code (`assets.full_bleed`, `assets.classify`):

- `full_bleed` rejects any image under 1080 px wide *before* upscaling. Decision 5.3 says
  "≥ 1080 px wide after ≤ 1.5x upscale"; the code is stricter than the decision. run03's
  owner photo 1000 × 1406 covers the frame at 1.37x and still became a card.
- `classify` never lets a `web` image be full-bleed (5.1: "web images are always
  re-dressed as cards"). Trump 1120 × 1496 covers at 1.28x and became a card.
- The cover limit is 1.5x. run03's main owner portrait (819 × 1024, eleven beats) needs
  1.875x.
- The 055 opening ("full-screen images behind the speaker") therefore opened on cards:
  b01 and b02 are cards on the contact sheet.

Operator decision, 27 Sep 2026 (amends 5.1's "web images always cards" and 5.3's
full-bleed rule; the operator records it in `docs/grill-decisions.md` from the done note):

1. An image goes full-bleed (`photo`, the style's Ken Burns, PIP circle and captions over
   it) when the planner asked `photo` or `auto`, it is portrait or square (height ≥
   width), and it covers 1080 × 1920 at an upscale of at most
   `broll.full_bleed_max_upscale` — a new style front matter number, 2.0 in explainer,
   educational, animated and hitech. Width is judged after the upscale, never before.
2. The origin no longer matters: owner, web, Commons, Openverse, stock and generated
   images follow the same rule. The Ken Burns and the overlays are the re-dressing.
3. Landscape images and images that cannot cover the frame at ≤ 2.0x stay cards, drawn
   exactly as today (card size and the 1.5x card upscale unchanged).
4. The opening beats (055) ask for `photo`, so the opening is full-screen whenever the
   image allows; planner prompt v8 says so in one line (v7 said "`photo` or `card`").
5. The contact sheet summary line shows "full-screen N / card M" so the mix is visible
   on every job.

## Acceptance criteria

- [ ] run03's `work/assets.json` and `work/plan.json` as fixtures: b01, b05, b08, b10 and
      b13 (819 × 1024, planned `photo`) and b14 (web, 908 × 1024) become `photo`; b19
      (1600 × 1169) and b22 (1024 × 632) stay cards; beats the planner asked as `card`
      stay cards; b07 stays `photo`.
- [ ] A 1000 × 1406 web image and a 1080 × 1920 image go full-bleed; a 500 × 900 image
      (needs 2.16x) and any landscape image stay cards. The 2.0 is read from the style,
      not typed in code.
- [ ] Every style's front matter carries `broll.full_bleed_max_upscale: 2.0`; `version`
      bumped; the 5.1 source line in each style spec no longer says web images are
      always cards.
- [ ] Planner prompt v8: the opening beats ask for `photo`; the fake planner follows it.
- [ ] The contact sheet summary shows the full-screen / card count.
- [ ] T12 safe area still passes; smoke explainer and hitech T1–T13; `npm run typecheck`
      and `npm test` if `src/remotion/**` changes; ruff, pyright, every test file green in
      foreground chunks.
- [ ] Done note: the amendment lines for 5.1 and 5.3 for the operator to paste, and what
      to look at on the next real job (the full-screen / card count, softness of the
      2.0x images on the phone).

## Blocked by

- Nothing. Independent of 056.

## User stories addressed

- run03 phone verdict, 27 Sep 2026: "pop-up images are small; lots of area on screen is
  unused."
- Operator, 27 Sep 2026 (055): "at the start just use the most relevant, most interesting
  images in the background".
