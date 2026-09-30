"""Split cards keep faces clear (ticket 105; run05 b16, operator finding 2, 30 Sep 2026).

Run05's stacked split cropped both portraits at the centre (`objectFit: cover`, no
`objectPosition`), so the top portrait lost its face and the title strip ran along it.
Here every pane's face is found with the 3.3 detector and the pane is framed so the face
sits at the style's `split.face_y` of the picture; the title strip goes where it misses
every face (the seam, the bottom or the top of the card), shrinking if none fits, and is
never drawn across a face; a stamp on a split moves off the faces as it does on a card.
"""

from __future__ import annotations

import pytest

from shortsmith import render
from shortsmith.contracts import FaceBox, SplitPane, SplitSpec

VISHVA = render.style_numbers("vishva")  # stacked, as run05
EXPLAINER = render.style_numbers("explainer")  # side by side
PORTRAIT = (623, 800)  # run05 b16's first pane

Box = tuple[float, float, float, float]  # left, top, right, bottom


def _items(size: tuple[int, int] = PORTRAIT) -> list[render.ItemSource]:
    return [
        render.ItemSource(text=t, card=render.CardSource(src=f"{t}.png", width=size[0],
                                                         height=size[1]))  # fmt: skip
        for t in ("पहली शादी", "लास्ट शादी")
    ]


def _split(numbers: render.StyleNumbers, face: FaceBox | None,
           size: tuple[int, int] = PORTRAIT) -> SplitSpec:  # fmt: skip
    return render.split_spec("पहली शादी 20 साल | लास्ट शादी 65 साल", _items(size), None,
                             numbers=numbers, pip_top=960, face_of=lambda _src: face)  # fmt: skip


def _image_h(piece: SplitSpec, pane: SplitPane) -> float:
    return pane.pane_height - piece.label_px


def _meet(a: Box, b: Box) -> bool:
    eps = 1e-6
    return a[0] < b[2] - eps and b[0] < a[2] - eps and a[1] < b[3] - eps and b[1] < a[3] - eps


def _strip(piece: SplitSpec) -> Box:
    return (0.0, piece.title_top, piece.width, piece.title_top + piece.title_px)


def test_the_face_row_is_a_style_number() -> None:
    for name in ("explainer", "fastfacts", "footage", "vishva", "hitech"):
        broll = render.style_numbers(name).broll
        assert 0.0 < broll.split_face_y <= 1 / 3, name
        assert 0.0 <= broll.split_faceless_y < 0.5, name


@pytest.mark.parametrize("numbers", [VISHVA, EXPLAINER], ids=["stacked", "side"])
def test_a_portrait_with_a_face_near_the_top_keeps_the_face_inside_the_pane(
    numbers: render.StyleNumbers,
) -> None:
    face = FaceBox(left=250, top=40, width=130, height=160)  # a head near the top edge
    piece = _split(numbers, face)
    for pane in piece.panes:
        assert pane.face_box is not None
        left, top, right, bottom = pane.face_box
        # inside the pane's picture (card pixels), the face in its upper part
        assert pane.left - 1e-6 <= left and right <= pane.left + pane.pane_width + 1e-6
        assert pane.top - 1e-6 <= top and bottom <= pane.top + _image_h(piece, pane) + 1e-6
        centre = ((top + bottom) / 2 - pane.top) / _image_h(piece, pane)
        assert centre <= 0.5
        assert 0.0 <= pane.focus_x <= 1.0 and 0.0 <= pane.focus_y <= 1.0
    # run05's centre crop would have cut this head off the top of the pane
    assert piece.panes[0].focus_y < 0.5


def test_a_pane_with_no_face_found_frames_the_top_where_a_head_is() -> None:
    # run05 b16's second portrait: a seated king, his turned head 15 % down the picture,
    # which the Haar cascade misses; a split pane is a portrait (5.2), so it shows the top
    piece = _split(VISHVA, None)
    faceless = VISHVA.broll.split_faceless_y
    assert 0.0 <= faceless < 0.5
    assert all((p.focus_x, p.focus_y) == (0.5, faceless) and p.face_box is None
               for p in piece.panes)  # fmt: skip


def test_no_detector_keeps_the_centre_crop() -> None:
    piece = render.split_spec("Alpha versus Beta", _items(), None, numbers=VISHVA, pip_top=960)
    assert all((p.focus_x, p.focus_y) == (0.5, 0.5) for p in piece.panes)


@pytest.mark.parametrize("numbers", [VISHVA, EXPLAINER], ids=["stacked", "side"])
@pytest.mark.parametrize(
    ("face", "size"),
    [
        (FaceBox(left=250, top=40, width=130, height=160), PORTRAIT),  # near the top
        (FaceBox(left=240, top=330, width=140, height=150), PORTRAIT),  # the middle
        (FaceBox(left=250, top=600, width=130, height=180), PORTRAIT),  # near the bottom
        (FaceBox(left=60, top=40, width=500, height=720), PORTRAIT),  # the whole picture
        (FaceBox(left=100, top=10, width=780, height=240), (1000, 260)),  # a wide strip
    ],
    ids=["top", "middle", "bottom", "huge", "wide"],
)
def test_the_title_strip_never_crosses_a_face(
    numbers: render.StyleNumbers, face: FaceBox, size: tuple[int, int]
) -> None:
    piece = _split(numbers, face, size)
    faces = [p.face_box for p in piece.panes if p.face_box is not None]
    assert faces
    if piece.title_px > 0:
        assert not any(_meet(_strip(piece), f) for f in faces), (piece.title_top, faces)
    else:
        assert piece.title_words == []  # no room anywhere: the strip is left off


def test_a_huge_face_shrinks_the_strip_before_it_crosses_it() -> None:
    normal = _split(VISHVA, FaceBox(left=250, top=40, width=130, height=160))
    assert normal.title_px == render.SPLIT_TITLE_PX
    huge = _split(VISHVA, FaceBox(left=60, top=40, width=500, height=720))
    assert huge.title_px < render.SPLIT_TITLE_PX


def test_a_stamp_on_a_split_moves_off_the_faces() -> None:
    piece = _split(VISHVA, FaceBox(left=240, top=330, width=140, height=150))
    stamp = render.stamp_spec("KING", numbers=VISHVA)
    faces = render.split_face_boxes(piece)
    assert faces
    # put the stamp right over the first face, as a landed stamp might
    face, _pane = faces[0]
    over = stamp.model_copy(update={"top": face.top + face.height / 2 - stamp.height / 2})
    assert render.stamp_box(over).overlaps(face)
    moved, cleared = render.stamp_off_split(over, piece, numbers=VISHVA)
    assert cleared
    assert not any(render.stamp_box(moved).overlaps(f) for f, _ in faces)
