// `infographic` (decisions 9.2, 9.3, 5.5): the labelled diagram's base. The picture is
// label-free - the generator was told "no text, no labels" - and takes the style's Ken
// Burns and scrim in the box `infographics.resolve_diagram` placed it in. Its labels are
// drawn in code over it by `label_flyin` (029), each flying in from its nearest edge.
import React from "react";
import { AbsoluteFill, Img, interpolate } from "remotion";
import type { DiagramLayout } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Infographic: React.FC<{
  spec: DiagramLayout;
  frame: number;
  fps: number;
  lengthS: number;
}> = ({ spec, frame, fps, lengthS }) => {
  const t = frame / fps;
  const scale = interpolate(t, [0, Math.max(lengthS, 1 / fps)], [spec.scale_from, spec.scale_to], clamp);
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: spec.left,
          top: spec.top,
          width: spec.box_width,
          height: spec.box_height,
          overflow: "hidden",
        }}
      >
        <Img
          src={spec.src}
          style={{
            width: spec.box_width,
            height: spec.box_height,
            objectFit: "cover",
            objectPosition: `${spec.focus_x * 100}% ${spec.focus_y * 100}%`,
            transformOrigin: `${spec.focus_x * 100}% ${spec.focus_y * 100}%`,
            transform: `scale(${scale * spec.zoom})`,
          }}
        />
        {spec.dim > 0 ? (
          <AbsoluteFill style={{ background: "#000", opacity: spec.dim }} />
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
