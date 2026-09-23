// `wall` (decisions 4.1, 9.2): the grid set piece of nkb_09 - a 2x2 to 3x3 wall of
// framed cards flying in from alternating sides on the style's stagger, each cell
// carrying its own Ken Burns. The beat's still is drawn behind this by `photo`, dimmed
// by the style's `broll.motion.wall.dim`. `render.wall_spec` laid the grid out.
import React from "react";
import { AbsoluteFill } from "remotion";
import type { WallSpec } from "../types";
import { PlacedCard } from "./hook_cards";

export const Wall: React.FC<{
  spec: WallSpec;
  frame: number;
  fps: number;
  lengthS: number;
}> = ({ spec, frame, fps, lengthS }) => (
  <AbsoluteFill>
    {spec.cells.map((cell, i) => (
      <PlacedCard key={i} card={cell} frame={frame} fps={fps} holdS={lengthS} />
    ))}
  </AbsoluteFill>
);
