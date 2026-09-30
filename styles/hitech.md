---
version: "25"
status: draft
aliases: [hitech, hi-tech, tech, techy, gadget, gadgets, product, futuristic, cyber]
requires_components: [captions, pip, photo, card, clip, stamp, lower_third, finale, list,
                      chart, split, wall, infographic, label_flyin, counter, map,
                      pin_drop, route_arrow, object_path,
                      crop_fill, backdrop, polaroid,
                      cut, fade, wipe, zoom]
beats:
  min_s: 0.7
  max_s: 5.0
  set_piece_max_s: 7.0
  target_mean_s: 2.5
  mean_min_s: 2.0
  mean_max_s: 3.2
  density_gap_max_s: 1.5
  snap_window_s: 0.15
  opening_beats_min: 2
  opening_beats_max: 3
  opening_max_s: 5.0
presenter:
  modes: [full, pip, "off"]
  full_max_fraction: 0.2
  full_never_consecutive: true
  full_reasons: [emotional_line, argument_turn]
  pip_max_run: 6
  off_max_run: 4
  opening_mode: pip
  finale_mode: "off"
cut:
  max_pause_s: 0.6
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
  kinds: [photo, card, clip, stamp, lower_third, finale, presenter_full, presenter_pip,
          list, chart, split, wall, map, infographic, pin_drop, route_arrow, label_flyin,
          counter, object_path]
  tier2_kinds: []
  motion:
    photo: {kind: ken_burns, scale_from: 1.08, scale_to: 1.14, alternate: true}
    card: {kind: push, scale_from: 1.3, scale_to: 1.8, border_px: 2, rotate_deg: 0.0,
           ring_color: "#22D3EE"}
    # 102: the local motion measure - frames sampled motion_fps a second at 64 px, the
    # mean grey change per step (0-1). A clip whose best window moves less than
    # motion_min is passed over (a still colour clip measures 0; the synthetic
    # testsrc2 1080x1920 0.0044-0.006; run05 b18, which read as a still, 0.009-0.035).
    clip: {kind: push, scale_from: 1.0, scale_to: 1.0, speed: 1.0, motion_fps: 4,
           motion_min: 0.004}  # 058
    stamp: {kind: land, duration_s: 0.12, shake: false, palette: cyan_white}
    lower_third: {kind: fade, duration_s: 0.3, top_y: 1150, bottom_y: 1240}
    finale: {kind: fade, duration_s: 0.35, cards: 3}
    list: {kind: reveal, items_max: 6, duration_s: 0.30, scale_from: 1.08, scale_to: 1.14,
           dim: 0.55}
    split: {kind: slide, panes: 2, duration_s: 0.25, face_y: 0.3,
           faceless_y: 0.1}  # 105: a face centred 0.3 down its pane; no face: the top
    wall: {kind: zoom, cells_min: 4, cells_max: 9, duration_s: 0.25, scale_from: 1.12,
           scale_to: 1.2, dim: 0.7}
    chart: {kind: draw_on, marks_max: 6, duration_s: 0.5, decimals: 0, grouping: indian}
    infographic: {kind: fly_in, labels_max: 5, duration_s: 0.30, scale_from: 1.04,
                  scale_to: 1.1, dim: 0.35}
    counter: {kind: count_up, grouping: indian}
    text_pop: {kind: pop, duration_s: 0.18, hold_max_s: 2.5, max_per_beat: 2, tilt_deg: 4,
               size_px: 92, fill: "#FFD60A"}  # 061
    bubble: {kind: pop, duration_s: 0.18, hold_max_s: 3.0, max_per_beat: 2, words_max: 7,
             dialogue_gap_min_s: 0.6, dialogue_gap_max_s: 1.2, size_px: 54, min_size_px: 36,
             width_px: 640, fill: "#FFFFFF", ink: "#0F172A"}  # 063
    sticker: {kind: pop, duration_s: 0.18, hold_max_s: 2.5, max_per_beat: 1, size_px: 240,
              float_px: 10, float_period_s: 1.8}  # 062
    # 078: the marker over an owner's article screenshot - the accent at about 45 %,
    # padded round each text line; the screenshot card pushes to push_to about the lines.
    highlight: {kind: sweep, color: "#22D3EE", opacity: 0.45, pad_px: 8, push_to: 1.12}
    # 102: the light film grade on a clip or still the era judge found `timeless` (099): a
    # modern-looking shot made to sit in the period. The references' archival stills are
    # fully black and white (NKB b06, b12, b21 `bw`); a stand-in goes 60 % of the way
    # (saturate 0.4) with a warm cast and a touch of contrast.
    era_grade: {sepia: 0.3, saturate: 0.4, contrast: 1.05}
    # 103: the picture treatments beside the full-bleed photo and the card. `backdrop`: the
    # image sharp across the frame (at most width_px wide, never over max_upscale) between
    # the safe top and the card line, over its own blurred, darkened, enlarged copy (the
    # card's cover numbers: blur 36 px, brightness 0.45, the dark surround of the reference
    # cards), pushing scale_from -> scale_to (the photo's +0.06). `crop_fill`: full screen
    # cropped round the detected face (its centre at face_y of the height, as a split pane
    # frames one), never over max_upscale, a slow push. `polaroid`: a print width_px wide,
    # border_px white round the picture and bottom_px under it (the lower-third label sits
    # there), dropping drop_px in drop_s (the wall's spring) under a shadow_px shadow, its
    # tilt varied per use within tilt_min_deg-tilt_max_deg (the text pop's 6 degrees).
    backdrop: {kind: push, scale_from: 1.0, scale_to: 1.06, width_px: 1080, max_upscale: 2.0,
               blur_px: 36, brightness: 0.45}
    crop_fill: {kind: push, scale_from: 1.0, scale_to: 1.08, max_upscale: 2.5, face_y: 0.38}
    polaroid: {kind: drop, width_px: 760, border_px: 20, bottom_px: 84, max_upscale: 1.5,
               tilt_min_deg: -6, tilt_max_deg: 6, drop_px: 240, drop_s: 0.3, shadow_px: 36,
               blur_px: 36, brightness: 0.45}
    map: {kind: travel, markers_max: 6, duration_s: 0.45, padding: 0.15, land: "#3E6E96",
          coast: "#22D3EE", border: "#020617", coast_px: 2, border_px: 2,
          # 072: a pill over another pill or dot flips sides, then steps up or down
          label_step_px: 24, label_steps_max: 3,
          # 104: every map at least min_span_deg across; the named country filled in
          # `highlight` and circled (red_circle_india, ePTZVwipoAM 48 s: drawn in 0.3 s,
          # 0.6 of the frame) with its tag at a tilt (indus_war_tag, 26 s: slides in
          # 0.3 s); up to names_max countries in view named at name_font_px.
          min_span_deg: 12, names_max: 6, name_font_px: 30, circle_px: 10,
          circle_size: 0.6, circle_draw_s: 0.3, tag_font_px: 48, tag_tilt_deg: -8,
          tag_slide_s: 0.3, stamp_margin_px: 24,  # 108: a stamp or calendar keeps this far off the map's content
          highlight: "#A3E635", name_color: "#FFFFFF",
          circle_color: "#F43F5E", tag_fill: "#22D3EE", tag_ink: "#020617"}
  enter_transitions: [cut, fade, wipe, zoom]
  whip_max_per_3_beats: 0
  flash_max_per_60s: 5  # 060: the cap where a style enables `flash`; never two in a row
  text_pops_max_per_60s: 0  # 061: off here
  bubbles_max_per_60s: 0  # 063: off here
  stickers_max_per_60s: 0  # 062: off here
  highlights_max_per_60s: 0  # 078: off here
  clip_max_fraction: 0.35  # 058: the runtime share clips may take (reference median 31 %)
  # 103: the treatments the planner picks per still, in the renderer's fallback order; a
  # framed one never on two beats in a row; the red card at most card_max_per_60s (the
  # approved references: NKB 2 archival cards in 60 s, Dyson 3 in 57.5 s).
  treatments: [photo, crop_fill, backdrop, polaroid, card]
  no_repeat_treatments: [backdrop, polaroid, card]
  card_max_per_60s: 3
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
  # 102: the camera move each planner `motion` names on a full-screen still (photo,
  # crop_fill), from the beat tables of the two approved shorts (work/beat-tables.md,
  # `s0->s1` scale and `x`/`y` drift in % of the frame): push_in = the origin-pinned
  # pushes (Dyson b05 1.0->1.22, b10 1.28, b20 1.16, NKB b23 1.10: median ~1.2); pull_out =
  # the reveals (NKB b03 1.35->1.12, b06 1.25->1.10, b21 1.30->1.12, Dyson b03 1.32->1.08,
  # b11 1.38->1.06, b16 1.16->1.0, b19 1.15->1.02: medians 1.30 -> 1.08); ken_burns_in =
  # the drifting pushes (12 beats, median +0.14, y 2 -> -2 %), started at 1.04 so the 4 %
  # drift never shows an edge; ken_burns_out = the drifting pull-backs (NKB b05 1.12->1.0 x
  # 3->-3, b24 1.14->1.0, Dyson b09 1.12->1.0 x -2->2: -0.13); the pans = the largest
  # drift in the tables (6 %: NKB b05 x, Dyson b17 y) at a 1.12 hold; hold = no move in
  # the tables (every reference still moves), so the gentlest breath, +0.03. pan_x / pan_y
  # are the picture's travel (+ right / down): pan_left slides it right. `aim: subject`
  # centres the push on the beat's subject face (the one the card's ring circles).
  motion_moves:
    push_in: {scale_from: 1.0, scale_to: 1.2, pan_x: 0.0, pan_y: 0.0, aim: subject}
    pull_out: {scale_from: 1.3, scale_to: 1.08, pan_x: 0.0, pan_y: 0.0, aim: subject}
    ken_burns_in: {scale_from: 1.04, scale_to: 1.18, pan_x: 0.0, pan_y: -0.04, aim: frame}
    ken_burns_out: {scale_from: 1.17, scale_to: 1.04, pan_x: 0.04, pan_y: 0.0, aim: frame}
    pan_left: {scale_from: 1.12, scale_to: 1.12, pan_x: 0.06, pan_y: 0.0, aim: frame}
    pan_right: {scale_from: 1.12, scale_to: 1.12, pan_x: -0.06, pan_y: 0.0, aim: frame}
    pan_up: {scale_from: 1.12, scale_to: 1.12, pan_x: 0.0, pan_y: 0.06, aim: frame}
    pan_down: {scale_from: 1.12, scale_to: 1.12, pan_x: 0.0, pan_y: -0.06, aim: frame}
    hold: {scale_from: 1.02, scale_to: 1.05, pan_x: 0.0, pan_y: 0.0, aim: frame}
  full_bleed_max_upscale: 2.0  # 057: a portrait covering the frame at <= this is full-screen, any origin
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
  max_width_px: 880
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
  default_bed_query: electronic ambient technology  # the bed search's last try (054)
  bed_query_anchor: music  # 069: every bed search rung carries it (Freesound adds tag:music)
  bed_db_under_voice: -14  # 056: run03 phone verdict "a bit loud, reduce by 30 %"
  bed_accept_db: [-15, -12]
  speech_band_hz: [250, 4000]
  speech_band_margin_db: 12
  speech_band_margin_max_db: 20  # 069, 088: screens unheard beds only (runtime fallbacks); an ear-approved bed over it plays with a note. Set from run04's bed, freesound_557546, a car exhaust, not music; 089 re-derives it
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
  forbidden: [sweep, riser, rumble_crescendo]
  # 070 (run04 QA, all styles): a soft mark only on a visible pop-in or transition, never
  # on every one (refs: ~6.7 sfx a minute against ~9.3 visual events, each synced to one)
  whoosh: {max_per_60s: 6, min_gap_s: 3.0, max_len_s: 0.8, "on": [fade, wipe, zoom, pop]}  # "on" quoted: YAML reads a bare on as true
  tick: {max_per_60s: 6, min_gap_s: 2.0, max_len_s: 0.25, "on": [pop]}
  ding: {max_per_60s: 2, max_len_s: 0.8, "on": [idea_sticker]}  # the FactTechz lightbulb (zXK42RMPKUY 34 s)
  floor_max_len_s: {bass: 1.5, drum: 1.2, thump: 0.8}  # 075's shortlist lengths
  # 076: at most one bed change, on a story-part boundary, both beds approved (075). The
  # lengths are starting values: no committed card is v2 yet, so none carries a measured
  # `music_changes` to derive them from; re-derive after `reference inventory --all`.
  bed_changes_max: 1
  bed_crossfade_s: 1.0  # both beds heard together this long
  bed_silence_s: 0.5  # a drop to silence holds this long before the new bed
  bed_cut_fade_s: 0.02  # a hard cut's fade, under one frame at 30 fps
  # 087: every shipped style is a fact or explainer channel, so a flavour or mood miss
  # takes the facts-default bed before a same-mood bed of another flavour.
  facts_default_first: true
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
Dark, glowing, product and tech facts. DRAFT (grill decision 1.4): aliases resolve to `explainer` with a notice until one rated short flips this to shipped. This is the draft the 1.4 smoke render uses (ticket 048: `python -m shortsmith.smoke --style hitech`), so `requires_components` is complete against the renderer registry: the spec stamp is the `stamp` component in the `cyan_white` palette and the glow border is the `pip` ring in `pip.ring_color`. Not judged, not shipped; the numbers are a first draft for the smoke, not read off reference frames.

## Beat grammar
- Beats `min_s`–`max_s`; presenter in a framed PIP with a glow border most of the time. The short opens with the speaker's first words (055): `opening_beats_min`–`opening_beats_max` quick `opening_mode` beats over the product's strongest images (owner reference first, then the best sourced or generated image), no title card, nothing lifted or dropped; the cut removes only silence (`cut.max_pause_s`). Same tiling, snapping and no-mid-word rules as explainer (3.1).

## B-roll
- Product images on the dark gradient, UI mock cards, spec stamps and number counters; sources and rights as in explainer (5.1). Generated named products stay illustration-style (`illustration_look`).
- Moving footage as in explainer (058): a `clip` beat is a muted full-screen stock clip on a concept beat (a process, a material, a kind of place) or a named place, era, event or object (a product included), never a named person (099; on an era beat, period-looking footage comes first; a timeless shot (desert, sea, sky, sand dunes) is fine and may take a light film or sepia grade; never modern cars, skylines, phones or present-day clothes standing in for the old era, then a still (099)); at most `clip_max_fraction` of the runtime, drawn at `motion.clip.speed` with no push.
- The set pieces, infographics and map are the explainer's components under hitech numbers: flat cards (`rotate_deg` 0, a 2 px border), deeper dims under lists and walls, the map's land in the gradient's blue with a cyan coast.
- Transitions are `cut`, `fade`, `wipe` and `zoom` (9.4); no whips or springs, no flash (060).
- Article highlights (4.1 as amended by 078; off here: `highlights_max_per_60s` is 0): where a style allows them, a `photo` or `card` beat that shows the owner's uploaded article or document screenshot (an owner reference; never a searched or generated page, never a made-up article) may carry one `highlight`: the `sentence` to mark as it reads on the screenshot and the transcript `words` that say it. A marker in `motion.highlight.color` at `motion.highlight.opacity` sweeps the sentence's lines left to right from the first word to the last while the screenshot, a straight card, pushes in toward them. Code finds the lines on the image; a sentence it cannot find is dropped and the beat stays.

## Captions
- Wider letter spacing for a monospace flavour, cyan/white emphasis, the same lower-third anchor and safe area as explainer (6.3); the plan may move a page to the upper third only once ticket 010 adds per-page zones.

## Sound
- Sub-bass electronic bed `bed_db_under_voice` dB under the voice; a single low thump on reveals is the floor. Forbidden: `forbidden`, checked on the SFX stem (7.1, 7.3); a soft tick on a pop-in and a short whoosh on a transition, within `sound.tick` and `sound.whoosh` (070).

## Finale
- Spec summary card with a call to action, `min_s`–`max_s` s.
