"""The variety line (ticket 110c): how varied the job's final plan is, beside the style.

It extends the self-inventory's table (074): `rows(beats, spec)` reads the beats of
`work/plan.json` against the style's variety numbers (110b) and gives four rows -

- the picture treatments used on the still beats (a still with no treatment counts as
  its kind), beside the style's `broll.treatments`;
- the clip share of the runtime against `broll.clip_share_target` (red outside it);
- the enter transitions used, beside `broll.enter_transitions` (red when fewer than
  `broll.non_cut_min_share` of the beats after the first enter on anything but a cut);
- the repeats: showings past `broll.reuse_max` (`grammar.reuse`), the same treatment on
  two beats running, and enters that run past `broll.enter_run_max` (red above 0).

Red rows are logged only (a `job.log` line); they are never a gate - the job is
delivered as the verdict leaves it. Every number comes from the style's front matter.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from itertools import pairwise

from shortsmith import grammar
from shortsmith.contracts import Beat, ComparisonRow
from shortsmith.styles import StyleSpec

TREATMENTS = "variety: treatments used"
CLIP_SHARE = "variety: clip share (of the runtime)"
TRANSITIONS = "variety: transitions used"
REPEATS = "variety: repeats"
DIGITS = 2
EPS = 1e-9


def rows(beats: Sequence[Beat], spec: StyleSpec) -> list[ComparisonRow]:
    b = spec.broll
    runtime = beats[-1].end if beats else 0.0
    stills = [beat.treatment or beat.kind for beat in beats if beat.kind in grammar.TREATED_KINDS]
    share = round(grammar.clip_share(beats) / runtime, DIGITS) if runtime else 0.0
    low, high = b.clip_share_target
    after = list(beats[1:])
    non_cut = sum(1 for beat in after if beat.enter != "cut")
    need = math.ceil(b.non_cut_min_share * len(after) - EPS)
    reused = len(grammar.reuse(beats, spec=spec))
    back_to_back = sum(
        1 for before, beat in pairwise(beats)
        if beat.treatment is not None and beat.treatment == before.treatment
    )  # fmt: skip
    run = b.enter_run_max
    runs = sum(
        1 for i in range(run, len(beats)) if len({x.enter for x in beats[i - run : i + 1]}) == 1
    )
    repeats = reused + back_to_back + runs
    return [
        ComparisonRow(name=TREATMENTS, ours=_tally(stills),
                      refs=f"offered: {', '.join(b.treatments)}"),
        ComparisonRow(name=CLIP_SHARE, ours=share, low=low, high=high,
                      outside=not low - EPS <= share <= high + EPS),
        ComparisonRow(name=TRANSITIONS, ours=_tally([beat.enter for beat in beats]),
                      refs=f"offered: {', '.join(b.enter_transitions)}; not a cut {non_cut} of "
                      f"{len(after)} after the first (at least {need})",
                      outside=non_cut < need),
        ComparisonRow(name=REPEATS, ours=repeats, low=0, high=0, outside=repeats > 0,
                      refs=f"asset reuse {reused}, treatment back to back {back_to_back}, "
                      f"enter runs {runs}"),
    ]  # fmt: skip


def _tally(values: Sequence[str]) -> str:
    return ", ".join(f"{value} {n}" for value, n in Counter(values).most_common()) or "none"
