// `clip` (ticket 058; decisions 4.1 and 5.1 as amended): a full-screen moving shot from a
// free stock video library, drawn exactly where a `photo` is drawn - under the PIP
// circle and the captions - and always muted: the master carries the voice, the bed and
// the cues, never a clip's own sound. The spec gives the file (served by the driver like
// the presenter cut), the playback `speed` (the style's `broll.motion.clip.speed`), the
// second of the clip the beat starts at (`start_s`; a number beat carrying the clip on
// starts where the last beat stopped), and the slow push `scale_from` -> `scale_to`
// (1.0 -> 1.0 in every existing style: the clip's own movement is the motion). Nothing
// is measured here. Ticket 102: `start_s` is the clip's most moving stretch (measured by
// the asset step), and a clip the era judge found `timeless` carries the style's film grade.
import { Video } from "@remotion/media";
import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import type { BeatSpec } from "../types";
import { beatProgress, gradeFilter } from "./photo";

export const Clip: React.FC<{ beat: BeatSpec; frame: number; fps: number; width: number; height: number }> = ({
  beat,
  frame,
  fps,
  width,
  height,
}) => {
  const visual = beat.visual;
  if (!visual || visual.treatment !== "clip") {
    return null;
  }
  const p = beatProgress(beat, frame);
  const scale = interpolate(p, [0, 1], [visual.scale_from, visual.scale_to]);
  // The clip plays from `start_s` of its own timeline at the beat's first frame: the
  // Video sequence is trimmed by that many frames of the clip at `speed`.
  const trimBefore = Math.round(visual.start_s * fps);
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 0, top: 0, width, height, overflow: "hidden" }}>
        <Video
          src={visual.src}
          muted
          playbackRate={visual.speed}
          trimBefore={trimBefore}
          disallowFallbackToOffthreadVideo
          style={{
            width,
            height,
            objectFit: "cover",
            objectPosition: `${visual.focus_x * 100}% ${visual.focus_y * 100}%`,
            transformOrigin: `${visual.focus_x * 100}% ${visual.focus_y * 100}%`,
            transform: `scale(${scale * visual.zoom})`,
            filter: gradeFilter(visual) || undefined,
          }}
        />
      </div>
      {visual.dim > 0 ? <AbsoluteFill style={{ background: "#000", opacity: visual.dim }} /> : null}
    </AbsoluteFill>
  );
};
