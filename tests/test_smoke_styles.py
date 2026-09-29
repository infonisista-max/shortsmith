"""The smoke walk under each opt-in style (048 hitech, 061 text pops, 062 stickers, 063
bubbles), split from `test_smoke.py` so each file stays well under the 8-minute test
chunk: every test here is a full real-engine render."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith import fixture, render, smoke, styles
from shortsmith.contracts import PicturePlan, RenderSpec
from shortsmith.jobs import load
from shortsmith.qa import technical


def test_run_smoke_renders_the_hitech_draft_end_to_end(tmp_path: Path) -> None:
    """048 (1.4, 9.2, 9.4): the fixture renders under the `hitech` draft with every
    fake: the job carries the draft's name, the render spec carries its palette,
    typography and four-transition subset with `wipe` on a beat, T1-T13 pass, and the
    upload form's resolution of the word still redirects to explainer with the notice."""
    result = smoke.run_smoke(tmp_path, style="hitech")
    job = load(result.job_dir)
    assert job.status == "delivered"
    assert job.record.style == "hitech" and job.record.style_note == "hitech"
    specs = styles.load_all(render.registry())
    hitech = specs["hitech"]
    assert styles.resolve("hitech", specs) == styles.Resolution(
        name="explainer", note="hitech", notice="hitech not available yet, using explainer"
    )
    spec = RenderSpec.model_validate_json((job.work_dir / "render_spec.json").read_text("utf-8"))
    assert spec.palette == hitech.palette
    assert spec.caption_style == hitech.caption_style()
    assert spec.transitions.enabled == ["cut", "fade", "wipe", "zoom"]
    enters = {b.enter for b in spec.beats}
    assert "wipe" in enters and enters == {"cut", "fade", "wipe", "zoom"}
    assert spec.pip.ring_color == hitech.pip.ring_color
    stamped = [b.stamp for b in spec.beats if b.stamp is not None]
    assert stamped and all(s.color == "#22D3EE" for s in stamped)
    report = technical.load_report(job)
    assert report is not None and report.passed
    assert [c.name for c in report.checks] == list(technical.CHECK_ORDER)
    assert all(c.status == "pass" for c in report.checks)
    assert "style hitech" in result.summary and "T13 pass" in result.summary


def test_run_smoke_renders_one_text_pop_under_the_pops_style(tmp_path: Path) -> None:
    """061: under the explainer copy with text pops on, the fake plan's b03 carries one
    pop landing on "this" (1.2 s), the render spec draws it clear of the reserved
    zones and the presenter's face, T1-T13 pass with T12 counting it, and the summary
    says so; the plain walk draws none."""
    result = smoke.run_smoke(tmp_path, text_pops=True)
    job = load(result.job_dir)
    assert job.status == "delivered"
    plan = PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))
    (pop,) = next(b for b in plan.beats if b.id == "b03").text_pops
    assert (pop.text, pop.word, pop.at_s) == ("THIS", 2, 1.2)
    spec = RenderSpec.model_validate_json((job.work_dir / "render_spec.json").read_text("utf-8"))
    b03 = next(b for b in spec.beats if b.id == "b03")
    (placed,) = b03.text_pops
    assert b03.mode == "full" and placed.text == "THIS" and placed.at_s == 0.2
    assert technical.zone_hits(placed.left, placed.top, placed.width, placed.height) == []
    measured = job.record.presenter
    assert measured is not None
    face = render.presenter_face_box(measured.face)
    box = render.Box(placed.left, placed.top, placed.width, placed.height)
    assert not box.overlaps(face)
    report = technical.load_report(job)
    assert report is not None and report.passed
    assert "1 text pop" in next(c.detail for c in report.checks if c.name == "T12")
    assert "text pops 1" in result.summary and "T13 pass" in result.summary
    noted = job.log_path.read_text(encoding="utf-8").splitlines()
    pop_lines = [line for line in noted if "text pop:" in line]
    assert not any("dropped" in line for line in pop_lines), pop_lines


def test_run_smoke_fetches_and_renders_one_sticker_under_the_stickers_style(
    tmp_path: Path,
) -> None:
    """062: under the explainer copy with stickers on, the fake plan's b01 carries the
    light bulb landing on "there", fetched through the fake fetcher into a cache under
    the smoke root (the second use would be a hit) and copied into the job; the render
    spec draws it above the PIP circle; T1-T13 pass with T12 counting it; the rights log
    and credits carry it; the summary says so."""
    result = smoke.run_smoke(tmp_path, stickers_on=True)
    job = load(result.job_dir)
    assert job.status == "delivered"
    plan = PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))
    (sticker,) = next(b for b in plan.beats if b.id == "b01").stickers
    assert (sticker.intent, sticker.name) == ("idea", "Light bulb")
    assert (tmp_path / "stickers" / "light_bulb_3d.png").is_file(), "the cache holds the PNG"
    spec = RenderSpec.model_validate_json((job.work_dir / "render_spec.json").read_text("utf-8"))
    (placed,) = next(b for b in spec.beats if b.id == "b01").stickers
    assert placed.top + placed.size + render.STICKER_GAP_PX == pytest.approx(spec.pip.top)
    report = technical.load_report(job)
    assert report is not None and report.passed
    assert "1 sticker" in next(c.detail for c in report.checks if c.name == "T12")
    assert "stickers 1" in result.summary and "bubbles 0" in result.summary
    assert "Fluent Emoji by Microsoft, MIT License" in (job.out_dir / "credits.md").read_text(
        "utf-8"
    )


def test_run_smoke_renders_the_dialogue_pair_under_the_bubbles_style(tmp_path: Path) -> None:
    """063: under the explainer copy with bubbles on, the fake plan's b04 carries a
    dialogue pair landing at the beat's start and the fixture-scaled gap later, the
    render spec draws both clear of the reserved zones, the circle, the stamp and each
    other with the tail tips on their anchors, T1-T13 pass with T12 counting them,
    job.log names each bubble's source words, and the summary says so; the plain walk
    draws none."""
    result = smoke.run_smoke(tmp_path, bubbles=True)
    job = load(result.job_dir)
    assert job.status == "delivered"
    plan = PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))
    speech, thought = next(b for b in plan.beats if b.id == "b04").bubbles
    gap = fixture.SMOKE_BUBBLE["dialogue_gap_min_s"]
    assert (speech.shape, speech.at_s) == ("speech", 1.5)
    assert (thought.shape, thought.at_s) == ("thought", 1.5 + gap)
    spec = RenderSpec.model_validate_json((job.work_dir / "render_spec.json").read_text("utf-8"))
    b04 = next(b for b in spec.beats if b.id == "b04")
    first, second = b04.bubbles
    assert (first.at_s, second.at_s) == (0.0, gap)
    assert (first.tip_x, first.tip_y) == (19.4 / 100 * render.WIDTH, 0.5 * render.HEIGHT)
    circle = render.Box(spec.pip.left, spec.pip.top, spec.pip.diameter, spec.pip.diameter)
    for bubble in (first, second):
        body = render.Box(bubble.left, bubble.top, bubble.width, bubble.height)
        assert technical.zone_hits(bubble.left, bubble.top, bubble.width, bubble.height) == []
        assert not body.overlaps(circle)
    report = technical.load_report(job)
    assert report is not None and report.passed
    assert "2 bubbles" in next(c.detail for c in report.checks if c.name == "T12")
    assert "bubbles 2" in result.summary and "text pops 0" in result.summary
    assert "T13 pass" in result.summary
    noted = job.log_path.read_text(encoding="utf-8").splitlines()
    bubble_lines = [line for line in noted if "bubble: " in line]
    hello = "'Hello there?' from words 0-1 'hello there'"
    sourced = [line for line in bubble_lines if hello in line]
    assert sourced, bubble_lines
    assert not any("dropped" in line for line in bubble_lines), bubble_lines
