# 110 — The planner edits like a creative human editor (the standing rule for every job)

## Type

AFK. The capstone: built last so the vocabulary it lists exists.

## Parent PRD

`issues/prd.md`

## Why (the causes of "every vishva reel looks the same")

1. Places, eras and events could never be clips (fixed by 099).
2. Vishva is stills by spec: `vishva.md:210` says "full-screen stills are the base", and
   `clip_max_fraction: 0.15` (`:95`) was measured only from the 3 Vishva Gyan shorts.
3. Worked examples are same-style only (`reference/examples.py:102`). A vishva job only
   ever sees `FbaBcWgMIEY` and `ePTZVwipoAM`, both 97-100 % stills.
4. The prompt offers clips for a narrow case: "cheese", "the sun" and "a busy market"
   (`picture_v19.md:85-87`), and the opening may be a clip only for a concept (`:55-56`).
5. Motion is one Ken Burns for all (fixed by 102), and the card is one pop-up for all
   (fixed by 103).
6. Repeats happen by rule:
   - number beats must reuse the previous asset (`vishva.md:212`);
   - set pieces and carry-ons do not count toward `reuse_max` (`:105`);
   - so run05 showed `img_saud_young` on b12/b13/b16 and `img_saud_old` on b14/b15/b16.
7. Transitions and overlays are narrow: `wipe` is missing from `vishva.md:88` although it
   is built; cut was used 17 of 26 times; there were 12 identical yellow stamps, and there
   is no stamp cap.

## What to build

- **The creative-editor section in the picture prompt** (`picture_v20.md`, shared with 099):
  - For each script the planner reads the story and chooses from the **full vocabulary**:
    - clips for places, eras, objects and events;
    - every picture treatment of 103 and every move of 102;
    - every transition;
    - text treatments: stamp, text_pop, banner, bubble, lower_third, calendar;
    - maps with a highlight or circle, counters and charts, overlays;
    - pacing changes: a burst of short beats against a held beat.
  - It plans as a human editor would: what this line needs, what the previous two beats
    did, and what would surprise without distracting.
  - It **varies**, so no two reels feel like one template, and says in each beat's `why`
    what it chose and why.
- **Operator taste (30 Sep 2026), written into the prompt and the style front matter:**
  - **Moving footage is a range, not a rule:** `clip_share_target: [0.20, 0.40]` for
    vishva; every style gets its own range from its references.
  - The planner decides per script how much really fits.
  - **The low end is a target, never a gate.** Short of good clips → stills, a logged
    reason, delivered. Never fail a job; never force a bad clip to hit a number.
  - The same picture treatment never runs back to back; the planner picks per image.
- **Variety numbers in front matter, as soft rules in `grammar.py`** (094: soft, keep_soft,
  the editor's repair, never a failure):
  - at most N stamps per 60 s;
  - a minimum share of non-cut enters;
  - no same transition three times running;
  - set pieces and carry-ons count toward `reuse_max`;
  - a number beat may take a counter, chart, calendar or a new picture instead of reusing.
- **vishva.md re-derived:**
  - `wipe` goes into the transitions;
  - "stills are the base" is replaced by the range;
  - the numbers are checked against the reference frames and the facts references'
    moving-footage data (GAPS.md), not taste.
  - Every other style gets the same section and its own numbers.
- **Worked examples across styles:** when fewer than 2 own-style examples show footage,
  `examples.select` adds a Tier A card from another style on a near topic, labelled as a
  vocabulary example, not a style example.
- **A variety line in the job's inventory** (074's table): treatments used, clip share,
  transitions used, repeats. Red rows are logged only; they are not a gate.
- **Where it lives** (the answer for the operator): the prompt section; `styles/*.md` front
  matter + the "creative editor" prose; the soft rules in `grammar.py`;
  `reference/examples.py`. `styles/README.md` names them.

## Acceptance criteria

- [ ] A new prompt version with the creative-editor section; the fake planner's plan and
      `fixture.smoke_specs` updated so the smoke still judges it.
- [ ] Each style's front matter carries `clip_share_target`, the stamp cap, the non-cut
      share and the treatment/transition run limits; `styles.load_all` validates them.
- [ ] The soft rules are tested: each is a soft violation, repaired by the editor, and
      never fails a job.
- [ ] A clip share below target with no usable clips delivers with a logged reason (test).
- [ ] The `examples.select` cross-style fill is tested.
- [ ] The variety line is present on the smoke job's inventory.
- [ ] The full chunked suite + smoke green.

## Blocked by

099, 102, 103, 104, 107, 108, 109 (it lists their vocabulary).

## User stories addressed

Operator, 30 Sep 2026 (run05 King Saud, phone 6.5/10), finding 3: "the planner works like
a creative human editor. For each script it chooses from the full vocabulary my reference
URLs taught ... so no two reels feel like one template ... Build it into the standing
rules."
