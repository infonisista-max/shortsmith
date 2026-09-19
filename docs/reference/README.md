# Reference pack — the editing bar

Two owner-approved shorts from the old engine define what "done" looks like for
Shortsmith. Everything the planner and renderer produce is judged against them.
The videos and frames are git-ignored under `work/reference/`; this README is
the only committed part and contains the commands to regenerate the frames.

## The bar

GLOBAL (every style): editing at the level of top YouTube Shorts (Dhruv
Rathee-style, CapCut-level polish); every third-party asset carries a licence
tag or is disclosed as AI; sound follows the fact-channel profile below;
Shubham's phone verdict against these references is the final judge.

Measured from the two references (STYLE:explainer; other styles set their own
numbers in `styles/`): a 1080x1920, 30 fps explainer of up to 60 s
(references: 57–60 s, 22–26 beats) with contiguous beats averaging 2.3 to
2.6 s, where a new visual event lands at least every 1.5 s and the presenter
is full-frame for no more than about 25 % of the runtime. Roughly two thirds
of the time the presenter lives in a 300 px circle at bottom-left over a still
that is always moving (Ken Burns, 1.0 to about 1.2 scale) and is annotated by
one landed event per beat: a rotated stamp, a red ring on an archival card, a
lower-third label, or a set-piece (hook cards, list, chart, split, wall,
finale). Captions are Poppins 74 px weight 800, 2 to 4 words per page, active
word yellow, keywords boxed, held above the PIP and hidden before the finale
word. Sound is a quiet minor-key bed 9 to 12 dB under voice, at most 16 short
hits on stamps, reveals and headers, nothing on cuts, no noise sweeps, master
−14 LUFS / −1.5 dBTP.

## The two references

### NeemKaroliBaba_Short_v4.mp4 (60.0 s, 26 beats)

What it does well:
- Shows every set-piece kind the engine had: hook cards, list, chart drawn in
  code, split screen with a travelling dot, wall, cutout presenter, finale.
- Tight rhythm: mean beat 2.31 s, shortest 0.68 s, presenter full-frame only
  12.4 % of runtime. Presenter never appears full-frame twice in a row.
- Callbacks: the tantra fire still and the red cross stamp return at 52.6 s to
  close the loop opened at 5.3 s. The finale reuses the five hook faces.
- Asset discipline: 14 Wikimedia stills with licence tags in the filename,
  6 owner-supplied, 8 AI stills disclosed as such.
- The v3 owner note that defined the PIP rule: whole head including hair plus
  neck and collar, "good view, not just face".

### DysonToothbrush_Short_v1.mp4 (57.5 s, 22 beats)

What it does well:
- Archival-card pattern at its cleanest: press photo in a white frame, caption
  strip, slow push in, red ring that lands 0.2 to 2.7 s after the beat starts.
- Product stills carry the story: owner-supplied press images are reused
  across hook, reveal, dock, hero and finale so the object stays recognisable.
- Stamps as the emotional beat: yellow price stamp at the reveal, green tick
  for the payoff, red cross for the counter-argument, yellow "status" and
  "100%" for the punchline.
- Headers over full-frame presenter for the turn of the argument (30.3 s).
- Its v2 sound revision is the adopted chain; the picture is v1, unchanged.

## Evidence

- `work/beat-tables.md` — every beat of both shorts: times, presenter mode,
  kind, motion, asset, licence, stamps, rings, labels. Computed stats at the
  bottom.
- `work/old-engine/engine/vg-short_source_2026-09-08/vg-short/src/remotion/plan.ts`
  lines 35–84 — the NKB `BEATS` array (served v1 to v4). Read only; never
  execute anything under `work/old-engine`.
- `work/old-engine/08_JOB_RECORDS/DysonToothbrush/plan_v1.ts` lines 62–128 —
  the Dyson `BEATS` array (final picture).
- `research.md` section 2 (presenter, PIP, beat stats), section 4 (captions),
  section 5 (sound chain), section 12 (prototype findings and the
  Remotion-for-visuals, ffmpeg-for-audio verdict).
- `styles/explainer.md` — the style spec both references belong to.

## Fact-channel sound profile (research.md section 5)

Adopted from Dyson v2 after the owner's v1 note: "the sound effects and
background music give a very artificial feel, not a fact-based-channel feel …
only the sound effects need to be updated".

- Voice stem: mono downmix, high-pass 80 Hz, compressor −18 dB ratio 2.5,
  two-pass loudnorm to −19 LUFS / −3 dBTP. Do the mono fold inside the filter
  graph, not with `-ac 1` (that landed the stem 3.6 dB low).
- Bed: minor key, static harmony, about 15 % percussive, no vocals. Target
  −11 dB against voice RMS while speaking, acceptance band −9 to −12 dB.
  Sidechain ducking ratio 2, at most 4 dB of duck. Fade in 0.6 s, out 1.2 s.
  Offset the track so its drop lands on the first stamp.
- Hits: 16 cues total, down from 45. Short bass hit about 5 dB under voice on
  stamps, reveals and headers. Hard drum hit 2 to 3 dB under on the money
  reveal and the finale word. Channel thump 8 to 10 dB under on card fly-ins.
  Nothing on whip cuts, punch-ins, rings or lower thirds. No ticks, pops,
  bells, chimes or heartbeats. (Hit placement is research.md open item 3 —
  the brief says reveals only; the PRD decides.)
- Banned: any rising or falling broadband-noise envelope. Whooshes, swishes,
  risers, air transitions, rumble crescendos, reverse cymbals.
- Master: −14 LUFS, −1.5 dBTP ceiling, limiter 0.891. Speech band 250 Hz to
  4 kHz at least 20 dB above the bed. Stems for voice, music and SFX written
  alongside the mix so balance can be measured.

## Patterns on record beyond the two references

Added 19 Sep 2026 from the grill (decision 5.2). Not evidenced by the NKB or
Dyson frames; recorded here so the `card` kind grows toward it.

### News-card composite (Startuppedia style)

The re-dress that makes raw web-sourced portraits look professional. For a
two-entity beat (two people, a person and a company, two products):
- Two portraits side by side inside one framed card, equal height, each
  cropped to head plus collar, thin divider or seam between them.
- A circular logo badge (company, channel or subject mark) overlapping one
  corner of the card, white ring, drop shadow.
- A title strip along the bottom of the card: bold sans, two to six words,
  key words highlighted in the style's accent colour on a box.
- Card obeys the archival-card rules: white border, slight rotate, blurred
  darkened cover behind, slow push in, sits above the caption line.

Card-kind support required: 2-up composite, badge overlay, highlight strip.
Tier 2 if it does not fit day 14, but on record now.

## Frames

Stored in `work/reference/frames/` (git-ignored), 540x960 JPEG, all under
100 KB. Picked by coverage: every beat kind and presenter mode has a frame,
the rest go to beats with a landed event. Timestamp is beat start + 0.5 s so
the 7-frame enter transition has finished, or event time + 0.3 s where the
beat has a stamp or ring, never later than 0.2 s before beat end.

### NKB

| # | File | Beat | t (s) | What it shows |
|---|---|---|---|---|
| 1 | nkb_01_b01_presenter_open_0.60s.jpg | b01 | 0.60 | Full-frame cold open mid punch-in, first caption page with yellow keyword box |
| 2 | nkb_02_b02_hook_cards_2.30s.jpg | b02 | 2.30 | Hook: three labelled Wikimedia cards sprung in from three sides under the big title, presenter off |
| 3 | nkb_03_b04_tantra_6.70s.jpg | b04 | 6.70 | PIP circle bottom-left over an AI fire still, red cross stamp landed at a tilt |
| 4 | nkb_04_b09_list_20.20s.jpg | b09 | 20.20 | List set-piece: header plus three of four items with icons over a dimmed Ken Burns base |
| 5 | nkb_05_b11_jobs_26.40s.jpg | b11 | 26.40 | Plain lower-third label (name and role) under a slow-zoom portrait with PIP |
| 6 | nkb_06_b12_jobs_desk_28.10s.jpg | b12 | 28.10 | Archival card: black and white photo in a white frame, caption strip, red ring on the detail |
| 7 | nkb_07_b13_fbchart_32.30s.jpg | b13 | 32.30 | Chart drawn in code, line turned red with the problem callout, PIP overlapping the chart edge |
| 8 | nkb_08_b15_split_journey_35.30s.jpg | b15 | 35.30 | Split screen, two place labels, dashed arc with the travelling dot crossing the seam |
| 9 | nkb_09_b17_wall_40.00s.jpg | b17 | 40.00 | Wall: three labelled cards flown in alternating sides over a dimmed temple still |
| 10 | nkb_10_b23_cutout_think_51.80s.jpg | b23 | 51.80 | Cutout presenter mode over a dimmed AI interior, no circle |
| 11 | nkb_11_b25_finale_59.20s.jpg | b25 | 59.20 | Finale: yellow-ringed centre circle, five cards, the question word, captions hidden |

### Dyson

| # | File | Beat | t (s) | What it shows |
|---|---|---|---|---|
| 1 | dyson_01_b01_presenter_open_0.70s.jpg | b01 | 0.70 | Full-frame cold open, punch-in at 1.16, tight framing that led to the PIP head-room rule |
| 2 | dyson_02_b02_hook_cards_2.60s.jpg | b02 | 2.60 | Hook: three press-image cards, two-line price question title with yellow keyword |
| 3 | dyson_03_b03_reveal_price_5.60s.jpg | b03 | 5.60 | Reveal: hero still zooming out, yellow price stamp top-right, presenter off |
| 4 | dyson_04_b04_dyson_launch_10.10s.jpg | b04 | 10.10 | Archival card plus lower-third label plus red ring, three annotations on one beat |
| 5 | dyson_05_b06_camera_card_14.60s.jpg | b06 | 14.60 | Archival card at 16:9 with caption strip and ring on the camera label |
| 6 | dyson_06_b10_hidden_gap_23.50s.jpg | b10 | 23.50 | Red ring on an AI macro still, PIP, two-word caption page |
| 7 | dyson_07_b12_dock_clean_28.30s.jpg | b12 | 28.30 | Green tick stamp for the payoff over the product dock still |
| 8 | dyson_08_b14_presenter_india_31.50s.jpg | b14 | 31.50 | Full-frame presenter with a two-line header for the turn of the argument |
| 9 | dyson_09_b17_iphone_status_41.90s.jpg | b17 | 41.90 | Label bottom-left plus yellow "status" stamp on a Wikimedia still |
| 10 | dyson_10_b22_finale_55.60s.jpg | b22 | 55.60 | Finale: hero in the centre circle, three press cards, the question word |

### Regenerating the frames

From the repo root with the two mp4s in `work/reference/`:

```sh
mkdir -p work/reference/frames
f() { ffmpeg -v error -y -ss "$3" -i "work/reference/$1" -frames:v 1 \
      -vf scale=540:960 -q:v 5 "work/reference/frames/$2"; }
N=NeemKaroliBaba_Short_v4.mp4
f $N nkb_01_b01_presenter_open_0.60s.jpg 0.60
f $N nkb_02_b02_hook_cards_2.30s.jpg 2.30
f $N nkb_03_b04_tantra_6.70s.jpg 6.70
f $N nkb_04_b09_list_20.20s.jpg 20.20
f $N nkb_05_b11_jobs_26.40s.jpg 26.40
f $N nkb_06_b12_jobs_desk_28.10s.jpg 28.10
f $N nkb_07_b13_fbchart_32.30s.jpg 32.30
f $N nkb_08_b15_split_journey_35.30s.jpg 35.30
f $N nkb_09_b17_wall_40.00s.jpg 40.00
f $N nkb_10_b23_cutout_think_51.80s.jpg 51.80
f $N nkb_11_b25_finale_59.20s.jpg 59.20
D=DysonToothbrush_Short_v1.mp4
f $D dyson_01_b01_presenter_open_0.70s.jpg 0.70
f $D dyson_02_b02_hook_cards_2.60s.jpg 2.60
f $D dyson_03_b03_reveal_price_5.60s.jpg 5.60
f $D dyson_04_b04_dyson_launch_10.10s.jpg 10.10
f $D dyson_05_b06_camera_card_14.60s.jpg 14.60
f $D dyson_06_b10_hidden_gap_23.50s.jpg 23.50
f $D dyson_07_b12_dock_clean_28.30s.jpg 28.30
f $D dyson_08_b14_presenter_india_31.50s.jpg 31.50
f $D dyson_09_b17_iphone_status_41.90s.jpg 41.90
f $D dyson_10_b22_finale_55.60s.jpg 55.60
```

If any frame exceeds 150 KB, raise `-q:v` one step for that file and retry.
