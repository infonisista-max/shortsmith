---
version: "16"
status: shipped
aliases: [vishva, vishvagyan, vishva gyan, desi, history]
requires_components: [captions, pip, photo, card, clip, stamp, lower_third, finale, list,
                      chart, split, wall, infographic, label_flyin, counter, map,
                      pin_drop, route_arrow, object_path,
                      crop_fill, backdrop, polaroid,
                      cut, fade, whip, zoom, spring, wipe, flash,
                      text_pop, bubble, sticker, banner]
beats:
  min_s: 0.7
  max_s: 6.0
  set_piece_max_s: 8.0
  target_mean_s: 2.6
  mean_min_s: 2.1
  mean_max_s: 3.2
  density_gap_max_s: 1.5
  snap_window_s: 0.15
  opening_beats_min: 2
  opening_beats_max: 3
  opening_max_s: 5.0
presenter:
  modes: [full, pip, "off"]
  full_max_fraction: 0.25
  full_never_consecutive: true
  full_reasons: [emotional_line, argument_turn]
  pip_max_run: 6
  off_max_run: 3
  opening_mode: pip
  finale_mode: "off"
cut:
  max_pause_s: 0.6  # 055: a sentence pause; the pager already breaks a page at 0.35 s
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
  kinds: [photo, card, clip, stamp, lower_third, finale, presenter_full, presenter_pip,
          list, chart, split, wall, map, infographic, pin_drop, route_arrow, label_flyin,
          counter, object_path]
  tier2_kinds: []
  motion:
    photo: {kind: ken_burns, scale_from: 1.10, scale_to: 1.16, alternate: true}
    card: {kind: push, scale_from: 1.45, scale_to: 2.1, border_px: 14, rotate_deg: -1.5,
           ring_color: "#E53935"}
    # 058: a full-screen stock clip; no push and real speed (4 of the 119 reference clips
    # were pushed, 5 were slowed: the clip's own movement is the motion).
    # 102: the local motion measure - frames sampled motion_fps a second at 64 px, the
    # mean grey change per step (0-1). A clip whose best window moves less than
    # motion_min is passed over (a still colour clip measures 0; the synthetic
    # testsrc2 1080x1920 0.0044-0.006; run05 b18, which read as a still, 0.009-0.035).
    clip: {kind: push, scale_from: 1.0, scale_to: 1.0, speed: 1.0, motion_fps: 4,
           motion_min: 0.004}
    stamp: {kind: land, duration_s: 0.16, shake: true, palette: yellow_green_red}
    lower_third: {kind: fade, duration_s: 0.35, top_y: 1150, bottom_y: 1240}
    finale: {kind: fade, duration_s: 0.35, cards: 3}
    list: {kind: reveal, items_max: 6, duration_s: 0.35, scale_from: 1.15, scale_to: 1.25,
           dim: 0.45}
    # 059: two pictures top and bottom, the Vishva Gyan panels (refs 18-39 % of the runtime)
    split: {kind: slide, panes: 2, duration_s: 0.30, layout: stacked,
           face_y: 0.3, faceless_y: 0.1}  # 105: a face centred 0.3 down its pane; no face: the top
    wall: {kind: spring, cells_min: 4, cells_max: 9, duration_s: 0.30, scale_from: 1.2,
           scale_to: 1.3, dim: 0.65}
    chart: {kind: draw_on, marks_max: 6, duration_s: 0.6, decimals: 0, grouping: indian}
    infographic: {kind: fly_in, labels_max: 5, duration_s: 0.35, scale_from: 1.06,
                  scale_to: 1.12, dim: 0.3}
    counter: {kind: count_up, grouping: indian}
    map: {kind: travel, markers_max: 6, duration_s: 0.5, padding: 0.15, land: "#E3D9C0",
          coast: "#9DBBF5", border: "#0B1D3A", coast_px: 3, border_px: 2,
          # 072: a pill over another pill or dot flips sides, then steps up or down
          label_step_px: 24, label_steps_max: 3,
          # 104: every map at least min_span_deg across; the named country filled in
          # `highlight` and circled (red_circle_india, ePTZVwipoAM 48 s: drawn in 0.3 s,
          # 0.6 of the frame) with its tag at a tilt (indus_war_tag, 26 s: slides in
          # 0.3 s); up to names_max countries in view named at name_font_px.
          min_span_deg: 12, names_max: 6, name_font_px: 30, circle_px: 10,
          circle_size: 0.6, circle_draw_s: 0.3, tag_font_px: 48, tag_tilt_deg: -8,
          tag_slide_s: 0.3,
          highlight: "#1F9E89", name_color: "#0B1D3A",
          circle_color: "#E53935", tag_fill: "#FFD60A", tag_ink: "#111111"}
    # 061: 1-4 bold words pinned on the picture, landing on the spoken word; `fill` is
    # the pop yellow, white is white, and the accent (years, numbers) is `palette.accent`.
    text_pop: {kind: pop, duration_s: 0.2, hold_max_s: 2.5, max_per_beat: 2, tilt_deg: 6,
               size_px: 96, fill: "#FFD60A"}
    # 063: speech and thought bubbles of the recording's own words; a beat may carry a
    # dialogue pair, the second landing dialogue_gap_min_s-dialogue_gap_max_s after the
    # first; the text shrinks from size_px to min_size_px to fit width_px, then fails.
    bubble: {kind: pop, duration_s: 0.2, hold_max_s: 3.0, max_per_beat: 2, words_max: 7,
             dialogue_gap_min_s: 0.6, dialogue_gap_max_s: 1.2, size_px: 56, min_size_px: 36,
             width_px: 640, fill: "#FFFFFF", ink: "#111111"}
    # 062: a Fluent Emoji 3D sticker popping in on its word, then floating gently; a
    # size_px square (180-320 px), one per beat at most.
    sticker: {kind: pop, duration_s: 0.2, hold_max_s: 2.5, max_per_beat: 1, size_px: 240,
              float_px: 10, float_period_s: 1.8}
    # 078: the marker over an owner's article screenshot - the accent at about 45 %,
    # padded round each text line; the screenshot card pushes to push_to about the lines.
    highlight: {kind: sweep, color: "#FFD60A", opacity: 0.45, pad_px: 8, push_to: 1.12}
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
  enter_transitions: [cut, fade, whip, zoom, spring, flash]
  whip_max_per_3_beats: 1
  flash_max_per_60s: 5  # 060: never two in a row (refs: at most 4 a minute)
  text_pops_max_per_60s: 9  # 061
  bubbles_max_per_60s: 4  # 063
  stickers_max_per_60s: 2  # 062
  highlights_max_per_60s: 0  # 078: off here
  clip_max_fraction: 0.15  # 058: the runtime share clips may take
  # 103: the treatments the planner picks per still, in the renderer's fallback order; a
  # framed one never on two beats in a row; the red card at most card_max_per_60s (the
  # approved references: NKB 2 archival cards in 60 s, Dyson 3 in 57.5 s).
  treatments: [photo, crop_fill, backdrop, polaroid, card]
  no_repeat_treatments: [backdrop, polaroid, card]
  card_max_per_60s: 3
  # 107: the banner of the recording's words. FbaBcWgMIEY (0.4 s top, 9.8 s bottom) and ePTZVwipoAM (24.2 s "yellow banner", 26.2 s): two a minute. slide_s = M78CO3Ybr7U date_stamp
  # and ePTZVwipoAM indus_war_tag (slide 0.3 s); hold_max_s = the longest reference banner
  # (bL3rUtUPYsc barabar_banner 2.0 s; the rest 0.8-1.7 s); words_max = the longest ones
  # ("ALWAYS WIN ON CUCAI'S PREDICTIONS", "INDUS VALLEY WAR 12TH CENTURY"). The cards give
  # size 0.85-0.9 of the width: the safe band (0.81) is the widest a banner may be. The
  # bar's height, type sizes and top_y are no card number: the 059 title strip's (the
  # Q2pquJ2FlzA header banner), gap_px the text pop's clearance.
  banner: {max_per_60s: 2, words_max: 5, slide_s: 0.3, hold_max_s: 2.0, top_y: 262,
           height_px: 104, gap_px: 24, size_px: 60, min_size_px: 36, fill: "#FFD60A",
           ink: "#111111", bar: "#E53935", bar_px: 10}
  transitions:
    fade: {duration_s: 0.35}
    whip: {duration_s: 0.22, blur_px: 14}
    zoom: {duration_s: 0.3, scale_from: 1.6}
    spring: {damping: 14, stiffness: 160, mass: 0.7}
    wipe: {duration_s: 0.25}
    flash: {duration_s: 0.3, color: "#FFD60A"}  # 060: the accent
  unique_assets_min_per_60s: 12
  unique_assets_max_per_60s: 23
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
  photo_look: "archival documentary photograph, natural light, film grain"
  illustration_look: "vintage editorial illustration, muted archival palette, visible brush texture"
  scene_mood: "grounded storytelling mood"
  scene_lighting: "soft natural daylight"
captions:
  font_family: Poppins
  font_weight: 800
  size_px: 74
  line_height: 1.35
  letter_spacing_px: 0.5
  anchor_y: 1460
  max_lines: 2
  max_width_px: 880
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
  bed_score_threshold: 0.5  # a tag hit scores 1, energy distance at most 0.4: one tag must match
  default_bed_query: calm ambient history documentary  # the bed search's last try (054)
  bed_query_anchor: music  # 069: every bed search rung carries it (Freesound adds tag:music)
  bed_db_under_voice: -14  # 056: run03 phone verdict "a bit loud, reduce by 30 %" = -3.1 dB
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
    bass: [stamp, reveal, header]
    drum: [money_reveal, finale_word]
    thump: [card_fly_in]
  cues_max_per_60s: 20
  cues_per_beat_max: 1
  cue_db_min: -10
  cue_db_max: -2
  forbidden: [sweep, riser, rumble_crescendo]
  # 070 (run04 QA, all styles): a soft mark only on a visible pop-in or transition, never
  # on every one (refs: ~6.7 sfx a minute against ~9.3 visual events, each synced to one)
  whoosh: {max_per_60s: 6, min_gap_s: 3.0, max_len_s: 0.8, "on": [fade, whip, zoom, spring, flash, pop]}  # "on" quoted: YAML reads a bare on as true
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
# Style: vishva
Desi history and story shorts in the operator's own Vishva Gyan manner (recipe 059): full-screen stills, dense overlays - words pinned on the picture, speech and thought bubbles, emoji stickers - and two pictures stacked top and bottom. Measured from the operator's Vishva Gyan shorts `FbaBcWgMIEY`, `ePTZVwipoAM` and `nBihHUlYOQk` (Tier B, proven on his audience). Every number traces to the recipe table in `styles/README.md` and to `docs/reference/inventory/`; every reference figure is ESTIMATED.

## Beat grammar
- Recipe: a shot every ~2.6 s (refs 3.2-4.9 shots per 10 s): keep the mean near `target_mean_s`. Enter a turn back to the presenter or a new section with `flash`.
- A beat is one contiguous span of the cut voice track with one presenter mode, one visual kind, one asset and at most one landed event; beats tile the runtime with no gaps (3.1). Propose boundaries in seconds; code snaps each to the nearest word end within `snap_window_s`, so never plan a cut mid-word.
- Keep the plan mean between `mean_min_s` and `mean_max_s`; set pieces (list, chart, split, wall, finale) may run to `set_piece_max_s`. Something must change on screen at least every `density_gap_max_s`.
- The short opens with the speaker's own first words (3.4 as amended by 055): the first sentence is `opening_beats_min`–`opening_beats_max` quick `opening_mode` beats over full-screen images of the main subject, the first `opening_beats_min` of them ending by `opening_max_s`. No line is lifted from elsewhere, no hook title, no hook cards, normal captions. The opening images are the short's strongest: the owner's reference first; else the best sourced image of the main subject (a named person or place under the 5.1/053 rules; a thing or idea from any source); else a generated image. The brief's hook wish steers what those images show, never the order of the voice.
- The cut removes only silence, breaths and dead air: every transcript word appears once, in the order it was spoken; `cut.drop` never covers a word. Code tightens any pause between two kept words longer than `cut.max_pause_s` and trims the head before the first word.
- Presenter modes are `full`, `pip`, `off` (3.2). Every `full` beat carries one reason tag from `full_reasons`; `full` beats are never consecutive and never more than `full_max_fraction` of the runtime. PIP runs up to `pip_max_run` beats are fine (the references ran six); `off` runs up to `off_max_run`.
- PIP framing: whole head plus neck/collar, chin at `chin_anchor` of the window, never a tight face crop (3.3).

## B-roll
- Recipe: full-screen stills are the base (`photo`); clips at most `clip_max_fraction` of the runtime. Overlays are dense, about 2.5 per 10 s (refs 1.5-5.7) across text pops, bubbles and stickers: a pop on each name, number or year as it is said, a bubble where the story quotes someone or asks a question, a sticker on a reaction. Use `split` for comparisons and pairs about a quarter of the runtime (refs 18-39 %): here it draws the two pictures stacked, top and bottom (`motion.split.layout`).
- Only kinds in `kinds` may be used; `tier2_kinds` is empty here, so parallax depth and vector-illustration looks are validation errors naming the nearest tier-1 substitute (4.1 as amended by 9.2). Every non-presenter beat has exactly one motion; there is never a static still.
- Label every non-presenter beat with `subject_kind` and a `query` plus a broader `query_fallback` (4.2): `entity` beats get a card or photo from owner references first, then search, then generation as the last resort, plus a lower-third; `concept` beats get a Ken Burns photo and a stamp of the key word; `number` and `quote` beats reuse the previous asset with a stamp and add nothing to the asset count; a `number` beat may instead carry a `counter` that counts up to the real figure and lands on it like a stamp, its digits written in `motion.counter.grouping`.
- Source order is owner references → web image search → Wikimedia Commons → Openverse → Pexels/Pixabay → generated illustration (5.1). Every image, whatever its source, is re-dressed the same way (5.1 and 5.3 as amended by 057): a portrait or square image asked as `photo` that covers the frame at no more than `full_bleed_max_upscale` is drawn full-screen under the Ken Burns, the PIP circle and the captions; an image that cannot cover the frame at that upscale is shown another way: cropped full-screen round a face (`crop_fill`), sharp over its own blurred copy (`backdrop`), as a dropped print (`polaroid`) or as the red-ringed archival `card`. Pick the `treatment` per image like an editor and vary it (103): never the same framed one on two beats in a row, the card at most `card_max_per_60s`; code draws another allowed one when the image cannot take the pick. Generated depictions of a named person or product are illustration-style (`illustration_look`); scenes and unnamed people may be photoreal (`photo_look`).
- Moving footage (4.1 and 5.1 as amended by 058): a `clip` beat is a full-screen stock video clip, always muted, under the PIP circle and the captions exactly like a `photo`, drawn at `motion.clip.speed` with the push in `motion.clip` (none here: the clip's own movement is the motion). Ask `clip` on concept beats — a thing, a kind of place, a process, nature, science ("cheese", "the sun", "the brain") — on the opening when the topic is a concept; and on a named place, era, event or object in any story, a person's included ("a 1950s oil field", "an old Arabian palace", "a plane taking off"); never for a named person, who keeps the still ladder (a stock stranger is never King Saud; 099). On an era beat, period-looking footage comes first; a timeless shot (desert, sea, sky, sand dunes) is fine and may take a light film or sepia grade; never modern cars, skylines, phones or present-day clothes standing in for the old era, then a still (099). Clips come from Pexels video, then Pixabay video, judged on their preview image like any candidate; a clip shorter than its beat is skipped, and a beat that finds no usable clip is drawn from the still ladder instead, logged. Clip beats take at most `clip_max_fraction` of the runtime. A clip counts as an image for `reuse_max`; a set piece's items and the finale's cards are stills, so they never name a clip beat's asset.
- Count unique assets, not beats: between `unique_assets_min_per_60s` and `unique_assets_max_per_60s` per minute, each reused at most `reuse_max` times (4.3). Reuse is encouraged for callbacks, payoffs and number beats; a short with no reused asset is a warning.
- The three set pieces carry their own content: a `list` beat gets a `set_piece_title` header and up to `motion.list.items_max` `items`, each with text and optionally an asset; a `split` beat gets a title strip plus exactly `motion.split.panes` items, one per side, each naming an asset and labelled with the words the strip highlights; a `wall` beat gets `motion.wall.cells_min` to `cells_max` items, each naming an asset. Item assets are ids other beats already source — a montage of the plan's pictures, never new ones (4.3).
- The two infographic kinds are drawn in code, never sourced as pictures of themselves (9.2, 9.3): a `chart` beat carries `chart_form` (bar, line or a two-value comparison), 2 to `motion.chart.marks_max` `series` points of `{label, value}` with the real numbers, the `value_unit` they are in and `set_piece_title` as its title strip — code writes the numbers in `motion.chart.grouping` and scales the axes. An `infographic` beat's own asset is a label-free base picture (the generator is told "no text, no labels") and its `labels` are 1 to `motion.infographic.labels_max` of `{text, x, y, anchor}` in percentages of that picture, flying in one after another (`label_flyin`); a label that would land outside the phone's safe area fails the build.
- A `map` beat is drawn from bundled map data, never sourced as a picture (9.3): it carries `map` with a `region` by name (a country, a state, "South Asia", or a city for a close-up) or a `bbox` of west, south, east, north degrees, 1 to `motion.map.markers_max` `markers` each `{name}` (write the place name; code looks the coordinate up and refuses a name it cannot find, so use the common English name), an optional `route` of two or more place names in order and an `object` (plane, ship or arrow) that travels it. The beat needs no `asset_id`. Its overlays are `pin_drop`, `route_arrow` (needs the route) and `object_path` (needs the route and the object).
- Transitions: `enter_transitions` only, at most `whip_max_per_3_beats` whip per three beats and never two whips in a row (9.4); the renderer draws each from `transitions` and refuses a name outside the list. Exit is always a cut, or a fade under a `fade` or `wipe` enter; the next beat's enter carries the motion. `flash` is enabled here (9.4 as amended by 060): it is a full-frame colour flash peaking on the cut, for a turn back to the presenter or a section change: at most `flash_max_per_60s` per minute and never on two consecutive beats; the PIP circle and the captions stay on top of it. Cards end above `card_max_bottom_y`; stamps stay in the top `stamp_max_y_fraction` of the frame; lower-thirds sit at y 1150–1240 and are suppressed under a two-line caption page (6.3).
- Text pops (4.1 as amended by 061; on here, at most `text_pops_max_per_60s` per minute): a `photo`, `card` or presenter-full beat carries `text_pops`, 1–4 bold words from the script pinned near the thing they name at `{x, y, anchor}` in percent of the frame, each landing on its spoken `word`, at most `motion.text_pop.max_per_beat` per beat; code keeps them inside the safe area, off the circle, the captions and any face.
- Bubbles (4.1 as amended by 063; on here, at most `bubbles_max_per_60s` per minute): a `photo`, `card` or presenter-full beat carries `bubbles`, each a `speech` or `thought` bubble of 1–`motion.bubble.words_max` words that the recording itself carries (what the speaker says someone said or thought, or his own question, shortened or in the caption language; `first`–`last` name the transcript words it came from), its tail pointing at `{x, y}` in percent of the frame — a person in the picture, or the PIP circle when the presenter is the one asking. At most `motion.bubble.max_per_beat` per beat; a dialogue pair's second bubble lands `dialogue_gap_min_s`–`dialogue_gap_max_s` after the first. Code keeps the body inside the safe area, off the captions, the circle, the stamp and any face (the tail points at it instead).
- Stickers (4.1 as amended by 062; on here, at most `stickers_max_per_60s` per minute): a `photo`, `card`, `clip` or presenter-full beat may carry one Fluent Emoji 3D sticker picked by an intent tag from the sticker catalogue, popping in on its spoken `word` and floating gently; above the speaker's circle when no `{x, y}` is given, else near the thing it reacts to. At most `motion.sticker.max_per_beat` per beat; code keeps it off the circle, the captions, the stamp and any face.
- Article highlights (4.1 as amended by 078; off here: `highlights_max_per_60s` is 0): where a style allows them, a `photo` or `card` beat that shows the owner's uploaded article or document screenshot (an owner reference; never a searched or generated page, never a made-up article) may carry one `highlight`: the `sentence` to mark as it reads on the screenshot and the transcript `words` that say it. A marker in `motion.highlight.color` at `motion.highlight.opacity` sweeps the sentence's lines left to right from the first word to the last while the screenshot, a straight card, pushes in toward them. Code finds the lines on the image; a sentence it cannot find is dropped and the beat stays.

## Captions
- The captions are the explainer's, number for number (run03: "subtitles perfect").
- Word-synced from the ASR word list only; the planner never touches word times (6.1). Pages hold `words_per_page` words, preferring `prefer`; never split a marked name or number run; break on segment punctuation and on inter-word gaps over `gap_break_s`.
- Return `keywords` as word indices in priority order (names, numbers, hidden-truth nouns and verbs, the final question word); code keeps at most `emphasis_max_ratio` of the words and one keyword per page.
- Typography is the reference look above (Poppins 800 at 74 px, white with dark outline, the active word in yellow, the keyword boxed); block bottom anchored at `anchor_y`, at most `max_lines` lines, above the platform safe area and touching the PIP bottom (6.2, 6.3). Verbatim in the spoken language; Latin script for English loanwords as the ASR returns them.

## Sound
- Recipe: SFX about 1.3 per 10 s - a tick on the overlays (a ding only on an idea sticker), a whoosh on a transition.
- Sound is the sound director's job (grill decision 7.1), not a fixed hit table: return a `sound_story` with a theme, a mood curve with build and drop points, a bed query (`theme`, `mood`, `energy`) and a per-beat cue list with intent labels; read the script and choose. Music and SFX come only from the tagged free library; never name a track.
- Bed target `bed_db_under_voice` dB under the voice, ducking at most `duck_max_db` dB, swells at most `swell_max_db` dB above target and drops at least `drop_min_db` dB below, every ramp at least `ramp_min_s` s. A drop is a step down at a beat boundary followed by a changeover cue, never a rise into a hit (7.3).
- The floor hits in `floor_hits` are derived by code from plan events so a short is never flat; the planner's cues layer on top within `cues_max_per_60s` and `cues_per_beat_max`, each between `cue_db_min` and `cue_db_max` dB under the voice. The cues are a closed palette (070): `tick` on a pop-in, `whoosh` on a non-cut transition or a pop-in, a soft `ding` only on an `idea` sticker, `bass`, `drum` and `thump` on landed events; the director adds ticks and whooshes itself within `sound.tick` and `sound.whoosh`, never on every event, and every file comes from the operator's approved library.
- Forbidden, checked in code on the SFX stem: `forbidden` (sweeps, risers, rumble crescendos); no ring, bell or chime is in the palette. No floor hit on whip cuts, punch-ins, rings or lower-thirds. Marks (7.3 as amended by 060 and 070, every style): a `whoosh` sits only on an enter `sound.whoosh.on` names or a pop-in, a `tick` only on a pop-in, a `ding` only on an `idea` sticker's pop-in, each within its row's `max_per_60s`, `min_gap_s` and `max_len_s`.
- When the library has no matching bed or SFX, code searches the free library with plain keywords from the bed query, then the mood alone, then `default_bed_query`, and adopts only CC0 / CC BY files that pass the sweep detector (7.2, 054); the planner still never names a track.
- Voice −19 LUFS / −3 dBTP on the stem, master −14 LUFS / −1.5 dBTP (7.3).

## Finale
- The last beat is `off`, `min_s`–`max_s` long: the payoff line plus a call-to-action card with the presenter in its centre circle and the short's first `motion.finale.cards` images (the opening's) around it, closing the loop; captions are hidden from the finale word onward. The finale word gets a drum floor hit.
