"""qa.technical: T1-T4 (decision 10.1), the 016 rescue limit (reported as T8 until 032
completes it) and T9 rights completeness, each with a passing and a failing input, the
boundaries on both sides, and `run(job)` stopping at the first FAIL and writing
`out/qa.json`. Boundary cases use ffprobe-shaped dicts and `Loudness` values; the
real-file cases encode small synthetic clips (12.1: never a committed video).

Ticket 031: T5 (caption coverage at three seeded timestamps, lip-sync lag by envelope
cross-correlation), T7 (mean luma per frame, frozen runs before the finale) and T10
(no cut boundary mid-word), each pure over what ffmpeg measured, with the T11-T13
placeholders recorded `not_implemented` and never passing silently."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from shortsmith import assets, ffmpeg, jobs, presenter, rights, sound
from shortsmith.contracts import (
    AssetManifest,
    AssetRecord,
    Beat,
    BeatAsset,
    CaptionPage,
    Captions,
    CueRecord,
    CueSheet,
    CutPlan,
    Finale,
    Hook,
    PicturePlan,
    Span,
    Word,
)
from shortsmith.ffmpeg import FrameStat, Loudness
from shortsmith.qa import technical
from shortsmith.qa.technical import LipSync, QaCheck, QaReport
from shortsmith.sound import sweep
from shortsmith.transcriber import FakeTranscriber
from tests.conftest import Media, Sounds, ring, stem, swell, write_wav

MP4 = "mov,mp4,m4a,3gp,3g2,mj2"
FPS = 30
IMPLEMENTED = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10"]
ALL_CHECKS = [*IMPLEMENTED, "T11", "T12", "T13"]


def _info(
    *,
    width: int = 1080,
    height: int = 1920,
    fps: str = "30/1",
    codec: str = "h264",
    fmt: str = MP4,
    audio: int = 1,
    nb_frames: int = 180,
    duration: float = 6.0,
) -> dict[str, Any]:
    video = {
        "codec_type": "video",
        "codec_name": codec,
        "width": width,
        "height": height,
        "r_frame_rate": fps,
        "avg_frame_rate": fps,
        "nb_frames": str(nb_frames),
        "duration": f"{duration:.6f}",
    }
    streams: list[dict[str, Any]] = [video]
    streams += [{"codec_type": "audio", "codec_name": "aac"} for _ in range(audio)]
    return {"streams": streams, "format": {"format_name": fmt, "duration": f"{duration:.6f}"}}


def _beat(id: str, start: float, end: float, kind: str = "photo") -> Beat:
    return Beat(id=id, start=start, end=end, mode="off", kind=kind, asset_id="a1")  # type: ignore[arg-type]


def _plan(beats: list[Beat], finale_id: str) -> PicturePlan:
    return PicturePlan(
        prompt_version="test",
        cut=CutPlan(keep=[Span(start=0.0, end=beats[-1].end)]),
        beats=beats,
        hook=Hook(
            title="t", cold_open_span=Span(start=0.0, end=0.5), original_position="drop",
            card_asset_ids=["a1"],
        ),  # fmt: skip
        finale=Finale(beat_id=finale_id, text="end"),
        title="t",
        description="d",
    )


def _good_plan(finale_len: float = 1.0, gap: float = 0.0) -> PicturePlan:
    beats = [
        _beat("b1", 0.0, 2.0),
        _beat("b2", 2.0 + gap, 4.0),
        _beat("b3", 4.0, 4.0 + finale_len, kind="finale"),
    ]
    return _plan(beats, "b3")


# --- T1 codec / container / geometry -------------------------------------------------


def test_t1_passes_a_conforming_probe() -> None:
    check = technical.t1(_info())
    assert check.name == "T1"
    assert check.passed
    assert "1080x1920" in check.detail


@pytest.mark.parametrize(
    ("info", "needle"),
    [
        (_info(width=720, height=1280), "720x1280"),
        (_info(fps="25/1"), "25/1"),
        (_info(codec="hevc"), "hevc"),
        (_info(fmt="matroska,webm"), "matroska"),
        (_info(audio=0), "0 audio"),
        (_info(audio=2), "2 audio"),
    ],
)
def test_t1_fails_and_names_the_offence(info: dict[str, Any], needle: str) -> None:
    check = technical.t1(info)
    assert not check.passed
    assert needle in check.detail


def test_t1_on_real_files(media: Media) -> None:
    good = ffmpeg.probe(media.clip(duration_s=2.0, ext=".mp4"))
    assert technical.t1(good).passed
    wrong_size = ffmpeg.probe(media.clip(duration_s=2.0, width=720, height=1280, ext=".mp4"))
    assert not technical.t1(wrong_size).passed


# --- T2 frame count ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nb_frames", "duration", "ok"),
    [(180, 6.0, True), (179, 6.0, False), (181, 6.0, False), (60, 2.0, True), (59, 2.0, False)],
)
def test_t2_frame_count_is_round_duration_times_30(
    nb_frames: int, duration: float, ok: bool
) -> None:
    check = technical.t2(_info(nb_frames=nb_frames, duration=duration))
    assert check.name == "T2"
    assert check.passed is ok
    assert str(nb_frames) in check.detail


def test_t2_on_real_files(media: Media, tmp_path: Path) -> None:
    good = media.clip(duration_s=2.0, ext=".mp4")
    assert technical.t2(ffmpeg.probe(good)).passed
    dropped = tmp_path / "dropped.mp4"
    ffmpeg.run(
        [
            ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(good),
            "-vf", "select=not(eq(n\\,10))", "-fps_mode", "vfr",
            "-c:v", "libx264", "-preset", "ultrafast", "-an", str(dropped),
        ]  # fmt: skip
    )
    check = technical.t2(ffmpeg.probe(dropped))
    assert not check.passed
    assert "59" in check.detail


# --- T3 duration, contiguity, finale ---------------------------------------------------


def test_t3_passes_a_conforming_plan_and_duration() -> None:
    check = technical.t3(_info(duration=6.0), _good_plan())
    assert check.name == "T3"
    assert check.passed


@pytest.mark.parametrize(("duration", "ok"), [(60.0, True), (60.001, False)])
def test_t3_duration_boundary(duration: float, ok: bool) -> None:
    check = technical.t3(_info(duration=duration), _good_plan())
    assert check.passed is ok
    if not ok:
        assert "60.001" in check.detail


@pytest.mark.parametrize(
    ("gap", "ok", "word"),
    [(0.011, True, ""), (0.012, False, "gap"), (-0.011, True, ""), (-0.012, False, "overlap")],
)
def test_t3_beats_contiguous_within_0_011(gap: float, ok: bool, word: str) -> None:
    check = technical.t3(_info(), _good_plan(gap=gap))
    assert check.passed is ok
    if not ok:
        assert "b1" in check.detail and "b2" in check.detail and word in check.detail


@pytest.mark.parametrize(
    ("finale_len", "ok"), [(0.8, True), (0.79, False), (1.2, True), (1.21, False)]
)
def test_t3_finale_between_0_8_and_1_2_s(finale_len: float, ok: bool) -> None:
    check = technical.t3(_info(), _good_plan(finale_len=finale_len))
    assert check.passed is ok
    if not ok:
        assert "finale" in check.detail


def test_t3_names_a_missing_finale_beat() -> None:
    plan = _plan([_beat("b1", 0.0, 1.0)], "nope")
    check = technical.t3(_info(), plan)
    assert not check.passed
    assert "nope" in check.detail


def test_t3_on_an_over_long_real_file(media: Media) -> None:
    info = ffmpeg.probe(media.clip(duration_s=60.5, width=180, height=320, ext=".mp4"))
    check = technical.t3(info, _good_plan())
    assert not check.passed
    assert "60.5" in check.detail


# --- T4 master loudness ------------------------------------------------------------------


def _loud(integrated: float = -14.0, true_peak: float = -1.5) -> Loudness:
    return Loudness(
        integrated=integrated, true_peak=true_peak, lra=5.0, threshold=-24.0, offset=0.0
    )


@pytest.mark.parametrize(
    ("integrated", "true_peak", "ok"),
    [
        (-14.0, -1.5, True),
        (-14.5, -1.5, True),
        (-13.5, -1.5, True),
        (-14.51, -1.5, False),
        (-13.49, -1.5, False),
        (-14.0, -1.49, False),
        (-14.0, -3.0, True),
    ],
)
def test_t4_master_within_half_lu_and_under_true_peak(
    integrated: float, true_peak: float, ok: bool
) -> None:
    check = technical.t4(_loud(integrated, true_peak))
    assert check.name == "T4"
    assert check.passed is ok
    assert "LUFS" in check.detail and "dBTP" in check.detail


def test_t4_on_a_quiet_real_master(media: Media) -> None:
    quiet = media.clip(duration_s=2.0, amplitude=0.01, ext=".mp4")
    check = technical.t4(ffmpeg.measure_loudness(quiet))
    assert not check.passed


# --- T8 rescue limit (4.4; the rest of T8 is ticket 032) ------------------------------------


def _owner(asset_id: str) -> AssetRecord:
    return AssetRecord(id=asset_id, origin="owner_supplied", licence="owner",
                       file=f"input/refs/{asset_id}.png", sha256="0" * 64, width=1080,
                       height=1920, fetched_at="2026-09-22T12:00:00+00:00")  # fmt: skip


def _manifest(records: list[AssetRecord], beats: list[BeatAsset], *, rescued_max: int = 4,
              runtime_s: float = 60.0) -> AssetManifest:  # fmt: skip
    return AssetManifest(assets=records, beats=beats, runtime_s=runtime_s,
                         rescued_max=rescued_max)  # fmt: skip


def _rescues(n: int, total: int = 12) -> list[BeatAsset]:
    return [
        BeatAsset(beat_id=f"b{i:02d}", asset_id=None if i < n else "a1",
                  treatment="gradient" if i < n else "card", fallback_rung=4 if i < n else 0)
        for i in range(total)
    ]  # fmt: skip


def test_t8_four_rescues_in_sixty_seconds_pass() -> None:
    check = technical.t8(_manifest([_owner("a1")], _rescues(4)))
    assert (check.name, check.passed) == ("T8", True)
    assert "4 rescued beats (max 4" in check.detail


def test_t8_the_fifth_rescue_fails_with_not_enough_relevant_broll() -> None:
    check = technical.t8(_manifest([_owner("a1")], _rescues(5)))
    assert not check.passed
    assert check.detail.startswith("not enough relevant B-roll")
    assert "5 rescued beats (max 4" in check.detail


def test_t8_counts_rung_3_as_a_rescue() -> None:
    beats = [BeatAsset(beat_id="b1", asset_id="a1", treatment="card", fallback_rung=3),
             BeatAsset(beat_id="b2", asset_id="a1", treatment="card", fallback_rung=2)]  # fmt: skip
    assert not technical.t8(_manifest([_owner("a1")], beats, rescued_max=0)).passed
    assert technical.t8(_manifest([_owner("a1")], beats, rescued_max=1)).passed


def test_t8_without_a_manifest_fails() -> None:
    check = technical.t8(None)
    assert not check.passed and "work/assets.json" in check.detail


# --- T9 rights completeness (5.4) ----------------------------------------------------------


def test_t9_passes_a_complete_log() -> None:
    plan = _good_plan()
    manifest = _manifest([_owner("a1")], [])
    check = technical.t9(rights.rows(manifest, plan), manifest, plan)
    assert (check.name, check.passed) == ("T9", True)
    assert check.detail == "1 rights row, every beat's asset logged"


def test_t9_fails_naming_each_problem() -> None:
    plan = _good_plan()
    manifest = _manifest([], [])
    check = technical.t9([], manifest, plan)
    assert not check.passed
    assert check.detail.startswith("b1: asset a1 has no rights row")


def test_t9_without_a_rights_log_fails() -> None:
    check = technical.t9(None, _manifest([], []), _good_plan())
    assert not check.passed and "out/rights.json" in check.detail


# --- T6 no sweep on the SFX stem (7.3) -------------------------------------------------------


def _sheet() -> CueSheet:
    return CueSheet(
        cues=[
            CueRecord(beat_id="b1", intent="bass", entry_id="sfx_bass", start_s=0.5, end_s=0.9),
            CueRecord(beat_id="b2", intent="reveal", entry_id="sfx_rise", start_s=2.0, end_s=4.0),
        ]
    )


def test_t6_without_an_sfx_stem_passes_with_its_reason() -> None:
    check = technical.t6(None, None)
    assert (check.name, check.passed) == ("T6", True)
    assert check.detail == (
        "no SFX stem: work/stems/sfx.wav is absent, so the short has no cues to scan"
    )


def test_t6_passes_a_clean_stem() -> None:
    check = technical.t6([], _sheet())
    assert (check.name, check.passed) == ("T6", True)
    assert check.detail == "R1-R4 clean on the SFX stem (2 cues)"


def test_t6_fails_naming_the_cue_sounding_at_the_hit() -> None:
    hit = sweep.Hit(rule="R2", at_s=2.1, detail="crescendo of 9.0 dB over 0.23 s")
    check = technical.t6([hit], _sheet())
    assert not check.passed
    assert check.detail == (
        "R2 at 2.10 s in cue sfx_rise on b2 ('reveal'): crescendo of 9.0 dB over 0.23 s"
    )


def test_t6_names_the_last_cue_before_a_hit_between_cues() -> None:
    hit = sweep.Hit(rule="R3", at_s=1.5, detail="one sound 5.10 s long")
    check = technical.t6([hit], _sheet())
    assert not check.passed and "cue sfx_bass on b1" in check.detail


def test_t6_says_so_when_no_cue_sounds_before_a_hit() -> None:
    hit = sweep.Hit(rule="R1", at_s=0.1, detail="flat")
    check = technical.t6([hit], _sheet())
    assert not check.passed and "no cue sounds there" in check.detail


def _with_sfx_stem(job: jobs.Job, source: Path, sheet: CueSheet) -> None:
    stems = job.work_dir / "stems"
    stems.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, stems / "sfx.wav")
    (stems / sound.CUES_NAME).write_text(sheet.model_dump_json(indent=2), encoding="utf-8")


def test_run_fails_t6_naming_the_offending_cue(
    speaking_short: Path, sounds: Sounds, tmp_path: Path
) -> None:
    job = _speaking_job(tmp_path, speaking_short)
    sheet = CueSheet(
        cues=[CueRecord(beat_id="b1", intent="whoosh", entry_id="sfx_noise", start_s=0.0,
                        end_s=1.0)]  # fmt: skip
    )
    _with_sfx_stem(job, sounds("noise_500ms"), sheet)
    report = technical.run(job)
    assert [c.name for c in report.checks] == ["T1", "T2", "T3", "T4", "T5", "T6"]
    assert report.failed is not None and report.failed.name == "T6"
    assert report.failed.detail.startswith("R1 at 0.00 s in cue sfx_noise on b1 ('whoosh')")


def test_t6_names_the_cue_a_sliced_hit_came_from() -> None:
    # 050: an R3/R4 hit carries the index of its cue in the sheet it was sliced by, so
    # it names that cue even where a neighbour's tail also sounds at its time.
    hit = sweep.Hit(rule="R4", at_s=2.05, detail="attack of 0.20 s", slice=0)
    check = technical.t6([hit], _sheet())
    assert not check.passed
    assert check.detail == "R4 at 2.05 s in cue sfx_bass on b1 ('bass'): attack of 0.20 s"


def test_cue_slices_run_to_the_earlier_of_the_end_and_the_next_start() -> None:
    sheet = CueSheet(
        cues=[
            CueRecord(beat_id="b1", intent="a", entry_id="x", start_s=0.0, end_s=2.0),
            CueRecord(beat_id="b2", intent="b", entry_id="y", start_s=1.5, end_s=3.5),
            CueRecord(beat_id="b3", intent="c", entry_id="z", start_s=6.0, end_s=8.0),
        ]
    )
    assert technical.cue_slices(sheet) == [(0.0, 1.5), (1.5, 3.5), (6.0, 8.0)]


def test_sorted_sheet_orders_cues_by_start() -> None:
    late = CueRecord(beat_id="b2", intent="b", entry_id="y", start_s=3.0, end_s=5.0)
    early = CueRecord(beat_id="b1", intent="a", entry_id="x", start_s=0.0, end_s=2.0)
    assert technical.sorted_sheet(CueSheet(cues=[late, early])) == CueSheet(cues=[early, late])
    assert technical.sorted_sheet(None) is None


def _chained_stem_job(tmp_path: Path, short: Path, plan: PicturePlan) -> jobs.Job:
    """Five ringing cues whose tails run together (the 023 misfire), the fourth a 200 ms
    swell; the cue sheet is written in a scrambled order."""
    job = _speaking_job(tmp_path, short, plan)
    starts = [0.0, 1.5, 3.0, 4.5, 6.0]
    parts = [ring() for _ in starts]
    parts[3] = swell(over_s=0.2)
    x = stem(list(zip(starts, parts, strict=True)), runtime_s=9.0)
    stems = job.work_dir / "stems"
    stems.mkdir(parents=True, exist_ok=True)
    write_wav(stems / "sfx.wav", x)
    cues = [
        CueRecord(beat_id=f"b{i + 1}", intent=f"hit{i + 1}", entry_id=f"sfx_{i + 1}",
                  start_s=s, end_s=s + (0.4 if i == 3 else 2.0))
        for i, s in enumerate(starts)
    ]  # fmt: skip
    scrambled = [cues[3], cues[0], cues[4], cues[1], cues[2]]
    sheet = CueSheet(cues=scrambled)
    (stems / sound.CUES_NAME).write_text(sheet.model_dump_json(indent=2), encoding="utf-8")
    return job


def test_run_fails_t6_naming_the_one_offending_cue_in_a_chained_stem(
    speaking_short: Path, tmp_path: Path
) -> None:
    job = _chained_stem_job(tmp_path, speaking_short, _good_plan())
    report = technical.run(job)
    assert report.failed is not None and report.failed.name == "T6"
    assert report.failed.detail.startswith("R4 at 4.5")
    assert "in cue sfx_4 on b4 ('hit4'): attack of 0." in report.failed.detail
    attack = float(report.failed.detail.split("attack of ")[1].split(" s")[0])
    assert attack == pytest.approx(0.2, abs=0.03), "the swell's own attack, not a tail's"
    assert report.failed.detail.count(" in cue ") == 1, "one hit, from one cue"


def test_run_passes_t6_when_every_chained_cue_is_clean(
    speaking_short: Path, tmp_path: Path
) -> None:
    job = _chained_stem_job(tmp_path, speaking_short, _good_plan())
    starts = [0.0, 1.5, 3.0, 4.5, 6.0]
    x = stem([(s, ring()) for s in starts], runtime_s=9.0)
    write_wav(job.work_dir / "stems" / "sfx.wav", x)
    report = technical.run(job)
    t6 = next(c for c in report.checks if c.name == "T6")
    assert t6.passed and t6.detail == "R1-R4 clean on the SFX stem (5 cues)"


def test_run_passes_t6_on_a_clean_stem(
    speaking_short: Path, sounds: Sounds, tmp_path: Path
) -> None:
    job = _speaking_job(tmp_path, speaking_short)
    _with_sfx_stem(job, sounds("clicks"), _sheet())
    report = technical.run(job)
    t6 = next(c for c in report.checks if c.name == "T6")
    assert t6.passed and t6.detail == "R1-R4 clean on the SFX stem (2 cues)"


# --- check status and the T11-T13 placeholders (031) ------------------------------------------


def test_check_status_follows_passed_unless_not_implemented() -> None:
    assert QaCheck(name="T1", passed=True, detail="x").status == "pass"
    assert QaCheck(name="T1", passed=False, detail="x").status == "fail"
    held = technical.placeholder("T11")
    assert (held.name, held.passed, held.status) == ("T11", False, "not_implemented")
    assert "032" in held.detail
    with pytest.raises(ValueError):
        QaCheck(name="T11", passed=True, status="not_implemented", detail="x")


def test_report_passes_with_placeholders_but_never_counts_them_as_pass() -> None:
    checks = [QaCheck(name="T1", passed=True, detail="x"), technical.placeholder("T11")]
    report = technical.report(checks)
    assert report.passed and report.failed is None
    assert [c.status for c in report.checks] == ["pass", "not_implemented"]
    failing = technical.report([*checks, QaCheck(name="T12", passed=False, detail="bad")])
    assert not failing.passed and failing.failed is not None and failing.failed.name == "T12"


def test_check_order_is_t1_to_t13_with_the_032_placeholders_last() -> None:
    assert list(technical.CHECK_ORDER) == ALL_CHECKS
    assert list(technical.PLACEHOLDERS) == ["T11", "T12", "T13"]
    assert list(technical.IMPLEMENTED) == IMPLEMENTED


# --- T5 caption coverage and lip-sync (6.1, 3.1) -------------------------------------------------


def _pages(words: list[Word], *, hide_from: float | None = None, hold_s: float = 0.9,
           per_page: int = 2) -> list[CaptionPage]:  # fmt: skip
    """One page per `per_page` words, each running from its first word to the next
    page's start (or `hold_s` after its last word), clipped at `hide_from`."""
    shown = [w for w in words if hide_from is None or w.start < hide_from]
    groups = [shown[i : i + per_page] for i in range(0, len(shown), per_page)]
    pages: list[CaptionPage] = []
    for n, group in enumerate(groups):
        start = max(0.0, group[0].start - 0.04)
        end = groups[n + 1][0].start - 0.04 if n + 1 < len(groups) else group[-1].end + hold_s
        if hide_from is not None:
            end = min(end, hide_from)
        first = words.index(group[0])
        pages.append(
            CaptionPage(
                index=n,
                word_indices=list(range(first, first + len(group))),
                texts=[w.text for w in group],
                start=round(start, 3),
                end=round(end, 3),
            )
        )
    return pages


FAKE_WORDS = FakeTranscriber().transcribe(Path("unused.mp4")).words


def test_t5_passes_with_every_sampled_word_on_a_page_and_no_lag() -> None:
    pages = _pages(FAKE_WORDS, hide_from=5.0)
    check = technical.t5(pages, FAKE_WORDS, LipSync(lag_s=0.0), hide_from=5.0)
    assert (check.name, check.passed) == ("T5", True)
    assert f"seed {technical.T5_SEED}" in check.detail
    assert "lip-sync lag +0.0 frames" in check.detail


def test_t5_records_three_seeded_timestamps_before_the_finale() -> None:
    pages = _pages(FAKE_WORDS, hide_from=5.0)
    sampled = technical.sample_words(FAKE_WORDS, hide_from=5.0)
    assert len(sampled) == 3
    assert all(w.end <= 5.0 for w in sampled), "never a word the finale hides"
    assert sampled == technical.sample_words(FAKE_WORDS, hide_from=5.0), "seeded: the same draw"
    check = technical.t5(pages, FAKE_WORDS, LipSync(lag_s=0.0), hide_from=5.0)
    for word in sampled:
        assert f"{(word.start + word.end) / 2:.2f} s" in check.detail


def test_t5_fails_on_a_page_gap_naming_the_time() -> None:
    sampled = technical.sample_words(FAKE_WORDS, hide_from=5.0)
    first = FAKE_WORDS.index(sampled[0])
    pages = [p for p in _pages(FAKE_WORDS, hide_from=5.0) if first not in p.word_indices]
    check = technical.t5(pages, FAKE_WORDS, LipSync(lag_s=0.0), hide_from=5.0)
    assert not check.passed
    t = (sampled[0].start + sampled[0].end) / 2
    assert f"no caption page at {t:.2f} s" in check.detail


def test_t5_fails_with_no_captioned_words() -> None:
    check = technical.t5([], FAKE_WORDS, LipSync(lag_s=0.0), hide_from=0.0)
    assert not check.passed and "no captioned words" in check.detail


@pytest.mark.parametrize(
    ("frames", "ok"), [(1.0, True), (1.01, False), (-1.0, True), (-1.01, False), (0.0, True)]
)
def test_t5_lag_boundary_is_one_frame_either_way(frames: float, ok: bool) -> None:
    pages = _pages(FAKE_WORDS, hide_from=5.0)
    lag = LipSync(lag_s=frames / FPS)
    assert lag.frames == pytest.approx(frames)
    check = technical.t5(pages, FAKE_WORDS, lag, hide_from=5.0)
    assert check.passed is ok
    if not ok:
        assert "outside +/-1 frame" in check.detail


def _bursts(*, rate: int, length_s: float, shift_s: float = 0.0) -> np.ndarray:
    """Tone bursts 0.3 s long every second (the fixture's speech), moved `shift_s` later."""
    t = np.arange(round(length_s * rate)) / rate - shift_s
    on = ((t % 1.0) >= 0.2) & ((t % 1.0) < 0.5) & (t >= 0)
    return 0.5 * np.sin(2 * np.pi * 880 * t) * on


@pytest.mark.parametrize("shift_s", [0.0, 0.1, -0.1, 0.02])
def test_lipsync_lag_finds_the_shift_of_the_other_track(shift_s: float) -> None:
    rate = 48000
    reference = _bursts(rate=rate, length_s=6.0)
    other = _bursts(rate=rate, length_s=6.0, shift_s=shift_s)
    lag = technical.lipsync_lag_s(reference, other, rate)
    assert lag == pytest.approx(shift_s, abs=0.002)


def test_lipsync_lag_is_zero_on_silence() -> None:
    zeros = np.zeros(48000)
    assert technical.lipsync_lag_s(zeros, zeros, 48000) == 0.0


# --- T7 luma and frozen frames (4.4, 3.1) --------------------------------------------------------


def _frames(lumas: list[float], hashes: list[str] | None = None) -> list[FrameStat]:
    hashes = hashes or [f"h{i}" for i in range(len(lumas))]
    pairs = zip(lumas, hashes, strict=True)
    return [FrameStat(index=i, luma=luma, hash=h) for i, (luma, h) in enumerate(pairs)]


def test_t7_passes_bright_moving_frames() -> None:
    check = technical.t7(_frames([100.0] * 60), fps=FPS, finale_start_s=1.5)
    assert (check.name, check.passed) == ("T7", True)
    assert "60 frames" in check.detail and "min 100.0/255" in check.detail


@pytest.mark.parametrize(("luma", "ok"), [(12.0, True), (11.99, False)])
def test_t7_luma_boundary_is_12_of_255(luma: float, ok: bool) -> None:
    lumas = [100.0] * 60
    lumas[45] = luma
    check = technical.t7(_frames(lumas), fps=FPS, finale_start_s=1.5)
    assert check.passed is ok
    if not ok:
        assert "1.50 s" in check.detail and "11.99" in check.detail


@pytest.mark.parametrize(("run", "ok"), [(15, True), (16, False)])
def test_t7_frozen_run_boundary_is_half_a_second(run: int, ok: bool) -> None:
    hashes = [f"h{i}" for i in range(90)]
    hashes[30 : 30 + run] = ["same"] * run
    check = technical.t7(_frames([100.0] * 90, hashes), fps=FPS, finale_start_s=2.5)
    assert check.passed is ok
    if not ok:
        span = f"from 1.00 s to {(30 + run) / FPS:.2f} s"
        assert f"frozen for {run / FPS:.2f} s {span}" in check.detail


def test_t7_ignores_a_frozen_finale() -> None:
    hashes = [f"h{i}" for i in range(90)]
    hashes[60:] = ["card"] * 30
    check = technical.t7(_frames([100.0] * 90, hashes), fps=FPS, finale_start_s=2.0)
    assert check.passed
    still_before = technical.t7(_frames([100.0] * 90, hashes), fps=FPS, finale_start_s=3.0)
    assert not still_before.passed and "frozen for 1.00 s from 2.00 s" in still_before.detail


def _moving_clip(path: Path, *, duration_s: float, vf: str = "") -> Path:
    """A 30 fps clip whose every frame differs (`testsrc2`), through `vf`."""
    argv = [ffmpeg.FFMPEG, "-v", "error", "-y", "-f", "lavfi",
            "-i", f"testsrc2=s=192x336:r=30:d={duration_s}"]  # fmt: skip
    if vf:
        argv += ["-vf", vf]
    argv += ["-t", f"{duration_s}", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt",
             "yuv420p", str(path)]  # fmt: skip
    ffmpeg.run(argv)
    return path


# Frame 29 held for 29 more frames (`tpad` clones it on CFR timestamps, which `loop`
# does not): 30 identical frames, 0.97-1.97 s, then the picture moves on. The encode
# is lossless (`-qp 0`): a lossy x264 keeps refining a held picture for frames on end
# before its P-frames become bit-identical, so the run would start late.
FREEZE_GRAPH = (
    "[0:v]trim=end=1,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop=29[a];"
    "[0:v]trim=start=1,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0[v]"
)
FROZEN_SECOND = "frozen for 1.00 s from 0.97 s to 1.97 s"
LOSSLESS = ["-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-pix_fmt", "yuv420p"]


def test_frame_stats_maps_limited_range_black_to_zero_luma(tmp_path: Path) -> None:
    black = tmp_path / "black.mp4"
    ffmpeg.run(
        [ffmpeg.FFMPEG, "-v", "error", "-y", "-f", "lavfi",
         "-i", "color=c=black:s=64x64:r=30:d=0.2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(black)]  # fmt: skip
    )
    stats = ffmpeg.frame_stats(black)
    assert len(stats) == 6 and [s.index for s in stats] == list(range(6))
    assert all(s.luma == 0.0 for s in stats), "Y=16 is black in limited range"
    assert len({s.hash for s in stats}) == 1
    assert ffmpeg.luma_full(16.0) == 0.0 and ffmpeg.luma_full(235.0) == 255.0
    assert ffmpeg.luma_full(16.0, full_range=True) == 16.0


def test_t7_on_a_real_clip_with_a_black_frame(tmp_path: Path) -> None:
    clean = _moving_clip(tmp_path / "clean.mp4", duration_s=2.0)
    assert technical.t7(ffmpeg.frame_stats(clean), fps=FPS, finale_start_s=1.5).passed
    dark = _moving_clip(
        tmp_path / "dark.mp4", duration_s=2.0,
        vf="drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,1.5,1.52)'",
    )  # fmt: skip
    check = technical.t7(ffmpeg.frame_stats(dark), fps=FPS, finale_start_s=1.8)
    assert not check.passed and "1 frame under 12/255" in check.detail and "1.50 s" in check.detail


def test_t7_on_a_real_clip_with_a_frozen_second(tmp_path: Path) -> None:
    frozen = tmp_path / "frozen.mp4"
    ffmpeg.run(
        [ffmpeg.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=192x336:r=30:d=3",
         "-filter_complex", FREEZE_GRAPH, "-map", "[v]", "-t", "3", *LOSSLESS,
         str(frozen)]  # fmt: skip
    )
    check = technical.t7(ffmpeg.frame_stats(frozen), fps=FPS, finale_start_s=2.8)
    assert not check.passed and FROZEN_SECOND in check.detail


# --- T10 no cut mid-word (3.1) --------------------------------------------------------------------


def test_t10_passes_boundaries_on_word_edges_and_in_silence() -> None:
    spans = [Span(start=0.0, end=0.5), Span(start=0.5, end=1.15), Span(start=2.0, end=6.0)]
    check = technical.t10(spans, FAKE_WORDS)
    assert (check.name, check.passed) == ("T10", True)
    assert "5 cut boundaries" in check.detail and "0.03" in check.detail


@pytest.mark.parametrize(("inside_s", "ok"), [(0.03, True), (0.031, False), (0.05, False)])
def test_t10_boundary_is_0_03_s_inside_a_word(inside_s: float, ok: bool) -> None:
    # 'hello' runs 0.2-0.34 s; a cut `inside_s` after its start.
    t = round(0.2 + inside_s, 3)
    spans = [Span(start=0.0, end=t), Span(start=t, end=6.0)]
    check = technical.t10(spans, FAKE_WORDS)
    assert check.passed is ok
    if not ok:
        assert f"cut at {t:.3f} s is inside 'hello' (0.2-0.34 s)" in check.detail


def test_t10_without_a_cut_list_fails() -> None:
    check = technical.t10(None, FAKE_WORDS)
    assert not check.passed and "work/cut.json" in check.detail


# --- run(job) ------------------------------------------------------------------------------


def _job_with(tmp_path: Path, short: Path, plan: PicturePlan,
              manifest: AssetManifest | None = None) -> jobs.Job:  # fmt: skip
    job = jobs.create(tmp_path)
    (job.work_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    (job.out_dir / "short.mp4").write_bytes(short.read_bytes())
    manifest = manifest or _manifest([_owner("a1")], [])
    assets.write_manifest(job.path, manifest)
    rights.write(job.path, manifest, plan)
    return job


@pytest.fixture(scope="session")
def speaking_short(tmp_path_factory: pytest.TempPathFactory, fixture_clip: Path) -> Path:
    """The fixture as a mastered short: its moving gradient and tone bursts (the fake
    transcript's twelve words) with the audio 1.7 dB down, from -12.3 to -14.0 LUFS, so
    T4 passes and T5, T7 and T10 have a real short to read."""
    out = tmp_path_factory.mktemp("speaking") / "short.mp4"
    ffmpeg.run(
        [ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(fixture_clip), "-c:v", "copy",
         "-af", "volume=-1.7dB", "-c:a", "aac", "-b:a", "192k", str(out)]  # fmt: skip
    )
    return out


def _with_speech(job: jobs.Job, clip: Path, *, voice_delay_ms: int = 0) -> None:
    """What `transcribing`, `planning` and `rendering` leave for T5 and T10: the fake
    transcript, its pages, the cut list, the cut clip and a voice stem lifted from the
    clip's audio, `voice_delay_ms` late."""
    transcript = FakeTranscriber().transcribe(clip)
    (job.work_dir / "asr.json").write_text(transcript.model_dump_json(), encoding="utf-8")
    plan = PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))
    finale = next(b for b in plan.beats if b.id == plan.finale.beat_id)
    spans = presenter.cut_list(plan)
    presenter.write_cut_list(job, spans)
    words = [w for _, w in presenter.words_on_cut(spans, transcript.words)]
    pages = Captions(pages=_pages(words, hide_from=finale.start))
    (job.work_dir / "captions.json").write_text(pages.model_dump_json(), encoding="utf-8")
    shutil.copy(clip, job.work_dir / "cut.mp4")
    stems = job.work_dir / "stems"
    stems.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(
        [ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(clip), "-map", "0:a:0",
         "-af", f"adelay={voice_delay_ms}:all=1", "-ac", "1", "-ar", "48000",
         "-c:a", "pcm_s16le", str(stems / "voice.wav")]  # fmt: skip
    )


def _speaking_job(
    tmp_path: Path, short: Path, plan: PicturePlan | None = None,
    manifest: AssetManifest | None = None, **speech: Any,
) -> jobs.Job:  # fmt: skip
    """A job whose short is `speaking_short` and whose work dir has what T5 and T10
    read; `_good_plan` keeps 0-5 s of it with the cold open lifted from the head."""
    job = _job_with(tmp_path, short, plan or _good_plan(), manifest)
    _with_speech(job, short, **speech)
    return job


def test_run_writes_qa_json_with_every_check_passing(tmp_path: Path, speaking_short: Path) -> None:
    job = _speaking_job(tmp_path, speaking_short)
    report = technical.run(job)
    assert [c.name for c in report.checks] == ALL_CHECKS
    assert report.passed
    on_disk = QaReport.model_validate_json((job.out_dir / "qa.json").read_text(encoding="utf-8"))
    assert on_disk == report
    assert all(c.detail for c in on_disk.checks)
    t6 = next(c for c in on_disk.checks if c.name == "T6")
    assert t6.passed and "work/stems/sfx.wav is absent" in t6.detail, "never a bare pass"
    assert [c.status for c in on_disk.checks[-3:]] == ["not_implemented"] * 3
    assert [c.passed for c in on_disk.checks[-3:]] == [False] * 3, "never a silent pass"
    t5 = next(c for c in on_disk.checks if c.name == "T5")
    assert "lip-sync lag +0.0 frames" in t5.detail


def test_run_fails_t5_on_a_voice_stem_three_frames_late(
    tmp_path: Path, speaking_short: Path
) -> None:
    job = _speaking_job(tmp_path, speaking_short, voice_delay_ms=100)
    report = technical.run(job)
    assert [c.name for c in report.checks] == ["T1", "T2", "T3", "T4", "T5"]
    assert report.failed is not None
    assert "lip-sync lag +3.0 frames (+100 ms), outside +/-1 frame" in report.failed.detail


def test_run_fails_t5_without_a_voice_stem(tmp_path: Path, speaking_short: Path) -> None:
    job = _speaking_job(tmp_path, speaking_short)
    (job.work_dir / "stems" / "voice.wav").unlink()
    report = technical.run(job)
    assert report.failed is not None and report.failed.name == "T5"
    assert "work/stems/voice.wav" in report.failed.detail


def test_run_fails_t7_on_a_frozen_second(tmp_path: Path, speaking_short: Path) -> None:
    frozen = tmp_path / "frozen.mp4"
    ffmpeg.run(
        [ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(speaking_short),
         "-filter_complex", FREEZE_GRAPH, "-map", "[v]", "-map", "0:a:0", "-t", "6",
         *LOSSLESS, "-c:a", "copy", str(frozen)]  # fmt: skip
    )
    job = _speaking_job(tmp_path, frozen)
    report = technical.run(job)
    assert [c.name for c in report.checks] == ["T1", "T2", "T3", "T4", "T5", "T6", "T7"]
    assert report.failed is not None and FROZEN_SECOND in report.failed.detail


def test_run_fails_t10_on_a_cut_inside_a_word(tmp_path: Path, speaking_short: Path) -> None:
    job = _speaking_job(tmp_path, speaking_short)
    presenter.write_cut_list(job, [Span(start=0.0, end=1.25), Span(start=1.25, end=6.0)])
    report = technical.run(job)
    assert [c.name for c in report.checks] == IMPLEMENTED
    assert report.failed is not None and report.failed.name == "T10"
    assert "cut at 1.250 s is inside 'this'" in report.failed.detail


def test_run_stops_at_the_first_failure_and_names_it(media: Media, tmp_path: Path) -> None:
    job = _job_with(
        tmp_path, media.clip(duration_s=2.0, width=720, height=1280, ext=".mp4"), _good_plan()
    )
    report = technical.run(job)
    assert not report.passed
    assert [c.name for c in report.checks] == ["T1"]
    assert report.failed is not None and report.failed.name == "T1"
    written = json.loads((job.out_dir / "qa.json").read_text(encoding="utf-8"))
    assert written["passed"] is False
    assert written["checks"][0]["name"] == "T1"


def test_run_reaches_t3_when_the_plan_is_the_problem(media: Media, tmp_path: Path) -> None:
    job = _job_with(tmp_path, media.clip(duration_s=2.0, ext=".mp4"), _good_plan(finale_len=0.5))
    report = technical.run(job)
    assert [c.name for c in report.checks] == ["T1", "T2", "T3"]
    assert report.failed is not None and report.failed.name == "T3"


def test_run_fails_t5_naming_the_missing_captions(media: Media, tmp_path: Path) -> None:
    job = _job_with(tmp_path, media.clip(duration_s=2.0, ext=".mp4"), _good_plan())
    report = technical.run(job)
    assert [c.name for c in report.checks] == ["T1", "T2", "T3", "T4", "T5"]
    assert report.failed is not None and "work/captions.json" in report.failed.detail


def test_run_fails_t8_on_too_many_rescues(tmp_path: Path, speaking_short: Path) -> None:
    manifest = _manifest([_owner("a1")], _rescues(2, total=3), rescued_max=1, runtime_s=5.0)
    job = _speaking_job(tmp_path, speaking_short, manifest=manifest)
    report = technical.run(job)
    assert [c.name for c in report.checks] == ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
    assert report.failed is not None and report.failed.name == "T8"


def test_run_fails_t9_on_an_incomplete_log(tmp_path: Path, speaking_short: Path) -> None:
    job = _speaking_job(tmp_path, speaking_short)
    (job.out_dir / "rights.json").write_text("[]", encoding="utf-8")
    report = technical.run(job)
    assert report.failed is not None and report.failed.name == "T9"
