# 093 — Pick a different bed for the reel on the job page, from the approved beds that fit, with the same audio-only remix

## Type

AFK — no network, no keys, no new packages. No `src/remotion` change.

## Parent PRD

`issues/prd.md`

## Why

Operator, 30 Sep 2026: "next to the slider, let me pick a different bed for the reel from
the approved library (the few that fit the plan's mood, plus the facts default), with the
same quick audio-only remix." The slider fixes a bed's level. This fixes a bed that is the
wrong music.

## What to build

- **The choices.** Beside the slider (090): a short list of approved beds. The list holds
  the beds matching any mood the job's sound story plans (mood + flavour matches first,
  then mood only), plus every `facts_default` bed (087). The bed now playing is marked.
  Each row has a small player and shows the bed's title, source and mood/flavour. Beds
  the operator has never approved are not offered (088's "heard" mark), and no network
  search runs.
- **One bed for the reel.** Picking one plays it under the whole reel. If the story had
  bed changes (076), the page says the pick replaces them. Swells, drops and ducking
  follow the story as before, on the new bed.
- **The same remix as the slider.** The pick is levelled to the style's starting level (as
  090 defines it) plus the reel's current slider offset, then the bed stem, duck, premix, master, and remux with the
  picture copied. The same atomic replace, T4 gate, swept-job rule and ear-wins note as
  090 apply.
- **Rights.** The rights log row for the old bed is replaced by the new bed's row (source
  URL, licence, attribution), and the description's attribution lines follow if the
  new bed needs one. A CC BY bed without its attribution must not ship.
- **Recorded.** `job.json` gets `bed_pick`: entry id and time. The job log gets one line.
  091's remembered level is untouched by a pick; only the slider sets it.

## Acceptance criteria

- [x] App test with a fake library: the list holds the planned mood's beds and the
      `facts_default` bed, with no unapproved and no off-mood beds. The playing bed is
      marked.
- [x] Picking a bed delivers a file whose `balance.json` names the new bed at the target
      starting level (plus offset). The picture stream is byte-identical and no Remotion call is
      made.
- [x] The rights log and the attribution lines name the new bed, not the old one (a CC BY
      case is tested).
- [x] A 076 two-bed story becomes one bed, with the page notice.
- [x] Failure keeps the old file. A swept job shows the list disabled.
- [x] Ruff, pyright and every test file are green in foreground chunks. The smoke passes
      T1–T13.

## Done (afk, 30 Sep 2026)

- `sound/pick.py`. `fitting_beds` lists the approved beds (`approved_beds`: the tracked
  catalogue, never `fetched/`). The order is every segment's mood + flavour matches (a
  segment with no flavour matches on its whole mood), then mood alone, then every
  `facts_default` bed. Each bed appears once. The playing bed comes from `balance.json`'s
  new `beds` field, or from the rights log's music rows for a job mixed before 093.
- Decision: a CC BY bed with no `author` is not offered, and a pick of it is refused.
  Its credits line would have no one to attribute. `credit` alone does not count,
  because `rights.credit_line` does not print it.
- `sound.repick` renders the new bed alone for the whole runtime, with the story's
  envelope, at the style's starting level into `scratch/start/`, then applies the reel's
  slider offset. It shares `_from_start` with `relevel` (090's one-gain step). The old
  bed's dip is not carried over. The balance is measured as `heard`: it is never repaired
  and ear notes only.
- `level.deliver` is 090's scratch → master → remux → T4 → atomic swap, now shared by the
  slider and the pick. A mix that brings its own `start/` replaces the old one and removes
  the old `music.N.wav` segment stems. A later slider remix therefore moves the picked bed
  from its own starting level (tested).
- Rights: `rights.replace_music` swaps the music rows in `work/audio_rights.json`,
  `out/rights.json` and `out/credits.md`. The SFX and picture rows are kept. The
  description reads `credits.md`, so its attribution lines follow.
- Recorded: `job.json` `bed_pick` (entry id, time) and the ear notes on `music_level` (the
  offset is unchanged). `job.log` gets one `bed pick:` line. `music_level.json` (091) is
  not written.
- Page: a "Music bed" block under the slider. Each row has a radio button, a player
  (`GET /audio/beds/<id>`, approved beds only), the title, source, author, licence and
  mood/flavour/role, and "now playing" on the current bed. `REPLACES_CHANGE` shows when
  the story plans a 076 change. The block is disabled with a reason for a swept job or a
  job with no bed. `POST /jobs/<id>/bed-pick` returns 409 for those, 422 for a bed not on
  the list, and 500 with the error when delivery fails (the old short is kept).
- Tests: `tests/test_bed_pick.py` (9 tests).

## Blocked by

- `issues/090-music-level-slider-audio-only-remix.md` (the remix path and the page
  block).
- `issues/088-ear-approved-beds-pass-the-ceiling.md` (the "heard" mark on catalogue
  entries).

## User stories addressed

- Operator, 30 Sep 2026: "let me pick a different bed for the reel from the approved
  library (the few that fit the plan's mood, plus the facts default)".
