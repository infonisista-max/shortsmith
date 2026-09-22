"""The Python half of the picture engine (decision 9.1, ticket 004).

`build_spec` is pure: from the PicturePlan and the laid-out captions (`captions.build`,
ticket 010: word boxes already measured, wrapped and anchored, times on the cut
timeline) it resolves everything the Remotion composition needs into a `RenderSpec`
(frames not seconds, the caption boxes and `beats_with_two_lines` as given, the PIP
circle and crop window, the palette, the 6.2 typography numbers). The composition
under `src/remotion/` draws what it is given and measures nothing.

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

Style numbers come from the style front matter (ticket 008, decision 1.2):
`numbers_for(spec)` narrows a loaded `StyleSpec` to the `StyleNumbers` the builder
reads (the 6.2 typography, the 3.3 / 6.3 PIP geometry, the palette), and
`style_numbers(name)` looks a style up in the specs loaded once per process.

Component registry (9.2): `src/remotion/registry.json` is the checked-in list the
Node test asserts against the component files; `registry()` reads the same file.

B-roll (ticket 016; decisions 4.1, 4.4, 5.3): `build_spec` takes the asset step's
manifest and gives every `photo` / `card` beat that shows an asset a `VisualSpec`.
A photo is full-bleed with the style's Ken Burns (`broll.motion.photo`, 1.10 -> 1.16
on explainer), in and out and the pan direction alternating per consecutive
photo/card beat. A card is the framed archival look from `broll.motion.card`: a card
min(980, 650 x aspect) wide border included (5.3; the reference card measures ~982 px
across), its image never over a 1.5x upscale, inside a white border, tilted, with a
caption strip when the beat carries a lower-third label and the red ring when it
carries a ring event; behind it the same image blurred and
darkened as the cover, which takes the card's push (1.45 -> 2.1), while the card body
takes the Ken Burns ratio of the photo motion (5.3: the Ken Burns is on the card, not
the cover). The card is centred horizontally with its bottom, at full push and tilt,
`PIP_GAP_PX` above the PIP circle as in the reference frames (dyson_05, nkb_06: a
card from y ~190 to ~925 over a PIP at 960), and never below
`broll.card_max_bottom_y`. A rung-4 rescue is drawn as `pip` over the gradient;
other kinds keep their visuals for their own tickets. The engine constants below
(strip, blur, ring) are not style numbers yet.
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
from functools import cache
from pathlib import Path

from shortsmith import assets, ffmpeg, presenter, styles, subproc
from shortsmith.contracts import (
    AssetManifest,
    BeatSpec,
    CaptionPageSpec,
    Captions,
    CaptionStyle,
    CardSpec,
    Crop,
    Mode,
    Palette,
    PicturePlan,
    PipGeometry,
    RenderSpec,
    Span,
    VisualSpec,
)
from shortsmith.jobs import Job
from shortsmith.styles import StyleSpec

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


class RenderError(RuntimeError):
    """The driver failed; the message carries the tail of its output."""


# --- style numbers (decision 1.2: read from front matter, never from code) --------------


@dataclass(frozen=True)
class PipNumbers:
    diameter: int
    large_face_diameter: int
    chin_anchor: float
    left: int
    ring_px: int
    ring_color: str


@dataclass(frozen=True)
class BrollNumbers:
    """`broll.motion.photo` / `broll.motion.card` and the card's bottom limit (4.1)."""

    photo_scale_from: float
    photo_scale_to: float
    photo_alternate: bool
    card_scale_from: float
    card_scale_to: float
    card_border_px: int
    card_rotate_deg: float
    card_ring_color: str
    card_max_bottom_y: int
    pip_top: int


@dataclass(frozen=True)
class StyleNumbers:
    captions: CaptionStyle
    pip: PipNumbers
    palette: Palette
    broll: BrollNumbers


def broll_numbers(spec: StyleSpec) -> BrollNumbers:
    try:
        photo, card = spec.broll.motion["photo"], spec.broll.motion["card"]
        return BrollNumbers(
            photo_scale_from=float(photo["scale_from"]),
            photo_scale_to=float(photo["scale_to"]),
            photo_alternate=bool(photo["alternate"]),
            card_scale_from=float(card["scale_from"]),
            card_scale_to=float(card["scale_to"]),
            card_border_px=int(card["border_px"]),
            card_rotate_deg=float(card["rotate_deg"]),
            card_ring_color=str(card["ring_color"]),
            card_max_bottom_y=spec.broll.card_max_bottom_y,
            pip_top=spec.pip.top,
        )
    except KeyError as exc:
        raise styles.StyleError(f"{spec.name}: broll.motion is missing {exc}") from None


def numbers_for(spec: StyleSpec) -> StyleNumbers:
    """The subset of a loaded spec the render spec builder reads."""
    return StyleNumbers(
        broll=broll_numbers(spec),
        captions=spec.caption_style(),
        pip=PipNumbers(
            diameter=spec.pip.diameter,
            large_face_diameter=spec.pip.large_face_diameter,
            chin_anchor=spec.pip.chin_anchor,
            left=spec.pip.left,
            ring_px=spec.pip.ring_px,
            ring_color=spec.pip.ring_color,
        ),
        palette=spec.palette,
    )


@cache
def loaded_styles() -> dict[str, StyleSpec]:
    """The specs under `styles/`, validated against this project's registry, loaded
    once per process for the render path (the app and worker load their own copy)."""
    return styles.load_all(registry())


def style_numbers(name: str) -> StyleNumbers:
    return numbers_for(loaded_styles()[name])


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


# --- photo and card (ticket 016) -------------------------------------------------------

# 5.3: a card is at most 980 px wide and 650 px tall at its native aspect.
CARD_MAX_W, CARD_BASE_H, CARD_MAX_UPSCALE = 980.0, 650.0, 1.5
# Engine look constants the style front matter does not carry yet.
STRIP_PX, STRIP_FONT_PX = 64, 30
PIP_GAP_PX = 32  # the reference cards end ~35 px above the PIP circle
COVER_BLUR_PX, COVER_BRIGHTNESS = 36, 0.45
RING_FRACTION, RING_PX, RING_AT_S = 0.32, 8, 0.2  # the ring lands 0.2 s into the beat


def card_image_size(width: int, height: int, border_px: int) -> tuple[float, float]:
    """The card's image size: the card is min(980, 650 x aspect) wide border included,
    the image inside never over a 1.5x upscale (5.3)."""
    aspect = width / height
    card_w = min(CARD_MAX_W, CARD_BASE_H * aspect)
    image_w = min(card_w - 2 * border_px, CARD_MAX_UPSCALE * width)
    return image_w, image_w / aspect


def _ken_burns(index: int, low: float, high: float, alternate: bool) -> tuple[float, float]:
    return (high, low) if alternate and index % 2 else (low, high)


def _pan_sign(index: int) -> int:
    return -1 if index % 2 else 1


def photo_visual(src: str, width: int, height: int, *, index: int, crop: Crop,
                 numbers: StyleNumbers) -> VisualSpec:  # fmt: skip
    """The full-bleed photo: Ken Burns from the style, drifting across the margin the
    smaller scale leaves, direction alternating with `index` (4.1)."""
    b = numbers.broll
    scale_from, scale_to = _ken_burns(index, b.photo_scale_from, b.photo_scale_to,
                                      b.photo_alternate)  # fmt: skip
    margin = (min(scale_from, scale_to) - 1.0) * WIDTH / 2
    return VisualSpec(
        treatment="photo", src=src, width=width, height=height, zoom=crop.zoom,
        focus_x=crop.focus_x, focus_y=crop.focus_y, scale_from=scale_from, scale_to=scale_to,
        pan_px=_pan_sign(index) * margin,
    )  # fmt: skip


def _half_extent(card: CardSpec, scale: float) -> float:
    """Half the height of the card's box once tilted and pushed to `scale`."""
    theta = math.radians(card.rotate_deg)
    return scale * (card.width * abs(math.sin(theta)) + card.height * math.cos(theta)) / 2


def card_bottom(visual: VisualSpec) -> float:
    """The lowest y the card reaches over its beat (full push, tilt included)."""
    card = visual.card
    assert card is not None
    return card.top + card.height / 2 + _half_extent(card, max(visual.scale_from, visual.scale_to))


def card_visual(src: str, width: int, height: int, *, strip_text: str, ring: bool, index: int,
                crop: Crop, numbers: StyleNumbers) -> VisualSpec:  # fmt: skip
    """The framed archival card (4.1, 5.3), placed so it ends above the style limit."""
    b = numbers.broll
    image_w, image_h = card_image_size(width, height, b.card_border_px)
    strip = STRIP_PX if strip_text else 0
    outer_w = image_w + 2 * b.card_border_px
    outer_h = image_h + 2 * b.card_border_px + strip
    ratio = b.photo_scale_to / b.photo_scale_from
    scale_from, scale_to = _ken_burns(index, 1.0, ratio, b.photo_alternate)
    card = CardSpec(
        left=(WIDTH - outer_w) / 2, top=0.0, width=outer_w, height=outer_h,
        image_width=image_w, image_height=image_h, border_px=b.card_border_px,
        rotate_deg=b.card_rotate_deg, strip_text=strip_text, strip_px=strip,
        strip_font_px=STRIP_FONT_PX, cover_scale_from=b.card_scale_from,
        cover_scale_to=b.card_scale_to, cover_blur_px=COVER_BLUR_PX,
        cover_brightness=COVER_BRIGHTNESS, ring=ring, ring_color=b.card_ring_color,
        ring_diameter_px=RING_FRACTION * min(image_w, image_h), ring_px=RING_PX,
        ring_at_s=RING_AT_S,
    )  # fmt: skip
    half = _half_extent(card, max(scale_from, scale_to))
    centre = min(b.pip_top - PIP_GAP_PX, b.card_max_bottom_y) - half
    card = card.model_copy(update={"top": centre - outer_h / 2})
    return VisualSpec(
        treatment="card", src=src, width=width, height=height, zoom=crop.zoom,
        focus_x=crop.focus_x, focus_y=crop.focus_y, scale_from=scale_from, scale_to=scale_to,
        pan_px=0.0, card=card,
    )  # fmt: skip


def _visuals(
    plan: PicturePlan, manifest: AssetManifest | None, job_dir: Path | None,
    numbers: StyleNumbers,
) -> dict[str, tuple[Mode, VisualSpec | None]]:  # fmt: skip
    """Per beat id: the mode to draw (a rung-4 rescue becomes `pip`) and its visual."""
    out: dict[str, tuple[Mode, VisualSpec | None]] = {}
    if manifest is None:
        return out
    if job_dir is None:
        raise ValueError("build_spec needs job_dir to resolve the manifest's asset files")
    index = 0
    for beat in plan.beats:
        decided = manifest.beat(beat.id)
        if decided is None:
            continue
        if decided.fallback_rung == 4 or decided.asset_id is None:
            out[beat.id] = ("pip", None)
            continue
        record = manifest.asset(decided.asset_id)
        if beat.kind not in ("photo", "card") or record is None:
            continue
        src = str((job_dir / record.file).resolve())
        if decided.treatment == "photo":
            visual = photo_visual(src, record.width, record.height, index=index,
                                  crop=decided.crop, numbers=numbers)  # fmt: skip
        else:
            label = beat.event.text if beat.event.kind == "lower_third" else None
            visual = card_visual(src, record.width, record.height, strip_text=label or "",
                                 ring=beat.event.kind == "ring", index=index,
                                 crop=decided.crop, numbers=numbers)  # fmt: skip
        out[beat.id] = (beat.mode, visual)
        index += 1
    return out


# --- the spec --------------------------------------------------------------------------


def build_spec(
    plan: PicturePlan,
    captions: Captions,
    *,
    presenter: Path,
    source_size: tuple[int, int],
    duration_s: float,
    numbers: StyleNumbers | None = None,
    fps: int = FPS,
    manifest: AssetManifest | None = None,
    job_dir: Path | None = None,
) -> RenderSpec:
    numbers = numbers or style_numbers(styles.DEFAULT)
    frames = round(duration_s * fps)
    visuals = _visuals(plan, manifest, job_dir, numbers)
    beats = [
        BeatSpec(
            id=b.id,
            start_frame=round(b.start * fps),
            end_frame=round(b.end * fps),
            mode=visuals.get(b.id, (b.mode, None))[0],
            kind=b.kind,
            enter=b.enter,
            visual=visuals.get(b.id, (b.mode, None))[1],
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
        captions=[
            CaptionPageSpec(index=p.index, start=p.start, end=p.end, lines=p.lines, words=p.words)
            for p in captions.pages
        ],
        beats_with_two_lines=captions.beats_with_two_lines,
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


def load_captions(job: Job) -> Captions:
    return Captions.model_validate_json(
        (job.work_dir / "captions.json").read_text(encoding="utf-8")
    )


def _load_plan(job: Job) -> PicturePlan:
    return PicturePlan.model_validate_json(
        (job.work_dir / "plan.json").read_text(encoding="utf-8")
    )


def _raw_path(job: Job) -> Path:
    return job.input_dir / (job.record.input.file if job.record.input else "raw.mp4")


def _cut_path(job: Job) -> Path:
    return job.work_dir / "cut.mp4"


def spec_for_job(job: Job, *, numbers: StyleNumbers | None = None) -> RenderSpec:
    """The RenderSpec from the job's files: plan.json, captions.json and the
    presenter cut (`work/cut.mp4`, 005), with the numbers of the job's resolved style
    (`job.json.style`, 008). The short is as long as the cut list."""
    numbers = numbers or style_numbers(job.record.style)
    plan = _load_plan(job)
    captions = load_captions(job)
    cut = _cut_path(job)
    if not cut.is_file():
        raise RenderError("work/cut.mp4 is missing: cut_presenter runs before the picture")
    return build_spec(
        plan,
        captions,
        presenter=cut,
        source_size=_probe_size(cut),
        duration_s=presenter.total_duration(presenter.cut_list(plan)),
        numbers=numbers,
        manifest=assets.load_manifest(job.path),
        job_dir=job.path,
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
        captions = load_captions(job)
        spec = build_spec(
            plan,
            captions,
            presenter=cut,
            source_size=(WIDTH, HEIGHT),
            duration_s=presenter.total_duration(presenter.cut_list(plan)),
            numbers=style_numbers(job.record.style),
            manifest=assets.load_manifest(job.path),
            job_dir=job.path,
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
