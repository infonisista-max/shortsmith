// `card` (decisions 4.1, 5.3): the framed archival card. Behind it, the same image
// blurred and darkened as the cover, pushing from the style's `scale_from` to
// `scale_to`; in front, the image at its native aspect inside a white border, tilted,
// with a caption strip when the beat carries a label, taking the slow Ken Burns push,
// and the red ring landing on the framing's focus when the beat carries a ring event.
// Every box and number comes from the spec (render.card_visual places it so it ends
// above the style's card_max_bottom_y). Ticket 078: an owner's article screenshot is a
// straight card pushing in about its highlighted lines (`origin_x`, `origin_y`), the
// `highlight` marker sweeping them inside the image.
import React from "react";
import { AbsoluteFill, Easing, interpolate } from "remotion";
import type { BeatSpec } from "../types";
import { FONT_FAMILY } from "../fonts";
import { Highlight } from "./highlight";
import { Framed, beatProgress } from "./photo";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const RING_LAND_S = 0.16; // the ring lands like a stamp (4.1)

type CardProps = {
  beat: BeatSpec;
  frame: number;
  fps: number;
  width: number;
  height: number;
};

export const Card: React.FC<CardProps> = (props) => <CardBody {...props} />;

// 103: the body the card, the backdrop and the polaroid share - the blurred, darkened
// cover of the image filling the frame, and the boxed image over it (a backdrop's box has
// no border and no tilt; a polaroid's is a print). `lift` is extra transform on the box
// before its tilt (the polaroid's drop) and `shadow` replaces the card's shadow.
export const CardBody: React.FC<CardProps & { lift?: string; shadow?: string }> = ({
  beat,
  frame,
  fps,
  width,
  height,
  lift = "",
  shadow = "0 18px 48px rgba(0,0,0,0.55)",
}) => {
  const visual = beat.visual;
  const card = visual?.card;
  if (!visual || !card) {
    return null;
  }
  const p = beatProgress(beat, frame);
  const cover = interpolate(p, [0, 1], [card.cover_scale_from, card.cover_scale_to]);
  const push = interpolate(p, [0, 1], [visual.scale_from, visual.scale_to]);
  const t = (frame - beat.start_frame) / fps;
  const ringIn = interpolate(t, [card.ring_at_s, card.ring_at_s + RING_LAND_S], [0, 1], {
    ...clamp,
    easing: Easing.out(Easing.back(1.6)),
  });
  const coverVisual = { ...visual, zoom: 1, focus_x: 0.5, focus_y: 0.5 };
  return (
    <AbsoluteFill>
      <Framed
        visual={coverVisual}
        width={width}
        height={height}
        scale={cover}
        style={{ filter: `blur(${card.cover_blur_px}px) brightness(${card.cover_brightness})` }}
      />
      <div
        style={{
          position: "absolute",
          left: card.left,
          top: card.top,
          width: card.width,
          height: card.height,
          boxSizing: "border-box",
          padding: card.border_px,
          background: "#fff",
          boxShadow: shadow,
          transform: `${lift} rotate(${card.rotate_deg}deg) scale(${push})`,
          transformOrigin: `${card.origin_x * 100}% ${card.origin_y * 100}%`,
        }}
      >
        <div
          style={{
            position: "relative",
            width: card.image_width,
            height: card.image_height,
            overflow: "hidden",
          }}
        >
          <Framed visual={visual} width={card.image_width} height={card.image_height} scale={1} />
          {card.highlight ? <Highlight spec={card.highlight} t={t} /> : null}
          {card.ring ? (
            <div
              style={{
                position: "absolute",
                left: visual.focus_x * card.image_width - card.ring_diameter_px / 2,
                top: visual.focus_y * card.image_height - card.ring_diameter_px / 2,
                width: card.ring_diameter_px,
                height: card.ring_diameter_px,
                boxSizing: "border-box",
                borderRadius: "50%",
                border: `${card.ring_px}px solid ${card.ring_color}`,
                opacity: ringIn,
                transform: `scale(${interpolate(ringIn, [0, 1], [1.3, 1])})`,
              }}
            />
          ) : null}
        </div>
        {card.strip_px > 0 ? (
          <div
            style={{
              height: card.strip_px,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontFamily: FONT_FAMILY,
              fontWeight: 700,
              fontSize: card.strip_font_px,
              color: "#111",
              whiteSpace: "nowrap",
              overflow: "hidden",
            }}
          >
            {card.strip_text}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
