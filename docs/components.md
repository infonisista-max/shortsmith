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
| `photo` | 1 | implemented | b01, b04 | b01, b04 | Ken Burns from `broll.motion.photo`; b01 opens the short (055) |
| `card` | 1 | implemented | b02 | b02 | hitech: flat card, 2 px border, no tilt |
| `stamp` | 1 | implemented | b04 | b04 | hitech: `cyan_white` palette, no shake |
| `lower_third` | 1 | implemented | none drawn | none drawn | b02's card strip carries the label, so the standalone overlay is not exercised by the fixture plan |
| `hook_cards` | retired | retired (055) |  |  | no longer a tier-1 kind: the short opens with the speaker's first words over images, no title card; the Node component stays exported until it is removed with its registry test |
| `finale` | 1 | implemented | b11 | b11 | hitech: `spec_summary_card` kind, same component; 055: its cards are the short's first three distinct images |
| `list` | 1 | implemented | b08 | b08 | over the dimmed base still |
| `chart` | 1 | implemented | b06 | b06 | drawn from the series, never sourced |
| `split` | 1 | implemented | b09 | b09 | two panes, badge, highlighted title strip |
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

## The hitech render (ticket 048)

Not judged, not shipped: `styles/hitech.md` stays `status: draft` and its aliases still
redirect to `explainer` with the page notice; the smoke proves that redirect before it
selects the draft directly. The run on 2026-09-26 delivered with T1-T13 passing, the
render spec carrying hitech's palette (`#020617` to `#0F172A`, accent `#22D3EE`), caption
typography and PIP ring, and `wipe` on b04 (b02 since 055). The sound director placed one cue where the
explainer run places two: hitech's `cues_max_per_60s` is 16 against explainer's 20, and
the renderer scales the on-disk number to the six-second clip.
