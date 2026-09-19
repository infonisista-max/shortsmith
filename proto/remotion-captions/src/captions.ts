// Copied verbatim from proto/ffmpeg_proto.py so Version A and B share inputs.

export const FPS = 30;
export const CUT_IN = 20.0; // source 20-50 s -> output 0-30 s
export const CUT_LEN = 30.0;
export const DURATION_FRAMES = CUT_LEN * FPS; // 900

export const PIP_START = 10.0; // output-relative
export const PIP_END = 20.0;
export const PIP_FRAMES = (PIP_END - PIP_START) * FPS; // 300

export const FACE_CY = 870;
export const PIP_DIAM = 300;
export const PIP_X = 70;
export const PIP_Y = 960;
export const PIP_CROP_Y = Math.min(Math.max(FACE_CY - 540, 0), 840); // 330

export type Word = { text: string; start: number; end: number; keyword?: boolean };

export const PAGES: Word[][] = [
  // ~2 s: "start ki thi aur finally"  (keyword: finally)
  [
    { text: "start", start: 2.0, end: 2.35 },
    { text: "ki", start: 2.38, end: 2.55 },
    { text: "thi", start: 2.58, end: 2.8 },
  ],
  [
    { text: "aur", start: 2.95, end: 3.15 },
    { text: "finally", start: 3.2, end: 3.7, keyword: true },
  ],
  // ~6 s: "Olympic bhi le aaye the"  (keyword: Olympic)
  [
    { text: "Olympic", start: 6.0, end: 6.55, keyword: true },
    { text: "bhi", start: 6.6, end: 6.8 },
  ],
  [
    { text: "le", start: 6.85, end: 7.0 },
    { text: "aaye", start: 7.05, end: 7.35 },
    { text: "the", start: 7.38, end: 7.6 },
  ],
  // ~13 s: "aapko pata hai kya hai police force"  (keyword: police force)
  [
    { text: "aapko", start: 13.0, end: 13.35 },
    { text: "pata", start: 13.4, end: 13.65 },
    { text: "hai", start: 13.68, end: 13.85 },
  ],
  [
    { text: "kya", start: 13.95, end: 14.15 },
    { text: "hai", start: 14.18, end: 14.35 },
  ],
  [
    { text: "police", start: 14.5, end: 14.9, keyword: true },
    { text: "force", start: 14.95, end: 15.35, keyword: true },
  ],
];

// Section-4 timing, identical to page_bounds() in ffmpeg_proto.py:
// start = first start - 0.04; end = min(last end + 0.9, next start - 0.04); last page holds 1.2 s.
export const PAGE_BOUNDS: { start: number; end: number }[] = PAGES.map((page, i) => {
  const start = page[0].start - 0.04;
  const hold = i === PAGES.length - 1 ? 1.2 : 0.9;
  let end = page[page.length - 1].end + hold;
  if (i + 1 < PAGES.length) end = Math.min(end, PAGES[i + 1][0].start - 0.04);
  return { start, end };
});
