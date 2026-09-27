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

## Done note (28 Sep 2026)

What changed:

- `styles.Broll.full_bleed_max_upscale` (required, > 0); every style's front matter
  carries `broll.full_bleed_max_upscale: 2.0`, `version` bumped 4 → 5. Explainer's 5.1
  prose line now says every image is re-dressed the same way whatever its source: a
  portrait or square asked as `photo` that covers the frame at ≤ the number goes
  full-screen, anything else is a card; "web images are always re-dressed as cards" is
  gone.
- `assets.full_bleed(width, height, max_upscale=...)`: height ≥ width and
  `covers_frame(width, height, max_upscale)`; no pre-upscale width floor. `classify`
  takes `max_upscale` instead of `origin`; `source_assets` passes the spec's number in.
  `base.covers_frame` takes the upscale from the caller (the card slot's 1.5x in
  `reject_size` is untouched).
- Contact sheet counts line: `clamps N · rescued N · full-screen N / card M`.
- Planner prompt v8 (`picture_v8.md`, `sound_v8.md` unchanged in words): the opening
  beats are `photo` ("code draws a card only when the image cannot fill the frame at
  `broll.full_bleed_max_upscale`"); the entity bullet says the same. The fake planner's
  b01 and b02 both ask `photo`; b04 (a1 again, with the stamp) is now the plan's one
  planned `card`, so every tier-1 kind is still named once. In the smoke, b02's web
  image is a 1600×1000 landscape, so it is drawn as a card (the card path stays
  rendered) and the lower-third sits on its strip as before.
- Tests: run03's beat table (planned kind, origin, real size → treatment) is in
  `tests/test_assets.py::RUN03`, transcribed from the job's `work/plan.json` and
  `work/assets.json`; the 1000×1406 web image, 1080×1920, 500×900, landscape and
  "2.0 is read from the style" cases; every style carries the number; the counts line;
  the v8 prompt and its recorded snapshots; the floor hits and the critic summary follow
  the fake plan's new kinds; the two adapter reply fixtures (`claude_cli`, `anthropic`)
  carry the same plan.

Loops: ruff, pyright, all 51 test files green in five foreground chunks, smoke explainer
and smoke hitech T1–T13 pass (explainer 62.6 s, hitech 58.8 s). No `src/remotion/**`
change, so the npm loops did not apply.

Denied in this session, left for the operator (none reached another way):

- `Copy-Item` of run03's `work/plan.json` and `work/assets.json` into
  `tests/fixtures/run03/` was denied, so the fixture is the transcribed table in
  `RUN03` instead of the two files; `tests/fixtures/run03/` exists empty and untracked
  (delete it, or drop the two files in and point a test at them).
- Editing `CLAUDE.md` was denied. Its rule line still says "web images are always
  re-dressed, never shown raw"; replacement line: "every asset gets a rights-log row
  with its source URL. Every image is re-dressed the same way whatever its origin
  (057): a portrait that covers the frame at ≤ `broll.full_bleed_max_upscale` is
  full-screen under the Ken Burns, PIP and captions; anything else is a card."
- Setting `SHORTSMITH_UPDATE_SNAPSHOTS=1` was denied, so the v8 snapshots were written
  from the v7 ones with the changed paragraphs; the snapshot test compares them byte
  for byte and passes.

Amendment lines for `docs/grill-decisions.md` (operator pastes):

- 5.1 — AMENDED by 057 (28 Sep 2026): "Web-sourced images are always re-dressed per
  the card/archival patterns, never shown raw" is withdrawn. The origin of an image
  no longer decides its treatment: owner, web, Commons, Openverse, stock and generated
  images follow the same 5.3 rule; the Ken Burns, the PIP circle and the captions are
  the re-dressing of a full-screen image, the card frame that of a card.
- 5.3 — AMENDED by 057 (28 Sep 2026): full-bleed `photo` when the planner asked
  `photo` (or left it open), the image is portrait or square (height ≥ width) and it
  covers 1080×1920 at an upscale of at most `broll.full_bleed_max_upscale` (2.0 in
  every style), the width judged after the upscale, never before. Landscape images and
  images that cannot cover the frame at that upscale stay cards, drawn exactly as
  before (card size and the 1.5x card upscale unchanged). The opening beats ask
  `photo` (prompt v8). The contact sheet summary shows "full-screen N / card M".

What to look at on the next real job (run04):

- The contact sheet counts line: the full-screen / card mix. run03's manifest would now
  give 8 full-screen of 24 image beats (b01, b05, b07, b08, b10, b13 and b14 from the
  owner portrait and one web image; b07 unchanged) against 1 before.
- Softness of the 2.0x images on the phone: the 819×1024 owner portrait is shown at
  1.875x (plus the Ken Burns' 1.10–1.16). If it reads soft, the knob is
  `broll.full_bleed_max_upscale` in the style, not code.
- Whether the planner (v8) now asks `photo` on the opening beats and on entity beats
  where a card was the habit; `treatment_downgraded` counts on the sheet tell how often
  a `photo` ask met a landscape.

## Second session (28 Sep 2026) — STILL NOT COMMITTED, commit denied again

The first session's `git commit` was denied and the tree was left staged and
described above. This session found the staged tree, matched it to this ticket
(the diff is exactly the five decisions: `full_bleed`/`classify` on the style's
`broll.full_bleed_max_upscale` with no origin check, the number in every style with
`version` 5, prompt v8 opening on `photo`, the counts line, the run03 table), and
re-ran every loop in the foreground before committing. No source edit was made.

Loops seen green this session: ruff; pyright (0 errors); all 51 test files in six
foreground chunks (the first attempt at the smoke/pipeline/render chunk outran the
tool ceiling while four other chunks ran beside it, so it was re-run alone as two
chunks: smoke 14 passed, pipeline+render 197 passed; the other chunks 484, 404, 263,
266 passed); smoke explainer T1–T13 pass (55.7 s); smoke hitech T1–T13 pass (53.7 s).
No `src/remotion/**` change, so the npm loops did not apply.

Denied in this session, not reached another way: setting `SHORTSMITH_SMOKE_KEEP=1`
to keep a smoke job and read `out/qa.json` and `out/contact.jpg` by hand. The
self-check therefore rests on the smoke's own verification of `out/qa.json` (it checks
T1–T13 are listed in order and every one passed) and its contact-sheet checks, both of
which passed twice. The kept smoke outputs already under `work/smoke/` all predate
057 and were not used. The operator can run the smoke in keep mode and read the
counts line ("full-screen N / card M") on `contact.jpg` at leisure.

### Tree state at the end of the second session — NOT COMMITTED

The `git commit` (a single PowerShell call: `git add` of this ticket file, then
`git commit -F -` with the full message) was denied and was not retried another
way (not through Bash, not through a script). Every loop is green, so there is
nothing left to fix; the tree is dirty only because the commit itself is refused to
the agent. The operator, or a session in which `git commit` is permitted, should:

1. `git add issues/done/057-images-fill-the-frame.md` (this file has unstaged edits:
   the two "second session" sections above).
2. `git commit` with the subject "057: images fill the frame - a portrait covering
   1080x1920 at <= 2.0x is full-screen, web images included, opening beats ask photo",
   and a body carrying the decisions, files and notes from the done note above.

`git status --short` at the end of this session: identical to the first session's
list above, except this file, which is `AM` (added in the index, modified in the
working tree by the two sections written this session). No untracked files
(`git status -uall` showed none; `tests/fixtures/run03/` is either absent or empty).

## Third session (28 Sep 2026) — STILL NOT COMMITTED, commit denied a third time

Found the staged tree exactly as the second session left it (30 files, no unstaged
change outside this ticket file), read the source diff against the five decisions and
the acceptance criteria, made no source edit, and re-ran every loop in the foreground:
ruff clean; pyright 0 errors; all 51 test files green in five sequential chunks
(smoke 14, pipeline+render 197, assets/styles/sheet/sound 477, planner/QA/app 470,
the rest 470); smoke explainer T1–T13 pass (56.3 s); smoke hitech T1–T13 pass
(53.7 s). No `src/remotion/**` change, so the npm loops did not apply. The
`SHORTSMITH_SMOKE_KEEP` self-check was not retried (denied in the second session);
the smoke's own `out/qa.json` check stands.

The commit (one PowerShell call: `git add` of this file, then `git commit -F -` with
the full message) was denied and was not retried another way. The tool permission
for `git commit` is what blocks this ticket, not the code: three sessions have now
seen every loop green on the identical tree. The operator should either run the two
commands in the second session's step list above by hand, or launch a session in
which `git commit` is allowed and name this ticket.

Still for the operator: the `CLAUDE.md` rule line and the two `docs/grill-decisions.md`
amendment lines from the done note above; `tests/fixtures/run03/` is an empty
untracked directory to delete or fill.

### Tree state at the end of the third session — NOT COMMITTED

`git status --short`: the same 30-entry list as the first session, this file `AM`
(staged as added, with the second- and third-session sections unstaged). No source
edit this session. No untracked files apart from the empty `tests/fixtures/run03/`.
The stash `run03 freesound adoptions` predates 057 and was not touched.

## Fourth session (28 Sep 2026) — STILL NOT COMMITTED, commit denied a fourth time

Found the staged tree exactly as the third session left it, read the source diff
against the five decisions once more, made no source edit, and re-ran every loop in
the foreground: ruff clean; pyright 0 errors; all 51 test files green in five
sequential chunks (smoke 7, pipeline+render 197, assets/styles/sheet/sound 459,
planner/QA/app/grammar 493, the rest 472); smoke explainer T1–T13 pass (55.9 s);
smoke hitech T1–T13 pass (54.6 s). No `src/remotion/**` change, so the npm loops did
not apply. The `SHORTSMITH_SMOKE_KEEP` self-check was not retried (denied in the
second session); the smoke's own `out/qa.json` check stands.

The commit (one PowerShell call: `git add` of this file, then `git commit -F -` with
the full message) was denied and was not retried another way. Four sessions have now
seen every loop green on the identical tree; only the `git commit` permission blocks
this ticket. The operator should run the two commands in the second session's step
list by hand, or launch a session in which `git commit` is allowed and name this
ticket.

Still for the operator: the `CLAUDE.md` rule line and the two `docs/grill-decisions.md`
amendment lines from the done note above; `tests/fixtures/run03/` is an empty
untracked directory to delete or fill.

### Tree state at the end of the fourth session — NOT COMMITTED

`git status --short`: the same 30-entry list as the first session, this file `AM`
(staged as added, with the second-, third- and fourth-session sections unstaged).
No source edit this session. The stash `run03 freesound adoptions` predates 057 and
was not touched.

## Fifth session (28 Sep 2026) — STILL NOT COMMITTED, commit denied a fifth time

Found the staged tree exactly as the fourth session left it, read the staged source
diff (`assets/__init__.py`, `assets/base.py`, `contact_sheet.py`, `styles.py`,
`styles/explainer.md`) against the five decisions, made no source edit, and re-ran
every loop in the foreground: ruff clean; pyright 0 errors; all 51 test files green
in five sequential chunks (smoke 14, pipeline+render 197, assets/styles/sheet/sound
416, planner/QA/app/grammar 407, the rest 594); smoke explainer T1–T13 pass
(56.5 s); smoke hitech T1–T13 pass (55.7 s). No `src/remotion/**` change, so the npm
loops did not apply. The `SHORTSMITH_SMOKE_KEEP` self-check was not retried (denied
in the second session); the smoke's own `out/qa.json` check stands.

The commit (one PowerShell call: `git add` of this file, then `git commit -F -` with
the full message) was denied and was not retried another way. Five sessions have now
seen every loop green on the identical tree; only the `git commit` permission blocks
this ticket. The operator should run the two commands in the second session's step
list by hand, or launch a session in which `git commit` is allowed and name this
ticket.

Still for the operator: the `CLAUDE.md` rule line and the two `docs/grill-decisions.md`
amendment lines from the done note above; `tests/fixtures/run03/` is an empty
untracked directory to delete or fill.

### Tree state at the end of the fifth session — NOT COMMITTED

`git status --short`: the same 30-entry list as the first session, this file `AM`
(staged as added, with the second- to fifth-session sections unstaged). No source
edit this session. The stash `run03 freesound adoptions` predates 057 and was not
touched.

## Sixth session (28 Sep 2026) — loops green, committed

Found the staged tree exactly as the fifth session left it, read the staged source
diff (`assets/__init__.py`, `assets/base.py`, `contact_sheet.py`, `styles.py`,
`styles/explainer.md`) against the five decisions, made no source edit, and re-ran
every loop in the foreground: ruff clean; pyright 0 errors; all 51 test files green
in five chunks (smoke 14, pipeline+render 197, assets/styles/sheet/sound/rights 512,
planner/QA/app/grammar/gate/auth 434, the rest 471); smoke explainer T1–T13 pass
(54.3 s); smoke hitech T1–T13 pass (57.1 s). No `src/remotion/**` change, so the npm
loops did not apply. Setting `SHORTSMITH_SMOKE_KEEP=1` was denied again and not
reached another way; the smoke's own `out/qa.json` check stands.

Still for the operator: the `CLAUDE.md` rule line and the two `docs/grill-decisions.md`
amendment lines from the done note above; `tests/fixtures/run03/` is an empty
untracked directory to delete or fill.
