// `highlight` (ticket 078; 4.1 as amended): the article highlighter. Inside a screenshot
// card's image, a semi-transparent marker stroke in the style's colour sweeps each line of
// the spoken sentence left to right, one line after the other, over the seconds the spec
// gives (the first word to the last). Drawn by the card, so it shares the card's push and
// sits under the PIP circle and the captions. Every box and time comes from the spec.
import React from "react";
import { interpolate } from "remotion";
import type { HighlightSpec } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Highlight: React.FC<{ spec: HighlightSpec; t: number }> = ({ spec, t }) => (
  <>
    {spec.lines.map((line, i) => {
      const swept = interpolate(t, [line.start_s, Math.max(line.end_s, line.start_s + 1e-3)],
                                [0, 1], clamp);  // prettier-ignore
      return swept > 0 ? (
        <div
          key={i}
          style={{
            position: "absolute",
            left: line.left,
            top: line.top,
            width: line.width * swept,
            height: line.height,
            background: spec.color,
            opacity: spec.opacity,
            mixBlendMode: "multiply",
          }}
        />
      ) : null;
    })}
  </>
);
