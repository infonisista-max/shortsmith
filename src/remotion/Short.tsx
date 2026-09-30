// The explainer composition (ticket 004): per frame, the beat's presenter mode picks
// full-frame presenter, PIP over the palette gradient, or the gradient alone (`off`),
// with the caption layer on top. Ticket 016 draws the beat's B-roll between the
// gradient and the presenter: a full-bleed `photo` or a framed `card`. A rung-4
// rescue arrives as `pip` with no visual. Ticket 026 adds the two set pieces (the
// hook's cards and the finale) between the B-roll and the presenter, the full-frame
// punch-in, and the two landed overlays (`stamp`, `lower_third`) over the presenter.
// Ticket 027 adds the other three tier-1 set pieces in the same layer: `list` and
// `wall` over the beat's dimmed base still, `split` as the news-card composite.
// Ticket 021 adds the two infographic kinds: `infographic` draws its own label-free base
// with the labels in code over it, `chart` is drawn from the planner's series over the
// gradient. Ticket 029 flies the diagram's labels in (`label_flyin`, over its base) and
// adds the `counter`, a number beat's landed event in the stamp's layer. Ticket 020 draws
// the `map` from the bundled geodata over the gradient (the water), with its markers at
// real coordinates. Ticket 028 animates it over the base, in layer order: `route_arrow`
// draws the route on, `pin_drop` drops the markers in (the base draws them static when
// the beat has no pin drop), `object_path` moves the object along the route on top.
//
// Ticket 030 (decision 9.4): a beat's picture - its B-roll, set piece, infographic, map
// or full-frame presenter (`BeatLayers`) - enters through the beat's `enter` transition
// with the spec's numbers. The PIP circle, the landed overlays and the captions sit above
// the transition and never move with it (the circle is anchored, 14.1; a stamp lands in
// its own time). Under a `fade` or `wipe` the previous beat's layers stay drawn beneath
// for the motion's length, so the exit is a dissolve or the uncovered picture; every
// other exit is a cut.
//
// Ticket 060 (9.4 as amended): a `flash` enter is a cut for the picture with a colour
// flash over it, peaking on the boundary frame and fading `transitions.flash.duration_s`
// / 2 either side (`flashAt`): it rises through the previous beat's last frames and falls
// through the new beat's first. The overlay sits above both beats' picture layers and
// below the PIP circle, the landed overlays and the captions, which never blink.
//
// Ticket 061 (4.1 as amended): a beat's text pops (`text_pop`) are drawn with the landed
// overlays, above the PIP circle and below the captions; they are placed clear of both,
// so the order only settles what a stray pixel would cover. Ticket 063: a beat's speech
// and thought bubbles (`bubble`) sit in the same layer, after the text pops. Ticket 062:
// a beat's sticker (`sticker`, a Fluent Emoji PNG) after the bubbles, under the captions.
//
// Ticket 058 (4.1 as amended): a `clip` treatment is a full-screen muted stock video drawn
// in the photo's layer, under the PIP circle, the overlays and the captions.
//
// Ticket 103: the picture treatments an editor picks per still (`backdrop`, `crop_fill`,
// `polaroid`) are drawn in the same layer as the photo and the card they stand beside.
//
// Ticket 107: a `light_flare` enter is a cut with a warm light burst over it, drawn like
// the flash (`lightFlareAt`, over both beats' picture layers, under the circle, the
// overlays and the captions). A beat's `banner` sits with the landed overlays, after the
// lower-third and before the text pops; it is placed clear of the circle and the captions.
// Ticket 108: a year beat's `calendar` page lands in the stamp's layer, after the counter.
// Ticket 109: a beat's cash or brain `particles` sit over the picture and under the PIP
// circle, in a box kept off the circle, the captions and any face.
//
// Ticket 059: a recipe style's fixed title strip (`title_strip`) sits above the beat
// overlays and under the captions from the first frame to the finale's first frame.
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Backdrop } from "./components/backdrop";
import { Banner } from "./components/banner";
import { Bubble } from "./components/bubble";
import { Calendar } from "./components/calendar";
import { Captions } from "./components/captions";
import { Card } from "./components/card";
import { Chart } from "./components/chart";
import { Clip } from "./components/clip";
import { Counter } from "./components/counter";
import { CropFill } from "./components/crop_fill";
import { Finale } from "./components/finale";
import { FlashOverlay, flashAt } from "./components/flash";
import { HookCards } from "./components/hook_cards";
import { Infographic } from "./components/infographic";
import { LabelFlyin } from "./components/label_flyin";
import { LightFlareOverlay, lightFlareAt } from "./components/light_flare";
import { List } from "./components/list";
import { LowerThird } from "./components/lower_third";
import { MapBase } from "./components/map";
import { ObjectPath } from "./components/object_path";
import { Particles } from "./components/particles";
import { Photo } from "./components/photo";
import { PinDrop } from "./components/pin_drop";
import { Polaroid } from "./components/polaroid";
import { Pip, Presenter } from "./components/pip";
import { RouteArrow } from "./components/route_arrow";
import { Split } from "./components/split";
import { Stamp } from "./components/stamp";
import { Sticker } from "./components/sticker";
import { TextPop } from "./components/text_pop";
import { TitleStrip } from "./components/title_strip";
import { Transition, holdFrames, holdsPrevious } from "./components/transitions";
import { Wall } from "./components/wall";
import { fontsReady } from "./fonts";
import type { BeatSpec, RenderSpec } from "./types";

void fontsReady;

// Everything that is the beat's own picture, in layer order; `frame` is absolute, the
// pieces that animate from the beat's start get `since`.
const BeatLayers: React.FC<{ spec: RenderSpec; beat: BeatSpec; frame: number }> = ({
  spec,
  beat,
  frame,
}) => {
  const visual = beat.mode === "full" ? null : beat.visual;
  const since = frame - beat.start_frame;
  const lengthS = (beat.end_frame - beat.start_frame) / spec.fps;
  return (
    <AbsoluteFill>
      {visual?.treatment === "photo" ? (
        <Photo beat={beat} frame={frame} width={spec.width} height={spec.height} />
      ) : null}
      {visual?.treatment === "card" ? (
        <Card beat={beat} frame={frame} fps={spec.fps} width={spec.width} height={spec.height} />
      ) : null}
      {visual?.treatment === "clip" ? (
        <Clip beat={beat} frame={frame} fps={spec.fps} width={spec.width} height={spec.height} />
      ) : null}
      {visual?.treatment === "backdrop" ? (
        <Backdrop beat={beat} frame={frame} fps={spec.fps} width={spec.width} height={spec.height} />
      ) : null}
      {visual?.treatment === "crop_fill" ? (
        <CropFill beat={beat} frame={frame} width={spec.width} height={spec.height} />
      ) : null}
      {visual?.treatment === "polaroid" ? (
        <Polaroid beat={beat} frame={frame} fps={spec.fps} width={spec.width} height={spec.height} />
      ) : null}
      {beat.hook ? (
        <HookCards spec={beat.hook} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat.finale ? (
        <Finale
          spec={beat.finale}
          render={spec}
          style={spec.caption_style}
          frame={since}
          fps={spec.fps}
        />
      ) : null}
      {beat.list ? (
        <List spec={beat.list} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat.split ? (
        <Split spec={beat.split} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat.wall ? <Wall spec={beat.wall} frame={since} fps={spec.fps} lengthS={lengthS} /> : null}
      {beat.infographic ? (
        <Infographic spec={beat.infographic} frame={since} fps={spec.fps} lengthS={lengthS} />
      ) : null}
      {beat.infographic ? (
        <LabelFlyin
          spec={beat.infographic}
          style={spec.caption_style}
          frame={since}
          fps={spec.fps}
        />
      ) : null}
      {beat.chart ? (
        <Chart spec={beat.chart} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat.map ? (
        <MapBase
          spec={beat.map}
          style={spec.caption_style}
          frame={since}
          fps={spec.fps}
          width={spec.width}
          height={spec.height}
        />
      ) : null}
      {beat.map?.route_arrow ? (
        <RouteArrow
          spec={beat.map}
          frame={since}
          fps={spec.fps}
          width={spec.width}
          height={spec.height}
        />
      ) : null}
      {beat.map?.pin_drop ? (
        <PinDrop spec={beat.map} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat.map?.object_path ? (
        <ObjectPath spec={beat.map} frame={since} fps={spec.fps} />
      ) : null}
      {beat.mode === "full" ? <Presenter spec={spec} beat={beat} frame={frame} /> : null}
    </AbsoluteFill>
  );
};

export const Short: React.FC<RenderSpec> = (spec) => {
  const frame = useCurrentFrame();
  const t = frame / spec.fps;
  const found = spec.beats.findIndex((b) => frame >= b.start_frame && frame < b.end_frame);
  const index = found >= 0 ? found : spec.beats.length - 1;
  const beat = spec.beats[index];
  const previous = index > 0 ? spec.beats[index - 1] : undefined;
  const next = index + 1 < spec.beats.length ? spec.beats[index + 1] : undefined;
  const [from, to] = spec.palette.gradient;
  const since = beat ? frame - beat.start_frame : 0;
  const held =
    beat && previous && holdsPrevious(beat.enter)
      ? since < holdFrames(beat.enter, spec.transitions, spec.fps)
      : false;
  const flash = flashAt(frame, spec.fps, spec.transitions, beat, next);
  const flare = lightFlareAt(frame, spec.fps, spec.transitions, beat, next);
  return (
    <AbsoluteFill
      style={{ background: `linear-gradient(${spec.palette.angle_deg}deg, ${from}, ${to})` }}
    >
      {held && previous ? <BeatLayers spec={spec} beat={previous} frame={frame} /> : null}
      {beat ? (
        <Transition
          enter={beat.enter}
          since={since}
          fps={spec.fps}
          numbers={spec.transitions}
          width={spec.width}
          height={spec.height}
        >
          <BeatLayers spec={spec} beat={beat} frame={frame} />
        </Transition>
      ) : null}
      <FlashOverlay opacity={flash} numbers={spec.transitions} />
      <LightFlareOverlay
        state={flare}
        numbers={spec.transitions}
        width={spec.width}
        height={spec.height}
      />
      {beat?.particles ? (
        <Particles spec={beat.particles} frame={since} fps={spec.fps} />
      ) : null}
      {beat?.mode === "pip" ? <Pip spec={spec} /> : null}
      {beat?.stamp ? (
        <Stamp spec={beat.stamp} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat?.counter ? (
        <Counter spec={beat.counter} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat?.calendar ? (
        <Calendar spec={beat.calendar} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat?.lower_third ? (
        <LowerThird
          spec={beat.lower_third}
          style={spec.caption_style}
          frame={since}
          fps={spec.fps}
        />
      ) : null}
      {beat?.banner ? (
        <Banner spec={beat.banner} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat?.text_pops?.length ? (
        <TextPop pops={beat.text_pops} style={spec.caption_style} frame={since} fps={spec.fps} />
      ) : null}
      {beat?.bubbles?.length ? (
        <Bubble
          bubbles={beat.bubbles}
          style={spec.caption_style}
          frame={since}
          fps={spec.fps}
          width={spec.width}
          height={spec.height}
        />
      ) : null}
      {beat?.stickers?.length ? (
        <Sticker stickers={beat.stickers} frame={since} fps={spec.fps} />
      ) : null}
      {spec.title_strip ? (
        <TitleStrip spec={spec.title_strip} style={spec.caption_style} frame={frame} fps={spec.fps} />
      ) : null}
      <Captions spec={spec} t={t} />
    </AbsoluteFill>
  );
};
