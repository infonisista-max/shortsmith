import { Composition } from "remotion";
import { DURATION_FRAMES, FPS } from "./captions";
import { Short } from "./Short";

export const Root: React.FC = () => (
  <Composition
    id="Short"
    component={Short}
    width={1080}
    height={1920}
    fps={FPS}
    durationInFrames={DURATION_FRAMES}
  />
);
