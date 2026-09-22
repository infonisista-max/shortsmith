"""Planner interface and its fake (decisions 8.1, 8.2, 8.3, 12.1).

Two sequential calls per job on one adapter: `plan_picture` then `plan_sound`, the
sound call receiving the validated, snapped picture plan (ticket 009) and the audio
catalogue tags (an empty list until 022). A call the grammar rejects is re-sent once
with `feedback`: the previous output as JSON and the violation list (8.2); the
adapter appends both to the same prompt. The prompt builder, the `claude_code` CLI
adapter (014) and the `api` adapter (015) arrive with their tickets; selecting either
today yields a planner that fails the job at `planning` with the ticket named, never
a silent fallback to the fake.

`FakePlanner` is co-located so fake and real share one type. Its canned plan is shaped
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

from abc import ABC, abstractmethod
from collections.abc import Sequence

from shortsmith.config import Settings
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


class PlannerUnavailable(Exception):
    """The selected planner adapter is not built yet (or cannot run here)."""


class Planner(ABC):
    @abstractmethod
    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        """The picture call (8.1): beats, hook, finale, keywords, title, description.
        `feedback` is set on the one retry after a rejection (8.2)."""

    @abstractmethod
    def plan_sound(
        self,
        request: PlanRequest,
        picture: PicturePlan,
        catalogue_tags: Sequence[str] = (),
        *,
        feedback: PlanFeedback | None = None,
    ) -> SoundStory:
        """The sound call (8.1), second because cues need the picture plan's beats."""


class UnavailablePlanner(Planner):
    """Stands in for an adapter that a later ticket delivers; every call raises."""

    def __init__(self, name: str, ticket: str) -> None:
        self.name = name
        self.ticket = ticket

    def _refuse(self) -> PlannerUnavailable:
        return PlannerUnavailable(
            f"PLANNER={self.name} is not implemented yet (ticket {self.ticket}); "
            "set PLANNER=fake to run without a paid planner"
        )

    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        raise self._refuse()

    def plan_sound(
        self,
        request: PlanRequest,
        picture: PicturePlan,
        catalogue_tags: Sequence[str] = (),
        *,
        feedback: PlanFeedback | None = None,
    ) -> SoundStory:
        raise self._refuse()


def from_settings(settings: Settings) -> Planner:
    if settings.planner == "fake":
        return FakePlanner()
    ticket = {"claude_code": "014", "api": "015"}[settings.planner]
    return UnavailablePlanner(settings.planner, ticket)


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
            B(id="b08", start=3.5, end=4.0, mode="off", kind="list", motion="reveal",
              subject_kind="concept", query="three things about nothing",
              query_fallback="empty list", source_intent="generate", asset_id="a7",
              enter="spring"),
            B(id="b09", start=4.0, end=4.5, mode="pip", kind="split", motion="pan_left",
              subject_kind="entity", query="two synthetic faces side by side",
              query_fallback="two portraits", source_intent="search", asset_id="a8",
              enter="zoom"),
            B(id="b10", start=4.5, end=5.0, mode="off", kind="wall", motion="pan_right",
              subject_kind="concept", depicts="scene", query="grid of colour gradients",
              query_fallback="colour swatches", source_intent="generate", asset_id="a9"),
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
