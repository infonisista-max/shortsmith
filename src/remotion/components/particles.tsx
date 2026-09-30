// `particles` (ticket 109; 083: currency_shower, cash_cascade, brain_particles_overlay): a
// light overlay drawn in code, no stock asset. `cash` rains banknotes that tumble down
// through the area; `brain` drifts glowing particles up through two lobes that twinkle.
// Every piece stays inside the spec's box - `render.particles_spec` keeps that box off the
// PIP circle, the captions and any face - from `at_s` to `until_s`, fading in and out over
// `fade_s`. Positions come from a fixed hash of the piece's index, so every render of a
// frame is the same.
import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import type { ParticlesSpec } from "../types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const NOTE_ASPECT = 0.46; // a banknote's height over its width (a 500 rupee note)

// A repeatable pseudo-random number in [0, 1) for piece `i`, channel `k`.
export function hash(i: number, k: number): number {
  const s = Math.sin(i * 127.1 + k * 311.7) * 43758.5453;
  return s - Math.floor(s);
}

// Where piece `i` is `t` seconds after the overlay starts, as fractions of the box: each
// piece crosses it once per `fall_s`, starting at its own phase, so pieces enter over time.
export function piecePath(
  spec: ParticlesSpec,
  i: number,
  t: number,
): { x: number; y: number; spin: number } {
  const phase = hash(i, 1);
  const cycle = (t / spec.fall_s + phase) % 1;
  const sway = Math.sin((t / spec.fall_s) * Math.PI * 2 + hash(i, 2) * 6.28) * 0.04;
  const x = hash(i, 0) + sway;
  const y = spec.kind === "cash" ? cycle : 1 - cycle; // cash falls, a thought rises
  const spin = (hash(i, 3) - 0.5) * 720 * (t / spec.fall_s);
  return { x: Math.min(1, Math.max(0, x)), y, spin };
}

export const Particles: React.FC<{ spec: ParticlesSpec; frame: number; fps: number }> = ({
  spec,
  frame,
  fps,
}) => {
  const t = frame / fps;
  if (t < spec.at_s || t >= spec.until_s) {
    return null;
  }
  const since = t - spec.at_s;
  const fade =
    spec.fade_s > 0
      ? Math.min(
          interpolate(t, [spec.at_s, spec.at_s + spec.fade_s], [0, 1], clamp),
          interpolate(t, [spec.until_s - spec.fade_s, spec.until_s], [1, 0], clamp),
        )
      : 1;
  const w = spec.size_px;
  const h = spec.kind === "cash" ? spec.size_px * NOTE_ASPECT : spec.size_px;
  const pieces = Array.from({ length: spec.count }, (_, i) => {
    const { x, y, spin } = piecePath(spec, i, since);
    const colour = spec.colors[i % spec.colors.length];
    const left = x * (spec.width - w);
    const top = y * (spec.height - h);
    if (spec.kind === "cash") {
      return (
        <div
          key={i}
          style={{
            position: "absolute",
            left,
            top,
            width: w,
            height: h,
            background: colour,
            border: `${Math.max(2, w / 40)}px solid rgba(0,0,0,0.35)`,
            borderRadius: w / 30,
            boxSizing: "border-box",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "rgba(0,0,0,0.45)",
            fontFamily: "Poppins",
            fontWeight: 800,
            fontSize: h * 0.5,
            transform: `rotate(${spin}deg) rotateX(${spin / 2}deg)`,
          }}
        >
          ₹
        </div>
      );
    }
    // brain: two lobes - each piece keeps to the left or right half, twinkling
    const lobe = i % 2 === 0 ? 0 : 0.5;
    const twinkle = 0.5 + 0.5 * Math.sin(since * 8 + hash(i, 4) * 6.28);
    return (
      <div
        key={i}
        style={{
          position: "absolute",
          left: (lobe + x * 0.5) * (spec.width - w),
          top,
          width: w,
          height: h,
          borderRadius: w,
          background: colour,
          opacity: twinkle,
          boxShadow: `0 0 ${w * 2}px ${colour}`,
        }}
      />
    );
  });
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: spec.left,
          top: spec.top,
          width: spec.width,
          height: spec.height,
          overflow: "hidden",
          opacity: spec.opacity * fade,
          pointerEvents: "none",
        }}
      >
        {pieces}
      </div>
    </AbsoluteFill>
  );
};
