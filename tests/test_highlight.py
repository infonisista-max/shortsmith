"""078: the article highlighter - a marker sweeps across the key sentence of an owner's
uploaded article screenshot, on the spoken words.

The plan (`Beat.highlight`: the screenshot's asset id, the sentence to find, the transcript
words that say it), the grammar (owner references only, the beat shows the screenshot,
the style's cap, the landing written from the words), the line finder (one vision call
through the judge model, its ledger row, the cache per asset + sentence, the fake), the
sourcing step (a found highlight recorded on the manifest; no boxes, no finder or a beat
that does not show the screenshot drops it with a job.log line), the render spec (the
screenshot as a straight card pushing in toward the lines, the marker lines swept one
after another from the first word to the last), one real Remotion render of a drawn
screenshot, the styles' row and cap, the fake planner, the prompt and the analyser's
label set. No network, no key."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest
from anthropic.types import Message
from PIL import Image, ImageDraw
from pydantic import SecretStr, ValidationError

from shortsmith import assets, captions, ffmpeg, fixture, grammar, jobs, reference, render, styles
from shortsmith.assets import lines as lines_module
from shortsmith.assets.lines import (
    FakeLineFinder,
    LineError,
    VisionLineFinder,
    find_highlights,
    parse_lines,
)
from shortsmith.contracts import (
    AssetManifest,
    BedQuery,
    Constraints,
    Highlight,
    HighlightRecord,
    LineBox,
    PicturePlan,
    PlanReference,
    PlanRequest,
    PlanStyle,
    ReferenceRecord,
    SoundStory,
    ValidatedPlan,
    Violation,
)
from shortsmith.ledger import BudgetExceeded, Caps, Ledger, Prices
from shortsmith.planner import FakePlanner, prompt
from shortsmith.planner.fake import FAKE_SENTENCE
from shortsmith.transcriber import FakeTranscriber

TRANSCRIPT = FakeTranscriber().transcribe(Path("unused.mp4"))
WORDS = TRANSCRIPT.words
SPECS = styles.load_all(render.registry())
EXPLAINER = SPECS["explainer"]
REF = "ref1"
SENTENCE = "Nothing happened here today"
# The drawn screenshot's two target lines, as fractions of the 1600 x 900 image.
LINE_BOXES = (
    LineBox(left=0.1, top=0.3, right=0.9, bottom=0.4),
    LineBox(left=0.1, top=0.5, right=0.9, bottom=0.6),
)
SCREENSHOT_SIZE = (1600, 900)
YELLOW = (255, 214, 10)  # the explainer's accent, the marker's colour


def _on(spec: styles.StyleSpec) -> styles.StyleSpec:
    return fixture.highlights_on(spec)


def _smoke_on() -> styles.StyleSpec:
    return _on(fixture.smoke_specs(SPECS)["explainer"])


def _request(*, caption: str = "article screenshot: the news report",
             spec: styles.StyleSpec | None = None) -> PlanRequest:  # fmt: skip
    spec = spec or _smoke_on()
    return PlanRequest(
        brief="Topic: a six-second synthetic clip.",
        style=PlanStyle(name=spec.name, numbers=spec.numbers(), prose=spec.prose),
        style_note="explainer",
        transcript=TRANSCRIPT,
        references=[PlanReference(id=REF, kind="image", caption=caption, width=1600, height=900)],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    )


def _plan(**kwargs: Any) -> PicturePlan:
    return FakePlanner().plan_picture(_request(**kwargs))


def _with_highlight(plan: PicturePlan, beat_id: str, highlight: Highlight | None) -> PicturePlan:
    return plan.model_copy(update={"beats": [
        b.model_copy(update={"highlight": highlight}) if b.id == beat_id else b for b in plan.beats
    ]})  # fmt: skip


Checked = grammar.PictureCheck | grammar.Violations


def _check(plan: PicturePlan, spec: styles.StyleSpec | None = None,
           references: tuple[str, ...] = (REF,)) -> Checked:  # fmt: skip
    return grammar.validate_picture(plan, TRANSCRIPT, spec or _smoke_on(), references=references)


def _lines(result: Checked) -> list[Violation]:
    assert isinstance(result, grammar.Violations), "the plan passed"
    return [v for v in result.items if "highlight" in v.message]


# --- the plan ------------------------------------------------------------------------------


def test_a_highlight_names_the_screenshot_the_sentence_and_its_words_in_order() -> None:
    lit = Highlight(asset_id=REF, sentence=SENTENCE, words=(0, 1))
    assert (lit.at_s, lit.end_s) == (None, None)
    with pytest.raises(ValidationError, match="before"):
        Highlight(asset_id=REF, sentence=SENTENCE, words=(3, 1))
    with pytest.raises(ValidationError):
        Highlight(asset_id=REF, sentence="", words=(0, 1))
    assert _plan(spec=_smoke_on()).beats[1].highlight is None  # a beat carries none by default


def test_a_line_box_is_a_non_empty_box_in_fractions_of_the_image() -> None:
    LineBox(left=0.0, top=0.0, right=1.0, bottom=1.0)
    with pytest.raises(ValidationError):
        LineBox(left=0.5, top=0.1, right=0.4, bottom=0.2)
    with pytest.raises(ValidationError):
        LineBox(left=0.1, top=0.1, right=1.2, bottom=0.2)


# --- the styles ----------------------------------------------------------------------------


def test_every_style_carries_the_highlight_cap_and_row() -> None:
    """0 in the four existing styles; the recipe footage (whose reference ATkSnL_CdLg
    sweeps a marker at 14 s) turns it on; vishva and fastfacts, whose references never
    do, keep it off. The marker is the style's accent at about 45 %."""
    caps = {name: spec.broll.highlights_max_per_60s for name, spec in SPECS.items()}
    assert caps == {"animated": 0, "educational": 0, "explainer": 0, "hitech": 0,
                    "fastfacts": 0, "footage": 2, "vishva": 0}  # fmt: skip
    for spec in SPECS.values():
        row = spec.broll.motion["highlight"]
        assert row["color"] == spec.palette.accent, spec.name
        assert 0.3 <= float(row["opacity"]) <= 0.6, spec.name
        assert float(row["push_to"]) > 1.0 and float(row["pad_px"]) >= 0, spec.name
    numbers = render.broll_numbers(EXPLAINER)
    assert (numbers.highlight_color, numbers.highlight_opacity) == ("#FFD60A", 0.45)


def test_a_spec_without_the_highlight_row_or_cap_fails_to_load(tmp_path: Path) -> None:
    source = (Path(styles.__file__).resolve().parents[2] / "styles" / "explainer.md").read_text(
        encoding="utf-8"
    )
    no_cap = source.replace("  highlights_max_per_60s: 0", "", 1)
    assert no_cap != source
    (tmp_path / "explainer.md").write_text(no_cap, encoding="utf-8")
    with pytest.raises(styles.StyleError, match="highlights_max_per_60s"):
        styles.load_all(render.registry(), styles_dir=tmp_path)
    spec = EXPLAINER.model_copy(deep=True)
    del spec.broll.motion["highlight"]
    with pytest.raises(styles.StyleError, match="highlight"):
        render.broll_numbers(spec)


def test_the_highlight_is_a_registered_component_the_analyser_can_name() -> None:
    """The registry exports `highlight`, and the reference analyser's label set (the
    registry with each component's note from docs/components.md) names it, so a new
    reference card says `highlight` instead of `unregistered`."""
    assert "highlight" in render.registry()
    assert "marker" in reference.component_meanings()["highlight"]
    text = reference.build_prompt(render.registry())
    assert "- `highlight`: " in text


# --- the grammar ---------------------------------------------------------------------------


def test_the_fake_plans_highlight_passes_and_lands_on_its_words() -> None:
    """b01 (0-0.5 s) shows the screenshot and sweeps words 0-1 ("hello" 0.2 s, "there"
    ending 0.5 s): the grammar writes both ends on the output timeline."""
    result = _check(_plan())
    assert isinstance(result, grammar.PictureCheck), result
    lit = result.picture.beats[0].highlight
    assert lit is not None and lit.asset_id == REF and lit.sentence == FAKE_SENTENCE
    assert lit.at_s == pytest.approx(WORDS[0].start)
    assert lit.end_s == pytest.approx(WORDS[1].end)


def test_a_highlight_counts_as_a_change_on_screen_at_its_landing() -> None:
    beat = _plan().beats[0].model_copy(update={"highlight": Highlight(
        asset_id=REF, sentence=SENTENCE, words=(0, 1), at_s=0.2, end_s=0.5)})  # fmt: skip
    assert 0.2 in grammar.change_times(beat)


def test_a_highlight_on_a_picture_that_is_not_the_owners_fails_naming_the_beat() -> None:
    plan = _plan()
    searched = plan.model_copy(update={"beats": [
        b.model_copy(update={"asset_id": "a1", "highlight": b.highlight.model_copy(
            update={"asset_id": "a1"})}) if b.id == "b01" and b.highlight else b
        for b in plan.beats
    ]})  # fmt: skip
    (found,) = _lines(_check(searched, references=()))
    assert found.beat_id == "b01" and found.rule == "4.1"
    assert "owner" in found.message


def test_a_highlight_on_another_asset_than_the_beat_shows_fails() -> None:
    plan = _plan()
    other = plan.model_copy(update={"beats": [
        b.model_copy(update={"asset_id": "a1"}) if b.id == "b01" else b for b in plan.beats
    ]})  # fmt: skip
    found = _lines(_check(other))
    assert any(v.beat_id == "b01" and "shows" in v.message for v in found)


def test_a_highlight_over_the_cap_fails_naming_the_beat() -> None:
    """The explainer keeps the cap at 0, so any highlight is over it."""
    (found,) = _lines(_check(_plan(), spec=fixture.smoke_specs(SPECS)["explainer"]))
    assert found.beat_id == "b01" and "highlights_max_per_60s" in found.message


def test_a_highlight_sits_only_on_a_photo_or_card_beat_with_the_picture_on_screen() -> None:
    lit = Highlight(asset_id=REF, sentence=SENTENCE, words=(2, 3))
    full = _with_highlight(_with_highlight(_plan(), "b01", None), "b03", lit)
    found = _lines(_check(full))
    assert any(v.beat_id == "b03" and "photo" in v.message for v in found)


def test_a_highlight_whose_words_the_beat_does_not_say_fails() -> None:
    late = _with_highlight(_plan(), "b01", Highlight(asset_id=REF, sentence=SENTENCE,
                                                        words=(4, 5)))  # fmt: skip
    found = _lines(_check(late))
    assert any(v.beat_id == "b01" and "word 4" in v.message for v in found)
    beyond = _with_highlight(_plan(), "b01", Highlight(asset_id=REF, sentence=SENTENCE,
                                                          words=(0, 40)))  # fmt: skip
    assert any("transcript has 12 words" in v.message for v in _lines(_check(beyond)))


# --- the line finder -----------------------------------------------------------------------


def _png(size: tuple[int, int] = (40, 30)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (250, 250, 250)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_the_fake_finder_answers_the_boxes_it_was_given_and_counts_its_calls() -> None:
    finder = FakeLineFinder({SENTENCE: LINE_BOXES})
    assert finder.find(_png(), SENTENCE) == list(LINE_BOXES)
    assert finder.find(_png(), "a sentence that is not there") == []
    assert finder.calls == 2 and FakeLineFinder().find(_png(), SENTENCE) == []


def test_the_reply_becomes_line_boxes_clamped_into_the_image() -> None:
    reply = ('Here: {"lines": [{"left": 0.1, "top": 0.3, "right": 0.9, "bottom": 0.4}, '
             '{"left": -0.2, "top": 0.5, "right": 1.3, "bottom": 0.6}, '
             '{"left": 0.5, "top": 0.7, "right": 0.5, "bottom": 0.8}]}')  # fmt: skip
    assert parse_lines(reply) == [
        LineBox(left=0.1, top=0.3, right=0.9, bottom=0.4),
        LineBox(left=0.0, top=0.5, right=1.0, bottom=0.6),
    ]  # the empty third box is dropped
    assert parse_lines('{"lines": []}') == []
    with pytest.raises(LineError, match="JSON"):
        parse_lines("no boxes, sorry")


KEY = "sk-ant-test-not-real"
PRICES = Prices({"judge": {"input_tokens": 0.25, "output_tokens": 1.25}})


def _message(text: str, *, stop: str = "end_turn") -> Message:
    return Message.model_validate({
        "id": "msg_078", "type": "message", "role": "assistant",
        "model": "claude-haiku-4-5-20251001",
        "content": [{"type": "text", "text": text}], "stop_reason": stop,
        "stop_sequence": None, "usage": {"input_tokens": 900, "output_tokens": 60},
    })  # fmt: skip


@dataclass
class StubApi:
    replies: list[Message]
    requests: list[dict[str, Any]] = field(default_factory=lambda: [])

    def __call__(self, **params: Any) -> Message:
        self.requests.append(params)
        return self.replies.pop(0)


def _vision(api: StubApi, job: jobs.Job, *, hard: float | None = None) -> VisionLineFinder:
    book = Ledger(PRICES, Caps(per_job=None, hard=hard, per_day=500))
    return VisionLineFinder(lambda: book, api_key=SecretStr(KEY),
                            model="claude-haiku-4-5-20251001", create=api).bind(job)  # fmt: skip


def test_the_vision_finder_is_one_judge_call_with_the_image_and_one_ledger_row(
    tmp_path: Path,
) -> None:
    job = jobs.create(tmp_path, style="explainer", style_note="explainer")
    api = StubApi([_message('{"lines": [{"left": 0.1, "top": 0.3, "right": 0.9, "bottom": 0.4}]}')])
    found = _vision(api, job).find(_png(), SENTENCE)
    assert found == [LINE_BOXES[0]]
    (request,) = api.requests
    body = cast(dict[str, Any], json.loads(json.dumps(request)))
    assert body["model"] == "claude-haiku-4-5-20251001"
    content = body["messages"][0]["content"]
    assert SENTENCE in content[0]["text"]
    assert [b["type"] for b in content] == ["text", "image"]
    assert "line" in body["system"][0]["text"]
    (row,) = jobs.load(job.path).record.cost
    assert (row.step, row.provider) == ("sourcing", "judge")
    assert row.units == {"input_tokens": 900.0, "output_tokens": 60.0}


def test_the_vision_finder_checks_the_hard_cap_before_it_calls(tmp_path: Path) -> None:
    job = jobs.create(tmp_path, style="explainer", style_note="explainer")
    api = StubApi([_message('{"lines": []}')])
    with pytest.raises(BudgetExceeded):
        _vision(api, job, hard=0.0001).find(_png(), SENTENCE)
    assert api.requests == []


def test_a_refused_or_keyless_vision_finder_is_a_line_error(tmp_path: Path) -> None:
    job = jobs.create(tmp_path, style="explainer", style_note="explainer")
    with pytest.raises(LineError, match="refus"):
        _vision(StubApi([_message("", stop="refusal")]), job).find(_png(), SENTENCE)
    keyless = VisionLineFinder(lambda: Ledger(PRICES, Caps(per_job=None, hard=None, per_day=1)),
                               api_key=None).bind(job)  # fmt: skip
    with pytest.raises(LineError, match="ANTHROPIC_API_KEY"):
        keyless.find(_png(), SENTENCE)


# --- sourcing: the boxes found once per asset and sentence -----------------------------------


def _screenshot(path: Path) -> Path:
    """A 1600 x 900 white page with two dark text bars inside each target line box (the
    boxes' top and bottom tenths left white), so the marker's tint reads on white."""
    width, height = SCREENSHOT_SIZE
    image = Image.new("RGB", SCREENSHOT_SIZE, (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for box in LINE_BOXES:
        top, bottom = box.top * height, box.bottom * height
        pad = (bottom - top) * 0.3
        draw.rectangle((box.left * width, top + pad, box.right * width, bottom - pad),
                       fill=(20, 20, 20))  # fmt: skip
    draw.rectangle((160, 120, 900, 180), fill=(40, 40, 40))  # a headline off the target lines
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return path


def _reference(job_dir: Path) -> ReferenceRecord:
    _screenshot(job_dir / "input" / "refs" / "ref1.png")
    width, height = SCREENSHOT_SIZE
    return ReferenceRecord(id=REF, file="refs/ref1.png", kind="image",
                           caption="article screenshot: the news report",
                           original_name="news.png", width=width, height=height,
                           size_bytes=1000)  # fmt: skip


def _validated(plan: PicturePlan) -> ValidatedPlan:
    return ValidatedPlan(picture=plan, sound=SoundStory(
        prompt_version="t", theme="t", mood_curve=[], bed_query=BedQuery(theme="t", mood="t",
        energy=3), cues=[]))  # fmt: skip


def _checked_plan() -> PicturePlan:
    result = _check(_plan())
    assert isinstance(result, grammar.PictureCheck), result
    return result.picture


def _sourced(job_dir: Path, plan: PicturePlan) -> AssetManifest:
    (job_dir / "work").mkdir(parents=True, exist_ok=True)
    return assets.source_assets(
        _validated(plan), [_reference(job_dir)], "any", spec=EXPLAINER, job_dir=job_dir,
        sources={"web": assets.FakeImageSource("web")},
    )  # fmt: skip


def test_a_found_highlight_is_recorded_and_its_boxes_cached_per_asset_and_sentence(
    tmp_path: Path,
) -> None:
    plan = _checked_plan()
    manifest = _sourced(tmp_path, plan)
    finder = FakeLineFinder({FAKE_SENTENCE: LINE_BOXES})
    log: list[str] = []
    (record,) = find_highlights(plan, manifest, job_dir=tmp_path, finder=finder, log=log.append)
    assert record == HighlightRecord(beat_id="b01", asset_id=REF, sentence=FAKE_SENTENCE,
                                     lines=list(LINE_BOXES))  # fmt: skip
    assert finder.calls == 1
    assert any("highlight: b01" in line and "2 lines" in line for line in log)
    again = find_highlights(plan, manifest, job_dir=tmp_path, finder=finder, log=log.append)
    assert again == [record] and finder.calls == 1  # the cache answered


def test_a_finder_that_finds_no_boxes_drops_the_highlight_with_a_log_line(tmp_path: Path) -> None:
    plan = _checked_plan()
    manifest = _sourced(tmp_path, plan)
    log: list[str] = []
    assert find_highlights(plan, manifest, job_dir=tmp_path, finder=FakeLineFinder(),
                           log=log.append) == []  # fmt: skip
    assert any("highlight: b01" in line and "dropped" in line and "no line" in line
               for line in log)  # fmt: skip


def test_no_finder_or_a_beat_that_does_not_show_the_screenshot_drops_it(tmp_path: Path) -> None:
    plan = _checked_plan()
    manifest = _sourced(tmp_path, plan)
    log: list[str] = []
    assert find_highlights(plan, manifest, job_dir=tmp_path, finder=None, log=log.append) == []
    assert any("dropped" in line and "no line finder" in line for line in log)
    elsewhere = manifest.model_copy(update={"beats": [
        b.model_copy(update={"asset_id": "a2"}) if b.beat_id == "b01" else b
        for b in manifest.beats
    ]})  # fmt: skip
    log.clear()
    finder = FakeLineFinder({FAKE_SENTENCE: LINE_BOXES})
    assert find_highlights(plan, elsewhere, job_dir=tmp_path, finder=finder, log=log.append) == []
    assert finder.calls == 0 and any("does not show" in line for line in log)


def test_a_finder_error_drops_the_highlight_and_never_fails_the_step(tmp_path: Path) -> None:
    class Broken(FakeLineFinder):
        def find(self, image: bytes, sentence: str) -> list[LineBox]:
            raise LineError("the judge could not be reached")

    plan = _checked_plan()
    log: list[str] = []
    assert find_highlights(plan, _sourced(tmp_path, plan), job_dir=tmp_path, finder=Broken(),
                           log=log.append) == []  # fmt: skip
    assert any("could not be reached" in line for line in log)


def test_the_sourcing_step_puts_the_highlights_on_the_manifest(tmp_path: Path) -> None:
    job = jobs.create(tmp_path, style="explainer", style_note="explainer")
    plan = _checked_plan()
    ref = _reference(job.path)
    (job.input_dir / "refs.json").write_text(json.dumps([ref.model_dump()]), encoding="utf-8")
    (job.input_dir / "brief.md").write_text("Topic: nothing.", encoding="utf-8")
    (job.work_dir / "plan.validated.json").write_text(
        _validated(plan).model_dump_json(), encoding="utf-8"
    )
    step = assets.Sourcing(sources={"web": assets.FakeImageSource("web")}, order=("web",),
                           lines=FakeLineFinder({FAKE_SENTENCE: LINE_BOXES}))  # fmt: skip
    manifest = step.run(job, EXPLAINER)
    assert [h.beat_id for h in manifest.highlights] == ["b01"]
    assert assets.load_manifest(job.path) == manifest
    assert "highlight: b01" in (job.path / "job.log").read_text(encoding="utf-8")


def test_the_configured_finder_follows_the_relevance_judge() -> None:
    from shortsmith import config

    def settings(judge: str) -> config.Settings:
        return config.Settings(_env_file=None, relevance_judge=judge, anthropic_api_key=KEY)  # pyright: ignore[reportCallIssue, reportArgumentType]

    book = lambda: Ledger(PRICES, Caps(per_job=None, hard=None, per_day=1))  # noqa: E731
    assert assets.from_settings(settings("none"), ledger=book).lines is None
    assert isinstance(assets.from_settings(settings("fake"), ledger=book).lines, FakeLineFinder)
    real = assets.from_settings(settings("api"), ledger=book).lines
    assert isinstance(real, VisionLineFinder) and real.model == lines_module.DEFAULT_MODEL


# --- the render spec ------------------------------------------------------------------------


def _spec_for(job_dir: Path, plan: PicturePlan, manifest: AssetManifest):  # noqa: ANN202
    return render.build_spec(
        plan, captions.build(TRANSCRIPT, plan, EXPLAINER), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        numbers=render.numbers_for(EXPLAINER), manifest=manifest, job_dir=job_dir,
    )  # fmt: skip


def _highlighted(job_dir: Path) -> tuple[PicturePlan, AssetManifest]:
    plan = _checked_plan()
    manifest = _sourced(job_dir, plan)
    manifest.highlights = [HighlightRecord(beat_id="b01", asset_id=REF, sentence=FAKE_SENTENCE,
                                           lines=list(LINE_BOXES))]  # fmt: skip
    return plan, manifest


def test_the_screenshot_is_a_straight_card_pushing_in_toward_the_lines(tmp_path: Path) -> None:
    plan, manifest = _highlighted(tmp_path)
    beat = _spec_for(tmp_path, plan, manifest).beats[0]
    visual = beat.visual
    assert visual is not None and visual.treatment == "card" and visual.card is not None
    card = visual.card
    assert card.rotate_deg == 0 and (visual.zoom, visual.focus_x, visual.focus_y) == (1, 0.5, 0.5)
    assert (visual.scale_from, visual.scale_to) == (1.0, render.broll_numbers(EXPLAINER)
                                                    .highlight_push_to)  # fmt: skip
    # the push is about the lines' centre (both lines span y 0.3-0.6 of the image)
    centre_y = card.border_px + 0.45 * card.image_height
    assert card.origin_y == pytest.approx(centre_y / card.height)
    assert card.origin_x == pytest.approx(0.5)
    # at full push the card still ends above the circle and the style's limit
    limit = min(EXPLAINER.pip.top - render.PIP_GAP_PX, EXPLAINER.broll.card_max_bottom_y)
    assert render.card_bottom(visual) <= limit + 1e-6
    assert card.top >= 0


def test_the_marker_lines_sweep_one_after_another_from_the_first_word_to_the_last(
    tmp_path: Path,
) -> None:
    plan, manifest = _highlighted(tmp_path)
    spec = _spec_for(tmp_path, plan, manifest)
    beat = spec.beats[0]
    assert beat.visual is not None and beat.visual.card is not None
    card = beat.visual.card
    lit = card.highlight
    assert lit is not None and lit.color == "#FFD60A" and lit.opacity == pytest.approx(0.45)
    first, second = lit.lines
    pad = render.broll_numbers(EXPLAINER).highlight_pad_px
    assert first.left == pytest.approx(0.1 * card.image_width)
    assert first.width == pytest.approx(0.8 * card.image_width)
    assert first.top == pytest.approx(0.3 * card.image_height - pad)
    assert first.height == pytest.approx(0.1 * card.image_height + 2 * pad)
    # 078: the sweep starts on the first word (+-0.15 s) and is done by the beat's last frame
    assert abs(first.start_s - WORDS[0].start) <= 0.15
    assert first.end_s == pytest.approx(second.start_s)
    last_frame_s = (beat.end_frame - 1 - beat.start_frame) / spec.fps
    assert second.end_s <= last_frame_s + 1e-6
    assert first.end_s - first.start_s == pytest.approx(second.end_s - second.start_s)


def test_a_beat_with_no_recorded_highlight_is_drawn_as_before(tmp_path: Path) -> None:
    plan = _checked_plan()
    beat = _spec_for(tmp_path, plan, _sourced(tmp_path, plan)).beats[0]
    assert beat.visual is not None
    assert beat.visual.card is None or beat.visual.card.highlight is None


# --- one real render (Remotion) --------------------------------------------------------------


Frame = tuple[int, int, bytes]


def _pixel(frame: Frame, x: float, y: float) -> tuple[int, int, int]:
    width, _, data = frame
    i = 3 * (round(y) * width + round(x))
    return data[i], data[i + 1], data[i + 2]


def _on_screen(
    card: Any, visual: Any, frame: int, beat: Any, x: float, y: float
) -> tuple[float, float]:
    """A point of the card's image (image pixels) in composition pixels at `frame`: the
    card is pushed about its origin, linearly over the beat as `beatProgress` is."""
    last = max(beat.start_frame + 1, beat.end_frame - 1)
    p = min(max((frame - beat.start_frame) / (last - beat.start_frame), 0.0), 1.0)
    scale = visual.scale_from + (visual.scale_to - visual.scale_from) * p
    ox = card.left + card.origin_x * card.width
    oy = card.top + card.origin_y * card.height
    px = card.left + card.border_px + x
    py = card.top + card.border_px + y
    return ox + scale * (px - ox), oy + scale * (py - oy)


def test_a_drawn_screenshot_is_swept_line_by_line_under_the_circle_and_captions(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """078 end to end through Remotion on b01 (0-0.5 s, frames 0-14). At the first line's
    midpoint the marker tints its left half and not its right; on the beat's last frame
    both lines are tinted; the PIP circle and the caption pixels are those of the same
    render without the marker."""
    job = jobs.create(tmp_path, style="explainer", style_note="explainer")
    shutil.copyfile(fixture_clip, job.input_dir / "raw.mp4")
    plan, manifest = _highlighted(job.path)
    (job.work_dir / "plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    (job.work_dir / "captions.json").write_text(
        captions.build(TRANSCRIPT, plan, EXPLAINER).model_dump_json(), encoding="utf-8"
    )
    assets.write_manifest(job.path, manifest)
    render.cut_presenter(job)
    spec = render.spec_for_job(job).model_copy(update={"frames": 15})
    beat = spec.beats[0]
    assert beat.visual is not None and beat.visual.card is not None
    card, visual = beat.visual.card, beat.visual
    lit = card.highlight
    assert lit is not None
    unlit = visual.model_copy(update={"card": card.model_copy(update={"highlight": None})})
    plain = spec.model_copy(
        update={"beats": [beat.model_copy(update={"visual": unlit}), *spec.beats[1:]]}
    )

    def frames_of(which: Any, name: str) -> list[Frame]:
        out = job.work_dir / f"{name}.mp4"
        render.run_driver(which, spec_path=job.work_dir / f"{name}.json", out_path=out,
                          log_path=job.work_dir / f"{name}.log")  # fmt: skip
        return ffmpeg.frames_rgb(out, fps=30, width=1080, duration_s=0.5)

    marked, unmarked = frames_of(spec, "marked"), frames_of(plain, "plain")
    first, second = lit.lines
    # the white strip inside each line box, above its dark text bar
    white_y = LINE_BOXES[0].top * card.image_height + 0.1 * (0.1 * card.image_height)
    mid = round(((first.start_s + first.end_s) / 2) * spec.fps)

    def tinted(frames: list[Frame], index: int, line: Any, fx: float, y: float) -> bool:
        x, yy = _on_screen(card, visual, index, beat, line.left + fx * line.width, y)
        red, _, blue = _pixel(frames[index], x, yy)
        return blue < 200 and red > 200  # white under 45 % yellow is (255, 237, 145)

    assert tinted(marked, mid, first, 0.2, white_y)
    assert not tinted(marked, mid, first, 0.8, white_y)
    assert not tinted(unmarked, mid, first, 0.2, white_y)
    second_y = LINE_BOXES[1].top * card.image_height + 0.1 * (0.1 * card.image_height)
    for line, y in ((first, white_y), (second, second_y)):
        for fx in (0.1, 0.5, 0.9):
            assert tinted(marked, 14, line, fx, y), (line, fx)
    # the circle and the captions are untouched by the marker
    cx, cy = spec.pip.left + spec.pip.diameter / 2, spec.pip.top + spec.pip.diameter / 2
    band_top = styles.caption_block_top(spec.caption_style)
    for index in (mid, 14):
        for x, y in ((cx, cy), (cx - 60, cy + 40), (540, band_top + 60), (300, band_top + 100)):
            got, want = _pixel(marked[index], x, y), _pixel(unmarked[index], x, y)
            assert max(abs(a - b) for a, b in zip(got, want, strict=True)) <= 6, (index, x, y)


# --- the fake planner and the prompt ---------------------------------------------------------


def test_the_fake_planner_highlights_a_fixture_screenshot_only_where_allowed() -> None:
    lit = _plan().beats[0].highlight
    assert lit == Highlight(asset_id=REF, sentence=FAKE_SENTENCE, words=(0, 1))
    assert _plan().beats[0].asset_id == REF
    assert _plan(caption="my product").beats[0].highlight is None  # not a screenshot
    off = fixture.smoke_specs(SPECS)["explainer"]
    assert _plan(spec=off).beats[0].highlight is None  # the cap is 0


def test_the_v19_picture_prompt_says_when_to_highlight_and_never_a_fake_article() -> None:
    assert prompt.PROMPT_VERSION == "v19"
    text = prompt.build_prompt(_request(), "picture")
    for needle in (
        "`highlight`",
        "`broll.highlights_max_per_60s`",
        "only on an owner reference",
        "article or document screenshot",
        "never invent",
        "`words`",
    ):
        assert needle in text, needle
