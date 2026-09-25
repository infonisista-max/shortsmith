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

test("Short.tsx draws every registered component", () => {
  const short = readFileSync(join(root, "Short.tsx"), "utf-8");
  const drawn = { hook_cards: "HookCards", finale: "Finale", stamp: "Stamp",
                  lower_third: "LowerThird", photo: "Photo", card: "Card",
                  captions: "Captions", pip: "Pip", list: "List", split: "Split",
                  wall: "Wall", chart: "Chart", infographic: "Infographic",
                  label_flyin: "LabelFlyin", counter: "Counter", map: "MapBase" };
  for (const name of registry.components) {
    assert.match(short, new RegExp(`<${drawn[name]}\\b`), `Short.tsx never draws ${name}`);
  }
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
