---
version: "1"
status: draft
aliases: [animated, animation, cartoon, motion, motion-graphics, illustrated, vector]
requires_components: [captions, pip, parallax, vector_illustration, title_card, end_card]
beats:
  min_s: 0.7
  max_s: 4.0
  set_piece_max_s: 6.0
  target_mean_s: 2.5
  mean_min_s: 2.0
  mean_max_s: 3.2
  density_gap_max_s: 1.2
  snap_window_s: 0.15
  cold_open_min_s: 0.7
  cold_open_max_s: 2.0
  hook_cards_min_s: 2.0
  hook_cards_max_s: 4.0
  hook_title_max_words: 8
presenter:
  modes: [full, pip, "off"]
  full_max_fraction: 0.15
  full_never_consecutive: true
  full_reasons: [cold_open, emotional_line, argument_turn]
  pip_max_run: 6
  off_max_run: 6
  hook_modes: ["off"]
  finale_mode: "off"
pip:
  left: 60
  top: 990
  diameter: 260
  large_face_diameter: 300
  large_face_ratio: 0.45
  chin_anchor: 0.82
  ring_px: 8
  ring_color: "#F97316"
broll:
  kinds: [photo, card, stamp, lower_third, hook_cards, finale, presenter_full, presenter_pip,
          list, chart, split, wall, map, infographic, pin_drop, route_arrow, label_flyin,
          counter, object_path]
  tier2_kinds: [parallax, vector_illustration]
  motion:
    photo: {kind: parallax, depth_px: 40, alternate: true}
    card: {kind: pop_in, scale_from: 0.6, scale_to: 1.0, border_px: 0, rotate_deg: 0.0,
           ring_color: "#F97316"}
    stamp: {kind: pop, duration_s: 0.12, shake: true, palette: accent}
    lower_third: {kind: spring, duration_s: 0.3, top_y: 1150, bottom_y: 1240}
    hook_cards: {kind: spring, cards: 3}
    finale: {kind: spring, duration_s: 0.4}
  enter_transitions: [cut, fade, whip, zoom, spring, wipe]
  whip_max_per_3_beats: 1
  transitions:
    fade: {duration_s: 0.35}
    whip: {duration_s: 0.22, blur_px: 14}
    zoom: {duration_s: 0.3, scale_from: 1.6}
    spring: {damping: 14, stiffness: 160, mass: 0.7}
    wipe: {duration_s: 0.25}
  unique_assets_min_per_60s: 12
  unique_assets_max_per_60s: 24
  reuse_max: 4
  rescued_max_per_60s: 4
  card_max_bottom_y: 1240
  stamp_max_y_fraction: 0.6
  photo_look: "bold flat-colour illustration, strong shapes, consistent palette"
  illustration_look: "vector cartoon illustration, thick outlines, limited palette, clearly stylised"
  scene_mood: "playful, upbeat mood"
  scene_lighting: "flat even light, no harsh shadows"
captions:
  font_family: Poppins
  font_weight: 900
  size_px: 78
  line_height: 1.3
  letter_spacing_px: 0.5
  anchor_y: 1460
  max_lines: 2
  max_width_px: 960
  word_gap_px: 24
  unspoken_alpha: 0.8
  active_color: "#F97316"
  active_scale: 1.12
  active_scale_s: 0.08
  keyword_fg: "#FFFFFF"
  keyword_bg: "#F97316"
  keyword_pad_px: 14
  keyword_radius_px: 18
  enter_scale_from: 0.8
  enter_s: 0.14
  enter_opacity_s: 0.06
  stroke_px: 3
  drop_px: 4
  glow_px: 0
  words_per_page: [1, 3]
  prefer: 2
  emphasis_max_ratio: 0.3
  gap_break_s: 0.35
sound:
  bed_score_threshold: 0.5  # a tag hit scores 1, energy distance at most 0.4: one tag must match
  bed_db_under_voice: -10
  bed_accept_db: [-12, -9]
  speech_band_hz: [250, 4000]
  speech_band_margin_db: 20
  duck_max_db: 4
  swell_max_db: 4
  drop_min_db: -8
  ramp_min_s: 1.5
  fade_in_s: 0.4
  fade_out_s: 1.0
  floor_hits:
    bass: [stamp, reveal, header]
    drum: [money_reveal, finale_word]
    thump: [card_fly_in, pop_in]
  cues_max_per_60s: 20
  cues_per_beat_max: 1
  cue_db_min: -10
  cue_db_max: -2
  forbidden: [sweep, riser, rumble_crescendo, whoosh]
finale:
  kind: end_card
  mode: "off"
  min_s: 0.8
  max_s: 1.5
  cta: true
budget:
  judge_max_calls: 40
  search_max_queries: 60
  gen_max_per_short: 12
palette:
  gradient: ["#2A0A4A", "#6B21A8"]
  angle_deg: 160
  accent: "#F97316"
---
# Style: animated
Motion-graphics heavy; illustrated B-roll dominates. DRAFT (grill decision 1.4): aliases resolve to `explainer` with a notice until one rated short flips this to shipped. Full parallax depth and the vector-illustration look are the tier-2 kinds tied to this skin (9.2).

## Beat grammar
- Short beats (`min_s`–`max_s`), presenter mostly PIP or off; `full` is rare (`full_max_fraction`). The hook is an animated title card, so hook beats are `off` only.
- Same tiling, snapping and no-mid-word rules as explainer (3.1).

## B-roll
- Generated or vector illustrations with strong motion: parallax, pop-in, path animation; one consistent palette per short, and the accent may come from the user's references' dominant colour (1.3).
- Sources and rights as in explainer (5.1); generation cap `gen_max_per_short` is higher because illustration is the point here.
- All six enter transitions are enabled (9.4), still at most one whip per three beats.

## Captions
- Kinetic captions that pop per phrase: `words_per_page` words, heavier weight, the active word scales harder, two-colour emphasis with the accent. Same anchor, safe area and line limit as explainer (6.3).

## Sound
- Upbeat bed `bed_db_under_voice` dB under the voice; pops and thumps on pop-ins are floor hits. Forbidden: `forbidden`, checked on the SFX stem (7.1, 7.3).

## Finale
- Animated end card with a call to action, `min_s`–`max_s` s.
