"""The editor brain (097; work/editor-design.md "Editor"): a small problem never fails
the job. Where a step gets stuck, code builds a `Snag` - the step, the beat (or the
plan), what failed, and a CLOSED list of real `Option`s (swap, simplify, drop one
element; `repairs`) - and the `Editor` asks the model which option to take, one prompt
per round for every snag of that round. The model only picks listed option ids and
says why; it never writes content. Any failure (no model behind the planner - the fake
- a transport error, a reply that is not the JSON asked for, an unknown id) takes the
snag's `fallback_id`, the most targeted fix code can infer from the problem text, with
`by="fallback"`. Every decision is recorded on the job (`jobs.decide`).

Options for a beat (`beat_options`): `keep` (only when the problem is soft), one drop
per layer the beat carries, `plain_cut` when it enters on anything else, the map ones
on a map beat (`frame_markers` only when every marker and route point resolves in the
geocoder the renderer uses; `drop_route` when it has a route), and `replace_visual`
last (never on the finale). `fallback_for` picks, in order: a layer word in the problem
-> drop that layer; an `enter` problem -> `plain_cut`; a map problem -> `frame_markers`
when offered, else `replace_visual`; hard -> `replace_visual`; soft -> `keep`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError

from shortsmith import geo, jobs
from shortsmith.assets.generate import depicts_of
from shortsmith.contracts import Beat, EditorDecision, PicturePlan, Transcript
from shortsmith.editor import repairs
from shortsmith.editor.repairs import LAYERS, Layer, RepairError
from shortsmith.jobs import Clock, Job
from shortsmith.planner import Planner

__all__ = [
    "DELIVER",
    "KEEP",
    "REPLACE",
    "Choice",
    "Editor",
    "Option",
    "RepairError",
    "Snag",
    "beat_options",
    "fallback_for",
    "reference_options",
    "repairs",
]

KEEP = "keep"
REPLACE = "replace_visual"
DELIVER = "deliver_with_note"
Patch = Callable[[PicturePlan], PicturePlan]

LAYER_LABELS: Mapping[Layer, str] = {
    "text_pops": "drop this beat's text pops",
    "bubbles": "drop this beat's speech/thought bubbles",
    "stickers": "drop this beat's stickers",
    "highlight": "drop this beat's article highlight",
    "event": "drop this beat's landed event (stamp, ring or lower-third)",
    "counter": "drop this beat's counter",
    "route": "drop the map's route line and moving object (keep the markers)",
}
# The words in a problem that name a layer, in the order they are tried.
LAYER_WORDS: tuple[tuple[str, Layer], ...] = (
    ("route point", "route"),
    ("route_arrow", "route"),
    ("object_path", "route"),
    ("route", "route"),
    ("text pop", "text_pops"),
    ("text_pop", "text_pops"),
    ("bubble", "bubbles"),
    ("sticker", "stickers"),
    ("highlight", "highlight"),
    ("counter", "counter"),
    ("stamp", "event"),
    ("lower_third", "event"),
    ("lower-third", "event"),
    ("ring", "event"),
)
MAP_WORDS = ("map", "gazetteer", "marker", "region", "bbox", "geocod")
_WORD = re.compile(r"[a-z0-9]+")
STOP_WORDS = frozenset(
    {"with", "from", "that", "this", "their", "photo", "image", "picture", "portrait"}
)


@dataclass(frozen=True)
class Option:
    """One real way out of a snag. `apply` patches the picture plan (None: nothing to
    patch - `keep`, `deliver_with_note`); `resume_step` is where the job runs on from;
    `replaces` names the beat the replacement ladder re-sources (096)."""

    id: str
    label: str
    apply: Patch | None = None
    resume_step: str = "sourcing"
    replaces: str | None = None


@dataclass(frozen=True)
class Snag:
    """Where a step got stuck: the step, the beat (None for the plan), the problem, whether
    it is a hard truth (no `keep`), the options and the code's fallback option id.
    `lines` are the grammar lines the snag stands for (planning), for the kept set."""

    id: str
    step: str
    beat_id: str | None
    problem: str
    hard: bool
    options: tuple[Option, ...]
    fallback_id: str
    lines: tuple[str, ...] = ()

    def option(self, option_id: str) -> Option | None:
        return next((o for o in self.options if o.id == option_id), None)

    @property
    def fallback(self) -> Option:
        found = self.option(self.fallback_id)
        assert found is not None, f"{self.id}: fallback {self.fallback_id!r} is not an option"
        return found


@dataclass(frozen=True)
class Choice:
    snag: Snag
    option: Option
    decision: EditorDecision


# --- the options -----------------------------------------------------------------------------


def _replace(beat_id: str) -> Option:
    return Option(
        REPLACE,
        "replace this beat's visual with a plain re-sourced picture (stock clip or generated "
        "image; a named person only their own or an already-shown real photo)",
        lambda p: repairs.replace_visual(p, beat_id),
        replaces=beat_id,
    )


def beat_options(
    plan: PicturePlan,
    beat_id: str,
    *,
    hard: bool,
    geocoder: geo.Geocoder | None = None,
    keep: bool = True,
) -> list[Option]:
    """The real options for one beat (see the module docstring); `keep` False leaves the
    keep option out even when the problem is soft (a render failure cannot be kept)."""
    beat = repairs.beat_of(plan, beat_id)
    options: list[Option] = []
    if keep and not hard:
        options.append(Option(KEEP, "keep the beat as planned (the small break is noted)"))
    for layer in repairs.layers_of(beat):
        if layer == "route":
            continue  # the map's own option below
        options.append(
            Option(
                f"drop_{layer}",
                LAYER_LABELS[layer],
                lambda p, layer=layer: repairs.drop_layer(p, beat_id, layer),
            )  # fmt: skip
        )
    if beat.enter != "cut":
        options.append(
            Option(
                "plain_cut",
                f"enter on a plain cut instead of {beat.enter!r}",
                lambda p: repairs.plain_cut(p, beat_id),
            )  # fmt: skip
        )
    if beat.kind == "map" and beat.map is not None:
        coder = geocoder or geo.GazetteerGeocoder()
        box = repairs.marker_bbox(beat, coder)
        if box is not None:
            names = ", ".join(m.name for m in beat.map.markers)
            options.append(
                Option(
                    "frame_markers",
                    f"frame the map on its markers ({names}) at their real coordinates "
                    f"(bbox {list(box)}) instead of the region {beat.map.region!r}",
                    lambda p: repairs.frame_markers(p, beat_id, coder),
                )  # fmt: skip
            )
        if "route" in repairs.layers_of(beat):
            options.append(Option("drop_route", LAYER_LABELS["route"],
                                  lambda p: repairs.drop_route(p, beat_id)))  # fmt: skip
    if beat.kind != "finale" and beat.id != plan.finale.beat_id:
        options.append(_replace(beat_id))
    return options


def fallback_for(problem: str, options: Sequence[Option], *, hard: bool) -> str:
    """The most targeted fix code can infer from `problem` among `options` (module doc)."""
    ids = {o.id for o in options}
    text = problem.lower()

    def says(word: str) -> bool:
        return re.search(rf"\b{re.escape(word)}", text) is not None

    for word, layer in LAYER_WORDS:
        if f"drop_{layer}" in ids and re.search(rf"\b{re.escape(word)}\b", text):
            return f"drop_{layer}"
    if says("enter") and "plain_cut" in ids:
        return "plain_cut"
    if any(says(w) for w in MAP_WORDS):
        if "frame_markers" in ids:
            return "frame_markers"
        if REPLACE in ids:
            return REPLACE
    if not hard and KEEP in ids:
        return KEEP
    if REPLACE in ids:
        return REPLACE
    return options[-1].id if options else KEEP


def _significant(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) >= 4 and w not in STOP_WORDS}


def said_in(beat: Beat, transcript: Transcript) -> str:
    """The transcript words whose start falls inside the beat (the plan's timeline)."""
    return " ".join(w.text for w in transcript.words if beat.start - 1e-6 <= w.start < beat.end)


def reference_options(
    plan: PicturePlan, ref_id: str, caption: str, transcript: Transcript
) -> list[Option]:
    """`place_reference` on the safe beats only (design): a photo or card beat whose
    words (or query) match the reference caption, or a photo beat that does not depict a
    named entity. Caption matches first."""
    wanted = _significant(caption)
    matched: list[Beat] = []
    scenes: list[Beat] = []
    for b in plan.beats:
        if b.kind not in ("photo", "card"):
            continue
        if wanted & _significant(f"{said_in(b, transcript)} {b.query}"):
            matched.append(b)
        elif b.kind == "photo" and depicts_of(b) != "named_entity":
            scenes.append(b)
    return [
        Option(
            f"place_reference:{b.id}",
            f"show the owner's reference {ref_id!r} ({caption}) on {b.id}",
            lambda p, bid=b.id: repairs.place_reference(p, bid, ref_id),
        )  # fmt: skip
        for b in [*matched, *scenes]
    ]


# --- the editor ------------------------------------------------------------------------------

SYSTEM = """You are the editor of a YouTube Short (a 9:16 explainer at the level of the top \
facts channels). A step of the automatic edit got stuck. For every snag below, code has \
already built a closed list of real options; you pick exactly one of them.

Rules:
- You may only pick one of the option ids listed under that snag. Never invent an id, a \
fact, a coordinate, an asset or any new text.
- Prefer the smallest change that keeps the story and the brief: drop or simplify one \
element before replacing a whole picture; keep a small style break when the option exists \
and the beat still reads well.
- Say why like an editor, in one or two sentences: tie it to the brief, to what is said on \
this beat and the beats around it, and to what failed.

Reply with JSON only, no prose around it:
{"choices":[{"snag":"<snag id>","option":"<option id>","reason":"<why>"}]}"""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _beat_line(b: Beat, transcript: Transcript | None) -> str:
    shows = b.query or b.set_piece_title or ""
    if b.map is not None:
        where = b.map.region or (f"bbox {list(b.map.bbox)}" if b.map.bbox else "")
        shows = f"map {where}; markers {', '.join(m.name for m in b.map.markers)}"
        if b.map.route:
            shows += f"; route {' -> '.join(b.map.route)}"
    layers = ", ".join(repairs.layers_of(b)) or "none"
    said = f' says "{said_in(b, transcript)}"' if transcript is not None else ""
    return (
        f"- {b.id} {b.start:g}-{b.end:g} s {b.kind} ({b.mode}), shows {shows!r}, "
        f"layers {layers}{said}"
    )


def _around(plan: PicturePlan | None, beat_id: str | None) -> str:
    if plan is None or beat_id is None:
        return ""
    ids = [b.id for b in plan.beats]
    if beat_id not in ids:
        return ""
    i = ids.index(beat_id)
    return ", ".join(ids[max(0, i - 1) : i + 2])


@dataclass
class Editor:
    """`choose`/`pick` one option per snag, one `planner.ask` per round (the job's planner,
    so the fake answers every snag with its fallback). `geocoder` is the renderer's
    (`frame_markers` is offered only on names it resolves); None is the bundled
    gazetteer."""

    planner: Planner
    geocoder: geo.Geocoder | None = None
    clock: Clock = _utc_now
    asked: list[str] = field(default_factory=list[str])

    def geocoder_for(self, job: Job) -> geo.Geocoder:
        return (self.geocoder or geo.GazetteerGeocoder()).for_job(job.path)

    def choose(
        self, job: Job, snags: Sequence[Snag], *, step: str,
        plan: PicturePlan | None = None, transcript: Transcript | None = None,
    ) -> list[EditorDecision]:  # fmt: skip
        return [c.decision for c in self.pick(job, snags, step=step, plan=plan,
                                              transcript=transcript)]  # fmt: skip

    def pick(
        self, job: Job, snags: Sequence[Snag], *, step: str,
        plan: PicturePlan | None = None, transcript: Transcript | None = None,
    ) -> list[Choice]:  # fmt: skip
        """One round: every snag with more than one option goes into ONE prompt; the
        reply's choices are honoured when they name a listed option, every other snag
        takes its fallback. Each decision is recorded with `jobs.decide`."""
        asked = [s for s in snags if len(s.options) > 1]
        replies: dict[str, tuple[str, str]] = {}
        failure = ""
        if asked:
            try:
                text = self.prompt(job, asked, plan=plan, transcript=transcript)
                name = f"{step}_{len(self.asked) + 1}_{_stamp(self.clock())}"
                self.asked.append(name)
                reply = self.planner.bind(job).ask(name, SYSTEM, text, step=step)
                replies = parse_choices(reply)
            except Exception as exc:  # noqa: BLE001 - any failure is the code's fallback
                failure = f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"
        out: list[Choice] = []
        for snag in snags:
            picked = replies.get(snag.id)
            option = snag.option(picked[0]) if picked is not None else None
            if picked is not None and option is not None:
                by, reason = "editor", picked[1].strip() or "(no reason given)"
            elif len(snag.options) == 1:
                option = snag.options[0]
                by, reason = "fallback", "the only option code could build"
            else:
                option = snag.fallback
                if picked is not None:
                    why = f"the editor named {picked[0]!r}, which is not an option"
                elif failure:
                    why = f"no editor answer ({failure})"
                else:
                    why = "the editor did not answer this snag"
                by, reason = "fallback", f"{why}; code's most targeted fix"
            decision = EditorDecision(
                at=self.clock(), step=snag.step, beat_id=snag.beat_id,
                problem=_one_line(snag.problem), choice=option.label, reason=reason, by=by,
            )  # fmt: skip
            jobs.decide(job, decision, now=self.clock)
            out.append(Choice(snag, option, decision))
        return out

    def prompt(
        self, job: Job, snags: Sequence[Snag], *, plan: PicturePlan | None,
        transcript: Transcript | None,
    ) -> str:  # fmt: skip
        brief_path = job.input_dir / "brief.md"
        brief = brief_path.read_text(encoding="utf-8") if brief_path.is_file() else ""
        parts = ["## The brief", brief.strip() or "(none)"]
        if transcript is not None:
            words = " ".join(f"{w.text}@{w.start:.1f}" for w in transcript.words)
            parts += ["## The transcript (word@seconds on the recording)", words]
        if plan is not None:
            parts += ["## The beats", "\n".join(_beat_line(b, None) for b in plan.beats)]
        parts.append("## The snags")
        for s in snags:
            where = s.beat_id or "the plan"
            around = _around(plan, s.beat_id)
            head = f"### {s.id} ({s.step}, {where}{'; hard truth' if s.hard else ''})"
            lines = [head, f"What failed: {s.problem}"]
            if around:
                lines.append(f"Beats around it: {around}")
            lines.append("Options:")
            lines += [f"- `{o.id}`: {o.label}" for o in s.options]
            parts.append("\n".join(lines))
        parts.append('Reply with JSON only: {"choices":[{"snag":...,"option":...,"reason":...}]}')
        return "\n\n".join(parts)


def _stamp(at: datetime) -> str:
    return at.strftime("%H%M%S%f")


def _one_line(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first[:400]


_JSON = re.compile(r"\{.*\}", re.DOTALL)


class _Row(BaseModel):
    snag: str
    option: str = ""
    reason: str = ""


class _Reply(BaseModel):
    choices: list[_Row]


def parse_choices(reply: str) -> dict[str, tuple[str, str]]:
    """`{"choices":[{"snag","option","reason"}]}` from the reply (a fenced or wrapped
    object is found); snag id -> (option id, reason). Anything else raises ValueError."""
    match = _JSON.search(reply)
    if match is None:
        raise ValueError("the editor's reply holds no JSON object")
    try:
        parsed = _Reply.model_validate(json.loads(match.group(0)))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"the editor's reply is not the choices JSON: {exc}") from None
    return {row.snag: (row.option, row.reason) for row in parsed.choices}


def options_of(snag: Snag) -> list[str]:
    return [o.id for o in snag.options]


def make_snag(
    snag_id: str, step: str, beat_id: str | None, problem: str, *, hard: bool,
    options: Sequence[Option], lines: Sequence[str] = (),
) -> Snag:  # fmt: skip
    """A snag with its fallback inferred from the problem text (`fallback_for`)."""
    return Snag(
        id=snag_id, step=step, beat_id=beat_id, problem=problem, hard=hard,
        options=tuple(options), fallback_id=fallback_for(problem, options, hard=hard),
        lines=tuple(lines),
    )  # fmt: skip


LAYER_IDS = tuple(f"drop_{layer}" for layer in LAYERS)
