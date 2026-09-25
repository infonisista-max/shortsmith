---
status: draft
aliases: [educational, education, teach, teaching, lesson, tutorial, learn, classroom]
requires_components: [captions, pip, diagram, step_card, recap_card]
beats:
  min_s: 1.0
  max_s: 8.0
  set_piece_max_s: 10.0
  target_mean_s: 5.5
  mean_min_s: 4.0
  mean_max_s: 8.0
  density_gap_max_s: 2.5
  snap_window_s: 0.15
  cold_open_min_s: 1.0
  cold_open_max_s: 3.0
  hook_cards_min_s: 2.0
  hook_cards_max_s: 4.0
  hook_title_max_words: 10
presenter:
  modes: [full, pip, "off"]
  full_max_fraction: 0.4
  full_never_consecutive: false
  full_reasons: [cold_open, emotional_line, argument_turn, setup, summary]
  pip_max_run: 8
  off_max_run: 3
  hook_modes: [full, "off"]
  finale_mode: "off"
pip:
  left: 60
  top: 1000
  diameter: 280
  large_face_diameter: 320
  large_face_ratio: 0.45
  chin_anchor: 0.82
  ring_px: 4
  ring_color: "#1B7F79"
broll:
  kinds: [photo, card, stamp, lower_third, hook_cards, finale, presenter_full, presenter_pip,
          list, chart, split, map, infographic, pin_drop, route_arrow, label_flyin, counter]
  tier2_kinds: []
  motion:
    photo: {kind: ken_burns, scale_from: 1.04, scale_to: 1.08, alternate: true}
    card: {kind: push, scale_from: 1.1, scale_to: 1.25, border_px: 10, rotate_deg: 0.0,
           ring_color: "#1B7F79"}
    stamp: {kind: fade, duration_s: 0.3, shake: false, palette: teal}
    lower_third: {kind: fade, duration_s: 0.35, top_y: 1150, bottom_y: 1240}
    hook_cards: {kind: fade, cards: 3}
    finale: {kind: fade, duration_s: 0.5}
  enter_transitions: [cut, fade]
  whip_max_per_3_beats: 0
  transitions:
    fade: {duration_s: 0.35}
    whip: {duration_s: 0.22, blur_px: 14}
    zoom: {duration_s: 0.3, scale_from: 1.6}
    spring: {damping: 14, stiffness: 160, mass: 0.7}
    wipe: {duration_s: 0.25}
  unique_assets_min_per_60s: 8
  unique_assets_max_per_60s: 16
  reuse_max: 4
  rescued_max_per_60s: 4
  card_max_bottom_y: 1240
  stamp_max_y_fraction: 0.6
  photo_look: "clean textbook photograph, even light, neutral background"
  illustration_look: "flat educational diagram illustration, two-colour, clean lines"
  scene_mood: "calm, explanatory mood"
  scene_lighting: "even studio light on a neutral background"
captions:
  font_family: Poppins
  font_weight: 700
  size_px: 66
  line_height: 1.35
  letter_spacing_px: 0.0
  anchor_y: 1460
  max_lines: 2
  max_width_px: 960
  word_gap_px: 20
  unspoken_alpha: 0.9
  active_color: "#FFFFFF"
  active_scale: 1.0
  active_scale_s: 0.0
  keyword_fg: "#FFFFFF"
  keyword_bg: "#1B7F79"
  keyword_pad_px: 12
  keyword_radius_px: 10
  enter_scale_from: 1.0
  enter_s: 0.0
  enter_opacity_s: 0.12
  stroke_px: 2
  drop_px: 2
  glow_px: 0
  words_per_page: [3, 7]
  prefer: 5
  emphasis_max_ratio: 0.2
  gap_break_s: 0.35
sound:
  bed_score_threshold: 0.5  # a tag hit scores 1, energy distance at most 0.4: one tag must match
  bed_db_under_voice: -14
  bed_accept_db: [-15, -12]
  speech_band_hz: [250, 4000]
  speech_band_margin_db: 20
  duck_max_db: 3
  swell_max_db: 3
  drop_min_db: -8
  ramp_min_s: 1.5
  fade_in_s: 0.8
  fade_out_s: 1.5
  floor_hits:
    bass: [reveal]
    drum: [finale_word]
    thump: []
  cues_max_per_60s: 12
  cues_per_beat_max: 1
  cue_db_min: -12
  cue_db_max: -4
  forbidden: [sweep, riser, rumble_crescendo, whoosh]
finale:
  kind: recap_card
  mode: "off"
  min_s: 1.0
  max_s: 2.0
  cta: false
budget:
  judge_max_calls: 40
  search_max_queries: 60
  gen_max_per_short: 8
palette:
  gradient: ["#F4F1EA", "#E4DDD0"]
  angle_deg: 160
  accent: "#1B7F79"
---
# Style: educational
Calm, clear teaching. DRAFT (grill decision 1.4): aliases resolve to `explainer` with a notice until one rated short flips this to shipped. `requires_components` names what the renderer still owes it.

## Beat grammar
- Longer beats than explainer (`mean_min_s`–`mean_max_s`): presenter full-frame for the setup and the summary (`setup` and `summary` are valid reasons here), PIP during diagrams, off-screen while a step card or process animation carries the point.
- The hook is the question the video answers: cold open on the question, hook cards showing the three things the answer needs.
- Same tiling, snapping and no-mid-word rules as explainer (3.1).

## B-roll
- Diagrams, labelled images, step cards and simple process animations dominate; photos are calm Ken Burns, cards sit flat with no rotation.
- Sources and rights as in explainer (5.1); generated illustration is the flat diagram look in `illustration_look`.
- Fewer unique assets than explainer (`unique_assets_min_per_60s`–`unique_assets_max_per_60s`); reuse a diagram across the steps it explains.
- Transitions are `cut` and `fade` only (9.4); no whips.

## Captions
- Full short sentences of `words_per_page` words, neutral typography, no active-word pop; the key term is boxed in the accent colour. Same anchor, safe area and two-line limit as explainer (6.3).

## Sound
- Soft ambient bed `bed_db_under_voice` dB under the voice; a soft tick on step changes is a planner cue choice under the 7.3 caps (7.1 lifted the old tick ban). Forbidden: `forbidden`, checked on the SFX stem.

## Finale
- One-line recap card, `min_s`–`max_s` s, no call to action.
