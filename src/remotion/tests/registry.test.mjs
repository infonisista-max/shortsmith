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
