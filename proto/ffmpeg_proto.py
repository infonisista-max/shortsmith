"""Throwaway prototype: work/sample.mp4 -> work/proto_ffmpeg.mp4 with ffmpeg only.

Pipeline (see research.md sections 2, 4 and 5):
  cut 20-50 s -> 9:16 guard (source is already 1080x1920) -> three Hinglish
  caption phrases via a generated ASS file -> Ken Burns still + round PIP for
  output 10-20 s (source 30-40 s) -> two-pass voice loudnorm (stem -19,
  master -14 / -1.5 dBTP).

Run:  uv run python proto/ffmpeg_proto.py
No tests, no installs. ffmpeg via subprocess only (argv lists, no shell).
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
OLD = WORK / "old-engine" / "engine" / "vg-short_source_2026-09-08" / "vg-short" / "public"

SRC = WORK / "sample.mp4"
OUT = WORK / "proto_ffmpeg.mp4"
ASS = WORK / "proto_captions.ass"
STEM = WORK / "proto_voice_stem.wav"
STEM_JSON = WORK / "proto_loudnorm_stem.json"
MASTER_JSON = WORK / "proto_loudnorm_master.json"
FONTS_DIR = OLD / "fonts"  # Poppins-ExtraBold.ttf lives here; used via fontsdir=, nothing installed
# Still: Wikimedia Commons, CC BY-SA 4.0 (attribution required if this ever ships).
STILL = OLD / "img" / "wm_kainchi_dham_wide_ccbysa4.jpg"  # 1920x1080

# --- timeline (seconds) --------------------------------------------------------
CUT_IN, CUT_LEN = 20.0, 30.0  # source 20-50 s -> output 0-30 s
PIP_START, PIP_END = 10.0, 20.0  # output-relative (source 30-40 s)
PIP_FRAMES = int((PIP_END - PIP_START) * 30)  # 300 at 30 fps

# --- PIP geometry (research section 2, STYLE:explainer) -----------------------
# Face point measured once from work/proto_face_check.jpg (source 35 s):
# hair top ~300, eyes ~860, chin ~1330, collar ~1500. FACE_CY=870 -> window 330..1410.
FACE_CY = 870
PIP_DIAM = 300
PIP_X, PIP_Y = 70, 960
PIP_CROP_Y = min(max(FACE_CY - 540, 0), 840)  # clamp so the 1080 square stays inside 1920
# Ring intentionally omitted. If wanted: a second geq alpha band on the PIP stream
# (e.g. 144..150 px radius = white at 95 %), NOT drawbox (drawbox is square-only).

# --- captions (research section 4) --------------------------------------------
# Word times hand-estimated around the output anchors ~2 s, ~6 s, ~13 s.
# Pages: 2-4 words on phrase boundaries; a name/keyword pair never split.


@dataclass
class Word:
    text: str
    start: float
    end: float
    keyword: bool = False


PAGES: list[list[Word]] = [
    # ~2 s: "start ki thi aur finally"  (keyword: finally)
    [Word("start", 2.00, 2.35), Word("ki", 2.38, 2.55), Word("thi", 2.58, 2.80)],
    [Word("aur", 2.95, 3.15), Word("finally", 3.20, 3.70, keyword=True)],
    # ~6 s: "Olympic bhi le aaye the"  (keyword: Olympic)
    [Word("Olympic", 6.00, 6.55, keyword=True), Word("bhi", 6.60, 6.80)],
    [Word("le", 6.85, 7.00), Word("aaye", 7.05, 7.35), Word("the", 7.38, 7.60)],
    # ~13 s: "aapko pata hai kya hai police force"  (keyword: police force)
    [Word("aapko", 13.00, 13.35), Word("pata", 13.40, 13.65), Word("hai", 13.68, 13.85)],
    [Word("kya", 13.95, 14.15), Word("hai", 14.18, 14.35)],
    [Word("police", 14.50, 14.90, keyword=True), Word("force", 14.95, 15.35, keyword=True)],
]

# ASS colours are &HAABBGGRR&. Section 4: unspoken white 86 % alpha, spoken #fff,
# active #FFD60A scaled 1.0 -> 1.08 over 0.10 s, keyword #111 on #FFD60A once spoken.
WHITE = "&HFFFFFF&"
YELLOW = "&H0AD6FF&"  # #FFD60A
INK = "&H111111&"  # #111111
BLACK = "&H000000&"


def ffpath(p: Path) -> str:
    """Path for use inside a filtergraph option on Windows: forward slashes, escaped drive colon.

    The value is wrapped in single quotes by the caller. There is no shell layer
    (argv list), so this is the only escaping needed.
    """
    return str(p.resolve()).replace("\\", "/").replace(":", "\\:")


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(f'"{a}"' if " " in a else a for a in argv), flush=True)
    proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr[-4000:])
        raise SystemExit(f"ffmpeg failed with exit code {proc.returncode}")
    return proc


def parse_loudnorm(stderr: str) -> dict[str, str]:
    """loudnorm print_format=json writes a JSON object to stderr; take the last one."""
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start < 0 or end < start:
        raise SystemExit("no loudnorm JSON found in ffmpeg stderr")
    return json.loads(stderr[start : end + 1])


def measured(m: dict[str, str]) -> str:
    return (
        f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
        f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true"
    )


# --- ASS generation -------------------------------------------------------------


def ass_time(t: float) -> str:
    t = max(t, 0.0)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def page_bounds() -> list[tuple[float, float]]:
    """Section-4 timing: start = first start - 0.04; end = min(last end + 0.9, next start);
    last page holds 1.2 s."""
    out: list[tuple[float, float]] = []
    for i, page in enumerate(PAGES):
        start = page[0].start - 0.04
        hold = 1.2 if i == len(PAGES) - 1 else 0.9
        end = page[-1].end + hold
        if i + 1 < len(PAGES):
            end = min(end, PAGES[i + 1][0].start - 0.04)
        out.append((start, end))
    return out


def word_tags(w: Word, page_start: float) -> str:
    """Per-word override tags. Times are ms relative to the page's Dialogue start.

    Section 4: spoken at start - 0.02, active until end + 0.06. Karaoke \\k only
    gives two states, so each word carries explicit \\t transforms for three
    (unspoken -> active yellow 1.08 -> spoken white / keyword box).
    """
    ws = max(int(round((w.start - 0.02 - page_start) * 1000)), 0)
    we = max(int(round((w.end + 0.06 - page_start) * 1000)), ws + 100)
    base = f"\\1a&H24&\\c{WHITE}\\3c{BLACK}\\bord2\\shad3\\fscx100\\fscy100"
    active = f"\\t({ws},{ws + 100},\\1a&H00&\\c{YELLOW}\\fscx108\\fscy108)"
    if w.keyword:
        # Keyword "box": a 14 px yellow outline hugging the glyphs, no shadow.
        # An exact rectangle (14 px side pad, radius 14) needs text measurement
        # outside ASS (drawing commands positioned by glyph extents); skipped here.
        done = f"\\t({we},{we},\\c{INK}\\3c{YELLOW}\\bord14\\shad0\\fscx100\\fscy100)"
    else:
        done = f"\\t({we},{we},\\c{WHITE}\\fscx100\\fscy100)"
    return "{" + base + active + done + "}"


def glow_tags(w: Word, page_start: float) -> str:
    """Lower layer: transparent fill, 18 px blurred black border = the section-4 glow.
    Carries the same scale transform so it tracks the text layer."""
    ws = max(int(round((w.start - 0.02 - page_start) * 1000)), 0)
    we = max(int(round((w.end + 0.06 - page_start) * 1000)), ws + 100)
    return (
        "{" + f"\\1a&HFF&\\3c{BLACK}\\3a&H80&\\bord18\\blur18\\shad0\\fscx100\\fscy100"
        f"\\t({ws},{ws + 100},\\fscx108\\fscy108)\\t({we},{we},\\fscx100\\fscy100)" + "}"
    )


def write_ass(path: Path) -> None:
    # Style: Poppins ExtraBold (weight 800) at 74 px; Bold=0 so libass never
    # synthesises emboldening on top of the 800 face. Spacing 0.5 = letter
    # spacing. ASS has no line-height control, so 1.35 is not reproduced.
    # Alignment 2 (bottom centre), MarginV 460 -> text bottom at y 1460,
    # MarginL/R 60. BorderStyle 1, Outline 2, Shadow 3 = section-4 stroke.
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Cap,Poppins ExtraBold,74,&H00FFFFFF,&H24FFFFFF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0.5,0,1,2,3,2,60,60,460,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for page, (ps, pe) in zip(PAGES, page_bounds()):
        st, et = ass_time(ps), ass_time(pe)
        glow = " ".join(glow_tags(w, ps) + w.text for w in page)
        text = " ".join(word_tags(w, ps) + w.text for w in page)
        # Page enter: opacity over 0.06 s. The 0.94 -> 1 page scale is dropped
        # because per-word \fscx overrides would fight a line-level one.
        lines.append(f"Dialogue: 0,{st},{et},Cap,,0,0,0,,{{\\fad(60,0)}}{glow}")
        lines.append(f"Dialogue: 1,{st},{et},Cap,,0,0,0,,{{\\fad(60,0)}}{text}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- ffmpeg passes --------------------------------------------------------------

VOICE_PRE = (
    "pan=mono|c0=0.5*c0+0.5*c1,"  # mono in the graph, never -ac 1 (3.6 dB lesson)
    "highpass=f=80,"
    "acompressor=threshold=-18dB:ratio=2.5:attack=8:release=120"
)
STEM_TARGET = "loudnorm=I=-19:TP=-3:LRA=11"
MASTER_PRE = "aformat=channel_layouts=stereo,alimiter=limit=0.95:attack=5:release=50"
MASTER_TARGET = "loudnorm=I=-14:TP=-1.5:LRA=11"
MASTER_POST = "alimiter=limit=0.891:attack=3:release=60:level=false,aresample=48000"


def cut_input() -> list[str]:
    return ["-ss", f"{CUT_IN}", "-t", f"{CUT_LEN}", "-i", str(SRC)]


def video_graph() -> str:
    pip_win = f"enable='between(t,{PIP_START},{PIP_END})'"
    r = PIP_DIAM / 2
    return ";".join(
        [
            # base: 9:16 guard (no-op for this 1080x1920 source), 30 fps, pts from 0
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            "setsar=1,fps=30,setpts=PTS-STARTPTS,split=2[base][pipsrc]",
            # still: centre-crop 9:16, pre-scale 2x to tame zoompan's integer jitter,
            # Ken Burns 1.10 -> 1.16 over PIP_FRAMES, then shift onto the timeline.
            "[1:v]crop=608:1080:(iw-608)/2:0,scale=2160:3840,"
            f"zoompan=z='1.10+0.06*on/{PIP_FRAMES - 1}':d={PIP_FRAMES}"
            ":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
            f"setpts=PTS-STARTPTS+{PIP_START}/TB[still]",
            # pip: full-width square centred on the face point, 300 px, circular alpha
            f"[pipsrc]crop=1080:1080:0:{PIP_CROP_Y},scale={PIP_DIAM}:{PIP_DIAM},format=yuva444p,"
            "geq=lum='p(X,Y)':cb='p(X,Y)':cr='p(X,Y)'"
            f":a='255*clip({r + 1}-sqrt((X-{r})^2+(Y-{r})^2),0,1)'[pip]",
            f"[base][still]overlay=0:0:eof_action=pass:{pip_win}[b1]",
            f"[b1][pip]overlay={PIP_X}:{PIP_Y}:eof_action=pass:{pip_win}[b2]",
            f"[b2]subtitles=filename='{ffpath(ASS)}':fontsdir='{ffpath(FONTS_DIR)}',format=yuv420p[vout]",
        ]
    )


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}")
    if not STILL.exists():
        raise SystemExit(f"missing still {STILL}")
    write_ass(ASS)
    print(f"wrote {ASS}")

    # Pass 1: measure the voice stem.
    p1 = run(
        ["ffmpeg", "-hide_banner", "-nostats", "-y", *cut_input(), "-vn",
         "-af", f"{VOICE_PRE},{STEM_TARGET}:print_format=json", "-f", "null", "-"]
    )
    stem_m = parse_loudnorm(p1.stderr)
    STEM_JSON.write_text(json.dumps(stem_m, indent=2))
    print(f"stem measured I={stem_m['input_i']} TP={stem_m['input_tp']} LRA={stem_m['input_lra']}")

    # Pass 2: render the stem (mono, 48 kHz, -19 LUFS / -3 dBTP, linear).
    run(
        ["ffmpeg", "-hide_banner", "-nostats", "-y", *cut_input(), "-vn",
         "-af", f"{VOICE_PRE},{STEM_TARGET}:{measured(stem_m)},aresample=48000",
         "-c:a", "pcm_s16le", str(STEM)]
    )

    # Pass 3: measure the master (voice-only mix: stereo upmix + mixer limiter).
    p3 = run(
        ["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(STEM),
         "-af", f"{MASTER_PRE},{MASTER_TARGET}:print_format=json", "-f", "null", "-"]
    )
    master_m = parse_loudnorm(p3.stderr)
    MASTER_JSON.write_text(json.dumps(master_m, indent=2))
    print(f"master measured I={master_m['input_i']} TP={master_m['input_tp']}")

    # Pass 4: final render, one filter_complex for video + master audio chain.
    graph = video_graph() + ";" + (
        f"[2:a]{MASTER_PRE},{MASTER_TARGET}:{measured(master_m)},{MASTER_POST}[aout]"
    )
    run(
        ["ffmpeg", "-hide_banner", "-nostats", "-y",
         *cut_input(), "-i", str(STILL), "-i", str(STEM),
         "-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
         "-t", f"{CUT_LEN}", "-r", "30",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
         str(OUT)]
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
