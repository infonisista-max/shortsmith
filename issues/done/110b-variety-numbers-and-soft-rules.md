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

- [x] Each soft rule is tested: a violation, the editor's repair, and no job failure.
- [x] Below-target clip share with no usable clips delivers with a logged reason (test).
- [x] `styles.load_all` validates the new keys; the full chunked suite and smoke are green.

## Blocked by

110a (shares `picture_v20.md` wording on the rules).

## Done note (1 Oct 2026)

- Front matter (`broll`, validated by `styles.load_all`; `src/shortsmith/styles.py:270`,
  the range check `_share_range` `:322`): `clip_share_target: [low, high]` replaces
  `clip_max_fraction` (one number, not two: the top is the ceiling, the low end a target),
  `stamps_max_per_60s`, `non_cut_min_share`, `enter_run_max`; all four required.

  | style | clip_share_target | stamps / 60 s | non-cut share | enter run |
  | --- | --- | --- | --- | --- |
  | explainer (`styles/explainer.md:134`) | [0.05, 0.35] | 6 | 0.7 | 2 |
  | footage (`footage.md:132`) | [0.35, 0.75] | 4 | 0.15 | 2 |
  | fastfacts (`fastfacts.md:132`) | [0.35, 0.70] | 4 | 0.7 | 2 |
  | vishva (`vishva.md:133`) | [0.20, 0.40] (operator; 110c re-checks) | 4 | 0.7 | 2 |
  | animated / educational / hitech (drafts) | explainer's | 6 | 0.7 | 2 |

  Where each came from (the comments beside the keys say the same):
  - clip share: low = the lowest moving-footage share among the style's own inventory cards
    (`docs/reference/inventory/*.json`, `shots`), rounded down to 0.05 - footage cKxkAjYHXbk
    35 % (cards 35-92 %), fastfacts zXK42RMPKUY 38 % (38, 92 %), explainer the unassigned
    Tier A cards' lowest, QjwDTLPLJ6c 8 % (8-40 %; the approved shorts are 0 %); high =
    058's derived `clip_max_fraction` (0.35 / 0.75 / 0.70). Vishva: the operator's range.
  - stamps: explainer = the approved shorts' beat tables (`work/beat-tables.md`; Dyson 6
    stamps in 57.5 s, NKB 4 in 60 s, docs/reference/README.md); footage, fastfacts and
    vishva cards show no stamp (text pops carry the words; fastfacts 1 at most), so the
    approved shorts' lower count, NKB's 4 (run05 had 12).
  - non-cut share: explainer = the beat tables (NKB 22 of 26 enters not a cut, 0.85;
    Dyson 16 of 22, 0.73) -> 0.7; footage = its cards' median (0, 5, 23, 38 % -> 0.15);
    vishva and fastfacts cards register no non-cut enter at all at 5 fps (a 0.2-0.35 s
    transition spans one frame), so the approved shorts' floor, 0.7 (run05: cut 17 of 26).
  - enter run: the operator's rule in 110 ("no same transition three times running"); the
    old engine's own runs (NKB 11 whips, Dyson 4) are the monotony 110 names.
- Grammar soft rules (094: soft, kept with `keep_soft`, never a failure):
  `grammar.variety` (`src/shortsmith/grammar.py:1781`, called at `:262`): each stamp past
  `stamps_cap` (`:1773`) flagged on its beat; too few non-cut enters flags the cuts that
  break a run of cuts first; the beat that makes a run longer than `enter_run_max`.
  `grammar.reuse` (`:1745`): carry-on number / quote beats and a set piece's own asset now
  count toward `reuse_max`; the showings past the cap are flagged (never the first;
  carry-ons first, set pieces last). Clip share: the top of the range is the old soft
  ceiling (`_clips`); under the low end `clip_share_note` (`:852`) is a warning only.
- Editor repairs: a stamp problem -> `drop_event` (the existing layer word); a variety
  enter problem (`VARY_ENTER`, grammar `:1778`) -> the first `enter:<name>` swap
  (`_enter_swaps`, `src/shortsmith/editor/__init__.py:256`; never its own or a neighbour's;
  uncapped enters first, `CAPPED_ENTERS` `:74`, a cut last; `repairs.set_enter`,
  `src/shortsmith/editor/repairs.py:305`; offered when the pipeline passes the style's
  enters for such a beat, `src/shortsmith/pipeline.py:754`); a reuse problem ->
  `new_picture` (`editor/__init__.py:215`, `:298`; `repairs.new_picture` `:324`: the beat's
  asset cleared, searched afresh, a carry-on subject becomes `concept` so a number beat
  takes a new picture instead of reusing), else `replace_visual` on a set piece.
- Clip share below target at sourcing: `_clip_share_note`
  (`src/shortsmith/assets/__init__.py:1675`, logged at `:1657`) names the clip beats that
  found no usable clip and took a still; the manifest is returned, the job delivers.
- Prompt: picture_v20.md's creative-editor line points at `broll.clip_share_target`
  (`:40-42`), a variety line (`:47-50`), the clip ceiling (`:174-175`), the concept line
  (`:255`), the number beat may take a counter, chart, calendar or new picture (and a
  carry-on counts), reuse counts carry-ons and set pieces; snapshots re-recorded. Style
  prose: `clip_max_fraction` -> `clip_share_target`, the number-beat sentence, a variety
  sentence on the transitions bullet, the reuse_max comment; styles/README.md.
  Vishva's `wipe` and "stills are the base" prose are left to 110c.
- Fake planner: b07 fades in and the finale calls back a2 (a1 is on b01 and b06), the
  light flare falls back to a spring (`src/shortsmith/planner/fake.py`), so the fake plan
  passes every style's fixture rules; recorded CLI / API replies follow.
- Tests: `tests/test_variety.py` (21), `tests/test_assets_clips.py` (2: no usable clip
  delivers with the logged reason; inside the target logs nothing), `tests/test_pipeline.py`
  (1: a plan of nothing but cuts is repaired and delivered); test_grammar's fixture lifts
  the variety numbers (`no_variety`) since its base plan stamps every beat for density.

