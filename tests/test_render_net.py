"""111d: the render-time net. A beat that still breaks the render once node runs is
named (from the driver's `failed frame=` line, or, with no frame, from one still per
beat), simplified to a plain photo or the gradient, and the picture rendered again: at
most `render.MAX_NET_ROUNDS` re-renders, each only simplifying more. The job page gets
one warning naming the beats; a beat that is already as plain as it gets and still
fails is the net's one exit (`render.NetExhausted`, where 111g hooks the plain reel).

The driver here is a stub node script (`render.DRIVER` patched): it fails while a beat
listed in `script.json` is still drawn as it was planned (kind `card`), so the test
watches the real argv, the real stdout protocol and the real parse."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from shortsmith import captions, fixture, jobs, media, render
from shortsmith.contracts import (
    BeatSpec,
    Constraints,
    PlanRequest,
    PlanStyle,
    RenderSpec,
    StickerSpec,
    VisualSpec,
)
from shortsmith.fixture import make_clip
from shortsmith.jobs import Job, JobRecord
from shortsmith.planner import FakePlanner
from shortsmith.transcriber import FakeTranscriber

# 112b: the net simplifies beats, a downgrade forgiving keeps (strict is 112b phase 2's).
pytestmark = pytest.mark.usefixtures("forgiving")

BEATS = 5
STUB = r"""
import fs from "node:fs";
const here = new URL(".", import.meta.url);
const script = JSON.parse(fs.readFileSync(new URL("script.json", here), "utf-8"));
const argv = process.argv.slice(2);
const arg = (k) => argv[argv.indexOf(`--${k}`) + 1];
const spec = JSON.parse(fs.readFileSync(arg("spec"), "utf-8"));
fs.appendFileSync(new URL("calls.txt", here), argv[0] + "\n");
const broken = (b) =>
  (script.bad.includes(b.id) && b.kind === "card") || (script.always ?? []).includes(b.id);
if (argv[0] === "still") {
  for (const f of arg("frames").split(",").map(Number)) {
    const beat = spec.beats.find((b) => b.start_frame <= f && f < b.end_frame);
    if (beat && broken(beat)) console.error(`still frame=${f}: Error loading image ${beat.id}.jpg`);
    console.log(`still frame=${f} ${beat && broken(beat) ? "failed" : "ok"}`);
  }
  process.exit(0);
}
const bad = spec.beats.find(broken);
if (!bad) {
  fs.writeFileSync(arg("out"), "picture");
  console.log(`progress ${spec.frames}/${spec.frames}`);
  console.log(`done frames=${spec.frames} render_s=0.1 bundle_s=0.0`);
  process.exit(0);
}
console.error("Error: Error loading image with src: http://127.0.0.1/clip-1.mp4");
if (script.mode === "unknown") {
  console.log("failed frame=unknown");
} else if (script.mode === "progress") {
  console.log(`progress ${bad.start_frame}/${spec.frames}`);
  console.log(`failed frame=${bad.start_frame} via=progress`);
} else {
  console.log(`failed frame=${Math.floor((bad.start_frame + bad.end_frame) / 2)} via=error`);
}
process.exit(1);
"""


def _image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (320, 400), (170, 85, 51)).save(path, format="JPEG")
    return path


def _visual(src: Path, treatment: str = "card") -> VisualSpec:
    return VisualSpec.model_validate({
        "treatment": treatment, "src": str(src), "width": 320, "height": 400, "zoom": 1.0,
        "focus_x": 0.5, "focus_y": 0.5, "scale_from": 1.0, "scale_to": 1.08, "pan_px": 0.0,
    })  # fmt: skip


def _spec(job: Job, *, clip_for: str | None = None) -> RenderSpec:
    """Five `card` beats b1..b5 over the fixture's frames, each with a sticker and a
    text pop (the overlays a plain beat drops); `clip_for` draws that beat from a clip."""
    transcript = FakeTranscriber().transcribe(Path("unused.mp4"))
    plan = FakePlanner().plan_picture(PlanRequest(
        brief="Topic: a six-second synthetic clip.", style=PlanStyle(name="explainer"),
        style_note="explainer", transcript=transcript, references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    ))  # fmt: skip
    caps = captions.build(transcript, plan, render.loaded_styles()["explainer"])
    spec = render.build_spec(
        plan, caps, presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
    )  # fmt: skip
    photo = _image(job.work_dir / "assets" / "h" / "photo.jpg")
    sticker = StickerSpec(name="star", src=str(photo), left=10, top=10, size=200,
                          scale_from=0.6, at_s=0.2, pop_s=0.3, until_s=1.0, float_px=6,
                          float_period_s=2, shadow_px=8)  # fmt: skip
    step = spec.frames // BEATS
    template = spec.beats[0]
    beats: list[BeatSpec] = []
    for i in range(BEATS):
        beat_id = f"b{i + 1}"
        visual = _visual(photo)
        if beat_id == clip_for:
            clip = make_clip(job.work_dir / "assets" / "c" / "clip-1.mp4", duration_s=1.0,
                             width=320, height=240, audio=False)  # fmt: skip
            visual = _visual(clip, treatment="clip")
        end = spec.frames if i == BEATS - 1 else (i + 1) * step
        beats.append(template.model_copy(update={
            "id": beat_id, "start_frame": i * step, "end_frame": end, "mode": "pip",
            "kind": "card", "visual": visual, "stickers": (sticker,), "enter": "cut",
        }))  # fmt: skip
    return spec.model_copy(update={"beats": beats})


class Net:
    """A job whose picture render goes through the stub driver."""

    def __init__(self, job: Job, stub_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.job = job
        self.stub_dir = stub_dir
        self.monkeypatch = monkeypatch
        self.spec: RenderSpec | None = None

    def script(self, bad: list[str], mode: str = "frame", always: list[str] | None = None,
               clip_for: str | None = None) -> None:  # fmt: skip
        """The stub's failing beats and how it reports them; the job's spec."""
        (self.stub_dir / "script.json").write_text(
            json.dumps({"bad": bad, "mode": mode, "always": always or []}), encoding="utf-8"
        )
        spec = _spec(self.job, clip_for=clip_for)
        self.spec = spec

        def spec_for_job(*_a: object, **_k: object) -> RenderSpec:
            return spec

        self.monkeypatch.setattr(render, "spec_for_job", spec_for_job)

    def calls(self) -> list[str]:
        path = self.stub_dir / "calls.txt"
        return path.read_text(encoding="utf-8").split() if path.is_file() else []

    def sent(self) -> RenderSpec:
        return RenderSpec.model_validate_json(
            (self.job.work_dir / "render_spec.json").read_text(encoding="utf-8")
        )

    def record(self) -> JobRecord:
        return jobs.load(self.job.path).record

    def log(self) -> str:
        return (self.job.path / "job.log").read_text(encoding="utf-8")


@pytest.fixture
def net(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Net:
    return _net(tmp_path, monkeypatch)


@pytest.fixture
def strict_net(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Net:
    """112b: a job stamped strict (the module's `forgiving` pin is overridden first)."""
    monkeypatch.setenv("QUALITY_MODE", "strict")
    return _net(tmp_path, monkeypatch)


def _net(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Net:
    job = jobs.create(tmp_path / "job")
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    stub = stub_dir / "driver.mjs"
    stub.write_text(STUB, encoding="utf-8")
    monkeypatch.setattr(render, "DRIVER", stub)
    return Net(job, stub_dir, monkeypatch)


def _plain(spec: RenderSpec, beat_id: str) -> bool:
    beat = next(b for b in spec.beats if b.id == beat_id)
    return beat.kind != "card" and not beat.stickers and not beat.text_pops


def test_a_failed_frame_inside_b3_simplifies_b3_and_the_picture_renders(net: Net) -> None:
    net.script(bad=["b3"])

    out = render.render_picture(net.job)

    assert out.is_file()
    assert net.calls() == ["render", "render"]
    sent = net.sent()
    assert _plain(sent, "b3")
    assert [b.id for b in sent.beats if _plain(sent, b.id)] == ["b3"]
    b3 = next(b for b in sent.beats if b.id == "b3")
    assert b3.visual is not None and b3.visual.treatment == "photo"
    assert net.spec is not None and sent.captions == net.spec.captions
    warnings = net.record().warnings
    assert any("beat 3" in w and "simple picture" in w for w in warnings), warnings
    assert [d.beat_id for d in net.record().decisions] == ["b3"]
    assert "rescue: " in net.log()


def test_the_last_progress_count_names_the_beats_it_may_be_in(net: Net) -> None:
    net.script(bad=["b2"], mode="progress")

    render.render_picture(net.job)

    sent = net.sent()
    assert _plain(sent, "b2")
    assert not _plain(sent, "b4") and not _plain(sent, "b5")


def test_an_unknown_frame_is_found_by_one_still_per_beat(net: Net) -> None:
    net.script(bad=["b2"], mode="unknown")

    render.render_picture(net.job)

    assert net.calls() == ["render", "still", "render"]
    sent = net.sent()
    assert [b.id for b in sent.beats if _plain(sent, b.id)] == ["b2"]


def test_a_clip_beat_is_simplified_to_its_frame_grab(net: Net) -> None:
    net.script(bad=["b3"], clip_for="b3")

    render.render_picture(net.job)

    b3 = next(b for b in net.sent().beats if b.id == "b3")
    assert b3.visual is not None and b3.visual.treatment == "photo"
    assert media.probe(Path(b3.visual.src)) == "image"


def test_three_failing_beats_in_a_row_still_deliver(net: Net) -> None:
    net.script(bad=["b1", "b3", "b5"])

    render.render_picture(net.job)

    assert net.calls() == ["render"] * 4
    warnings = [w for w in net.record().warnings if "simple picture" in w]
    assert len(warnings) == 1
    assert warnings[0].startswith("beats 1, 3 and 5 were shown as simple pictures"), warnings


def test_a_fourth_round_never_happens(net: Net) -> None:
    net.script(bad=["b1", "b2", "b3", "b4"])

    with pytest.raises(render.NetExhausted):
        render.render_picture(net.job)

    assert net.calls() == ["render"] * (render.MAX_NET_ROUNDS + 1)


def test_a_beat_already_plain_that_still_fails_exhausts_the_net(net: Net) -> None:
    net.script(bad=[], always=["b3"])

    with pytest.raises(render.NetExhausted) as caught:
        render.render_picture(net.job)

    assert caught.value.beats == ("b3",)
    assert not caught.value.unnamed
    # b3 went photo, then gradient, and failed as the gradient: then the net stops.
    assert net.calls() == ["render"] * 3
    b3 = next(b for b in net.sent().beats if b.id == "b3")
    assert b3.visual is None


def test_an_unknown_frame_no_still_explains_is_unnamed(
    net: Net, monkeypatch: pytest.MonkeyPatch
) -> None:
    net.script(bad=["b2"], mode="unknown")
    # The stills all pass: the beat breaks only inside the full render.
    def no_failing_still(*_a: object, **_k: object) -> set[int]:
        return set()

    monkeypatch.setattr(render, "run_stills", no_failing_still)

    with pytest.raises(render.NetExhausted) as caught:
        render.render_picture(net.job)

    assert caught.value.unnamed
    assert caught.value.beats == ()


# --- 112b: strict mode - the diagnosis runs, the job stops once, nothing is simplified ------


def _asked_frames(net: Net) -> list[int]:
    log = (net.job.work_dir / "render-stills.log").read_text(encoding="utf-8")
    argv = next(line for line in log.splitlines() if "--frames" in line)
    return [int(f) for f in argv.split("--frames ")[1].split()[0].split(",")]


def test_strict_a_render_failure_stops_naming_the_beat_after_a_stills_pass_over_every_beat(
    strict_net: Net,
) -> None:
    from shortsmith import quality

    strict_net.script(bad=["b3"])

    with pytest.raises(quality.QualityStop) as stop:
        render.render_picture(strict_net.job)

    assert strict_net.calls() == ["render", "still"]  # the diagnosis; never a re-render
    assert len(_asked_frames(strict_net)) == BEATS  # every beat, not only those near it
    [finding] = stop.value.findings
    assert finding.beat == "b3" and finding.kind == "card"
    assert "Error loading image b3.jpg" in finding.cause
    assert not _plain(strict_net.sent(), "b3")
    assert strict_net.record().decisions == []
    assert "render net: the render failed at frame" in strict_net.log()


def test_strict_every_failing_beat_is_named_in_one_stop(strict_net: Net) -> None:
    from shortsmith import quality

    strict_net.script(bad=[], mode="unknown", always=["b2", "b4"])

    with pytest.raises(quality.QualityStop) as stop:
        render.render_picture(strict_net.job)

    assert strict_net.calls() == ["render", "still"]
    assert [f.beat for f in stop.value.findings] == ["b2", "b4"]
    assert all("Error loading image" in f.cause for f in stop.value.findings)


def test_strict_a_failure_no_still_explains_stops_with_the_renders_error(
    strict_net: Net, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shortsmith import quality

    strict_net.script(bad=["b2"], mode="unknown")

    def no_failing_still(*_a: object, **_k: object) -> set[int]:
        return set()

    monkeypatch.setattr(render, "run_stills", no_failing_still)

    with pytest.raises(quality.QualityStop) as stop:
        render.render_picture(strict_net.job)

    [finding] = stop.value.findings
    assert finding.beat is None
    assert "Error loading image with src" in finding.cause
    assert strict_net.calls() == ["render"]
