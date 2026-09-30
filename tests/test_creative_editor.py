"""110a: the planner edits like a creative human editor.

The picture prompt (v20, extended as 099 planned) carries "The creative editor": the full
vocabulary 099, 102, 103, 104, 107, 108 and 109 built, listed in one place; plan each
line as an editor would (this line, the previous two beats, a surprise that does not
distract); vary it so no two reels feel like one template; say in each beat's `why` what
was chosen and why. The operator's taste (30 Sep 2026): moving footage is a range, not a
rule; the low end is a target, never a gate; never force a bad clip; never fail a job;
never the same picture treatment back to back; a named person never a stock stranger or
AI. The narrow clip examples ("cheese", "the sun", "a busy market") and the concept-only
opening clip are gone.

Worked examples across styles: when fewer than two of the job's own-style examples show
moving footage, `examples.select` adds one Tier A card from another style (the job's
topic first), labelled as a vocabulary example, not a style example. No network.
"""

from __future__ import annotations

from typing import get_args

from shortsmith.contracts import (
    CAMERA_MOVES,
    PICTURE_TREATMENTS,
    Beat,
    PicturePlan,
    Transition,
)
from shortsmith.planner import FakePlanner, prompt
from shortsmith.reference import examples
from tests.test_planner_prompt import _request  # pyright: ignore[reportPrivateUsage]
from tests.test_worked_examples import (
    TOPICS,
    _card,  # pyright: ignore[reportPrivateUsage]
    _transcript,  # pyright: ignore[reportPrivateUsage]
)

SECTION = "The creative editor"


def _text() -> str:
    return (prompt.PROMPTS_DIR / f"picture_{prompt.PROMPT_VERSION}.md").read_text(
        encoding="utf-8"
    )


def _section() -> str:
    """The section, its line wrapping collapsed to single spaces."""
    text = _text()
    assert SECTION in text
    start = text.index(SECTION)
    return " ".join(text[start : text.index("\nThe speaker's order", start)].split())


# --- the prompt section ---------------------------------------------------------------------


def test_the_section_comes_first_in_how_to_plan() -> None:
    text = _text()
    assert text.index("## How to plan") < text.index(SECTION) < text.index("The speaker's order")


def test_the_section_lists_the_full_vocabulary_in_one_place() -> None:
    section = _section()
    names = [
        "`clip`", *(f"`{t}`" for t in PICTURE_TREATMENTS), *(f"`{m}`" for m in CAMERA_MOVES),
        *(f"`{t}`" for t in get_args(Transition)),
        "`stamp`", "`text_pops`", "`banner`", "`bubbles`", "`lower_third`", "`calendar`",
        "`map`", "`counter`", "`chart`", "`particles`", "`stickers`",
    ]  # fmt: skip
    missing = [n for n in names if n not in section]
    assert not missing, missing
    for needle in ("highlight", "circle", "tag", "burst of short beats", "held beat"):
        assert needle in section, needle


def test_the_section_plans_like_a_human_editor_and_varies() -> None:
    section = _section()
    for needle in (
        "what this line needs",
        "what the previous two beats did",
        "surprise without distracting",
        "no two reels feel like one template",
        "`why`",
    ):
        assert needle in section, needle


def test_the_operator_taste_is_written_faithfully() -> None:
    section = _section()
    for needle in (
        "Moving footage is a range, not a rule",
        "Decide per script how much really fits",
        "a target, never a gate",
        "logged reason",
        "Never force a bad clip",
        "never fails the job",
        "never runs back to back",
        "never a stock stranger and never AI",
    ):
        assert needle in section, needle


def test_the_prompts_own_examples_cover_place_era_object_and_event_clips() -> None:
    section = _section()
    for label in ("a place (", "an era (", "an object (", "an event ("):
        assert label in section, label


def test_the_narrow_clip_examples_and_the_concept_only_opening_are_gone() -> None:
    text = _text()
    assert '"cheese", "the sun"' not in text
    assert '"a busy market"' not in text
    assert "When the topic is a concept" not in text
    assert "on the opening when the topic is a concept" not in text


# --- the beat's `why` -----------------------------------------------------------------------


def test_a_beat_carries_its_why_in_the_reply_schema() -> None:
    assert Beat.model_fields["why"].default == ""
    schema = PicturePlan.model_json_schema()
    assert "why" in schema["$defs"]["Beat"]["properties"]


def test_the_fake_plan_says_why_on_every_beat() -> None:
    plan = FakePlanner().plan_picture(_request())
    assert all(b.why.strip() for b in plan.beats), [b.id for b in plan.beats if not b.why]


# --- worked examples across styles ----------------------------------------------------------


def _stills(vid: str, *, topic: str = "history", tier: str = "B",
            styles: tuple[str, ...] = ("vishva",)):  # fmt: skip
    """A card whose every beat and shot is a still (the Vishva Gyan shorts)."""
    card = _card(vid, topic=topic, tier=tier, styles=styles)
    return card.model_copy(update={
        "beats": [b.model_copy(update={"layout": "full_still"}) for b in card.beats],
        "shots": [s.model_copy(update={"background": "still_photo", "footage_kind": None})
                  for s in card.shots],
    })  # fmt: skip


def test_a_card_shows_footage_when_a_beat_or_shot_moves() -> None:
    assert examples.shows_footage(_card("aaaaaaaaaaa"))  # the recorded S5j answer
    assert not examples.shows_footage(_stills("bbbbbbbbbbb"))


def test_a_vishva_job_gets_a_footage_vocabulary_example_on_its_topic() -> None:
    cards = [
        _stills("FbaBcWgMIEY"), _stills("ePTZVwipoAM"),
        _card("sssssssssss", topic="science", styles=("footage",)),
        _card("hhhhhhhhhhh", topic="history", styles=()),
        _card("bbbbbbbbbbb", topic="history", tier="B", styles=("explainer",)),
    ]  # fmt: skip
    picked = examples.select(cards, style="vishva", topic="history")
    assert [c.video_id for c in picked] == ["FbaBcWgMIEY", "ePTZVwipoAM", "hhhhhhhhhhh"]
    assert [examples.is_vocabulary(c, "vishva") for c in picked] == [False, False, True]


def test_no_near_topic_takes_another_topics_footage_card() -> None:
    cards = [_stills("FbaBcWgMIEY"), _card("sssssssssss", topic="science", styles=("footage",))]
    picked = examples.select(cards, style="vishva", topic="history")
    assert [c.video_id for c in picked] == ["FbaBcWgMIEY", "sssssssssss"]


def test_two_own_style_footage_examples_need_no_fill() -> None:
    cards = [
        _card("aaaaaaaaaaa", topic="history", styles=("vishva",)),
        _card("ccccccccccc", topic="history", styles=("vishva",)),
        _card("hhhhhhhhhhh", topic="history", styles=("footage",)),
    ]
    picked = examples.select(cards, style="vishva", topic="history")
    assert [c.video_id for c in picked] == ["aaaaaaaaaaa", "ccccccccccc"]


def test_the_fill_is_tier_a_only_and_shows_footage() -> None:
    cards = [
        _stills("FbaBcWgMIEY"),
        _card("bbbbbbbbbbb", topic="history", tier="B", styles=("explainer",)),
        _stills("sssssssssss", tier="A", styles=("footage",)),
    ]
    picked = examples.select(cards, style="vishva", topic="history")
    assert [c.video_id for c in picked] == ["FbaBcWgMIEY"]


def test_the_section_labels_the_vocabulary_example() -> None:
    own = examples.worked(_stills("FbaBcWgMIEY"), {})
    vocab = examples.worked(_card("hhhhhhhhhhh", topic="history", styles=()), {})
    vocab = vocab.model_copy(update={"vocabulary": True})
    text = examples.section([own, vocab])
    assert "### Example 1: FbaBcWgMIEY" in text
    assert "### Vocabulary example: hhhhhhhhhhh" in text
    assert "not a style example" in text
    assert "vocabulary" not in examples.section([own]).lower()


def test_the_real_library_gives_a_vishva_history_job_a_footage_example() -> None:
    topic, worked = examples.for_job(
        "Topic: history\nKing Saud and the oil boom.", _transcript("raja", "tel"), "vishva",
        topics=TOPICS,
    )  # fmt: skip
    assert topic.name == "history"
    assert [w.vocabulary for w in worked].count(True) == 1
    assert worked[-1].vocabulary and worked[-1].tier == "A"
    assert any(r.layout == "full_footage" for r in worked[-1].rows)
