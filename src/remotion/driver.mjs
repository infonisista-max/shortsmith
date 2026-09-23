// The render driver the Python bridge runs (decision 9.1, ticket 004):
//
//   node src/remotion/driver.mjs render --spec <render_spec.json> --out <picture.mp4>
//                                      [--concurrency 2]
//   node src/remotion/driver.mjs bundle
//
// `render` bundles the composition once into build/remotion/ (reused while the
// sources are unchanged), serves the presenter and every beat's asset image (ticket
// 016) from their common directory over a local loopback HTTP server with Range
// support (Remotion only reads URLs and public files), and renders through
// @remotion/renderer with the 9.1 settings: concurrency 2, bt709, muted H.264.
//
// Protocol on stdout, one line each, nothing else:
//   progress <rendered>/<total>      whenever the rendered frame count changes
//   done frames=<n> render_s=<x> bundle_s=<y>
// Everything else (Remotion logs, bundler output) goes to stderr.

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { ensureBrowser, renderMedia, selectComposition } = require("@remotion/renderer");

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");
const ENTRY = path.join(HERE, "index.ts");
const BUNDLE_DIR = path.join(ROOT, "build", "remotion");
const STAMP = path.join(BUNDLE_DIR, ".shortsmith-stamp");
const COMPOSITION_ID = "Short";
const MIME = {
  ".mp4": "video/mp4",
  ".mov": "video/quicktime",
  ".m4v": "video/mp4",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
};

function log(line) {
  process.stderr.write(`${line}\n`);
}

function out(line) {
  process.stdout.write(`${line}\n`);
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a.startsWith("--")) {
      args[a.slice(2)] = argv[i + 1];
      i += 1;
    } else {
      args._.push(a);
    }
  }
  return args;
}

// --- bundle -----------------------------------------------------------------------------

function walk(dir, skip) {
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (skip.some((s) => full.startsWith(s))) continue;
    if (entry.isDirectory()) files.push(...walk(full, skip));
    else files.push(full);
  }
  return files.sort();
}

function sourceHash() {
  const hash = createHash("sha1");
  const inputs = [
    ...walk(HERE, [path.join(HERE, "tests")]),
    path.join(ROOT, "remotion.config.ts"),
    path.join(ROOT, "package-lock.json"),
    ...walk(path.join(ROOT, "assets"), []),
  ];
  for (const file of inputs) {
    hash.update(path.relative(ROOT, file));
    hash.update(fs.readFileSync(file));
  }
  return hash.digest("hex");
}

function remotionCli() {
  const pkgPath = require.resolve("@remotion/cli/package.json");
  const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf-8"));
  return path.join(path.dirname(pkgPath), pkg.bin.remotion);
}

function ensureBundle() {
  const started = performance.now();
  const wanted = sourceHash();
  const have = fs.existsSync(STAMP) ? fs.readFileSync(STAMP, "utf-8") : "";
  if (have === wanted && fs.existsSync(path.join(BUNDLE_DIR, "index.html"))) {
    log(`bundle: reusing ${BUNDLE_DIR}`);
    return 0;
  }
  log(`bundle: building ${BUNDLE_DIR}`);
  fs.rmSync(BUNDLE_DIR, { recursive: true, force: true });
  const result = execFileSync(
    process.execPath,
    [remotionCli(), "bundle", ENTRY, "--out-dir", BUNDLE_DIR, "--log", "error"],
    { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"], encoding: "utf-8" },
  );
  if (result.trim()) log(result.trim());
  fs.writeFileSync(STAMP, wanted, "utf-8");
  return (performance.now() - started) / 1000;
}

// --- serving the presenter and the assets -----------------------------------------------

// The deepest directory holding every file (all live under the job directory).
function commonDir(files) {
  const split = files.map((f) => path.dirname(path.resolve(f)).split(path.sep));
  const first = split[0];
  let n = first.length;
  for (const parts of split.slice(1)) {
    let i = 0;
    while (i < n && i < parts.length && parts[i].toLowerCase() === first[i].toLowerCase()) i += 1;
    n = i;
  }
  return first.slice(0, n).join(path.sep) || path.sep;
}

function urlFor(base, root, file) {
  const rel = path.relative(root, path.resolve(file)).split(path.sep);
  return base + rel.map(encodeURIComponent).join("/");
}

function serve(dir) {
  const server = http.createServer((req, res) => {
    const name = decodeURIComponent(new URL(req.url, "http://localhost").pathname.slice(1));
    const file = path.resolve(dir, name);
    if (!file.startsWith(path.resolve(dir)) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404).end();
      return;
    }
    const size = fs.statSync(file).size;
    const headers = {
      "Accept-Ranges": "bytes",
      "Content-Type": MIME[path.extname(file).toLowerCase()] ?? "application/octet-stream",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
      "Cache-Control": "no-store",
    };
    const range = req.headers.range;
    let start = 0;
    let end = size - 1;
    let status = 200;
    if (range) {
      const m = /^bytes=(\d*)-(\d*)$/.exec(range);
      if (!m) {
        res.writeHead(416, { "Content-Range": `bytes */${size}` }).end();
        return;
      }
      if (m[1] === "" && m[2] !== "") {
        start = Math.max(0, size - Number(m[2]));
      } else {
        start = Number(m[1] || 0);
        end = m[2] === "" ? size - 1 : Math.min(Number(m[2]), size - 1);
      }
      if (start > end || start >= size) {
        res.writeHead(416, { "Content-Range": `bytes */${size}` }).end();
        return;
      }
      status = 206;
      headers["Content-Range"] = `bytes ${start}-${end}/${size}`;
    }
    headers["Content-Length"] = String(end - start + 1);
    res.writeHead(status, headers);
    if (req.method === "HEAD") {
      res.end();
      return;
    }
    fs.createReadStream(file, { start, end }).pipe(res);
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      resolve({ base: `http://127.0.0.1:${port}/`, close: () => server.close() });
    });
  });
}

// --- render ---------------------------------------------------------------------------

async function render(args) {
  const specPath = path.resolve(args.spec);
  const outPath = path.resolve(args.out);
  const concurrency = Number(args.concurrency ?? 2);
  const spec = JSON.parse(fs.readFileSync(specPath, "utf-8"));

  const bundleSeconds = ensureBundle();
  await ensureBrowser();

  let server = null;
  const inputProps = { ...spec };
  // Every file the composition reads: the presenter cut, each beat's B-roll (016), the
  // cards of the hook and finale set pieces (026) and the wall's cells, the list's row
  // icons and the split's panes and badge (027), and the diagram's base picture (021).
  const setPieceCards = (beat) => [
    ...(beat.hook?.cards ?? []),
    ...(beat.finale?.cards ?? []),
    ...(beat.wall?.cells ?? []),
    ...(beat.split?.panes ?? []),
    ...(beat.split?.badge ? [beat.split.badge] : []),
  ];
  const assetFiles = spec.beats.flatMap((b) => [
    ...(b.visual ? [b.visual.src] : []),
    ...setPieceCards(b).map((c) => c.src),
    ...(b.list?.rows ?? []).map((r) => r.icon_src).filter(Boolean),
    // 021: the labelled diagram's own base picture.
    ...(b.infographic?.src ? [b.infographic.src] : []),
  ]);
  const files = [...(spec.presenter ? [spec.presenter] : []), ...assetFiles];
  if (files.length) {
    const root = commonDir(files);
    server = await serve(root);
    const url = (file) => urlFor(server.base, root, file);
    const served = (piece) =>
      piece ? { ...piece, cards: piece.cards.map((c) => ({ ...c, src: url(c.src) })) } : piece;
    const servedWall = (piece) =>
      piece ? { ...piece, cells: piece.cells.map((c) => ({ ...c, src: url(c.src) })) } : piece;
    const servedList = (piece) =>
      piece
        ? {
            ...piece,
            rows: piece.rows.map((r) =>
              r.icon_src ? { ...r, icon_src: url(r.icon_src) } : r,
            ),
          }
        : piece;
    const servedSplit = (piece) =>
      piece
        ? {
            ...piece,
            panes: piece.panes.map((p) => ({ ...p, src: url(p.src) })),
            badge: piece.badge ? { ...piece.badge, src: url(piece.badge.src) } : null,
          }
        : piece;
    if (spec.presenter) inputProps.presenter = url(spec.presenter);
    inputProps.beats = spec.beats.map((b) => ({
      ...b,
      ...(b.visual ? { visual: { ...b.visual, src: url(b.visual.src) } } : {}),
      ...(b.hook ? { hook: served(b.hook) } : {}),
      ...(b.finale ? { finale: served(b.finale) } : {}),
      ...(b.wall ? { wall: servedWall(b.wall) } : {}),
      ...(b.list ? { list: servedList(b.list) } : {}),
      ...(b.split ? { split: servedSplit(b.split) } : {}),
      ...(b.infographic ? { infographic: { ...b.infographic, src: url(b.infographic.src) } } : {}),
    }));
  }
  const started = performance.now();
  try {
    const composition = await selectComposition({
      serveUrl: BUNDLE_DIR,
      id: COMPOSITION_ID,
      inputProps,
      logLevel: "error",
    });
    const total = composition.durationInFrames;
    let last = -1;
    const report = (n) => {
      if (n !== last) {
        last = n;
        out(`progress ${n}/${total}`);
      }
    };
    report(0);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    await renderMedia({
      composition,
      serveUrl: BUNDLE_DIR,
      codec: "h264",
      outputLocation: outPath,
      inputProps,
      concurrency,
      colorSpace: "bt709",
      muted: true,
      crf: 18,
      pixelFormat: "yuv420p",
      imageFormat: "jpeg",
      logLevel: "error",
      onProgress: ({ renderedFrames }) => report(renderedFrames),
    });
    report(total);
    const renderSeconds = (performance.now() - started) / 1000;
    out(
      `done frames=${total} render_s=${renderSeconds.toFixed(3)} bundle_s=${bundleSeconds.toFixed(3)}`,
    );
  } finally {
    if (server) server.close();
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const command = args._[0];
  if (command === "bundle") {
    ensureBundle();
    return;
  }
  if (command === "render") {
    if (!args.spec || !args.out) throw new Error("render needs --spec and --out");
    await render(args);
    return;
  }
  throw new Error(`unknown command ${command ?? "(none)"}; use render or bundle`);
}

main().catch((err) => {
  log(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
