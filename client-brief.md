# Message from Shubham (founder, Shortsmith)

Worth continuing if, by day 14, from any of five of my own raw recordings plus a one-sentence prompt naming a style, the system produces a finished Short in that style — presenter PIP, script-matched moving B-roll, designed captions, hook, copyright-free music — that I would rate 6/10 or better for publishing without touching anything, for at least 3 of the 5. Technical checks passing is not a pass; my rating is.

**The problem.** Creators record themselves telling a story or explaining something and never turn it into a Short, because top-level editing — hook, cuts, B-roll for every beat, presenter in and out of frame, captions, sound — takes hours per clip and real editing skill.

**What I want — the destination.** A web page where a creator uploads a raw recording (their face + voice), types ONE sentence such as "explainer style, 55 seconds, Hindi captions, energetic" or "hi-tech animated style for a product fact", optionally attaches reference images or clips, and presses one button. They get back a publish-ready Short that looks cut by a top editor:
- A viral hook in the first 2 seconds, matched to the script.
- The presenter shown the way top explainers do it: sometimes full-frame, sometimes in a round or framed PIP, sometimes off-screen while B-roll carries the beat.
- Script-matched B-roll for every beat — relevant images or clips with motion (Ken Burns, zoom-to-point, framed archival cards, maps, charts, stamps, lower-thirds) — from the user's supplied images, rights-safe web sources, or AI-generated images.
- Word-synced designed captions with keyword emphasis.
- Copyright-free music bed plus relevant sound hits, voice always on top.
- Title, description, hashtags. 9:16, 1080x1920, ≤ 60 s.

**Styles.** The user names a style in plain words; the system recognises it and applies a written editing grammar from `styles/`. v1 styles: `explainer` (fact/story explainer), `educational` (calm, diagrams, labels), `animated` (motion-graphics heavy), `hitech` (dark, glowing UI, product facts). No examples needed from the user; supplied references only refine.

**Quality bar and settled rules.** The bar is a rating rubric, not a file. 8/10 = I would upload it as-is; 6/10 = I would upload after at most 5 minutes of fixes; below 6 = not publishable. A short scores well when: the hook stops the scroll within 2 seconds; every beat has relevant B-roll that moves; the presenter alternates full-frame / PIP / off naturally; captions are readable at arm's length on a phone; the sound sits under the voice with nothing artificial; no cut lands mid-word. The only reference material the system gets is the written editing grammar in `styles/` and the lessons in `research.md`; my rating and note on each job is the feedback loop. Rules already decided: presenter PIP shows the whole head plus neck/collar, never a tight face crop; no whoosh, sweep or riser transition sounds, ever; music about 10 dB under voice with light ducking; short bass hits only on reveals; voice normalised to −14 LUFS; captions verbatim in the spoken language.

**Hard constraints.**
- One page, one button; no terminal. Shareable by link; passcode in v1; uploads deleted after 24 h.
- Built from scratch in this repo; direct API calls only; no reuse of my earlier engine or n8n workflows as components (their lessons live in research.md).
- Asset rights: default is rights-safe (user-supplied; Wikimedia Commons, Openverse, Pexels, Pixabay with a per-asset rights log; AI-generated). "Any source" is an operator-only switch for my own channel, at my own risk. Music and SFX only from free-licence libraries.
- Cost target: under ₹50 of API spend per short; the planner may run on my Claude subscription for my own use.
- Two QA gates: technical (duration, size, loudness, captions present, rights log complete) and editorial (hook, pacing, visual relevance, captions) — editorial is my rating in v1. Every job produces a contact sheet so a human can review in 30 seconds.
- The first implementation slice must be thin but end to end.

**Not now (v1).** Accounts and billing; direct YouTube upload; in-browser editing; face-tracking crop; multiple candidates per job; avatar or lip-sync; long-form.

I have research.md with what worked and what failed before. Scope this so an agent can build it slice by slice.
