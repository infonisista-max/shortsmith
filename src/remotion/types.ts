// The composition's props: a mirror of `shortsmith.contracts.RenderSpec` (Python is
// the source of truth; the Python bridge writes work/render_spec.json and the
// driver passes it as inputProps). Keep field names identical to the Pydantic model.

export type Mode = "full" | "pip" | "off";

export type WordBox = {
  text: string;
  start: number;
  end: number;
  x: number;
  y: number;
  width: number;
  height: number;
  keyword: boolean;
};

export type CaptionPageSpec = {
  index: number;
  start: number;
  end: number;
  lines: number;
  words: WordBox[];
};

export type CardSpec = {
  left: number;
  top: number;
  width: number;
  height: number;
  image_width: number;
  image_height: number;
  border_px: number;
  rotate_deg: number;
  strip_text: string;
  strip_px: number;
  strip_font_px: number;
  cover_scale_from: number;
  cover_scale_to: number;
  cover_blur_px: number;
  cover_brightness: number;
  ring: boolean;
  ring_color: string;
  ring_diameter_px: number;
  ring_px: number;
  ring_at_s: number;
};

export type VisualSpec = {
  treatment: "photo" | "card";
  src: string;
  width: number;
  height: number;
  zoom: number;
  focus_x: number;
  focus_y: number;
  scale_from: number;
  scale_to: number;
  pan_px: number;
  card: CardSpec | null;
};

export type BeatSpec = {
  id: string;
  start_frame: number;
  end_frame: number;
  mode: Mode;
  kind: string;
  enter: string;
  visual?: VisualSpec | null;
};

export type PipGeometry = {
  left: number;
  top: number;
  diameter: number;
  ring_px: number;
  ring_color: string;
  window_left: number;
  window_top: number;
  window_size: number;
};

export type Palette = {
  gradient: string[];
  angle_deg: number;
  accent: string;
};

export type CaptionStyle = {
  font_family: string;
  font_weight: number;
  size_px: number;
  line_height: number;
  letter_spacing_px: number;
  anchor_y: number;
  max_lines: number;
  max_width_px: number;
  word_gap_px: number;
  unspoken_alpha: number;
  active_color: string;
  active_scale: number;
  active_scale_s: number;
  keyword_fg: string;
  keyword_bg: string;
  keyword_pad_px: number;
  keyword_radius_px: number;
  enter_scale_from: number;
  enter_s: number;
  enter_opacity_s: number;
  stroke_px: number;
  drop_px: number;
  glow_px: number;
};

export type RenderSpec = {
  width: number;
  height: number;
  fps: number;
  frames: number;
  presenter: string;
  source_width: number;
  source_height: number;
  beats: BeatSpec[];
  captions: CaptionPageSpec[];
  // Beats a two-line caption page shows over; lower-thirds are suppressed there (6.3, 026).
  beats_with_two_lines: string[];
  pip: PipGeometry;
  palette: Palette;
  caption_style: CaptionStyle;
};

// What the Studio shows with no spec: one second of gradient, no presenter.
export const EMPTY_SPEC: RenderSpec = {
  width: 1080,
  height: 1920,
  fps: 30,
  frames: 30,
  presenter: "",
  source_width: 1080,
  source_height: 1920,
  beats: [{ id: "b01", start_frame: 0, end_frame: 30, mode: "off", kind: "finale", enter: "cut" }],
  captions: [],
  beats_with_two_lines: [],
  pip: {
    left: 60,
    top: 960,
    diameter: 300,
    ring_px: 6,
    ring_color: "#FFFFFF",
    window_left: 0,
    window_top: 0,
    window_size: 1080,
  },
  palette: { gradient: ["#0B1D3A", "#1F3B73"], angle_deg: 160, accent: "#FFD60A" },
  caption_style: {
    font_family: "Poppins",
    font_weight: 800,
    size_px: 74,
    line_height: 1.35,
    letter_spacing_px: 0.5,
    anchor_y: 1460,
    max_lines: 2,
    max_width_px: 960,
    word_gap_px: 22,
    unspoken_alpha: 0.86,
    active_color: "#FFD60A",
    active_scale: 1.08,
    active_scale_s: 0.1,
    keyword_fg: "#111",
    keyword_bg: "#FFD60A",
    keyword_pad_px: 14,
    keyword_radius_px: 14,
    enter_scale_from: 0.94,
    enter_s: 0.12,
    enter_opacity_s: 0.06,
    stroke_px: 2,
    drop_px: 3,
    glow_px: 18,
  },
};
