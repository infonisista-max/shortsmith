---
version: "20"
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
  opening_beats_min: 2
  opening_beats_max: 3
  opening_max_s: 6.0
presenter:
  modes: [full, pip, "off"]
  full_max_fraction: 0.4
  full_never_consecutive: false
  full_reasons: [emotional_line, argument_turn, setup, summary]
  pip_max_run: 8
  off_max_run: 3
  opening_mode: pip
  finale_mode: "off"
cut:
  max_pause_s: 0.8  # a teacher's pause is longer than an explainer's
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
  kinds: [photo, card, clip, stamp, lower_third, finale, presenter_full, presenter_pip,
          list, chart, split, map, infographic, pin_drop, route_arrow, label_flyin, counter]
  tier2_kinds: []
  motion:
    photo: {kind: ken_burns, scale_from: 1.04, scale_to: 1.08, alternate: true}
    card: {kind: push, scale_from: 1.1, scale_to: 1.25, border_px: 10, rotate_deg: 0.0,
           ring_color: "#1B7F79"}
    # 102: the local motion measure - frames sampled motion_fps a second at 64 px, the
    # mean grey change per step (0-1). A clip whose best window moves less than
    # motion_min is passed over (a still colour clip measures 0; the synthetic
    # testsrc2 1080x1920 0.0044-0.006; run05 b18, which read as a still, 0.009-0.035).
    clip: {kind: push, scale_from: 1.0, scale_to: 1.0, speed: 1.0, motion_fps: 4,
           motion_min: 0.004}  # 058
    stamp: {kind: fade, duration_s: 0.3, shake: false, palette: teal}
    lower_third: {kind: fade, duration_s: 0.35, top_y: 1150, bottom_y: 1240}
    finale: {kind: fade, duration_s: 0.5, cards: 3}
    text_pop: {kind: pop, duration_s: 0.22, hold_max_s: 2.5, max_per_beat: 2, tilt_deg: 3,
               size_px: 88, fill: "#FFD60A"}  # 061
    bubble: {kind: pop, duration_s: 0.22, hold_max_s: 3.0, max_per_beat: 2, words_max: 7,
             dialogue_gap_min_s: 0.7, dialogue_gap_max_s: 1.2, size_px: 54, min_size_px: 36,
             width_px: 640, fill: "#FFFFFF", ink: "#123B3A"}  # 063
    sticker: {kind: pop, duration_s: 0.22, hold_max_s: 2.5, max_per_beat: 1, size_px: 220,
              float_px: 8, float_period_s: 2.0}  # 062
    # 078: the marker over an owner's article screenshot - the accent at about 45 %,
    # padded round each text line; the screenshot card pushes to push_to about the lines.
    highlight: {kind: sweep, color: "#1B7F79", opacity: 0.45, pad_px: 8, push_to: 1.12}
    # 102: the light film grade on a clip or still the era judge found `timeless` (099): a
    # modern-looking shot made to sit in the period. The references' archival stills are
    # fully black and white (NKB b06, b12, b21 `bw`); a stand-in goes 60 % of the way
    # (saturate 0.4) with a warm cast and a touch of contrast.
    era_grade: {sepia: 0.3, saturate: 0.4, contrast: 1.05}
  enter_transitions: [cut, fade]
  whip_max_per_3_beats: 0
  flash_max_per_60s: 5  # 060: the cap where a style enables `flash`; never two in a row
  text_pops_max_per_60s: 0  # 061: off here
  bubbles_max_per_60s: 0  # 063: off here
  stickers_max_per_60s: 0  # 062: off here
  highlights_max_per_60s: 0  # 078: off here
  # 110b: the variety numbers (soft rules the editor repairs). clip_share_target: draft: the explainer's.
  clip_share_target: [0.05, 0.35]
  stamps_max_per_60s: 6  # draft: the explainer's
  non_cut_min_share: 0.7  # draft: the explainer's
  enter_run_max: 2  # the operator's rule (110): never the same enter three beats running
  transitions:
    fade: {duration_s: 0.35}
    whip: {duration_s: 0.22, blur_px: 14}
    zoom: {duration_s: 0.3, scale_from: 1.6}
    spring: {damping: 14, stiffness: 160, mass: 0.7}
    wipe: {duration_s: 0.25}
    flash: {duration_s: 0.3, color: "#FFFFFF"}  # 060: not enabled here
  unique_assets_min_per_60s: 8
  unique_assets_max_per_60s: 16
  reuse_max: 2  # 056: per image (one file, however many ids), carry-on beats and set pieces counted too (110b)
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
  max_width_px: 880
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
  default_bed_query: calm ambient piano  # the bed search's last try (054)
  bed_query_anchor: music  # 069: every bed search rung carries it (Freesound adds tag:music)
  bed_db_under_voice: -14
  bed_accept_db: [-15, -12]
  speech_band_hz: [250, 4000]
  speech_band_margin_db: 12
  speech_band_margin_max_db: 20  # 069, 088: screens unheard beds only (runtime fallbacks); an ear-approved bed over it plays with a note. Set from run04's bed, freesound_557546, a car exhaust, not music; 089 re-derives it
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
  forbidden: [sweep, riser, rumble_crescendo]
  # 070 (run04 QA, all styles): a soft mark only on a visible pop-in or transition, never
  # on every one (refs: ~6.7 sfx a minute against ~9.3 visual events, each synced to one)
  whoosh: {max_per_60s: 6, min_gap_s: 3.0, max_len_s: 0.8, "on": [fade, pop]}  # "on" quoted: YAML reads a bare on as true
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
- The short opens with the speaker's own first words (055): `opening_beats_min`–`opening_beats_max` `opening_mode` beats over full-screen images of the subject (owner reference first, then the best sourced or generated image); no cold open lifted from elsewhere, no title card, nothing dropped. The cut removes only silence, pauses tightened to `cut.max_pause_s`.
- Same tiling, snapping and no-mid-word rules as explainer (3.1).

## B-roll
- Diagrams, labelled images, step cards and simple process animations dominate; photos are calm Ken Burns, cards sit flat with no rotation.
- Sources and rights as in explainer (5.1); generated illustration is the flat diagram look in `illustration_look`.
- Moving footage as in explainer (058): a `clip` beat is a muted full-screen stock clip on a concept beat (a process, a phenomenon, a kind of place) or a named place, era, event or object, never a named person (099; on an era beat, period-looking footage comes first; a timeless shot (desert, sea, sky, sand dunes) is fine and may take a light film or sepia grade; never modern cars, skylines, phones or present-day clothes standing in for the old era, then a still (099)); within `clip_share_target` of the runtime (the top the ceiling), drawn at `motion.clip.speed` with no push.
- Fewer unique assets than explainer (`unique_assets_min_per_60s`–`unique_assets_max_per_60s`); reuse a diagram across the steps it explains.
- Transitions are `cut` and `fade` only (9.4); no whips, no flash (060). Variety (110b; soft, the editor repairs): at least `non_cut_min_share` of the beats after the first enter on something other than a cut, the same enter on at most `enter_run_max` beats running, and at most `stamps_max_per_60s` stamps a minute.
- Article highlights (4.1 as amended by 078; off here: `highlights_max_per_60s` is 0): where a style allows them, a `photo` or `card` beat that shows the owner's uploaded article or document screenshot (an owner reference; never a searched or generated page, never a made-up article) may carry one `highlight`: the `sentence` to mark as it reads on the screenshot and the transcript `words` that say it. A marker in `motion.highlight.color` at `motion.highlight.opacity` sweeps the sentence's lines left to right from the first word to the last while the screenshot, a straight card, pushes in toward them. Code finds the lines on the image; a sentence it cannot find is dropped and the beat stays.

## Captions
- Full short sentences of `words_per_page` words, neutral typography, no active-word pop; the key term is boxed in the accent colour. Same anchor, safe area and two-line limit as explainer (6.3).

## Sound
- Soft ambient bed `bed_db_under_voice` dB under the voice; a soft tick only on a pop-in, a short whoosh only on a fade (070). Forbidden: `forbidden`, checked on the SFX stem; a soft tick on a pop-in and a short whoosh on a transition, within `sound.tick` and `sound.whoosh` (070).

## Finale
- One-line recap card, `min_s`–`max_s` s, no call to action.
