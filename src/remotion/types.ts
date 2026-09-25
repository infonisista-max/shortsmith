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
  // The black scrim over the still: 0 on a photo or card beat, the style's
  // broll.motion.<kind>.dim where it is only a set piece's base (027).
  dim: number;
  card: CardSpec | null;
};

// Set pieces and overlays (ticket 026): everything is already placed and measured in
// composition pixels; the components below animate the boxes, they never lay them out.

export type CardBox = {
  src: string;
  width: number;
  height: number;
  left: number;
  top: number;
  box_width: number;
  box_height: number;
  image_width: number;
  image_height: number;
  border_px: number;
  rotate_deg: number;
  label: string;
  strip_px: number;
  strip_font_px: number;
  from_x: number;
  from_y: number;
  delay_s: number;
  // The Ken Burns inside the window: 1 to 1 on a hook or finale card, the style's
  // photo motion on a wall cell (027).
  scale_from: number;
  scale_to: number;
};

export type HookCardsSpec = {
  title_lines: string[];
  title_font_px: number;
  title_top: number;
  title_line_px: number;
  title_color: string;
  cards: CardBox[];
  spring_s: number;
};

export type FinaleCardSpec = {
  text: string;
  text_font_px: number;
  text_top: number;
  text_color: string;
  circle_left: number;
  circle_top: number;
  circle_diameter: number;
  ring_px: number;
  ring_color: string;
  cards: CardBox[];
  fade_s: number;
};

export type StampSpec = {
  text: string;
  left: number;
  top: number;
  width: number;
  height: number;
  rotate_deg: number;
  font_px: number;
  border_px: number;
  radius_px: number;
  color: string;
  fill: string;
  scale_from: number;
  land_s: number;
  shake_s: number;
};

// 029: the counter is the stamp's box with the digits of every frame of its beat; the
// target lands from `land_frame`.
export type CounterSpec = StampSpec & {
  texts: string[];
  land_frame: number;
};

export type LowerThirdSpec = {
  name: string;
  role: string;
  left: number;
  top: number;
  width: number;
  height: number;
  bar_px: number;
  accent: string;
  fill: string;
  name_font_px: number;
  role_font_px: number;
  fade_s: number;
};

// The three remaining tier-1 set pieces (ticket 027): the list's rows, the news-card
// split and the wall grid, all placed and measured in Python.

export type ListRow = {
  text: string;
  font_px: number;
  left: number;
  top: number;
  width: number;
  height: number;
  text_left: number;
  icon_src: string;
  icon_width: number;
  icon_height: number;
  icon_left: number;
  icon_size: number;
  from_x: number;
  delay_s: number;
};

export type ListSpec = {
  header: string;
  header_font_px: number;
  header_left: number;
  header_top: number;
  header_color: string;
  rows: ListRow[];
  row_fill: string;
  row_radius_px: number;
  spring_s: number;
};

export type TitleWord = {
  text: string;
  left: number;
  width: number;
  highlight: boolean;
};

export type SplitPane = {
  src: string;
  width: number;
  height: number;
  left: number;
  top: number;
  pane_width: number;
  pane_height: number;
  label: string;
  from_x: number;
};

export type BadgeSpec = {
  src: string;
  width: number;
  height: number;
  left: number;
  top: number;
  diameter: number;
  ring_px: number;
  ring_color: string;
};

export type SplitSpec = {
  left: number;
  top: number;
  width: number;
  height: number;
  border_px: number;
  rotate_deg: number;
  seam_px: number;
  panes: SplitPane[];
  label_px: number;
  label_font_px: number;
  title_px: number;
  title_font_px: number;
  title_color: string;
  title_words: TitleWord[];
  highlight_fg: string;
  highlight_bg: string;
  highlight_pad_px: number;
  highlight_radius_px: number;
  badge: BadgeSpec | null;
  slide_s: number;
};

export type WallSpec = {
  cells: CardBox[];
  columns: number;
  spring_s: number;
};

// The two infographic kinds (ticket 021): the chart is drawn from the planner's series
// and the diagram's labels are drawn in code over a label-free base, both measured and
// placed by `shortsmith.infographics`.

export type ChartMark = {
  label: string;
  value: number;
  value_text: string;
  left: number;
  width: number;
  bar_left: number;
  bar_top: number;
  bar_width: number;
  bar_height: number;
  point_x: number;
  point_y: number;
  color: string;
  delay_s: number;
};

export type ChartLayout = {
  form: "bar" | "line" | "comparison";
  title: string;
  title_font_px: number;
  title_top: number;
  title_color: string;
  plot_left: number;
  plot_top: number;
  plot_width: number;
  plot_height: number;
  baseline_y: number;
  baseline_px: number;
  axis_color: string;
  label_top: number;
  label_font_px: number;
  value_font_px: number;
  dot_px: number;
  marks: ChartMark[];
  grow_s: number;
};

export type DiagramLabel = {
  text: string;
  left: number;
  top: number;
  width: number;
  height: number;
  font_px: number;
  anchor: "left" | "center" | "right";
  delay_s: number;
  // 029: the offset past the nearest frame edge the label springs in from.
  from_x: number;
  from_y: number;
};

export type DiagramLayout = {
  src: string;
  width: number;
  height: number;
  left: number;
  top: number;
  box_width: number;
  box_height: number;
  zoom: number;
  focus_x: number;
  focus_y: number;
  scale_from: number;
  scale_to: number;
  dim: number;
  labels: DiagramLabel[];
  fill: string;
  radius_px: number;
  text_color: string;
  fly_s: number;
};

// The map (ticket 020): the base as SVG path strings already projected, clipped and
// simplified by `shortsmith.infographics.resolve_map`, the markers at their geocoded
// points with measured label pills, and the route polyline 028 animates.

export type MapMarkerLayout = {
  name: string;
  lat: number;
  lon: number;
  x: number;
  y: number;
  label_left: number;
  label_top: number;
  label_width: number;
  label_height: number;
  label_font_px: number;
  delay_s: number;
  source: string;
};

export type MapLayout = {
  region: string;
  bbox: [number, number, number, number];
  left: number;
  top: number;
  width: number;
  height: number;
  scale: number;
  center_lon: number;
  center_merc: number;
  center_x: number;
  center_y: number;
  land: string[];
  coast: string[];
  borders: string[];
  land_color: string;
  coast_color: string;
  border_color: string;
  coast_px: number;
  border_px: number;
  markers: MapMarkerLayout[];
  route: [number, number][];
  object: "plane" | "ship" | "arrow" | null;
  marker_color: string;
  dot_px: number;
  ring_px: number;
  label_fill: string;
  label_radius_px: number;
  text_color: string;
  draw_s: number;
};

export type PunchIn = {
  scale_from: number;
  settle_to: number;
  settle_s: number;
  origin_y: number;
  contrast: number;
  saturate: number;
};

export type BeatSpec = {
  id: string;
  start_frame: number;
  end_frame: number;
  mode: Mode;
  kind: string;
  enter: string;
  visual?: VisualSpec | null;
  punch_in?: PunchIn | null;
  stamp?: StampSpec | null;
  lower_third?: LowerThirdSpec | null;
  hook?: HookCardsSpec | null;
  finale?: FinaleCardSpec | null;
  split?: SplitSpec | null;
  wall?: WallSpec | null;
  list?: ListSpec | null;
  chart?: ChartLayout | null;
  infographic?: DiagramLayout | null;
  map?: MapLayout | null;
  counter?: CounterSpec | null;
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

// 030: the 9.4 enter vocabulary - the style's enabled subset and every row's numbers,
// read from the style front matter (`broll.transitions`); `cut` has no numbers.
export type TransitionStyle = {
  enabled: string[];
  fade: { duration_s: number };
  whip: { duration_s: number; blur_px: number };
  zoom: { duration_s: number; scale_from: number };
  spring: { damping: number; stiffness: number; mass: number };
  wipe: { duration_s: number };
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
  transitions: TransitionStyle;
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
  transitions: {
    enabled: ["cut"],
    fade: { duration_s: 0.35 },
    whip: { duration_s: 0.22, blur_px: 14 },
    zoom: { duration_s: 0.3, scale_from: 1.6 },
    spring: { damping: 14, stiffness: 160, mass: 0.7 },
    wipe: { duration_s: 0.25 },
  },
};
