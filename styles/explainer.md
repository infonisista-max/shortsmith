---
status: shipped
aliases: [explainer, explain, explained, explanation, fact, facts, story, news, dhruv]
requires_components: [captions, pip, hook_cards, finale, stamp, lower_third, list, split, wall]
beats:
  min_s: 0.7
  max_s: 6.0
  set_piece_max_s: 8.0
  target_mean_s: 2.5
  mean_min_s: 2.0
  mean_max_s: 3.2
  density_gap_max_s: 1.5
  snap_window_s: 0.15
  cold_open_min_s: 0.7
  cold_open_max_s: 2.0
  hook_cards_min_s: 2.0
  hook_cards_max_s: 4.0
  hook_title_max_words: 8
presenter:
  modes: [full, pip, "off"]
  full_max_fraction: 0.25
  full_never_consecutive: true
  full_reasons: [cold_open, emotional_line, argument_turn]
  pip_max_run: 6
  off_max_run: 3
  hook_modes: [full, "off"]
  finale_mode: "off"
pip:
  left: 60
  top: 960
  diameter: 300
  large_face_diameter: 340
  large_face_ratio: 0.45
  chin_anchor: 0.82
  ring_px: 6
  ring_color: "#FFFFFF"
broll:
  kinds: [photo, card, stamp, lower_third, hook_cards, finale, presenter_full, presenter_pip,
          list, chart, split, wall, map, infographic, pin_drop, route_arrow, label_flyin,
          counter, object_path]
  tier2_kinds: []
  motion:
    photo: {kind: ken_burns, scale_from: 1.10, scale_to: 1.16, alternate: true}
    card: {kind: push, scale_from: 1.45, scale_to: 2.1, border_px: 14, rotate_deg: -1.5,
           ring_color: "#E53935"}
    stamp: {kind: land, duration_s: 0.16, shake: true, palette: yellow_green_red}
    lower_third: {kind: fade, duration_s: 0.35, top_y: 1150, bottom_y: 1240}
    hook_cards: {kind: spring, cards: 3}
    finale: {kind: fade, duration_s: 0.35}
    list: {kind: reveal, items_max: 6, duration_s: 0.35, scale_from: 1.15, scale_to: 1.25,
           dim: 0.45}
    split: {kind: slide, panes: 2, duration_s: 0.30}
    wall: {kind: spring, cells_min: 4, cells_max: 9, duration_s: 0.30, scale_from: 1.2,
           scale_to: 1.3, dim: 0.65}
  enter_transitions: [cut, fade, whip, zoom, spring]
  whip_max_per_3_beats: 1
  unique_assets_min_per_60s: 12
  unique_assets_max_per_60s: 24
  reuse_max: 4
  rescued_max_per_60s: 4
  card_max_bottom_y: 1240
  stamp_max_y_fraction: 0.6
  photo_look: "cinematic documentary photograph, natural light, film grain"
  illustration_look: "vintage editorial illustration, muted archival palette, visible brush texture"
  scene_mood: "grounded documentary mood"
  scene_lighting: "soft natural daylight"
captions:
  font_family: Poppins
  font_weight: 800
  size_px: 74
  line_height: 1.35
  letter_spacing_px: 0.5
  anchor_y: 1460
  max_lines: 2
  max_width_px: 960
  word_gap_px: 22
  unspoken_alpha: 0.86
  active_color: "#FFD60A"
  active_scale: 1.08
  active_scale_s: 0.10
  keyword_fg: "#111"
  keyword_bg: "#FFD60A"
  keyword_pad_px: 14
  keyword_radius_px: 14
  enter_scale_from: 0.94
  enter_s: 0.12
  enter_opacity_s: 0.06
  stroke_px: 2
  drop_px: 3
  glow_px: 18
  words_per_page: [2, 4]
  prefer: 3
  emphasis_max_ratio: 0.25
  gap_break_s: 0.35
sound:
  bed_db_under_voice: -11
  bed_accept_db: [-12, -9]
  speech_band_hz: [250, 4000]
  speech_band_margin_db: 20
  duck_max_db: 4
  swell_max_db: 4
  drop_min_db: -8
  ramp_min_s: 1.5
  fade_in_s: 0.6
  fade_out_s: 1.2
  floor_hits:
    bass: [stamp, reveal, header]
    drum: [money_reveal, finale_word]
    thump: [card_fly_in]
  cues_max_per_60s: 20
  cues_per_beat_max: 1
  cue_db_min: -10
  cue_db_max: -2
  forbidden: [sweep, riser, rumble_crescendo, whoosh]
finale:
  kind: finale_card
  mode: "off"
  min_s: 0.8
  max_s: 1.2
  cta: true
budget:
  judge_max_calls: 40
  search_max_queries: 60
  gen_max_per_short: 8
palette:
  gradient: ["#0B1D3A", "#1F3B73"]
  angle_deg: 160
  accent: "#FFD60A"
---
# Style: explainer
Fact/story explainer for Hindi/Hinglish and English audiences. High information density, presenter-led, B-roll on every beat. The default style and the only shipped one on day 14 (grill decision 1.4). The numbers above are the contract; this prose tells the planner how to use the latitude they leave.

## Beat grammar
- A beat is one contiguous span of the cut voice track with one presenter mode, one visual kind, one asset and at most one landed event; beats tile the runtime with no gaps (3.1). Propose boundaries in seconds; code snaps each to the nearest word end within `snap_window_s`, so never plan a cut mid-word.
- Keep the plan mean between `mean_min_s` and `mean_max_s`; set pieces (list, chart, split, wall, finale) may run to `set_piece_max_s`. Something must change on screen at least every `density_gap_max_s`.
- Hook is two beats of fixed shape (3.4): a `full` cold open with the `cold_open` reason (0.7–2.0 s, may be lifted from anywhere in the recording; say whether the original stays or drops), then `off` hook cards (2.0–4.0 s) with a title of at most `hook_title_max_words` words and three cards from the plan's assets in priority order.
- Presenter modes are `full`, `pip`, `off` (3.2). Every `full` beat carries one reason tag from `full_reasons`; `full` beats are never consecutive and never more than `full_max_fraction` of the runtime. PIP runs up to `pip_max_run` beats are fine (the references ran six); `off` runs up to `off_max_run`.
- PIP framing: whole head plus neck/collar, chin at `chin_anchor` of the window, never a tight face crop (3.3).

## B-roll
- Only kinds in `kinds` may be used; `tier2_kinds` is empty here, so parallax depth and vector-illustration looks are validation errors naming the nearest tier-1 substitute (4.1 as amended by 9.2). Every non-presenter beat has exactly one motion; there is never a static still.
- Label every non-presenter beat with `subject_kind` and a `query` plus a broader `query_fallback` (4.2): `entity` beats get a card or photo from owner references first, then search, then generation as the last resort, plus a lower-third; `concept` beats get a Ken Burns photo and a stamp of the key word; `number` and `quote` beats reuse the previous asset with a stamp and add nothing to the asset count.
- Source order is owner references → web image search → Wikimedia Commons → Openverse → Pexels/Pixabay → generated illustration (5.1); web images are always re-dressed as cards, never shown raw. Generated depictions of a named person or product are illustration-style (`illustration_look`); scenes and unnamed people may be photoreal (`photo_look`).
- Count unique assets, not beats: between `unique_assets_min_per_60s` and `unique_assets_max_per_60s` per minute, each reused at most `reuse_max` times (4.3). Reuse is encouraged for callbacks, payoffs and number beats; a short with no reused asset is a warning.
- The three set pieces carry their own content: a `list` beat gets a `set_piece_title` header and up to `motion.list.items_max` `items`, each with text and optionally an asset; a `split` beat gets a title strip plus exactly `motion.split.panes` items, one per side, each naming an asset and labelled with the words the strip highlights; a `wall` beat gets `motion.wall.cells_min` to `cells_max` items, each naming an asset. Item assets are ids other beats already source — a montage of the plan's pictures, never new ones (4.3).
- Transitions: `enter_transitions` only, at most `whip_max_per_3_beats` whip per three beats and never two whips in a row (9.4). Cards end above `card_max_bottom_y`; stamps stay in the top `stamp_max_y_fraction` of the frame; lower-thirds sit at y 1150–1240 and are suppressed under a two-line caption page (6.3).

## Captions
- Word-synced from the ASR word list only; the planner never touches word times (6.1). Pages hold `words_per_page` words, preferring `prefer`; never split a marked name or number run; break on segment punctuation and on inter-word gaps over `gap_break_s`.
- Return `keywords` as word indices in priority order (names, numbers, hidden-truth nouns and verbs, the final question word); code keeps at most `emphasis_max_ratio` of the words and one keyword per page.
- Typography is the reference look above (Poppins 800 at 74 px, white with dark outline, the active word in yellow, the keyword boxed); block bottom anchored at `anchor_y`, at most `max_lines` lines, above the platform safe area and touching the PIP bottom (6.2, 6.3). Verbatim in the spoken language; Latin script for English loanwords as the ASR returns them.

## Sound
- Sound is the sound director's job (grill decision 7.1), not a fixed hit table: return a `sound_story` with a theme, a mood curve with build and drop points, a bed query (`theme`, `mood`, `energy`) and a per-beat cue list with intent labels; read the script and choose. Music and SFX come only from the tagged free library; never name a track.
- Bed target `bed_db_under_voice` dB under the voice, ducking at most `duck_max_db` dB, swells at most `swell_max_db` dB above target and drops at least `drop_min_db` dB below, every ramp at least `ramp_min_s` s. A drop is a step down at a beat boundary followed by a changeover cue, never a rise into a hit (7.3).
- The floor hits in `floor_hits` are derived by code from plan events so a short is never flat; the planner's cues layer on top within `cues_max_per_60s` and `cues_per_beat_max`, each between `cue_db_min` and `cue_db_max` dB under the voice. A tick on a step change is an ordinary cue choice under those caps (7.1 lifted the old chime/tick ban).
- Forbidden, checked in code on the SFX stem: `forbidden` (sweeps, risers, rumble crescendos, whooshes). Nothing on whip cuts, punch-ins, rings or lower-thirds.
- Voice −19 LUFS / −3 dBTP on the stem, master −14 LUFS / −1.5 dBTP (7.3).

## Finale
- The last beat is `off`, `min_s`–`max_s` long: the payoff line plus a call-to-action card with the presenter in its centre circle; captions are hidden from the finale word onward. The finale word gets a drum floor hit.
