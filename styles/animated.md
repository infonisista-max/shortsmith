---
version: "14"
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
  opening_beats_min: 2
  opening_beats_max: 3
  opening_max_s: 5.0
presenter:
  modes: [full, pip, "off"]
  full_max_fraction: 0.15
  full_never_consecutive: true
  full_reasons: [emotional_line, argument_turn]
  pip_max_run: 6
  off_max_run: 6
  opening_mode: pip
  finale_mode: "off"
cut:
  max_pause_s: 0.6
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
  kinds: [photo, card, clip, stamp, lower_third, finale, presenter_full, presenter_pip,
          list, chart, split, wall, map, infographic, pin_drop, route_arrow, label_flyin,
          counter, object_path]
  tier2_kinds: [parallax, vector_illustration]
  motion:
    photo: {kind: parallax, depth_px: 40, alternate: true}
    card: {kind: pop_in, scale_from: 0.6, scale_to: 1.0, border_px: 0, rotate_deg: 0.0,
           ring_color: "#F97316"}
    clip: {kind: push, scale_from: 1.0, scale_to: 1.0, speed: 1.0}  # 058
    stamp: {kind: pop, duration_s: 0.12, shake: true, palette: accent}
    lower_third: {kind: spring, duration_s: 0.3, top_y: 1150, bottom_y: 1240}
    finale: {kind: spring, duration_s: 0.4, cards: 3}
    text_pop: {kind: pop, duration_s: 0.18, hold_max_s: 2.5, max_per_beat: 2, tilt_deg: 8,
               size_px: 100, fill: "#FFD60A"}  # 061
    bubble: {kind: pop, duration_s: 0.18, hold_max_s: 3.0, max_per_beat: 2, words_max: 7,
             dialogue_gap_min_s: 0.6, dialogue_gap_max_s: 1.0, size_px: 58, min_size_px: 36,
             width_px: 660, fill: "#FFFFFF", ink: "#111111"}  # 063
    sticker: {kind: pop, duration_s: 0.18, hold_max_s: 2.5, max_per_beat: 1, size_px: 240,
              float_px: 12, float_period_s: 1.6}  # 062
  enter_transitions: [cut, fade, whip, zoom, spring, wipe]
  whip_max_per_3_beats: 1
  flash_max_per_60s: 5  # 060: the cap where a style enables `flash`; never two in a row
  text_pops_max_per_60s: 0  # 061: off here
  bubbles_max_per_60s: 0  # 063: off here
  stickers_max_per_60s: 0  # 062: off here
  clip_max_fraction: 0.35  # 058: the runtime share clips may take (reference median 31 %)
  transitions:
    fade: {duration_s: 0.35}
    whip: {duration_s: 0.22, blur_px: 14}
    zoom: {duration_s: 0.3, scale_from: 1.6}
    spring: {damping: 14, stiffness: 160, mass: 0.7}
    wipe: {duration_s: 0.25}
    flash: {duration_s: 0.3, color: "#FFFFFF"}  # 060: not enabled here
  unique_assets_min_per_60s: 12
  unique_assets_max_per_60s: 24
  reuse_max: 2  # 056: per image (one file, however many ids), carry-on beats and set pieces aside
  rescued_max_per_60s: 4
  full_bleed_max_upscale: 2.0  # 057: a portrait covering the frame at <= this is full-screen, any origin
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
  max_width_px: 880
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
  default_bed_query: upbeat playful ambient  # the bed search's last try (054)
  bed_query_anchor: music  # 069: every bed search rung carries it (Freesound adds tag:music)
  bed_db_under_voice: -14  # 056: run03 phone verdict "a bit loud, reduce by 30 %"
  bed_accept_db: [-15, -12]
  speech_band_hz: [250, 4000]
  speech_band_margin_db: 12
  speech_band_margin_max_db: 20  # 069: further under than this, a phone speaker does not play the bed (run03 9.4 heard, run04 28.7 not)
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
  forbidden: [sweep, riser, rumble_crescendo]
  # 070 (run04 QA, all styles): a soft mark only on a visible pop-in or transition, never
  # on every one (refs: ~6.7 sfx a minute against ~9.3 visual events, each synced to one)
  whoosh: {max_per_60s: 6, min_gap_s: 3.0, max_len_s: 0.8, "on": [fade, whip, zoom, spring, wipe, pop]}  # "on" quoted: YAML reads a bare on as true
  tick: {max_per_60s: 6, min_gap_s: 2.0, max_len_s: 0.25, "on": [pop]}
  ding: {max_per_60s: 2, max_len_s: 0.8, "on": [idea_sticker]}  # the FactTechz lightbulb (zXK42RMPKUY 34 s)
  floor_max_len_s: {bass: 1.5, drum: 1.2, thump: 0.8}  # 075's shortlist lengths
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
- Short beats (`min_s`–`max_s`), presenter mostly PIP or off; `full` is rare (`full_max_fraction`). The short opens with the speaker's first words (055): `opening_beats_min`–`opening_beats_max` `opening_mode` beats over the strongest illustrations of the subject (owner reference first), no animated title card, nothing lifted or dropped; the cut removes only silence (`cut.max_pause_s`).
- Same tiling, snapping and no-mid-word rules as explainer (3.1).

## B-roll
- Generated or vector illustrations with strong motion: parallax, pop-in, path animation; one consistent palette per short, and the accent may come from the user's references' dominant colour (1.3).
- Sources and rights as in explainer (5.1); generation cap `gen_max_per_short` is higher because illustration is the point here.
- Moving footage as in explainer (058): a `clip` beat is a muted full-screen stock clip on a concept beat only, never a named entity; at most `clip_max_fraction` of the runtime, drawn at `motion.clip.speed` with no push.
- The six 030 enter transitions are enabled (9.4), still at most one whip per three beats; `flash` (060) is not.

## Captions
- Kinetic captions that pop per phrase: `words_per_page` words, heavier weight, the active word scales harder, two-colour emphasis with the accent. Same anchor, safe area and line limit as explainer (6.3).

## Sound
- Upbeat bed `bed_db_under_voice` dB under the voice; pops and thumps on pop-ins are floor hits. Forbidden: `forbidden`, checked on the SFX stem (7.1, 7.3); a soft tick on a pop-in and a short whoosh on a transition, within `sound.tick` and `sound.whoosh` (070).

## Finale
- Animated end card with a call to action, `min_s`–`max_s` s.
