"""reference.examples: the planner sees how two top shorts edited lines like yours
(ticket 077).

Code picks the job's topic before the planner runs (keyword hits from
`assets/reference/topics.yaml` in the brief and the transcript, counted like the style
aliases; a tie or no hit is style-only; `topic: <name>` in the brief wins), then two v2
cards by style, then topic, then the operator's own Tier B first. Their beat tables are
a picture-prompt section that says to copy the moves, never the content, with each
`unregistered` effect shown as its closest registered component or "(no equivalent:
skip)" from `assets/reference/effect_map.yaml`. The plan records `examples` and `topic`;
`compare_plan` re-plans once without examples and prints both match shares. No network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from shortsmith import app, jobs, meta, pipeline, presenter, render, vocab
from shortsmith import compare_plan as compare_cli
from shortsmith.contracts import PicturePlan, Transcript, ValidatedPlan, Word
from shortsmith.planner import FakePlanner, prompt
from shortsmith.qa.critic import FakeCritic
from shortsmith.qa.gate import FakeGate
from shortsmith.reference import (
    InventoryAnswerV2,
    ReferenceInventory,
    ReferenceInventoryV2,
    ReferenceLink,
    Tier,
    examples,
    parse_answer,
)
from shortsmith.reference.gemini import Usage
from shortsmith.render import FakeRenderer
from shortsmith.transcriber import FakeTranscriber
from tests.test_pipeline import SPECS, _sourcing, _uploaded  # pyright: ignore[reportPrivateUsage]
from tests.test_planner_prompt import _request  # pyright: ignore[reportPrivateUsage]

FIXTURES = Path(__file__).parent / "fixtures" / "gemini"
REGISTRY = render.registry()
TOPICS = vocab.load_topics()


def _answer_text() -> str:
    body = json.loads((FIXTURES / "inventory_v2.json").read_text(encoding="utf-8"))
    return body["candidates"][0]["content"]["parts"][0]["text"]


def _card(vid: str, *, topic: str = "science", tier: str = "A",
          styles: tuple[str, ...] = ("explainer",)) -> ReferenceInventoryV2:  # fmt: skip
    """The recorded v2 answer (S5j: 24 beats, the first carrying the unregistered
    `glowing_sun_prop`) as a card with the given id, topic, tier and styles."""
    answer = parse_answer(_answer_text(), registry=REGISTRY, version="v2")
    data = answer.model_dump()
    data["script"]["topic"] = topic
    link = ReferenceLink(url=f"https://www.youtube.com/watch?v={vid}", video_id=vid,
                         tier=cast(Tier, tier))  # fmt: skip
    made = ReferenceInventory.from_answer(
        InventoryAnswerV2.model_validate(data), link=link, model="m", fps=5.0,
        usage=Usage(), analysed_on="2026-09-29", styles=styles,
    )  # fmt: skip
    assert isinstance(made, ReferenceInventoryV2)
    return made


def _transcript(*texts: str) -> Transcript:
    words = [
        Word(text=t, start=i * 0.5, end=i * 0.5 + 0.4, segment=0) for i, t in enumerate(texts)
    ]
    return Transcript(language="hi", duration_s=len(texts) * 0.5, words=words, segments=[])


# --- the topic ------------------------------------------------------------------------------


def test_a_hindi_history_transcript_is_history() -> None:
    transcript = _transcript("यह", "राजा", "का", "साम्राज्य", "था,", "और", "युद्ध।", "itihas")
    picked = examples.pick_topic("King Saud short", transcript, TOPICS)
    assert picked == examples.TopicPick(name="history", source="keywords")


def test_a_tie_or_no_hit_is_style_only() -> None:
    tie = examples.pick_topic("", _transcript("king", "planet"), TOPICS)  # history 1, science 1
    assert tie.name is None and tie.source == "none"
    assert examples.pick_topic("", _transcript("hello", "there"), TOPICS).name is None


def test_topic_in_the_brief_wins_over_the_keywords() -> None:
    transcript = _transcript("राजा", "साम्राज्य", "युद्ध")
    picked = examples.pick_topic("Topic: science\nMust-say: the sun", transcript, TOPICS)
    assert picked == examples.TopicPick(name="science", source="brief")


def test_a_brief_topic_that_is_not_on_the_list_is_ignored() -> None:
    picked = examples.pick_topic("Topic: nothing. Must-say: raja", _transcript("x"), TOPICS)
    assert picked == examples.TopicPick(name="history", source="keywords")  # "raja" in the brief


# --- the selection --------------------------------------------------------------------------


def test_style_filters_first_topic_second_and_tier_b_wins_a_tie() -> None:
    cards = [
        _card("aaaaaaaaaaa", topic="history", tier="A"),
        _card("bbbbbbbbbbb", topic="history", tier="B"),
        _card("ccccccccccc", topic="science", tier="B"),
        _card("ddddddddddd", topic="history", tier="B", styles=("vishva",)),
        _card("eeeeeeeeeee", topic="history", tier="A"),
        _card("ownownownow", topic="history", tier="own"),
    ]
    picked = examples.select(cards, style="explainer", topic="history")
    assert [c.video_id for c in picked] == ["bbbbbbbbbbb", "aaaaaaaaaaa"]
    style_only = examples.select(cards, style="explainer", topic=None)
    assert [c.video_id for c in style_only] == ["bbbbbbbbbbb", "ccccccccccc"]


def test_fewer_than_two_takes_what_it_has_and_none_says_so() -> None:
    one = [_card("aaaaaaaaaaa", topic="history")]
    assert [c.video_id for c in examples.select(one, style="explainer", topic="sport")] == [
        "aaaaaaaaaaa"
    ]  # no sport card: the topic filter would leave nothing, so style only
    assert examples.select(one, style="vishva", topic=None) == []
    assert examples.section([]) == "(no worked examples for this style)"


# --- the prompt section ---------------------------------------------------------------------


def test_the_section_holds_both_beat_tables_with_unregistered_effects_mapped() -> None:
    first = _card("aaaaaaaaaaa", topic="history", tier="B")
    second = _card("bbbbbbbbbbb", topic="history")
    renamed = second.model_copy(deep=True)
    renamed.effects[0].name = "emoji_sticker_pop"  # at 0.6 s, inside the first beat
    worked = [examples.worked(c, {"glowing_sun_prop": None, "emoji_sticker_pop": "sticker"})
              for c in (first, renamed)]  # fmt: skip
    text = examples.section(worked)
    assert "aaaaaaaaaaa (Tier B, topic history" in text and "bbbbbbbbbbb (Tier A" in text
    assert text.count("| 0.0-3.0 | hook | What if the Sun vanished from the sky right now |") == 2
    assert "(no equivalent: skip)" in text  # glowing_sun_prop maps to nothing
    assert "sticker (closest to emoji_sticker_pop)" in text
    assert "| stamp |" in text  # a registered effect is shown as it is
    assert "never the content" in text
    assert "unregistered" not in text


def test_an_unregistered_effect_the_map_does_not_know_is_skipped() -> None:
    worked = examples.worked(_card("aaaaaaaaaaa"), {})
    assert worked.rows[0].effect == "(no equivalent: skip)"


def test_the_effect_map_names_only_registered_components_and_every_known_gap() -> None:
    mapping = examples.load_effect_map()
    assert set(v for v in mapping.values() if v is not None) <= set(REGISTRY)
    gaps: set[str] = set()
    # The live cards on purpose, like GAPS.md: a re-run card naming a new unregistered
    # effect should stop here until effect_map.yaml maps it.
    for path in examples.INVENTORY_DIR.glob("*.json"):
        card = json.loads(path.read_text(encoding="utf-8"))
        for item in card.get("effects", []) + card.get("transitions", []):
            if item["component"] == "unregistered":
                gaps.add(item["name"])
    assert gaps <= set(mapping), sorted(gaps - set(mapping))


# 106 (083 part 1): the operator's picks for the GAPS names, 30 Sep 2026.
GAPS_PICKS = {
    "number_badge_pop": "stamp", "numbered_tag": "stamp",
    "tag_pangea": "text_pop", "tag_supercontinent": "text_pop",
    "text_badge_pop": "text_pop", "stacked_labels": "text_pop",
    "text_banner": "lower_third",  # -> banner once 107 lands
    "persistent_header_banner": "title_strip",
    "label_slide": "label_flyin",
    "countdown_number_one": "counter", "countdown_number_two": "counter",
    "red_circle_india": "pin_drop",  # -> 104's map target circle once it lands
    "cartoon_scientist": "sticker",
}  # fmt: skip


def test_the_gaps_names_map_to_the_operators_closest_components() -> None:
    mapping = examples.load_effect_map()
    assert {name: mapping.get(name) for name in GAPS_PICKS} == GAPS_PICKS


def test_the_worked_examples_now_show_the_gaps_effects() -> None:
    shown: set[str] = set()
    for path in sorted(examples.INVENTORY_DIR.glob("*.json")):
        card = ReferenceInventoryV2.model_validate_json(path.read_text(encoding="utf-8"))
        shown |= {row.effect for row in examples.worked(card, examples.load_effect_map()).rows}
    picked = {e for e in shown if any(e.endswith(f"(closest to {n})") for n in GAPS_PICKS)}
    assert picked, "no worked example shows one of the GAPS picks"
    for effect in picked:
        name = effect.split("(closest to ")[1].rstrip(")")
        assert effect == f"{GAPS_PICKS[name]} (closest to {name})"


def test_an_effect_map_naming_an_unregistered_component_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "effect_map.yaml"
    bad.write_text("effects:\n  glow_title: sparkle_engine\n", encoding="utf-8")
    with pytest.raises(examples.EffectMapError, match="glow_title.*sparkle_engine"):
        examples.load_effect_map(bad, registry=REGISTRY)


def _with_examples() -> object:
    request = _request()
    cards = [_card("aaaaaaaaaaa", topic="science", tier="B"), _card("bbbbbbbbbbb")]
    worked = [examples.worked(c, examples.load_effect_map()) for c in cards]
    return request.model_copy(update={"topic": "science", "examples": worked})


def test_the_picture_prompt_carries_the_section_and_the_sound_prompt_does_not() -> None:
    request = _with_examples()
    picture = prompt.build_prompt(request, "picture")  # pyright: ignore[reportArgumentType]
    assert "## 7. How top shorts edit a line like yours" in picture
    assert picture.index("## 6. Transcript") < picture.index("## 7. How top shorts")
    assert "never the content" in picture
    sound = prompt.build_prompt(
        request, "sound", picture=FakePlanner().plan_picture(_request())  # pyright: ignore[reportArgumentType]
    )
    assert "How top shorts edit" not in sound
    bare = prompt.build_prompt(_request(), "picture")
    assert "(no worked examples for this style)" in bare
    assert prompt.PROMPT_VERSION == "v19"  # 077 v17; 076 v18 (the picture file unchanged); 078 v19


# --- the plan's match share -------------------------------------------------------------------


def test_the_plans_match_share_counts_named_entities_numbers_and_literal_subjects() -> None:
    plan = FakePlanner().plan_picture(_request())
    # b02, b05, b09 name an entity; b06 is the number beat: 4 of 11 beats
    assert examples.plan_match(plan) == (4, 11)
    assert examples.match_share(plan) == pytest.approx(4 / 11)


# --- the job: plan.validated.json, job.json, meta.json, the page ------------------------------


def _inventory(tmp_path: Path) -> Path:
    refs = tmp_path / "inventory"
    refs.mkdir()
    for card in (_card("aaaaaaaaaaa", topic="science"), _card("bbbbbbbbbbb", topic="science",
                 tier="B"), _card("ccccccccccc", topic="history", tier="B")):  # fmt: skip
        (refs / f"{card.video_id}.json").write_text(card.model_dump_json(), "utf-8")
    return refs


def _run(tmp_path: Path, clip: Path, brief: str) -> jobs.Job:
    job = _uploaded(tmp_path / "data", clip)
    (job.input_dir / "brief.md").write_text(brief, encoding="utf-8")
    return pipeline.run_job(
        job, transcriber=FakeTranscriber(), planner=FakePlanner(), renderer=FakeRenderer(),
        gate=FakeGate(), sourcing=_sourcing(), specs=SPECS,
        detector=presenter.FakeFaceDetector(), critic=FakeCritic(),
        inventory_dir=_inventory(tmp_path),
    )  # fmt: skip


def test_the_job_records_the_topic_and_the_two_examples(
    tmp_path: Path, fixture_clip: Path
) -> None:
    done = _run(tmp_path, fixture_clip, "Topic: science\nA short about the sun.")
    assert done.status == "delivered"
    validated = ValidatedPlan.model_validate_json(
        (done.work_dir / "plan.validated.json").read_text(encoding="utf-8")
    )
    assert validated.topic == "science"
    assert validated.examples == ["bbbbbbbbbbb", "aaaaaaaaaaa"]
    recorded = meta.load(done)
    assert recorded is not None
    assert (recorded.topic, recorded.examples) == ("science", ["bbbbbbbbbbb", "aaaaaaaaaaa"])
    page = app.render_job_page(jobs.load(done.path))
    assert "Worked examples" in page and "topic science" in page
    assert "bbbbbbbbbbb" in page and "aaaaaaaaaaa" in page
    log = done.log_path.read_text(encoding="utf-8")
    assert "worked examples: topic science (brief); bbbbbbbbbbb, aaaaaaaaaaa" in log


def test_a_style_only_job_records_no_topic(tmp_path: Path, fixture_clip: Path) -> None:
    done = _run(tmp_path, fixture_clip, "A short about nothing.")
    recorded = meta.load(done)
    assert recorded is not None and recorded.topic is None
    assert recorded.examples == ["bbbbbbbbbbb", "ccccccccccc"]  # Tier B first, then by id
    assert "topic none (style only)" in app.render_job_page(jobs.load(done.path))


def test_the_comparison_fills_the_match_share_row_for_our_plan(
    tmp_path: Path, fixture_clip: Path
) -> None:
    from shortsmith.reference import own
    from shortsmith.reference.gemini import FakeAnalyser

    done = _run(tmp_path, fixture_clip, "A short about nothing.")
    own.SelfInventory(FakeAnalyser([_answer_text()])).run(done)
    table = own.summary(done, tmp_path / "inventory")
    assert table is not None and table.comparison is not None
    row = next(r for r in table.comparison.rows if r.name.startswith("match share"))
    assert row.plan == "0.36"  # the fake plan: 4 of 11 beats


# --- compare_plan ---------------------------------------------------------------------------


def test_compare_plan_replans_once_without_examples_and_prints_both_shares(
    tmp_path: Path, fixture_clip: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    done = _run(tmp_path, fixture_clip, "Topic: science\nA short about the sun.")
    calls: list[int] = []

    class Counting(FakePlanner):
        def plan_picture(self, request, *, feedback=None):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN202
            calls.append(len(request.examples))
            return super().plan_picture(request, feedback=feedback)

    code = compare_cli.main(
        [str(done.path), "--dir", str(tmp_path / "inventory")], planner=Counting(), specs=SPECS
    )
    assert code == 0
    assert calls == [0]  # one call, and it carried no examples
    out = capsys.readouterr().out
    assert "with examples (bbbbbbbbbbb, aaaaaaaaaaa): 0.36 (4 of 11 beats)" in out
    assert "without examples: 0.36 (4 of 11 beats)" in out
    before = PicturePlan.model_validate_json((done.work_dir / "plan.json").read_text("utf-8"))
    assert examples.plan_match(before) == (4, 11)  # the job's own plan is left as it was
