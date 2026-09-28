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

Ticket 061: where the style's `broll.text_pops_max_per_60s` is over 0 (none of the four
shipped and draft styles; the smoke's `--text-pops` copy and 059's recipe styles), b03
also carries one text pop, "THIS", landing on word 2 ("this" at 1.2 s, 0.2 s into the
beat) at the frame's centre-ish, and the sound story cues a `popup_tick` at its event.
Under a cap of 0 the plan is byte-identical to before.

Ticket 063: where the style's `broll.bubbles_max_per_60s` is over 0 (none of the four
shipped and draft styles; the smoke's `--bubbles` copy and 059's recipe styles), b04 (the
stamped beat) carries a dialogue pair (`FAKE_BUBBLES`): a speech bubble of words 0-1
pointing at the PIP circle and a thought bubble of words 2-3 over the picture. The stamp
stays the beat's landed event, so the sound story is unchanged. Under a cap of 0 the plan
is byte-identical to before.

Ticket 062: where the style's `broll.stickers_max_per_60s` is over 0 (none of the four
shipped and draft styles; the smoke's `--stickers` copy and 059's recipe styles), b01 (the
opening photo) carries one sticker (`FAKE_STICKER`): the `idea` tag above the PIP circle,
landing on word 1. b01 already carries the opening hit, the one cue
`sound.cues_per_beat_max` allows, so the sound story is unchanged. Under a cap of 0 the
plan is byte-identical to before.

Ticket 059: under the recipe styles (`footage`, `vishva`, `fastfacts`) b03 flashes, its
whoosh is its one cue (the pop's tick gives way), and where the style carries
`broll.title_strip` (fastfacts) the plan writes `FAKE_TITLE_STRIP`. Under the explainer the
plan is byte-identical to before.

Ticket 058: b04 is the plan's one `clip` beat - a concept ("drifting clouds timelapse",
`CLIP_QUERY`) asking for moving stock footage under the stamp (and the bubbles), with its
own asset `a3`; with no clip source configured it takes the still ladder like any clip
beat. So that every tier-1 kind is still named once, b02 (the opening's second image,
India Gate, a named entity) is planned as the `card` it was drawn as anyway (its
landscape cannot fill the frame, 057), and the reuse 4.3 asks for moves to b06, the
number beat, which returns to the opening's first image `a1`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from shortsmith.contracts import (
    Beat as B,
)
from shortsmith.contracts import (
    BedQuery,
    Bubble,
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
    Sticker,
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
from shortsmith.contracts import (
    TextPop as Pop,
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


def text_pops_allowed(style: PlanStyle) -> bool:
    """061: the style's `broll.text_pops_max_per_60s` is over 0; a request with no
    numbers allows none (the explainer's rule)."""
    broll = style.numbers.get("broll")
    if not isinstance(broll, Mapping):
        return False
    cap = cast(Mapping[str, object], broll).get("text_pops_max_per_60s", 0)
    return isinstance(cap, int | float) and cap > 0


def bubbles_allowed(style: PlanStyle) -> bool:
    """063: the style's `broll.bubbles_max_per_60s` is over 0; a request with no
    numbers allows none (the explainer's rule)."""
    return _cap_over_zero(style, "bubbles_max_per_60s")


def stickers_allowed(style: PlanStyle) -> bool:
    """062: the style's `broll.stickers_max_per_60s` is over 0; a request with no
    numbers allows none (the explainer's rule)."""
    return _cap_over_zero(style, "stickers_max_per_60s")


def title_strip_allowed(style: PlanStyle) -> bool:
    """059: the style carries a `broll.title_strip` row; a request with no numbers has
    none (the explainer's rule)."""
    broll = style.numbers.get("broll")
    if not isinstance(broll, Mapping):
        return False
    return cast(Mapping[str, object], broll).get("title_strip") is not None


# 059: the fake's title strip, the topic in four words, where the style draws one.
FAKE_TITLE_STRIP = "Twelve words of nothing"


def _cap_over_zero(style: PlanStyle, key: str) -> bool:
    broll = style.numbers.get("broll")
    if not isinstance(broll, Mapping):
        return False
    cap = cast(Mapping[str, object], broll).get(key, 0)
    return isinstance(cap, int | float) and cap > 0


# 062: the fake's one sticker, on b01 (the opening `pip` photo, 0.0-0.5 s): the `idea` tag
# (the grammar writes its first row, the light bulb) above the PIP circle - no `{x, y}` -
# landing on word 1 ("there" at 0.36 s).
FAKE_STICKER = Sticker(intent="idea", word=1)


# 063: the fake's dialogue pair on b04 (the stamped clip beat, 1.5-2.0 s): the presenter's
# own question from words 0-1 ("hello there"), its tail at the top of the PIP circle
# (explainer pip.left 60 + diameter 300 / 2 = 210 px, pip.top 960 px), and the thought it
# prompts from words 2-3 ("this is"), over the picture. Both quote words said before the
# beat, so the grammar lands the first at the beat's start and the second the dialogue
# gap later.
FAKE_BUBBLES: tuple[Bubble, ...] = (
    Bubble(shape="speech", text="Hello there?", first=0, last=1, x=19.4, y=50.0),
    Bubble(shape="thought", text="This is...", first=2, last=3, x=62.0, y=30.0),
)
# 058: the fake's one clip beat asks for moving footage of a concept; the smoke's fake clip
# source answers this query with a synthetic clip.
CLIP_QUERY = "drifting clouds timelapse"
CLIP_FALLBACK = "sky timelapse"


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
        # 061: one pop on the presenter full beat where the style allows pops at all.
        allowed = text_pops_allowed(request.style)
        pops = [Pop(text="THIS", word=2, x=50.0, y=42.0)] if allowed else []
        # 063: the dialogue pair on the card beat where the style allows bubbles at all.
        bubbles = list(FAKE_BUBBLES) if bubbles_allowed(request.style) else []
        # 062: one sticker above the circle on the opening beat where the style allows any.
        stuck = [FAKE_STICKER] if stickers_allowed(request.style) else []

        def enter(wanted: Transition) -> Transition:
            return enter_for(wanted, enabled)

        # 055: the short opens with the speaker's first words in `pip` over the strongest
        # images - the owner's reference first when the job has one, else the searched
        # sky (a1) - then the second image, then the one `full` beat (an emotional line)
        # that keeps `presenter_full` in the plan. 057 / 058: b02 is planned as the
        # `card` (the plan's one; the smoke's India Gate is a landscape that could not
        # fill the frame anyway), with the lower-third on the card strip.
        first_asset = request.references[0].id if request.references else "a1"
        beats = [
            B(id="b01", start=0.0, end=0.5, mode="pip", kind="photo", motion="ken_burns_in",
              subject_kind="concept", depicts="scene", query="slow colour gradient sky",
              query_fallback="abstract gradient", source_intent="search",
              asset_id=first_asset, stickers=stuck),
            B(id="b02", start=0.5, end=1.0, mode="pip", kind="card", motion="push_in",
              subject_kind="entity", query="India Gate Delhi archival photo",
              query_fallback="Delhi monument", source_intent="search", asset_id="a2",
              enter=enter("whip"), event=Event(kind="lower_third", text="India Gate · Delhi")),
            # 060: the turn back to the presenter flashes where the style enables it.
            B(id="b03", start=1.0, end=1.5, mode="full", reason="emotional_line",
              kind="presenter_full", enter=enter("flash"), text_pops=pops),
            # 058: b04 is the plan's one `clip` beat - moving stock footage of a concept
            # under the stamp (and the 063 bubbles); a job with no clip source draws it
            # from the still ladder.
            B(id="b04", start=1.5, end=2.0, mode="pip", kind="clip", motion="push_in",
              subject_kind="concept", depicts="scene", query=CLIP_QUERY,
              query_fallback=CLIP_FALLBACK, source_intent="search", asset_id="a3",
              event=Event(kind="stamp", text="NOTHING"), bubbles=bubbles),
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
            # 058: the number beat returns to the opening's first image (4.3: a reuse).
            B(id="b06", start=2.5, end=3.0, mode="off", kind="chart", overlays=["counter"],
              motion="count_up", subject_kind="number", query="twelve words in six seconds",
              query_fallback="word count", source_intent="reuse", asset_id="a1",
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
              items=[Item(text="Nothing to see", asset_id="a1"),
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
              items=[Item(asset_id="a1"), Item(asset_id="a2"), Item(asset_id="a7"),
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
            title_strip=FAKE_TITLE_STRIP if title_strip_allowed(request.style) else "",
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
        # 060: one whoosh on the first flash, where the style allows whooshes at all.
        flashed = [b.id for b in picture.beats if b.enter == "flash"]
        whooshed = flashed[0] if flashed and whoosh_allowed(request.style) else None
        # 061: a tick where the text pop lands, on the beat that carries one - unless the
        # beat's flash already carries the whoosh (059: the recipes flash b03 and pop on
        # it), the one cue `sound.cues_per_beat_max` allows. (062: the sticker's beat, b01,
        # already carries the opening hit, so it gets no ding of its own.)
        cues += [
            Cue(beat_id=b.id, intent="popup_tick", at="event")
            for b in picture.beats
            if b.text_pops and b.event.kind == "none" and b.counter is None and b.id != whooshed
        ]
        cues.append(Cue(beat_id=last, intent="finale_hit", at="start"))
        if whooshed is not None:
            cues.append(Cue(beat_id=whooshed, intent=WHOOSH, at="start"))
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
