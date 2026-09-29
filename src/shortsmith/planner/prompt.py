"""The one prompt builder (decisions 2.3, 4.1, 8.1, 8.2, 8.3).

`build_prompt(request, call)` renders the versioned instruction file
`prompts/<call>_<PROMPT_VERSION>.md`, then the PlanRequest in the fixed 2.3 order
(spec numbers, spec prose, brief, style note, references, transcript: the brief is
the intent and precedes the transcript, the material), then for the sound call the
validated, snapped picture plan and the audio catalogue tags (8.1), then the JSON
schema generated from the model the parser validates (one source of truth), then on
the one retry the previous output and the violation list (8.2), and last the
"reply with JSON only" line. Every adapter sends this identical text, so switching
`PLANNER` changes cost and nothing else. `SYSTEM_PROMPT` is the one system prompt both
real adapters send, and `split_prompt` cuts (never rebuilds) the text where the api
adapter puts its cache markers.

The tier lists come from the spec: tier 1 is `broll.kinds`, tier 2 is every tier-2
kind with the spec's `broll.tier2_kinds` allowed and the rest refused (4.1 / 9.2).
The picture file states the 055 rule in one paragraph: the short starts with the first
spoken word, every word plays once in the speaker's order, the cut removes only
silence. Changing an instruction file's meaning means a new file and a new
`PROMPT_VERSION`; the version lands on every plan and in `job.json`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from string import Template
from typing import Literal

import yaml

from shortsmith import stickers
from shortsmith.contracts import (
    CATEGORIES,
    TIER2_KINDS,
    PicturePlan,
    PlanFeedback,
    PlanRequest,
    SoundStory,
)

Call = Literal["picture", "sound"]

# v16 (ticket 070): the sound file names the closed cue palette - `tick` on a pop-in,
# `whoosh` on a transition `sound.whoosh.on` names or a pop-in, `ding` only on an `idea`
# sticker, `bass` / `drum` / `thump` on landed events - with the `sound.tick`,
# `sound.whoosh` and `sound.ding` caps, says code marks further pop-ins and transitions
# itself, and that no other name is accepted; the schema lists the six kinds. The
# picture file is v15's unchanged.
# (v15, ticket 066: the picture file's Beats section states the still-screen rule (3.1
# as amended): a pop, bubble or sticker counts at its word's time, a stamp or
# lower-third at mid-beat, the longest span between changes at most
# `beats.density_gap_max_s`; the text-pop paragraph no longer implies a stamp makes up
# for a pop in the same half. The sound file is v14's unchanged.
# (v14, ticket 059: the picture file says when to write `title_strip` (the topic in at
# most `broll.title_strip.words_max` words, only where section 1 carries the row; empty
# elsewhere) and the schema carries the field; the sound file is v13's unchanged.
# v13, ticket 062: the picture file says when to write `stickers` (a 3D emoji picked by
# a tag of the committed catalogue, rendered tag by tag as `$stickers`, and optionally one
# of that tag's names, never a file; landing on the spoken `word`; above the speaker's
# circle without `{x, y}`, which a beat without the circle needs; one per beat under
# `broll.stickers_max_per_60s`; `at_s` left to code); the sound file says a ding or pop
# cue at `event`, and a whoosh under `pop`, may ride a sticker's pop-in.
# (v12, ticket 058: the picture file says when to ask `clip` (moving stock footage on a
# concept beat and on a concept opening, never a named entity, under
# `broll.clip_max_fraction`, a request the still ladder answers when no clip fits; its
# asset shared only with clip and carry-on beats, never a set piece's item), and that a
# text pop or a bubble may sit on a clip; the sound file says a clip is muted and an
# ordinary picture beat for cues;
# v11, ticket 063: the picture file says when to write `bubbles` (speech or thought
# bubbles of 1-`broll.motion.bubble.words_max` words the recording itself carries, on a
# photo, card or presenter-full beat, `first`-`last` naming the source words, the tail at
# `{x, y}`, a dialogue pair landing `dialogue_gap_min_s`-`dialogue_gap_max_s` apart, under
# `broll.bubbles_max_per_60s`, `at_s` left to code); the sound file says an `event` cue
# may hit a bubble and a whoosh may ride its pop-in like a text pop's;
# v10, ticket 061: the picture file says when to write `text_pops` (1-4 words from the
# script on a photo, card or presenter-full beat, at `{x, y, anchor}` near the thing
# named, landing on the transcript `word`, under `broll.motion.text_pop.max_per_beat`
# and `broll.text_pops_max_per_60s`, `at_s` left to code); the sound file says an
# `event` cue may hit a pop and a whoosh may ride a pop-in with `pop` in `sound.whoosh.on`;
# v9, ticket 060: the picture file says when to ask `flash` (a turn back to the
# presenter or a section change, under `broll.flash_max_per_60s`, never two in a row,
# only where the style lists it); the sound file says a whoosh is allowed only where
# section 1 carries `sound.whoosh`, and then only at the start of a `flash` beat (or a
# pop-in), within its caps; v8, ticket 057: the opening beats ask `photo` - full-screen
# whenever the image can fill the frame at the style's `broll.full_bleed_max_upscale`, a
# card only when it cannot; v7, ticket 055: the short opens with the speaker's own first
# words over the strongest images of the subject - no cold-open lift, no hook title, no
# hook cards; the cut removes only silence, beats are written on the recording's
# timeline; v6, ticket 033: the `category` rule; v5, ticket 020: the `map` recipe; v4,
# ticket 029: the `counter` overlay and `label_flyin`; v3, ticket 021: the chart and
# diagram data; v2, ticket 027: the set-piece content rules.)))
PROMPT_VERSION = "v16"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SYSTEM_PROMPT = (
    "You are the Shortsmith planner. You have no tools. Read the whole message and "
    "reply with JSON only: one object matching the schema it gives."
)
SPEC_HEADING = "## 1. Style numbers"
REQUEST_HEADING = "## 3. Brief"
REPLY_JSON_ONLY = (
    "Reply with JSON only: one object that matches the schema above, "
    "with no prose before or after it."
)
MODELS: Mapping[Call, type[PicturePlan] | type[SoundStory]] = {
    "picture": PicturePlan,
    "sound": SoundStory,
}


def build_prompt(
    request: PlanRequest,
    call: Call,
    *,
    picture: PicturePlan | None = None,
    catalogue_tags: Sequence[str] = (),
    feedback: PlanFeedback | None = None,
) -> str:
    if call == "sound" and picture is None:
        raise ValueError("the sound call needs the validated picture plan (8.1)")
    parts = [_instructions(request, call), *_sections(request)]
    if call == "sound":
        assert picture is not None
        parts.append(
            "## 7. Validated picture plan\n\n"
            "Boundaries are snapped and events are final; cue against these beats.\n\n"
            f"```json\n{picture.model_dump_json(indent=2)}\n```"
        )
        tags = ", ".join(catalogue_tags) if catalogue_tags else (
            "(no catalogue yet: describe the theme and mood in plain words)"
        )
        parts.append(f"## 8. Audio catalogue tags\n\n{tags}")
    schema = json.dumps(MODELS[call].model_json_schema(), indent=2)
    parts.append(f"## JSON schema ({MODELS[call].__name__})\n\n```json\n{schema}\n```")
    if feedback is not None:
        violations = "\n".join(f"- {line}" for line in feedback.violations)
        parts.append(
            "## Your previous reply was rejected\n\n"
            "Fix every violation below and send the whole corrected object again.\n\n"
            f"Violations:\n{violations}\n\n"
            f"Previous reply:\n\n```json\n{feedback.previous}\n```"
        )
    parts.append(REPLY_JSON_ONLY)
    return "\n\n".join(part.strip() for part in parts) + "\n"


def split_prompt(text: str) -> tuple[str, str, str]:
    """`build_prompt`'s text cut, not rebuilt, into instructions, spec sections (1-2)
    and request (3 onward) for the api adapter's cache markers; the three concatenate
    back to `text` exactly."""
    spec = text.find(f"\n{SPEC_HEADING}")
    request = text.find(f"\n{REQUEST_HEADING}\n", spec + 1)
    if spec < 0 or request < 0:
        raise ValueError("the prompt has no spec or brief heading to split at")
    return text[: spec + 1], text[spec + 1 : request + 1], text[request + 1 :]


def _instructions(request: PlanRequest, call: Call) -> str:
    path = PROMPTS_DIR / f"{call}_{PROMPT_VERSION}.md"
    template = Template(path.read_text(encoding="utf-8"))
    reasons = _strings(_group(request.style.numbers, "presenter"), "full_reasons")
    return template.substitute(
        prompt_version=PROMPT_VERSION,
        style_name=request.style.name,
        tiers=_tiers(request.style.numbers),
        full_reasons=", ".join(reasons),
        categories=", ".join(CATEGORIES),
        stickers=_sticker_catalogue(),
    )


def _sticker_catalogue() -> str:
    """062: the committed sticker catalogue as the planner reads it, one line per tag
    with its emoji names in catalogue order (the first is the tag's default)."""
    catalogue = stickers.shipped()
    return "\n".join(
        f"  - {tag}: {', '.join(e.name for e in catalogue.with_tag(tag))}"
        for tag in catalogue.tags()
    )


def _group(numbers: Mapping[str, object], name: str) -> Mapping[str, object]:
    group = numbers.get(name, {})
    return group if isinstance(group, Mapping) else {}  # pyright: ignore[reportUnknownVariableType]


def _strings(group: Mapping[str, object], key: str) -> list[str]:
    values = group.get(key, [])
    return [str(v) for v in values] if isinstance(values, list) else []  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]


def _tiers(numbers: Mapping[str, object]) -> str:
    broll = _group(numbers, "broll")
    tier1 = _strings(broll, "kinds")
    allowed = [k for k in TIER2_KINDS if k in _strings(broll, "tier2_kinds")]
    refused = [k for k in TIER2_KINDS if k not in allowed]
    lines = [f"- Tier 1 (allowed): {', '.join(tier1)}"]
    if allowed:
        lines.append(f"- Tier 2 (allowed): {', '.join(allowed)}")
    if refused:
        lines.append(
            f"- Tier 2 (not allowed on this style): {', '.join(refused)}. Naming one is "
            "rejected; use the nearest tier-1 kind instead."
        )
    lines.append(
        "- `kind` is one allowed kind. The presenter pseudo-kinds `presenter_full` and "
        "`presenter_pip` go with `full` and `pip` beats that show only the presenter."
    )
    return "\n".join(lines)


def _sections(request: PlanRequest) -> list[str]:
    numbers = dict(request.style.numbers)
    numbers["job"] = {
        "max_duration_s": request.constraints.max_duration_s,
        "target_duration_s": request.constraints.target_duration_s,
        "asset_policy": request.asset_policy,
    }
    dumped = yaml.safe_dump(numbers, sort_keys=False, allow_unicode=True).strip()
    return [
        f"{SPEC_HEADING} ({request.style.name})\n\n```yaml\n{dumped}\n```",
        f"## 2. Style prose\n\n{_demoted(request.style.prose) or '(none)'}",
        f"{REQUEST_HEADING}\n\n{request.brief.strip()}",
        f"## 4. Style note\n\n{request.style_note.strip() or '(none)'}",
        f"## 5. References\n\n{_references(request)}",
        f"## 6. Transcript\n\n{_transcript(request)}",
    ]


def _demoted(prose: str) -> str:
    """The spec's own headings (`# Style: <name>`, `## <section>`) nest under section 2."""
    return "\n".join(
        f"##{line}" if line.startswith("#") else line for line in prose.strip().splitlines()
    )


def _references(request: PlanRequest) -> str:
    if not request.references:
        return "(no references)"
    return "\n".join(
        f"- {r.id} ({r.kind}, {r.width}x{r.height}): {r.caption.strip() or '(no caption)'}"
        for r in request.references
    )


def _transcript(request: PlanRequest) -> str:
    transcript = request.transcript
    head = (
        f"Language: {transcript.language}; duration {transcript.duration_s:.2f} s; "
        f"{len(transcript.words)} words as `[index] start-end text` (seconds)."
    )
    words = "\n".join(
        f"[{i}] {w.start:.2f}-{w.end:.2f} {w.text}" for i, w in enumerate(transcript.words)
    )
    flagged = [
        f"segment {i} ({s.start:.2f}-{s.end:.2f})"
        + (" low confidence" if s.low_confidence else "")
        + (" no speech" if s.no_speech else "")
        for i, s in enumerate(transcript.segments)
        if s.low_confidence or s.no_speech
    ]
    tail = (
        "Flagged segments (do not stamp their words without the brief's support): "
        + "; ".join(flagged)
        if flagged
        else "No segment is flagged."
    )
    return f"{head}\n\n{words}\n\n{tail}"
