"""Style specs: loader, validation and the free-text resolver (decisions 1.1, 1.2, 1.4).

A spec is `styles/<name>.md`: YAML front matter followed by the five prose sections
(`## Beat grammar`, `## B-roll`, `## Captions`, `## Sound`, `## Finale`). The front
matter carries the seven key groups (`aliases`, `beats`, `presenter`, `broll`,
`captions`, `sound`, `finale`) plus `status`, `requires_components`, `budget`, `pip`
and `palette`; every number a later ticket reads (the grammar validator, the pager,
the renderer, the sound director, the gate) comes from here, never from code. The
renderer and QA read only the numbers; the planner reads numbers and prose.

`load_all(registry)` validates every spec at startup and fails with the spec name
and what is wrong: a missing key group, a stray or mistyped key, a missing prose
section, a PIP circle that would reach into the caption block (6.3), or a shipped
spec that requires a component the renderer registry does not export (9.2). Drafts
may require components still to be built.

`resolve(line, specs)` maps the upload form's style line to one spec (1.1): alias
hits are counted per spec, the highest count wins, zero hits or a tie fall back to
`explainer`. An alias of a draft spec resolves to `explainer` with a visible notice
(1.4). The full line is the style note the planner gets for what the spec leaves
open. No LLM is involved.

YAML note: PyYAML reads a bare `off`, `on`, `yes` or `no` as a boolean, so the
presenter mode `off` is quoted in every spec.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, ValidationError

from shortsmith.contracts import CaptionStyle, Palette, StrictModel, Transition, Transitions

STYLES_DIR = Path(__file__).resolve().parents[2] / "styles"
DEFAULT = "explainer"
KEY_GROUPS: tuple[str, ...] = (
    "aliases",
    "beats",
    "presenter",
    "broll",
    "captions",
    "sound",
    "finale",
)
PROSE_SECTIONS: tuple[str, ...] = ("Beat grammar", "B-roll", "Captions", "Sound", "Finale")

Status = Literal["shipped", "draft"]


class StyleError(ValueError):
    """A spec failed to load; the message names the spec and the problem."""


# --- front matter models (1.2) ---------------------------------------------------------


class Beats(StrictModel):
    """3.1 beat lengths plus the 3.4 hook slot lengths, all in seconds."""

    min_s: float
    max_s: float
    set_piece_max_s: float
    target_mean_s: float
    mean_min_s: float
    mean_max_s: float
    density_gap_max_s: float
    snap_window_s: float
    cold_open_min_s: float
    cold_open_max_s: float
    hook_cards_min_s: float
    hook_cards_max_s: float
    hook_title_max_words: int


class Presenter(StrictModel):
    """3.2 presenter modes and run limits."""

    modes: list[str]
    full_max_fraction: float
    full_never_consecutive: bool
    full_reasons: list[str]
    pip_max_run: int
    off_max_run: int
    hook_modes: list[str]
    finale_mode: str


class Pip(StrictModel):
    """3.3 / 6.3 circle geometry in composition pixels; `top` is for the normal
    diameter, the large-face circle grows upward from the same bottom edge."""

    left: int
    top: int
    diameter: int
    large_face_diameter: int
    large_face_ratio: float
    chin_anchor: float
    ring_px: int
    ring_color: str


class Broll(StrictModel):
    """4.1 / 9.2 kinds and per-kind motion numbers, 9.4 transitions, 4.3 asset counts."""

    kinds: list[str]
    tier2_kinds: list[str]
    motion: dict[str, dict[str, float | int | bool | str]]
    enter_transitions: list[Transition]
    whip_max_per_3_beats: int
    # 030: the 9.4 vocabulary's numbers. Every spec carries all five rows, enabled or
    # not, so the renderer reads one shape; `enter_transitions` is the subset it may use.
    transitions: Transitions
    unique_assets_min_per_60s: int
    unique_assets_max_per_60s: int
    reuse_max: int
    rescued_max_per_60s: int
    card_max_bottom_y: int
    stamp_max_y_fraction: float
    photo_look: str
    illustration_look: str
    # 5.5: the rest of the generated-scene prompt, in the style's own words; the
    # generator builds the sentence, the words are never in code.
    scene_mood: str
    scene_lighting: str


class Captions(CaptionStyle):
    """The 6.2 typography (`CaptionStyle`) plus the 6.1 pager numbers."""

    words_per_page: tuple[int, int]
    prefer: int
    emphasis_max_ratio: float
    gap_break_s: float


class Sound(StrictModel):
    """7.3 bed, envelope and cue numbers; the 7.1 floor hits; the forbidden list; the
    7.2 bed-score line under which the audio search is asked (024)."""

    bed_score_threshold: float
    bed_db_under_voice: float
    bed_accept_db: tuple[float, float]
    speech_band_hz: tuple[int, int]
    speech_band_margin_db: float
    duck_max_db: float
    swell_max_db: float
    drop_min_db: float
    ramp_min_s: float
    fade_in_s: float
    fade_out_s: float
    floor_hits: dict[str, list[str]]
    cues_max_per_60s: int
    cues_per_beat_max: int
    cue_db_min: float
    cue_db_max: float
    forbidden: list[str]


class FinaleSpec(StrictModel):
    kind: str
    mode: str
    min_s: float
    max_s: float
    cta: bool


class Budget(StrictModel):
    """5.5 / 5.6 per-step allowances; the ledger prices them (011)."""

    judge_max_calls: int
    search_max_queries: int
    gen_max_per_short: int


class FrontMatter(StrictModel):
    status: Status
    aliases: list[str] = Field(min_length=1)
    requires_components: list[str]
    beats: Beats
    presenter: Presenter
    pip: Pip
    broll: Broll
    captions: Captions
    sound: Sound
    finale: FinaleSpec
    budget: Budget
    palette: Palette


class StyleSpec(FrontMatter):
    """One loaded spec: the front matter numbers plus the prose sections."""

    name: str
    prose: str
    sections: dict[str, str]

    def numbers(self) -> dict[str, Any]:
        """The front matter as plain data: what the planner prompt embeds (1.2)."""
        return self.model_dump(exclude={"name", "prose", "sections"})

    def caption_style(self) -> CaptionStyle:
        """Only the 6.2 typography fields, as the render spec carries them."""
        return CaptionStyle.model_validate(
            self.captions.model_dump(include=set(CaptionStyle.model_fields))
        )


# --- parsing ---------------------------------------------------------------------------

_FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.DOTALL)
_SECTION = re.compile(r"^## (.+?)\s*$", re.MULTILINE)


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """The YAML mapping between the `---` fences and the markdown body after them."""
    match = _FRONT.match(text)
    if match is None:
        raise StyleError("no YAML front matter between --- fences")
    loaded: object = yaml.safe_load(match.group(1))
    if not isinstance(loaded, dict):
        raise StyleError("front matter is not a mapping")
    front: dict[str, Any] = {str(k): v for k, v in loaded.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return front, match.group(2)


def split_sections(body: str) -> dict[str, str]:
    """`## Heading` sections of the body, in file order, heading -> text."""
    found = list(_SECTION.finditer(body))
    sections: dict[str, str] = {}
    for i, match in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(body)
        sections[match.group(1)] = body[match.end() : end].strip()
    return sections


def parse(text: str, *, name: str) -> StyleSpec:
    """One spec from its file text; `StyleError` names `name` in every message."""
    try:
        front, body = split_front_matter(text)
    except StyleError as exc:
        raise StyleError(f"{name}: {exc}") from None
    for group in KEY_GROUPS:
        if group not in front:
            raise StyleError(f"{name}: missing key group {group!r}")
    try:
        matter = FrontMatter.model_validate(front)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise StyleError(f"{name}: invalid front matter: {problems}") from None
    sections = split_sections(body)
    if list(sections) != list(PROSE_SECTIONS):
        raise StyleError(
            f"{name}: prose sections must be exactly {list(PROSE_SECTIONS)}, "
            f"found {list(sections)}"
        )
    for heading, content in sections.items():
        if not content:
            raise StyleError(f"{name}: prose section {heading!r} is empty")
    return StyleSpec(**matter.model_dump(), name=name, prose=body.strip(), sections=sections)


# --- validation across a spec and the registry ----------------------------------------


def caption_block_top(captions: CaptionStyle) -> float:
    """The y of the caption block's top edge when every line is used (6.3)."""
    return captions.anchor_y - captions.max_lines * captions.size_px * captions.line_height


def check(spec: StyleSpec, registry: Sequence[str]) -> None:
    """The cross-field asserts: 6.3 collision and 9.2 components for shipped specs."""
    block_top = caption_block_top(spec.captions)
    bottom = spec.pip.top + spec.pip.diameter
    if bottom > block_top:
        raise StyleError(
            f"{spec.name}: pip.top + pip.diameter = {bottom} passes the caption block top "
            f"{block_top:g} (6.3: pip.top + pip.diameter <= captions.anchor_y - "
            "captions.max_lines x line height)"
        )
    if spec.status == "shipped":
        missing = [c for c in spec.requires_components if c not in registry]
        if missing:
            raise StyleError(
                f"{spec.name}: shipped but requires_components {missing} are not in the "
                f"renderer registry {list(registry)} (9.2)"
            )


def load_all(registry: Sequence[str], styles_dir: Path = STYLES_DIR) -> dict[str, StyleSpec]:
    """Every `<name>.md` under `styles_dir`, validated; the default must be shipped."""
    specs: dict[str, StyleSpec] = {}
    for path in sorted(styles_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        spec = parse(path.read_text(encoding="utf-8"), name=path.stem)
        check(spec, registry)
        specs[spec.name] = spec
    if DEFAULT not in specs:
        raise StyleError(f"{DEFAULT}: no styles/{DEFAULT}.md; the resolver falls back to it (1.1)")
    if specs[DEFAULT].status != "shipped":
        raise StyleError(f"{DEFAULT}: must be shipped, it is the fallback style (1.4)")
    return specs


def shipped(specs: Mapping[str, StyleSpec]) -> list[str]:
    """Names the upload form offers as chips (2.1)."""
    return [name for name, spec in specs.items() if spec.status == "shipped"]


# --- resolver (1.1, 1.4) ---------------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]*")


@dataclass(frozen=True)
class Resolution:
    name: str
    note: str
    notice: str = ""


def tokens(line: str) -> list[str]:
    return _TOKEN.findall(line.lower())


def resolve(line: str, specs: Mapping[str, StyleSpec]) -> Resolution:
    words = tokens(line)
    scores = {
        name: sum(1 for w in words if w in {a.lower() for a in spec.aliases})
        for name, spec in specs.items()
    }
    best = max(scores.values(), default=0)
    winners = [name for name, score in scores.items() if score == best]
    if best == 0 or len(winners) != 1:
        return Resolution(name=DEFAULT, note=line)
    (winner,) = winners
    if specs[winner].status != "shipped":
        return Resolution(
            name=DEFAULT, note=line, notice=f"{winner} not available yet, using {DEFAULT}"
        )
    return Resolution(name=winner, note=line)
