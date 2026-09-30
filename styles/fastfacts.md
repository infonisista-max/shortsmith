---
version: "12"
status: shipped
aliases: [fastfacts, fast facts, facts, fact, quick]
requires_components: [captions, pip, photo, card, clip, stamp, lower_third, finale, list,
                      chart, split, wall, infographic, label_flyin, counter, map,
                      pin_drop, route_arrow, object_path,
                      cut, fade, whip, zoom, spring, wipe, flash,
                      text_pop, title_strip]
beats:
  min_s: 0.5
  max_s: 3.0
  set_piece_max_s: 4.0
  target_mean_s: 1.2
  mean_min_s: 0.9
  mean_max_s: 1.5
  density_gap_max_s: 1.0
  snap_window_s: 0.15
  opening_beats_min: 2
  opening_beats_max: 3
  opening_max_s: 5.0
presenter:
  modes: [full, pip, "off"]
  full_max_fraction: 0.25
  full_never_consecutive: true
  full_reasons: [emotional_line, argument_turn]
  pip_max_run: 12
  off_max_run: 6
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
    clip: {kind: push, scale_from: 1.0, scale_to: 1.0, speed: 1.0}
    stamp: {kind: land, duration_s: 0.16, shake: true, palette: yellow_green_red}
    lower_third: {kind: fade, duration_s: 0.35, top_y: 1150, bottom_y: 1240}
    finale: {kind: fade, duration_s: 0.35, cards: 3}
    list: {kind: reveal, items_max: 6, duration_s: 0.35, scale_from: 1.15, scale_to: 1.25,
           dim: 0.45}
    split: {kind: slide, panes: 2, duration_s: 0.30}
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
  enter_transitions: [cut, fade, whip, zoom, spring, flash]
  whip_max_per_3_beats: 1
  flash_max_per_60s: 5  # 060: never two in a row (refs: at most 4 a minute)
  text_pops_max_per_60s: 10  # 061
  bubbles_max_per_60s: 0  # 063
  stickers_max_per_60s: 0  # 062
  highlights_max_per_60s: 0  # 078: off here
  clip_max_fraction: 0.7  # 058: the runtime share clips may take
  transitions:
    fade: {duration_s: 0.35}
    whip: {duration_s: 0.22, blur_px: 14}
    zoom: {duration_s: 0.3, scale_from: 1.6}
    spring: {damping: 14, stiffness: 160, mass: 0.7}
    wipe: {duration_s: 0.25}
    flash: {duration_s: 0.3, color: "#FFD60A"}  # 060: the accent
  unique_assets_min_per_60s: 25
  unique_assets_max_per_60s: 50
  reuse_max: 2  # 056: per image (one file, however many ids), carry-on beats and set pieces aside
  rescued_max_per_60s: 8
  full_bleed_max_upscale: 2.0  # 057: a portrait covering the frame at <= this is full-screen, any origin
  card_max_bottom_y: 1240
  stamp_max_y_fraction: 0.6
  photo_look: "crisp documentary photograph, natural light, high clarity"
  illustration_look: "vintage editorial illustration, muted archival palette, visible brush texture"
  scene_mood: "quick, curious mood"
  scene_lighting: "bright natural daylight"
  # 059: the fixed title strip at the top for the whole short (Q2pquJ2FlzA, VSJzviqMO7k)
  title_strip: {words_max: 5, top_y: 262, height_px: 104, size_px: 60, min_size_px: 36,
                fill: "#FFD60A", ink: "#111111", duration_s: 0.3}
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
  default_bed_query: upbeat curious electronic  # the bed search's last try (054)
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
  cues_max_per_60s: 24
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
  judge_max_calls: 80
  search_max_queries: 120
  gen_max_per_short: 8
palette:
  gradient: ["#0B1D3A", "#1F3B73"]
  angle_deg: 160
  accent: "#FFD60A"
---
# Style: fastfacts
Rapid-fire fact shorts (recipe 059): a new shot every ~1.2 s over moving clips and full-screen stills, a fixed title strip naming the topic at the top for the whole short, and a text pop on every number. Measured from NeelFacts `Q2pquJ2FlzA` and FactTechz `zXK42RMPKUY`. Every number traces to the recipe table in `styles/README.md` and to `docs/reference/inventory/`; every reference figure is ESTIMATED.

## Beat grammar
- Recipe: a shot every ~1.2 s (refs 7.0-9.3 shots per 10 s): beats from `min_s` up, the mean between `mean_min_s` and `mean_max_s`; runs of `pip` beats may reach `pip_max_run` at this pace. Write `title_strip`: the topic in at most `broll.title_strip.words_max` words; code draws it at the top of the frame for the whole short, the finale aside.
- A beat is one contiguous span of the cut voice track with one presenter mode, one visual kind, one asset and at most one landed event; beats tile the runtime with no gaps (3.1). Propose boundaries in seconds; code snaps each to the nearest word end within `snap_window_s`, so never plan a cut mid-word.
- Keep the plan mean between `mean_min_s` and `mean_max_s`; set pieces (list, chart, split, wall, finale) may run to `set_piece_max_s`. Something must change on screen at least every `density_gap_max_s`.
- The short opens with the speaker's own first words (3.4 as amended by 055): the first sentence is `opening_beats_min`–`opening_beats_max` quick `opening_mode` beats over full-screen images of the main subject, the first `opening_beats_min` of them ending by `opening_max_s`. No line is lifted from elsewhere, no hook title, no hook cards, normal captions. The opening images are the short's strongest: the owner's reference first; else the best sourced image of the main subject (a named person or place under the 5.1/053 rules; a thing or idea from any source); else a generated image. The brief's hook wish steers what those images show, never the order of the voice.
- The cut removes only silence, breaths and dead air: every transcript word appears once, in the order it was spoken; `cut.drop` never covers a word. Code tightens any pause between two kept words longer than `cut.max_pause_s` and trims the head before the first word.
- Presenter modes are `full`, `pip`, `off` (3.2). Every `full` beat carries one reason tag from `full_reasons`; `full` beats are never consecutive and never more than `full_max_fraction` of the runtime. PIP runs up to `pip_max_run` beats are fine (the references ran six); `off` runs up to `off_max_run`.
- PIP framing: whole head plus neck/collar, chin at `chin_anchor` of the window, never a tight face crop (3.3).

## B-roll
- Recipe: clips up to `clip_max_fraction` of the runtime on concept beats, full-screen stills otherwise. A text pop on every number as it is said. Asset counts are scaled to the pace (`unique_assets_min_per_60s`-`unique_assets_max_per_60s`), each image reused at most `reuse_max` times.
- Only kinds in `kinds` may be used; `tier2_kinds` is empty here, so parallax depth and vector-illustration looks are validation errors naming the nearest tier-1 substitute (4.1 as amended by 9.2). Every non-presenter beat has exactly one motion; there is never a static still.
- Label every non-presenter beat with `subject_kind` and a `query` plus a broader `query_fallback` (4.2): `entity` beats get a card or photo from owner references first, then search, then generation as the last resort, plus a lower-third; `concept` beats get a Ken Burns photo and a stamp of the key word; `number` and `quote` beats reuse the previous asset with a stamp and add nothing to the asset count; a `number` beat may instead carry a `counter` that counts up to the real figure and lands on it like a stamp, its digits written in `motion.counter.grouping`.
- Source order is owner references → web image search → Wikimedia Commons → Openverse → Pexels/Pixabay → generated illustration (5.1). Every image, whatever its source, is re-dressed the same way (5.1 and 5.3 as amended by 057): a portrait or square image asked as `photo` that covers the frame at no more than `full_bleed_max_upscale` is drawn full-screen under the Ken Burns, the PIP circle and the captions; a landscape image, or one that cannot cover the frame at that upscale, is drawn as a card. Ask `photo` wherever a full-screen image would serve; code draws the card when the image cannot fill the frame. Generated depictions of a named person or product are illustration-style (`illustration_look`); scenes and unnamed people may be photoreal (`photo_look`).
- Moving footage (4.1 and 5.1 as amended by 058): a `clip` beat is a full-screen stock video clip, always muted, under the PIP circle and the captions exactly like a `photo`, drawn at `motion.clip.speed` with the push in `motion.clip` (none here: the clip's own movement is the motion). Ask `clip` on concept beats — a thing, a kind of place, a process, nature, science ("cheese", "the sun", "the brain") — on the opening when the topic is a concept; and on a named place, era, event or object in any story, a person's included ("a 1950s oil field", "an old Arabian palace", "a plane taking off"); never for a named person, who keeps the still ladder (a stock stranger is never King Saud; 099). On an era beat, period-looking footage comes first; a timeless shot (desert, sea, sky, sand dunes) is fine and may take a light film or sepia grade; never modern cars, skylines, phones or present-day clothes standing in for the old era, then a still (099). Clips come from Pexels video, then Pixabay video, judged on their preview image like any candidate; a clip shorter than its beat is skipped, and a beat that finds no usable clip is drawn from the still ladder instead, logged. Clip beats take at most `clip_max_fraction` of the runtime. A clip counts as an image for `reuse_max`; a set piece's items and the finale's cards are stills, so they never name a clip beat's asset.
- Count unique assets, not beats: between `unique_assets_min_per_60s` and `unique_assets_max_per_60s` per minute, each reused at most `reuse_max` times (4.3). Reuse is encouraged for callbacks, payoffs and number beats; a short with no reused asset is a warning.
- The three set pieces carry their own content: a `list` beat gets a `set_piece_title` header and up to `motion.list.items_max` `items`, each with text and optionally an asset; a `split` beat gets a title strip plus exactly `motion.split.panes` items, one per side, each naming an asset and labelled with the words the strip highlights; a `wall` beat gets `motion.wall.cells_min` to `cells_max` items, each naming an asset. Item assets are ids other beats already source — a montage of the plan's pictures, never new ones (4.3).
- The two infographic kinds are drawn in code, never sourced as pictures of themselves (9.2, 9.3): a `chart` beat carries `chart_form` (bar, line or a two-value comparison), 2 to `motion.chart.marks_max` `series` points of `{label, value}` with the real numbers, the `value_unit` they are in and `set_piece_title` as its title strip — code writes the numbers in `motion.chart.grouping` and scales the axes. An `infographic` beat's own asset is a label-free base picture (the generator is told "no text, no labels") and its `labels` are 1 to `motion.infographic.labels_max` of `{text, x, y, anchor}` in percentages of that picture, flying in one after another (`label_flyin`); a label that would land outside the phone's safe area fails the build.
- A `map` beat is drawn from bundled map data, never sourced as a picture (9.3): it carries `map` with a `region` by name (a country, a state, "South Asia", or a city for a close-up) or a `bbox` of west, south, east, north degrees, 1 to `motion.map.markers_max` `markers` each `{name}` (write the place name; code looks the coordinate up and refuses a name it cannot find, so use the common English name), an optional `route` of two or more place names in order and an `object` (plane, ship or arrow) that travels it. The beat needs no `asset_id`. Its overlays are `pin_drop`, `route_arrow` (needs the route) and `object_path` (needs the route and the object).
- Transitions: `enter_transitions` only, at most `whip_max_per_3_beats` whip per three beats and never two whips in a row (9.4); the renderer draws each from `transitions` and refuses a name outside the list. Exit is always a cut, or a fade under a `fade` or `wipe` enter; the next beat's enter carries the motion. `flash` is enabled here (9.4 as amended by 060): it is a full-frame colour flash peaking on the cut, for a turn back to the presenter or a section change: at most `flash_max_per_60s` per minute and never on two consecutive beats; the PIP circle and the captions stay on top of it. Cards end above `card_max_bottom_y`; stamps stay in the top `stamp_max_y_fraction` of the frame; lower-thirds sit at y 1150–1240 and are suppressed under a two-line caption page (6.3).
- Text pops (4.1 as amended by 061; on here, at most `text_pops_max_per_60s` per minute): a `photo`, `card` or presenter-full beat carries `text_pops`, 1–4 bold words from the script pinned near the thing they name at `{x, y, anchor}` in percent of the frame, each landing on its spoken `word`, at most `motion.text_pop.max_per_beat` per beat; code keeps them inside the safe area, off the circle, the captions and any face.
- Bubbles (4.1 as amended by 063): off here, `bubbles_max_per_60s` is 0. Where a style allows them, a `photo`, `card` or presenter-full beat carries `bubbles`, each a `speech` or `thought` bubble of 1–`motion.bubble.words_max` words that the recording itself carries (what the speaker says someone said or thought, or his own question, shortened or in the caption language; `first`–`last` name the transcript words it came from), its tail pointing at `{x, y}` in percent of the frame — a person in the picture, or the PIP circle when the presenter is the one asking. At most `motion.bubble.max_per_beat` per beat; a dialogue pair's second bubble lands `dialogue_gap_min_s`–`dialogue_gap_max_s` after the first. Code keeps the body inside the safe area, off the captions, the circle, the stamp and any face (the tail points at it instead).
- Stickers (4.1 as amended by 062): off here, `stickers_max_per_60s` is 0.
- Article highlights (4.1 as amended by 078; off here: `highlights_max_per_60s` is 0): where a style allows them, a `photo` or `card` beat that shows the owner's uploaded article or document screenshot (an owner reference; never a searched or generated page, never a made-up article) may carry one `highlight`: the `sentence` to mark as it reads on the screenshot and the transcript `words` that say it. A marker in `motion.highlight.color` at `motion.highlight.opacity` sweeps the sentence's lines left to right from the first word to the last while the screenshot, a straight card, pushes in toward them. Code finds the lines on the image; a sentence it cannot find is dropped and the beat stays.

## Captions
- The captions are the explainer's, number for number (run03: "subtitles perfect").
- Word-synced from the ASR word list only; the planner never touches word times (6.1). Pages hold `words_per_page` words, preferring `prefer`; never split a marked name or number run; break on segment punctuation and on inter-word gaps over `gap_break_s`.
- Return `keywords` as word indices in priority order (names, numbers, hidden-truth nouns and verbs, the final question word); code keeps at most `emphasis_max_ratio` of the words and one keyword per page.
- Typography is the reference look above (Poppins 800 at 74 px, white with dark outline, the active word in yellow, the keyword boxed); block bottom anchored at `anchor_y`, at most `max_lines` lines, above the platform safe area and touching the PIP bottom (6.2, 6.3). Verbatim in the spoken language; Latin script for English loanwords as the ASR returns them.

## Sound
- Recipe: SFX about 1.2 per 10 s; a whoosh on a transition, a tick on a pop-in.
- Sound is the sound director's job (grill decision 7.1), not a fixed hit table: return a `sound_story` with a theme, a mood curve with build and drop points, a bed query (`theme`, `mood`, `energy`) and a per-beat cue list with intent labels; read the script and choose. Music and SFX come only from the tagged free library; never name a track.
- Bed target `bed_db_under_voice` dB under the voice, ducking at most `duck_max_db` dB, swells at most `swell_max_db` dB above target and drops at least `drop_min_db` dB below, every ramp at least `ramp_min_s` s. A drop is a step down at a beat boundary followed by a changeover cue, never a rise into a hit (7.3).
- The floor hits in `floor_hits` are derived by code from plan events so a short is never flat; the planner's cues layer on top within `cues_max_per_60s` and `cues_per_beat_max`, each between `cue_db_min` and `cue_db_max` dB under the voice. The cues are a closed palette (070): `tick` on a pop-in, `whoosh` on a non-cut transition or a pop-in, a soft `ding` only on an `idea` sticker, `bass`, `drum` and `thump` on landed events; the director adds ticks and whooshes itself within `sound.tick` and `sound.whoosh`, never on every event, and every file comes from the operator's approved library.
- Forbidden, checked in code on the SFX stem: `forbidden` (sweeps, risers, rumble crescendos); no ring, bell or chime is in the palette. No floor hit on whip cuts, punch-ins, rings or lower-thirds. Marks (7.3 as amended by 060 and 070, every style): a `whoosh` sits only on an enter `sound.whoosh.on` names or a pop-in, a `tick` only on a pop-in, a `ding` only on an `idea` sticker's pop-in, each within its row's `max_per_60s`, `min_gap_s` and `max_len_s`.
- When the library has no matching bed or SFX, code searches the free library with plain keywords from the bed query, then the mood alone, then `default_bed_query`, and adopts only CC0 / CC BY files that pass the sweep detector (7.2, 054); the planner still never names a track.
- Voice −19 LUFS / −3 dBTP on the stem, master −14 LUFS / −1.5 dBTP (7.3).

## Finale
- The last beat is `off`, `min_s`–`max_s` long: the payoff line plus a call-to-action card with the presenter in its centre circle and the short's first `motion.finale.cards` images (the opening's) around it, closing the loop; captions are hidden from the finale word onward. The finale word gets a drum floor hit.
