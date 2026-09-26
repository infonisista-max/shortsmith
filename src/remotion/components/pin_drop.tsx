// `pin_drop` (decisions 9.2, 9.3, 4.1; ticket 028): the map's markers dropping in one
// after another. Each pin starts `spec.pin_drop_px` above its geocoded point on its own
// `delay_s` (the stagger `infographics.map_timeline` worked out from the beat's
// length), falls and settles with a spring over `pin_drop_s`, sends a splash ring out
// as it lands, and its label pill pops in over `label_pop_s` once it has landed.
// Everything is placed and measured in the layout; this file only animates it.
import React from "react";
import { AbsoluteFill, Easing, interpolate, spring } from "remotion";
import type { CaptionStyle, MapLayout } from "../types";
import { Marker } from "./map";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
// The pin's settle: a slight overshoot past the point and back (research section 2).
const SPRING = { damping: 12, stiffness: 180, mass: 0.8 } as const;

export const PinDrop: React.FC<{
  spec: MapLayout;
  style: CaptionStyle;
  frame: number;
  fps: number;
}> = ({ spec, style, frame, fps }) => (
  <AbsoluteFill>
    {spec.markers.map((marker, i) => {
      const local = frame - Math.round(marker.delay_s * fps);
      const dropFrames = Math.max(1, Math.round(spec.pin_drop_s * fps));
      const dropped =
        local < 0
          ? 0
          : spring({ frame: local, fps, config: SPRING, durationInFrames: dropFrames });
      const sinceLanded = (local - dropFrames) / fps;
      const labelIn = interpolate(sinceLanded, [0, Math.max(spec.label_pop_s, 1 / fps)], [0, 1], {
        ...clamp,
        easing: Easing.out(Easing.back(1.6)),
      });
      const splash = interpolate(sinceLanded, [0, Math.max(spec.label_pop_s, 1 / fps)], [0, 1], clamp);
      return (
        <Marker
          key={i}
          marker={marker}
          spec={spec}
          style={style}
          lift={spec.pin_drop_px * (1 - dropped)}
          shown={local >= 0}
          labelIn={sinceLanded < 0 ? 0 : labelIn}
          splash={sinceLanded < 0 ? 0 : splash}
        />
      );
    })}
  </AbsoluteFill>
);
