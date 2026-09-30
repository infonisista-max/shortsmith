# 110b — Variety numbers in every style, as soft grammar rules the editor repairs

## Type

AFK. The second of three parts of the old 110 (split 1 Oct 2026).

## Parent PRD

`issues/prd.md`

## What to build

- **Front matter in every style**, validated by `styles.load_all`:
  - `clip_share_target: [low, high]` (vishva's value is 110c's; the others take a range
    from their own references);
  - at most N stamps per 60 s (run05 had 12 identical yellow stamps);
  - a minimum share of non-cut enters (run05: cut 17 of 26);
  - no same transition three times running.
- **Soft rules in `grammar.py`** (094's pattern: soft, keep_soft, the editor's repair,
  never a failure):
  - each of the numbers above;
  - set pieces and carry-ons count toward `reuse_max` (`vishva.md:105` excluded them;
    run05 showed `img_saud_young` on b12/b13/b16);
  - a number beat may take a counter, chart, calendar or a new picture instead of
    reusing the previous asset (`vishva.md:212` forced the reuse).
- **Clip share below target**: when sourcing finds no usable clip, the job delivers with
  a logged reason; never a failure, never a forced bad clip.

## Acceptance criteria

- [ ] Each soft rule is tested: a violation, the editor's repair, and no job failure.
- [ ] Below-target clip share with no usable clips delivers with a logged reason (test).
- [ ] `styles.load_all` validates the new keys; the full chunked suite and smoke are green.

## Blocked by

110a (shares `picture_v20.md` wording on the rules).
