"""Ticket 067: one definition of the 6.2/6.3 safe area, and caption lines laid out in
the safe band (x 60-940, centre 500) instead of centred on the frame, where a 960 px
line reached into the right rail (run04 T12, pages 3 and 56)."""

from __future__ import annotations

import random
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from shortsmith import captions, contact_sheet, infographics, render, safe_area, styles
from shortsmith.captions import LayoutError
from shortsmith.contracts import CaptionPage, Word
from shortsmith.qa import technical
from shortsmith.styles import StyleError, StyleSpec

REGISTRY = render.registry()
SRC = Path(__file__).resolve().parents[1] / "src" / "shortsmith"
EPS = 1e-6

# Run04 (job 20260928-140620-f774e1, vishva): the two pages T12 flagged, as text, word
# times and the keyword flag (no media).
PAGE_3 = [
    ("प्राइम", 2.30, 2.56), ("मिनिस्टर", 2.56, 2.88), ("कौन", 2.88, 3.06), ("है", 3.06, 3.50),
]  # fmt: skip
PAGE_3_KEYWORD = 2
PAGE_56 = [
    ("abduct", 54.32, 54.66), ("कर", 54.66, 54.92), ("लिया", 54.92, 55.14), ("था", 55.14, 55.28),
]  # fmt: skip
PAGE_56_KEYWORD = 0


@pytest.fixture(scope="module")
def specs() -> dict[str, StyleSpec]:
    return styles.load_all(REGISTRY)


def _words(rows: list[tuple[str, float, float]]) -> list[Word]:
    return [Word(text=t, start=s, end=e, segment=0) for t, s, e in rows]


def _layout(spec: StyleSpec, words: list[Word], keywords: list[int]) -> list[CaptionPage]:
    return captions.page(words, keywords, captions.numbers_for(spec), spec.caption_style())


def _inside_band(pages: list[CaptionPage]) -> None:
    for page in pages:
        for box in page.words:
            assert box.x >= safe_area.BAND_LEFT - EPS, (page.index, box.text, box.x)
            assert box.x + box.width <= safe_area.BAND_RIGHT + EPS, (
                page.index, box.text, box.x + box.width,
            )  # fmt: skip


# --- the one definition ----------------------------------------------------------------


def test_the_band_is_derived_from_the_frame_the_margin_and_the_rail() -> None:
    assert (safe_area.WIDTH, safe_area.HEIGHT) == (1080, 1920)
    assert (safe_area.SAFE_LEFT, safe_area.SAFE_RIGHT_PX) == (60, 140)
    assert (safe_area.SAFE_TOP_PX, safe_area.SAFE_BOTTOM_PX) == (250, 320)
    assert (safe_area.BAND_LEFT, safe_area.BAND_RIGHT) == (60, 940)
    assert (safe_area.BAND_WIDTH, safe_area.BAND_CENTRE) == (880, 500)


def test_every_consumer_uses_the_safe_area_values() -> None:
    for module in (render, infographics):
        assert module.SAFE_LEFT == safe_area.SAFE_LEFT, module.__name__
        assert module.SAFE_RIGHT_PX == safe_area.SAFE_RIGHT_PX, module.__name__
        assert module.SAFE_TOP_PX == safe_area.SAFE_TOP_PX, module.__name__
    assert render.SAFE_BOTTOM_PX == safe_area.SAFE_BOTTOM_PX
    for module in (technical, contact_sheet):
        assert module.SAFE_TOP_PX == safe_area.SAFE_TOP_PX, module.__name__
        assert module.SAFE_BOTTOM_PX == safe_area.SAFE_BOTTOM_PX, module.__name__
        assert module.SAFE_RIGHT_PX == safe_area.SAFE_RIGHT_PX, module.__name__
    assert captions.BAND_CENTRE == safe_area.BAND_CENTRE


def test_no_module_but_safe_area_defines_a_safe_area_number() -> None:
    definition = re.compile(r"^\s*(?:SAFE_(?:LEFT|RIGHT|TOP|BOTTOM)\w*\s*,?\s*)+=", re.MULTILINE)
    offenders = [
        f"{path.relative_to(SRC)}: {match.group(0).strip()}"
        for path in SRC.rglob("*.py")
        if path.name != "safe_area.py"
        for match in definition.finditer(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
    imports = re.compile(r"^(?:from|import) shortsmith", re.MULTILINE)
    assert not imports.search((SRC / "safe_area.py").read_text(encoding="utf-8"))


# --- the pager lays out in the band ----------------------------------------------------


@pytest.mark.parametrize(
    ("rows", "keyword"), [(PAGE_3, PAGE_3_KEYWORD), (PAGE_56, PAGE_56_KEYWORD)]
)
def test_run04_pages_3_and_56_stay_inside_the_band(
    specs: dict[str, StyleSpec], rows: list[tuple[str, float, float]], keyword: int
) -> None:
    pages = _layout(specs["vishva"], _words(rows), [keyword])
    assert [i for p in pages for i in p.word_indices] == list(range(len(rows)))
    _inside_band(pages)


def test_a_one_line_page_is_centred_on_the_band_centre(specs: dict[str, StyleSpec]) -> None:
    pages = _layout(specs["explainer"], _words([("two", 1.0, 1.2), ("words", 1.3, 1.5)]), [])
    (page,) = pages
    first, last = page.words[0], page.words[-1]
    assert (first.x + last.x + last.width) / 2 == pytest.approx(safe_area.BAND_CENTRE)


VOCABULARY = [
    "a", "is", "the", "India", "minister", "extraordinary", "responsibilities",
    "internationally", "abduct", "है", "था", "कर", "लिया", "कौन", "प्राइम", "मिनिस्टर",
    "प्रधानमंत्री", "अंतर्राष्ट्रीय", "स्वतंत्रता", "जिम्मेदारियां",
]  # fmt: skip


def test_every_page_the_pager_accepts_stays_inside_the_band_in_every_style(
    specs: dict[str, StyleSpec],
) -> None:
    rng = random.Random(67)
    checked = 0
    for spec in specs.values():
        for _ in range(60):
            texts = [rng.choice(VOCABULARY) for _ in range(rng.randint(2, 12))]
            words = _words([(t, 1.0 + 0.3 * i, 1.2 + 0.3 * i) for i, t in enumerate(texts)])
            keywords = rng.sample(range(len(words)), k=min(2, len(words)))
            try:
                pages = _layout(spec, words, keywords)
            except LayoutError:
                continue
            _inside_band(pages)
            checked += 1
    assert checked > 300


def test_a_single_word_wider_than_the_band_is_a_pager_bug(specs: dict[str, StyleSpec]) -> None:
    word = "pneumonoultramicroscopicsilicovolcanoconiosis"
    style = specs["explainer"].caption_style()
    assert captions.box_width(word, keyword=False, style=style) > safe_area.BAND_WIDTH
    with pytest.raises(LayoutError, match="wider than the safe band"):
        _layout(specs["explainer"], _words([(word, 1.0, 1.4)]), [])


# --- the style front matter ------------------------------------------------------------


def test_every_style_wraps_at_the_band_width(specs: dict[str, StyleSpec]) -> None:
    for spec in specs.values():
        assert spec.captions.max_width_px == 880, spec.name


def test_a_caption_width_over_the_band_fails_the_loader_naming_the_style(
    tmp_path: Path,
) -> None:
    target = tmp_path / "styles"
    shutil.copytree(styles.STYLES_DIR, target)
    path = target / "vishva.md"
    front, body = styles.split_front_matter(path.read_text(encoding="utf-8"))
    captions_front: dict[str, Any] = front["captions"]
    captions_front["max_width_px"] = 960
    path.write_text(f"---\n{yaml.safe_dump(front, sort_keys=False)}---\n{body}", encoding="utf-8")
    with pytest.raises(StyleError, match=r"vishva: captions\.max_width_px 960 .*880"):
        styles.load_all(REGISTRY, styles_dir=target)
