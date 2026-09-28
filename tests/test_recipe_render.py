"""The render side of ticket 059: the `stacked` split (two pictures top and bottom, the title
band between them, for `vishva`) and the fixed title strip `fastfacts` keeps at the top of
the frame for the whole short, judged by T12 like the other overlays."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith import fixture, render
from shortsmith.contracts import TitleStripSpec
from shortsmith.qa import technical
from tests.test_render import (
    _captions,  # pyright: ignore[reportPrivateUsage]
    _plan,  # pyright: ignore[reportPrivateUsage]
    _two_panes,  # pyright: ignore[reportPrivateUsage]
)

VISHVA = render.style_numbers("vishva")
FASTFACTS = render.style_numbers("fastfacts")
EXPLAINER = render.style_numbers("explainer")


def test_the_stacked_split_puts_one_picture_over_the_other_with_the_title_between() -> None:
    piece = render.split_spec("Alpha versus Beta", _two_panes(), None, numbers=VISHVA,
                              pip_top=960)  # fmt: skip
    top, bottom = piece.panes
    border = VISHVA.broll.card_border_px
    inner = piece.width - 2 * border
    assert top.pane_width == bottom.pane_width == pytest.approx(inner)
    assert top.left == bottom.left == border
    assert top.top == border
    assert piece.title_top == pytest.approx(top.top + top.pane_height)
    assert bottom.top == pytest.approx(piece.title_top + piece.title_px)
    assert bottom.top + bottom.pane_height + border == pytest.approx(piece.height)
    assert top.pane_height == pytest.approx(bottom.pane_height)
    # a picture, not a letterbox strip: wider than tall, but under three to one
    image_h = top.pane_height - piece.label_px
    assert 1.0 < top.pane_width / image_h < 3.0
    # the badge stays out of the top zone; the card ends above the style's card limit
    assert piece.badge is None or piece.badge.top >= render.SAFE_TOP_PX
    tilt = render._tilt_extent(piece.width, piece.height, piece.rotate_deg)  # pyright: ignore[reportPrivateUsage]
    centre = piece.top + piece.height / 2
    overhang = render.SPLIT_BADGE_DIAMETER * render.SPLIT_BADGE_DROP
    assert centre - tilt >= render.SAFE_TOP_PX + overhang - 1e-6
    assert render.split_bottom(piece) <= VISHVA.broll.card_max_bottom_y + 1e-6


def test_the_side_split_keeps_its_title_band_along_the_bottom() -> None:
    piece = render.split_spec("Alpha versus Beta", _two_panes(), None, numbers=EXPLAINER,
                              pip_top=960)  # fmt: skip
    assert piece.title_top == pytest.approx(piece.height - piece.title_px)
    left, right = piece.panes
    assert left.top == right.top and right.left > left.left


def test_the_title_strip_is_fitted_inside_the_safe_area_from_the_style_row() -> None:
    row = FASTFACTS.title_strip
    assert row is not None
    strip = render.title_strip_spec("Why cheese exists", until_frame=150, numbers=FASTFACTS)
    assert (strip.top, strip.height) == (row.top_y, row.height_px)
    assert strip.left == render.SAFE_LEFT
    assert strip.left + strip.width == render.WIDTH - render.SAFE_RIGHT_PX
    assert (strip.fill, strip.ink, strip.slide_s) == (row.fill, row.ink, row.duration_s)
    assert strip.font_px == row.size_px and strip.until_frame == 150
    assert not technical.zone_hits(strip.left, strip.top, strip.width, strip.height)
    words = "Extraordinarily unbelievable gigantic prehistoric megastructures"
    long = render.title_strip_spec(words, until_frame=150, numbers=FASTFACTS)
    assert row.min_size_px <= long.font_px < row.size_px


def test_build_spec_draws_the_plans_title_strip_until_the_finale() -> None:
    plan = _plan().model_copy(update={"title_strip": "A short about nothing"})
    spec = render.build_spec(plan, _captions(plan), presenter=Path("work/cut.mp4"),
                             source_size=(fixture.WIDTH, fixture.HEIGHT),
                             duration_s=fixture.DURATION_S, numbers=FASTFACTS)  # fmt: skip
    assert spec.title_strip is not None
    assert spec.title_strip.text == "A short about nothing"
    finale = next(b for b in spec.beats if b.id == plan.finale.beat_id)
    assert spec.title_strip.until_frame == finale.start_frame
    plain = render.build_spec(plan, _captions(plan), presenter=Path("work/cut.mp4"),
                              source_size=(fixture.WIDTH, fixture.HEIGHT),
                              duration_s=fixture.DURATION_S, numbers=EXPLAINER)  # fmt: skip
    assert plain.title_strip is None


def test_a_text_pop_is_kept_off_the_title_strip() -> None:
    from shortsmith.contracts import TextPop

    plan = _plan()
    beats = [b.model_copy(update={"text_pops": [TextPop(text="THIS", word=2, x=50.0, y=16.0)]})
             if b.id == "b03" else b for b in plan.beats]  # fmt: skip
    plan = plan.model_copy(update={"beats": beats, "title_strip": "A short about nothing"})
    spec = render.build_spec(plan, _captions(plan), presenter=Path("work/cut.mp4"),
                             source_size=(fixture.WIDTH, fixture.HEIGHT),
                             duration_s=fixture.DURATION_S, numbers=FASTFACTS)  # fmt: skip
    strip = spec.title_strip
    assert strip is not None
    (pop,) = next(b for b in spec.beats if b.id == "b03").text_pops
    assert pop.top >= strip.top + strip.height


def test_t12_judges_the_title_strip() -> None:
    plan = _plan().model_copy(update={"title_strip": "A short about nothing"})
    spec = render.build_spec(plan, _captions(plan), presenter=Path("work/cut.mp4"),
                             source_size=(fixture.WIDTH, fixture.HEIGHT),
                             duration_s=fixture.DURATION_S, numbers=FASTFACTS)  # fmt: skip
    passed = technical.t12(spec)
    assert passed.passed and "1 title strip" in passed.detail
    assert spec.title_strip is not None
    high: TitleStripSpec = spec.title_strip.model_copy(update={"top": 200.0})
    failed = technical.t12(spec.model_copy(update={"title_strip": high}))
    assert not failed.passed and "title strip" in failed.detail and "top zone" in failed.detail
