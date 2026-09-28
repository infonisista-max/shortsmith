"""planner.prompt: one builder renders a PlanRequest into the fixed sections (2.3:
spec numbers, spec prose, brief, style note, references, transcript; brief before
transcript) after the versioned instruction file, appends the JSON schema generated
from the model the parser validates (8.1), and on a retry the previous output and the
violation list (8.2). The recorded rendering is a snapshot under
`tests/fixtures/planner/`; set SHORTSMITH_UPDATE_SNAPSHOTS=1 to re-record it after a
deliberate prompt change (and bump the prompt version when the change is real)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from shortsmith import fixture
from shortsmith.contracts import (
    CATEGORIES,
    Constraints,
    PicturePlan,
    PlanFeedback,
    PlanReference,
    PlanRequest,
    PlanStyle,
    SoundStory,
)
from shortsmith.planner import FakePlanner, prompt
from shortsmith.transcriber import FakeTranscriber

SNAPSHOTS = Path(__file__).parent / "fixtures" / "planner"
SECTIONS = [
    "## 1. Style numbers",
    "## 2. Style prose",
    "## 3. Brief",
    "## 4. Style note",
    "## 5. References",
    "## 6. Transcript",
]


def _request() -> PlanRequest:
    """A fixed request that does not move when a real spec is edited."""
    return PlanRequest(
        brief="Topic: nothing. Must-say: twelve words. Hook wish: a number.",
        style=PlanStyle(
            name="explainer",
            numbers={
                "beats": {"min_s": 0.7, "max_s": 6.0},
                "presenter": {"full_reasons": ["emotional_line", "argument_turn"]},
                "broll": {"kinds": ["photo", "card", "stamp", "map"], "tier2_kinds": []},
            },
            prose="## Beat grammar\n- Beats 2-6 s.",
        ),
        style_note="explainer, energetic, in Hindi",
        transcript=FakeTranscriber().transcribe(Path("unused.mp4")),
        references=[
            PlanReference(id="ref1", kind="image", caption="my product", width=1200, height=1600),
            PlanReference(id="ref2", kind="clip_frame", caption="", width=1080, height=1920),
        ],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    )


def _positions(text: str, needles: list[str]) -> list[int]:
    return [text.index(n) for n in needles]


def test_the_six_sections_render_in_the_fixed_order_brief_before_transcript() -> None:
    text = prompt.build_prompt(_request(), "picture")
    positions = _positions(text, SECTIONS)
    assert positions == sorted(positions)
    assert text.index("Must-say: twelve words") < text.index("## 6. Transcript")
    assert "explainer, energetic, in Hindi" in text
    assert "\n#### Beat grammar\n- Beats 2-6 s." in text  # nested under section 2


def test_the_split_for_cache_markers_cuts_the_text_and_never_rebuilds_it() -> None:
    """015: the api adapter's three blocks are cuts of this text, so the prompt it
    sends stays byte-identical to the one the CLI adapter sends on stdin."""
    for call in ("picture", "sound"):
        picture = FakePlanner().plan_picture(_request()) if call == "sound" else None
        text = prompt.build_prompt(_request(), call, picture=picture)  # pyright: ignore[reportArgumentType]
        instructions, spec, rest = prompt.split_prompt(text)
        assert instructions + spec + rest == text
        assert spec.startswith("## 1. Style numbers") and "## 2. Style prose" in spec
        assert rest.startswith("## 3. Brief")
    with pytest.raises(ValueError, match="no spec or brief heading"):
        prompt.split_prompt("no headings here")


def test_references_are_a_captioned_list_never_pixels() -> None:
    text = prompt.build_prompt(_request(), "picture")
    assert "- ref1 (image, 1200x1600): my product" in text
    assert "- ref2 (clip_frame, 1080x1920): (no caption)" in text
    empty = _request().model_copy(update={"references": []})
    assert "(no references)" in prompt.build_prompt(empty, "picture")


def test_the_transcript_lists_every_word_with_its_index_and_times() -> None:
    request = _request()
    text = prompt.build_prompt(request, "picture")
    for i, word in enumerate(request.transcript.words):
        assert f"[{i}] {word.start:.2f}-{word.end:.2f} {word.text}" in text


@pytest.mark.parametrize(("call", "model"), [("picture", PicturePlan), ("sound", SoundStory)])
def test_the_schema_generated_from_the_model_is_appended(
    call: str, model: type[PicturePlan] | type[SoundStory]
) -> None:
    request = _request()
    picture = FakePlanner().plan_picture(request)
    text = prompt.build_prompt(request, call, picture=picture)  # pyright: ignore[reportArgumentType]
    schema = json.dumps(model.model_json_schema(), indent=2)
    assert schema in text
    assert text.index("## 6. Transcript") < text.index(schema)
    assert text.rstrip().endswith(prompt.REPLY_JSON_ONLY)


def test_the_picture_prompt_lists_the_tiers_from_the_spec() -> None:
    """4.1 / 9.2: tier 1 is the spec's `broll.kinds`; tier 2 is refused on a style
    whose `tier2_kinds` is empty, and the prompt says so."""
    text = prompt.build_prompt(_request(), "picture")
    assert "Tier 1 (allowed): photo, card, stamp, map" in text
    assert "Tier 2 (not allowed on this style): parallax, vector_illustration" in text
    assert "emotional_line, argument_turn" in text and "cold_open" not in text


def test_a_style_with_tier2_kinds_lists_them_as_allowed() -> None:
    request = _request()
    numbers = {**request.style.numbers, "broll": {"kinds": ["photo"], "tier2_kinds": ["parallax"]}}
    style = request.style.model_copy(update={"numbers": numbers})
    text = prompt.build_prompt(request.model_copy(update={"style": style}), "picture")
    assert "Tier 2 (allowed): parallax" in text
    assert "Tier 2 (not allowed on this style): vector_illustration" in text


def test_the_picture_prompt_carries_the_planning_rules() -> None:
    """2.3 brief-fact stamping, 5.1 source_intent, 6.1 name_runs and keywords are asked
    for in words, not only by the schema; 055's rule (the first spoken word, every word
    once in order, the cut removes only silence) is stated, and the hook fields are
    gone from the prompt and the schema."""
    text = prompt.build_prompt(_request(), "picture")
    for needle in (
        "stamp",
        "source_intent",
        "name_runs",
        "keywords",
        "must use",
        "first spoken word",
        "plays every word once",
        "never drop one",
        "removes only silence",
        "cut.max_pause_s",
        "beats.opening_beats_min",
        "presenter.opening_mode",
    ):
        assert needle in text, needle
    for gone in ("hook.original_position", "cold_open_span", "hook_cards", "hook.title",
                 '"hook"', "cold_open"):
        assert gone not in text, gone
    assert prompt.PROMPT_VERSION == "v14"


def test_the_v14_picture_prompt_says_when_to_write_the_title_strip() -> None:
    """059: the picture file says to write `title_strip` (the topic in at most
    `broll.title_strip.words_max` words) only where section 1 carries the row, and to
    leave it empty elsewhere; the schema carries the field."""
    picture = prompt.build_prompt(_request(), "picture")
    for needle in (
        "Title strip",
        "`title_strip`",
        "`broll.title_strip.words_max`",
        "leave `title_strip` empty",
        '"title_strip"',
    ):
        assert needle in picture, needle


def test_the_v9_prompts_say_when_to_flash_and_where_a_whoosh_may_sit() -> None:
    """060: the picture file's flash rule (a turn back to the presenter or a section
    change, under `broll.flash_max_per_60s`, never two in a row, only where the style
    lists it) and the sound file's whoosh rule (only under `sound.whoosh`, only at the
    start of a `flash` beat or a pop-in, within its caps)."""
    picture = prompt.build_prompt(_request(), "picture")
    for needle in (
        "`flash`",
        "turn back to the presenter or a section change",
        "`broll.flash_max_per_60s`",
        "never on two consecutive beats",
        "A style without `flash` in the list\n  never gets one",
    ):
        assert needle in picture, needle
    sound = prompt.build_prompt(_request(), "sound", picture=FakePlanner().plan_picture(_request()))
    for needle in (
        "no whooshes unless section 1 carries a\n  `sound.whoosh` allowance",
        "`intent: whoosh`",
        "`enter` is `flash`",
        "`sound.whoosh.max_per_60s`",
        "`sound.whoosh.min_gap_s`",
        "Code refuses a whoosh anywhere else",
    ):
        assert needle in sound, needle


def test_the_v10_prompts_say_when_to_pop_text_and_where_its_cue_sits() -> None:
    """061: the picture file's text pop rule (1-4 words from the script on a picture
    beat, at `{x, y, anchor}` near the thing named, landing on the spoken `word`, under
    `broll.motion.text_pop.max_per_beat` and `broll.text_pops_max_per_60s`, never where
    the cap is 0, `at_s` left to code) and the sound file's pop-in wording (an `event`
    cue may hit a pop; a whoosh may ride it under `sound.whoosh` with `pop` in `on`)."""
    picture = prompt.build_prompt(_request(), "picture")
    for needle in (
        "`text_pops`",
        "1-4 words",
        "`broll.motion.text_pop.max_per_beat`",
        "`broll.text_pops_max_per_60s`",
        "Never write `at_s`",
        "the transcript word index",
    ):
        assert needle in picture, needle
    sound = prompt.build_prompt(_request(), "sound", picture=FakePlanner().plan_picture(_request()))
    for needle in (
        "`text_pops`",
        "`at: event`",
        "`pop` in `sound.whoosh.on`",
    ):
        assert needle in sound, needle


def test_the_v11_prompts_say_when_to_bubble_and_that_the_words_are_the_recordings() -> None:
    """063: the picture file's bubble rule (speech or thought, 1-`words_max` words only
    from the recording with `first`-`last` naming them, the tail at `{x, y}`, a dialogue
    pair landing the gap apart, under `broll.bubbles_max_per_60s`, never where the cap
    is 0, `at_s` left to code) and the sound file's wording (an `event` cue may hit a
    bubble; a whoosh may ride it under `sound.whoosh` with `pop` in `on`)."""
    picture = prompt.build_prompt(_request(), "picture")
    for needle in (
        "`bubbles`",
        "`speech`",
        "`thought`",
        "never a quote the recording does not carry",
        "`first` and `last` are the\n  transcript word indices",
        "`broll.motion.bubble.words_max`",
        "`broll.motion.bubble.max_per_beat`",
        "`broll.motion.bubble.dialogue_gap_min_s`",
        "`broll.bubbles_max_per_60s`",
        "Never write\n  `at_s`",
    ):
        assert needle in picture, needle
    sound = prompt.build_prompt(_request(), "sound", picture=FakePlanner().plan_picture(_request()))
    for needle in (
        "`text_pops`, `bubbles` or `stickers`",  # v13 (062) added the sticker
        "A text pop, a\n  bubble or a sticker may carry a hit",
        "`pop` in `sound.whoosh.on`",
    ):
        assert needle in sound, needle


def test_the_v13_prompts_say_when_to_stick_an_emoji_and_list_the_catalogue_by_tag() -> None:
    """062: the picture file's sticker rule (picked by a catalogue tag and optionally one
    of its names, never a file; landing on the spoken `word`; above the circle without
    `{x, y}`; one per beat under `broll.stickers_max_per_60s`; `at_s` left to code) with
    the committed catalogue rendered tag by tag; the sound file says a ding or pop cue
    and a whoosh may ride a sticker's pop-in."""
    from shortsmith import stickers

    picture = prompt.build_prompt(_request(), "picture")
    for needle in (
        "Stickers (3D emoji pops)",
        "`stickers`",
        "Pick it by `intent`",
        "Never write a file name",
        "above the speaker's circle",
        "`broll.motion.sticker.max_per_beat`",
        "`broll.stickers_max_per_60s`",
        "- idea: Light bulb, Brain, Puzzle piece, Exploding head",
        "- death: Skull, Coffin, Ghost",
    ):
        assert needle in picture, needle
    for tag in stickers.shipped().tags():
        assert f"\n  - {tag}: " in picture, tag
    sound = prompt.build_prompt(_request(), "sound", picture=FakePlanner().plan_picture(_request()))
    assert "`text_pops`, `bubbles` or `stickers`" in sound
    assert "Stickers (3D emoji pops)" not in sound


def test_the_v12_prompts_say_when_to_ask_a_clip_and_never_for_a_named_entity() -> None:
    """058: the picture file's clip rule (moving stock footage on a concept beat and a
    concept opening, never a named entity, under `broll.clip_max_fraction`, a request the
    still ladder answers when no clip fits, its asset never a set piece's still) and the
    sound file's line (a clip is muted, an ordinary picture beat for cues)."""
    picture = prompt.build_prompt(_request(), "picture")
    for needle in (
        "Moving footage (`clip`)",
        "always muted",
        "Never for a named entity",
        "a stock stranger is never the person named",
        "`broll.clip_max_fraction`",
        "Pexels video, then Pixabay video",
        "a clip shorter than its beat is skipped",
        "request, never a promise",
        "a `photo`, `card`, `clip` or\n  presenter-full beat may carry `text_pops`",
        "a `photo`, `card`, `clip` or\n  presenter-full beat may carry `bubbles`",
        "an opening beat may be a\n  `clip`",
    ):
        assert needle in picture, needle
    sound = prompt.build_prompt(_request(), "sound", picture=FakePlanner().plan_picture(_request()))
    assert "A `clip` beat (moving stock footage) is always muted" in sound
    plan = FakePlanner().plan_picture(_request())
    assert [b.id for b in plan.beats if b.kind == "clip"] == ["b04"]


def test_the_picture_prompt_v8_asks_for_photo_on_the_opening_beats() -> None:
    """057 (4): the opening beats ask `photo` (full-screen whenever the image allows;
    code draws a card only when it cannot fill the frame); v7's "`photo` or a `card`"
    is gone."""
    text = prompt.build_prompt(_request(), "picture")
    assert "each a `photo` with an" in text
    assert "`photo` or a\n  `card`" not in text and "`photo` or a `card`" not in text
    assert "cannot fill the frame at `broll.full_bleed_max_upscale`" in text


def test_the_picture_prompt_names_the_categories_the_planner_may_choose_from() -> None:
    """10.3 / 033: the category is set by the planner from the fixed list, so the list
    is in the instructions in words, not only in the schema."""
    text = prompt.build_prompt(_request(), "picture")
    assert "`category`" in text
    assert ", ".join(CATEGORIES) in text
    assert '"category"' in text  # the schema carries the field too


def test_the_sound_prompt_carries_the_snapped_picture_and_the_catalogue_tags() -> None:
    """8.1: the sound call gets the validated, snapped picture plan and the tags."""
    request = _request()
    picture = FakePlanner().plan_picture(request)
    text = prompt.build_prompt(
        request, "sound", picture=picture, catalogue_tags=["suspense", "money", "reveal_drop"]
    )
    assert picture.model_dump_json(indent=2) in text
    assert "suspense, money, reveal_drop" in text
    none = prompt.build_prompt(request, "sound", picture=picture)
    assert "(no catalogue yet" in none


def test_the_sound_prompt_needs_the_picture_plan() -> None:
    with pytest.raises(ValueError, match="picture"):
        prompt.build_prompt(_request(), "sound")


def test_a_retry_appends_the_previous_output_and_the_violations() -> None:
    feedback = PlanFeedback(previous='{"beats": []}', violations=["b03 (4.1): no motion"])
    text = prompt.build_prompt(_request(), "picture", feedback=feedback)
    first = prompt.build_prompt(_request(), "picture")
    assert text.startswith(first.rstrip().removesuffix(prompt.REPLY_JSON_ONLY).rstrip())
    assert '{"beats": []}' in text
    assert "- b03 (4.1): no motion" in text
    assert text.rstrip().endswith(prompt.REPLY_JSON_ONLY)


def test_the_prompt_files_are_versioned() -> None:
    assert (prompt.PROMPTS_DIR / f"picture_{prompt.PROMPT_VERSION}.md").is_file()
    assert (prompt.PROMPTS_DIR / f"sound_{prompt.PROMPT_VERSION}.md").is_file()
    assert f"Prompt version: {prompt.PROMPT_VERSION}" in prompt.build_prompt(_request(), "picture")


@pytest.mark.parametrize("call", ["picture", "sound"])
def test_the_rendering_matches_the_recorded_snapshot(call: str) -> None:
    request = _request()
    picture = FakePlanner().plan_picture(request)
    text = prompt.build_prompt(
        request, call, picture=picture, catalogue_tags=["suspense", "money"]  # pyright: ignore[reportArgumentType]
    )
    path = SNAPSHOTS / f"{call}_{prompt.PROMPT_VERSION}.snapshot.md"
    if os.environ.get("SHORTSMITH_UPDATE_SNAPSHOTS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.is_file(), f"no recorded rendering at {path}; record it deliberately"
    assert text == path.read_text(encoding="utf-8")
