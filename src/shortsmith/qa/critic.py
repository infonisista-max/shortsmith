"""The editorial gate: the vision critic (decisions 10.2, 10.3, 12.1; ticket 033).

Runs on every job from day one, after the technical gate has passed and the contact
sheet exists, and is ADVISORY until the calibration streak of 034 flips it: the critic
rates, the operator rates on the phone, both land on the job and are compared. So a
critic that cannot answer never blocks delivery here; its report reads `unavailable`
with the reason, and the job is `delivered` all the same.

`score(inputs) -> CriticReport`: `VisionCritic` is one Anthropic Messages call with
the images and the texts, model from `CRITIC_MODEL`; `FakeCritic` (12.1) answers fixed
scores and reasons and records what it was shown. `build_inputs(job)` assembles the
10.3 inputs from the job's files: the contact sheet (`out/contact.jpg`), the PIP strip
(the eight measured stills as the circle shows them, composed side by side), the hook
strip (the first 2 s of `out/short.mp4` at 4 fps), the plan summary (beat count, mode
fractions, density, clamps, rescued beats, asset origins), the stem balance report,
the transcript, the approved-shorts anchors from `docs/reference/README.md` and the
category's pattern data from `docs/reference/<category>/README.md` when the library
has it (039 grows this into the measured ranges; here a missing category is a note in
the report, never a score against nothing). `run(job, critic)` is the pipeline's step:
build, score, write the report into `out/qa.json` beside T1-T13, note `job.log`.

Cost (5.6, 11.3): the call is checked against the hard cap first, estimated at the
texts' length in tokens plus a fixed allowance per image plus `max_tokens`; the hard
cap is not an API failure and reaches the pipeline as `BudgetExceeded`, which fails
the job visibly as every refused paid call does. Once the API answers, its `usage` is
one `critic` row in the `qa` step with fresh, cache-write and cache-read input tokens
at their own price keys, recorded before the reply is parsed. The rubric and the
anchors carry cache markers: they are the same for every job of a pack version.
"""

from __future__ import annotations

import base64
import copy
import json
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Self, cast

import anthropic
from anthropic.types import ImageBlockParam, Message, MessageParam, TextBlockParam
from PIL import Image
from pydantic import SecretStr

from shortsmith import assets, contact_sheet, ffmpeg, jobs, sound
from shortsmith.config import Settings
from shortsmith.contracts import (
    CRITIC_LINES,
    CRITIC_NOTES_MAX,
    AssetManifest,
    BalanceReport,
    CriticLine,
    CriticReport,
    PicturePlan,
    Transcript,
    ValidatedPlan,
)
from shortsmith.jobs import Job
from shortsmith.ledger import Ledger
from shortsmith.qa import technical

PROVIDER = "critic"
STEP = "qa"  # the pipeline step the critic runs in (after the gate, before `delivered`)
DEFAULT_MODEL = "claude-sonnet-5"  # 10.2: a config string like the judge's
MAX_TOKENS = 4000  # ten lines with a reason each, an overall and five notes
TIMEOUT_S = 300.0
MAX_RETRIES = 2
CHARS_PER_TOKEN = 3  # a generous token estimate for the hard-cap check only
TOKENS_PER_IMAGE = 2000  # a strip's worth of image tokens, for the same estimate
# 10.2: advisory until 034's calibration streak says otherwise.
ADVISORY = True

REFERENCE_DIR = Path(__file__).resolve().parents[3] / "docs" / "reference"
REFERENCE_README = REFERENCE_DIR / "README.md"
ANCHOR_SECTIONS = ("The bar", "The two references")
NO_REFERENCE_PACK = "(no reference pack: docs/reference/README.md is missing)"
NO_BALANCE = "no stem balance report (the mix left none)"
STRIP_FRAME_W = 270  # each frame of the PIP and hook strips the critic is shown
STRIP_GUTTER = 8
STRIP_QUALITY = 80
HOOK_FPS = contact_sheet.HOOK_FPS
HOOK_SECONDS = contact_sheet.HOOK_SECONDS

CONTACT_LABEL = (
    "Contact sheet: the hook strip (first 2 s at 4 fps), the PIP strip, then one frame "
    "per second with a strip line under each (beat id, presenter mode F/P/O, visual kind "
    "as drawn, asset origin letter; a red corner marks a rescued or downgraded beat), "
    "safe-area outlines on the first frame of each row, and the technical summary panel."
)
PIP_LABEL = (
    "PIP strip: the eight strip stills cropped through the measured window, as the "
    "presenter circle shows them, with the detector's face box drawn on each."
)
HOOK_LABEL = "Hook strip: the first 2 s of the short at 4 fps, left to right."

RUBRIC = (
    ("E1", "hook", "the first two seconds: a cold open that punches in on a face, then a "
     "title and cards that earn the next ten seconds"),
    ("E2", "broll_relevance", "every picture shows what its beat is about; cards and "
     "photos match the words, set pieces montage the short's own pictures"),
    ("E3", "mode_variation", "full, PIP and off alternate; no long run of one mode, the "
     "presenter never full-frame twice in a row"),
    ("E4", "density", "something changes on screen at least every 1.5 s: a beat, a landed "
     "event, a fly-in; nothing sits still"),
    ("E5", "captions", "two to four words a page, the keyword boxed, the block above the "
     "PIP and inside the safe area, hidden from the finale word"),
    ("E6", "pip_framing", "whole head plus neck and collar in the circle, chin near the "
     "lower third of it, never a tight face crop"),
    ("E7", "sound", "a quiet bed under the voice with short hits on stamps, reveals and "
     "the finale; no sweeps, no whooshes, nothing on cuts"),
    ("E8", "payoff", "the finale answers the hook; a callback, a reused asset or a number "
     "closes the loop the hook opened"),
    ("E9", "integrity", "every asset credited or disclosed, no watermark, no meme, no "
     "text inside a generated picture, numbers drawn from real data"),
    ("E10", "embarrassment", "nothing the presenter would be embarrassed to have posted: "
     "no mid-word cut, no frozen frame, no wrong picture, no misspelt stamp"),
)  # fmt: skip

SYSTEM_PROMPT = (
    "You are the editorial critic for Shortsmith, which turns a creator's talking-head "
    "recording into a 9:16 YouTube Short. You judge one finished short from its evidence: "
    "the contact sheet, the PIP strip, the hook strip, the plan summary, the stem balance "
    "report and the transcript. You do not see the video itself.\n"
    "The bar is the market's best: editing at the level of top YouTube Shorts "
    "(Dhruv Rathee-style, CapCut-level polish). Calibration: the operator's two approved "
    "shorts, described in the anchors, rate 6 out of 10 on this scale; top-creator "
    "reference shorts rate 8; 10 is flawless and 1 is unwatchable. Where the category's "
    "pattern data gives measured ranges, score against them.\n"
    "Score every line 1-10 with exactly one reason each, in this order:\n"
    + "\n".join(f"{name} ({label}): {text}." for name, label, text in RUBRIC)
    + "\nThen give `overall`, 1-10, your verdict on the whole short (not an average), and "
    f"up to {CRITIC_NOTES_MAX} `fix_notes`: concrete fixes an editor could make in five "
    "minutes, the most valuable first.\n"
    'Answer with JSON only: {"lines": [{"name": "E1", "score": 7, "reason": "..."}, ...], '
    '"overall": 7, "fix_notes": ["..."]}, the ten line objects in order, and nothing else.'
)

_JSON = re.compile(r"\{.*\}", re.DOTALL)
_LABELS = dict(CRITIC_LINES)


class CriticError(RuntimeError):
    """The critic could not answer (an API error, a reply that is not the report). The
    step writes an `unavailable` report and the job stays delivered (10.2)."""


@dataclass(frozen=True)
class Inputs:
    """The 10.3 inputs as the critic sees them: three JPEG strips (None where the job
    has none, with the reason in `notes`) and the texts."""

    contact_sheet: bytes | None
    pip_strip: bytes | None
    hook_strip: bytes | None
    plan_summary: str
    balance: str
    transcript: str
    anchors: str
    pattern_data: str
    category: str
    notes: tuple[str, ...] = ()


class Critic(ABC):
    """`score(inputs)` returns the report; `bind(job)` names the job a real critic
    writes its ledger row against (the fake ignores it)."""

    model: str

    def bind(self, job: Job) -> Self:
        return self

    @abstractmethod
    def score(self, inputs: Inputs) -> CriticReport: ...


class FakeCritic(Critic):
    """12.1: fixed scores and reasons, the inputs recorded so a test or the smoke can
    prove what the critic was shown. `overall` is settable for the calibration tests
    (034), `scores` for a line-by-line case."""

    SCORES: tuple[int, ...] = (7, 8, 7, 6, 8, 7, 7, 6, 9, 9)
    OVERALL = 7
    NOTES: tuple[str, ...] = (
        "Tighten the cold open by one beat.",
        "Land the stamp on the number, not before it.",
    )

    def __init__(
        self,
        *,
        model: str = "fake",
        scores: Sequence[int] | None = None,
        overall: int | None = None,
    ) -> None:
        self.model = model
        self.scores = tuple(scores) if scores is not None else self.SCORES
        self.overall = overall if overall is not None else self.OVERALL
        self.calls = 0
        self.inputs: list[Inputs] = []

    def score(self, inputs: Inputs) -> CriticReport:
        self.calls += 1
        self.inputs.append(inputs)
        lines = [
            CriticLine(name=name, label=label, score=score, reason=f"fake: {label} as planned")
            for (name, label), score in zip(CRITIC_LINES, self.scores, strict=True)
        ]
        return CriticReport(
            lines=lines,
            overall=self.overall,
            fix_notes=list(self.NOTES),
            model=self.model,
            category=inputs.category,
            notes=list(inputs.notes),
        )


def unavailable(
    model: str, reason: str, *, category: str, notes: Sequence[str] = ()
) -> CriticReport:
    """The report of a critic that could not answer: no lines, the reason first."""
    return CriticReport(
        status="unavailable", model=model, category=category, notes=[reason, *notes]
    )


# --- the inputs (10.3) --------------------------------------------------------------------


def anchors_text(readme: Path = REFERENCE_README) -> str:
    """The bar and the two approved shorts from the reference pack's README: its
    `## The bar` and `## The two references` sections, headings included, nothing of
    the evidence pointers or the ffmpeg commands."""
    if not readme.is_file():
        return NO_REFERENCE_PACK
    kept: list[str] = []
    keeping = False
    for line in readme.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            keeping = line[3:].strip() in ANCHOR_SECTIONS
        if keeping:
            kept.append(line)
    return "\n".join(kept).strip() or NO_REFERENCE_PACK


def pattern_data(category: str, *, reference_dir: Path = REFERENCE_DIR) -> tuple[str, str | None]:
    """The category's README text and None, or "" and the note that there is none."""
    path = reference_dir / category / "README.md"
    if not path.is_file():
        return "", f"no reference data for {category}"
    return path.read_text(encoding="utf-8").strip(), None


def _pct(part: float, whole: float) -> str:
    return f"{round(100 * part / whole) if whole else 0}%"


def _counts(counter: Counter[str]) -> str:
    return ", ".join(f"{name} {n}" for name, n in counter.most_common()) or "none"


def plan_summary(
    plan: PicturePlan, validated: ValidatedPlan | None, manifest: AssetManifest | None
) -> str:
    """The 10.3 plan summary in plain lines: beat count and lengths, mode fractions of
    the runtime, density, kinds, overlays, events, transitions, the hook and the finale,
    the clamps and warnings, the assets by origin and the rescued beats."""
    beats = plan.beats
    lengths = [b.end - b.start for b in beats]
    runtime = sum(lengths)
    by_mode: dict[str, float] = {}
    for beat, length in zip(beats, lengths, strict=True):
        by_mode[beat.mode] = by_mode.get(beat.mode, 0.0) + length
    kinds = Counter(str(b.kind) for b in beats)
    overlays = Counter(str(o) for b in beats for o in b.overlays)
    events = Counter[str]()
    for beat in beats:
        if beat.event.kind != "none":
            events[beat.event.kind] += 1
        if beat.counter is not None:
            events["counter"] += 1
    enters = Counter(str(b.enter) for b in beats)
    lines = [
        f"title: {plan.title}",
        f"category: {plan.category}",
        f"runtime {runtime:.1f} s, {len(beats)} beats, mean beat {runtime / len(beats):.2f} s, "
        f"longest beat {max(lengths):.2f} s, shortest {min(lengths):.2f} s, "
        f"{10 * len(beats) / runtime:.1f} beats per 10 s",
        "modes by runtime: " + ", ".join(
            f"{mode} {_pct(by_mode.get(mode, 0.0), runtime)}" for mode in ("full", "pip", "off")
        ),
        f"kinds: {_counts(kinds)}",
        f"overlays: {_counts(overlays)}",
        f"landed events: {_counts(events)}",
        f"enter transitions: {_counts(enters)}",
        f"hook title: {plan.hook.title} (cold open {plan.hook.cold_open_span.start:g}-"
        f"{plan.hook.cold_open_span.end:g} s, original {plan.hook.original_position})",
        f"finale word: {plan.finale.text}",
    ]
    if validated is not None:
        clamps = validated.clamps
        noun = "clamp" if len(clamps) == 1 else "clamps"
        lines.append(
            f"{len(clamps)} {noun}"
            + (": " + "; ".join(f"({c.rule}) {c.message}" for c in clamps) if clamps else "")
        )
        lines.append(
            "warnings: " + ("; ".join(validated.warnings) if validated.warnings else "none")
        )
    if manifest is not None:
        origins = Counter(str(a.origin) for a in manifest.assets)
        rescued = [f"{b.beat_id} (rung {b.fallback_rung})" for b in manifest.beats if b.rescued]
        lines.append(
            f"assets: {len(manifest.assets)} unique; origins: "
            + (", ".join(f"{o}: {n}" for o, n in origins.most_common()) or "none")
        )
        lines.append(
            f"{len(rescued)} rescued" + (": " + ", ".join(rescued) if rescued else "")
        )
        lines.append(f"judge: {manifest.judge_calls}/{manifest.judge_max} calls")
    return "\n".join(lines)


def balance_text(report: BalanceReport | None) -> str:
    """The 7.3 balance report in one line each; the band it was held to beside it."""
    if report is None:
        return NO_BALANCE
    low, high = report.bed_accept_db
    parts = [f"voice {report.voice_db:.1f} dB"]
    if report.bed_under_voice_db is not None:
        parts.append(
            f"bed {report.bed_under_voice_db:.1f} dB relative to the voice "
            f"(accept {low:g} to {high:g})"
        )
    else:
        parts.append("no bed")
    if report.duck_db is not None:
        parts.append(f"duck {report.duck_db:.1f} dB (max {report.duck_max_db:g})")
    if report.speech_band_margin_db is not None:
        parts.append(
            f"speech-band margin {report.speech_band_margin_db:.1f} dB "
            f"(min {report.speech_band_margin_min_db:g})"
        )
    parts.append(f"{report.cues} cues")
    parts.append(
        "problems: " + "; ".join(report.problems) if report.problems else "inside the 7.3 band"
    )
    return "\n".join(parts)


def transcript_text(transcript: Transcript) -> str:
    words = " ".join(w.text for w in transcript.words)
    return (
        f"Language {transcript.language}, {transcript.duration_s:.1f} s, "
        f"{len(transcript.words)} words:\n{words}"
    )


def _strip_jpeg(frames: Sequence[Image.Image]) -> bytes:
    """`frames` side by side on the sheet's background, as one JPEG."""
    height = max(f.height for f in frames)
    width = sum(f.width for f in frames) + STRIP_GUTTER * (len(frames) + 1)
    strip = Image.new("RGB", (width, height + 2 * STRIP_GUTTER), contact_sheet.BG_COLOUR)
    x = STRIP_GUTTER
    for frame in frames:
        strip.paste(frame.convert("RGB"), (x, STRIP_GUTTER))
        x += frame.width + STRIP_GUTTER
    buffer = BytesIO()
    strip.save(buffer, format="JPEG", quality=STRIP_QUALITY, optimize=True)
    return buffer.getvalue()


def pip_strip(job: Job) -> bytes | None:
    """The eight measured stills as the circle shows them (013), side by side; None
    when the job was not measured or the stills are gone."""
    record = jobs.load(job.path).record
    if record.presenter is None:
        return None
    cells, _ = contact_sheet.pip_row(job, record.presenter)
    if not cells:
        return None
    scale = STRIP_FRAME_W / contact_sheet.PIP_W
    sized = [
        c.resize((STRIP_FRAME_W, round(c.height * scale)))  # pyright: ignore[reportUnknownMemberType]
        for c in cells
    ]
    return _strip_jpeg(sized)


def hook_strip(job: Job) -> bytes | None:
    """The first 2 s of `out/short.mp4` at 4 fps, side by side; None when there is no
    short to read. A short ffmpeg cannot read raises `FFmpegError`."""
    short = job.out_dir / "short.mp4"
    if not short.is_file() or short.stat().st_size == 0:
        return None
    frames = [
        Image.frombytes("RGB", (w, h), px)
        for w, h, px in ffmpeg.frames_rgb(
            short, fps=HOOK_FPS, width=STRIP_FRAME_W, duration_s=HOOK_SECONDS
        )
    ]
    return _strip_jpeg(frames) if frames else None


def build_inputs(job: Job, *, reference_dir: Path = REFERENCE_DIR) -> Inputs:
    """The 10.3 inputs from the job's files. Nothing here fails the job: a strip that
    cannot be made is None with a note, a text file that is missing reads as such."""
    notes: list[str] = []
    sheet = job.out_dir / "contact.jpg"
    contact = sheet.read_bytes() if sheet.is_file() else None
    if contact is None:
        notes.append("contact sheet: out/contact.jpg is missing")
    pip = pip_strip(job)
    if pip is None:
        notes.append("PIP strip: the job has no measured stills")
    try:
        hook = hook_strip(job)
    except ffmpeg.FFmpegError as exc:
        hook, why = None, f"out/short.mp4 could not be read ({str(exc).strip()[:120]})"
    else:
        why = "no short to read"
    if hook is None:
        notes.append(f"hook strip: {why}")
    plan_path = job.work_dir / "plan.json"
    plan = (
        PicturePlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
        if plan_path.is_file()
        else None
    )
    validated_path = job.work_dir / "plan.validated.json"
    validated = (
        ValidatedPlan.model_validate_json(validated_path.read_text(encoding="utf-8"))
        if validated_path.is_file()
        else None
    )
    manifest = assets.load_manifest(job.path)
    if plan is not None:
        summary = plan_summary(plan, validated, manifest)
        category = plan.category
    else:
        summary, category = "no plan: work/plan.json is missing", "other"
        notes.append("plan summary: work/plan.json is missing")
    asr = job.work_dir / "asr.json"
    if asr.is_file():
        words = Transcript.model_validate_json(asr.read_text(encoding="utf-8"))
        transcript = transcript_text(words)
    else:
        transcript = "no transcript: work/asr.json is missing"
        notes.append("transcript: work/asr.json is missing")
    data, note = pattern_data(category, reference_dir=reference_dir)
    if note is not None:
        notes.append(note)
    return Inputs(
        contact_sheet=contact,
        pip_strip=pip,
        hook_strip=hook,
        plan_summary=summary,
        balance=balance_text(sound.balance_report(job.work_dir / "stems")),
        transcript=transcript,
        anchors=anchors_text(reference_dir / "README.md"),
        pattern_data=data,
        category=category,
        notes=tuple(notes),
    )


# --- the vision adapter (10.2) ------------------------------------------------------------

# The seam tests replace: what one Messages call is, keyword arguments in and the SDK's
# own `Message` out, exactly as the API planner and the judge define it.
Create = Callable[..., Message]


def create_message(api_key: SecretStr, *, max_retries: int, timeout_s: float) -> Create:
    def create(
        *,
        model: str,
        max_tokens: int,
        system: list[TextBlockParam],
        messages: list[MessageParam],
    ) -> Message:
        client = anthropic.Anthropic(
            api_key=api_key.get_secret_value(), max_retries=max_retries, timeout=timeout_s
        )
        return client.messages.create(
            model=model, max_tokens=max_tokens, system=system, messages=messages
        )

    return create


def _text(text: str, *, cached: bool = False) -> TextBlockParam:
    if cached:
        return {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}
    return {"type": "text", "text": text}


def _image(body: bytes) -> ImageBlockParam:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.b64encode(body).decode("ascii"),
        },
    }


def request_content(inputs: Inputs) -> list[TextBlockParam | ImageBlockParam]:
    """The user turn: the texts first, then each strip introduced by a line saying
    what it is, so the model knows which strip it is looking at."""
    data = inputs.pattern_data or "(none for this category)"
    content: list[TextBlockParam | ImageBlockParam] = [
        _text(f"## Category pattern data ({inputs.category})\n{data}"),
        _text(f"## Plan summary\n{inputs.plan_summary}"),
        _text(f"## Stem balance\n{inputs.balance}"),
        _text(f"## Transcript\n{inputs.transcript}"),
    ]
    if inputs.notes:
        listed = "\n".join(f"- {n}" for n in inputs.notes)
        content.append(_text(f"## Notes on the inputs\n{listed}"))
    for label, body in (
        (CONTACT_LABEL, inputs.contact_sheet),
        (PIP_LABEL, inputs.pip_strip),
        (HOOK_LABEL, inputs.hook_strip),
    ):
        if body is not None:
            content += [_text(label), _image(body)]
    return content


def parse_reply(
    reply: str, *, model: str, category: str, notes: Sequence[str] = ()
) -> CriticReport:
    """The report from the model's JSON: every rubric line by name (a missing one is a
    `CriticError`, never a made-up score), scores clamped to 1-10, `overall` clamped or,
    when missing, the rounded mean, and the notes cut to five."""
    match = _JSON.search(reply)
    if match is None:
        raise CriticError("the critic did not answer with JSON")
    try:
        body: object = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise CriticError(f"the critic's JSON did not parse: {exc}") from None
    listed = _field(body, "lines")
    if not isinstance(listed, list):
        raise CriticError("the critic's JSON has no `lines` list")
    scored: dict[str, CriticLine] = {}
    for i, item in enumerate(cast("list[object]", listed), start=1):
        name = _field(item, "name")
        name = name.strip().upper() if isinstance(name, str) else f"E{i}"
        label = _LABELS.get(name)
        score = _field(item, "score")
        if label is None or not isinstance(score, int | float):
            continue
        reason = _field(item, "reason")
        scored[name] = CriticLine(
            name=name,
            label=label,
            score=_clamp(score),
            reason=reason.strip() if isinstance(reason, str) else "",
        )
    lines: list[CriticLine] = []
    for name, label in CRITIC_LINES:
        if name not in scored:
            raise CriticError(f"the critic did not score {name} ({label})")
        lines.append(scored[name])
    overall = _field(body, "overall")
    if isinstance(overall, int | float):
        overall_score = _clamp(overall)
    else:
        overall_score = _clamp(sum(line.score for line in lines) / len(lines))
    raw_notes = _field(body, "fix_notes")
    fix_notes = [
        n.strip()
        for n in cast("list[object]", raw_notes if isinstance(raw_notes, list) else [])
        if isinstance(n, str) and n.strip()
    ][:CRITIC_NOTES_MAX]
    return CriticReport(
        lines=lines,
        overall=overall_score,
        fix_notes=fix_notes,
        model=model,
        category=category,
        notes=list(notes),
    )


def _clamp(value: float) -> int:
    return min(max(round(value), 1), 10)


def _field(value: object, name: str) -> object:
    return cast("dict[str, object]", value).get(name) if isinstance(value, dict) else None


def _error_text(body: object) -> str:
    """The API's own words from its error body; never the key, never a stack."""
    message = _field(_field(body, "error"), "message")
    return str(message)[:500] if message is not None else repr(body)[:500]


def _units(message: Message) -> dict[str, float]:
    usage = message.usage
    return {
        "input_tokens": usage.input_tokens,
        "cache_write_input_tokens": usage.cache_creation_input_tokens or 0,
        "cache_read_input_tokens": usage.cache_read_input_tokens or 0,
        "output_tokens": usage.output_tokens,
    }


class VisionCritic(Critic):
    """One Messages call per job with the three strips and the texts (10.2)."""

    def __init__(
        self,
        ledger: Callable[[], Ledger],
        *,
        api_key: SecretStr | None,
        model: str = DEFAULT_MODEL,
        create: Create | None = None,
        max_retries: int = MAX_RETRIES,
        timeout_s: float = TIMEOUT_S,
        max_tokens: int = MAX_TOKENS,
    ) -> None:
        self._ledger = ledger
        self._api_key = api_key
        self.model = model
        self._create = create
        self._max_retries = max_retries
        self._timeout_s = timeout_s
        self._max_tokens = max_tokens
        self._job: Job | None = None

    def bind(self, job: Job) -> Self:
        bound = copy.copy(self)
        bound._job = job
        return bound

    def score(self, inputs: Inputs) -> CriticReport:
        job = self._job
        if job is None:
            raise CriticError("VisionCritic has no job: bind(job) before calling")
        if self._api_key is None:
            raise CriticError("CRITIC=api needs ANTHROPIC_API_KEY in .env")
        content = request_content(inputs)
        system = [_text(SYSTEM_PROMPT, cached=True), _text(inputs.anchors, cached=True)]
        chars = sum(len(b["text"]) for b in [*system, *content] if b["type"] == "text")
        images = sum(1 for b in content if b["type"] == "image")

        book = self._ledger()
        estimate = {
            "input_tokens": math.ceil(chars / CHARS_PER_TOKEN) + images * TOKENS_PER_IMAGE,
            "output_tokens": self._max_tokens,
        }
        book.check_before_call(job, STEP, book.estimate(PROVIDER, estimate))
        create = self._create or create_message(
            self._api_key, max_retries=self._max_retries, timeout_s=self._timeout_s
        )
        try:
            message = create(
                model=self.model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.APIStatusError as exc:
            raise CriticError(
                f"the critic answered {exc.status_code}: {_error_text(exc.body)}"
            ) from None
        except anthropic.APIError as exc:
            raise CriticError(f"the critic could not be reached: {exc.message}") from None
        book.record(job, STEP, PROVIDER, message.model, _units(message))
        if message.stop_reason == "refusal":
            raise CriticError("the critic call was refused by the model (stop_reason refusal)")
        if message.stop_reason == "max_tokens":
            raise CriticError(
                f"the critic's reply was cut off at max_tokens ({self._max_tokens})"
            )
        reply = "".join(block.text for block in message.content if block.type == "text")
        return parse_reply(reply, model=message.model, category=inputs.category,
                           notes=inputs.notes)  # fmt: skip


def from_settings(settings: Settings, *, ledger: Callable[[], Ledger]) -> Critic:
    """The critic `CRITIC` names (10.2): `fake` for tests, the smoke and a local run
    with no key; `api` is the vision critic on `CRITIC_MODEL`."""
    if settings.critic == "fake":
        return FakeCritic()
    return VisionCritic(ledger, api_key=settings.anthropic_api_key, model=settings.critic_model)


# --- the step (10.2) ----------------------------------------------------------------------


def run(job: Job, critic: Critic, *, reference_dir: Path = REFERENCE_DIR) -> CriticReport:
    """The pipeline's critic step, after the gate has passed and the sheet exists: build
    the inputs, score, write the report into `out/qa.json` and note `job.log`. A critic
    that cannot answer (`CriticError`) leaves an `unavailable` report and the job goes
    on to `delivered`; the hard cap (`BudgetExceeded`) is not caught, it fails the job
    as every refused paid call does (11.3)."""
    report = technical.load_report(job)
    if report is None:
        raise CriticError("out/qa.json is missing: the gate runs before the critic")
    inputs = build_inputs(job, reference_dir=reference_dir)
    try:
        result = critic.bind(job).score(inputs)
    except CriticError as exc:
        result = unavailable(critic.model, str(exc), category=inputs.category, notes=inputs.notes)
        jobs.note(job, f"critic: unavailable: {exc}")
    else:
        result = result.model_copy(update={"advisory": ADVISORY})
        mode = "advisory" if ADVISORY else "blocking"
        scores = ", ".join(f"{line.name} {line.score}" for line in result.lines)
        jobs.note(
            job, f"critic: overall {result.overall}/10 {mode} ({result.model}): {scores}"
        )
    technical.write_report(job, report.model_copy(update={"critic": result}))
    return result
