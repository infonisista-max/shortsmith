# Grill agenda — branches to resolve before the PRD

Use with: `/grill-me the brief is @client-brief.md, prior knowledge is @research.md, style specs are in styles/, and every branch in @docs/grill-agenda.md must be resolved before you stop.`

1. Style system: how a prompt word maps to a style spec; unknown style → default; what a spec must contain; how user references refine a spec.
2. Beat grammar: what a "beat" is; min/max beat length; presenter modes (full / PIP / off) and the rules for switching; PIP framing rule; how the hook beat is built.
3. B-roll: visual kinds per beat (image, clip, card, map, chart, stamp, lower-third); motion per kind; how many assets per short; fallback when nothing relevant is found.
4. Asset sourcing: order of sources; rights log format; ASSET_POLICY switch; image generation (which API, prompt style, cost cap); caching per job.
5. Captions: word-sync source; phrase length; typography; keyword emphasis rule; safe area vs PIP and B-roll.
6. Sound: music library and selection by mood; ducking numbers; allowed hit types; the no-sweep rule as a hard, testable check; loudness targets.
7. Planner: one LLM call or two (beats vs assets); JSON schema; validation and clamping; retry; cost per call; `claude_code` vs `api` adapters.
8. Render engine: ffmpeg-only vs a Remotion layer; decision criterion = the phone test on the prototype; deployment weight of each.
9. QA gates: technical checks list (each one command); editorial rating capture; contact sheet; what "done" means for a job.
10. Jobs and product: statuses, progress, errors, passcode, limits, retention sweeper, cost accounting per job.
11. Testing: fixture clip; fakes for transcriber, style director, assets, image gen; which modules get boundary tests.
12. Out-of-scope confirmation and the worth-continuing line.
