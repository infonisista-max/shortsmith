// The render driver the Python bridge runs (decision 9.1, ticket 004):
//
//   node src/remotion/driver.mjs render --spec <render_spec.json> --out <picture.mp4>
//                                      [--concurrency 2]
//   node src/remotion/driver.mjs still --spec <render_spec.json> --frames <n,n,...>
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
//   failed frame=<n|unknown> via=<error|progress>   (111d) once, when the render fails:
//                                    the frame from Remotion's error when it names one
//                                    (via=error), else the last finished-frame count
//                                    (via=progress; the failing frame is at most a few
//                                    past it at concurrency 2); unknown before any frame
//   still frame=<n> ok|failed        (111d, `still` mode) one per asked frame: each beat's
//                                    middle still rendered on its own, so a failure
//                                    with no frame can still be pinned to a beat
// Everything else (Remotion logs, bundler output) goes to stderr.

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const {
  ensureBrowser,
  openBrowser,
  renderMedia,
  renderStill,
  selectComposition,
} = require("@remotion/renderer");

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");
const ENTRY = path.join(HERE, "index.ts");
const BUNDLE_DIR = path.join(ROOT, "build", "remotion");
const STAMP = path.join(BUNDLE_DIR, ".shortsmith-stamp");
const COMPOSITION_ID = "Short";
// 111b: .gif/.webm/.avif/.bmp are a backstop only - the pre-render check (111c) sends
// nothing but jpg/png/webp/mp4 here, but a stray file is served with its real type.
const MIME = {
  ".mp4": "video/mp4",
  ".webm": "video/webm",
  ".mov": "video/quicktime",
  ".m4v": "video/mp4",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".avif": "image/avif",
  ".bmp": "image/bmp",
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

// The spec's input props with every file served over loopback; `close` stops the server.
async function servedProps(spec) {
  let server = null;
  const inputProps = { ...spec };
  // Every file the composition reads: the presenter cut, each beat's B-roll (016), the
  // cards of the hook and finale set pieces (026) and the wall's cells, the list's row
  // icons and the split's panes and badge (027), the diagram's base picture (021), and
  // each beat's sticker PNG (062).
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
    // 062: the beat's sticker, the job's copy of the fetched Fluent Emoji PNG.
    ...(b.stickers ?? []).map((s) => s.src),
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
      ...(b.stickers?.length
        ? { stickers: b.stickers.map((s) => ({ ...s, src: url(s.src) })) }
        : {}),
    }));
  }
  return { inputProps, close: () => server?.close() };
}

// 111d: the one parseable failure line (see the protocol above).
let failure = { started: false, frame: null };

async function render(args) {
  const specPath = path.resolve(args.spec);
  const outPath = path.resolve(args.out);
  const concurrency = Number(args.concurrency ?? 2);
  const spec = JSON.parse(fs.readFileSync(specPath, "utf-8"));

  const bundleSeconds = ensureBundle();
  await ensureBrowser();

  const { inputProps, close } = await servedProps(spec);
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
        failure.frame = n;
        out(`progress ${n}/${total}`);
      }
    };
    report(0);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    failure.started = true;
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
    close();
  }
}

// --- still (111d): each asked frame rendered on its own -----------------------------------

async function still(args) {
  const spec = JSON.parse(fs.readFileSync(path.resolve(args.spec), "utf-8"));
  const frames = String(args.frames ?? "")
    .split(",")
    .filter((f) => f !== "")
    .map(Number);
  ensureBundle();
  await ensureBrowser();
  const { inputProps, close } = await servedProps(spec);
  let browser = null;
  try {
    const composition = await selectComposition({
      serveUrl: BUNDLE_DIR,
      id: COMPOSITION_ID,
      inputProps,
      logLevel: "error",
    });
    browser = await openBrowser("chrome", { logLevel: "error" });
    for (const frame of frames) {
      try {
        await renderStill({
          composition,
          serveUrl: BUNDLE_DIR,
          inputProps,
          frame,
          output: null,
          imageFormat: "jpeg",
          puppeteerInstance: browser,
          logLevel: "error",
        });
        out(`still frame=${frame} ok`);
      } catch (err) {
        log(`still frame=${frame}: ${err && err.message ? err.message : String(err)}`);
        out(`still frame=${frame} failed`);
      }
    }
  } finally {
    if (browser) await browser.close({ silent: true });
    close();
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
  if (command === "still") {
    if (!args.spec || !args.frames) throw new Error("still needs --spec and --frames");
    await still(args);
    return;
  }
  throw new Error(`unknown command ${command ?? "(none)"}; use render, still or bundle`);
}

main().catch((err) => {
  // 111d: the message on its own line (the stack alone can bury it), then the stack,
  // then the one parseable failure line.
  const message = err && err.message ? err.message : String(err);
  log(`error: ${message}`);
  if (err && err.stack) log(err.stack);
  if (Number.isInteger(err?.frame)) {
    out(`failed frame=${err.frame} via=error`);
  } else if (failure.started && failure.frame !== null) {
    out(`failed frame=${failure.frame} via=progress`);
  } else {
    out("failed frame=unknown");
  }
  process.exit(1);
});
