---
status: draft
aliases: [hitech, hi-tech, tech, techy, gadget, gadgets, product, futuristic, cyber]
requires_components: [captions, pip, spec_stamp, glow_ring, counter]
beats:
  min_s: 0.7
  max_s: 5.0
  set_piece_max_s: 7.0
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
  full_max_fraction: 0.2
  full_never_consecutive: true
  full_reasons: [cold_open, emotional_line, argument_turn]
  pip_max_run: 6
  off_max_run: 4
  hook_modes: [full, "off"]
  finale_mode: "off"
pip:
  left: 60
  top: 970
  diameter: 300
  large_face_diameter: 340
  large_face_ratio: 0.45
  chin_anchor: 0.82
  ring_px: 4
  ring_color: "#22D3EE"
broll:
  kinds: [photo, card, stamp, lower_third, hook_cards, finale, presenter_full, presenter_pip,
          list, chart, split, wall, map, infographic, pin_drop, route_arrow, label_flyin,
          counter, object_path]
  tier2_kinds: []
  motion:
    photo: {kind: ken_burns, scale_from: 1.08, scale_to: 1.14, alternate: true}
    card: {kind: push, scale_from: 1.3, scale_to: 1.8, border_px: 2, rotate_deg: 0.0,
           ring_color: "#22D3EE"}
    stamp: {kind: land, duration_s: 0.12, shake: false, palette: cyan_white}
    lower_third: {kind: fade, duration_s: 0.3, top_y: 1150, bottom_y: 1240}
    hook_cards: {kind: zoom, cards: 3}
    finale: {kind: fade, duration_s: 0.35}
  enter_transitions: [cut, fade, wipe, zoom]
  whip_max_per_3_beats: 0
  unique_assets_min_per_60s: 12
  unique_assets_max_per_60s: 24
  reuse_max: 4
  rescued_max_per_60s: 4
  card_max_bottom_y: 1240
  stamp_max_y_fraction: 0.6
  photo_look: "product photograph on a dark gradient, rim light, high contrast"
  illustration_look: "dark futuristic illustration, cyan glow accents, clean geometry, clearly stylised"
  scene_mood: "sleek, high-tech mood"
  scene_lighting: "rim light on a dark background, high contrast"
captions:
  font_family: Poppins
  font_weight: 700
  size_px: 70
  line_height: 1.35
  letter_spacing_px: 1.5
  anchor_y: 1460
  max_lines: 2
  max_width_px: 960
  word_gap_px: 22
  unspoken_alpha: 0.85
  active_color: "#22D3EE"
  active_scale: 1.06
  active_scale_s: 0.08
  keyword_fg: "#020617"
  keyword_bg: "#22D3EE"
  keyword_pad_px: 12
  keyword_radius_px: 6
  enter_scale_from: 0.96
  enter_s: 0.1
  enter_opacity_s: 0.06
  stroke_px: 2
  drop_px: 2
  glow_px: 24
  words_per_page: [2, 4]
  prefer: 3
  emphasis_max_ratio: 0.25
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
  fade_in_s: 0.6
  fade_out_s: 1.2
  floor_hits:
    bass: [stamp, reveal]
    drum: [money_reveal, finale_word]
    thump: [card_fly_in]
  cues_max_per_60s: 16
  cues_per_beat_max: 1
  cue_db_min: -10
  cue_db_max: -2
  forbidden: [sweep, riser, rumble_crescendo, whoosh]
finale:
  kind: spec_summary_card
  mode: "off"
  min_s: 0.8
  max_s: 1.5
  cta: true
budget:
  judge_max_calls: 40
  search_max_queries: 60
  gen_max_per_short: 8
palette:
  gradient: ["#020617", "#0F172A"]
  angle_deg: 160
  accent: "#22D3EE"
---
# Style: hitech
Dark, glowing, product and tech facts. DRAFT (grill decision 1.4): aliases resolve to `explainer` with a notice until one rated short flips this to shipped. This is the draft the 1.4 smoke render uses (ticket 048), since it needs the fewest style-specific components.

## Beat grammar
- Beats `min_s`–`max_s`; presenter in a framed PIP with a glow border most of the time; the hook is a spec or number stamp over the product. Same tiling, snapping and no-mid-word rules as explainer (3.1).

## B-roll
- Product images on the dark gradient, UI mock cards, spec stamps and number counters; sources and rights as in explainer (5.1). Generated named products stay illustration-style (`illustration_look`).
- Transitions are `cut`, `fade`, `wipe` and `zoom` (9.4); no whips or springs.

## Captions
- Wider letter spacing for a monospace flavour, cyan/white emphasis, the same lower-third anchor and safe area as explainer (6.3); the plan may move a page to the upper third only once ticket 010 adds per-page zones.

## Sound
- Sub-bass electronic bed `bed_db_under_voice` dB under the voice; a single low thump on reveals is the floor. Forbidden: `forbidden`, checked on the SFX stem (7.1, 7.3).

## Finale
- Spec summary card with a call to action, `min_s`–`max_s` s.
