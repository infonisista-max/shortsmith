"""The fake planner (decision 12.1), in the planner package so fake and real share one
type and return the same model classes.

`FakePlanner`'s canned plan is shaped
for the 6 s fixture: eleven beats tiling 0-6 s (ten of 0.5 s and a 1.0 s finale, so
T3's finale rule holds; ticket 006) with every boundary on a word end or in silence,
the 055 opening (two `pip` beats asking `photo` (057) - the owner's first reference on
the first when the request has one; the second is drawn as a card when the fixture's
image is a landscape), one `full` beat, more `pip` beats, and every
tier-1 kind (4.1 as amended by 9.2) named at least once across beat kinds, overlays,
events and presenter modes. Kinds the renderer cannot draw yet are still valid plan
data. The `map` beat (020) sources no picture. The plan passes the grammar under
`fixture.smoke_specs` (the explainer copy with beat, asset-count, ramp and pause
numbers scaled to six seconds) with zero violations; it uses only the explainer's five
transitions (9.4). The fake ignores `feedback`.

Ticket 048 renders the fixture under the `hitech` draft, whose enter list is `cut`,
`fade`, `wipe`, `zoom`. The fake keeps its canned enters and swaps any the requested
style does not enable for the nearest one it does (`ENTER_FALLBACKS`: a whip becomes
a wipe, a spring a zoom, and anything still outside the list a cut), reading the list
from `request.style.numbers` so the plan uses every enabled transition once and never
one the grammar would reject. A request carrying no numbers gets the explainer enters.

Ticket 060: b03, the one `full` beat (the turn back to the presenter), asks `flash`,
which becomes a `fade` under every style that does not enable it - the four shipped and
draft styles today. Where the style also allows whooshes (`sound.whoosh` present and
`whoosh` out of `sound.forbidden`), the sound story cues one `whoosh` at that beat's
start, the one cue a bare transition may carry.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from shortsmith.contracts import (
    Beat as B,
)
from shortsmith.contracts import (
    BedQuery,
    Cue,
    CutPlan,
    Event,
    Finale,
    MapMarker,
    MapPlan,
    MoodPoint,
    PicturePlan,
    PlanFeedback,
    PlanRequest,
    PlanStyle,
    SoundStory,
    Span,
    Transition,
)
from shortsmith.contracts import (
    CounterPlan as Counter,
)
from shortsmith.contracts import (
    PlanLabel as Label,
)
from shortsmith.contracts import (
    SeriesPoint as Point,
)
from shortsmith.contracts import (
    SetPieceItem as Item,
)
from shortsmith.planner.base import Planner


def kinds_named(plan: PicturePlan) -> set[str]:
    """Every kind the plan names: beat kinds, overlays, landed events and the
    presenter pseudo-kinds implied by `full` / `pip` modes."""
    named: set[str] = set()
    for beat in plan.beats:
        named.add(beat.kind)
        named.update(beat.overlays)
        if beat.event.kind != "none":
            named.add(beat.event.kind)
        if beat.mode == "full":
            named.add("presenter_full")
        elif beat.mode == "pip":
            named.add("presenter_pip")
    return named


# The explainer's five enters (030), which every style enables in full or in part.
EXPLAINER_ENTERS: tuple[Transition, ...] = ("cut", "fade", "whip", "zoom", "spring")
# 048 (9.4): what a canned enter becomes under a style that does not enable it, in
# order of preference; `cut` is the last resort and is in every list.
ENTER_FALLBACKS: Mapping[Transition, tuple[Transition, ...]] = {
    "whip": ("wipe", "zoom", "fade"),
    "spring": ("zoom", "wipe", "fade"),
    "wipe": ("fade",),
    "zoom": ("fade",),
    "flash": ("fade",),  # 060: the turn back to the presenter fades where no style flashes
    "fade": (),
}
WHOOSH = "whoosh"


def enabled_enters(style: PlanStyle) -> tuple[Transition, ...]:
    """The style's `broll.enter_transitions` from the request's numbers; the explainer
    five when the request carries no numbers (the planner's own tests)."""
    broll = style.numbers.get("broll")
    if not isinstance(broll, Mapping):
        return EXPLAINER_ENTERS
    listed = cast(Mapping[str, object], broll).get("enter_transitions")
    if not isinstance(listed, Sequence) or isinstance(listed, str):
        return EXPLAINER_ENTERS
    return tuple(cast(Transition, str(t)) for t in cast(Sequence[object], listed))


def whoosh_allowed(style: PlanStyle) -> bool:
    """060 (3): the style's `sound` numbers leave `whoosh` out of `forbidden` and carry
    a `whoosh` allowance; a request with no numbers allows none (the explainer's rule)."""
    sound = style.numbers.get("sound")
    if not isinstance(sound, Mapping):
        return False
    numbers = cast(Mapping[str, object], sound)
    forbidden = numbers.get("forbidden")
    banned = (
        WHOOSH in {str(f) for f in cast(Sequence[object], forbidden)}
        if isinstance(forbidden, Sequence) and not isinstance(forbidden, str)
        else True
    )
    return not banned and numbers.get(WHOOSH) is not None


def enter_for(wanted: Transition, enabled: Sequence[Transition]) -> Transition:
    """`wanted` when the style enables it, else its first enabled fallback, else `cut`."""
    if wanted in enabled:
        return wanted
    for alternative in ENTER_FALLBACKS.get(wanted, ()):
        if alternative in enabled:
            return alternative
    return "cut"


class FakePlanner(Planner):
    PROMPT_VERSION = "fake-1"

    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        enabled = enabled_enters(request.style)

        def enter(wanted: Transition) -> Transition:
            return enter_for(wanted, enabled)

        # 055: the short opens with the speaker's first words in `pip` over the strongest
        # images - the owner's reference first when the job has one, else the searched
        # sky (a1) - then the second image, then the one `full` beat (an emotional line)
        # that keeps `presenter_full` in the plan. 057 (4): both opening beats ask
        # `photo`; the smoke's second image is a landscape, so code draws it as a card
        # (with the lower-third on the card strip) and the card path stays rendered.
        first_asset = request.references[0].id if request.references else "a1"
        beats = [
            B(id="b01", start=0.0, end=0.5, mode="pip", kind="photo", motion="ken_burns_in",
              subject_kind="concept", depicts="scene", query="slow colour gradient sky",
              query_fallback="abstract gradient", source_intent="search",
              asset_id=first_asset),
            B(id="b02", start=0.5, end=1.0, mode="pip", kind="photo", motion="ken_burns_in",
              subject_kind="entity", query="India Gate Delhi archival photo",
              query_fallback="Delhi monument", source_intent="search", asset_id="a2",
              enter=enter("whip"), event=Event(kind="lower_third", text="India Gate · Delhi")),
            # 060: the turn back to the presenter flashes where the style enables it.
            B(id="b03", start=1.0, end=1.5, mode="full", reason="emotional_line",
              kind="presenter_full", enter=enter("flash")),
            # 057: b04 is the plan's one planned `card` (every tier-1 kind is named once),
            # the opening's first image again, re-dressed as a card with the stamp.
            B(id="b04", start=1.5, end=2.0, mode="pip", kind="card", motion="push_in",
              subject_kind="concept", depicts="scene", query="slow colour gradient sky",
              query_fallback="abstract gradient", source_intent="search", asset_id="a1",
              event=Event(kind="stamp", text="NOTHING")),
            # 020: the map is drawn from the bundled geodata with the markers at the
            # geocoder's points; it sources no picture. 028 animates its three overlays.
            B(id="b05", start=2.0, end=2.5, mode="off", kind="map",
              overlays=["pin_drop", "route_arrow", "object_path"], motion="travel",
              subject_kind="entity", query="Delhi to Mumbai route",
              query_fallback="India map", enter=enter("fade"),  # 009: `wipe` is not explainer
              map=MapPlan(region="India",
                          markers=[MapMarker(name="Delhi"), MapMarker(name="Mumbai")],
                          route=["Delhi", "Mumbai"], object="plane")),
            # 021: the chart is drawn from the series, the diagram's labels in code. 029:
            # the counter is the chart beat's landed event, counting to its top value.
            B(id="b06", start=2.5, end=3.0, mode="off", kind="chart", overlays=["counter"],
              motion="count_up", subject_kind="number", query="twelve words in six seconds",
              query_fallback="word count", source_intent="generate", asset_id="a5",
              counter=Counter(start=0, target=12, unit="words"), money_reveal=True,
              set_piece_title="Nothing per second", value_unit="words",
              chart_form="bar",
              series=[Point(label="Words", value=12), Point(label="Bursts", value=6),
                      Point(label="Seconds", value=6)]),
            B(id="b07", start=3.0, end=3.5, mode="pip", kind="infographic",
              overlays=["label_flyin"], motion="fly_in", subject_kind="concept",
              depicts="scene", query="labelled diagram of a tone burst",
              query_fallback="sound wave diagram", source_intent="generate", asset_id="a6",
              labels=[Label(text="Tone", x=30.0, y=22.0),
                      Label(text="Burst", x=60.0, y=38.0),
                      Label(text="Silence", x=45.0, y=55.0)]),
            # 027: the three set pieces carry their own content. Their items name assets
            # other beats already source, so the montage adds nothing to the asset count.
            B(id="b08", start=3.5, end=4.0, mode="off", kind="list", motion="reveal",
              subject_kind="concept", query="three things about nothing",
              query_fallback="empty list", source_intent="generate", asset_id="a7",
              enter=enter("spring"), set_piece_title="Three kinds of nothing",
              items=[Item(text="Nothing to see", asset_id="a5"),
                     Item(text="Nothing to hear", asset_id="a6"),
                     Item(text="Nothing at all")]),
            B(id="b09", start=4.0, end=4.5, mode="pip", kind="split", motion="pan_left",
              subject_kind="entity", query="two synthetic faces side by side",
              query_fallback="two portraits", source_intent="search", asset_id="a8",
              enter=enter("zoom"), set_piece_title="Delhi versus Mumbai",
              items=[Item(text="Delhi", asset_id="a1"), Item(text="Mumbai", asset_id="a2")]),
            B(id="b10", start=4.5, end=5.0, mode="off", kind="wall", motion="pan_right",
              subject_kind="concept", depicts="scene", query="grid of colour gradients",
              query_fallback="colour swatches", source_intent="generate", asset_id="a9",
              items=[Item(asset_id="a1"), Item(asset_id="a2"), Item(asset_id="a5"),
                     Item(asset_id="a6")]),
            # 006: the finale is one 1.0 s beat so T3 (finale 0.8-1.2 s) holds on the
            # fixture; the former b11 (photo, ken_burns_out, stamp "6 s") folded into it.
            B(id="b11", start=5.0, end=6.0, mode="off", kind="finale", asset_id="a1"),
        ]  # fmt: skip
        return PicturePlan(
            prompt_version=self.PROMPT_VERSION,
            cut=CutPlan(keep=[Span(start=0.0, end=request.transcript.duration_s)]),
            beats=beats,
            finale=Finale(beat_id="b11", text="Made from nothing"),
            keywords=[5, 10, 1, 7],
            title="A short about nothing",
            description="Six seconds, twelve words, every kind of picture.",
            hashtags=["#shorts", "#nothing", "#synthetic"],
            category="science",  # 033 / 10.3: a seeded category the library has no data for yet
        )

    def plan_sound(
        self,
        request: PlanRequest,
        picture: PicturePlan,
        catalogue_tags: Sequence[str] = (),
        *,
        feedback: PlanFeedback | None = None,
    ) -> SoundStory:
        ids = [b.id for b in picture.beats]
        first, second = ids[0], ids[1] if len(ids) > 1 else ids[0]
        last = ids[-1]
        cues = [
            Cue(beat_id=first, intent="opening_hit", at="start"),
            Cue(beat_id=second, intent="changeover", at="start"),
        ]
        cues += [
            Cue(beat_id=b.id, intent="money" if b.money_reveal else "popup_tick", at="event")
            for b in picture.beats
            if b.event.kind == "stamp" or b.counter is not None
        ]
        cues.append(Cue(beat_id=last, intent="finale_hit", at="start"))
        # 060: one whoosh on the first flash, where the style allows whooshes at all.
        flashed = [b.id for b in picture.beats if b.enter == "flash"]
        if flashed and whoosh_allowed(request.style):
            cues.append(Cue(beat_id=flashed[0], intent=WHOOSH, at="start"))
        end = picture.beats[-1].end
        return SoundStory(
            prompt_version=self.PROMPT_VERSION,
            theme="curious tech",
            mood_curve=[
                MoodPoint(t=0.0, level=0.0),
                MoodPoint(t=picture.beats[1].start, level=2.0),
                MoodPoint(t=end / 2, level=-6.0),
                MoodPoint(t=end / 2 + 0.5, level=0.0),
                MoodPoint(t=end, level=-8.0),
            ],
            bed_query=BedQuery(theme="tech", mood="curious", energy=3),
            cues=cues,
        )
