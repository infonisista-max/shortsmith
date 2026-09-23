"""The fake planner (decision 12.1), in the planner package so fake and real share one
type and return the same model classes.

`FakePlanner`'s canned plan is shaped
for the 6 s fixture: eleven beats tiling 0-6 s (ten of 0.5 s and a 1.0 s finale, so
T3's finale rule holds; ticket 006) with every boundary on a word end or in silence,
a `full` cold open, an `off` hook-cards beat, `pip` beats, and every
tier-1 kind (4.1 as amended by 9.2) named at least once across beat kinds, overlays,
events and presenter modes. Kinds the renderer cannot draw yet are still valid plan
data. The plan passes the grammar under `fixture.smoke_specs` (the explainer copy
with beat, asset-count and ramp numbers scaled to six seconds) with zero violations;
it uses only the explainer's five transitions (9.4). The fake ignores `feedback`.
"""

from __future__ import annotations

from collections.abc import Sequence

from shortsmith.contracts import (
    Beat as B,
)
from shortsmith.contracts import (
    BedQuery,
    Cue,
    CutPlan,
    Event,
    Finale,
    Hook,
    MoodPoint,
    PicturePlan,
    PlanFeedback,
    PlanRequest,
    SoundStory,
    Span,
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


class FakePlanner(Planner):
    PROMPT_VERSION = "fake-1"

    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        beats = [
            B(id="b01", start=0.0, end=0.5, mode="full", reason="cold_open",
              kind="presenter_full"),
            B(id="b02", start=0.5, end=1.0, mode="off", kind="hook_cards",
              asset_id="a1"),
            B(id="b03", start=1.0, end=1.5, mode="pip", kind="photo", motion="ken_burns_in",
              subject_kind="concept", depicts="scene", query="slow colour gradient sky",
              query_fallback="abstract gradient", source_intent="search", asset_id="a1",
              enter="fade", event=Event(kind="stamp", text="NOTHING")),
            B(id="b04", start=1.5, end=2.0, mode="pip", kind="card", motion="push_in",
              subject_kind="entity", query="India Gate Delhi archival photo",
              query_fallback="Delhi monument", source_intent="search", asset_id="a2",
              enter="whip", event=Event(kind="lower_third", text="India Gate · Delhi")),
            B(id="b05", start=2.0, end=2.5, mode="off", kind="map",
              overlays=["pin_drop", "route_arrow", "object_path"], motion="travel",
              subject_kind="entity", query="Delhi to Mumbai route",
              query_fallback="India map", source_intent="generate", asset_id="a4",
              enter="fade"),  # 009: `wipe` is not an explainer transition (9.4)
            B(id="b06", start=2.5, end=3.0, mode="off", kind="chart", overlays=["counter"],
              motion="count_up", subject_kind="number", query="twelve words in six seconds",
              query_fallback="word count", source_intent="generate", asset_id="a5",
              event=Event(kind="stamp", text="12 WORDS"), money_reveal=True),
            B(id="b07", start=3.0, end=3.5, mode="pip", kind="infographic",
              overlays=["label_flyin"], motion="fly_in", subject_kind="concept",
              depicts="scene", query="labelled diagram of a tone burst",
              query_fallback="sound wave diagram", source_intent="generate", asset_id="a6"),
            # 027: the three set pieces carry their own content. Their items name assets
            # other beats already source, so the montage adds nothing to the asset count.
            B(id="b08", start=3.5, end=4.0, mode="off", kind="list", motion="reveal",
              subject_kind="concept", query="three things about nothing",
              query_fallback="empty list", source_intent="generate", asset_id="a7",
              enter="spring", set_piece_title="Three kinds of nothing",
              items=[Item(text="Nothing to see", asset_id="a5"),
                     Item(text="Nothing to hear", asset_id="a6"),
                     Item(text="Nothing at all")]),
            B(id="b09", start=4.0, end=4.5, mode="pip", kind="split", motion="pan_left",
              subject_kind="entity", query="two synthetic faces side by side",
              query_fallback="two portraits", source_intent="search", asset_id="a8",
              enter="zoom", set_piece_title="Delhi versus Mumbai",
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
            hook=Hook(
                title="A Short About Nothing",
                cold_open_span=Span(start=0.0, end=0.5),
                original_position="drop",  # lifted from the head: a no-op reorder (005)
                card_asset_ids=["a1", "a2", "a4"],
            ),
            finale=Finale(beat_id="b11", text="Made from nothing"),
            keywords=[5, 10, 1, 7],
            title="A short about nothing",
            description="Six seconds, twelve words, every kind of picture.",
            hashtags=["#shorts", "#nothing", "#synthetic"],
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
        first, hook_cards = ids[0], ids[1] if len(ids) > 1 else ids[0]
        last = ids[-1]
        cues = [
            Cue(beat_id=first, intent="cold_open_hit", at="start"),
            Cue(beat_id=hook_cards, intent="changeover", at="start"),
        ]
        cues += [
            Cue(beat_id=b.id, intent="money" if b.money_reveal else "popup_tick", at="event")
            for b in picture.beats
            if b.event.kind == "stamp"
        ]
        cues.append(Cue(beat_id=last, intent="finale_hit", at="start"))
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
