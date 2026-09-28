# 066 — Density (3.1) counts each change at its own time: a pop and a stamp really do split a beat

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Run04 (job `20260928-140620-f774e1`) was rejected on 3.1 three times: both calls of
run 2, then the first call of run 3. In run 3's first reply, b20 carried a
`lower_third` and a text pop in a 3.82 s beat, and it was still flagged for "one
landed event". The job only got through when run 3's retry split the beats.

The cause is that the grammar and the prompt disagree:

- `grammar._density` treats "landed" as yes/no:
  `landed = b.event.kind != "none" or pops_in(b)`, and then `gap = length / 2`. A beat
  with a pop, a stamp, a sticker and a bubble counts as one event, so adding changes
  to a beat never helps. Only splitting it does.
- `picture_v14.md` (text pops) says "A text pop is not the beat's landed event, so the
  beat may still carry a `stamp` or `lower_third`". The model takes that as "a stamp
  adds a change". The rejection text ("one landed event in a 4.04 s beat") pushes it
  the same way.

Operator decision (QA review, 28 Sep 2026): the grammar is wrong. 3.1 measures what
really changes on screen and when:

- **Change times in a beat:** the beat start; every text pop, bubble and sticker at
  its resolved `at_s`, the word time `_text_pops` / `_bubbles` / `_stickers` already
  compute; the beat's `stamp`, `lower_third` or `counter` event at mid-beat (today's
  reading, kept); and the beat end.
- **The rule:** the largest gap between consecutive change times must be at most
  `beats.density_gap_max_s`. Set pieces and beats with overlays stay exempt, as today.
- **Order:** `_density` must run after the pop, bubble and sticker passes, because it
  needs their times. Today it runs before them.
- **Rejection text:** name the gap, e.g. `b14 (3.1): nothing changes on screen from
  24.10 s to 26.00 s (1.9 s), over beats.density_gap_max_s 1.5 s; add a pop on a word
  in that span or split the beat`.
- **Prompt:** `picture_v15.md` (a copy of v14; `PROMPT_VERSION` bumped) says the same
  in the density line and the text-pop paragraph. A pop, bubble or sticker counts at
  its word, and a stamp or lower-third counts at mid-beat.

A note for the operator, not in this ticket's scope: the renderer lands the stamp and
the lower-third at the start of the beat (`stamp_land_s`, `lower_third.duration_s`),
not in the middle. So the mid-beat reading is kinder than what the viewer sees.
Whether to tighten it is a separate call, to be checked against the reference beat
tables.

## Acceptance criteria

- [ ] A 4.0 s beat with a stamp and no pop is rejected (the mid-beat event leaves 2.0
      s on each side). With one pop at +3.0 s it is still rejected, and the message
      names the 0.00–2.00 s span. With pops at +1.0 s and +3.0 s it passes (four 1.0 s
      gaps). Each case is tested with the style's own number, where 1.5 s is the vishva
      value.
- [ ] A 3.0 s beat with only a pop at +1.5 s passes. The same beat with the pop at
      +0.2 s is rejected, and the message names the span from the pop to the beat end.
- [ ] Bubbles and stickers count at their `at_s` in the same way. Set pieces and
      overlay beats stay unmeasured.
- [ ] Beats with no pops, bubbles or stickers are judged exactly as today: a regression
      test over the fake plans and `fixture.smoke_specs`.
- [ ] Run04's run-3 first reply (`work/planner/reply_picture.json` of the job, copied
      into a test fixture as JSON only, no media) produces 3.1 messages that name the
      span of each flagged beat.
- [ ] `picture_v15.md` is shipped and `PROMPT_VERSION` is v15. A test asserts the
      text-pop paragraph no longer implies that a stamp alone fixes density.
- [ ] The grammar module docstring's "Two readings" paragraph describes the new
      reading.
- [ ] Smoke explainer, hitech, footage, vishva and fastfacts pass T1–T13 (T8
      re-validates with the new rule). Ruff, pyright and every test file are green in
      foreground chunks.
- [ ] Done note: the amendment line for 3.1 for the operator to paste, and what to
      check on run05: `job.log` shows no 3.1 rejection on a beat that carries a
      well-placed pop.

## Done note (29 Sep 2026, AFK session)

All boxes above are met:

- `grammar.change_times(beat)` lists the times: the start, each pop, bubble and
  sticker at its resolved `at_s` (clamped into the beat), the landed event (stamp,
  ring, lower-third) at mid-beat, and the end. `grammar.density` (it was `_density`,
  now public for the tests) now runs after the sticker pass and rejects when the
  largest gap is over `beats.density_gap_max_s`. The message is
  `b05 (3.1): nothing changes on screen from 10.00 s to 12.00 s (2 s), over
  beats.density_gap_max_s 1.5 s; add a pop on a word in that span or split the beat`.
  The times are output seconds, as in the 4.1 pop messages. When two gaps tie, the
  earlier one is named.
- A counter rides an overlay, so its beat stays exempt, the same as before.
- `tests/fixtures/run04/` holds run 3's first reply, parsed to a PicturePlan, and the
  job's transcript (JSON only). Under the new rule the reply is still rejected, and
  each line names its still span. b20's pop (47.90 s) and its lower-third (48.23 s) are
  both in the first half, so 48.23–50.14 s stays still. b02 is now flagged too: its one
  bubble lands at the beat start (1.90 s), which leaves 1.6 s of nothing after it. The
  old rule counted any bubble as a pass.
- Five older tests put a pop, bubble or sticker at +0.4 s on a bare 2.5 s beat and
  expected a pass. They now put the word at +1.0 s (1.0 s + 1.5 s still).
- `picture_v15.md` adds a still-screen line under Beats and rewrites the text-pop
  paragraph ("counts at its word's time, while a `stamp` or `lower_third` counts at
  mid-beat ... Put the pop on a word inside the still span, or split the beat"). The
  bubble and sticker lines say the same. `sound_v15.md` is v14 unchanged.
  `PROMPT_VERSION` is v15, and the v15 snapshots are recorded.
- Checks: ruff and pyright are clean. All 59 test files are green in foreground chunks.
  Smoke passes T1–T13 on explainer, hitech, footage, vishva and fastfacts; each kept
  qa.json was read.

Amendment line for 3.1, for the operator to paste:
> 3.1 (as amended by 066): density measures what changes on screen and when. A beat's
> change times are its start, each text pop, bubble and sticker at its word's time,
> its stamp or lower-third at mid-beat, and its end. The largest gap between them is
> at most `beats.density_gap_max_s`. Set pieces and overlay beats are not measured.

Check on run05: `job.log` shows no 3.1 rejection on a beat that carries a well-placed
pop. Any 3.1 line left should name a span (`from X s to Y s`) that really has nothing
in it.

Still open for the operator (out of scope, as the ticket says): the renderer lands the
stamp and lower-third at the start of the beat, not mid-beat.

## Blocked by

- Nothing. (065's per-run planner folders would have kept run 2's retry reply; they
  are not needed to build this.)

## User stories addressed

- Operator, run04 QA (28 Sep 2026): planning failed twice on 3.1 even though the retry
  added a stamp to the beats that already had a text pop.
