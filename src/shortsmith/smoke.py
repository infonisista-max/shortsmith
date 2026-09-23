"""The fourth feedback loop: `python -m shortsmith.smoke`.

Walks the same path the tests walk, end to end, with every fake and no network:
generate the 12.1 fixture, ingest it the way the upload route does (`ingest.accept`,
not HTTP), run the job through the worker (`pipeline.Worker.run_next`, the same code
the web app's thread runs) with the fake transcriber, the fake planner, the fake
image sources (016: web answers every query but the photo beat's, Commons has that
one as a full-bleed portrait) and the real Remotion renderer, assert `work/asr.json`,
`work/plan.json`, `work/sound.json`, `work/captions.json`, `work/assets.json` (every
sourced beat found, none rescued, the photo beat a photo and the card beat a card),
`out/rights.json` complete and `out/credits.md`, `work/picture.mp4` (H.264,
1080x1920, round(6 x 30) frames, silent), the sound director's bed, cues, stems and
balance report from a synthesised catalogue (022),
`out/short.mp4`, `out/qa.json` with T1-T4,
T8 and T9 passing, `out/contact.jpg` under
2 MB at the sheet's width, and the job's `uploaded -> ... -> qa -> delivered` trail,
print one summary line and exit 0. Any failed assertion exits non-zero with the
failing check on stderr. Later tickets extend this walk until it asserts T1-T13
(decision 12.1); over ninety seconds is a bug.

The fixture is six seconds long, so smoke lowers only `Limits.min_duration_s`; every
other 2.1 limit stays at its default.

Everything happens in a temp directory that is removed afterwards, unless
`SHORTSMITH_SMOKE_KEEP=1` (ticket 049): then the run lands under `work/smoke/` beneath
the current directory, survives, and the summary line ends with the absolute path of
`picture.mp4` so the operator can watch the render. `work/` is git-ignored.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from shortsmith import (
    assets,
    contact_sheet,
    ffmpeg,
    fixture,
    infographics,
    ingest,
    jobs,
    pipeline,
    render,
    rights,
    sound,
    styles,
)
from shortsmith.contracts import (
    TIER1_KINDS,
    Captions,
    PicturePlan,
    RenderSpec,
    SoundStory,
    Transcript,
    ValidatedPlan,
)
from shortsmith.ingest import Limits, VideoUpload
from shortsmith.planner import FakePlanner, Planner, kinds_named
from shortsmith.qa import technical
from shortsmith.render import Renderer
from shortsmith.transcriber import FakeTranscriber, Transcriber

EXPECTED_WORDS = 12
EXPECTED_FRAMES = round(fixture.DURATION_S * fixture.FPS)
LAST_STATUS: jobs.Status = "delivered"
TRAIL = [
    "created uploaded",
    "uploaded -> transcribing",
    "transcribing -> planning",
    "planning -> sourcing",
    "sourcing -> rendering",
    "rendering -> qa",
    "qa -> delivered",
]
TECHNICAL_CHECKS = ("T1", "T2", "T3", "T4", "T8", "T9")  # grows with the gate tickets
SMOKE_BRIEF = (
    "Topic: a six-second synthetic clip. Angle: prove the pipeline end to end. "
    "Must-say: twelve words on six tone bursts. Hook wish: none."
)
SMOKE_STYLE_LINE = "explainer, energetic"
SMOKE_LIMITS = Limits(min_duration_s=fixture.DURATION_S)
# 016: the fake plan's photo beat (b03) asks for this; Commons answers it with a
# full-bleed portrait, web (which is always a card, 5.1) answers everything else.
PHOTO_QUERY = "slow colour gradient sky"


def smoke_sourcing() -> assets.Sourcing:
    return assets.Sourcing(
        sources={
            "web": assets.FakeImageSource("web", nothing_for={PHOTO_QUERY}),
            "commons": assets.FakeImageSource("commons", sizes={PHOTO_QUERY: (1080, 1920)}),
        },
        order=("web", "commons"),
        judge=assets.FakeRelevanceJudge(),  # 017: the judge runs, on no paid call
        generator=assets.FakeImageGenerator(),  # 019: rung 2, on no paid call either
    )


class SmokeFailure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


KEEP_ENV = "SHORTSMITH_SMOKE_KEEP"
KEEP_DIR = Path("work") / "smoke"
TMP_PREFIX = "shortsmith-smoke-"


@dataclass(frozen=True)
class SmokeResult:
    job_dir: Path
    summary: str
    picture: Path


def run_smoke(
    root: Path,
    *,
    transcriber: Transcriber | None = None,
    planner: Planner | None = None,
    renderer: Renderer | None = None,
) -> SmokeResult:
    started = time.perf_counter()
    transcriber = transcriber or FakeTranscriber()
    planner = planner or FakePlanner()

    clip = fixture.make_fixture(root / "fixture" / "fixture.mp4")
    check(clip.stat().st_size < 1_000_000, "fixture must be under 1 MB (12.1)")

    # 022: the synthesised audio catalogue, the one the shipped file will hold after 025.
    library = sound.load_catalogue(fixture.make_catalogue(root / "audio"))
    check(bool(library.beds()) and bool(library.sfx()), "the synthesised catalogue is empty")

    # 008: every spec loads against the registry, and the style line resolves in code.
    specs = styles.load_all(render.registry())
    check(styles.shipped(specs) == ["explainer"], f"shipped styles: {styles.shipped(specs)}")
    resolution = styles.resolve(SMOKE_STYLE_LINE, specs)
    check(resolution.name == "explainer" and resolution.notice == "", f"resolved {resolution}")

    job = ingest.accept(
        root / "data",
        video=VideoUpload(path=clip, original_name="fixture.mp4"),
        brief=SMOKE_BRIEF,
        style=resolution,
        references=[],
        limits=SMOKE_LIMITS,
    )
    check(job.status == "uploaded", f"ingest left the job {job.status!r}, not 'uploaded'")
    check(
        (job.record.style, job.record.style_note) == ("explainer", SMOKE_STYLE_LINE),
        "job.json does not carry the resolved style and note",
    )
    check((job.input_dir / "raw.mp4").is_file(), "ingest did not write input/raw.mp4")
    check((job.input_dir / "brief.md").is_file(), "ingest did not write input/brief.md")
    check((job.input_dir / "refs.json").is_file(), "ingest did not write input/refs.json")

    # 009: the fake plan is judged by the fixture-shaped copy of explainer.
    worker = pipeline.Worker(
        transcriber=transcriber, planner=planner, renderer=renderer,
        sourcing=smoke_sourcing(), specs=fixture.smoke_specs(specs), library=library,
    )  # fmt: skip
    worker.submit(job.path)
    check(worker.run_next(), "the worker had nothing to run")

    # Assertions: re-read from disk, the way the next step will.
    reloaded = jobs.load(job.path)
    if reloaded.record.error is not None:
        err = reloaded.record.error
        raise SmokeFailure(f"job failed at {err.step}: {err.message} ({err.detail.strip()})")
    check(reloaded.status == LAST_STATUS, f"job status is {reloaded.status}")
    # 011: every fake is free, so the ledger stays empty (and no cap can be crossed).
    check(reloaded.record.cost == [], f"fake-only job has ledger rows: {reloaded.record.cost}")
    asr_path = job.work_dir / "asr.json"
    check(asr_path.is_file(), "worker did not write work/asr.json")
    on_disk = Transcript.model_validate_json(asr_path.read_text(encoding="utf-8"))
    check(
        len(on_disk.words) == EXPECTED_WORDS,
        f"expected {EXPECTED_WORDS} words in work/asr.json, got {len(on_disk.words)}",
    )
    for i, burst_start in enumerate(fixture.BURST_TIMES):
        burst_end = burst_start + fixture.BURST_LEN_S
        for w in on_disk.words[2 * i : 2 * i + 2]:
            check(
                burst_start <= w.start < w.end <= burst_end + 1e-9,
                f"word {w.text!r} [{w.start}, {w.end}] is outside burst {i} "
                f"[{burst_start}, {burst_end}]",
            )
    plan_path, sound_path, captions_path, validated_path = (
        job.work_dir / name
        for name in ("plan.json", "sound.json", "captions.json", "plan.validated.json")
    )
    for path in (plan_path, sound_path, captions_path, validated_path):
        check(path.is_file(), f"planning did not write work/{path.name}")
    plan = PicturePlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    story = SoundStory.model_validate_json(sound_path.read_text(encoding="utf-8"))
    pages = Captions.model_validate_json(captions_path.read_text(encoding="utf-8")).pages
    # 009: the validated plan is what plan.json / sound.json hold, with zero violations
    # (or the job would have failed at planning) and the clamps logged.
    validated = ValidatedPlan.model_validate_json(validated_path.read_text(encoding="utf-8"))
    check(
        validated.picture == plan and validated.sound == story,
        "plan.validated.json disagrees with plan.json / sound.json",
    )
    check(
        [c.rule for c in validated.clamps] == ["6.1"],
        f"expected one keyword clamp on the fake plan, got {[str(c) for c in validated.clamps]}",
    )
    check(
        plan.beats[0].start == 0.0 and plan.beats[-1].end == fixture.DURATION_S,
        "plan beats do not tile the fixture",
    )
    check(
        all(a.end == b.start for a, b in zip(plan.beats, plan.beats[1:], strict=False)),
        "plan beats have a gap or overlap",
    )
    missing = set(TIER1_KINDS) - kinds_named(plan)
    check(not missing, f"plan does not name every tier-1 kind: {sorted(missing)}")
    beat_ids = {b.id for b in plan.beats}
    check(all(c.beat_id in beat_ids for c in story.cues), "a sound cue names an unknown beat")
    check(all(2 <= len(p.word_indices) <= 4 for p in pages), "a caption page is not 2-4 words")
    # 010: every word before the finale beat is paged once, in order; none after it.
    finale_start = next(b.start for b in plan.beats if b.id == plan.finale.beat_id)
    before = [i for i, w in enumerate(on_disk.words) if w.start < finale_start]
    check(
        [i for p in pages for i in p.word_indices] == before,
        f"caption pages do not cover exactly the words before the finale ({before})",
    )
    check(all(p.end <= finale_start for p in pages), "a caption page shows into the finale")
    check(
        all(1 <= p.lines <= 2 and len(p.words) == len(p.word_indices) for p in pages),
        "a caption page is not laid out in one or two lines",
    )
    manifest = check_assets(reloaded, plan)
    picture = job.work_dir / "picture.mp4"
    check(picture.is_file(), "rendering did not write work/picture.mp4")
    check((job.work_dir / "render_spec.json").is_file(), "rendering did not write render_spec.json")
    check((job.work_dir / "render.log").is_file(), "rendering did not keep work/render.log")
    frames = check_picture(picture)
    check_cut(job.work_dir / "cut.mp4")
    cues = check_sound(reloaded, plan, story, library, specs)
    short = job.out_dir / "short.mp4"
    check(short.is_file(), "rendering did not write out/short.mp4")
    short_s, short_lufs = check_short(short, picture)
    check_qa(reloaded)
    sheet = job.out_dir / "contact.jpg"
    check_contact_sheet(sheet)
    log_lines = reloaded.log_path.read_text(encoding="utf-8").splitlines()
    noted = [line.split(" ", 1)[1] for line in log_lines]
    # The steps' own notes (the sound director's summary, 022) sit between the status
    # lines; TRAIL is the status trail, so it is compared against those alone.
    trail = [line for line in noted if line == "created uploaded" or " -> " in line]
    check(trail == TRAIL, f"unexpected job.log trail {trail}")
    check(
        any(line.startswith("sound: bed ") for line in noted),
        f"the sound director left no summary in job.log: {noted}",
    )

    elapsed = time.perf_counter() - started
    summary = (
        f"smoke ok: job {job.id} -> {reloaded.status}, {len(on_disk.words)} words, "
        f"{len(plan.beats)} beats, {len(cues)} cues, {len(pages)} caption pages, "
        f"picture {frames} frames {picture.stat().st_size // 1024} KiB, "
        f"short {short_s:.1f} s {short_lufs:.1f} LUFS {short.stat().st_size // 1024} KiB, "
        f"{len(manifest.assets)} assets, "
        f"{' '.join(TECHNICAL_CHECKS)} pass, "
        f"contact {sheet.stat().st_size // 1024} KiB, "
        f"fixture {clip.stat().st_size // 1024} KiB, {elapsed:.1f}s"
    )
    return SmokeResult(job_dir=job.path, summary=summary, picture=picture)


def check_assets(job: jobs.Job, plan: PicturePlan) -> assets.AssetManifest:
    """016: `work/assets.json` sources every labelled beat through the fakes with no
    rescue, the photo beat as a photo and the card beat as a card; the rights log is
    complete and the credits exist; the render spec draws both. 017: the fake
    relevance judge scored the candidates and its verdict is on every searched row.
    019: the concept beats the plan asks to generate come back at rung 2, each with a
    prompt on its rights row, and the credits carry the AI-disclosure line."""
    manifest = assets.load_manifest(job.path)
    check(manifest is not None, "sourcing did not write work/assets.json")
    assert manifest is not None
    sourced = [b.id for b in plan.beats if b.subject_kind is not None]
    check([b.beat_id for b in manifest.beats] == sourced, "a labelled beat was not sourced")
    rescued = [b.beat_id for b in manifest.beats if b.rescued]
    check(not rescued, f"beats rescued although the fakes answer: {rescued}")
    treatments = {b.beat_id: b.treatment for b in manifest.beats}
    check(
        (treatments.get("b03"), treatments.get("b04")) == ("photo", "card"),
        f"b03/b04 drawn as {treatments.get('b03')}/{treatments.get('b04')}, not photo/card",
    )
    # 017: the fake judge scored every candidate, so every searched asset carries a
    # verdict, no beat was sourced unjudged, and the style's ceiling was not reached.
    check(manifest.judge_calls > 0, "the relevance judge never ran")
    check(manifest.judge_calls < manifest.judge_max, "the judge budget was spent")
    unjudged = [b.beat_id for b in manifest.beats if b.judge_skipped]
    check(not unjudged, f"beats sourced unjudged although the judge answers: {unjudged}")
    searched = [a for a in manifest.assets if a.origin in ("web", "commons")]
    check(
        all(a.judge is not None and a.judge.score >= 2 for a in searched),
        "a searched asset has no accepted judge verdict",
    )
    # 019: rung 2 is real, on the fake generator: every `generate` concept beat was
    # made rather than found, under the style's cap and with no ledger row.
    generated = [b.beat_id for b in manifest.beats if b.fallback_rung == 2]
    check(bool(generated), "no beat reached rung 2 although the plan asks to generate")
    check(
        0 < manifest.generated_images <= manifest.gen_max,
        f"{manifest.generated_images} images generated, cap {manifest.gen_max}",
    )
    made = [a for a in manifest.assets if a.origin == "generated"]
    check(
        all(a.generated is not None and a.generated.prompt for a in made),
        "a generated asset carries no prompt (5.4, T9)",
    )
    rows = rights.load(job.path)
    check(rows is not None, "sourcing did not write out/rights.json")
    assert rows is not None
    check(
        all(r.judge is not None for r in rows if r.origin in ("web", "commons")),
        "a searched rights row carries no judge verdict",
    )
    credits_text = (job.out_dir / "credits.md").read_text(encoding="utf-8")
    check(rights.DISCLOSURE in credits_text, "credits.md has no AI-disclosure line (5.4)")
    problems = rights.completeness(rows, manifest, plan)
    check(not problems, f"rights log incomplete: {problems}")
    check((job.out_dir / "credits.md").is_file(), "sourcing did not write out/credits.md")
    spec = RenderSpec.model_validate_json(
        (job.work_dir / "render_spec.json").read_text(encoding="utf-8")
    )
    # 027: b08 (list) and b10 (wall) also carry a visual - their dimmed base still.
    drawn = {b.id: b.visual.treatment for b in spec.beats if b.visual is not None}
    check(
        drawn == {"b03": "photo", "b04": "card", "b08": "photo", "b10": "photo"},
        f"render spec draws {drawn}",
    )
    check_set_pieces(spec, plan)
    return manifest


def check_set_pieces(spec: RenderSpec, plan: PicturePlan) -> None:
    """026: the short opens with the two-beat hook (a full-frame cold open that punches
    in, then the title and three cards) and ends with the finale card; the two landed
    events are drawn where the plan puts them, inside the style's geometry."""
    cold_open, hook_beat = spec.beats[0], spec.beats[1]
    check(cold_open.mode == "full", f"the cold open is {cold_open.mode}, not full")
    check(cold_open.punch_in is not None, "the cold open does not punch in (research S2)")
    hook = hook_beat.hook
    check(hook is not None, "the hook-cards beat carries no hook")
    assert hook is not None
    check(bool(hook.title_lines), "the hook draws no title")
    check(len(hook.cards) == 3, f"the hook draws {len(hook.cards)} cards, not three")
    finale_beat = next(b for b in spec.beats if b.id == plan.finale.beat_id)
    card = finale_beat.finale
    check(card is not None, "the finale beat carries no finale card")
    assert card is not None
    check(card.text == plan.finale.text, f"the finale word is {card.text!r}")
    check(finale_beat is spec.beats[-1], "the finale is not the last beat of the spec")
    stamped = sorted(b.id for b in spec.beats if b.stamp is not None)
    check(stamped == ["b03", "b06"], f"stamps land on {stamped}, not the plan's stamp beats")
    numbers = render.style_numbers(styles.DEFAULT)
    limit = numbers.broll.stamp_max_y_fraction * render.HEIGHT
    for beat in spec.beats:
        if beat.stamp is None:
            continue
        low = beat.stamp.top + beat.stamp.height
        check(low <= limit, f"{beat.id}'s stamp ends at y {low:g}, past the top {limit:g}")
    labelled = [b.id for b in spec.beats if b.lower_third is not None]
    check(not labelled, f"lower-thirds drawn on {labelled}; b04's card strip carries it")
    check_list_split_wall(spec, plan)
    check_infographics(spec, plan)


def check_infographics(spec: RenderSpec, plan: PicturePlan) -> None:
    """021: the fake plan's `chart` beat is drawn from its series (the numbers written in
    the style's grouping, the axes scaled, the plot above `broll.card_max_bottom_y`) and
    its `infographic` beat draws its label-free base with every label in code, inside the
    safe area."""
    numbers = render.style_numbers(styles.DEFAULT)
    limit = numbers.broll.card_max_bottom_y
    planned = {b.kind: b for b in plan.beats if b.kind in ("chart", "infographic")}
    check(set(planned) == {"chart", "infographic"}, f"the fake plan names {sorted(planned)}")
    drawn = next(b for b in spec.beats if b.id == planned["chart"].id)
    chart = drawn.chart
    check(chart is not None, "the chart beat carries no chart")
    assert chart is not None
    check(
        [m.label for m in chart.marks] == [p.label for p in planned["chart"].series],
        f"the chart draws {[m.label for m in chart.marks]}",
    )
    check(
        [m.value for m in chart.marks] == [p.value for p in planned["chart"].series],
        "the chart's values are not the plan's series (9.2)",
    )
    tallest = max(m.bar_height for m in chart.marks)
    check(tallest == chart.plot_height, f"the largest bar is {tallest:g}, not the plot height")
    lowest = max(chart.label_top + chart.label_font_px, chart.baseline_y)
    check(lowest <= limit, f"the chart's axis ends at y {lowest:g}, past {limit}")
    check(drawn.visual is None, "the chart beat draws a picture; a chart is drawn in code")
    diagram_beat = next(b for b in spec.beats if b.id == planned["infographic"].id)
    diagram = diagram_beat.infographic
    check(diagram is not None, "the infographic beat carries no diagram")
    assert diagram is not None
    check(
        [label.text for label in diagram.labels]
        == [label.text for label in planned["infographic"].labels],
        f"the diagram draws {[label.text for label in diagram.labels]}",
    )
    check(Path(diagram.src).is_file(), f"the diagram base {diagram.src} does not exist")
    check(diagram_beat.visual is None, "the diagram base is drawn as a bare photo too (9.3)")
    for label in diagram.labels:
        inside = (
            label.left >= infographics.SAFE_LEFT
            and label.left + label.width <= render.WIDTH - infographics.SAFE_RIGHT_PX
            and label.top >= infographics.SAFE_TOP
            and label.top + label.height <= limit
        )
        check(inside, f"the label {label.text!r} draws outside the safe area")


def check_list_split_wall(spec: RenderSpec, plan: PicturePlan) -> None:
    """027: the fake plan's `list`, `split` and `wall` beats are drawn with the items
    the plan gave them, every picture resolved through the manifest, and every box
    inside the safe area and above the style's `broll.card_max_bottom_y`."""
    numbers = render.style_numbers(styles.DEFAULT)
    limit = numbers.broll.card_max_bottom_y
    planned = {b.kind: b for b in plan.beats if b.kind in ("list", "split", "wall")}
    check(set(planned) == {"list", "split", "wall"}, f"the fake plan names {sorted(planned)}")
    rows = next(b for b in spec.beats if b.id == planned["list"].id)
    piece = rows.list
    check(piece is not None, "the list beat carries no list")
    assert piece is not None
    check(
        [r.text for r in piece.rows] == [i.text for i in planned["list"].items],
        f"the list draws {[r.text for r in piece.rows]}",
    )
    check(rows.visual is not None, "the list has no base still to sit on")
    assert rows.visual is not None
    check(rows.visual.dim > 0, "the list's base still is not dimmed (nkb_04)")
    low = max(r.top + r.height for r in piece.rows)
    check(low <= limit, f"the list's last row ends at y {low:g}, past {limit}")
    split = next(b for b in spec.beats if b.id == planned["split"].id).split
    check(split is not None, "the split beat carries no composite")
    assert split is not None
    check(len(split.panes) == 2, f"the split draws {len(split.panes)} panes, not two")
    check(split.badge is not None, "the split draws no badge (5.2)")
    boxed = {w.text for w in split.title_words if w.highlight}
    check(
        boxed == {i.text for i in planned["split"].items},
        f"the title strip highlights {sorted(boxed)}, not the pane words",
    )
    check(
        split.top + split.height <= limit,
        f"the split card ends at y {split.top + split.height:g}, past {limit}",
    )
    wall = next(b for b in spec.beats if b.id == planned["wall"].id)
    grid = wall.wall
    check(grid is not None, "the wall beat carries no grid")
    assert grid is not None
    check(
        len(grid.cells) == len(planned["wall"].items),
        f"the wall draws {len(grid.cells)} cells for {len(planned['wall'].items)} items",
    )
    check(2 <= grid.columns <= 3, f"the wall is {grid.columns} columns wide, not 2 or 3")
    check(wall.visual is not None and wall.visual.dim > 0, "the wall has no dimmed base")
    lowest = max(c.top + c.box_height for c in grid.cells)
    check(lowest <= limit, f"the wall's last row ends at y {lowest:g}, past {limit}")
    for piece_beat in (rows, wall):
        pictures = [
            s
            for s in (
                [r.icon_src for r in (piece_beat.list.rows if piece_beat.list else [])]
                + [c.src for c in (piece_beat.wall.cells if piece_beat.wall else [])]
            )
            if s
        ]
        missing = [s for s in pictures if not Path(s).is_file()]
        check(not missing, f"{piece_beat.id} names files that do not exist: {missing}")


def check_sound(
    job: jobs.Job,
    plan: PicturePlan,
    story: SoundStory,
    library: sound.Library,
    specs: dict[str, styles.StyleSpec],
) -> tuple[sound.PlacedCue, ...]:
    """022: the fixture short has a bed and at least one floor hit. The stems sit beside
    the mix, the balance report is inside the 7.3 acceptance band, and the bed and every
    cue file the mix used carry a rights row with their source URL (5.4).

    The director is pure above ffmpeg, so the smoke re-derives the bed and the cues from
    the same plan, story and catalogue the renderer had, and checks the files it left.
    The renderer reads the shipped spec's sound numbers, not the fixture-shaped copy the
    grammar uses, so this is the real `cues_max_per_60s` scaled to six seconds."""
    stems = job.work_dir / "stems"
    for stem in ("voice.wav", "music.wav", "sfx.wav", "mix.wav"):
        check((stems / stem).is_file(), f"rendering did not write stems/{stem}")
    nums = specs[styles.DEFAULT].sound
    bed, _ = sound.choose_bed(library, story.bed_query, first_stamp_s=sound.first_stamp_s(plan))
    check(bed is not None, f"no bed was chosen for {story.bed_query}")
    assert bed is not None
    floor = sound.floor_hits(plan, nums)
    check(bool(floor), "the plan's events earned no floor hit (7.1: a short is never flat)")
    runtime = float(plan.beats[-1].end)
    cues = sound.place_cues(plan, story, library, nums, runtime_s=runtime).cues
    check(bool(cues), "the short has no cues")
    check(
        any(c.hit for c in cues),
        f"no cue carries a floor class: {[(c.beat_id, c.intent, c.hit) for c in cues]}",
    )
    for cue in cues:
        check(
            nums.cue_db_min <= cue.gain_db <= nums.cue_db_max,
            f"cue on {cue.beat_id} is {cue.gain_db:g} dB under the voice, outside the band",
        )
    balance = sound.balance_report(stems)
    check(balance is not None, "the mix did not write stems/balance.json")
    assert balance is not None
    check(not balance.problems, f"the mix missed the 7.3 band: {balance.problems}")
    low, high = nums.bed_accept_db
    under = balance.bed_under_voice_db
    check(
        under is not None and low - 1e-9 <= under <= high + 1e-9,
        f"the bed sits {under} dB under the voice, outside {low:g} to {high:g}",
    )
    rows = rights.load(job.path) or []
    audio = {r.id: r for r in rows if r.kind in rights.AUDIO_KINDS}
    check(bed.id in audio and audio[bed.id].kind == "music", f"no music row for {bed.id}")
    for cue in cues:
        check(cue.entry_id in audio, f"no rights row for the cue file {cue.entry_id}")
    check(
        all(r.origin == "library" and r.source_url for r in audio.values()),
        "an audio rights row has no source URL or is not `library` (5.4)",
    )
    credits_text = (job.out_dir / "credits.md").read_text(encoding="utf-8")
    check("Music:" in credits_text, "credits.md has no music line (5.4)")
    return cues


def check_qa(job: jobs.Job) -> None:
    """`out/qa.json`: T1-T4 (006), T8's rescue limit and T9 (016) ran in order and every
    one passed (10.1)."""
    report = technical.load_report(job)
    check(report is not None, "qa did not write out/qa.json")
    assert report is not None
    names = [c.name for c in report.checks]
    check(names == list(TECHNICAL_CHECKS), f"qa.json lists {names}, expected {TECHNICAL_CHECKS}")
    for c in report.checks:
        check(c.passed, f"{c.name} failed: {c.detail}")
    check(report.passed, "qa.json says the report failed although every check passed")


def check_contact_sheet(sheet: Path) -> None:
    """`out/contact.jpg` per 10.4: a JPEG at the sheet width, under 2 MB, laid out for
    the fixture's eight hook frames and six per-second frames."""
    check(sheet.is_file(), "qa did not write out/contact.jpg")
    check(sheet.stat().st_size < contact_sheet.MAX_BYTES, "contact.jpg is 2 MB or more")
    expected = contact_sheet.layout(contact_sheet.HOOK_FRAMES, round(fixture.DURATION_S))
    with Image.open(sheet) as image:
        check(image.format == "JPEG", f"contact.jpg is {image.format}, not JPEG")
        check(
            image.size == (expected.width, expected.height),
            f"contact.jpg is {image.size[0]}x{image.size[1]}, "
            f"expected {expected.width}x{expected.height}",
        )


def check_cut(cut: Path) -> None:
    """`work/cut.mp4` per ticket 005: CFR 30 fps H.264 with no B-frames, plus audio."""
    check(cut.is_file(), "rendering did not write work/cut.mp4")
    streams = ffmpeg.probe(cut)["streams"]
    kinds = [s.get("codec_type") for s in streams]
    check(kinds == ["video", "audio"], f"cut.mp4 streams are {kinds}, expected video + audio")
    video = streams[0]
    check(video.get("codec_name") == "h264", f"cut.mp4 codec is {video.get('codec_name')}")
    check(int(video.get("has_b_frames", 1)) == 0, "cut.mp4 has B-frames")
    rates = (video.get("r_frame_rate"), video.get("avg_frame_rate"))
    check(rates == ("30/1", "30/1"), f"cut.mp4 is not constant 30 fps: {rates}")
    frames = int(video.get("nb_frames", 0))
    check(frames == EXPECTED_FRAMES, f"cut.mp4 has {frames} frames, expected {EXPECTED_FRAMES}")


def check_short(short: Path, picture: Path) -> tuple[float, float]:
    """`out/short.mp4` per ticket 005: the picture stream copied bit-for-bit, audio
    present, the fixture's length, the master near -14 LUFS (T4 proper is 006)."""
    info = ffmpeg.probe(short)
    kinds = sorted(s.get("codec_type") for s in info["streams"])
    check(kinds == ["audio", "video"], f"short.mp4 streams are {kinds}, expected video + audio")
    check(
        ffmpeg.video_md5(short) == ffmpeg.video_md5(picture),
        "short.mp4 video stream differs from picture.mp4 (mux re-encoded the picture)",
    )
    duration = float(info["format"]["duration"])
    check(
        abs(duration - fixture.DURATION_S) <= 0.1,
        f"short.mp4 is {duration:.2f} s, expected {fixture.DURATION_S:g} s",
    )
    lufs = ffmpeg.measure_loudness(short).integrated
    check(abs(lufs + 14.0) <= 1.0, f"short.mp4 master is {lufs:.1f} LUFS, expected about -14")
    return duration, lufs


def check_picture(picture: Path) -> int:
    """`work/picture.mp4` per ticket 004: silent H.264, 1080x1920, round(6 x 30) frames."""
    streams = ffmpeg.probe(picture)["streams"]
    kinds = [s.get("codec_type") for s in streams]
    check(kinds == ["video"], f"picture.mp4 streams are {kinds}, expected one silent video")
    video = streams[0]
    check(video.get("codec_name") == "h264", f"picture.mp4 codec is {video.get('codec_name')}")
    size = (int(video.get("width", 0)), int(video.get("height", 0)))
    check(size == (fixture.WIDTH, fixture.HEIGHT), f"picture.mp4 is {size[0]}x{size[1]}")
    frames = int(video.get("nb_frames", 0))
    check(frames == EXPECTED_FRAMES, f"picture.mp4 has {frames} frames, expected {EXPECTED_FRAMES}")
    return frames


def keep_requested() -> bool:
    return os.environ.get(KEEP_ENV) == "1"


@contextmanager
def workspace(keep: bool) -> Generator[Path]:
    """The smoke's root: a system temp directory removed on exit, or, in keep mode,
    a fresh directory under `work/smoke/` that is never removed."""
    if keep:
        KEEP_DIR.mkdir(parents=True, exist_ok=True)
        yield Path(tempfile.mkdtemp(prefix=TMP_PREFIX, dir=KEEP_DIR))
        return
    with tempfile.TemporaryDirectory(prefix=TMP_PREFIX) as tmp:
        yield Path(tmp)


def main(
    argv: list[str] | None = None,
    *,
    transcriber: Transcriber | None = None,
    planner: Planner | None = None,
) -> int:
    keep = keep_requested()
    with workspace(keep) as root:
        try:
            result = run_smoke(root, transcriber=transcriber, planner=planner)
        except Exception as exc:  # noqa: BLE001 - the smoke reports every failure the same way
            print(f"smoke FAILED: {exc}", file=sys.stderr)
            return 1
    summary = result.summary
    if keep:
        summary += f", kept {result.picture.resolve()}"
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
