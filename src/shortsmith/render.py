"""The Python half of the picture engine (decision 9.1, ticket 004).

`build_spec` is pure: from the PicturePlan, the caption pages and the transcript
words it resolves everything the Remotion composition needs into a `RenderSpec`
(frames not seconds, a pixel box per word, the PIP circle and crop window, the
palette, the 6.2 typography numbers). The composition under `src/remotion/` draws
what it is given and measures nothing.

`render_picture(job)` writes `work/render_spec.json`, runs `src/remotion/driver.mjs`
(which bundles once into `build/remotion/` and renders through `@remotion/renderer`
with concurrency 2 and bt709), streams the driver's `progress N/M` lines to the
caller, keeps the full driver output in `work/render.log` and leaves
`work/picture.mp4`, silent H.264.

The ffmpeg half (ticket 005, decision 9.1) wraps it. `cut_presenter` builds
`work/cut.mp4` from the plan's cut list (`presenter.cut_list`): one trim/concat graph,
the largest centred 9:16 window under the 1.5x rule scaled to 1080x1920, re-encoded
once to constant-frame-rate H.264 with `-bf 0` so the B-frame pyramid failure cannot
occur; the composition reads this cut, never the raw upload. `voice_stem` runs the same
span graph on the raw audio through the 7.3 voice chain verbatim (mono fold inside the
graph, high-pass 80 Hz, compressor -18 dB ratio 2.5, two-pass loudnorm -19 LUFS /
-3 dBTP) into `work/stems/voice.wav`. `mux` masters the mix (voice only until 022:
two-pass loudnorm -14 LUFS / -1.5 dBTP less `AAC_HEADROOM_DB` so the encoded file
still meets -1.5 dBTP, then the 0.891 limiter with auto-level off so the target holds)
into `work/stems/mix.wav` and muxes it with the picture stream copied bit-for-bit into
`out/short.mp4` (revision proof (a), 10.1). Stems always sit beside the mix under
`work/stems/`. `render_short` is the whole `rendering` step.

Style numbers: the loader (008) does not exist yet, so `EXPLAINER` holds the 6.2, 6.3
and 3.3 numbers as one typed constant, the way `pipeline` holds the pager numbers.
Word widths are estimated from a per-glyph advance table for Poppins 800; ticket 010
replaces the estimate with a Pillow measurement and adds the pager's own wrapping.
The gradient palette, PIP left edge and ring look are placeholders that 008 moves
into front matter (no reference value exists on record for them).

Component registry (9.2): `src/remotion/registry.json` is the checked-in list the
Node test asserts against the component files; `registry()` reads the same file.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from shortsmith import ffmpeg, presenter, subproc
from shortsmith.contracts import (
    BeatSpec,
    CaptionPage,
    CaptionPageSpec,
    CaptionStyle,
    Palette,
    PicturePlan,
    PipGeometry,
    RenderSpec,
    Span,
    Transcript,
    Word,
    WordBox,
)
from shortsmith.jobs import Job

REPO_ROOT = Path(__file__).resolve().parents[2]
REMOTION_DIR = REPO_ROOT / "src" / "remotion"
DRIVER = REMOTION_DIR / "driver.mjs"
REGISTRY_PATH = REMOTION_DIR / "registry.json"
WIDTH, HEIGHT, FPS = 1080, 1920, 30
CONCURRENCY = 2  # decision 9.1
DRIVER_TIMEOUT_S = 3600.0
FFMPEG_TIMEOUT_S = 1800.0

# Decision 7.3 (research §5) sound numbers.
VOICE_LUFS, VOICE_TP = -19.0, -3.0
MASTER_LUFS, MASTER_TP = -14.0, -1.5
# T4 (10.1) measures the delivered AAC, and the encoder overshoots the mastered WAV's
# true peak by a few tenths of a dB (the fixture: -1.50 -> -1.42 dBTP), so loudnorm is
# asked for the ceiling less this headroom and the delivered file meets MASTER_TP (006).
AAC_HEADROOM_DB = 0.5
LIMITER = 0.891
SAMPLE_RATE = 48000

_PAGES = TypeAdapter(list[CaptionPage])


class RenderError(RuntimeError):
    """The driver failed; the message carries the tail of its output."""


class LayoutError(ValueError):
    """A caption page cannot be laid out within the style's line limit (6.2)."""


# --- style numbers (until 008) ---------------------------------------------------------


@dataclass(frozen=True)
class PipNumbers:
    diameter: int
    large_face_diameter: int
    chin_anchor: float
    left: int
    ring_px: int
    ring_color: str


@dataclass(frozen=True)
class StyleNumbers:
    captions: CaptionStyle
    pip: PipNumbers
    palette: Palette


EXPLAINER = StyleNumbers(
    captions=CaptionStyle(
        font_family="Poppins",
        font_weight=800,
        size_px=74,
        line_height=1.35,
        letter_spacing_px=0.5,
        anchor_y=1460,
        max_lines=2,
        max_width_px=960,
        word_gap_px=22,
        unspoken_alpha=0.86,
        active_color="#FFD60A",
        active_scale=1.08,
        active_scale_s=0.10,
        keyword_fg="#111",
        keyword_bg="#FFD60A",
        keyword_pad_px=14,
        keyword_radius_px=14,
        enter_scale_from=0.94,
        enter_s=0.12,
        enter_opacity_s=0.06,
        stroke_px=2,
        drop_px=3,
        glow_px=18,
    ),
    pip=PipNumbers(
        diameter=300,
        large_face_diameter=340,
        chin_anchor=0.82,
        left=60,  # placeholder until 008: "bottom-left" is all the reference records
        ring_px=6,
        ring_color="#FFFFFF",
    ),
    palette=Palette(gradient=["#0B1D3A", "#1F3B73"], angle_deg=160, accent="#FFD60A"),
)


# --- text width estimate (until 010 measures with Pillow) -----------------------------

# Advance widths in em for Poppins 800, by glyph class; a guess good to about 10 %.
_NARROW = set("iljtfr.,'!|:;")
_WIDE = set("mw")
_WIDE_UPPER = set("MW")
_ADVANCE_EM = {"narrow": 0.34, "lower": 0.58, "wide": 0.90, "upper": 0.72, "wide_upper": 1.0,
               "digit": 0.62, "space": 0.30, "other": 0.60}  # fmt: skip


def _glyph_em(ch: str) -> float:
    if ch in _NARROW:
        return _ADVANCE_EM["narrow"]
    if ch in _WIDE:
        return _ADVANCE_EM["wide"]
    if ch in _WIDE_UPPER:
        return _ADVANCE_EM["wide_upper"]
    if ch.isspace():
        return _ADVANCE_EM["space"]
    if ch.isdigit():
        return _ADVANCE_EM["digit"]
    if ch.isupper():
        return _ADVANCE_EM["upper"]
    if ch.islower():
        return _ADVANCE_EM["lower"]
    return _ADVANCE_EM["other"]


def text_width(text: str, style: CaptionStyle) -> float:
    """Resting width of `text` at the style size: glyph advances plus letter spacing."""
    return sum(_glyph_em(ch) for ch in text) * style.size_px + style.letter_spacing_px * len(text)


def box_width(text: str, *, keyword: bool, style: CaptionStyle) -> float:
    """The fixed box: the 1.08-scaled width, plus the keyword padding when boxed (6.2)."""
    width = text_width(text, style) * style.active_scale
    if keyword:
        width += 2 * style.keyword_pad_px
    return width


# --- caption layout --------------------------------------------------------------------


def layout_page(page: CaptionPage, words: Sequence[Word], style: CaptionStyle) -> CaptionPageSpec:
    """Boxes for one page: greedy fill into lines no wider than `max_width_px`, each
    line centred, the block's bottom edge on `anchor_y`. More than `max_lines` raises."""
    items = [
        (words[i], box_width(words[i].text, keyword=(i == page.keyword), style=style), i)
        for i in page.word_indices
    ]
    lines: list[list[tuple[Word, float, int]]] = [[]]
    used = 0.0
    for item in items:
        width = item[1]
        extra = width if not lines[-1] else style.word_gap_px + width
        if lines[-1] and used + extra > style.max_width_px:
            lines.append([item])
            used = width
        else:
            lines[-1].append(item)
            used += extra
    if len(lines) > style.max_lines:
        raise LayoutError(
            f"caption page {page.index} needs {_count(len(lines))} lines "
            f"(max {style.max_lines}): {' '.join(page.texts)!r}"
        )
    line_h = style.size_px * style.line_height
    top = style.anchor_y - len(lines) * line_h
    boxes: list[WordBox] = []
    for n, line in enumerate(lines):
        line_w = sum(w for _, w, _ in line) + style.word_gap_px * (len(line) - 1)
        x = (WIDTH - line_w) / 2
        for word, width, index in line:
            boxes.append(
                WordBox(
                    text=word.text,
                    start=word.start,
                    end=word.end,
                    x=x,
                    y=top + n * line_h,
                    width=width,
                    height=line_h,
                    keyword=index == page.keyword,
                )
            )
            x += width + style.word_gap_px
    return CaptionPageSpec(
        index=page.index, start=page.start, end=page.end, lines=len(lines), words=boxes
    )


def _count(n: int) -> str:
    return {3: "three", 4: "four"}.get(n, str(n))


# --- PIP geometry ----------------------------------------------------------------------


def fixed_pip(source_size: tuple[int, int], numbers: StyleNumbers) -> PipGeometry:
    """The 004 geometry: the style diameter, left at the style edge, bottom touching the
    caption block's top (6.3); the crop window is the largest square of full source
    width anchored at the top, centred horizontally on a landscape source."""
    style = numbers.captions
    block_top = style.anchor_y - style.max_lines * style.size_px * style.line_height
    top = int(block_top) - numbers.pip.diameter
    src_w, src_h = source_size
    size = min(src_w, src_h)
    return PipGeometry(
        left=numbers.pip.left,
        top=top,
        diameter=numbers.pip.diameter,
        ring_px=numbers.pip.ring_px,
        ring_color=numbers.pip.ring_color,
        window_left=(src_w - size) // 2,
        window_top=0,
        window_size=size,
    )


# --- the spec --------------------------------------------------------------------------


def build_spec(
    plan: PicturePlan,
    pages: Sequence[CaptionPage],
    words: Sequence[Word],
    *,
    presenter: Path,
    source_size: tuple[int, int],
    duration_s: float,
    numbers: StyleNumbers = EXPLAINER,
    fps: int = FPS,
) -> RenderSpec:
    frames = round(duration_s * fps)
    beats = [
        BeatSpec(
            id=b.id,
            start_frame=round(b.start * fps),
            end_frame=round(b.end * fps),
            mode=b.mode,
            kind=b.kind,
            enter=b.enter,
        )
        for b in plan.beats
    ]
    return RenderSpec(
        width=WIDTH,
        height=HEIGHT,
        fps=fps,
        frames=frames,
        presenter=str(presenter),
        source_width=source_size[0],
        source_height=source_size[1],
        beats=beats,
        captions=[layout_page(p, words, numbers.captions) for p in pages],
        pip=fixed_pip(source_size, numbers),
        palette=numbers.palette,
        caption_style=numbers.captions,
    )


# --- the driver ------------------------------------------------------------------------

_PROGRESS = re.compile(r"^progress (\d+)/(\d+)\s*$")
_DONE = re.compile(r"^done frames=(\d+) render_s=([\d.]+) bundle_s=([\d.]+)\s*$")


def parse_progress(line: str) -> tuple[int, int] | None:
    match = _PROGRESS.match(line)
    return (int(match.group(1)), int(match.group(2))) if match else None


@dataclass(frozen=True)
class DriverResult:
    frames: int
    render_s: float
    bundle_s: float
    wall_s: float


def registry() -> list[str]:
    """The component names the Node project exports (9.2)."""
    return list(json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["components"])


def node_binary() -> str:
    node = shutil.which("node")
    if node is None:
        raise RenderError("node is not on PATH; the picture engine needs Node (ticket 004)")
    return node


def run_driver(
    spec: RenderSpec,
    *,
    spec_path: Path,
    out_path: Path,
    log_path: Path,
    on_progress: Callable[[int], None] | None = None,
    concurrency: int = CONCURRENCY,
) -> DriverResult:
    """Render `spec` to `out_path` through the driver; every driver line lands in
    `log_path`, `progress` lines reach `on_progress` as a percentage when it changes."""
    spec_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    argv = [
        node_binary(),
        str(DRIVER),
        "render",
        "--spec",
        str(spec_path),
        "--out",
        str(out_path),
        "--concurrency",
        str(concurrency),
    ]
    done: DriverResult | None = None
    last_pct = -1
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as log:
        log.write(" ".join(argv) + "\n")

        def on_line(stream: str, line: str) -> None:
            nonlocal done, last_pct
            log.write(f"[{stream}] {line}\n")
            if stream != "out":
                return
            progress = parse_progress(line)
            if progress is not None and on_progress is not None:
                rendered, total = progress
                pct = min(100, math.floor(100 * rendered / max(1, total)))
                if pct != last_pct:
                    last_pct = pct
                    on_progress(pct)
                return
            match = _DONE.match(line)
            if match:
                done = DriverResult(
                    frames=int(match.group(1)),
                    render_s=float(match.group(2)),
                    bundle_s=float(match.group(3)),
                    wall_s=0.0,
                )

        proc = subproc.stream(argv, on_line, timeout_s=DRIVER_TIMEOUT_S, cwd=REPO_ROOT)
    if proc.returncode != 0 or done is None or not out_path.is_file():
        tail = log_path.read_text(encoding="utf-8")[-4000:]
        raise RenderError(f"remotion driver exited {proc.returncode}:\n{tail}")
    if on_progress is not None and last_pct != 100:
        on_progress(100)
    return DriverResult(
        frames=done.frames,
        render_s=done.render_s,
        bundle_s=done.bundle_s,
        wall_s=time.perf_counter() - started,
    )


def _load_plan(job: Job) -> PicturePlan:
    return PicturePlan.model_validate_json(
        (job.work_dir / "plan.json").read_text(encoding="utf-8")
    )


def _raw_path(job: Job) -> Path:
    return job.input_dir / (job.record.input.file if job.record.input else "raw.mp4")


def _cut_path(job: Job) -> Path:
    return job.work_dir / "cut.mp4"


def spec_for_job(job: Job, *, numbers: StyleNumbers = EXPLAINER) -> RenderSpec:
    """The RenderSpec from the job's files: plan.json, asr.json, captions.json and the
    presenter cut (`work/cut.mp4`, 005). The short is as long as the cut list."""
    work = job.work_dir
    plan = _load_plan(job)
    transcript = Transcript.model_validate_json((work / "asr.json").read_text(encoding="utf-8"))
    pages = _PAGES.validate_json((work / "captions.json").read_text(encoding="utf-8"))
    cut = _cut_path(job)
    if not cut.is_file():
        raise RenderError("work/cut.mp4 is missing: cut_presenter runs before the picture")
    return build_spec(
        plan,
        pages,
        transcript.words,
        presenter=cut,
        source_size=_probe_size(cut),
        duration_s=presenter.total_duration(presenter.cut_list(plan)),
        numbers=numbers,
    )


def _probe_size(path: Path) -> tuple[int, int]:
    for stream in ffmpeg.probe(path)["streams"]:
        if stream.get("codec_type") == "video":
            return int(stream["width"]), int(stream["height"])
    raise RenderError(f"{path.name} has no video stream")


def render_picture(job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
    """The `rendering` step's picture half: `work/picture.mp4`, silent H.264."""
    spec = spec_for_job(job)
    out = job.work_dir / "picture.mp4"
    run_driver(
        spec,
        spec_path=job.work_dir / "render_spec.json",
        out_path=out,
        log_path=job.work_dir / "render.log",
        on_progress=on_progress,
    )
    return out


# --- the ffmpeg half (ticket 005; decisions 2.1, 7.3, 9.1, 10.1) -----------------------


def span_filter(spans: Sequence[Span], *, video: bool, audio: bool) -> str:
    """A filter graph that trims each span of input 0 and concatenates them in order;
    the outputs are `[vc]` and/or `[ac]`. Both streams use the same span times, so the
    cut and the voice stem stay sample-aligned."""
    parts: list[str] = []
    inputs = ""
    for i, span in enumerate(spans):
        if video:
            parts.append(
                f"[0:v]trim=start={span.start:.3f}:end={span.end:.3f},setpts=PTS-STARTPTS[v{i}]"
            )
            inputs += f"[v{i}]"
        if audio:
            parts.append(
                f"[0:a]atrim=start={span.start:.3f}:end={span.end:.3f},asetpts=PTS-STARTPTS[a{i}]"
            )
            inputs += f"[a{i}]"
    outs = ("[vc]" if video else "") + ("[ac]" if audio else "")
    parts.append(f"{inputs}concat=n={len(spans)}:v={int(video)}:a={int(audio)}{outs}")
    return ";".join(parts)


def crop_filter(source_size: tuple[int, int]) -> str:
    """Centre crop to the largest 9:16 window (1.5x rule enforced by `crop_window`),
    scale to the composition size, constant 30 fps, 4:2:0."""
    crop_w, crop_h, x, y = presenter.crop_window(source_size)
    return (
        f"crop={crop_w}:{crop_h}:{x}:{y},scale={WIDTH}:{HEIGHT}:flags=lanczos,"
        f"fps={FPS},format=yuv420p"
    )


def cut_presenter(job: Job) -> Path:
    """`work/cut.mp4`: the cut list applied to the raw upload, CFR 30 fps H.264 with no
    B-frames, 1080x1920, its audio carried along as AAC."""
    plan = _load_plan(job)
    raw = _raw_path(job)
    if job.record.input is not None:
        source_size = (job.record.input.width, job.record.input.height)
    else:
        source_size = _probe_size(raw)
    picture = crop_filter(source_size)  # raises UpscaleExceeded before ffmpeg starts
    spans = presenter.cut_list(plan)
    graph = f"{span_filter(spans, video=True, audio=True)};[vc]{picture}[v]"
    out = _cut_path(job)
    ffmpeg.run(
        [
            ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(raw),
            "-filter_complex", graph, "-map", "[v]", "-map", "[ac]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-bf", "0",
            "-fps_mode", "cfr", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", str(SAMPLE_RATE),
            "-movflags", "+faststart", str(out),
        ],  # fmt: skip
        timeout_s=FFMPEG_TIMEOUT_S,
    )
    return out


def voice_chain() -> str:
    """Research §5 / decision 7.3 voice chain before loudnorm: the mono fold inside the
    graph (never `-ac 1`), high-pass 80 Hz, compressor -18 dB ratio 2.5."""
    return (
        "aformat=channel_layouts=stereo,pan=mono|c0=0.5*c0+0.5*c1,"
        "highpass=f=80,acompressor=threshold=-18dB:ratio=2.5"
    )


def loudnorm_second_pass(measured: ffmpeg.Loudness, *, target_lufs: float, target_tp: float) -> str:
    """The linear second pass of two-pass loudnorm from the first pass's measurement."""
    return (
        f"{ffmpeg.loudnorm_filter(target_lufs=target_lufs, target_tp=target_tp)}"
        f":measured_I={measured.integrated:g}:measured_TP={measured.true_peak:g}"
        f":measured_LRA={measured.lra:g}:measured_thresh={measured.threshold:g}"
        f":offset={measured.offset:g}:linear=true:print_format=summary"
    )


def _stems_dir(job: Job) -> Path:
    stems = job.work_dir / "stems"
    stems.mkdir(parents=True, exist_ok=True)
    return stems


def voice_stem(job: Job) -> Path:
    """`work/stems/voice.wav`: the cut list's audio through the voice chain and
    two-pass loudnorm to -19 LUFS / -3 dBTP, mono 48 kHz PCM."""
    plan = _load_plan(job)
    raw = _raw_path(job)
    graph = span_filter(presenter.cut_list(plan), video=False, audio=True)
    measured = ffmpeg.measure_loudness(
        raw,
        prefilter=voice_chain(),
        target_lufs=VOICE_LUFS,
        target_tp=VOICE_TP,
        filter_complex=graph,
        label="ac",
    )
    second = loudnorm_second_pass(measured, target_lufs=VOICE_LUFS, target_tp=VOICE_TP)
    out = _stems_dir(job) / "voice.wav"
    ffmpeg.run(
        [
            ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(raw),
            "-filter_complex", f"{graph};[ac]{voice_chain()},{second},aresample={SAMPLE_RATE}[out]",
            "-map", "[out]", "-c:a", "pcm_s16le", str(out),
        ],  # fmt: skip
        timeout_s=FFMPEG_TIMEOUT_S,
    )
    return out


def master_chain(measured: ffmpeg.Loudness, *, request_lufs: float = MASTER_LUFS) -> str:
    """Master: two-pass loudnorm to `request_lufs` / (-1.5 dBTP less the AAC headroom)
    then the 0.891 limiter. The limiter's auto-level is off; on, it would re-gain the
    output to 0 dB and break T4."""
    second = loudnorm_second_pass(
        measured, target_lufs=request_lufs, target_tp=MASTER_TP - AAC_HEADROOM_DB
    )
    return f"{second},alimiter=limit={LIMITER}:level=false,aresample={SAMPLE_RATE}"


MASTER_TOLERANCE_LU = 0.2
MASTER_PASSES = 4


def master(source: Path, mix: Path) -> ffmpeg.Loudness:
    """Render `source` through the master chain into `mix` and converge on -14 LUFS.

    loudnorm's linear mode is impossible whenever the gain to target would push the
    peaks past the -1.5 dBTP ceiling (any voice stem peaking above about -6.5 dBTP, so
    most speech), and its dynamic mode lands a few tenths of an LU off a fresh
    measurement. The requested target is corrected by the measured error and the pass
    re-run, at most `MASTER_PASSES` times, so T4 (-14 +- 0.5) holds on every recording
    while the chain itself stays the 7.3 graph."""
    request = MASTER_LUFS
    got: ffmpeg.Loudness | None = None
    for _ in range(MASTER_PASSES):
        measured = ffmpeg.measure_loudness(
            source, target_lufs=request, target_tp=MASTER_TP - AAC_HEADROOM_DB
        )
        ffmpeg.run(
            [
                ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(source),
                "-af", master_chain(measured, request_lufs=request),
                "-c:a", "pcm_s16le", str(mix),
            ],  # fmt: skip
            timeout_s=FFMPEG_TIMEOUT_S,
        )
        got = ffmpeg.measure_loudness(mix)
        error = MASTER_LUFS - got.integrated
        if abs(error) <= MASTER_TOLERANCE_LU:
            break
        request += error
    assert got is not None
    return got


def mux(job: Job) -> Path:
    """`work/stems/mix.wav` (the mastered mix; voice only until 022) and
    `out/short.mp4`: the picture stream copied, the mix as AAC."""
    stems = _stems_dir(job)
    voice = stems / "voice.wav"
    picture = job.work_dir / "picture.mp4"
    for needed in (voice, picture):
        if not needed.is_file():
            raise RenderError(f"{needed.relative_to(job.path).as_posix()} is missing before mux")
    mix = stems / "mix.wav"
    master(voice, mix)
    job.out_dir.mkdir(parents=True, exist_ok=True)
    out = job.out_dir / "short.mp4"
    ffmpeg.run(
        [
            ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(picture), "-i", str(mix),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out),
        ],  # fmt: skip
        timeout_s=FFMPEG_TIMEOUT_S,
    )
    return out


def render_short(job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
    """The whole `rendering` step (9.1): cut, voice stem, picture, master and mux."""
    cut_presenter(job)
    voice_stem(job)
    render_picture(job, on_progress=on_progress)
    return mux(job)


# --- the interface the pipeline uses ---------------------------------------------------


class Renderer(ABC):
    """The render engine as the pipeline sees it: the whole `rendering` step from the
    job's plan to `out/short.mp4`. Remotion and ffmpeg are local, not paid, but a
    render costs seconds, so the fake keeps the pipeline and app tests fast; the real
    path is covered by test_render and smoke (12.1)."""

    @abstractmethod
    def render(self, job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
        """Write `work/cut.mp4`, `work/stems/*`, `work/picture.mp4` and `out/short.mp4`;
        return the short. `on_progress` gets the picture render's 0-100."""


class RemotionRenderer(Renderer):
    def render(self, job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
        return render_short(job, on_progress=on_progress)


class FakeRenderer(Renderer):
    """Builds the same RenderSpec (so a bad plan still fails here), reports 0, 50 and
    100, and writes placeholders for every file the step leaves; none is media."""

    def __init__(self) -> None:
        self.jobs: list[Path] = []

    def render(self, job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
        self.jobs.append(job.path)
        cut = _cut_path(job)
        cut.write_bytes(b"")
        plan = _load_plan(job)
        transcript = Transcript.model_validate_json(
            (job.work_dir / "asr.json").read_text(encoding="utf-8")
        )
        pages = _PAGES.validate_json((job.work_dir / "captions.json").read_text(encoding="utf-8"))
        spec = build_spec(
            plan,
            pages,
            transcript.words,
            presenter=cut,
            source_size=(WIDTH, HEIGHT),
            duration_s=presenter.total_duration(presenter.cut_list(plan)),
        )
        (job.work_dir / "render_spec.json").write_text(
            spec.model_dump_json(indent=2), encoding="utf-8"
        )
        stems = _stems_dir(job)
        (stems / "voice.wav").write_bytes(b"")
        for pct in (0, 50, 100):
            if on_progress is not None:
                on_progress(pct)
        (job.work_dir / "picture.mp4").write_bytes(b"")
        (stems / "mix.wav").write_bytes(b"")
        job.out_dir.mkdir(parents=True, exist_ok=True)
        out = job.out_dir / "short.mp4"
        out.write_bytes(b"")
        return out
