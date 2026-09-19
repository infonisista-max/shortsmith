import { loadFont } from "@remotion/fonts";
import { Video } from "@remotion/media";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  CUT_IN,
  PAGES,
  PAGE_BOUNDS,
  PIP_CROP_Y,
  PIP_DIAM,
  PIP_END,
  PIP_FRAMES,
  PIP_START,
  PIP_X,
  PIP_Y,
  type Word,
} from "./captions";

// Poppins 800 from the same TTF the ffmpeg version used via fontsdir=.
loadFont({
  family: "Poppins",
  url: staticFile("Poppins-ExtraBold.ttf"),
  weight: "800",
});

const SRC = staticFile("sample.mp4");
const STILL = staticFile("still.jpg");

const YELLOW = "#FFD60A";
const INK = "#111";

// Section 4: 2 px four-direction fake stroke + 3 px drop + 18 px black glow.
const STROKE =
  "-2px 0 #000, 2px 0 #000, 0 -2px #000, 0 2px #000, " +
  "-2px -2px #000, 2px -2px #000, -2px 2px #000, 2px 2px #000, " +
  "0 3px 0 #000, 0 0 18px #000";

const WordSpan: React.FC<{ word: Word; t: number }> = ({ word, t }) => {
  // Spoken at start - 0.02 s; active until end + 0.06 s (no frame quantisation).
  const onset = word.start - 0.02;
  const release = word.end + 0.06;
  const spoken = t >= onset;
  const active = spoken && t < release;
  const scale = active
    ? interpolate(t, [onset, onset + 0.1], [1.0, 1.08], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 1;
  const boxed = word.keyword && spoken && !active;

  return (
    <span
      style={{
        display: "inline-block",
        transform: `scale(${scale})`,
        transformOrigin: "center bottom",
        color: boxed ? INK : active ? YELLOW : spoken ? "#fff" : "rgba(255,255,255,0.86)",
        backgroundColor: boxed ? YELLOW : "transparent",
        padding: boxed ? "0 14px" : 0,
        borderRadius: boxed ? 14 : 0,
        textShadow: boxed ? "none" : STROKE,
      }}
    >
      {word.text}
    </span>
  );
};

const Captions: React.FC<{ t: number }> = ({ t }) => {
  const idx = PAGE_BOUNDS.findIndex((b) => t >= b.start && t < b.end);
  if (idx < 0) return null;
  const { start } = PAGE_BOUNDS[idx];

  // Page enter: scale 0.94 -> 1 over 0.12 s with back easing; opacity over 0.06 s.
  const scale = interpolate(t, [start, start + 0.12], [0.94, 1], {
    easing: Easing.out(Easing.back(1.7)),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = interpolate(t, [start, start + 0.06], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        left: 60,
        right: 60,
        bottom: 460,
        textAlign: "center",
        fontFamily: "Poppins",
        fontWeight: 800,
        fontSize: 74,
        lineHeight: 1.35,
        letterSpacing: 0.5,
        transform: `scale(${scale})`,
        transformOrigin: "center bottom",
        opacity,
      }}
    >
      {PAGES[idx].map((w, i) => (
        <span key={i}>
          {i > 0 ? " " : ""}
          <WordSpan word={w} t={t} />
        </span>
      ))}
    </div>
  );
};

export const Short: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const inPip = t >= PIP_START && t < PIP_END;
  const startFrom = Math.round(CUT_IN * fps); // 600

  // Ken Burns 1.10 -> 1.16, linear over PIP_FRAMES, same as zoompan's 1.10+0.06*on/299.
  const zoom = 1.1 + (0.06 * (frame - PIP_START * fps)) / (PIP_FRAMES - 1);
  const pipScale = PIP_DIAM / 1080;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Base presenter. Hidden behind the still during the PIP window, so not rendered there. */}
      {!inPip && (
        <Video
          src={SRC}
          trimBefore={startFrom}
          muted
          disallowFallbackToOffthreadVideo
          objectFit="cover"
          style={{ width: 1080, height: 1920 }}
        />
      )}

      {inPip && (
        <>
          {/* Still: centre crop to 9:16 (object-fit cover on a 1920x1080 image = 608x1080 crop). */}
          <AbsoluteFill style={{ overflow: "hidden" }}>
            <Img
              src={STILL}
              style={{
                width: 1080,
                height: 1920,
                objectFit: "cover",
                transform: `scale(${zoom})`,
                transformOrigin: "center center",
              }}
            />
          </AbsoluteFill>

          {/* Round PIP: 1080 px square at y PIP_CROP_Y, scaled to 300 px, circular. */}
          <div
            style={{
              position: "absolute",
              left: PIP_X,
              top: PIP_Y,
              width: PIP_DIAM,
              height: PIP_DIAM,
              borderRadius: "50%",
              overflow: "hidden",
            }}
          >
            <Video
              src={SRC}
              trimBefore={startFrom}
              muted
              disallowFallbackToOffthreadVideo
              style={{
                position: "absolute",
                left: 0,
                top: -PIP_CROP_Y * pipScale,
                width: 1080 * pipScale,
                height: 1920 * pipScale,
              }}
            />
          </div>
        </>
      )}

      <Captions t={t} />
    </AbsoluteFill>
  );
};
