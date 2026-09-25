// `pip` (decisions 3.3, 6.3): the presenter in a circle of the diameter the spec gives
// at the style's anchor, cropped through the square window the spec gives, with the
// ring look. Ticket 013 measures both once per job (the window around the chin, the
// circle grown for a large face); this component only draws what it is handed and
// never follows the face (14.1). `Presenter` is the full-frame form the `full` mode
// uses; both read the same source.
import { Video } from "@remotion/media";
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { BeatSpec, RenderSpec } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Research section 2: a full-frame beat opens pushed in and settles over `settle_s`,
// then relaxes to 1 by the end of the beat, graded a touch up.
function punch(beat: BeatSpec | undefined, frame: number, fps: number) {
  const numbers = beat?.punch_in;
  if (!beat || !numbers) {
    return { scale: 1, filter: "none", origin: "50% 50%" };
  }
  const t = (frame - beat.start_frame) / fps;
  const beatLength = Math.max((beat.end_frame - beat.start_frame) / fps, 1 / fps);
  // A beat shorter than the settle stops at `settle_to`; it never gets to relax to 1.
  const [range, output] =
    beatLength > numbers.settle_s
      ? [
          [0, numbers.settle_s, beatLength],
          [numbers.scale_from, numbers.settle_to, 1],
        ]
      : [
          [0, beatLength],
          [numbers.scale_from, numbers.settle_to],
        ];
  return {
    scale: interpolate(t, range, output, { ...clamp, easing: Easing.out(Easing.cubic) }),
    filter: `contrast(${numbers.contrast}) saturate(${numbers.saturate})`,
    origin: `50% ${numbers.origin_y * 100}%`,
  };
}

export const Presenter: React.FC<{
  spec: RenderSpec;
  beat?: BeatSpec;
  frame?: number;
}> = ({ spec, beat, frame = 0 }) => {
  if (!spec.presenter) {
    return null;
  }
  const { scale, filter, origin } = punch(beat, frame, spec.fps);
  return (
    <AbsoluteFill>
      <Video
        src={spec.presenter}
        muted
        disallowFallbackToOffthreadVideo
        style={{
          width: spec.width,
          height: spec.height,
          objectFit: "cover",
          transform: `scale(${scale})`,
          transformOrigin: origin,
          filter,
        }}
      />
    </AbsoluteFill>
  );
};

// The presenter cut through the spec's square crop window, in a ring of any size: the
// PIP circle, and the finale card's centre circle (ticket 026).
export const PresenterCircle: React.FC<{
  spec: RenderSpec;
  left: number;
  top: number;
  diameter: number;
  ringPx: number;
  ringColor: string;
}> = ({ spec, left, top, diameter, ringPx, ringColor }) => {
  const pip = spec.pip;
  if (!spec.presenter) {
    return null;
  }
  const scale = diameter / pip.window_size;
  return (
    <div
      style={{
        position: "absolute",
        left,
        top,
        width: diameter,
        height: diameter,
        borderRadius: "50%",
        overflow: "hidden",
        boxSizing: "border-box",
        border: `${ringPx}px solid ${ringColor}`,
        boxShadow: "0 6px 24px rgba(0,0,0,0.45)",
      }}
    >
      <Video
        src={spec.presenter}
        muted
        disallowFallbackToOffthreadVideo
        style={{
          position: "absolute",
          left: -pip.window_left * scale - ringPx,
          top: -pip.window_top * scale - ringPx,
          width: spec.source_width * scale,
          height: spec.source_height * scale,
        }}
      />
    </div>
  );
};

export const Pip: React.FC<{ spec: RenderSpec }> = ({ spec }) => {
  const pip = spec.pip;
  return (
    <PresenterCircle
      spec={spec}
      left={pip.left}
      top={pip.top}
      diameter={pip.diameter}
      ringPx={pip.ring_px}
      ringColor={pip.ring_color}
    />
  );
};
