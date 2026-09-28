// `sticker` (decision 4.1 as amended by ticket 062): a Microsoft Fluent Emoji 3D PNG (MIT)
// popping over the picture - above the PIP circle ("over his head") or near its subject.
// The beat's sticker is already fetched into the job, placed and timed by
// `render.sticker_spec` (inside the safe area, off the PIP circle, the captions, the stamp,
// any detected face and the beat's text pops and bubbles); this file only draws and
// animates it: hidden until `at_s` seconds into the beat, a back-eased overshoot from
// `scale_from` to 1 over `pop_s` about the square's centre, then a gentle float of
// `float_px` up and down every `float_period_s`, under a soft drop shadow of `shadow_px`,
// held until `until_s`.
import React from "react";
import { AbsoluteFill, Easing, Img, interpolate } from "remotion";
import type { StickerSpec } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const OVERSHOOT = 2.2; // the back-easing's overshoot: a bouncier pop than the text pop's

export const Sticker: React.FC<{
  stickers: StickerSpec[];
  frame: number;
  fps: number;
}> = ({ stickers, frame, fps }) => {
  const t = frame / fps;
  return (
    <AbsoluteFill>
      {stickers.map((sticker, i) => {
        if (t < sticker.at_s || t >= sticker.until_s) {
          return null;
        }
        const landed = interpolate(t, [sticker.at_s, sticker.at_s + sticker.pop_s], [0, 1], {
          ...clamp,
          easing: Easing.out(Easing.back(OVERSHOOT)),
        });
        const scale = interpolate(landed, [0, 1], [sticker.scale_from, 1]);
        const floating = Math.max(0, t - sticker.at_s - sticker.pop_s);
        const lift =
          -sticker.float_px * Math.sin((2 * Math.PI * floating) / sticker.float_period_s);
        return (
          <Img
            key={i}
            src={sticker.src}
            style={{
              position: "absolute",
              left: sticker.left,
              top: sticker.top,
              width: sticker.size,
              height: sticker.size,
              objectFit: "contain",
              transform: `translateY(${lift}px) scale(${scale})`,
              transformOrigin: "50% 50%",
              filter: `drop-shadow(0px ${sticker.shadow_px / 2}px ${sticker.shadow_px}px rgba(0, 0, 0, 0.45))`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};
