"""The fourth feedback loop: `python -m shortsmith.smoke`.

Walks the same path the tests walk, end to end, with every fake and no network:
generate the 12.1 fixture, ingest it the way the upload route does (`ingest.accept`,
not HTTP), run the job through the worker (`pipeline.Worker.run_next`, the same code
the web app's thread runs) with the fake transcriber, the fake planner, the fake
image sources (016: web answers every query but the photo beat's, Commons has that
one as a full-bleed portrait) and the real Remotion renderer, assert `work/asr.json`,
`work/plan.json`, `work/sound.json`, `work/captions.json`, `work/assets.json` (every
sourced beat found, none rescued, the photo beat a photo and the card beat a card, the
map beat drawn from the bundled geodata with fake-geocoded markers and no picture, 020),
`out/rights.json` complete and `out/credits.md`, the face measured by the real
cascade on all eight strip stills with the 3.3 geometry on `job.json` and in the
render spec (013), `work/picture.mp4` (H.264,
1080x1920, round(6 x 30) frames, silent), the sound director's bed, cues, stems and
balance report from a synthesised catalogue (022),
`out/short.mp4`, `out/qa.json` with T1-T13 all passing (032; decision 12.1) and the
fake critic's advisory report beside them, scored from the real sheet and strips (033),
`out/contact.jpg` under 2 MB at the sheet's width with the PIP strip row and the
critic's scores drawn into its summary panel (035), `out/meta.json` validating against
`contracts.Meta` with the versions and the empty ledger (035), the publishing text
assembled from the plan and the credits (035), the self-inventory's card of the
delivered short from the fake analyser in `out/inventory.json` and its comparison rows
in `meta.json` (074), and the
job's `uploaded -> ... -> qa -> delivered` trail, print one summary line and exit 0.
Any failed assertion exits non-zero with the failing check on stderr. Over ninety
seconds is a bug.

The fixture is six seconds long, so smoke lowers only `Limits.min_duration_s`; every
other 2.1 limit stays at its default.

Everything happens in a temp directory that is removed afterwards, unless
`SHORTSMITH_SMOKE_KEEP=1` (ticket 049): then the run lands under `work/smoke/` beneath
the current directory, survives, and the summary line ends with the absolute path of
`picture.mp4` so the operator can watch the render. `work/` is git-ignored.

`--style hitech` (ticket 048; decisions 1.4, 9.2, 9.4) renders the same walk under the
`hitech` draft: the smoke first proves the form's resolver still redirects the word to
`explainer` with the notice, then selects the draft directly (the resolver never picks
one), and every check reads that spec's numbers - its palette, typography, PIP ring,
four-transition subset with `wipe` on a beat - through the same T1-T13. The draft stays
`draft`; nothing about it is judged here.

`--style footage|vishva|fastfacts` (ticket 059) renders the walk under a shipped recipe
style: the smoke proves the form resolves the name to itself, judges the fake plan under
the style's fixture-shaped copy with its own overlays on at the fixture's counts
(`judged_specs`), and `check_recipe` reads the recipe off the render spec - the flash and
the tick on b03's pop-in (070: the whoosh moves to the next transition), the stacked
split (vishva), the title strip until the finale (fastfacts), none where the style has
no row. `check_marks` (070) holds every style to the closed palette: the fake story's
one transition whoosh and, where the plan pops something in, one pop-in tick, both
placed.

`--text-pops` (ticket 061) runs the walk under the selected style's copy with text pops
turned on (`fixture.pops_on`; every existing style keeps them off): the fake plan's b03
carries one pop, the grammar writes its landing on the word, the render draws it clear of
the circle, the captions and the presenter's face, and T12 counts it.

`--bubbles` (ticket 063) likewise with bubbles on (`fixture.bubbles_on`): the fake plan's
b04 carries a dialogue pair, the grammar lands the first at the beat's start and the
second the fixture-scaled gap later, the render draws both clear of the circle, the
captions, the stamp and each other with their tails on their anchors, T12 counts them,
and job.log carries each bubble's text beside its source words.

`--stickers` (ticket 062) likewise with stickers on (`fixture.stickers_on`): the fake
plan's b01 carries one sticker (the `idea` tag, resolved by the grammar to the light
bulb), the sourcing step fetches it through the fake fetcher into a cache under the smoke
root and copies it into the job, the render draws it centred above the PIP circle, T12
counts it, and the rights log and credits carry it.

Ticket 058: the fake plan's b04 is a `clip` beat; the fake clip source (Pexels video)
answers its query with a synthetic moving clip carrying a tone, and `check_clip` proves
the walk: the manifest's `clip` record with its real length, the rights row and the
"Video by ... on Pexels" credit, the render spec's `clip` visual at the style's speed,
the strip's `Pv` letter, a frame at the beat's middle that differs from its first, and a
picture with no audio stream. The summary carries the picture render's seconds (from
`render.log`) so a run can be compared with the one before it.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image

from shortsmith import (
    assets,
    contact_sheet,
    ffmpeg,
    fixture,
    geo,
    infographics,
    ingest,
    jobs,
    meta,
    pipeline,
    presenter,
    publishing,
    render,
    rights,
    safe_area,
    sound,
    stickers,
    styles,
)
from shortsmith.contracts import (
    CRITIC_LINES,
    CUE_KINDS,
    TIER1_KINDS,
    AssetManifest,
    Captions,
    CriticReport,
    DiagramLayout,
    Meta,
    PicturePlan,
    RenderSpec,
    SoundStory,
    Transcript,
    ValidatedPlan,
)
from shortsmith.ingest import Limits, VideoUpload
from shortsmith.planner import FakePlanner, Planner, kinds_named
from shortsmith.qa import critic as critic_module
from shortsmith.qa import technical
from shortsmith.qa.critic import FakeCritic
from shortsmith.reference import PROMPT_VERSION, ReferenceInventoryV2, own
from shortsmith.reference.gemini import FakeAnalyser
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
TECHNICAL_CHECKS = technical.CHECK_ORDER  # T1-T13
SMOKE_BRIEF = (
    "Topic: a six-second synthetic clip. Angle: prove the pipeline end to end. "
    "Must-say: twelve words on six tone bursts. Hook wish: none."
)
SMOKE_STYLE_LINE = "explainer, energetic"
# 059: the shipped styles, the explainer and the three recipes from the references.
SHIPPED = ["explainer", "fastfacts", "footage", "vishva"]
SMOKE_LIMITS = Limits(min_duration_s=fixture.DURATION_S)
# 016: the fake plan's b01 (the opening's first image) asks for this; Commons answers it
# with a full-bleed portrait. Web answers everything else with a 1600x1000 landscape, so
# b02 (the planned card, 057 / 058) is drawn as a card. 058: b04 asks for moving footage,
# which the fake Pexels video source answers with a 3 s synthetic clip.
PHOTO_QUERY = "slow colour gradient sky"
# Below the stamp, right of the PIP circle, above the caption band: only the clip moves here.
CLIP_REGION = (400, 720, 940, 940)
CLIP_MOTION_MIN = 0.01  # the share of the region's pixels that must change over the beat


def smoke_sourcing(sticker_cache: Path | None = None) -> assets.Sourcing:
    """The fake sources; `sticker_cache` (062) gives the step the shipped sticker
    catalogue over the fake fetcher, cached there."""
    shelf = (
        stickers.StickerShelf(catalogue=stickers.shipped(), fetcher=stickers.FakeStickerFetcher(),
                              cache_dir=sticker_cache)  # fmt: skip
        if sticker_cache is not None
        else None
    )
    return assets.Sourcing(
        sources={
            "web": assets.FakeImageSource("web", nothing_for={PHOTO_QUERY}),
            "commons": assets.FakeImageSource("commons", sizes={PHOTO_QUERY: (1080, 1920)}),
        },
        order=("web", "commons"),
        judge=assets.FakeRelevanceJudge(),  # 017: the judge runs, on no paid call
        generator=assets.FakeImageGenerator(),  # 019: rung 2, on no paid call either
        clips={"pexels": assets.FakeClipSource("pexels")},  # 058: the clip beat's footage
        stickers=shelf,
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


def select_style(style: str, specs: dict[str, styles.StyleSpec]) -> styles.Resolution:
    """The style the smoke renders under (008, 048). The default resolves from the form's
    style line, with no notice. Any other name is a draft the resolver must still redirect
    to `explainer` with the 1.4 notice - proved here - and is then selected directly, as
    the operator does for a smoke render and never a user job."""
    if style == styles.DEFAULT:
        resolution = styles.resolve(SMOKE_STYLE_LINE, specs)
        check(
            resolution.name == styles.DEFAULT and resolution.notice == "",
            f"resolved {resolution}",
        )
        return resolution
    check(style in specs, f"style {style!r} is not a loaded spec (loaded: {sorted(specs)})")
    if specs[style].status == "shipped":
        # 059: a shipped recipe style resolves from its own name, as the form would.
        resolution = styles.resolve(style, specs)
        check(
            resolution == styles.Resolution(name=style, note=style),
            f"the form would resolve {style!r} to {resolution}, not to itself",
        )
        return resolution
    redirected = styles.resolve(style, specs)
    check(
        redirected.name == styles.DEFAULT
        and redirected.notice == f"{style} not available yet, using {styles.DEFAULT}",
        f"the form would resolve {style!r} to {redirected}, not to {styles.DEFAULT} "
        "with the notice",
    )
    return styles.Resolution(name=style, note=style)


def judged_specs(
    specs: dict[str, styles.StyleSpec], style: str, *, text_pops: bool = False,
    bubbles: bool = False, stickers_on: bool = False,
) -> dict[str, styles.StyleSpec]:  # fmt: skip
    """The specs the fake plan is judged by (009): the fixture-shaped copy of `style`,
    with text pops, bubbles and stickers raised to the fixture's counts where asked for
    (061-063) or where the style turns them on itself (059's recipes: a cap over 0 per
    60 s rounds to fewer than the fake's one pop, dialogue pair or sticker in 6 s)."""
    judged = fixture.smoke_specs(specs, style)
    broll = specs[style].broll
    if text_pops or broll.text_pops_max_per_60s > 0:
        judged[style] = fixture.pops_on(judged[style])
    if bubbles or broll.bubbles_max_per_60s > 0:
        judged[style] = fixture.bubbles_on(judged[style])
    if stickers_on or broll.stickers_max_per_60s > 0:
        judged[style] = fixture.stickers_on(judged[style])
    return judged


def run_smoke(
    root: Path,
    *,
    style: str = styles.DEFAULT,
    text_pops: bool = False,
    bubbles: bool = False,
    stickers_on: bool = False,
    transcriber: Transcriber | None = None,
    planner: Planner | None = None,
    renderer: Renderer | None = None,
) -> SmokeResult:
    """`text_pops` (061) judges and renders the walk under the selected style's copy
    with text pops turned on (`fixture.pops_on`), so the fake plan's one pop is drawn;
    `bubbles` (063) likewise with bubbles on (`fixture.bubbles_on`), so the fake plan's
    dialogue pair is drawn; `stickers_on` (062) likewise with stickers on
    (`fixture.stickers_on`), so the fake plan's one sticker is fetched and drawn; every
    existing style keeps all three off, so the plain walk draws none."""
    started = time.perf_counter()
    transcriber = transcriber or FakeTranscriber()
    planner = planner or FakePlanner()

    clip = fixture.make_fixture(root / "fixture" / "fixture.mp4")
    check(clip.stat().st_size < 1_000_000, "fixture must be under 1 MB (12.1)")

    # 022: the synthesised audio catalogue, the one the shipped file will hold after 025.
    library = sound.load_catalogue(fixture.make_catalogue(root / "audio"))
    check(bool(library.beds()) and bool(library.sfx()), "the synthesised catalogue is empty")
    # 024: the renderer carries the 7.2 audio search; the fake records whether the
    # director asked it, and the fake plan's bed query scores in the library, so it is
    # never asked - the gate is proved shut, not just present.
    search = sound.FakeAudioSearch()
    # 020: the map's markers come from the fake geocoder's ten places; the land under
    # them is the real bundled geodata, read with no network (13.1).
    renderer = renderer or render.RemotionRenderer(search=search, geocoder=geo.FakeGeocoder())

    # 008: every spec loads against the registry, and the style line resolves in code.
    specs = styles.load_all(render.registry())
    check(styles.shipped(specs) == SHIPPED, f"shipped styles: {styles.shipped(specs)}")
    resolution = select_style(style, specs)
    # 059: a recipe style turns its overlays on itself; the checks below follow it.
    broll = specs[style].broll
    text_pops = text_pops or broll.text_pops_max_per_60s > 0
    bubbles = bubbles or broll.bubbles_max_per_60s > 0
    stickers_on = stickers_on or broll.stickers_max_per_60s > 0

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
        (job.record.style, job.record.style_note) == (style, resolution.note),
        "job.json does not carry the resolved style and note",
    )
    check((job.input_dir / "raw.mp4").is_file(), "ingest did not write input/raw.mp4")
    check((job.input_dir / "brief.md").is_file(), "ingest did not write input/brief.md")
    check((job.input_dir / "refs.json").is_file(), "ingest did not write input/refs.json")

    # 009: the fake plan is judged by the fixture-shaped copy of the selected style. 033:
    # the fake critic records what it was shown, so the strips are proved real below.
    critic = FakeCritic()
    # 074: the self-inventory reads the delivered short through the fake analyser.
    analyser = FakeAnalyser([fixture.own_inventory_answer()])
    judged = judged_specs(specs, style, text_pops=text_pops, bubbles=bubbles,
                          stickers_on=stickers_on)  # fmt: skip
    worker = pipeline.Worker(
        transcriber=transcriber, planner=planner, renderer=renderer,
        sourcing=smoke_sourcing(root / "stickers"), specs=judged, library=library,
        critic=critic, inventory=own.SelfInventory(analyser),
        # 097: the editor on the fake planner (every decision the code's fallback) and
        # the renderer's fake geocoder.
        editor=pipeline.default_editor(planner, renderer),
    )  # fmt: skip
    worker.submit(job.path)
    check(worker.run_next(), "the worker had nothing to run")

    # Assertions: re-read from disk, the way the next step will.
    reloaded = jobs.load(job.path)
    if reloaded.record.error is not None:
        err = reloaded.record.error
        raise SmokeFailure(f"job failed at {err.step}: {err.message} ({err.detail.strip()})")
    check(reloaded.status == LAST_STATUS, f"job status is {reloaded.status}")
    # 097: the fixture plan needs no rescue; a decision here means the editor hid a
    # regression the smoke used to fail on.
    rescued = [f"{d.step} {d.beat_id or 'plan'}: {d.problem}" for d in reloaded.record.decisions]
    check(not rescued, f"the editor had to rescue the fixture job: {'; '.join(rescued)}")
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
    manifest = check_assets(reloaded, plan, style)
    faces = check_presenter(reloaded, style)
    picture = job.work_dir / "picture.mp4"
    check(picture.is_file(), "rendering did not write work/picture.mp4")
    check((job.work_dir / "render_spec.json").is_file(), "rendering did not write render_spec.json")
    check((job.work_dir / "render.log").is_file(), "rendering did not keep work/render.log")
    frames = check_picture(picture)
    render_s = check_render_time(job)
    check_clip(reloaded, plan, manifest, style)
    check_cut(job.work_dir / "cut.mp4")
    cues = check_sound(reloaded, plan, story, library, specs[style])
    check(
        search.calls == [],
        f"a library bed scored over the threshold, yet the audio search was asked: {search.calls}",
    )
    short = job.out_dir / "short.mp4"
    check(short.is_file(), "rendering did not write out/short.mp4")
    short_s, short_lufs = check_short(short, picture)
    check_qa(reloaded)
    pops = check_text_pops(reloaded, plan, on=text_pops)
    drawn_bubbles = check_bubbles(reloaded, plan, on_disk, on=bubbles)
    drawn_stickers = check_stickers(reloaded, plan, manifest, on_disk, on=stickers_on)
    recipe = check_recipe(reloaded, plan, story, specs[style])
    sheet = job.out_dir / "contact.jpg"
    check_contact_sheet(sheet)
    verdict = check_critic(reloaded, critic, plan)
    check_meta(reloaded, plan, validated, verdict, specs[style])
    compared = check_inventory(reloaded, analyser, style)
    check_publishing(reloaded, plan)
    log_lines = reloaded.log_path.read_text(encoding="utf-8").splitlines()
    noted = [line.split(" ", 1)[1] for line in log_lines]
    # The steps' own notes (the sound director's summary, 022) sit between the status
    # lines; TRAIL is the status trail, so it is compared against those alone.
    trail = [
        line
        for line in noted
        if line == "created uploaded" or (" -> " in line and not line.startswith("sound: "))
    ]  # 056 / 076: a repair's "margin a -> b dB" line is a sound note, not a status
    check(trail == TRAIL, f"unexpected job.log trail {trail}")
    check(
        any(line.startswith("sound: bed ") for line in noted),
        f"the sound director left no summary in job.log: {noted}",
    )
    # 033: the critic's line sits inside the `qa` step, after the gate's sheet.
    critic_lines = [line for line in noted if line.startswith("critic: ")]
    check(len(critic_lines) == 1, f"expected one critic line in job.log, got {critic_lines}")
    at = noted.index(critic_lines[0])
    check(
        noted.index("rendering -> qa") < at < noted.index("qa -> delivered"),
        "the critic's line is not inside the qa step",
    )

    elapsed = time.perf_counter() - started
    summary = (
        f"smoke ok: style {style}, job {job.id} -> {reloaded.status}, "
        f"{len(on_disk.words)} words, "
        f"{len(plan.beats)} beats, {len(cues)} cues, {len(pages)} caption pages, "
        f"text pops {pops}, bubbles {drawn_bubbles}, stickers {drawn_stickers}, clip b04, "
        f"{recipe}"
        f"picture {frames} frames {picture.stat().st_size // 1024} KiB render {render_s:.1f}s, "
        f"short {short_s:.1f} s {short_lufs:.1f} LUFS {short.stat().st_size // 1024} KiB, "
        f"{len(manifest.assets)} assets, face {faces}/{presenter.STRIP_COUNT}, "
        f"{' '.join(TECHNICAL_CHECKS)} pass, "
        f"critic {verdict.overall}/10 {'advisory' if verdict.advisory else 'blocking'}, "
        f"inventory {compared} rows, "
        f"contact {sheet.stat().st_size // 1024} KiB, "
        f"fixture {clip.stat().st_size // 1024} KiB, {elapsed:.1f}s"
    )
    return SmokeResult(job_dir=job.path, summary=summary, picture=picture)


def check_assets(job: jobs.Job, plan: PicturePlan, style: str) -> assets.AssetManifest:
    """016: `work/assets.json` sources every labelled beat through the fakes with no
    rescue, the photo beat as a photo and the card beat as a card; the rights log is
    complete and the credits exist; the render spec draws both. 017: the fake
    relevance judge scored the candidates and its verdict is on every searched row.
    019: the concept beats the plan asks to generate come back at rung 2, each with a
    prompt on its rights row, and the credits carry the AI-disclosure line."""
    manifest = assets.load_manifest(job.path)
    check(manifest is not None, "sourcing did not write work/assets.json")
    assert manifest is not None
    sourced = [
        b.id for b in plan.beats
        if b.subject_kind is not None and b.kind not in assets.NOT_SOURCED
    ]  # fmt: skip
    check([b.beat_id for b in manifest.beats] == sourced, "a labelled beat was not sourced")
    rescued = [b.beat_id for b in manifest.beats if b.rescued]
    check(not rescued, f"beats rescued although the fakes answer: {rescued}")
    treatments = {b.beat_id: b.treatment for b in manifest.beats}
    check(
        (treatments.get("b01"), treatments.get("b02")) == ("photo", "card"),
        f"b01/b02 drawn as {treatments.get('b01')}/{treatments.get('b02')}, not photo/card "
        "(055: the opening's two images; 057: b02's landscape cannot fill the frame)",
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
    # 027: b08 (list) and b10 (wall) also carry a visual - their dimmed base still;
    # 055 / 057 / 058: b01 and b02 are the opening's two image beats (b02 the planned
    # card, its landscape could not fill the frame anyway), b04 the clip that carries the
    # stamp.
    drawn = {b.id: b.visual.treatment for b in spec.beats if b.visual is not None}
    check(
        drawn == {"b01": "photo", "b02": "card", "b04": "clip", "b08": "photo", "b10": "photo"},
        f"render spec draws {drawn}",
    )
    check_set_pieces(spec, plan, style)
    check_transitions(spec, plan, style)
    check_look(spec, style)
    return manifest


def check_render_time(job: jobs.Job) -> float:
    """058: the picture render's seconds, read off the driver's `done` line in
    `work/render.log`, so the summary carries a number to set beside the last run's."""
    text = (job.work_dir / "render.log").read_text(encoding="utf-8", errors="replace")
    seconds = [
        float(match.group(1))
        for line in text.splitlines()
        if (match := re.search(r"done frames=\d+ render_s=([\d.]+)", line)) is not None
    ]
    check(len(seconds) == 1, f"render.log carries {len(seconds)} `done` lines, not one")
    return seconds[0]


def _region_motion(
    a: tuple[int, int, bytes], b: tuple[int, int, bytes], box: tuple[int, int, int, int]
) -> float:
    """The share of the pixels inside `box` (every other pixel) that differ by more than
    30 levels in any channel between frames `a` and `b`."""
    left, top, right, bottom = box
    width = a[0]
    changed = total = 0
    for y in range(top, bottom, 2):
        for x in range(left, right, 2):
            i = 3 * (y * width + x)
            total += 1
            if any(abs(a[2][i + c] - b[2][i + c]) > 30 for c in range(3)):
                changed += 1
    return changed / max(1, total)


def check_clip(
    job: jobs.Job, plan: PicturePlan, manifest: assets.AssetManifest, style: str
) -> None:
    """058: the fake plan's b04 (`clip`) was sourced from the fake Pexels video source -
    a `clip` record at rung 0 with its real size and length, a rights row of kind
    `clip` and the "Video by <name> on Pexels" credit - drawn as the `clip` treatment at
    the style's speed from the file's start, marked `Pv` on the contact sheet's strip,
    moving between the beat's first frame and its middle, while the picture stays silent
    although the clip file carries a tone (the master carries no clip audio)."""
    beat = next(b for b in plan.beats if b.kind == "clip")
    check(beat.id == "b04", f"the fake plan's clip beat is {beat.id}, not b04")
    decided = manifest.beat(beat.id)
    check(decided is not None, "the clip beat was not sourced")
    assert decided is not None
    check(
        (decided.treatment, decided.fallback_rung, decided.asset_id) == ("clip", 0, "a3"),
        f"the clip beat was decided as {decided}",
    )
    record = manifest.asset("a3")
    check(record is not None, "the manifest has no record for the clip")
    assert record is not None
    check(
        (record.kind, record.origin, record.licence) == ("clip", "pexels", "Pexels License"),
        f"the clip record is {record.kind} from {record.origin} under {record.licence!r}",
    )
    check(abs(record.duration_s - 3.0) <= 0.1, f"the clip record runs {record.duration_s} s")
    clip_file = job.path / record.file
    check(clip_file.is_file() and clip_file.suffix == ".mp4", f"the clip file {record.file} is off")
    streams = {s.get("codec_type") for s in ffmpeg.probe(clip_file)["streams"]}
    check(streams == {"video", "audio"}, f"the clip file carries {sorted(streams)}, not a tone")
    check(ffmpeg.video_size(clip_file) == (record.width, record.height), "the clip size is off")
    rows = rights.load(job.path) or []
    clip_rows = [r for r in rows if r.kind == "clip"]
    check(
        [(r.id, r.origin, r.beat_ids) for r in clip_rows] == [("a3", "pexels", ["b04"])],
        f"the clip's rights rows are {clip_rows}",
    )
    credits_text = (job.out_dir / "credits.md").read_text(encoding="utf-8")
    check(
        "Video by fake pexels video on Pexels via " in credits_text,
        f"credits.md has no Pexels video credit:\n{credits_text}",
    )
    spec = RenderSpec.model_validate_json(
        (job.work_dir / "render_spec.json").read_text(encoding="utf-8")
    )
    drawn = next(b for b in spec.beats if b.id == beat.id)
    visual = drawn.visual
    check(visual is not None and visual.treatment == "clip", f"b04 is drawn as {visual}")
    assert visual is not None
    numbers = render.style_numbers(style).broll
    # 102: the clip plays from its most moving stretch, the second the asset step measured
    start = decided.clip_start_s
    check(
        (visual.speed, visual.start_s, visual.scale_from, visual.scale_to)
        == (numbers.clip_speed, start, numbers.clip_scale_from, numbers.clip_scale_to),
        f"the clip visual is not {style}'s clip row from its measured start: {visual}",
    )
    check(Path(visual.src) == clip_file.resolve(), "the render spec does not draw the clip file")
    check(drawn.stamp is not None and drawn.mode == "pip", "the clip beat lost its stamp or circle")
    strip = contact_sheet.strip_line(beat.start + 0.25, plan, manifest)
    check(strip.text == "b04 P clip Pv", f"the strip line reads {strip.text!r}")
    picture = job.work_dir / "picture.mp4"
    first = ffmpeg.frame_rgb(picture, at_s=(drawn.start_frame + 1) / spec.fps)
    middle = ffmpeg.frame_rgb(picture, at_s=(drawn.start_frame + drawn.end_frame) / 2 / spec.fps)
    motion = _region_motion(first, middle, CLIP_REGION)
    check(
        motion > CLIP_MOTION_MIN,
        f"the clip beat's middle frame differs from its first on {motion:.1%} of the region; "
        f"the footage is not moving",
    )
    kinds = [s.get("codec_type") for s in ffmpeg.probe(picture)["streams"]]
    check(kinds == ["video"], f"picture.mp4 carries {kinds}; the clip's tone must not reach it")
    log = job.log_path.read_text(encoding="utf-8")
    check("pexels video: " in log, "job.log has no clip search line (058 (5))")
    check("no usable clip" not in log, "job.log says the clip beat fell to the still ladder")


def check_transitions(spec: RenderSpec, plan: PicturePlan, style: str) -> None:
    """030 (9.4): the spec carries the style's enter list and the vocabulary's numbers
    from the front matter, every beat's `enter` is the plan's, and the fake plan
    exercises each of the style's enabled transitions at least once (048: under
    `hitech` that is cut, fade, wipe and zoom, the whip and spring swapped away)."""
    loaded = styles.load_all(render.registry())[style]
    check(
        spec.transitions.enabled == list(loaded.broll.enter_transitions),
        f"the render spec enables {spec.transitions.enabled}",
    )
    numbers = spec.transitions.model_dump(exclude={"enabled"})
    check(
        numbers == loaded.broll.transitions.model_dump(),
        f"the render spec's transition numbers are not the front matter's: {numbers}",
    )
    check(
        [b.enter for b in spec.beats] == [b.enter for b in plan.beats],
        "a render beat's enter is not its plan beat's",
    )
    used = {b.enter for b in spec.beats}
    check(
        used == set(spec.transitions.enabled),
        f"the fake plan enters with {sorted(used)}, not every {style} transition",
    )


def check_look(spec: RenderSpec, style: str) -> None:
    """048 (1.2): the render spec's palette, caption typography, PIP ring and stamp
    colour are the selected style's front matter, never another spec's."""
    loaded = styles.load_all(render.registry())[style]
    check(spec.palette == loaded.palette, f"the render spec's palette is {spec.palette}")
    check(
        spec.caption_style == loaded.caption_style(),
        f"the render spec's caption typography is not {style}'s",
    )
    check(
        (spec.pip.ring_px, spec.pip.ring_color) == (loaded.pip.ring_px, loaded.pip.ring_color),
        f"the PIP ring is {spec.pip.ring_px} px {spec.pip.ring_color}, not {style}'s",
    )
    lead = render.stamp_colors(render.numbers_for(loaded))[0]
    off_palette = [b.id for b in spec.beats if b.stamp is not None and b.stamp.color != lead]
    check(not off_palette, f"stamps on {off_palette} are not in {style}'s stamp palette")


def check_presenter(job: jobs.Job, style: str) -> int:
    """013: the real cascade found the fixture's drawn face on every strip still, the
    eight stills are on disk, the measurement on job.json is the 3.3 geometry (a
    full-width square window, the circle on the caption block's top edge), and the
    render spec crops through exactly that window. Returns the stills with a face."""
    measured = job.record.presenter
    check(measured is not None, "transcribing did not measure the face onto job.json")
    assert measured is not None
    found = sum(1 for f in measured.faces if f is not None)
    check(
        found == presenter.STRIP_COUNT,
        f"the cascade found the fixture face on {found} of {presenter.STRIP_COUNT} stills",
    )
    missing = [n for n in range(1, presenter.STRIP_COUNT + 1)
               if not presenter.still_path(job, n).is_file()]  # fmt: skip
    check(not missing, f"strip stills missing: {missing}")
    check(measured.times_s == list(presenter.strip_times(fixture.DURATION_S)),
          f"strip times are {measured.times_s}")  # fmt: skip
    spec_style = styles.load_all(render.registry())[style]
    expected = presenter.pip_geometry(measured.face, (fixture.WIDTH, fixture.HEIGHT), spec_style)
    check(measured.pip == expected, f"job.json pip {measured.pip} is not the 3.3 geometry")
    check(
        (measured.pip.window_left, measured.pip.window_size) == (0, fixture.WIDTH),
        "the PIP window is not the full source width, square",
    )
    cx, cy = fixture.FACE_CENTER
    face = measured.face
    check(
        face.left < cx < face.left + face.width and face.top < cy < face.top + face.height,
        f"the median face box {face} does not hold the drawn face's centre",
    )
    spec = RenderSpec.model_validate_json(
        (job.work_dir / "render_spec.json").read_text(encoding="utf-8")
    )
    check(spec.pip == measured.pip, "the render spec does not crop through the measured window")
    return found


def check_set_pieces(spec: RenderSpec, plan: PicturePlan, style: str) -> None:
    """055: the short opens with the speaker's first words in `pip` over two full-screen
    images (no cold open, no title, no hook cards), the one `full` beat punches in,
    and the finale card closes with the payoff word and the opening's images around
    the circle; the two landed events are drawn where the plan puts them, inside the
    style's geometry."""
    numbers = render.style_numbers(style)
    opening = spec.beats[:2]
    for beat in opening:
        check(beat.mode == "pip", f"opening beat {beat.id} is {beat.mode}, not pip")
        check(beat.visual is not None, f"opening beat {beat.id} draws no full-screen image")
        check(beat.punch_in is None, f"opening beat {beat.id} punches in; only full beats do")
    full = [b for b in spec.beats if b.mode == "full"]
    check([b.id for b in full] == ["b03"], f"full beats are {[b.id for b in full]}, not [b03]")
    check(all(b.punch_in is not None for b in full), "the full beat does not punch in (S2)")
    finale_beat = next(b for b in spec.beats if b.id == plan.finale.beat_id)
    card = finale_beat.finale
    check(card is not None, "the finale beat carries no finale card")
    assert card is not None
    check(card.text == plan.finale.text, f"the finale word is {card.text!r}")
    check(finale_beat is spec.beats[-1], "the finale is not the last beat of the spec")
    wanted = numbers.broll.finale_cards
    check(len(card.cards) == wanted, f"the finale draws {len(card.cards)} cards, not {wanted}")
    first = opening[0].visual
    assert first is not None
    check(card.cards[0].src == first.src, "the finale's first card is not the opening's image")
    stamped = sorted(b.id for b in spec.beats if b.stamp is not None)
    check(stamped == ["b04"], f"stamps land on {stamped}, not the plan's stamp beats")
    numbers = render.style_numbers(style)
    limit = numbers.broll.stamp_max_y_fraction * render.HEIGHT
    for beat in spec.beats:
        if beat.stamp is None:
            continue
        low = beat.stamp.top + beat.stamp.height
        check(low <= limit, f"{beat.id}'s stamp ends at y {low:g}, past the top {limit:g}")
    labelled = [b.id for b in spec.beats if b.lower_third is not None]
    check(not labelled, f"lower-thirds drawn on {labelled}; b02's card strip carries it")
    check_list_split_wall(spec, plan, style)
    check_infographics(spec, plan, style)
    check_map(spec, plan, style)


def check_map(spec: RenderSpec, plan: PicturePlan, style: str) -> None:
    """020: the fake plan's `map` beat draws a region of the bundled land with its two
    markers at the fake geocoder's coordinates (never the plan's), Delhi north-east of
    Mumbai, every dot and label inside the safe band, the route ready for 028, and no
    picture sourced for it."""
    beat = next(b for b in plan.beats if b.kind == "map")
    drawn = next(b for b in spec.beats if b.id == beat.id)
    layout = drawn.map
    check(layout is not None, "the map beat carries no map")
    assert layout is not None and beat.map is not None
    check(drawn.visual is None, "the map beat draws a picture; a map is drawn in code (9.3)")
    check(bool(layout.land) and bool(layout.coast) and bool(layout.borders),
          "the map draws no land, coast or borders from the bundled data")  # fmt: skip
    names = [m.name for m in layout.markers]
    check(names == [m.name for m in beat.map.markers], f"the map places {names}")
    check({m.source for m in layout.markers} == {"fake"}, "the markers were not fake-geocoded")
    delhi, mumbai = layout.markers
    check(delhi.y < mumbai.y and delhi.x > mumbai.x, "Delhi is not north-east of Mumbai")
    limit = render.style_numbers(style).broll.card_max_bottom_y
    for m in layout.markers:
        inside = (
            safe_area.BAND_LEFT <= m.x <= safe_area.BAND_RIGHT
            and infographics.DIAGRAM_BAND_TOP <= m.y <= limit
            and m.label_left >= safe_area.BAND_LEFT
            and m.label_left + m.label_width <= safe_area.BAND_RIGHT
            and m.label_top >= safe_area.SAFE_TOP_PX
            and m.label_top + m.label_height <= limit
        )
        check(inside, f"the marker {m.name!r} or its label is outside the safe band")
    check(len(layout.route) == len(beat.map.route), f"the route has {len(layout.route)} points")
    check(layout.object == beat.map.object, f"the map object is {layout.object!r}")


def check_infographics(spec: RenderSpec, plan: PicturePlan, style: str) -> None:
    """021: the fake plan's `chart` beat is drawn from its series (the numbers written in
    the style's grouping, the axes scaled, the plot above `broll.card_max_bottom_y`) and
    its `infographic` beat draws its label-free base with every label in code, inside the
    safe area."""
    numbers = render.style_numbers(style)
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
            label.left >= safe_area.BAND_LEFT
            and label.left + label.width <= safe_area.BAND_RIGHT
            and label.top >= safe_area.SAFE_TOP_PX
            and label.top + label.height <= limit
        )
        check(inside, f"the label {label.text!r} draws outside the safe area")
    check_flyin_and_counter(spec, plan, diagram, style)


def check_flyin_and_counter(
    spec: RenderSpec, plan: PicturePlan, diagram: DiagramLayout, style: str
) -> None:
    """029: the diagram's labels fly in one after another from off-frame and have all
    landed inside the first part of their beat; the fake plan's counter beat counts from
    its start to its target in the style's grouping, lands in the stamp's time, and
    stays in the stamp's top band."""
    delays = [label.delay_s for label in diagram.labels]
    check(
        all(b > a for a, b in zip(delays, delays[1:], strict=False)),
        f"the labels do not enter one after another: delays {delays}",
    )
    offscreen = [
        label.text
        for label in diagram.labels
        if (label.from_x, label.from_y) == (0.0, 0.0)
    ]
    check(not offscreen, f"the labels {offscreen} do not fly in from a frame edge")
    beat = next(b for b in plan.beats if b.kind == "infographic")
    landed = delays[-1] + diagram.fly_s
    window = (beat.end - beat.start) * infographics.LABELS_IN_FRACTION
    check(landed <= window + 1e-9, f"the last label lands at {landed:g} s, after {window:g} s")
    counted = [b for b in plan.beats if b.counter is not None]
    check(len(counted) == 1, f"the fake plan has {len(counted)} counter beats, not one")
    planned = counted[0].counter
    assert planned is not None
    drawn = next(b for b in spec.beats if b.id == counted[0].id)
    counter = drawn.counter
    check(counter is not None, f"{drawn.id} carries no counter")
    assert counter is not None
    numbers = render.style_numbers(style)
    first, last = (
        infographics.with_unit(
            infographics.format_value(v, decimals=planned.decimals,
                                      grouping=numbers.broll.counter_grouping),  # fmt: skip
            planned.unit,
        )
        for v in (planned.start, planned.target)
    )
    check(
        (counter.texts[0], counter.texts[-1]) == (first, last),
        f"the counter runs {counter.texts[0]!r} to {counter.texts[-1]!r}, not {first!r} "
        f"to {last!r}",
    )
    frames = drawn.end_frame - drawn.start_frame
    check(len(counter.texts) == frames, f"{len(counter.texts)} counter texts for {frames} frames")
    check(
        counter.land_s == numbers.broll.stamp_land_s
        and counter.land_frame == frames - round(counter.land_s * spec.fps),
        f"the counter lands at frame {counter.land_frame} over {counter.land_s:g} s",
    )
    limit = numbers.broll.stamp_max_y_fraction * render.HEIGHT
    low = counter.top + counter.height
    check(low <= limit, f"the counter ends at y {low:g}, past the top {limit:g}")
    check(drawn.stamp is None, f"{drawn.id} draws a stamp as well as its counter (3.1)")


def check_list_split_wall(spec: RenderSpec, plan: PicturePlan, style: str) -> None:
    """027: the fake plan's `list`, `split` and `wall` beats are drawn with the items
    the plan gave them, every picture resolved through the manifest, and every box
    inside the safe area and above the style's `broll.card_max_bottom_y`."""
    numbers = render.style_numbers(style)
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
    spec: styles.StyleSpec,
) -> tuple[sound.PlacedCue, ...]:
    """022: the fixture short has a bed and at least one floor hit. The stems sit beside
    the mix, the balance report is inside the 7.3 acceptance band, and the bed and every
    cue file the mix used carry a rights row with their source URL (5.4).

    The director is pure above ffmpeg, so the smoke re-derives the bed and the cues from
    the same plan, story and catalogue the renderer had, and checks the files it left.
    The renderer reads the selected spec's sound numbers as loaded from disk, not the
    fixture-shaped copy the grammar uses, so this is the real `cues_max_per_60s` scaled
    to six seconds."""
    stems = job.work_dir / "stems"
    for stem in ("voice.wav", "music.wav", "sfx.wav", "mix.wav"):
        check((stems / stem).is_file(), f"rendering did not write stems/{stem}")
    nums = spec.sound
    # 076: the bed per story part - every segment's approved bed of its mood, and the one
    # change (the fake's crossfade at vishva's reveal) with both stems and its windows.
    score = next(
        (s for s, _, _ in sound.score_candidates(library, story, plan, nums) if s), None
    )
    check(score is not None, f"no approved bed for the story's moods {story.bed}")
    assert score is not None
    named = len(story.bed)
    check(len(score.spans) == named, f"the story names {named} beds, the score {score.label}")
    changed = story.change is not None
    for i in range(1, len(score.spans) + 1):
        check((stems / f"music.{i}.wav").is_file() == changed,
              f"stems/music.{i}.wav is {'missing' if changed else 'left over'}")  # fmt: skip
    land_s = render.counter_land_s(spec)
    floor = sound.floor_hits(plan, nums, counter_land_s=land_s)
    check(bool(floor), "the plan's events earned no floor hit (7.1: a short is never flat)")
    # 029: the counter's hit fires where its digits land, not at its beat's start.
    for hit in floor:
        beat = next(b for b in plan.beats if b.id == hit.beat_id)
        if beat.counter is not None and land_s is not None:
            check(
                abs(hit.at_s - (beat.end - land_s)) < 1e-9,
                f"{beat.id}'s floor hit fires at {hit.at_s:g} s, not at its counter's landing",
            )
    runtime = float(plan.beats[-1].end)
    cues = sound.place_cues(
        plan, story, library, nums, runtime_s=runtime, counter_land_s=land_s
    ).cues
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
        # 070: a palette kind's approved file, no longer than the kind's length
        entry = library.entry(cue.entry_id)
        kind = sound.cue_kind(cue)
        check(kind in CUE_KINDS and entry is not None
              and entry.duration_s <= sound.kind_max_len_s(kind, nums) + 1e-9,
              f"cue on {cue.beat_id} plays {cue.entry_id} as {kind!r}, outside the palette "
              "or over its length")  # fmt: skip
    check_marks(plan, story)
    balance = sound.balance_report(stems)
    check(balance is not None, "the mix did not write stems/balance.json")
    assert balance is not None
    check(not balance.problems, f"the mix missed the 7.3 band: {balance.problems}")
    expected = len(sound.balance_windows(score, nums, runtime_s=runtime))
    measured = len(balance.windows)
    check(measured == expected, f"balance.json measured {measured} windows, not {expected}")
    low, high = nums.bed_accept_db
    under = balance.bed_under_voice_db
    check(
        under is not None and low - 1e-9 <= under <= high + 1e-9,
        f"the bed sits {under} dB under the voice, outside {low:g} to {high:g}",
    )
    rows = rights.load(job.path) or []
    audio = {r.id: r for r in rows if r.kind in rights.AUDIO_KINDS}
    for bed in score.beds:
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


def check_text_pops(job: jobs.Job, plan: PicturePlan, *, on: bool) -> int:
    """061: with pops on, the fake plan's b03 carries its one pop ("THIS" on word 2),
    the grammar wrote its landing (1.2 s on the cut, 0.2 s into the beat), the render
    spec draws it inside the 6.3 zones with the style's pop look, T12 counted it and
    job.log dropped nothing; with pops off (every existing style) no beat carries one.
    Returns the pops drawn."""
    spec = RenderSpec.model_validate_json(
        (job.work_dir / "render_spec.json").read_text(encoding="utf-8")
    )
    planned = {b.id: b.text_pops for b in plan.beats if b.text_pops}
    drawn = {b.id: b.text_pops for b in spec.beats if b.text_pops}
    report = technical.load_report(job)
    assert report is not None
    t12 = next(c.detail for c in report.checks if c.name == "T12")
    if not on:
        check(not planned and not drawn, f"text pops without the pops style: {planned} {drawn}")
        check("0 text pops" in t12, f"T12 did not count the text pops: {t12}")
        return 0
    check(list(planned) == ["b03"], f"the fake plan pops on {list(planned)}, not on b03")
    (pop,) = planned["b03"]
    check((pop.text, pop.word, pop.at_s) == ("THIS", 2, 1.2), f"b03's pop is {pop}")
    check(list(drawn) == ["b03"], f"the render spec draws pops on {list(drawn)}, not on b03")
    (placed,) = drawn["b03"]
    beat = next(b for b in spec.beats if b.id == "b03")
    numbers = render.style_numbers(job.record.style)
    row = numbers.broll
    check(placed.text == "THIS" and placed.font_weight == render.TEXT_POP_WEIGHT,
          f"b03's pop is drawn as {placed.text!r} at weight {placed.font_weight}")  # fmt: skip
    styled = (placed.color, placed.pop_s) == (row.pop_fill, row.pop_s)
    check(styled and placed.font_px <= row.pop_font_px,
          f"b03's pop look is not {job.record.style}'s text_pop row: {placed}")  # fmt: skip
    check(abs(beat.start_frame / spec.fps + placed.at_s - 1.2) <= 0.15,
          f"b03's pop lands {placed.at_s:g} s into the beat, not on the word at 1.2 s")  # fmt: skip
    check(placed.until_s <= (beat.end_frame - beat.start_frame) / spec.fps + 1e-6,
          "b03's pop outlives its beat")  # fmt: skip
    hits = technical.zone_hits(placed.left, placed.top, placed.width, placed.height)
    check(not hits, f"b03's pop reaches a reserved zone: {hits}")
    check("1 text pop" in t12, f"T12 did not count the text pop: {t12}")
    # only the render's own `text pop:` lines: the sound director also writes "dropped"
    # when the disk spec's cue cap (two in 6 s) cuts the fake story's cues
    dropped = [
        line for line in job.log_path.read_text(encoding="utf-8").splitlines()
        if "text pop:" in line and "dropped" in line
    ]
    check(not dropped, f"a text pop was dropped: {dropped}")
    return len(drawn["b03"])


def check_bubbles(job: jobs.Job, plan: PicturePlan, transcript: Transcript, *, on: bool) -> int:
    """063: with bubbles on, the fake plan's b04 carries its dialogue pair (a speech
    bubble of words 0-1 at the PIP circle, a thought bubble of words 2-3 over the
    card), the grammar landed the first at the beat's start and the second the
    fixture-scaled gap later, the render spec draws both inside the 6.3 zones in the
    style's bubble look, apart from each other, the stamp and the circle, with the tail
    tips on their anchors, T12 counted them, and job.log carries each text beside its
    source words and dropped nothing; with bubbles off (every existing style) no beat
    carries one. Returns the bubbles drawn."""
    spec = RenderSpec.model_validate_json(
        (job.work_dir / "render_spec.json").read_text(encoding="utf-8")
    )
    planned = {b.id: b.bubbles for b in plan.beats if b.bubbles}
    drawn = {b.id: b.bubbles for b in spec.beats if b.bubbles}
    report = technical.load_report(job)
    assert report is not None
    t12 = next(c.detail for c in report.checks if c.name == "T12")
    log_lines = job.log_path.read_text(encoding="utf-8").splitlines()
    bubble_lines = [line.split(" ", 1)[1] for line in log_lines if "bubble: " in line]
    if not on:
        check(not planned and not drawn, f"bubbles without the bubbles style: {planned} {drawn}")
        check("0 bubbles" in t12, f"T12 did not count the bubbles: {t12}")
        check(not bubble_lines, f"job.log has bubble lines without the style: {bubble_lines}")
        return 0
    check(list(planned) == ["b04"], f"the fake plan bubbles on {list(planned)}, not on b04")
    speech, thought = planned["b04"]
    gap = fixture.SMOKE_BUBBLE["dialogue_gap_min_s"]
    check((speech.shape, speech.first, speech.last, speech.at_s) == ("speech", 0, 1, 1.5),
          f"b04's first bubble is {speech}")  # fmt: skip
    check((thought.shape, thought.first, thought.last) == ("thought", 2, 3)
          and thought.at_s == 1.5 + gap, f"b04's second bubble is {thought}")  # fmt: skip
    check(list(drawn) == ["b04"], f"the render spec draws bubbles on {list(drawn)}, not on b04")
    beat = next(b for b in spec.beats if b.id == "b04")
    check(beat.stamp is not None, "b04 lost its stamp")
    assert beat.stamp is not None
    row = render.style_numbers(job.record.style).broll
    circle = render.Box(spec.pip.left, spec.pip.top, spec.pip.diameter, spec.pip.diameter)
    stamp = render.stamp_box(beat.stamp)
    bodies: list[render.Box] = []
    for asked, placed in zip(planned["b04"], drawn["b04"], strict=True):
        drawn_as = (placed.shape, placed.text, placed.font_weight)
        check(drawn_as == (asked.shape, asked.text, render.BUBBLE_WEIGHT),
              f"b04's bubble is drawn as {drawn_as}")  # fmt: skip
        look = (placed.fill, placed.ink, placed.pop_s)
        styled = look == (row.bubble_fill, row.bubble_ink, row.bubble_s)
        check(styled and row.bubble_min_font_px <= placed.font_px <= row.bubble_font_px,
              f"b04's bubble look is not {job.record.style}'s bubble row: {placed}")  # fmt: skip
        anchor = (asked.x / 100 * render.WIDTH, asked.y / 100 * render.HEIGHT)
        check((placed.tip_x, placed.tip_y) == anchor,
              f"b04's bubble tail tip is off its anchor: {placed}")  # fmt: skip
        assert asked.at_s is not None
        landing = beat.start_frame / spec.fps + placed.at_s
        check(abs(landing - asked.at_s) <= 0.15,
              f"b04's bubble lands at {landing:g} s, not at {asked.at_s:g} s")  # fmt: skip
        check(placed.until_s <= (beat.end_frame - beat.start_frame) / spec.fps + 1e-6,
              "b04's bubble outlives its beat")  # fmt: skip
        body = render.Box(placed.left, placed.top, placed.width, placed.height)
        hits = technical.zone_hits(placed.left, placed.top, placed.width, placed.height)
        check(not hits, f"b04's bubble reaches a reserved zone: {hits}")
        check(not body.overlaps(circle) and not body.overlaps(stamp),
              f"b04's bubble {placed.text!r} sits on the circle or the stamp")  # fmt: skip
        check(all(not body.overlaps(other) for other in bodies), "b04's bubbles overlap")
        bodies.append(body)
    first, second = drawn["b04"]
    check(second.at_s - first.at_s == gap, f"the pair lands {second.at_s - first.at_s:g} s apart")
    check(first.dots == [] and len(second.dots) == 3, "the speech or thought trail is wrong")
    check("2 bubbles" in t12, f"T12 did not count the bubbles: {t12}")
    for line in pipeline.bubble_lines(plan, transcript):
        check(line in bubble_lines, f"job.log lacks the bubble's source words: {bubble_lines}")
    dropped = [line for line in bubble_lines if "dropped" in line]
    check(not dropped, f"a bubble was dropped: {dropped}")
    return len(drawn["b04"])


def check_stickers(
    job: jobs.Job, plan: PicturePlan, manifest: AssetManifest, transcript: Transcript,
    *, on: bool,
) -> int:  # fmt: skip
    """062: with stickers on, the fake plan's b01 carries one sticker (the `idea` tag,
    which the grammar resolved to the light bulb, landing on word 1), the sourcing step
    fetched it (the fake fetcher) and copied it into the job, the render spec draws it
    as the style's square centred above the PIP circle, off the circle and the 6.3 zones
    with its float, from the job's copy, T12 counted it, the rights log and the credits
    carry it, and job.log dropped nothing; with stickers off (every existing style) no
    beat carries one and no sticker is fetched or credited. Returns the stickers drawn."""
    spec = RenderSpec.model_validate_json(
        (job.work_dir / "render_spec.json").read_text(encoding="utf-8")
    )
    planned = {b.id: b.stickers for b in plan.beats if b.stickers}
    drawn = {b.id: b.stickers for b in spec.beats if b.stickers}
    report = technical.load_report(job)
    assert report is not None
    t12 = next(c.detail for c in report.checks if c.name == "T12")
    rows = rights.load(job.path) or []
    stuck_rows = [r for r in rows if r.kind == "sticker"]
    credits = (job.out_dir / rights.CREDITS_NAME).read_text(encoding="utf-8")
    log_lines = job.log_path.read_text(encoding="utf-8").splitlines()
    sticker_lines = [line.split(" ", 1)[1] for line in log_lines if "sticker: " in line]
    if not on:
        check(not planned and not drawn, f"stickers without the stickers style: {planned} {drawn}")
        check(manifest.stickers == [] and not stuck_rows, "a sticker was fetched or credited")
        check("0 stickers" in t12, f"T12 did not count the stickers: {t12}")
        check(not sticker_lines, f"job.log has sticker lines without the style: {sticker_lines}")
        return 0
    check(list(planned) == ["b01"], f"the fake plan sticks on {list(planned)}, not on b01")
    (asked,) = planned["b01"]
    landing = transcript.words[1].start
    check((asked.intent, asked.name, asked.at_s, asked.x) == ("idea", "Light bulb", landing, None),
          f"b01's sticker is {asked}")  # fmt: skip
    (record,) = manifest.stickers
    check(record.name == "Light bulb" and (job.path / record.file).is_file(),
          f"the sticker was not fetched into the job: {record}")  # fmt: skip
    check(list(drawn) == ["b01"], f"the render spec draws stickers on {list(drawn)}, not on b01")
    (placed,) = drawn["b01"]
    beat = next(b for b in spec.beats if b.id == "b01")
    row = render.style_numbers(job.record.style).broll
    check((placed.size, placed.pop_s, placed.float_px) == (
        float(row.sticker_size_px), row.sticker_s, row.sticker_float_px),
        f"b01's sticker is not {job.record.style}'s sticker row: {placed}")  # fmt: skip
    check(placed.src == str((job.path / record.file).resolve()),
          f"b01's sticker is not drawn from the job's copy: {placed.src}")  # fmt: skip
    circle = render.Box(spec.pip.left, spec.pip.top, spec.pip.diameter, spec.pip.diameter)
    square = render.Box(placed.left, placed.top, placed.size, placed.size)
    check(abs(placed.left + placed.size / 2 - (circle.left + circle.width / 2)) < 1e-6
          and abs(square.bottom + render.STICKER_GAP_PX - circle.top) < 1e-6,
          f"b01's sticker is not centred above the circle: {square} over {circle}")  # fmt: skip
    check(not square.overlaps(circle), "b01's sticker sits on the circle")
    hits = technical.zone_hits(placed.left, placed.top - placed.float_px, placed.size,
                               placed.size + 2 * placed.float_px)  # fmt: skip
    check(not hits, f"b01's sticker reaches a reserved zone: {hits}")
    at = beat.start_frame / spec.fps + placed.at_s
    check(abs(at - landing) <= 0.15, f"b01's sticker lands at {at:g} s, not at {landing:g} s")
    check("1 sticker" in t12, f"T12 did not count the sticker: {t12}")
    check(len(stuck_rows) == 1 and stuck_rows[0].beat_ids == ["b01"],
          f"the rights log does not carry the sticker: {stuck_rows}")  # fmt: skip
    check(f"Sticker: Light bulb - {stickers.CREDIT} via {record.source_url}" in credits,
          f"credits.md lacks the sticker line: {credits}")  # fmt: skip
    check(not sticker_lines, f"a sticker was moved, dropped or left out: {sticker_lines}")
    return len(drawn["b01"])


def check_marks(plan: PicturePlan, story: SoundStory) -> None:
    """070: the validated fake story speaks only the palette, with one whoosh on a
    transition and, where the plan pops something in on a beat no other cue holds, one
    tick on a pop-in. (The render
    judges them under the shipped `cues_max_per_60s`, two cues in six seconds, so the
    drums keep the slots; the director tests place them.)"""
    named = [c.intent for c in story.cues]
    check(set(named) <= set(CUE_KINDS), f"the story names cues outside the palette: {named}")
    beats = {b.id: b for b in plan.beats}
    whooshes = [c for c in story.cues if c.intent == styles.WHOOSH]
    check(len(whooshes) == 1 and beats[whooshes[0].beat_id].enter != "cut",
          f"the story's whooshes {whooshes} are not one on a transition")  # fmt: skip
    ticks = [c for c in story.cues if c.intent == styles.TICK]
    # one cue a beat: a pop-in on a beat another cue already holds (b01's sticker under
    # the opening bass, b04's bubbles under the stamp's) gets no tick
    others = {c.beat_id for c in story.cues if c.intent != styles.TICK}
    free = any(b.text_pops or b.bubbles or b.stickers for b in plan.beats if b.id not in others)
    check(len(ticks) == (1 if free else 0), f"the story's ticks are {ticks}")
    for tick in ticks:
        beat = beats[tick.beat_id]
        check(tick.at == "event" and bool(beat.text_pops or beat.bubbles or beat.stickers),
              f"the tick on {tick.beat_id} is not on a pop-in")  # fmt: skip


def check_recipe(
    job: jobs.Job, plan: PicturePlan, story: SoundStory, spec_style: styles.StyleSpec
) -> str:
    """059: the render spec shows the style's recipe. Where `flash` is enabled, b03 (the
    turn back to the presenter) flashes and, where whooshes are allowed, carries the
    whoosh; a `stacked` split draws its two pictures one above the other with the title
    band between; a style with a title strip draws the plan's words at its row until the
    finale and T12 counted it; a style without one draws none. Returns a summary
    fragment for the smoke line."""
    spec = RenderSpec.model_validate_json(
        (job.work_dir / "render_spec.json").read_text(encoding="utf-8")
    )
    numbers = render.numbers_for(spec_style)
    shown: list[str] = []
    if "flash" in spec_style.broll.enter_transitions:
        flashed = [b.id for b in spec.beats if b.enter == "flash"]
        check(flashed == ["b03"], f"the flash lands on {flashed}, not on b03")
        shown.append("flash b03")
        if any(b.text_pops for b in plan.beats if b.id == "b03"):
            # 070: b03's pop-in carries the tick; the whoosh moves to the next transition
            ticked = [c.beat_id for c in story.cues if c.intent == styles.TICK]
            check(ticked == ["b03"], f"the tick sits on {ticked}, not on b03's pop-in")
            shown.append("tick b03")
    if numbers.broll.split_layout == "stacked":
        piece = next((b.split for b in spec.beats if b.split is not None), None)
        check(piece is not None, "the stacked style draws no split")
        assert piece is not None
        top, bottom = piece.panes
        check(top.left == bottom.left and top.top + top.pane_height <= piece.title_top
              and bottom.top >= piece.title_top + piece.title_px,
              f"the split is not stacked with the title between: {piece.panes}")  # fmt: skip
        shown.append("stacked split")
    report = technical.load_report(job)
    assert report is not None
    t12 = next(c.detail for c in report.checks if c.name == "T12")
    strip = spec.title_strip
    if numbers.title_strip is None:
        check(strip is None and plan.title_strip == "", "a title strip without the style's row")
    else:
        check(strip is not None and strip.text == plan.title_strip != "",
              f"the title strip is {strip}, not the plan's {plan.title_strip!r}")  # fmt: skip
        assert strip is not None
        check(strip.top == numbers.title_strip.top_y, f"the title strip sits at y {strip.top:g}")
        finale = next(b for b in spec.beats if b.id == plan.finale.beat_id)
        check(strip.until_frame == finale.start_frame, "the title strip runs into the finale")
        check("1 title strip" in t12, f"T12 did not count the title strip: {t12}")
        shown.append(f"title strip {strip.text!r}")
    mean = sum(b.end - b.start for b in plan.beats) / len(plan.beats)
    shown.append(f"beat mean {mean:.2f} s")
    return f"recipe {', '.join(shown)}, "


def check_qa(job: jobs.Job) -> None:
    """`out/qa.json`: T1-T13 ran in order and every one passed (10.1; 006, 016, 023,
    031, 032). The smoke mixes cues, so T6 must have scanned a real SFX stem - its
    no-stem pass would mean the detector never ran; likewise T5 must have measured a
    lag, T7 read every frame, T8 re-validated the plan and read the render log, T11
    judged all eight strip stills, T12 counted the fixture's captions and its two
    stamps, and T13 recorded the empty ledger."""
    report = technical.load_report(job)
    check(report is not None, "qa did not write out/qa.json")
    assert report is not None
    names = [c.name for c in report.checks]
    check(names == list(TECHNICAL_CHECKS), f"qa.json lists {names}, expected {TECHNICAL_CHECKS}")
    for c in report.checks:
        check(c.status == "pass", f"{c.name} failed: {c.detail}")
    details = {c.name: c.detail for c in report.checks}
    check(
        "lip-sync lag" in details["T5"] and f"seed {technical.T5_SEED}" in details["T5"],
        f"T5 did not measure the lag or draw its samples: {details['T5']}",
    )
    check(
        details["T6"].startswith("R1-R4 clean on the SFX stem"),
        f"T6 did not scan the SFX stem: {details['T6']}",
    )
    check(
        details["T7"].startswith(f"{EXPECTED_FRAMES} frames"),
        f"T7 did not read every frame: {details['T7']}",
    )
    check(
        "zero violations" in details["T8"] and "no NetworkError" in details["T8"],
        f"T8 did not re-validate the plan and read the render log: {details['T8']}",
    )
    every_still = f"face on {presenter.STRIP_COUNT} of {presenter.STRIP_COUNT} strip frames"
    check(every_still in details["T11"], f"T11 did not judge every strip still: {details['T11']}")
    check(
        "2 stamps" in details["T12"] and not details["T12"].startswith("0 caption"),
        f"T12 did not count the fixture's captions and stamps: {details['T12']}",
    )
    check(
        details["T13"].startswith("ledger INR 0.00 cash over 0 rows"),
        f"T13 did not record the empty ledger: {details['T13']}",
    )
    check(report.passed, "qa.json says the report failed although every check passed")


def check_critic(job: jobs.Job, critic: FakeCritic, plan: PicturePlan) -> CriticReport:
    """033 (10.2, 10.3): the fake critic scored the delivered short once, advisory, and
    its report sits in `out/qa.json` beside T1-T13 with the plan's category and the
    note that the library has no data for it yet. What it was shown is the proof that
    `build_inputs` works on real media: the gate's sheet, the eight measured stills as
    one strip, the first 2 s of the real short at 4 fps as another, the plan summary
    with the 10.3 numbers, the mix's balance report and the transcript."""
    report = technical.load_report(job)
    assert report is not None
    verdict = report.critic
    check(verdict is not None, "qa.json carries no critic report")
    assert verdict is not None
    check(verdict.status == "scored", f"the critic report is {verdict.status}: {verdict.notes}")
    check(verdict.advisory, "the critic is not advisory (10.2: advisory until calibrated)")
    check(
        [line.name for line in verdict.lines] == [name for name, _ in CRITIC_LINES],
        f"the critic report lines are {[line.name for line in verdict.lines]}",
    )
    check(verdict.model == critic.model, f"the critic report names model {verdict.model!r}")
    check(verdict.category == plan.category, f"the critic scored category {verdict.category!r}")
    check(
        f"no reference data for {plan.category}" in verdict.notes,
        f"the report does not say the library has no {plan.category} data: {verdict.notes}",
    )
    check(critic.calls == 1, f"the critic was called {critic.calls} times, not once")
    (shown,) = critic.inputs
    # 035: the critic saw the sheet before its scores were drawn on it, so the file on
    # disk (composed again afterwards) is the same sheet at the same size, not the same
    # bytes; the panel it now carries is checked in `check_contact_sheet`.
    check(shown.contact_sheet is not None, "the critic was not shown out/contact.jpg")
    assert shown.contact_sheet is not None
    with (
        Image.open(BytesIO(shown.contact_sheet)) as seen,
        Image.open(job.out_dir / "contact.jpg") as final,
    ):
        check(seen.format == "JPEG", f"the critic's sheet is {seen.format}, not JPEG")
        check(seen.size == final.size, f"the critic's sheet is {seen.size}, the final {final.size}")
    check(
        shown.contact_sheet != (job.out_dir / "contact.jpg").read_bytes(),
        "out/contact.jpg was not composed again after the critic scored (035)",
    )
    for name, body, frames in (
        ("PIP strip", shown.pip_strip, presenter.STRIP_COUNT),
        ("hook strip", shown.hook_strip, contact_sheet.HOOK_FRAMES),
    ):
        check(body is not None, f"the critic was not shown the {name}")
        assert body is not None
        with Image.open(BytesIO(body)) as strip:
            check(strip.format == "JPEG", f"the {name} is {strip.format}, not JPEG")
            width = frames * critic_module.STRIP_FRAME_W + (frames + 1) * critic_module.STRIP_GUTTER
            check(strip.width == width, f"the {name} is {strip.width} px wide, not {width}")
    summary = shown.plan_summary
    for needle in (
        f"{len(plan.beats)} beats",
        "modes by runtime: full",
        "1 clamp: (6.1)",
        "0 rescued",
        "origins: ",
        "web: ",
        "generated: ",
        f"category: {plan.category}",
    ):
        check(needle in summary, f"the plan summary lacks {needle!r}:\n{summary}")
    check("inside the 7.3 band" in shown.balance, f"the balance text is {shown.balance!r}")
    check(f"{EXPECTED_WORDS} words" in shown.transcript, "the transcript text lacks the words")
    check(shown.anchors.startswith("## The bar"), "the anchors are not the reference pack's bar")
    return verdict


def check_contact_sheet(sheet: Path) -> None:
    """`out/contact.jpg` per 10.4: a JPEG at the sheet width, under 2 MB, laid out for
    the fixture's eight hook frames and six per-second frames; its summary panel (035)
    carries text on the critic line and the counts line."""
    check(sheet.is_file(), "qa did not write out/contact.jpg")
    check(sheet.stat().st_size < contact_sheet.MAX_BYTES, "contact.jpg is 2 MB or more")
    # 013: the sheet carries the PIP strip row between the hook row and the frames.
    expected = contact_sheet.layout(
        contact_sheet.HOOK_FRAMES, round(fixture.DURATION_S),
        presenter.strip_times(fixture.DURATION_S),
    )  # fmt: skip
    with Image.open(sheet) as image:
        check(image.format == "JPEG", f"contact.jpg is {image.format}, not JPEG")
        check(
            image.size == (expected.width, expected.height),
            f"contact.jpg is {image.size[0]}x{image.size[1]}, "
            f"expected {expected.width}x{expected.height}",
        )
        for slot, what in ((0, "critic line"), (contact_sheet.SUMMARY_LINES - 1, "counts line")):
            box = contact_sheet.panel_line_box(expected.summary, slot)
            region = image.crop((box.x, box.y, box.x + box.w, box.y + box.h))
            colours = len(region.getcolors(maxcolors=1 << 16) or [])
            check(colours > 8, f"the summary panel's {what} is blank ({colours} colours)")


def check_meta(
    job: jobs.Job,
    plan: PicturePlan,
    validated: ValidatedPlan,
    verdict: CriticReport,
    spec: styles.StyleSpec,
) -> None:
    """`out/meta.json` per 10.4 (035): validates against `contracts.Meta` and records
    the delivered short, the versions, the critic's report, the empty ledger and the
    plan's clamps; no rating and no audience yet."""
    path = job.out_dir / meta.NAME
    check(path.is_file(), "the pipeline did not write out/meta.json")
    recorded = Meta.model_validate_json(path.read_text(encoding="utf-8"))
    check(recorded.job_id == job.id, f"meta.json names job {recorded.job_id!r}")
    check(recorded.status == LAST_STATUS and recorded.delivered, "meta.json is not delivered")
    check(
        [c.name for c in recorded.technical] == list(TECHNICAL_CHECKS)
        and all(c.status == "pass" for c in recorded.technical)
        and recorded.technical_passed,
        "meta.json does not carry T1-T13 all passing",
    )
    check(recorded.critic == verdict, "meta.json's critic report differs from qa.json's")
    check(
        (recorded.style, recorded.style_version) == (spec.name, spec.version),
        f"meta.json style is {recorded.style} v{recorded.style_version}, "
        f"expected {spec.name} v{spec.version}",
    )
    check(
        recorded.prompt_version == plan.prompt_version,
        f"meta.json prompt version is {recorded.prompt_version!r}",
    )
    check(recorded.category == plan.category, f"meta.json category is {recorded.category!r}")
    check(
        recorded.reference_pack_version is not None
        and recorded.reference_pack_version == meta.pack_version(),
        f"meta.json pack version is {recorded.reference_pack_version!r}",
    )
    check(recorded.ledger == [] and recorded.cash_inr == 0.0, "meta.json ledger is not empty")
    check(not recorded.over_soft_cap, "meta.json says over the soft cap on a free job")
    check(recorded.clamps == len(validated.clamps), f"meta.json counts {recorded.clamps} clamps")
    check(recorded.rescued == 0, f"meta.json counts {recorded.rescued} rescued beats")
    check(recorded.rating is None and recorded.performance is None, "meta.json is rated already")


def check_inventory(job: jobs.Job, analyser: FakeAnalyser, style: str) -> int:
    """074: the advisory `inventory` step read `out/short.mp4` through the fake analyser
    with the v2 prompt, wrote our card (`tier: own`, the job id, the style) to
    `out/inventory.json`, and `meta.json` carries its comparison rows against the
    style's reference cards. Returns the number of rows."""
    short = job.out_dir / "short.mp4"
    check(
        [path for path, _ in analyser.calls] == [str(short)],
        f"the inventory step read {[path for path, _ in analyser.calls]}, not out/short.mp4",
    )
    card = own.load(job)
    if isinstance(card, own.NotAnalysed):
        raise SmokeFailure(f"the fixture short was not analysed: {card.reason}")
    check(isinstance(card, ReferenceInventoryV2), "the step wrote no out/inventory.json")
    assert isinstance(card, ReferenceInventoryV2)
    check(
        (card.tier, card.video_id, card.styles, card.prompt_version)
        == ("own", job.id, [style], PROMPT_VERSION),
        f"out/inventory.json is {card.tier} {card.video_id} {card.styles} {card.prompt_version}",
    )
    recorded = meta.load(job)
    assert recorded is not None
    found = recorded.inventory
    check(
        found is not None and found.status == "analysed" and found.comparison is not None,
        f"meta.json carries no comparison: {found}",
    )
    assert found is not None and found.comparison is not None
    rows = {row.name: row for row in found.comparison.rows}
    check("shots per 10 s" in rows, f"meta.json's comparison has no shots row: {sorted(rows)}")
    check(rows["shots per 10 s"].ours == 5.0, f"shots per 10 s is {rows['shots per 10 s'].ours}")
    return len(rows)


def check_publishing(job: jobs.Job, plan: PicturePlan) -> None:
    """The copyable text (035): the plan's title, its description with the credits and
    the disclosure line (the fake plan generates scenes), the hashtags."""
    text = publishing.load(job)
    check(text is not None, "no publishing text for the delivered job")
    assert text is not None
    check(text.title == plan.title, f"publishing title is {text.title!r}")
    credits = (job.out_dir / "credits.md").read_text(encoding="utf-8").strip()
    check(
        text.description == f"{plan.description}\n\n{credits}",
        "the description is not the plan's text plus credits.md",
    )
    check(rights.DISCLOSURE in text.description, "the description lacks the disclosure line")
    check(text.hashtags == plan.hashtags[:5], f"hashtags are {text.hashtags}")


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


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m shortsmith.smoke",
        description="Render the fixture end to end with every fake (decision 12.1).",
    )
    parser.add_argument(
        "--style",
        default=styles.DEFAULT,
        help=f"the style spec to render under: a recipe (footage, vishva, fastfacts; 059) "
        f"or a draft such as hitech (048). Default: {styles.DEFAULT}",
    )
    parser.add_argument(
        "--text-pops",
        action="store_true",
        help="judge and render under the style's copy with text pops turned on (061), so "
        "the fake plan's one pop is drawn",
    )
    parser.add_argument(
        "--bubbles",
        action="store_true",
        help="judge and render under the style's copy with bubbles turned on (063), so "
        "the fake plan's dialogue pair is drawn",
    )
    parser.add_argument(
        "--stickers",
        action="store_true",
        help="judge and render under the style's copy with stickers turned on (062), so "
        "the fake plan's one sticker is fetched (fake fetcher) and drawn",
    )
    return parser.parse_args(argv if argv is not None else [])


def main(
    argv: list[str] | None = None,
    *,
    transcriber: Transcriber | None = None,
    planner: Planner | None = None,
) -> int:
    args = parse_args(argv)
    keep = keep_requested()
    with workspace(keep) as root:
        try:
            result = run_smoke(
                root, style=args.style, text_pops=args.text_pops, bubbles=args.bubbles,
                stickers_on=args.stickers, transcriber=transcriber, planner=planner,
            )  # fmt: skip
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
