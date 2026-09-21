import React from "react";
import { Composition } from "remotion";
import { Short } from "./Short";
import { EMPTY_SPEC, type RenderSpec } from "./types";

export const Root: React.FC = () => (
  <Composition
    id="Short"
    component={Short}
    width={EMPTY_SPEC.width}
    height={EMPTY_SPEC.height}
    fps={EMPTY_SPEC.fps}
    durationInFrames={EMPTY_SPEC.frames}
    defaultProps={EMPTY_SPEC}
    calculateMetadata={({ props }: { props: RenderSpec }) => ({
      durationInFrames: props.frames,
      fps: props.fps,
      width: props.width,
      height: props.height,
    })}
  />
);
