"""assets, ticket 053: real people, no stock watermarks, slot floors, source notes.

Replayed from F1 (job 20260927-041728-656506): the candidate rows every search
returned are in `tests/fixtures/f1/candidates.json` (URLs and reported sizes only,
never an image). The step helpers are `tests.test_assets`'s."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from shortsmith import assets
from shortsmith.contracts import Beat, Candidate
from tests.test_assets import (
    SPEC,
    Scoring,
    Scripted,
    _beat,  # pyright: ignore[reportPrivateUsage]
    _candidates,  # pyright: ignore[reportPrivateUsage]
    _generating,  # pyright: ignore[reportPrivateUsage]
    _run,  # pyright: ignore[reportPrivateUsage]
)

F1 = json.loads((Path(__file__).parent / "fixtures" / "f1" / "candidates.json").read_text("utf-8"))
BABA = "Neem Karoli Baba portrait blanket"
PEXELS_STRANGER = "https://images.pexels.com/photos/30756218/pexels-photo-30756218.jpeg"
FINEART = (
    "https://images.fineartamerica.com/images/artworkimages/mediumlarge/3/"
    "neem-karoli-baba-portrait-neem-karoli-baba.jpg"
)


def _f1(source: str, query: str) -> list[Candidate]:
    return [Candidate.model_validate(row) for row in F1[f"{source}|{query}"]["candidates"]]


class Forbidding(Scripted):
    """F1's web source: worthpoint answers 403 to the download."""

    def fetch(self, candidate: Candidate, dest: Path) -> Path:
        if "worthpoint" in candidate.url:
            self.fetched.append(candidate.url)
            raise assets.SourceError(f"{candidate.url} could not be downloaded: 403 Forbidden")
        return super().fetch(candidate, dest)


def _named(i: int = 1, *, kind: str = "card", query: str = BABA,
           fallback: str = "Neem Karoli Baba") -> Beat:  # fmt: skip
    return _beat(i, "entity", kind=kind, query=query, fallback=fallback, depicts="named_entity")


def _f1_sources(*, web: Sequence[Candidate]) -> dict[str, Scripted]:
    return {
        "web": Forbidding("web", web),
        "commons": Scripted("commons", []),
        "openverse": Scripted("openverse", []),
        "pexels": Scripted("pexels", _f1("pexels", BABA)),
    }


# --- rule 1: a named person is never shown as a stranger --------------------------------


def test_a_named_entity_beat_never_takes_a_stock_library_picture(tmp_path: Path) -> None:
    """F1 showed a Pexels stranger (judged 3/3) as Neem Karoli Baba on four beats. The
    stock libraries are neither searched nor accepted for a named entity."""
    sources = _f1_sources(web=_f1("web", BABA))
    judge = Scoring({PEXELS_STRANGER: 3, FINEART: 2}, default=3)
    log: list[str] = []
    manifest = _run(tmp_path, [_named()], sources=dict(sources), judging=assets.Judging(judge, 40),
                    log=log)  # fmt: skip
    assert manifest.assets[0].source_url == FINEART
    assert manifest.assets[0].origin == "web"
    assert sources["pexels"].searches == 0
    assert all("pexels.com" not in a.source_url for a in manifest.assets)
    assert any("b01" in line and "pexels" in line and "not searched" in line for line in log)


def test_a_named_entity_nobody_has_a_picture_of_is_illustrated_never_a_stranger(
    tmp_path: Path,
) -> None:
    """Web 403s, Commons and Openverse empty, both queries -> rung 2 (the 5.5 stylised
    illustration), never the stock libraries."""
    web = [c for c in _f1("web", BABA) if "worthpoint" in c.url]
    sources = _f1_sources(web=web)
    judge = Scoring({}, default=3)
    generating = _generating()
    manifest = _run(tmp_path, [_named()], sources=dict(sources), judging=assets.Judging(judge, 40),
                    generating=generating)  # fmt: skip
    (beat,) = manifest.beats
    assert beat.fallback_rung == 2
    record = manifest.assets[0]
    assert record.origin == "generated" and record.generated is not None
    assert (record.generated.depicts, record.generated.render) == ("named_entity", "illustration")
    assert sources["pexels"].searches == 0
    assert sources["web"].searches == 2


def test_a_scene_beat_still_walks_the_whole_5_1_order(tmp_path: Path) -> None:
    """Rule 1 is about named entities only: a scene keeps Pexels and Pixabay (5.1)."""
    sources = _f1_sources(web=[])
    beat = _beat(1, "concept", query="elderly sadhu wrapped in a blanket", depicts="scene")
    manifest = _run(tmp_path, [beat], sources=dict(sources))
    assert manifest.assets[0].origin == "pexels"


# --- rule 2: name evidence first ----------------------------------------------------------

KOHLI = "Virat Kohli Kainchi Dham visit"
LANGIMG = next(c.url for c in _f1("web", KOHLI) if "langimg" in c.url)
WIX = next(c.url for c in _f1("web", KOHLI) if "wixstatic" in c.url)
YTIMG = next(c.url for c in _f1("web", KOHLI) if "ytimg" in c.url)


def test_name_words_come_from_the_beats_own_query() -> None:
    """The plan names its entities in the beat's capitalised query words, then in
    `query_fallback` when the query has none, and never in the stopwords."""
    assert assets.name_words(_named()) == frozenset({"neem", "karoli", "baba"})
    assert assets.name_words(_named(query=KOHLI)) == frozenset(
        {"virat", "kohli", "kainchi", "dham"}
    )
    assert assets.name_words(
        _named(query="Steve Jobs young 1970s India trip portrait", fallback="Steve Jobs portrait")
    ) == frozenset({"steve", "jobs", "india"})
    lower = _named(query="the baba in a blanket", fallback="Neem Karoli Baba")
    assert assets.name_words(lower) == frozenset({"neem", "karoli", "baba"})
    assert assets.name_words(_named(query="portrait", fallback="portrait")) == frozenset()


@pytest.mark.parametrize(
    ("url", "page_url", "evidenced"),
    [
        (LANGIMG, "", True),  # neem-karoli-baba-who-inspired-virat-kohli...kainchi-dham
        (WIX, "https://www.nomadznorth.com/post/9-lessons", False),  # the file name is a hash
        (YTIMG, "https://www.youtube.com/watch?v=PqBdutL3emo", False),
        ("https://cdn.example/x.jpg", "https://blog.example/virat-kohli-at-kainchi-dham", True),
        ("https://cdn.example/x.jpg", "https://blog.example/a-day-in-kainchi", False),  # 1 of 4
        ("https://cdn.example/x.jpg", "https://blog.example/ViratKohli", False),  # no word boundary
    ],
)
def test_name_evidence_is_half_the_name_words_in_the_page_url_or_file_name(
    url: str, page_url: str, evidenced: bool
) -> None:
    words = assets.name_words(_named(query=KOHLI, fallback="Virat Kohli portrait"))
    candidate = Candidate(url=url, page_url=page_url, width=0, height=0)
    assert assets.name_evidence(words, candidate) is evidenced


def test_name_evidence_ranks_ahead_of_the_judges_score(tmp_path: Path) -> None:
    """A named candidate at 2 outranks an unnamed one at 3; the judge still filters, so
    a named candidate under 2 never wins."""
    source = Scripted("web", _f1("web", KOHLI))
    judge = Scoring({LANGIMG: 2, YTIMG: 3}, default=1)  # ytimg: the one URL with no name
    manifest = _run(tmp_path, [_named(query=KOHLI, fallback="Virat Kohli portrait")],
                    sources={"web": source}, judging=assets.Judging(judge, 40))  # fmt: skip
    assert manifest.assets[0].source_url == LANGIMG

    judge = Scoring({LANGIMG: 1, YTIMG: 3}, default=1)
    manifest = _run(tmp_path / "again", [_named(query=KOHLI, fallback="Virat Kohli portrait")],
                    sources={"web": source}, judging=assets.Judging(judge, 40))  # fmt: skip
    assert manifest.assets[0].source_url == YTIMG


def test_name_evidence_orders_the_unjudged_ladder_too(tmp_path: Path) -> None:
    source = Scripted("web", _f1("web", KOHLI))  # iwmbuzz first in the source's order
    manifest = _run(tmp_path, [_named(query=KOHLI, fallback="Virat Kohli portrait")],
                    sources={"web": source})  # fmt: skip
    assert "virat-kohl" in manifest.assets[0].source_url


# --- rule 3: stock-preview hosts are dropped before judging -------------------------------

FIRE = "tantric ritual fire sadhu night India"


def test_stock_preview_hosts_never_reach_the_judge_and_each_drop_is_logged(
    tmp_path: Path,
) -> None:
    """F1's rights log held four alamy comps and a Freepik premium image, judged 3/3
    from thumbnails where the watermark is not visible."""
    source = Scripted("web", _f1("web", FIRE))
    judge = Scoring({}, default=3)
    log: list[str] = []
    beat = _beat(1, "concept", query=FIRE, depicts="scene")
    manifest = _run(tmp_path, [beat], sources={"web": source}, judging=assets.Judging(judge, 40),
                    log=log)  # fmt: skip
    asked = judge.asked[0][3]
    assert len(asked) == 2 and all("pexels" in u or "seaart" in u for u in asked)
    assert "images.pexels.com" in manifest.assets[0].source_url
    dropped = [line for line in log if "stock preview host" in line]
    assert len(dropped) == 4
    assert dropped[0] == (
        "sourcing: " + _f1("web", FIRE)[0].url + " rejected: stock preview host freepik.com"
    )
    assert {line.rsplit(" ", 1)[1] for line in dropped} == {
        "freepik.com", "alamy.com", "dreamstime.com"
    }


# --- rule 4: the size floor follows the slot -----------------------------------------------


@pytest.mark.parametrize("kind", ["card", "photo", "stamp", "wall"])
def test_a_small_real_photo_is_kept_where_it_is_shown_as_a_card(tmp_path: Path, kind: str) -> None:
    """F1 lost 584-768 px photos of the Baba to the flat 800 px floor. A card fills its
    slot at <= 1.5x, and a `photo` beat that cannot be full-bleed is a card by 5.3, so
    the floor is the card's for every sourced beat."""
    source = Scripted("web", _candidates(("six", 600, 800), ("seven", 768, 896)))
    manifest = _run(tmp_path, [_beat(1, "entity", kind=kind)], sources={"web": source})
    (beat,) = manifest.beats
    assert manifest.assets[0].source_url == "https://e.example/six.png"
    assert (beat.fallback_rung, beat.treatment) == (0, "card")
    assert beat.treatment_downgraded is (kind == "photo")


def test_a_photo_that_covers_the_frame_is_still_full_bleed(tmp_path: Path) -> None:
    """The 5.3 treatment rule is untouched: what covers 1080x1920 within the style's
    upscale is a full-bleed photo, what does not is a card."""
    source = Scripted("commons", _candidates(("tall", 1080, 1920)))
    manifest = _run(tmp_path, [_beat(1, "entity", kind="photo")], sources={"commons": source})
    assert (manifest.beats[0].treatment, manifest.beats[0].treatment_downgraded) == ("photo", False)


def test_the_floor_is_too_small_for_the_card_and_says_so(tmp_path: Path) -> None:
    source = Scripted("web", _candidates(("tiny", 300, 200), ("six", 600, 800)))
    log: list[str] = []
    manifest = _run(tmp_path, [_beat(1, "entity", kind="card")], sources={"web": source},
                    log=log)  # fmt: skip
    assert manifest.assets[0].source_url == "https://e.example/six.png"
    assert log[0] == (
        "sourcing: https://e.example/tiny.png rejected: 300x200 px cannot fill a 947 px wide "
        "card at <= 1.5x"  # min(980, 650 x 1.5) - 2 x 14
    )


def test_the_floor_reads_the_styles_card_border() -> None:
    assert assets.card_border(SPEC) == 14


# --- rule 5: a source says why it returned nothing ----------------------------------------


def test_a_sources_notes_reach_the_job_log(tmp_path: Path) -> None:
    """F1's Commons and Openverse searches returned nothing with no log line at all.
    Whatever a source notes about a search is one `sourcing:` line."""

    class Noting(Scripted):
        def search(self, query: str, n: int) -> list[Candidate]:
            self.note(f"{self.origin} answered 403 for {query!r}")
            return super().search(query, n)

    log: list[str] = []
    _run(tmp_path, [_beat(1, "concept", query="q1", fallback="q2")],
         sources={"commons": Noting("commons", [])}, log=log)  # fmt: skip
    assert [line for line in log if "answered 403" in line] == [
        "sourcing: commons answered 403 for 'q1'",
        "sourcing: commons answered 403 for 'q2'",
    ]
