// `pip` (decisions 3.3, 6.3): the presenter in a circle of the style's diameter at the
// style's anchor, cropped through the square window the spec gives (fixed geometry
// until ticket 013 measures the face), with the ring look. `Presenter` is the
// full-frame form the `full` mode uses; both read the same source.
import { Video } from "@remotion/media";
import React from "react";
import { AbsoluteFill } from "remotion";
import type { RenderSpec } from "../types";

export const Presenter: React.FC<{ spec: RenderSpec }> = ({ spec }) => {
  if (!spec.presenter) {
    return null;
  }
  return (
    <AbsoluteFill>
      <Video
        src={spec.presenter}
        muted
        disallowFallbackToOffthreadVideo
        style={{ width: spec.width, height: spec.height, objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
};

export const Pip: React.FC<{ spec: RenderSpec }> = ({ spec }) => {
  const pip = spec.pip;
  if (!spec.presenter) {
    return null;
  }
  const scale = pip.diameter / pip.window_size;
  return (
    <div
      style={{
        position: "absolute",
        left: pip.left,
        top: pip.top,
        width: pip.diameter,
        height: pip.diameter,
        borderRadius: "50%",
        overflow: "hidden",
        boxSizing: "border-box",
        border: `${pip.ring_px}px solid ${pip.ring_color}`,
        boxShadow: "0 6px 24px rgba(0,0,0,0.45)",
      }}
    >
      <Video
        src={spec.presenter}
        muted
        disallowFallbackToOffthreadVideo
        style={{
          position: "absolute",
          left: -pip.window_left * scale - pip.ring_px,
          top: -pip.window_top * scale - pip.ring_px,
          width: spec.source_width * scale,
          height: spec.source_height * scale,
        }}
      />
    </div>
  );
};
