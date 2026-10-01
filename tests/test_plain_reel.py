"""111g: the last rung. Any failure after planning ends in the plain reel - the speaker
video with captions, voice and music, no b-roll or overlays - delivered with a warning
that says what was dropped. `failed` is left for planning and for a plain reel that
cannot be made (no cut, no voice stem)."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from shortsmith import (
    assets,
    ffmpeg,
    fixture,
    jobs,
    pipeline,
    presenter,
    render,
    sound,
    styles,
    subproc,
)
from shortsmith.app import retry_refusal
from shortsmith.planner import FakePlanner, UnavailablePlanner
from shortsmith.qa.critic import FakeCritic
from shortsmith.qa.gate import FakeGate, Gate
from shortsmith.qa.technical import QaReport
from shortsmith.render import FakeRenderer, Renderer
from shortsmith.transcriber import FakeTranscriber
from tests.test_pipeline import BRIEF

# 112: the plain reel is a forgiving-mode net; strict mode fails loudly instead.
pytestmark = pytest.mark.usefixtures("forgiving")

SPECS = fixture.smoke_specs(styles.load_all(render.registry()))
Progress = Callable[[int], None] | None


def _uploaded(data_dir: Path, clip: Path) -> jobs.Job:
    job = jobs.create(data_dir, style="explainer", style_note="explainer, energetic")
    shutil.copyfile(clip, job.input_dir / "raw.mp4")
    (job.input_dir / "brief.md").write_text(BRIEF, encoding="utf-8")
    (job.input_dir / "refs.json").write_text("[]", encoding="utf-8")
    return job


def _sourcing() -> assets.Sourcing:
    return assets.Sourcing(sources={"web": assets.FakeImageSource("web")}, order=("web",))


def _run(job: jobs.Job, renderer: Renderer, gate: Gate | None = None,
         planner: object | None = None) -> jobs.Job:  # fmt: skip
    return pipeline.run_job(
        job, transcriber=FakeTranscriber(), planner=planner or FakePlanner(),  # pyright: ignore[reportArgumentType]
        renderer=renderer, gate=gate or FakeGate(), sourcing=_sourcing(), specs=SPECS,
        detector=presenter.FakeFaceDetector(), critic=FakeCritic(),
    )  # fmt: skip


class _Raises(FakeRenderer):
    """The full edit always raises `exc`; the plain reel is the fake's."""

    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self.exc = exc
        self.plain: list[Path] = []

    def render(self, job: jobs.Job, *, on_progress: Progress = None,
               library: sound.Library | None = None) -> Path:  # fmt: skip
        raise self.exc

    def render_plain(self, job: jobs.Job, *, on_progress: Progress = None,
                     library: sound.Library | None = None) -> render.PlainReel:  # fmt: skip
        self.plain.append(job.path)
        return super().render_plain(job, on_progress=on_progress, library=library)


def _assert_plain(done: jobs.Job, renderer: _Raises) -> None:
    assert done.status == "delivered", done.record.error
    assert renderer.plain == [done.path]
    assert done.record.plain_reel
    assert any(w.startswith(pipeline.PLAIN_LEAD) for w in done.record.warnings)
    assert any(d.choice == pipeline.PLAIN_CHOICE for d in done.record.decisions)
    assert "plain reel:" in done.log_path.read_text(encoding="utf-8")
    assert (done.out_dir / "short.mp4").is_file()


def test_a_picture_render_that_always_fails_delivers_the_plain_reel(
    tmp_path: Path, fixture_clip: Path
) -> None:
    renderer = _Raises(render.NetExhausted("b1 still failed drawn plain: boom", beats=("b1",),
                                           unnamed=False))  # fmt: skip
    done = _run(_uploaded(tmp_path, fixture_clip), renderer)
    _assert_plain(done, renderer)
    warning = next(w for w in done.record.warnings if w.startswith(pipeline.PLAIN_LEAD))
    assert "captions and music" in warning
    assert "pictures and effects were dropped" in warning


def test_a_mux_crash_delivers_the_plain_reel(tmp_path: Path, fixture_clip: Path) -> None:
    renderer = _Raises(render.RenderError("ffmpeg exited 1: mux: invalid argument"))
    _assert_plain(_run(_uploaded(tmp_path, fixture_clip), renderer), renderer)


def test_a_step_budget_running_out_delivers_the_plain_reel(
    tmp_path: Path, fixture_clip: Path
) -> None:
    renderer = _Raises(subproc.Killed("node was killed: its step ran past its time budget"))
    _assert_plain(_run(_uploaded(tmp_path, fixture_clip), renderer), renderer)


class _CrashingGate(FakeGate):
    def check(self, job: jobs.Job) -> QaReport:
        raise RuntimeError("qa crashed reading the picture")


def test_a_qa_crash_delivers_the_plain_reel_and_its_qa_only_warns(
    tmp_path: Path, fixture_clip: Path
) -> None:
    renderer = _Raises(RuntimeError("unused"))
    renderer.render = FakeRenderer.render.__get__(renderer)  # the full edit renders fine
    done = _run(_uploaded(tmp_path, fixture_clip), renderer, gate=_CrashingGate())
    _assert_plain(done, renderer)
    assert "plain reel: qa" in done.log_path.read_text(encoding="utf-8")


def test_a_sourcing_crash_delivers_the_plain_reel(
    tmp_path: Path, fixture_clip: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("the image source fell over")

    monkeypatch.setattr(pipeline, "_source", boom)
    renderer = _Raises(RuntimeError("unused"))
    _assert_plain(_run(_uploaded(tmp_path, fixture_clip), renderer), renderer)


class _NoPlain(_Raises):
    def render_plain(self, job: jobs.Job, *, on_progress: Progress = None,
                     library: sound.Library | None = None) -> render.PlainReel:  # fmt: skip
        raise render.PlainImpossible("work/cut.mp4 is missing and could not be cut: no input")


def test_with_no_cut_the_job_fails_with_an_honest_message(
    tmp_path: Path, fixture_clip: Path
) -> None:
    done = _run(_uploaded(tmp_path, fixture_clip), _NoPlain(render.RenderError("boom")))
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.message.endswith(pipeline.PLAIN_FAILED_TEXT)
    assert "cut.mp4" in done.record.error.detail


def test_a_planning_failure_still_fails(tmp_path: Path, fixture_clip: Path) -> None:
    renderer = _Raises(RuntimeError("unused"))
    planner = UnavailablePlanner("claude_code", "014")
    done = _run(_uploaded(tmp_path, fixture_clip), renderer, planner=planner)
    assert done.status == "failed"
    assert renderer.plain == []


def test_retry_on_a_plain_reel_job_re_renders_the_full_edit(
    tmp_path: Path, fixture_clip: Path
) -> None:
    done = _run(_uploaded(tmp_path, fixture_clip), _Raises(render.RenderError("boom")))
    assert done.record.plain_reel
    assert retry_refusal(done) == ""
    again = jobs.requeue(done)
    assert again.status == "uploaded"
    assert again.record.retry_from == "rendering"
    assert again.record.plain_reel is None
    assert not any(w.startswith(pipeline.PLAIN_LEAD) for w in again.record.warnings)
    good = FakeRenderer()
    final = _run(again, good)
    assert final.status == "delivered"
    assert good.jobs == [final.path]
    assert final.record.plain_reel is None


# --- the render side --------------------------------------------------------------------


def _rendered_job(tmp_path: Path, fixture_clip: Path, voice: Path) -> jobs.Job:
    """A delivered fake job whose cut and voice stem are real media."""
    done = _run(_uploaded(tmp_path, fixture_clip), FakeRenderer())
    shutil.copyfile(fixture_clip, done.work_dir / "cut.mp4")
    shutil.copyfile(voice, done.work_dir / "stems" / "voice.wav")
    return done


def test_the_plain_spec_is_the_presenter_with_captions(
    tmp_path: Path, fixture_clip: Path, voice: Path
) -> None:
    job = _rendered_job(tmp_path, fixture_clip, voice)
    spec = render.plain_spec(job)
    assert [b.kind for b in spec.beats] == ["presenter_full"]
    assert spec.beats[0].mode == "full"
    assert spec.beats[0].start_frame == 0 and spec.beats[0].end_frame == spec.frames
    assert spec.captions
    assert spec.title_strip is None


def test_the_remotion_plain_render_failing_too_delivers_the_ffmpeg_reel(
    tmp_path: Path, fixture_clip: Path, voice: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _rendered_job(tmp_path, fixture_clip, voice)

    def driver_fails(*_a: object, **_k: object) -> None:
        raise render.DriverFailed("remotion driver exited 1", frame=None, exact=False)

    def fake_mux(job: jobs.Job, **_k: object) -> Path:
        out = job.out_dir / "short.mp4"
        shutil.copyfile(job.work_dir / "picture.mp4", out)
        return out

    monkeypatch.setattr(render, "run_driver", driver_fails)
    monkeypatch.setattr(render, "mux", fake_mux)
    reel = render.render_plain(job)
    assert not reel.captions
    assert reel.music
    picture = job.work_dir / "picture.mp4"
    assert ffmpeg.video_size(picture) == ffmpeg.video_size(fixture_clip)
    assert "plain reel" in (job.work_dir / "render.log").read_text(encoding="utf-8")
    warning = pipeline.plain_warning("rendering", reel, timed_out=False)
    assert "captions" in warning.split("dropped")[0].split("The ")[-1]


def test_a_mux_crash_in_the_plain_reel_keeps_the_voice(
    tmp_path: Path, fixture_clip: Path, voice: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _rendered_job(tmp_path, fixture_clip, voice)

    def driver_fails(*_a: object, **_k: object) -> None:
        raise render.DriverFailed("remotion driver exited 1", frame=None, exact=False)

    def mux_crash(*_a: object, **_k: object) -> Path:
        raise RuntimeError("the sound director fell over")

    monkeypatch.setattr(render, "run_driver", driver_fails)
    monkeypatch.setattr(render, "mux", mux_crash)
    reel = render.render_plain(job)
    assert not reel.music
    assert ffmpeg.video_size(reel.path) == ffmpeg.video_size(fixture_clip)


def test_no_cut_and_no_input_cannot_make_the_plain_reel(
    tmp_path: Path, fixture_clip: Path, voice: Path
) -> None:
    job = _rendered_job(tmp_path, fixture_clip, voice)
    (job.work_dir / "cut.mp4").unlink()
    (job.input_dir / "raw.mp4").unlink()
    with pytest.raises(render.PlainImpossible, match="cut.mp4"):
        render.render_plain(job)


def test_the_plain_reel_renders_for_real(
    tmp_path: Path, fixture_clip: Path, voice: Path, library: sound.Library
) -> None:
    """The captioned Remotion render of the plain spec, then the real mux."""
    job = _rendered_job(tmp_path, fixture_clip, voice)
    reel = render.render_plain(job, library=library)
    assert reel.captions and reel.music
    assert ffmpeg.video_size(reel.path) == (render.WIDTH, render.HEIGHT)
