# Style specs

One markdown file per style: YAML front matter between `---` fences, then the five prose sections. `shortsmith.styles.load_all` validates every file at app startup; a broken spec stops the app with the spec name and the problem (grill decisions 1.2, 1.4).

Front matter must carry the eight key groups plus six more keys:

| key | who reads it |
| --- | --- |
| `version` | `meta.json` (10.4, ticket 035): recorded on every job the spec judged, so a short's provenance names the spec it was made under; bump it by hand whenever a number or a prose section changes. Quote it (`"1"`) so YAML keeps it a string |
| `aliases` | the resolver (1.1): words in the style line that pick this spec |
| `beats` | grammar validator (3.1, 3.4): beat lengths and the opening's shape (`opening_beats_min`, `opening_beats_max`, `opening_max_s`; 055) |
| `presenter` | grammar validator (3.2); `opening_mode` is the opening beats' mode (055) |
| `cut` | grammar validator (3.4 as amended by 055): `max_pause_s`, the longest pause between two kept words; code tightens longer ones and never touches a word |
| `broll` | grammar validator, asset step, renderer (4.1, 4.3, 9.2, 9.4); `enter_transitions` is the style's subset of the global vocabulary and `transitions` carries every row of its numbers (fade, whip, zoom, spring, wipe, flash; `cut` has none), enabled or not; `flash_max_per_60s` caps the flash (060); `text_pops_max_per_60s` caps the text pops (061; 0 turns them off) and `motion.text_pop` carries their numbers (overshoot length, hold, per-beat cap, tilt, type size, the pop yellow); `bubbles_max_per_60s` caps the speech and thought bubbles (063; 0 turns them off) and `motion.bubble` carries their numbers (overshoot length, hold, per-beat cap, word cap, the dialogue gap's bounds, type size and its floor, body width, fill, ink); `highlights_max_per_60s` caps the article highlights (078; 0 turns them off) and `motion.highlight` carries the marker's numbers (colour - the palette accent -, opacity, padding round a text line, and `push_to`, how far the owner's screenshot card pushes in toward the lines); `clip_max_fraction` is the share of the runtime `clip` beats (full-screen muted stock footage, 058; 0 turns them off) may take and `motion.clip` carries their numbers (the push `scale_from` -> `scale_to`, the playback `speed`); `motion.map.label_step_px` and `label_steps_max` are how far and how many times a map label that would cover another label or dot steps up or down after flipping sides (072); `motion.map.min_span_deg` is the least span in degrees any map shows, `highlight` fills the named country, `names_max` / `name_font_px` / `name_color` name the countries in view, `circle_color` / `circle_px` / `circle_size` (fraction of the band width) / `circle_draw_s` draw the target circle round the named place and `tag_font_px` / `tag_tilt_deg` / `tag_slide_s` / `tag_fill` / `tag_ink` its angled tag (104; the circle and tag times and size are ePTZVwipoAM's `red_circle_india` and `indus_war_tag` cards) |
| `captions` | pager and renderer (6.1, 6.2, 6.3) |
| `sound` | sound director and gate (7.1, 7.3); `default_bed_query` is the plain-words last rung of the runtime bed search (7.2, 054); `bed_query_anchor` rides on every rung and `speech_band_margin_max_db` fails a bed a phone speaker cannot play (069), and screens only beds nobody has heard: an ear-approved bed over it plays with a note (088); `bed_changes_max` caps the bed changes a short may make on a story-part boundary, and `bed_crossfade_s` / `bed_silence_s` / `bed_cut_fade_s` are how long a crossfade, a drop to silence and a hard cut's fade take (076); `facts_default_first` (required) puts the approved `facts_default` bed before a same-mood bed of another flavour on a flavour or mood miss (087) |
| `finale` | grammar validator and gate |
| `status` | `shipped` or `draft` (1.4): only shipped styles are offered and used; a draft's alias resolves to `explainer` with a notice |
| `requires_components` | cross-checked against the renderer registry; a shipped spec may not require a missing one (9.2) |
| `budget` | ledger caps (5.5, 5.6) |
| `pip` | PIP geometry (3.3); the loader asserts `pip.top + pip.diameter <= captions.anchor_y - captions.max_lines x line height` (6.3) |
| `palette` | renderer gradient and accent |

Two optional rows (059): `broll.motion.split.layout` is `side` (the 5.2 news card, the default when absent) or `stacked` (two pictures top and bottom); `broll.title_strip` (`words_max`, `top_y`, `height_px`, `size_px`, `min_size_px`, `fill`, `ink`, `duration_s`) draws the plan's `title_strip` at the top of the frame for the whole short, the finale aside - a style without the row has no strip and its plans carry none.

## Recipe styles (ticket 059)

Three shipped styles built from the reference inventory (036: `docs/reference/inventory/<id>.json`, `GAPS.md`; every figure ESTIMATED, model-observed on sampled frames). In all three the captions, PIP geometry, 055 opening, finale, cut and bed level (-14 dB, 056) are the explainer's, number for number; `flash` is in `enter_transitions` (cap 5 a minute) and whooshes are allowed under 060's rule (`sound.whoosh: {max_per_60s: 6, min_gap_s: 3.0, max_len_s: 0.8, on: [flash, pop]}`; refs: whooshes in all 12, median about 3.5 a minute).

| style | references | number | from |
| --- | --- | --- | --- |
| `footage` | `S5j-2CWYYwM`, `ATkSnL_CdLg`, `VSJzviqMO7k`, `cKxkAjYHXbk` | `beats.target_mean_s` 2.2 (mean 1.8-2.8, `max_s` 5.0) | `counts.shots_per_10s` 4.0, 5.2, 4.8, 4.0 -> a shot every 1.9-2.5 s |
| | | `clip_max_fraction` 0.75 | `moving_footage` / `full_footage` share of `shots`: 49-82 % |
| | | `presenter.full_max_fraction` 0.25, entered with `flash` | explainer's cap; the Dhruv turn back to the presenter (`S5j-2CWYYwM` 17 s colour flash) |
| | | `text_pops_max_per_60s` 6, `stickers_max_per_60s` 3, bubbles 0 | stamps or pops on numbers about 1 per 10 s; a sticker at most every ~20 s |
| | | `highlights_max_per_60s` 2 (078) | `ATkSnL_CdLg` 14 s sweeps a marker over a news snippet; the only recipe whose references do (vishva and fastfacts keep 0) |
| | | `unique_assets_*_per_60s` 14-27 | explainer's 12-24 scaled by 2.5 / 2.2 |
| | | SFX about 1.2 per 10 s (`cues_max_per_60s` 20 is the cap) | `counts.sfx_per_10s` 1.2, 1.3, 1.1, 2.3 |
| `vishva` | `FbaBcWgMIEY`, `ePTZVwipoAM`, `nBihHUlYOQk` (Tier B, the operator's own) | `beats.target_mean_s` 2.6 (mean 2.1-3.2) | `counts.shots_per_10s` 3.5, 3.2, 4.9 -> a shot every 2.0-3.1 s |
| | | `clip_max_fraction` 0.15 | `moving_footage` share: 7 %, 0 %, 16 % |
| | | overlays 15 a minute: `text_pops_max_per_60s` 9, `bubbles_max_per_60s` 4, `stickers_max_per_60s` 2 | `counts.effects_per_10s` 1.5, 2.3, 5.7 -> about 2.5 per 10 s |
| | | `motion.split.layout: stacked` | `split` layout share 18 %, 24 %, 39 % of the runtime |
| | | `unique_assets_*_per_60s` 12-23 | explainer's scaled by 2.5 / 2.6 |
| | | SFX about 1.3 per 10 s | `counts.sfx_per_10s` 1.5, 0.8, 1.5 |
| `fastfacts` | `Q2pquJ2FlzA`, `zXK42RMPKUY` | `beats.min_s` 0.5, `target_mean_s` 1.2 (mean 0.9-1.5, `max_s` 3.0, set pieces 4.0, gap 1.0) | `counts.shots_per_10s` 9.3, 7.0 -> a shot every 1.1-1.4 s |
| | | `clip_max_fraction` 0.7 | `moving_footage` share 92 %, 37 % |
| | | `title_strip` (5 words, y 262-366) | `Q2pquJ2FlzA` 0 s `header_banner`, also `VSJzviqMO7k` |
| | | `text_pops_max_per_60s` 10 | a pop on every number |
| | | `unique_assets_*_per_60s` 25-50, `reuse_max` 2, `rescued_max_per_60s` 8, budget doubled | explainer's scaled by 2.5 / 1.2 (056's reuse cap kept) |
| | | `presenter.pip_max_run` 12, `off_max_run` 6 | explainer's runs in seconds at the faster pace |
| | | SFX about 1.2 per 10 s (`cues_max_per_60s` 24 is the cap) | `counts.sfx_per_10s` 1.1, 1.2 |

The prose sections are exactly, in order: **Beat grammar**, **B-roll**, **Captions**, **Sound**, **Finale**. The renderer and QA read only the numbers; the planner reads numbers and prose.

Rules: numbers are contracts (a sweep, a tight PIP crop, a collision fails QC). Add a style by adding a file; never hard-code a style rule in code. Quote `"off"` in YAML (a bare `off` is a boolean). Every `sound.forbidden` list bans sweeps and risers; cues are the closed palette tick, whoosh, bass, drum, thump and ding, each with its row or length in `sound` (070), and never a ring, bell or chime.
