"""Ticket 069: a bed you can hear on a phone. Run04 went out with a car's exhaust as its
bed: the search ladder narrowed to words that were not about music, and the balance gate
had no upper bound on the speech-band margin, so a bed 28.7 dB under the voice in the
band a phone speaker plays passed. Two numbers in every style's `sound` front matter fix
it: `bed_query_anchor` rides on every search rung (and the Freesound bed request filters
on `tag:music`), and `speech_band_margin_max_db` fails a bed the speaker cannot play.

The mix half (a bass-only bed dropped for a mid-band one) is in `test_sound.py`, beside
the 056 ladder tests and their voice fixture."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import yaml
from pydantic import SecretStr

from shortsmith import render, sound, styles
from shortsmith.contracts import BalanceReport, BedQuery
from shortsmith.sound import (
    _BedMix,  # pyright: ignore[reportPrivateUsage]
    _repaired_bed,  # pyright: ignore[reportPrivateUsage]
    freesound,
)

ALL = ("explainer", "educational", "animated", "hitech", "footage", "vishva", "fastfacts")
VERSIONS = {
    "explainer": "17", "educational": "15", "animated": "15", "hitech": "16",
    "footage": "7", "vishva": "7", "fastfacts": "7",
}  # fmt: skip  (069 bumped each once more, 072 every style with a map, 070 every style, 076 each)
# Run04's sound call (job 20260928-140620-f774e1, vishva): the bed query as written.
RUN04 = BedQuery(theme="history documentary", mood="regal intriguing eastern oud", energy=3)


@pytest.fixture(scope="module")
def specs() -> dict[str, styles.StyleSpec]:
    return styles.load_all(render.registry())


# --- the numbers -------------------------------------------------------------------------


def test_every_style_carries_the_music_anchor_and_the_margin_ceiling(
    specs: dict[str, styles.StyleSpec],
) -> None:
    assert sorted(specs) == sorted(ALL)
    for name in ALL:
        nums = specs[name].sound
        assert nums.bed_query_anchor == "music", name
        assert nums.speech_band_margin_max_db == 20, name
        assert nums.speech_band_margin_max_db > nums.speech_band_margin_db, name
        assert specs[name].version == VERSIONS[name], name


def _variant(tmp_path: Path, mutate: Any) -> Path:
    import shutil

    target = tmp_path / "styles"
    shutil.copytree(styles.STYLES_DIR, target)
    path = target / "vishva.md"
    front, body = styles.split_front_matter(path.read_text(encoding="utf-8"))
    mutate(front)
    path.write_text(f"---\n{yaml.safe_dump(front, sort_keys=False)}---\n{body}", encoding="utf-8")
    return target


def test_load_all_refuses_a_ceiling_below_the_floor(tmp_path: Path) -> None:
    def low(front: dict[str, Any]) -> None:
        front["sound"]["speech_band_margin_max_db"] = 10

    with pytest.raises(styles.StyleError, match="vishva: sound.speech_band_margin_max_db 10"):
        styles.load_all(render.registry(), _variant(tmp_path, low))


def test_load_all_refuses_a_style_without_the_anchor(tmp_path: Path) -> None:
    def gone(front: dict[str, Any]) -> None:
        del front["sound"]["bed_query_anchor"]

    with pytest.raises(styles.StyleError, match="bed_query_anchor"):
        styles.load_all(render.registry(), _variant(tmp_path, gone))


# --- fault 2: the search asks for music --------------------------------------------------


def test_every_rung_of_run04s_ladder_asks_for_music(specs: dict[str, styles.StyleSpec]) -> None:
    nums = specs["vishva"].sound
    rungs = sound.bed_queries(RUN04, nums.default_bed_query, nums.bed_query_anchor)
    assert rungs, "a ladder"
    for rung in rungs:
        words = rung.split()
        assert "music" in words, rung
        assert words.count("music") == 1, rung
        assert 1 <= len(words) <= sound.QUERY_MAX_WORDS, rung
    assert "regal" not in rungs, "run04's fourth rung, a Buick's exhaust, is never asked alone"
    assert rungs[-1] == "calm ambient history documentary music"


def test_without_an_anchor_the_ladder_is_as_before() -> None:
    assert sound.bed_queries(RUN04, "calm ambient") == sound.bed_queries(RUN04, "calm ambient", "")


def test_the_director_passes_the_styles_anchor_to_the_search(
    library: sound.Library, specs: dict[str, styles.StyleSpec]
) -> None:
    nums = specs["vishva"].sound
    no_beds = sound.Library(root=library.root, entries=tuple(library.sfx()))
    search = sound.FakeAudioSearch()
    chosen, _ = sound.choose_bed(
        no_beds, RUN04, first_stamp_s=1.0, threshold=nums.bed_score_threshold, search=search,
        default_query=nums.default_bed_query, anchor=nums.bed_query_anchor,
    )  # fmt: skip
    assert chosen is None
    assert search.calls == list(
        sound.bed_queries(RUN04, nums.default_bed_query, nums.bed_query_anchor)
    )
    assert all("music" in c.split() for c in search.calls)


def test_the_freesound_bed_request_filters_on_the_music_tag() -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"count": 0, "results": []})

    client = httpx.Client(transport=httpx.MockTransport(answer))
    adapter = freesound.FreesoundAudioSearch(api_key=SecretStr("not-a-key"), client=client)
    adapter.search("history documentary music", "bed")
    adapter.search("tick", "sfx")
    bed, sfx = (r.url.params["filter"] for r in seen)
    assert "tag:music" in bed.split()
    assert "tag:music" not in sfx, "a cue is not music"


# --- fault 3: a bed the speaker cannot play fails the balance ----------------------------


def test_a_margin_over_the_ceiling_is_a_problem_naming_the_margin(
    specs: dict[str, styles.StyleSpec],
) -> None:
    for name in ALL:
        nums = specs[name].sound
        assert sound.margin_problem(20.0, nums) is None, name
        assert sound.margin_problem(15.0, nums) is None, name
        problem = sound.margin_problem(28.7, nums)
        assert problem is not None, name
        assert "28.7 dB" in problem and "sound.speech_band_margin_max_db 20 dB" in problem, name
        under = sound.margin_problem(11.0, nums)
        assert under is not None and "under sound.speech_band_margin_db 12 dB" in under, name


def _report(nums: styles.Sound, margin: float) -> BalanceReport:
    problem = sound.margin_problem(margin, nums)
    return BalanceReport(
        voice_db=-20.0, bed_under_voice_db=-14.0, speech_band_margin_db=margin,
        bed_accept_db=nums.bed_accept_db, speech_band_margin_min_db=nums.speech_band_margin_db,
        speech_band_margin_max_db=nums.speech_band_margin_max_db, duck_max_db=nums.duck_max_db,
        problems=[] if problem is None else [problem],
    )  # fmt: skip


def test_an_inaudible_bed_takes_no_repair_it_goes_to_the_next_candidate(
    monkeypatch: pytest.MonkeyPatch, specs: dict[str, styles.StyleSpec]
) -> None:
    """A dip or a lower bed only moves the band further down; no repair makes a bass-only
    bed audible, so the plain mix is the answer and the caller walks on."""
    nums = specs["vishva"].sound
    calls: list[tuple[object, object]] = []

    def fake_mix(stems: Path, **kw: object) -> _BedMix:
        calls.append((kw["dip_db"], kw["under_db"]))
        return _BedMix(None, None, _report(nums, 28.7), dip_db=0.0)

    monkeypatch.setattr(sound, "_mix_bed", fake_mix)
    lines: list[str] = []
    result = _repaired_bed(
        Path("stems"), score=SimpleNamespace(label="freesound_557546"), library=None,  # type: ignore[arg-type]
        story=None, nums=nums,  # type: ignore[arg-type]
        voice=Path("voice.wav"), voice_db=-20.0, runtime_s=6.0, cues=0,
        note=lambda ls: lines.extend(ls),
    )  # fmt: skip
    assert calls == [(0.0, None)]
    assert result.repairs == ()
    assert result.balance.problems and "28.7 dB" in result.balance.problems[0]
    assert any("freesound_557546" in line and "no repair" in line for line in lines), lines


def test_a_dip_that_the_lowering_pushes_over_the_ceiling_is_taken_off(
    monkeypatch: pytest.MonkeyPatch, specs: dict[str, styles.StyleSpec]
) -> None:
    """A bed both too loud and crowding the band is dipped at the loud level, then
    lowered; the dip and the drop together can leave the band inaudible, so the lowered
    bed is mixed once more without the dip."""
    nums = specs["explainer"].sound
    loud = "the bed sits -3.0 dB under the voice, outside sound.bed_accept_db -15 to -12 dB"
    calls: list[tuple[float, float | None]] = []

    def fake_mix(stems: Path, **kw: Any) -> _BedMix:
        dip, under = kw["dip_db"], kw["under_db"]
        calls.append((dip, under))
        margin = {(True, False): 5.0, (False, False): 13.0, (False, True): 24.0,
                  (True, True): 17.0}[(dip == 0.0, under is not None)]  # fmt: skip
        report = _report(nums, margin)
        if under is None:
            report = report.model_copy(update={"problems": [*report.problems, loud]})
        return _BedMix(None, None, report, dip_db=dip)

    monkeypatch.setattr(sound, "_mix_bed", fake_mix)
    lines: list[str] = []
    result = _repaired_bed(
        Path("stems"), score=SimpleNamespace(label="bed_x"), library=None,  # type: ignore[arg-type]
        story=None, nums=nums,  # type: ignore[arg-type]
        voice=Path("voice.wav"), voice_db=-20.0, runtime_s=6.0, cues=0,
        note=lambda ls: lines.extend(ls),
    )  # fmt: skip
    low = nums.bed_accept_db[0] + sound.BED_TOLERANCE_DB
    first_dip = sound.dip_depths(nums.speech_band_margin_db - 5.0)[0]
    assert calls == [(0.0, None), (first_dip, None), (first_dip, low), (0.0, low)]
    assert result.balance.problems == [] and result.dip_db == 0.0
    assert "without the dip" in result.repairs[-1] and "17.0 dB" in result.repairs[-1]


def test_the_balance_report_names_the_ceiling() -> None:
    report = BalanceReport.model_validate(
        json.loads(
            '{"voice_db": -20, "bed_accept_db": [-15, -12], "speech_band_margin_min_db": 12,'
            ' "speech_band_margin_max_db": 20, "duck_max_db": 4}'
        )
    )
    assert report.speech_band_margin_max_db == 20
    old = BalanceReport(voice_db=-20, bed_accept_db=(-15, -12), speech_band_margin_min_db=12,
                        duck_max_db=4)  # fmt: skip
    assert old.speech_band_margin_max_db is None, "a job from before 069 still loads"


def test_the_job_page_balance_line_shows_both_bounds() -> None:
    from shortsmith.qa import critic

    report = BalanceReport(
        voice_db=-20, bed_under_voice_db=-14, speech_band_margin_db=28.7,
        bed_accept_db=(-15, -12), speech_band_margin_min_db=12, speech_band_margin_max_db=20,
        duck_max_db=4,
    )  # fmt: skip
    assert "speech-band margin 28.7 dB (min 12, max 20)" in critic.balance_text(report)
