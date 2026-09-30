"""The change box (098; work/editor-design.md "Change box (job page)"): the operator types
what to change about a delivered reel in plain words, the model turns the words into
ops from a CLOSED set, code checks every op against the real plan and applies it.

The ops (`OPS`):
- `replace_visual{beat}`: the beat's visual goes; the replacement ladder (096)
  re-sources a plain picture for it (`repairs.replace_visual`, the beat marked replaced).
- `drop_layer{beat,layer}`: one layer the beat carries off (`repairs.drop_layer`).
- `show_reference{beat,ref}`: the beat shows one of the owner's references
  (`input/refs.json` only); a beat that is not a photo or card becomes a photo first.
- `new_image{beat,query,depicts}`: the beat's visual is replaced and re-sourced for the
  operator's words: its query and what it depicts are set, the beat marked replaced.
- `music{from_s,to_s,db}`: the mood curve (`work/sound.json`) moved by `db` between the
  two reel times, with points added at the range edges and a `sound.ramp_min_s` ramp
  outside each so nothing else moves; every level clipped to the style's
  `sound.swell_max_db` / `sound.drop_min_db` (the grammar's +4/-8).
- `music_level{offset_db}`: the whole reel's bed level, the slider's path (`level.remix`).

`plan_change` asks the model once (`Planner.ask`, step `change`) with the brief, the
transcript words at their reel seconds, every beat (times, kind, what it shows, its
layers, what is said on it), the owner's references and the mood curve. The reply is
`{"ops":[...],"summary":"..."}` or `{"refuse":"..."}`. Any unknown op, beat, layer or
reference, or a bad number, refuses the WHOLE change with the reason; nothing is ever
applied in part. A planner with no model behind it (the fake) or a transport failure
refuses with "the editor is not available: ...".

`apply_change`: a picture op patches `work/plan.json` and `work/plan.validated.json`
(re-validated on the output timeline with the soft rules kept; a hard violation refuses
the change and nothing is written) and rebuilds `work/captions.json`
(`pipeline.patch_picture`, the rescues' own path), then the short is kept as
`out/previous/short.mp4` (one previous version only) and the job is reworked to
`uploaded` with `retry_from=sourcing` for the worker to run; the change stays `running`
until the job delivers again (`jobs.finish_changes`). Sound-only ops patch
`work/sound.json` and remix the audio only: a `music` op rebuilds the bed stems with the
new curve (`sound.recurve`, the renderer's `_music_stem`) through 090's delivery
(`level.deliver`: duck, premix, master, remux with the picture copied, T4), a
`music_level` op is the slider's `level.remix`. Every change is a `job.json.changes`
row and `change:` lines in job.log; every op applied an `EditorDecision` by `operator`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast, get_args

from pydantic import TypeAdapter

from shortsmith import grammar, jobs, pipeline, presenter, render, sound, styles
from shortsmith.assets.generate import depicts_of
from shortsmith.contracts import (
    Beat,
    ChangeRequest,
    Depicts,
    EditorDecision,
    MoodPoint,
    PicturePlan,
    ReferenceRecord,
    SoundStory,
    Transcript,
    ValidatedPlan,
)
from shortsmith.editor import repairs
from shortsmith.editor.repairs import LAYERS, Layer, RepairError
from shortsmith.jobs import Clock, Job
from shortsmith.planner import Planner
from shortsmith.sound import level
from shortsmith.styles import StyleSpec

PICTURE_OPS = ("replace_visual", "drop_layer", "show_reference", "new_image")
SOUND_OPS = ("music", "music_level")
OPS = PICTURE_OPS + SOUND_OPS
DEPICTS: tuple[str, ...] = get_args(Depicts)
PREVIOUS_DIR = "previous"
PREVIOUS_NAME = "short.mp4"
PENDING_NAME = "short.pending.mp4"
UNAVAILABLE = "the editor is not available: "
SWEPT_SENTENCE = (
    "The working files for this job were deleted 24 hours after upload, so the reel can no "
    "longer be changed."
)
EPS = 1e-6
_REFS = TypeAdapter(list[ReferenceRecord])
_JSON = re.compile(r"\{.*\}", re.DOTALL)
_CLOCK_TIME = re.compile(r"^\s*(\d+):(\d{1,2}(?:\.\d+)?)\s*$")


class ChangeRefused(Exception):
    """The change cannot be made (the message says why, for the page); nothing changed."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ChangeOp:
    """One checked op of the closed set (the fields its `op` uses are set)."""

    op: str
    beat: str | None = None
    layer: Layer | None = None
    ref: str | None = None
    query: str = ""
    depicts: Depicts | None = None
    from_s: float = 0.0
    to_s: float = 0.0
    db: float = 0.0
    offset_db: float = 0.0
    caption: str = ""

    @property
    def picture(self) -> bool:
        return self.op in PICTURE_OPS

    def label(self) -> str:
        match self.op:
            case "replace_visual":
                return f"replace {self.beat}'s visual with a re-sourced picture"
            case "drop_layer":
                return f"drop {self.beat}'s {self.layer}"
            case "show_reference":
                return f"show the owner's reference {self.ref} ({self.caption}) on {self.beat}"
            case "new_image":
                return f"a new picture on {self.beat}: {self.query!r} ({self.depicts})"
            case "music":
                return f"music {self.db:+g} dB from {self.from_s:g} s to {self.to_s:g} s"
            case _:
                return f"music level {self.offset_db:+g} dB for the whole reel"


@dataclass(frozen=True)
class ChangePlan:
    """What `plan_change` made of the operator's words: the checked ops and the model's
    one-line summary, or the reason the whole change is refused. `index` is the
    change's row on `job.json.changes`."""

    text: str
    index: int
    ops: tuple[ChangeOp, ...] = ()
    summary: str = ""
    refused: str = ""

    @property
    def picture(self) -> bool:
        return any(o.picture for o in self.ops)


# --- what the model is told ---------------------------------------------------------------

SYSTEM = """You are the editor of a delivered YouTube Short (a 9:16 explainer). The owner \
has watched it and asks for a change in plain words. You turn the request into changes \
from a CLOSED list; code applies them. You never write captions, facts, coordinates, asset \
ids or any content beyond an image search query.

The changes you may use (JSON objects):
- {"op":"replace_visual","beat":"b03"}: the beat's picture goes; a plain picture is \
re-sourced for its line (stock clip or generated image; a named person only their own \
photo). Not on the finale beat.
- {"op":"drop_layer","beat":"b03","layer":"<layer>"}: remove one layer the beat has; \
layer is one of text_pops, bubbles, stickers, highlight, event, counter, route.
- {"op":"show_reference","beat":"b03","ref":"ref1"}: the beat shows one of the owner's \
reference images listed below (only those ids).
- {"op":"new_image","beat":"b03","query":"<image search words>","depicts":"scene"}: a new \
picture for the beat, searched with the query; depicts is "named_entity" for a real named \
person, place or organisation, else "scene". Not on the finale beat.
- {"op":"music","from_s":12,"to_s":18,"db":-4}: the music bed louder (+) or quieter (-) \
between two times of the reel, in dB (levels are clipped to +4/-8 around the bed).
- {"op":"music_level","offset_db":-2}: the music level of the whole reel, as an offset in \
dB from the style's starting level.

Times the owner gives like "0:12" or "12s" are seconds in the finished reel - the same \
timeline as the beat times and word times below. Use the beat ids exactly as listed. \
Prefer the smallest change that does what the owner asked.

Reply with JSON only, no prose around it:
{"ops":[...],"summary":"<one sentence: what you will change>"}
or, when the request cannot be done with these changes:
{"refuse":"<one sentence: why>"}"""


def _load_plan(job: Job) -> PicturePlan:
    return PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))


def _load_story(job: Job) -> SoundStory | None:
    path = job.work_dir / "sound.json"
    if not path.is_file():
        return None
    return SoundStory.model_validate_json(path.read_text(encoding="utf-8"))


def _refs(job: Job) -> list[ReferenceRecord]:
    path = job.input_dir / "refs.json"
    return _REFS.validate_json(path.read_text(encoding="utf-8")) if path.is_file() else []


def _spans(job: Job, plan: PicturePlan) -> list[Any]:
    return presenter.load_cut_list(job) or presenter.cut_list(plan)


def _words_on_reel(job: Job, plan: PicturePlan) -> list[tuple[str, float]]:
    """The kept words at their seconds in the finished reel."""
    asr = job.work_dir / "asr.json"
    if not asr.is_file():
        return []
    transcript = Transcript.model_validate_json(asr.read_text(encoding="utf-8"))
    return [(w.text, w.start) for _, w in presenter.words_on_cut(_spans(job, plan),
                                                                 transcript.words)]  # fmt: skip


def runtime_of(job: Job, plan: PicturePlan) -> float:
    return presenter.total_duration(_spans(job, plan))


def _shows(b: Beat) -> str:
    if b.map is not None:
        where = b.map.region or (f"bbox {list(b.map.bbox)}" if b.map.bbox else "")
        text = f"a map of {where}; markers {', '.join(m.name for m in b.map.markers)}"
        if b.map.route:
            text += f"; route {' -> '.join(b.map.route)}"
        return text
    parts = [f"depicts {depicts_of(b)}"]
    if b.query:
        parts.append(f"query {b.query!r}")
    if b.set_piece_title:
        parts.append(f"title {b.set_piece_title!r}")
    parts.append(f"asset {b.asset_id or 'none'}")
    return "; ".join(parts)


def prompt(job: Job, text: str, plan: PicturePlan, story: SoundStory | None,
           refs: Sequence[ReferenceRecord]) -> str:  # fmt: skip
    brief_path = job.input_dir / "brief.md"
    brief = brief_path.read_text(encoding="utf-8").strip() if brief_path.is_file() else ""
    words = _words_on_reel(job, plan)
    beats: list[str] = []
    for b in plan.beats:
        said = " ".join(w for w, t in words if b.start - EPS <= t < b.end)
        layers = ", ".join(repairs.layers_of(b)) or "none"
        finale = " (the finale)" if b.id == plan.finale.beat_id else ""
        beats.append(f"- {b.id}{finale} {b.start:.1f}-{b.end:.1f} s, {b.kind}: shows {_shows(b)}; "
                     f"layers {layers}; says \"{said}\"")  # fmt: skip
    parts = [
        "## The brief", brief or "(none)",
        f"## The reel: {runtime_of(job, plan):.1f} s",
        "## The transcript (word@seconds in the reel)",
        " ".join(f"{w}@{t:.1f}" for w, t in words) or "(none)",
        "## The beats", "\n".join(beats),
        "## The owner's reference images",
        "\n".join(f"- {r.id}: {r.caption}" for r in refs) or "(none)",
    ]  # fmt: skip
    if story is not None:
        curve = ", ".join(f"{p.t:g} s: {p.level:+g} dB" for p in story.mood_curve) or "(flat)"
        parts += ["## The music's mood curve (dB around the bed level)", curve]
    parts += ["## The owner asks", text.strip(),
              'Reply with JSON only: {"ops":[...],"summary":"..."} or {"refuse":"..."}']
    return "\n\n".join(parts)


# --- the reply, checked ---------------------------------------------------------------------


def _seconds(value: object, name: str) -> float:
    if isinstance(value, str):
        m = _CLOCK_TIME.match(value)
        if m is not None:
            return int(m.group(1)) * 60 + float(m.group(2))
        try:
            return float(value.strip().removesuffix("s"))
        except ValueError:
            raise ValueError(f"{name} {value!r} is not a time in seconds") from None
    return _number(value, name)


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} {value!r} is not a number")
    return float(value)


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{row.get('op')} needs {key}")
    return value.strip()


def check_ops(
    rows: Sequence[object], plan: PicturePlan, refs: Sequence[ReferenceRecord], *,
    runtime_s: float, story: SoundStory | None, scale: level.LevelScale,
) -> list[ChangeOp]:  # fmt: skip
    """Every op checked against the real plan; the first bad one raises `ValueError`
    with the reason (the whole change is refused)."""
    if not rows:
        raise ValueError("the editor found nothing it could change")
    beats = {b.id: b for b in plan.beats}
    captions = {r.id: r.caption for r in refs}
    out: list[ChangeOp] = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError(f"{raw!r} is not a change")
        row = cast(dict[str, object], raw)
        op = row.get("op")
        if op not in OPS:
            raise ValueError(f"{op!r} is not a change the editor may make")
        beat: Beat | None = None
        if op in PICTURE_OPS:
            beat_id = _text(row, "beat")
            beat = beats.get(beat_id)
            if beat is None:
                raise ValueError(f"there is no beat {beat_id!r} in this reel")
            if op in ("replace_visual", "new_image") and beat.id == plan.finale.beat_id:
                raise ValueError(f"{beat.id} is the finale; its picture is not replaced")
        match op:
            case "replace_visual":
                assert beat is not None
                out.append(ChangeOp(op, beat=beat.id))
            case "drop_layer":
                assert beat is not None
                layer = _text(row, "layer")
                if layer not in LAYERS:
                    raise ValueError(f"{layer!r} is not a layer the editor can drop")
                if layer not in repairs.layers_of(beat):
                    raise ValueError(f"{beat.id} has no {layer} to drop")
                out.append(ChangeOp(op, beat=beat.id, layer=layer))
            case "show_reference":
                assert beat is not None
                ref = _text(row, "ref")
                if ref not in captions:
                    raise ValueError(f"{ref!r} is not one of the owner's references")
                out.append(ChangeOp(op, beat=beat.id, ref=ref, caption=captions[ref]))
            case "new_image":
                assert beat is not None
                depicts = _text(row, "depicts")
                if depicts not in DEPICTS:
                    raise ValueError(f"depicts {depicts!r} is not one of {', '.join(DEPICTS)}")
                out.append(ChangeOp(op, beat=beat.id, query=_text(row, "query"),
                                    depicts=cast(Depicts, depicts)))  # fmt: skip
            case "music":
                if story is None:
                    raise ValueError("this reel has no sound story whose music could change")
                start = _seconds(row.get("from_s"), "from_s")
                end = min(_seconds(row.get("to_s"), "to_s"), runtime_s)
                db = _number(row.get("db"), "db")
                if not 0 <= start < end:
                    raise ValueError(f"{start:g}-{end:g} s is not a range inside the reel "
                                     f"(0-{runtime_s:g} s)")  # fmt: skip
                if db == 0:
                    raise ValueError("a music change of 0 dB changes nothing")
                out.append(ChangeOp(op, from_s=round(start, 3), to_s=round(end, 3), db=db))
            case _:
                offset = _number(row.get("offset_db"), "offset_db")
                if not scale.contains(offset):
                    raise ValueError(f"the music level must be from {scale.min_db:g} to "
                                     f"{scale.max_db:g} dB")  # fmt: skip
                out.append(ChangeOp(op, offset_db=offset))
    return out


def parse_reply(reply: str) -> tuple[list[object], str, str]:
    """(ops, summary, refusal) from the model's reply; ValueError when it is not the
    JSON asked for."""
    match = _JSON.search(reply)
    if match is None:
        raise ValueError("the editor's reply holds no JSON object")
    try:
        data: object = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"the editor's reply is not JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ValueError("the editor's reply is not a JSON object")
    body = cast(dict[str, object], data)
    refuse = body.get("refuse")
    if isinstance(refuse, str) and refuse.strip():
        return [], "", refuse.strip()
    ops = body.get("ops")
    if not isinstance(ops, list):
        raise ValueError("the editor's reply has no list of ops")
    summary = body.get("summary")
    return cast(list[object], ops), summary.strip() if isinstance(summary, str) else "", ""


def plan_change(
    job: Job, text: str, planner: Planner, *, clock: Clock = _utc_now,
    scale: level.LevelScale | None = None,
) -> ChangePlan:  # fmt: skip
    """Record the request (`running`), ask the model once, check every op. A refusal is
    recorded on the change row and returned in `refused`; nothing else is touched."""
    text = text.strip()
    index = jobs.add_change(job, ChangeRequest(at=clock(), text=text, status="running"),
                            now=clock)  # fmt: skip

    def refused(reason: str) -> ChangePlan:
        jobs.update_change(job, index, status="refused", summary=reason, now=clock)
        return ChangePlan(text=text, index=index, refused=reason)

    if job.record.swept_at is not None:
        return refused(SWEPT_SENTENCE)
    try:
        plan = _load_plan(job)
    except (OSError, ValueError):
        return refused("this reel has no plan on disk to change")
    story = _load_story(job)
    refs = _refs(job)
    try:
        reply = planner.bind(job).ask(
            f"change_{clock().strftime('%H%M%S%f')}", SYSTEM,
            prompt(job, text, plan, story, refs), step="change",
        )  # fmt: skip
    except Exception as exc:  # noqa: BLE001 - no model, quota, outage: the change is refused
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        return refused(UNAVAILABLE + first)
    try:
        rows, summary, refusal = parse_reply(reply)
        if refusal:
            return refused(f"the editor cannot do this: {refusal}")
        ops = check_ops(rows, plan, refs, runtime_s=runtime_of(job, plan), story=story,
                        scale=scale or level.load_scale())  # fmt: skip
    except ValueError as exc:
        return refused(f"refused: {exc}")
    summary = summary or "; ".join(o.label() for o in ops)
    return ChangePlan(text=text, index=index, ops=tuple(ops), summary=summary)


# --- the ops, applied -----------------------------------------------------------------------


def patch_picture_op(plan: PicturePlan, op: ChangeOp) -> PicturePlan:
    """One picture op on the plan (pure)."""
    assert op.beat is not None
    match op.op:
        case "replace_visual":
            return repairs.replace_visual(plan, op.beat)
        case "drop_layer":
            assert op.layer is not None
            return repairs.drop_layer(plan, op.beat, op.layer)
        case "show_reference":
            assert op.ref is not None
            if repairs.beat_of(plan, op.beat).kind not in ("photo", "card"):
                plan = repairs.replace_visual(plan, op.beat)
            return repairs.place_reference(plan, op.beat, op.ref)
        case "new_image":
            replaced = repairs.replace_visual(plan, op.beat)
            subject = "entity" if op.depicts == "named_entity" else None
            beats = [
                b.model_copy(update={
                    "query": op.query, "query_fallback": "", "depicts": op.depicts,
                    "subject_kind": subject or ("concept" if b.subject_kind == "entity"
                                                else b.subject_kind),
                    "asset_id": None, "source_intent": "search",
                }) if b.id == op.beat else b
                for b in replaced.beats
            ]  # fmt: skip
            return replaced.model_copy(update={"beats": beats})
        case _:
            raise RepairError(f"{op.op} is not a picture change")


def shift_curve(
    points: Sequence[MoodPoint], *, from_s: float, to_s: float, db: float,
    nums: styles.Sound, runtime_s: float,
) -> list[MoodPoint]:  # fmt: skip
    """The mood curve moved by `db` from `from_s` to `to_s` (reel seconds): a point at
    each edge (the curve's level there), every point inside shifted, the level before
    and after held by a point `ramp_min_s` outside each edge (points in those ramps go),
    every level clipped to `drop_min_db`..`swell_max_db`."""
    old = sorted(points, key=lambda p: p.t)

    def at(t: float) -> float:
        if not old:
            return 0.0
        if t <= old[0].t:
            return old[0].level
        for a, b in zip(old, old[1:], strict=False):
            if t < b.t:
                span = b.t - a.t
                return b.level if span <= 0 else a.level + (b.level - a.level) * (t - a.t) / span
        return old[-1].level

    def clip(level_db: float) -> float:
        return round(min(max(level_db, nums.drop_min_db), nums.swell_max_db), 3)

    start, end = max(0.0, from_s), min(runtime_s, to_s)
    before, after = start - nums.ramp_min_s, end + nums.ramp_min_s
    out = [p for p in old if p.t < before - EPS or p.t > after + EPS]
    inside = [p for p in old if start - EPS <= p.t <= end + EPS]
    for edge in (start, end):
        if not any(abs(p.t - edge) <= EPS for p in inside):
            inside.append(MoodPoint(t=round(edge, 3), level=at(edge)))
    out += [MoodPoint(t=p.t, level=clip(p.level + db)) for p in inside]
    if before > EPS:
        out.append(MoodPoint(t=round(before, 3), level=clip(at(before))))
    if after < runtime_s - EPS:
        out.append(MoodPoint(t=round(after, 3), level=clip(at(after))))
    return sorted(out, key=lambda p: p.t)


def _backup(job: Job) -> Path | None:
    """The short as it is now, copied beside the previous version (kept by `_keep`)."""
    short = job.out_dir / "short.mp4"
    if not short.is_file():
        return None
    folder = job.out_dir / PREVIOUS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    pending = folder / PENDING_NAME
    shutil.copyfile(short, pending)
    return pending


def _keep(pending: Path | None) -> None:
    """Operator answer 4: ONE previous version, the one just replaced."""
    if pending is not None:
        os.replace(pending, pending.with_name(PREVIOUS_NAME))


def previous_short(job: Job) -> Path | None:
    path = job.out_dir / PREVIOUS_DIR / PREVIOUS_NAME
    return path if path.is_file() else None


def _decide(job: Job, plan: ChangePlan, clock: Clock) -> None:
    for op in plan.ops:
        jobs.decide(job, EditorDecision(
            at=clock(), step="change", beat_id=op.beat,
            problem=" ".join(plan.text.split())[:400], choice=op.label(),
            reason=plan.summary, by="operator",
        ), now=clock)  # fmt: skip


def _write_story(job: Job, story: SoundStory) -> None:
    (job.work_dir / "sound.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")
    validated = pipeline.load_validated(job)
    if validated is not None:
        updated = validated.model_copy(update={"sound": story})
        (job.work_dir / "plan.validated.json").write_text(
            updated.model_dump_json(indent=2), encoding="utf-8"
        )


def _new_story(job: Job, story: SoundStory, ops: Sequence[ChangeOp], nums: styles.Sound,
               runtime_s: float) -> SoundStory:  # fmt: skip
    curve = list(story.mood_curve)
    for op in ops:
        curve = shift_curve(curve, from_s=op.from_s, to_s=op.to_s, db=op.db, nums=nums,
                            runtime_s=runtime_s)  # fmt: skip
    return story.model_copy(update={"mood_curve": curve})


def apply_change(
    job: Job, plan: ChangePlan, *, specs: Mapping[str, StyleSpec] | None = None,
    library: sound.Library | None = None, clock: Clock = _utc_now,
) -> str:  # fmt: skip
    """Apply a checked change (module note) and return its summary. Raises
    `ChangeRefused` (recorded on the change row, nothing changed) when it cannot."""
    if plan.refused:
        raise ChangeRefused(plan.refused)

    def refuse(reason: str) -> ChangeRefused:
        jobs.update_change(job, plan.index, status="refused", summary=reason, now=clock)
        return ChangeRefused(reason)

    job = jobs.load(job.path)
    if job.status not in jobs.VERDICTS:
        raise refuse("this job has no finished short to change right now")
    specs = specs if specs is not None else render.loaded_styles()
    spec = pipeline.style_of(job, specs)
    picture = _load_plan(job)
    runtime = runtime_of(job, picture)
    story = _load_story(job)
    music = [o for o in plan.ops if o.op == "music"]
    new_story = None
    if music:
        assert story is not None  # check_ops refused a music op without a story
        new_story = _new_story(job, story, music, spec.sound, runtime)
    offset = next((o.offset_db for o in plan.ops if o.op == "music_level"), None)
    if plan.picture:
        return _apply_picture(job, plan, picture, new_story, offset, specs, clock, refuse)
    return _apply_sound(job, plan, new_story, offset, spec, runtime, picture, library, clock,
                        refuse)  # fmt: skip


def _apply_picture(
    job: Job, plan: ChangePlan, picture: PicturePlan, new_story: SoundStory | None,
    offset: float | None, specs: Mapping[str, StyleSpec], clock: Clock,
    refuse: Callable[[str], ChangeRefused],
) -> str:  # fmt: skip
    validated: ValidatedPlan | None = pipeline.load_validated(job)
    if validated is None:
        raise refuse("this reel has no validated plan on disk to change")
    patched = picture
    try:
        for op in plan.ops:
            if op.picture:
                patched = patch_picture_op(patched, op)
    except RepairError as exc:
        raise refuse(f"refused: {exc}") from None
    result = pipeline.patch_picture(job, validated, patched, specs, step="change", clock=clock,
                                    force=False)  # fmt: skip
    if isinstance(result, grammar.Violations):
        raise refuse("refused: the changed plan breaks a rule that is never bent: "
                     + "; ".join(result.lines()))  # fmt: skip
    if new_story is not None:
        _write_story(job, new_story)
    if offset is not None:
        started = job.record.music_level
        jobs.amend(job, music_level=jobs.MusicLevel(
            offset_db=offset, measure=level.MEASURE, set_by="slider", set_at=clock(),
            from_job=started.from_job if started is not None else None,
            start_db=started.start_db if started is not None else 0.0,
        ))  # fmt: skip
    replaced = list(jobs.load(job.path).record.replaced)
    for op in plan.ops:
        if op.op in ("replace_visual", "new_image") and op.beat not in replaced:
            assert op.beat is not None
            replaced.append(op.beat)
    jobs.amend(job, replaced=replaced)
    _decide(job, plan, clock)
    _keep(_backup(job))
    jobs.rework(job, "sourcing", f"the operator's change: {plan.summary}", now=clock)
    summary = (
        f"{plan.summary} (re-rendering from sourcing; the old reel is kept as the previous "
        "version)"
    )
    jobs.update_change(job, plan.index, status="running", summary=summary, now=clock)
    return summary


def _apply_sound(
    job: Job, plan: ChangePlan, new_story: SoundStory | None, offset: float | None,
    spec: StyleSpec, runtime: float, picture: PicturePlan, library: sound.Library | None,
    clock: Clock, refuse: Callable[[str], ChangeRefused],
) -> str:  # fmt: skip
    why = level.refusal(job)
    if why:
        raise refuse(why)
    pending = _backup(job)
    try:
        if new_story is not None:
            lib = library if library is not None else sound.load_catalogue()
            started = job.record.music_level
            now_db = started.offset_db if started is not None else 0.0
            story = new_story
            level.deliver(job, lambda stems, scratch: sound.recurve(
                stems, scratch, library=lib, story=story, plan=picture, nums=spec.sound,
                runtime_s=runtime, offset_db=now_db,
            ))  # fmt: skip
            _write_story(job, new_story)
            jobs.note(job, "change: music stems rebuilt with the new mood curve "
                      f"({', '.join(o.label() for o in plan.ops if o.op == 'music')})",
                      now=clock)  # fmt: skip
        if offset is not None:
            level.remix(job, offset_db=offset, now=clock)
    except level.LevelError as exc:
        if pending is not None:
            pending.unlink(missing_ok=True)
        raise refuse(f"refused: {exc}") from None
    _keep(pending)
    _decide(job, plan, clock)
    jobs.update_change(job, plan.index, status="applied", summary=plan.summary, now=clock)
    return plan.summary
