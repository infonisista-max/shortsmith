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

test("the map draws every label pill before every dot, so no dot is ever hidden (072)", () => {
  for (const name of ["map", "pin_drop"]) {
    const source = readFileSync(join(root, "components", `${name}.tsx`), "utf-8");
    const pills = source.indexOf("<MarkerPill");
    const dots = source.indexOf("<MarkerDot");
    assert.ok(pills > 0 && dots > 0, `${name}.tsx does not draw pills and dots apart`);
    assert.ok(pills < dots, `${name}.tsx draws a dot before the pills`);
    assert.equal(source.lastIndexOf("<MarkerPill"), pills, `${name}.tsx draws pills twice`);
    assert.doesNotMatch(source, /<Marker\s/, `${name}.tsx still draws a dot and pill together`);
  }
});

const TRANSITIONS = ["cut", "fade", "whip", "zoom", "spring", "wipe", "flash", "light_flare"];

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

test("the composition lists highlight after ticket 078 and draws it inside the card, under the circle", () => {
  assert.ok(registry.components.includes("highlight"), "highlight is not registered");
  const card = readFileSync(join(root, "components", "card.tsx"), "utf-8");
  // Inside the card's image box, after the picture: it moves with the card's push.
  assert.ok(card.indexOf("<Framed visual={visual}") < card.indexOf("<Highlight "),
            "the marker is drawn under the screenshot");  // prettier-ignore
  assert.match(card, /card\.origin_x/, "the card never pushes about its origin");
  assert.match(card, /card\.origin_y/, "the card never pushes about its origin");
  // The card is the beat's picture, drawn before the PIP circle and the captions.
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  assert.ok(short.indexOf("<Card ") < short.indexOf("<Pip "), "the card is drawn over the circle");
  // Every number is the spec's: the boxes, the times, the colour and the opacity.
  const source = readFileSync(join(root, "components", "highlight.tsx"), "utf-8");
  for (const field of ["lines", "left", "top", "width", "height", "start_s", "end_s", "color",
                       "opacity"]) {
    assert.ok(source.includes(`.${field}`), `highlight.tsx never reads ${field}`);
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
                  title_strip: "TitleStrip", backdrop: "Backdrop", crop_fill: "CropFill",
                  polaroid: "Polaroid", banner: "Banner", calendar: "Calendar",
                  particles: "Particles" };
  // The transitions are drawn through the `Transition` dispatcher, one entry each.
  assert.match(short, /<Transition\b/, "Short.tsx never wraps a beat in a Transition");
  // 078: the highlight is drawn inside the screenshot's card, which Short.tsx draws.
  const card = readFileSync(join(root, "components", "card.tsx"), "utf-8");
  for (const name of registry.components) {
    if (TRANSITIONS.includes(name)) {
      assert.match(enters, new RegExp(`\\b${name}: `), `transitions.tsx never maps ${name}`);
      continue;
    }
    if (name === "highlight") {
      assert.match(card, /<Highlight\b/, "card.tsx never draws the highlight");
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

test("the map fills the named country, names the countries and draws the target circle (104)", () => {
  const source = readFileSync(join(root, "components", "map.tsx"), "utf-8");
  // every number and colour is the layout's: the fill, the names, the circle and its tag
  for (const field of ["highlight", "highlight_color", "names", "name_color", "font_px",
                       "target", "radius", "stroke_px", "draw_s", "tag", "tag_left", "tag_top",
                       "tag_width", "tag_height", "tag_font_px", "tag_fill", "tag_ink",
                       "rotate_deg", "slide_s"]) {
    assert.ok(source.includes(`.${field}`), `map.tsx never reads ${field}`);
  }
  assert.match(source, /<circle/, "the target circle is never drawn");
  assert.match(source, /strokeDashoffset/, "the target circle is never drawn on");
  assert.match(source, /rotate\(\$\{/, "the tag is never turned");
  // the fill sits on the land and under the borders; the markers are drawn over it all
  const fill = source.indexOf("(spec.highlight ?? []).map");
  assert.ok(fill > source.indexOf("spec.land.map"), "the fill is drawn under the land");
  assert.ok(fill < source.indexOf("spec.borders.map"), "the fill hides the borders");
  assert.ok(source.indexOf("<TargetCircle") < source.indexOf("<MarkerPill"),
            "the target circle is drawn over the markers");  // prettier-ignore
  // 104: the object stops beside the endpoint dot, never on it
  const object = readFileSync(join(root, "components", "object_path.tsx"), "utf-8");
  assert.ok(object.includes(".object_end_t"), "object_path.tsx never stops short of the dot");
});

test("the split frames each pane round its face with objectPosition (105)", () => {
  const source = readFileSync(join(root, "components", "split.tsx"), "utf-8");
  assert.match(source, /objectPosition:/, "split.tsx never sets objectPosition");
  for (const field of ["focus_x", "focus_y"]) {
    assert.ok(source.includes(`pane.${field}`), `split.tsx never reads ${field}`);
  }
  // the badge keeps its own centre crop; only the panes move
  assert.equal(source.match(/objectPosition:/g)?.length, 1);
});

const TREATMENTS = { backdrop: "Backdrop", crop_fill: "CropFill", polaroid: "Polaroid" };

test("the picture treatments are registered and each is drawn for its treatment (103)", () => {
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  for (const [name, tag] of Object.entries(TREATMENTS)) {
    assert.ok(registry.components.includes(name), `${name} is not registered`);
    assert.match(short, new RegExp(`treatment === "${name}"`), `Short.tsx never draws ${name}`);
    assert.ok(short.includes(`<${tag} `), `Short.tsx never renders <${tag}>`);
  }
  // every treatment is drawn under the PIP circle, like the photo and the card
  const pip = short.indexOf("<Pip ");
  for (const tag of Object.values(TREATMENTS)) {
    assert.ok(short.indexOf(`<${tag} `) < pip, `<${tag}> is drawn over the PIP circle`);
  }
});

test("the treatments read every number from the spec, never a literal (103)", () => {
  const rows = {
    // the body the card, the backdrop and the polaroid share
    card: ["cover_blur_px", "cover_brightness", "cover_scale_from", "cover_scale_to",
           "scale_from", "scale_to", "rotate_deg", "border_px"],
    polaroid: ["drop_px", "drop_s", "shadow_px", "rotate_deg"],
    crop_fill: ["scale_from", "scale_to"],
    // Framed: the objectPosition and transform origin crop_fill frames the face with
    photo: ["focus_x", "focus_y"],
  };
  for (const [name, fields] of Object.entries(rows)) {
    const source = readFileSync(join(root, "components", `${name}.tsx`), "utf-8");
    for (const field of fields) {
      assert.ok(source.includes(`.${field}`), `${name}.tsx never reads ${field}`);
    }
  }
  // the backdrop and the polaroid stand over their own blurred copy (the card's body)
  for (const name of ["backdrop", "polaroid"]) {
    const source = readFileSync(join(root, "components", `${name}.tsx`), "utf-8");
    assert.match(source, /<CardBody/, `${name}.tsx does not draw the shared card body`);
    assert.match(source, new RegExp(`treatment !== "${name}"`), `${name}.tsx draws any box`);
  }
  // the print drops and settles with an overshoot, a soft shadow under it
  const polaroid = readFileSync(join(root, "components", "polaroid.tsx"), "utf-8");
  assert.match(polaroid, /Easing\.back\(/, "the polaroid drop has no settle");
  assert.match(polaroid, /translateY\(/, "the polaroid never drops");
  const card = readFileSync(join(root, "components", "card.tsx"), "utf-8");
  assert.match(card, /\$\{lift\} rotate\(/, "the body never applies the polaroid's drop");
  // crop_fill draws the framed image, full screen, pushing toward the face
  const crop = readFileSync(join(root, "components", "crop_fill.tsx"), "utf-8");
  assert.match(crop, /<Framed/, "crop_fill.tsx does not draw the framed image");
});

test("the full-screen stills draw the move's drift both ways and its origin (102)", () => {
  const photo = readFileSync(join(root, "components", "photo.tsx"), "utf-8");
  for (const field of ["pan_px", "pan_y_px", "origin_x", "origin_y", "scale_from", "scale_to"]) {
    assert.ok(photo.includes(`.${field}`), `photo.tsx never reads ${field}`);
  }
  assert.match(photo, /translateY\(/, "photo.tsx never drifts the picture up or down");
  // crop_fill takes the planner's move too: its push, both drifts, its face-centred origin
  const cropFill = readFileSync(join(root, "components", "crop_fill.tsx"), "utf-8");
  for (const field of ["scale_from", "scale_to", "pan_px", "pan_y_px"]) {
    assert.ok(cropFill.includes(`.${field}`), `crop_fill.tsx never reads ${field}`);
  }
  const types = readFileSync(join(root, "types.ts"), "utf-8");
  for (const field of ["pan_y_px", "origin_x", "origin_y", "grade"]) {
    assert.ok(types.includes(`  ${field}: `), `VisualSpec has no ${field}`);
  }
});

test("the era grade is a filter from the spec on every picture and clip (102)", () => {
  const photo = readFileSync(join(root, "components", "photo.tsx"), "utf-8");
  assert.match(photo, /export function gradeFilter/, "photo.tsx has no gradeFilter");
  for (const field of ["sepia", "saturate", "contrast"]) {
    assert.ok(photo.includes(`grade.${field}`), `gradeFilter never reads grade.${field}`);
  }
  // Framed draws every still (photo, crop_fill, the card's image and cover), so the grade
  // is applied there; the clip applies it to its video
  assert.match(photo, /gradeFilter\(visual\)/, "Framed never applies the grade");
  const clip = readFileSync(join(root, "components", "clip.tsx"), "utf-8");
  assert.match(clip, /gradeFilter\(visual\)/, "clip.tsx never applies the grade");
  // no strength is written in the component: every number comes from the spec
  assert.doesNotMatch(photo, /sepia\(0\.\d/, "a literal sepia strength in photo.tsx");
});

test("the banner slides in from its side, clipped to its box, every number the spec's (107)", () => {
  assert.ok(registry.components.includes("banner"), "banner is not registered");
  const source = readFileSync(join(root, "components", "banner.tsx"), "utf-8");
  for (const field of ["left", "top", "width", "height", "font_px", "font_weight", "fill", "ink",
                       "bar", "bar_px", "from_top", "at_s", "slide_s", "until_s"]) {
    assert.ok(source.includes(`.${field}`), `banner.tsx never reads ${field}`);
  }
  assert.match(source, /overflow: "hidden"/, "the banner is not clipped to its own box");
  assert.match(source, /translateY\(/, "the banner never slides");
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  // with the landed overlays: over the PIP circle's layer, under the text pops and captions
  const banner = short.indexOf("<Banner ");
  assert.ok(banner > short.indexOf("<Pip "), "the banner is drawn under the PIP circle");
  assert.ok(banner < short.indexOf("<TextPop "), "the banner is drawn over the text pops");
  assert.ok(banner < short.indexOf("<Captions "), "the banner is drawn over the captions");
});

test("the light flare is an enter drawn like the flash, over the pictures only (107)", () => {
  assert.ok(registry.components.includes("light_flare"), "light_flare is not registered");
  const enters = readFileSync(join(root, "components", "transitions.tsx"), "utf-8");
  assert.match(enters, /light_flare: LightFlare/, "light_flare is not an enter");
  const source = readFileSync(join(root, "components", "light_flare.tsx"), "utf-8");
  for (const field of ["duration_s", "core", "glow", "from_x", "to_x", "y"]) {
    assert.ok(source.includes(`.${field}`), `light_flare.tsx never reads ${field}`);
  }
  assert.match(source, /mixBlendMode: "screen"/, "the flare does not burn to light");
  assert.match(source, /radial-gradient/, "the flare is not a burst");
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  const flare = short.indexOf("<LightFlareOverlay");
  assert.ok(flare > short.indexOf("<Transition"), "the flare is drawn under the picture");
  assert.ok(flare < short.indexOf("<Pip "), "the flare is drawn over the PIP circle");
  assert.ok(flare < short.indexOf("<Captions "), "the flare is drawn over the captions");
});

test("the calendar peels from one date to the next on the spoken word (108)", () => {
  assert.ok(registry.components.includes("calendar"), "calendar is not registered");
  const source = readFileSync(join(root, "components", "calendar.tsx"), "utf-8");
  for (const field of ["from_text", "to_text", "left", "top", "width", "height", "header_px",
                       "font_px", "page", "ink", "header", "header_ink", "appear_s",
                       "flip_start_s", "land_s", "until_s"]) {
    assert.ok(source.includes(`.${field}`), `calendar.tsx never reads ${field}`);
  }
  assert.match(source, /rotateX\(/, "the page never peels");
  assert.match(source, /transformOrigin: "50% 0"/, "the page does not peel about its binding");
  // the peel is 1 from the landing on: the new date is flat on the spoken word
  assert.match(source, /t >= spec\.land_s/, "the peel does not end on the landing");
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  const calendar = short.indexOf("<Calendar ");
  assert.ok(calendar > short.indexOf("<Pip "), "the calendar is drawn under the PIP circle");
  assert.ok(calendar < short.indexOf("<Captions "), "the calendar is drawn over the captions");
});

test("the cash and brain particles are drawn in code inside their box (109)", () => {
  assert.ok(registry.components.includes("particles"), "particles is not registered");
  const source = readFileSync(join(root, "components", "particles.tsx"), "utf-8");
  for (const field of ["kind", "left", "top", "width", "height", "count", "size_px", "fall_s",
                       "fade_s", "opacity", "colors", "at_s", "until_s"]) {
    assert.ok(source.includes(`.${field}`), `particles.tsx never reads ${field}`);
  }
  assert.match(source, /overflow: "hidden"/, "the pieces may leave their box");
  assert.doesNotMatch(source, /staticFile|<Img/, "the overlay uses a stock asset");
  assert.doesNotMatch(source, /Math\.random/, "the pieces are not repeatable frame to frame");
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  const particles = short.indexOf("<Particles ");
  assert.ok(particles > short.indexOf("<Transition"), "the particles are under the picture");
  assert.ok(particles < short.indexOf("<Pip "), "the particles are drawn over the PIP circle");
  assert.ok(particles < short.indexOf("<Captions "), "the particles are drawn over the captions");
});

test("the driver serves every media type a stray asset could carry (111b)", () => {
  const driver = readFileSync(join(root, "driver.mjs"), "utf-8");
  const types = {
    ".gif": "image/gif",
    ".webm": "video/webm",
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".mp4": "video/mp4",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
  };
  for (const [ext, type] of Object.entries(types)) {
    assert.ok(driver.includes(`"${ext}": "${type}"`), `${ext} is not served as ${type}`);
  }
});

test("a list or wall base that is a clip plays under the same scrim (111b)", () => {
  const clip = readFileSync(join(root, "components", "clip.tsx"), "utf-8");
  assert.match(clip, /<Video/);
  assert.match(clip, /visual\.dim > 0/);
});
