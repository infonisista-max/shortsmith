# Style specs

One markdown file per style. The planner reads the spec named by the user's prompt (unknown → `explainer`) and must obey it. A spec has exactly these sections so it can be validated and tested:

1. **Beat grammar** — beat length, presenter modes and switching rules, hook beat, finale.
2. **B-roll** — allowed visual kinds, motion per kind, source order, rights rule.
3. **Captions** — sync unit, phrase length, typography, emphasis rule, placement.
4. **Sound** — bed, levels, ducking, allowed and forbidden cues, loudness targets.
5. **Finale** — closing beat rules.

Rules stated here are contracts: a rendered short that violates one (e.g. a sweep sound, a tight PIP crop) fails technical QC. Add a style by adding a file; never hard-code style rules in code.
