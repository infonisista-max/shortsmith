"""`python -m shortsmith.smoke`: fixture -> job -> fake transcriber -> fake planner ->
work/{asr,plan,sound,captions}.json -> Remotion -> work/picture.mp4 -> out/short.mp4
-> assets through the fake sources, out/rights.json and out/credits.md (016) ->
T1-T13 in out/qa.json -> out/contact.jpg, uploaded -> transcribing -> planning ->
sourcing -> rendering -> qa -> delivered, exit 0 with one summary line, non-zero on a
failed assertion. The render is the real engine (12.1), so the walk is the slow test
in the suite."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from shortsmith import assets, contact_sheet, ffmpeg, fixture, render, rights, smoke, styles
from shortsmith.contracts import (
    PicturePlan,
    PlanFeedback,
    PlanRequest,
    RenderSpec,
    SoundStory,
    Transcript,
    ValidatedPlan,
)
from shortsmith.jobs import load
from shortsmith.planner import FakePlanner
from shortsmith.qa import technical
from shortsmith.transcriber import FakeTranscriber, Transcriber


def test_run_smoke_walks_the_path(tmp_path: Path) -> None:
    result = smoke.run_smoke(tmp_path)
    job = load(result.job_dir)
    assert job.status == "delivered"
    assert (job.input_dir / "raw.mp4").is_file()
    assert (job.input_dir / "brief.md").is_file()
    assert (job.input_dir / "refs.json").is_file()
    assert job.record.input is not None and job.record.input.width == 1080
    asr = Transcript.model_validate_json((job.work_dir / "asr.json").read_text(encoding="utf-8"))
    assert len(asr.words) == 12
    plan = PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))
    SoundStory.model_validate_json((job.work_dir / "sound.json").read_text("utf-8"))
    assert (job.work_dir / "captions.json").is_file()
    assert plan.beats[-1].end == 6.0
    # 009: the grammar ran; the fake plan's only clamp is the keyword trim (6.1).
    validated = ValidatedPlan.model_validate_json(
        (job.work_dir / "plan.validated.json").read_text("utf-8")
    )
    assert validated.picture == plan and [c.rule for c in validated.clamps] == ["6.1"]
    assert (job.work_dir / "plan.raw.json").is_file()
    picture = job.work_dir / "picture.mp4"
    assert picture.is_file() and (job.work_dir / "render_spec.json").is_file()
    (video,) = ffmpeg.probe(picture)["streams"]
    assert video["codec_name"] == "h264" and int(video["nb_frames"]) == 180
    # 005: the cut, the stems and the muxed short with the picture stream untouched.
    cut = ffmpeg.probe(job.work_dir / "cut.mp4")["streams"]
    assert [s["codec_type"] for s in cut] == ["video", "audio"]
    assert int(cut[0]["has_b_frames"]) == 0 and cut[0]["avg_frame_rate"] == "30/1"
    assert (job.work_dir / "stems" / "voice.wav").is_file()
    assert (job.work_dir / "stems" / "mix.wav").is_file()
    short = job.out_dir / "short.mp4"
    assert short.is_file()
    assert {s["codec_type"] for s in ffmpeg.probe(short)["streams"]} == {"video", "audio"}
    assert ffmpeg.video_md5(short) == ffmpeg.video_md5(picture)
    assert float(ffmpeg.probe(short)["format"]["duration"]) == pytest.approx(6.0, abs=0.1)
    assert ffmpeg.measure_loudness(short).integrated == pytest.approx(-14.0, abs=1.0)
    # 006: the technical gate and the contact sheet, then `delivered`.
    report = technical.load_report(job)
    assert report is not None and report.passed
    assert [c.name for c in report.checks] == list(technical.CHECK_ORDER)
    # 031 / 032: every check ran on the real short and the real files, and passed.
    assert all(c.status == "pass" for c in report.checks)
    # 033: the fake critic scored the delivered short from the real strips, advisory.
    assert report.critic is not None and report.critic.status == "scored"
    assert report.critic.advisory is True and report.critic.model == "fake"
    assert len(report.critic.lines) == 10 and report.critic.category == plan.category
    # 016: every sourced beat found its picture through the fakes, none rescued; the
    # photo beat is a full-bleed photo, the card beat a card; the rights log is complete.
    manifest = assets.load_manifest(job.path)
    assert manifest is not None and manifest.rescued == 0
    assert [b.beat_id for b in manifest.beats] == [
        b.id for b in plan.beats
        if b.subject_kind is not None and b.kind not in assets.NOT_SOURCED
    ]  # fmt: skip
    # 020: the map beat is drawn, not sourced, and its markers are fake-geocoded
    spec = RenderSpec.model_validate_json((job.work_dir / "render_spec.json").read_text("utf-8"))
    layout = next(b for b in spec.beats if b.kind == "map").map
    assert layout is not None and [m.source for m in layout.markers] == ["fake", "fake"]
    treatments = {b.beat_id: b.treatment for b in manifest.beats}
    assert (treatments["b01"], treatments["b02"]) == ("photo", "card")  # 055: the opening
    # 058: b04 is the clip beat, sourced from the fake Pexels video source as a muted clip
    assert treatments["b04"] == "clip"
    clip = manifest.asset("a3")
    assert clip is not None and clip.kind == "clip" and clip.origin == "pexels"
    assert (job.path / clip.file).suffix == ".mp4"
    assert clip.duration_s == pytest.approx(3.0, abs=0.1)
    b04 = next(b for b in spec.beats if b.id == "b04")
    assert b04.visual is not None and b04.visual.treatment == "clip" and b04.visual.speed == 1.0
    rows = rights.load(job.path)
    assert rows is not None and rights.completeness(rows, manifest, plan) == []
    assert [r.kind for r in rows if r.id == "a3"] == ["clip"]
    credits_text = (job.out_dir / "credits.md").read_text("utf-8")
    assert credits_text.startswith("Photo: fake ")
    assert "Video by fake pexels video on Pexels via https://fake.invalid/" in credits_text
    sheet = job.out_dir / "contact.jpg"
    assert sheet.is_file() and sheet.stat().st_size < contact_sheet.MAX_BYTES
    with Image.open(sheet) as image:
        assert image.format == "JPEG" and image.width == contact_sheet.SHEET_W
    log = job.log_path.read_text(encoding="utf-8").splitlines()
    noted = [line.split(" ", 1)[1] for line in log]
    # 022: the steps' own notes sit between the status lines, so the trail is the status
    # lines alone; the sound director's summary is one of those notes, inside `rendering`.
    assert [line for line in noted if line == "created uploaded" or " -> " in line] == [
        "created uploaded",
        "uploaded -> transcribing",
        "transcribing -> planning",
        "planning -> sourcing",
        "sourcing -> rendering",
        "rendering -> qa",
        "qa -> delivered",
    ]
    # 054 (1): the bed decision ("from the library") precedes the summary line, both
    # inside `rendering`, and the placed cues are one line each.
    (decision,) = [line for line in noted if line.startswith("sound: bed ") and "library" in line]
    (sound_note,) = [line for line in noted if line.startswith("sound: bed ") and " cues (" in line]
    # 076: the bed per story part, by its closed mood
    assert "for hook: mysterious_curiosity from the approved library" in decision
    assert noted.index("sourcing -> rendering") < noted.index(decision) < noted.index(sound_note)
    assert noted.index(sound_note) < noted.index("rendering -> qa")
    assert any(line.startswith("sound: ") and "placed at" in line for line in noted)
    assert "ok" in result.summary and job.id in result.summary
    assert "180 frames" in result.summary and "short" in result.summary
    assert "clip b04" in result.summary and " render " in result.summary  # 058
    assert "T1 T2 T3 T4 T5 T6 T7 T8 T9 T10 T11 T12 T13 pass" in result.summary
    assert f"critic {report.critic.overall}/10 advisory" in result.summary
    assert "not implemented" not in result.summary and "contact" in result.summary
    assert f"{len(manifest.assets)} assets" in result.summary


def test_main_prints_one_line_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert smoke.main([]) == 0
    out = capsys.readouterr()
    assert out.out.count("\n") == 1
    assert out.out.startswith("smoke ok")


class _ShortTranscriber(Transcriber):
    """Ten of the twelve words: the last burst is dropped whole, so the fake plan still
    passes the grammar (a half-kept burst would snap b10 under `min_s` first, 055) and
    the smoke fails on its own word count."""

    def transcribe(self, audio: Path) -> Transcript:
        full = FakeTranscriber().transcribe(audio)
        return full.model_copy(update={"words": full.words[:10]})


def test_failed_assertion_exits_non_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert smoke.main([], transcriber=_ShortTranscriber()) != 0
    out = capsys.readouterr()
    assert out.out == ""
    assert "smoke FAILED" in out.err and "12" in out.err


class _GappyPlanner(FakePlanner):
    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        plan = super().plan_picture(request)
        first = plan.beats[0].model_copy(update={"end": plan.beats[0].end - 0.1})
        return plan.model_copy(update={"beats": [first, *plan.beats[1:]]})


def test_plan_assertion_failure_names_the_gap(capsys: pytest.CaptureFixture[str]) -> None:
    """009: the grammar now catches the gap at `planning` (3.1), twice, and the smoke
    reports the failed job with the violation list."""
    assert smoke.main([], planner=_GappyPlanner()) != 0
    err = capsys.readouterr().err
    assert "failed at planning" in err and "gap" in err and "(3.1)" in err


def test_main_passes_the_style_flag_to_run_smoke(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """048: `--style hitech` selects the draft; no flag keeps the default. 061:
    `--text-pops` turns the pops style on; 063: `--bubbles` the bubbles style; 062:
    `--stickers` the stickers style; no flag keeps all three off."""
    seen: list[tuple[str, bool, bool, bool]] = []

    def fake_run(root: Path, **kwargs: object) -> smoke.SmokeResult:
        seen.append((str(kwargs.get("style")), bool(kwargs.get("text_pops")),
                     bool(kwargs.get("bubbles")), bool(kwargs.get("stickers_on"))))  # fmt: skip
        picture = root / "picture.mp4"
        picture.write_bytes(b"")
        return smoke.SmokeResult(job_dir=root, summary="smoke ok: faked", picture=picture)

    monkeypatch.setattr(smoke, "run_smoke", fake_run)
    monkeypatch.delenv(smoke.KEEP_ENV, raising=False)
    assert smoke.main(["--style", "hitech"]) == 0
    assert smoke.main([]) == 0
    assert smoke.main(["--text-pops"]) == 0
    assert smoke.main(["--bubbles"]) == 0
    assert smoke.main(["--stickers"]) == 0
    assert seen == [
        ("hitech", False, False, False), ("explainer", False, False, False),
        ("explainer", True, False, False), ("explainer", False, True, False),
        ("explainer", False, False, True),
    ]  # fmt: skip
    assert capsys.readouterr().out == "smoke ok: faked\n" * 5


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


def test_module_entry_point() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "shortsmith.smoke"], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("smoke ok")
