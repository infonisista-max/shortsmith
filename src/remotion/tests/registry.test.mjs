// The registry the style loader cross-checks (decision 9.2): every name in
// registry.json must have a component file and be wired into registry.ts.
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const registry = JSON.parse(readFileSync(join(root, "registry.json"), "utf-8"));

test("registry.json lists unique, sorted component names", () => {
  const names = registry.components;
  assert.ok(Array.isArray(names) && names.length > 0);
  assert.deepEqual(names, [...new Set(names)].sort());
});

test("every registered component has a file and is wired in registry.ts", () => {
  const wiring = readFileSync(join(root, "registry.ts"), "utf-8");
  for (const name of registry.components) {
    const file = join(root, "components", `${name}.tsx`);
    assert.ok(existsSync(file), `missing ${file}`);
    assert.match(wiring, new RegExp(`\\b${name}:`), `${name} not wired in registry.ts`);
  }
});

test("the composition lists captions and pip after ticket 004", () => {
  assert.ok(registry.components.includes("captions"));
  assert.ok(registry.components.includes("pip"));
});

test("the composition lists photo and card after ticket 016", () => {
  assert.ok(registry.components.includes("photo"));
  assert.ok(registry.components.includes("card"));
});

test("the composition lists the set pieces and overlays after ticket 026", () => {
  for (const name of ["hook_cards", "finale", "stamp", "lower_third"]) {
    assert.ok(registry.components.includes(name), `${name} is not registered`);
  }
});

test("the composition lists list, split and wall after ticket 027", () => {
  for (const name of ["list", "split", "wall"]) {
    assert.ok(registry.components.includes(name), `${name} is not registered`);
  }
});

test("the composition lists chart and infographic after ticket 021", () => {
  for (const name of ["chart", "infographic"]) {
    assert.ok(registry.components.includes(name), `${name} is not registered`);
  }
});

test("the composition lists label_flyin and counter after ticket 029", () => {
  for (const name of ["label_flyin", "counter"]) {
    assert.ok(registry.components.includes(name), `${name} is not registered`);
  }
});

test("the composition lists map after ticket 020", () => {
  assert.ok(registry.components.includes("map"), "map is not registered");
});

const MAP_ANIMATIONS = ["pin_drop", "route_arrow", "object_path"];

test("the composition lists the three map animations after ticket 028", () => {
  for (const name of MAP_ANIMATIONS) {
    assert.ok(registry.components.includes(name), `${name} is not registered`);
  }
});

test("the map animations read their timing and pixels from the layout, never a literal (028)", () => {
  const rows = {
    pin_drop: ["delay_s", "pin_drop_s", "pin_drop_px", "label_pop_s"],
    route_arrow: ["route_start_s", "route_draw_s", "route_length_px", "route_path", "arrow_px"],
    object_path: ["object_start_s", "object_travel_s", "segments", "heading_deg", "object_px"],
  };
  for (const [name, fields] of Object.entries(rows)) {
    const source = readFileSync(join(root, "components", `${name}.tsx`), "utf-8");
    for (const field of fields) {
      assert.ok(source.includes(`.${field}`), `${name}.tsx never reads ${field}`);
    }
  }
  // the object follows the route's tangent: the heading comes from the segment, not a guess
  const object = readFileSync(join(root, "components", "object_path.tsx"), "utf-8");
  assert.match(object, /rotate\(\$\{/, "object_path.tsx never turns the sprite");
});

const TRANSITIONS = ["cut", "fade", "whip", "zoom", "spring", "wipe", "flash"];

test("the composition lists the six enter transitions after ticket 030 and flash after 060", () => {
  for (const name of TRANSITIONS) {
    assert.ok(registry.components.includes(name), `${name} is not registered`);
  }
});

test("the flash is drawn over the picture layers and under the pip, overlays and captions (060)", () => {
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  const overlay = short.indexOf("<FlashOverlay");
  assert.ok(overlay > 0, "Short.tsx never draws the FlashOverlay");
  assert.ok(short.lastIndexOf("</Transition>") < overlay, "the flash is under the beat's picture");
  for (const above of ["<Pip ", "<Stamp ", "<Counter ", "<LowerThird", "<TextPop ", "<Bubble",
                       "<Sticker ", "<Captions "]) {
    assert.ok(short.indexOf(above) > overlay, `${above.trim()} is drawn under the flash`);
  }
  // Both sides of the boundary: the next beat's flash rises through this beat's last frames.
  assert.match(short, /flashAt\(frame, spec\.fps, spec\.transitions, beat, next\)/);
  const flash = readFileSync(join(root, "components", "flash.tsx"), "utf-8");
  assert.match(flash, /next\.start_frame - frame/, "the rising half is never drawn");
  assert.match(flash, /frame - beat\.start_frame/, "the falling half is never drawn");
  assert.match(flash, /duration_s \* fps\) \/ 2/, "the flash does not peak on the boundary");
  // A flash never holds the previous beat: its exit is a cut under the colour.
  const enters = readFileSync(join(root, "components", "transitions.tsx"), "utf-8");
  assert.doesNotMatch(enters, /enter === "flash"/, "flash must not hold the previous beat");
});

test("the composition lists text_pop after ticket 061 and draws it over the pip, under the captions", () => {
  assert.ok(registry.components.includes("text_pop"), "text_pop is not registered");
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  const pops = short.indexOf("<TextPop ");
  assert.ok(pops > 0, "Short.tsx never draws TextPop");
  assert.ok(short.indexOf("<Pip ") < pops, "text pops are drawn under the PIP circle");
  assert.ok(pops < short.indexOf("<Captions "), "text pops are drawn over the captions");
  // Every number is the spec's: the landing, the overshoot, the leave and the tilt.
  const source = readFileSync(join(root, "components", "text_pop.tsx"), "utf-8");
  for (const field of ["at_s", "pop_s", "until_s", "rotate_deg", "scale_from", "stroke_px",
                       "drop_px", "font_weight"]) {
    assert.ok(source.includes(`.${field}`), `text_pop.tsx never reads ${field}`);
  }
  assert.match(source, /Easing\.back\(/, "the pop has no overshoot");
});

test("the composition lists bubble after ticket 063 and draws it over the text pops, under the captions", () => {
  assert.ok(registry.components.includes("bubble"), "bubble is not registered");
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  const bubbles = short.indexOf("<Bubble");
  assert.ok(bubbles > 0, "Short.tsx never draws Bubble");
  assert.ok(short.indexOf("<Pip ") < bubbles, "bubbles are drawn under the PIP circle");
  assert.ok(short.indexOf("<TextPop ") < bubbles, "bubbles are drawn under the text pops");
  assert.ok(bubbles < short.indexOf("<Captions "), "bubbles are drawn over the captions");
  // Every number is the spec's: the landing, the overshoot, the leave, the outline path,
  // the trail, the lines and the type treatment.
  const source = readFileSync(join(root, "components", "bubble.tsx"), "utf-8");
  for (const field of ["at_s", "pop_s", "until_s", "scale_from", "path", "dots", "lines",
                       "font_weight", "font_px", "fill", "ink", "stroke_px"]) {
    assert.ok(source.includes(`.${field}`), `bubble.tsx never reads ${field}`);
  }
  assert.match(source, /Easing\.back\(/, "the bubble has no overshoot");
  assert.match(source, /<path/, "the bubble body is not drawn as one path");
  assert.match(source, /<circle/, "the thought trail is never drawn");
});

test("the composition lists sticker after ticket 062 and draws it over the bubbles, under the captions", () => {
  assert.ok(registry.components.includes("sticker"), "sticker is not registered");
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  const stickers = short.indexOf("<Sticker ");
  assert.ok(stickers > 0, "Short.tsx never draws Sticker");
  assert.ok(short.indexOf("<Pip ") < stickers, "stickers are drawn under the PIP circle");
  assert.ok(short.indexOf("<Bubble") < stickers, "stickers are drawn under the bubbles");
  assert.ok(stickers < short.indexOf("<Captions "), "stickers are drawn over the captions");
  // Every number is the spec's: the file, the square, the landing, the overshoot, the
  // float, the shadow and the leave.
  const source = readFileSync(join(root, "components", "sticker.tsx"), "utf-8");
  for (const field of ["src", "left", "top", "size", "at_s", "pop_s", "until_s", "scale_from",
                       "float_px", "float_period_s", "shadow_px"]) {
    assert.ok(source.includes(`.${field}`), `sticker.tsx never reads ${field}`);
  }
  assert.match(source, /Easing\.back\(/, "the sticker has no overshoot");
  assert.match(source, /<Img/, "the sticker PNG is not drawn with Remotion's Img");
  // The driver serves the job's copy of the PNG like any other picture.
  const driver = readFileSync(join(root, "driver.mjs"), "utf-8");
  assert.match(driver, /b\.stickers \?\? \[\]\)\.map\(\(s\) => s\.src\)/,
               "the driver never serves a beat's sticker");  // prettier-ignore
});

test("the composition lists title_strip after ticket 059 and draws it over the overlays, under the captions", () => {
  assert.ok(registry.components.includes("title_strip"), "title_strip is not registered");
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  const strip = short.indexOf("<TitleStrip ");
  assert.ok(strip > 0, "Short.tsx never draws TitleStrip");
  assert.ok(short.indexOf("<Sticker ") < strip, "the strip is drawn under the stickers");
  assert.ok(strip < short.indexOf("<Captions "), "the strip is drawn over the captions");
  // Every number is the spec's: the box, the type, the colours, the slide and the leave.
  const source = readFileSync(join(root, "components", "title_strip.tsx"), "utf-8");
  for (const field of ["text", "left", "top", "width", "height", "font_px", "font_weight",
                       "fill", "ink", "slide_s", "until_frame"]) {
    assert.ok(source.includes(`.${field}`), `title_strip.tsx never reads ${field}`);
  }
});

test("the composition lists clip after ticket 058 and draws it muted in the photo's layer", () => {
  assert.ok(registry.components.includes("clip"), "clip is not registered");
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  const clip = short.indexOf("<Clip ");
  assert.ok(clip > 0, "Short.tsx never draws Clip");
  assert.ok(clip < short.indexOf("<Pip "), "the clip is drawn over the PIP circle");
  assert.ok(clip < short.indexOf("<Captions "), "the clip is drawn over the captions");
  assert.ok(clip < short.indexOf("<Stamp "), "the clip is drawn over the stamp");
  // Every number is the spec's: the speed, the start offset and the push; never a sound.
  const source = readFileSync(join(root, "components", "clip.tsx"), "utf-8");
  for (const field of ["speed", "start_s", "scale_from", "scale_to", "zoom", "focus_x"]) {
    assert.ok(source.includes(`.${field}`), `clip.tsx never reads ${field}`);
  }
  assert.match(source, /\bmuted\b/, "the clip is not muted");
  assert.match(source, /playbackRate=\{visual\.speed\}/, "the speed is not the spec's");
  assert.match(source, /trimBefore=/, "the clip never starts where the spec says");
  // The driver serves video files, so a clip's file reaches Chrome like the presenter cut.
  const driver = readFileSync(join(root, "driver.mjs"), "utf-8");
  assert.match(driver, /"\.mp4": "video\/mp4"/, "the driver does not serve .mp4");
  assert.match(driver, /b\.visual \? \[b\.visual\.src\]/, "the driver never serves a beat's visual");
});

test("the registry holds the whole tier-1 set the explainer requires (030)", () => {
  const tier1 = ["captions", "pip", "photo", "card", "clip", "stamp", "lower_third", "hook_cards",
                 "finale", "list", "chart", "split", "wall", "infographic", "label_flyin",
                 "counter", "map", ...MAP_ANIMATIONS, ...TRANSITIONS];
  for (const name of tier1) {
    assert.ok(registry.components.includes(name), `${name} is not registered`);
  }
});

test("Short.tsx draws every registered component", () => {
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  const enters = readFileSync(join(root, "components", "transitions.tsx"), "utf-8");
  const drawn = { hook_cards: "HookCards", finale: "Finale", stamp: "Stamp",
                  lower_third: "LowerThird", photo: "Photo", card: "Card", clip: "Clip",
                  captions: "Captions", pip: "Pip", list: "List", split: "Split",
                  wall: "Wall", chart: "Chart", infographic: "Infographic",
                  label_flyin: "LabelFlyin", counter: "Counter", map: "MapBase",
                  pin_drop: "PinDrop", route_arrow: "RouteArrow", object_path: "ObjectPath",
                  text_pop: "TextPop", bubble: "Bubble", sticker: "Sticker",
                  title_strip: "TitleStrip" };
  // The transitions are drawn through the `Transition` dispatcher, one entry each.
  assert.match(short, /<Transition\b/, "Short.tsx never wraps a beat in a Transition");
  for (const name of registry.components) {
    if (TRANSITIONS.includes(name)) {
      assert.match(enters, new RegExp(`\\b${name}: `), `transitions.tsx never maps ${name}`);
      continue;
    }
    assert.match(short, new RegExp(`<${drawn[name]}\\b`), `Short.tsx never draws ${name}`);
  }
});

test("the transition dispatcher refuses an enter outside the style's list (9.4)", () => {
  const enters = readFileSync(join(root, "components", "transitions.tsx"), "utf-8");
  assert.match(enters, /numbers\.enabled\.includes\(enter\)/, "the enabled list is never read");
  assert.match(enters, /throw new Error\(/, "an enter outside the list is not refused");
});

test("every transition reads its numbers from the spec, never a literal (9.4)", () => {
  const rows = { fade: ["duration_s"], whip: ["duration_s", "blur_px"],
                 zoom: ["duration_s", "scale_from"],
                 spring: ["damping", "stiffness", "mass"], wipe: ["duration_s"],
                 flash: ["duration_s", "color"] };
  for (const [name, fields] of Object.entries(rows)) {
    const source = readFileSync(join(root, "components", `${name}.tsx`), "utf-8");
    assert.ok(source.includes(`numbers.${name}`), `${name}.tsx never reads numbers.${name}`);
    for (const field of fields) {
      assert.ok(source.includes(field), `${name}.tsx never reads ${field}`);
    }
  }
  const cut = readFileSync(join(root, "components", "cut.tsx"), "utf-8");
  assert.doesNotMatch(cut, /interpolate|spring\(/, "cut has no motion");
});

test("only fade and wipe hold the previous beat beneath (exit is cut or fade)", () => {
  const enters = readFileSync(join(root, "components", "transitions.tsx"), "utf-8");
  assert.match(enters, /enter === "fade" \|\| enter === "wipe"/);
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  assert.match(short, /holdsPrevious\(beat\.enter\)/, "Short.tsx never holds the previous beat");
});

test("the driver serves the asset image types", () => {
  const driver = readFileSync(join(root, "driver.mjs"), "utf-8");
  for (const ext of [".png", ".jpg", ".jpeg", ".webp"]) {
    assert.match(driver, new RegExp(`"\\${ext}": "image/`), `driver does not serve ${ext}`);
  }
});

test("the driver rewrites the set pieces' card sources to served URLs", () => {
  const driver = readFileSync(join(root, "driver.mjs"), "utf-8");
  assert.match(driver, /hook\?\.cards/, "hook cards are never collected");
  assert.match(driver, /finale\?\.cards/, "finale cards are never collected");
  assert.match(driver, /cards: piece\.cards\.map/, "set-piece card srcs are never rewritten");
});

test("the driver serves the list, split and wall assets too (027)", () => {
  const driver = readFileSync(join(root, "driver.mjs"), "utf-8");
  assert.match(driver, /wall\?\.cells/, "wall cells are never collected");
  assert.match(driver, /split\?\.panes/, "split panes are never collected");
  assert.match(driver, /split\?\.badge/, "the split badge is never collected");
  assert.match(driver, /list\?\.rows/, "list row icons are never collected");
  assert.match(driver, /cells: piece\.cells\.map/, "wall cell srcs are never rewritten");
  assert.match(driver, /icon_src: url\(r\.icon_src\)/, "list icons are never rewritten");
  assert.match(driver, /panes: piece\.panes\.map/, "split pane srcs are never rewritten");
});

test("the driver serves the labelled diagram's base picture (021)", () => {
  const driver = readFileSync(join(root, "driver.mjs"), "utf-8");
  assert.match(driver, /infographic\?\.src/, "the diagram base is never collected");
  assert.match(
    driver,
    /infographic: \{ \.\.\.b\.infographic, src: url\(b\.infographic\.src\) \}/,
    "the diagram base src is never rewritten",
  );
});
