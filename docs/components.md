# Renderer components

The registry is `src/remotion/registry.json` (decision 9.2): the component names the Node
project exports, which `styles.load_all` checks every shipped spec's `requires_components`
against. This table is the maintained status per component, the one the day-14 gate
(ticket 047) reads: `implemented` means the registry exports it and a smoke render draws
it; `incomplete` carries the one-line reason.

The two smoke columns record what the fixture render exercised under each style, read
off `work/render_spec.json` of the run (ticket 048: `python -m shortsmith.smoke --style
hitech`; the plain command renders `explainer`). "b0N" is the fake plan's beat that drew
it. A blank cell means the style does not enable that component.

| component | tier | status | explainer smoke | hitech smoke | note |
| --- | --- | --- | --- | --- | --- |
| `captions` | 1 | implemented | 5 pages | 5 pages | hitech: Poppins 700 at 70 px, cyan active word |
| `pip` | 1 | implemented | b01, b02, b04, b07, b09 | b01, b02, b04, b07, b09 | hitech: 4 px cyan ring at y 970; 055: the opening beats b01 and b02 are pip over full-screen images |
| `photo` | 1 | implemented | b01 | b01 | Ken Burns from `broll.motion.photo`; b01 opens the short (055); b04's still became the clip (058) |
| `card` | 1 | implemented | b02 | b02 | hitech: flat card, 2 px border, no tilt; 058: b02 is planned as the card (the India Gate landscape), b04 became the clip |
| `clip` | 1 | implemented | b04 | b04 | 058: a full-screen muted stock video clip drawn in the photo's layer under the circle and the captions, played at `broll.motion.clip.speed` with no push; the smoke's fake clip source answers b04's concept query with a 3 s synthetic `testsrc2` clip; never on a named entity (the still ladder keeps those) |
| `stamp` | 1 | implemented | b04 | b04 | hitech: `cyan_white` palette, no shake |
| `lower_third` | 1 | implemented | none drawn | none drawn | b02's card strip carries the label, so the standalone overlay is not exercised by the fixture plan |
| `hook_cards` | retired | retired (055) |  |  | no longer a tier-1 kind: the short opens with the speaker's first words over images, no title card; the Node component stays exported until it is removed with its registry test |
| `finale` | 1 | implemented | b11 | b11 | hitech: `spec_summary_card` kind, same component; 055: its cards are the short's first three distinct images |
| `list` | 1 | implemented | b08 | b08 | over the dimmed base still |
| `chart` | 1 | implemented | b06 | b06 | drawn from the series, never sourced |
| `split` | 1 | implemented | b09 | b09 | two panes, badge, highlighted title strip; 059: `motion.split.layout: stacked` (vishva) draws the two pictures top and bottom with the title band between, the card running from under the top zone to `card_max_bottom_y`, under the PIP circle |
| `wall` | 1 | implemented | b10 | b10 | 2x2 grid over the dimmed base still |
| `infographic` | 1 | implemented | b07 | b07 | label-free base under the labels |
| `label_flyin` | 1 | implemented | b07 | b07 | labels fly in one after another |
| `counter` | 1 | implemented | b06 | b06 | counts to 12 words, lands in the stamp's time |
| `map` | 1 | implemented | b05 | b05 | bundled geodata, fake-geocoded markers; hitech: dark land, cyan coast |
| `pin_drop` | 1 | implemented | b05 | b05 | markers drop in on a stagger with a spring settle, label pops after the landing (028) |
| `route_arrow` | 1 | implemented | b05 | b05 | Delhi to Mumbai draws on with an arrowhead at the tip, after the pins (028) |
| `object_path` | 1 | implemented | b05 | b05 | the plane sprite flies the route heading along the tangent, after the draw-on (028) |
| `cut` | transition | implemented | b01, b04, b06, b07, b10, b11 | b01, b04, b06, b07, b10, b11 | the default enter |
| `fade` | transition | implemented | b03, b05 | b03, b05 | 0.35 s |
| `whip` | transition | implemented | b02 |  | hitech does not enable it; the fake swaps it for a wipe |
| `zoom` | transition | implemented | b09 | b08, b09 | 0.3 s from 1.6 |
| `spring` | transition | implemented | b08 |  | hitech does not enable it; the fake swaps it for a zoom |
| `wipe` | transition | implemented |  | b02 | 0.25 s; exercised only by the hitech render |
| `flash` | transition | implemented |  |  | 060: a 0.3 s full-frame colour flash peaking on the cut, over the picture layers only (the PIP circle and captions never blink); the explainer and the drafts do not enable it; 059's recipe styles do, and their smokes draw it on b03 |
| `text_pop` | 1 | implemented |  |  | 061: 1-4 bold words (Poppins 900, yellow / white / accent, dark outline) pinned on a picture beat at the planner's `{x, y, anchor}`, popping in with an overshoot on the spoken word and staying to the beat's end or `hold_max_s`; placed clear of the PIP circle, the caption band and any detected face. Every existing style sets `text_pops_max_per_60s: 0` (059's recipe styles turn it on), so the plain smokes draw none; `python -m shortsmith.smoke --text-pops` renders the fake plan's one pop (b03, "THIS", on the presenter full beat) under the explainer copy with pops on |
| `bubble` | 1 | implemented |  |  | 063: a `speech` bubble (rounded white body with a tail, Poppins 800 in the style's `motion.bubble.ink`) or a `thought` bubble (the body with a trail of dots) of 1-7 words the recording itself carries, its tail tip on the planner's `{x, y}`; pops in with an overshoot at its landing (the grammar's `at_s`: the first source word, or the beat's start; a pair's second bubble lands `dialogue_gap_min_s`-`dialogue_gap_max_s` after the first) and stays to the beat's end or `hold_max_s`; the body wraps and shrinks to `min_size_px`, then fails the build; placed clear of the PIP circle, the caption band, the stamp, any detected face and the beat's other bubble. Every existing style sets `bubbles_max_per_60s: 0` (059's recipe styles turn it on), so the plain smokes draw none; `python -m shortsmith.smoke --bubbles` renders the fake plan's dialogue pair (b04, the card beat: a speech bubble at the PIP circle, a thought bubble over the card) under the explainer copy with bubbles on |
| `sticker` | 1 | implemented |  |  | 062: a Microsoft Fluent Emoji 3D PNG (MIT; the committed catalogue `assets/stickers/catalog.yaml`, picked by intent tag) in a `motion.sticker.size_px` square (180-320 px), popping in with an overshoot on its spoken word (the grammar's `at_s`), then floating gently under a soft shadow until the beat's end or `hold_max_s`; above the PIP circle when the planner gives no `{x, y}`, else centred on its point; placed clear of the PIP circle, the caption band, the stamp, any detected face and the beat's text pops and bubbles; at most one per beat. The PNG is fetched by the asset step on first use into the data dir's cache and copied into the job; a failed fetch drops the sticker, logged. Every existing style sets `stickers_max_per_60s: 0` (059's recipe styles set theirs), so the plain smokes draw none; `python -m shortsmith.smoke --stickers` renders the fake plan's one sticker (b01, a light bulb above the circle on "there") under the explainer copy with stickers on |
| `highlight` | 1 | implemented |  |  | 078: a yellow marker sweeping the spoken sentence on an owner's uploaded article or document screenshot, line by line, left to right, from the sentence's first word to its last - the style's `motion.highlight.color` (the accent) at `opacity` 0.45, multiplied over the page so the ink stays dark; the screenshot is a straight card pushing in to `push_to` about the highlighted lines, under the PIP circle and the captions. The lines are found on the image by one judge-model call at sourcing (cached per asset and sentence); none found drops it, logged. Owner screenshots only, never a made-up article. Every style but footage sets `highlights_max_per_60s: 0`, and the smoke uploads no screenshot, so the smokes draw none; `tests/test_highlight.py` renders a drawn screenshot through Remotion |
| `title_strip` | 1 | implemented |  |  | 059: the fixed topic bar a style with `broll.title_strip` (fastfacts) keeps at the top of the frame (y 262, under the 6.3 top zone) from the first frame to the finale: the plan's `title_strip` (at most `words_max` words) in the caption weight, ink on the fill, fitted from `size_px` to `min_size_px`, sliding down over `duration_s`; the text pops, bubbles and stickers are placed off it and T12 judges its box. `python -m shortsmith.smoke --style fastfacts` draws "Twelve words of nothing" |

## The recipe renders (ticket 059)

`python -m shortsmith.smoke --style footage|vishva|fastfacts` renders the fixture under
each shipped recipe style (the smoke proves the form resolves each name to itself). Every
recipe enables `flash` and allows whooshes: b03, the turn back to the presenter, flashes
and carries the one whoosh (its text pop's tick gives way under `cues_per_beat_max`).
footage: the text pop on b03, the sticker on b01, the clip on b04. vishva: the pop on b03,
the dialogue pair on b04, the sticker on b01 and the stacked split on b09. fastfacts: the
pop on b03 and the title strip over b01-b10. The recipes turn their overlays on
themselves, so the smoke judges them under the fixture's overlay counts (`pops_on`,
`bubbles_on`, `stickers_on`), as the flags do for the other styles.

## The hitech render (ticket 048)

Not judged, not shipped: `styles/hitech.md` stays `status: draft` and its aliases still
redirect to `explainer` with the page notice; the smoke proves that redirect before it
selects the draft directly. The run on 2026-09-26 delivered with T1-T13 passing, the
render spec carrying hitech's palette (`#020617` to `#0F172A`, accent `#22D3EE`), caption
typography and PIP ring, and `wipe` on b04 (b02 since 055). The sound director placed one cue where the
explainer run places two: hitech's `cues_max_per_60s` is 16 against explainer's 20, and
the renderer scales the on-disk number to the six-second clip.
