# Shortsmith PRD

Source documents: `client-brief.md` (the founder's message) and `docs/grill-decisions.md` (45 decisions, branches 1–14, resolved 19 Sep 2026). Every decision is binding, amendments included (4.1 amended by 9.2, 5.6 amended by 11.3, 5.1 and 7.1 and 9.2 are overrides of the brief). This PRD cites decisions by number (`N.k`) and does not restate their text; where this PRD and a decision differ, the decision wins. Where a decision and a style draft under `styles/` differ, the decision wins (1.2 rebuilds the drafts).

## Problem Statement

Creators record themselves telling a story or explaining something and never turn the recording into a Short. Top-level editing takes hours per clip and real skill: a hook that stops the scroll in two seconds, cuts on every beat, relevant moving B-roll for every beat, the presenter moving between full frame, a round picture-in-picture and off-screen, designed word-synced captions, and a music bed with sound hits that never fights the voice. Templates and auto-caption tools produce something that looks auto-made. The creator either spends the evening in an editor or the clip stays on the phone.

Shubham has two approved shorts from an earlier engine that reached the bar, and a research file recording what worked and what failed. The earlier engine is not reusable: it was stitched from n8n workflows, drifted, and cannot be built on. What is needed is a system built from scratch that reaches the same bar from one upload and one button, every time, without a human touching the edit.

## Solution

One web page behind a passcode. The creator uploads a raw recording of their face and voice, writes a brief of a few lines (topic, angle, must-say facts, hook wish), names a style in plain words, optionally attaches reference images or clips with a one-line caption each, and presses one button (2.1, 1.1, 1.3). The page shows the resolved style before submit and a notice when the style asked for is not shipped yet (1.1, 1.4).

The job runs unattended through transcription, planning, sourcing, rendering and QA, and the page shows the current step, elapsed time and render progress (11.1). What comes back is a finished 9:16, 1080x1920, ≤ 60 s Short that looks cut by a top editor: a two-beat hook (3.4), the presenter full-frame, in a round PIP or off-screen by an editing grammar (3.2), script-matched B-roll with motion on every beat drawn from the creator's references first, then web and free libraries, then generated illustration (4.1–4.4, 5.1), maps, charts and motion graphics composed in code when the script needs them (9.2, 9.3), designed word-synced captions with keyword emphasis (6.1–6.3), a copyright-free music bed with editor-style swells, drops and hits under a voice normalised to broadcast loudness (7.1–7.3), and a title, description with credits and hashtags (5.4, 8.1).

Beside the short the page shows a contact sheet a human can review in thirty seconds, the technical gate results, the vision critic's rubric scores and fix notes, the per-step cost, and a 1–10 rating slider whose value is the editorial verdict while the critic calibrates (10.1–10.4, 11.3). Every asset in the short has a rights row, every paid call has a ledger row, and the whole job is reproducible from its plan (5.4, 5.6, 9.1).

The bar is a rating, not a checklist: by day 14, five of Shubham's own recordings each produce a `delivered` short with all technical checks passing, and at least three of the five rate 6/10 or better on the phone without touching anything (14.1).

## User Stories

Actors: **creator** (any user of the page; in v1, Shubham), **rater** (Shubham judging shorts on the phone), **operator** (Shubham running the deployment), **agent** (the coding agent building the system slice by slice from tickets), **reviewer** (anyone reading a contact sheet or a job page).

### Inputs

1. As a creator, I want to upload one raw recording, write a brief of a few lines, name a style in plain words and attach optional references on one page with one button, so that I never open a terminal or an editor. (2.1, 11.1)
2. As a creator, I want the page to tell me before I submit which style it resolved my words to and to show my style note, so that I know what grammar the short will follow. (1.1)
3. As a creator, I want a clear notice when the style I asked for is not shipped yet and the system is using `explainer` instead, so that I am not surprised by the result. (1.4)
4. As a creator, I want my upload rejected immediately with a plain reason when it has no speech, no audio stream, is too short or too long, or would need more than a 1.5x upscale to fill 9:16, so that I fix the recording instead of waiting for a bad short. (2.1)
5. As a creator, I want a one-line framing guideline on the upload page and an early failure when my face cannot be found, so that the PIP always shows my whole head and collar. (3.3)
6. As a creator, I want my reference images to outrank anything sourced from the web for beats about that subject, so that the short shows my product or my face and not a stranger's. (1.3, 4.2)
7. As a creator, I want to caption each reference in one line, so that the planner knows what it shows without seeing it. (1.3, 2.3)
8. As a creator, I want my references logged as owner-supplied in the rights log from the moment of upload, so that the credits never attribute my own picture to someone else. (2.2, 5.4)
9. As a creator, I want the brief to shape intent and the transcript to be the material, so that a fact I wrote as must-say lands on screen as a stamp, label or card even when I only spoke it. (2.3)
10. As a creator, I want a style line like "explainer, 55 seconds, Hindi captions, energetic" to set length, caption language and energy where the spec leaves room, so that plain words are enough. (1.1, 2.3)

### The short

11. As a creator, I want a hook in the first two seconds made of a cold open lifted from the strongest line and a title with three cards, so that the short stops the scroll. (3.4)
12. As a creator, I want the cold-open line never to repeat by accident at its original place, so that the short does not sound like a stutter. (3.4)
13. As a creator, I want myself shown full-frame only for a cold open, an emotional line or an argument turn, never twice in a row, and never more than a quarter of the runtime, so that my face carries weight when it appears. (3.2)
14. As a creator, I want the PIP to show my whole head and collar with the chin anchored, growing when my face is large, so that it never looks like a tight crop. (3.3)
15. As a creator, I want every non-presenter beat to carry a relevant image or graphic that moves, never a static still and never a blank or black frame, so that the short never reads as a slideshow. (4.1, 4.4)
16. As a creator, I want beats to be short and varied with a visual change at least every 1.5 s and no cut ever landing mid-word, so that the pacing matches top shorts. (3.1)
17. As a creator, I want named people, places and products shown from a real image whenever one exists, and an illustration only when reality has no picture, so that my short never passes off a fake photo of a real person or product. (4.2, 5.4)
18. As a creator, I want scenes, environments and unnamed people generated photoreal when needed, so that a "vintage street" beat looks like a photograph and not a cartoon. (4.2, 5.5)
19. As a creator, I want numbers and dates stamped over the previous image with its motion continued, so that a stat lands with punch and no new image is wasted on it. (4.2)
20. As a creator, I want web-sourced images always re-dressed as framed cards with a blurred cover, never shown raw or stretched, so that the short looks designed. (5.1, 5.3)
21. As a creator, I want a landscape or small image shown as a card at its native aspect and only a large portrait image shown full-bleed, so that nothing is stretched, letterboxed in flat black or upscaled beyond 1.5x. (5.3)
22. As a creator, I want a beat with nothing relevant found to be rescued by a re-dressed callback to an earlier image or by my PIP over a gradient with a stamp, so that no beat is skipped and the rescue reads as deliberate. (4.4)
23. As a creator, I want maps with real coordinates, charts from real series and labelled diagrams composed in code, so that a geopolitics or finance short has the graphics the script demands and no AI-garbled borders or text. (9.2, 9.3)
24. As a creator, I want animated pin drops, drawn-on route arrows, sequential label fly-ins, counters and an object moving along a path, so that an explainer looks like a top channel's motion graphics. (9.2)
25. As a creator, I want cuts, fades, whips, zooms and spring fly-ins used with restraint and never a whip on every cut, so that the short does not carry the template tell. (9.4)
26. As a creator, I want captions verbatim in the language I spoke, two to four words per page, paged on my pauses and punctuation, with names and numbers never split, so that captions read naturally at arm's length. (6.1)
27. As a creator, I want the spoken word highlighted in time and one keyword per page boxed, with neighbouring words never shifting, so that emphasis lands without jitter. (6.1, 6.2)
28. As a creator, I want nothing readable placed where the YouTube UI covers the frame, so that captions and stamps are never hidden by buttons. (6.3)
29. As a creator, I want the music to behave like a human editor chose it: a theme fitting the script, swells and drops at the turns, a changeover at a reveal, hits on stamps, reveals and the finale word, so that the short does not sound flat. (7.1, 7.2)
30. As a creator, I want the music about 10 dB under my voice with light ducking, no whoosh, sweep or riser ever, and my voice at broadcast loudness, so that nothing artificial sits over the speech. (7.3)
31. As a creator, I want a finale card with my face in its centre and the captions hidden from the finale word, so that the short ends cleanly. (3.2, 6.1)
32. As a creator, I want a title, a description with credits and an AI disclosure when one applies, and up to five hashtags as copyable text, so that publishing takes one paste. (5.4, 8.1, 11.1)

### Rights and cost

33. As a creator, I want every image, music track and sound effect in my short listed with its source URL, licence text or "unknown", and author, so that I can answer any claim. (5.4)
34. As a creator, I want every generated image recorded with its prompt, model and whether it depicts a named entity or a scene, so that disclosure is exact. (5.4, 5.5)
35. As an operator, I want web image search on by default and switchable off to a free-library-only order without code, so that a shared deployment can be made stricter in one config line. (5.1, 5.2)
36. As an operator, I want a relevance judge to filter candidate images cheaply before download and a vision critic to judge the result, with both models set by config, so that I can swap models when a source rates weak. (5.2, 10.2)
37. As an operator, I want every paid call priced from a file I edit, never from prices in code, so that a vendor price change is an edit, not a release. (5.6)
38. As an operator, I want a soft cap that only flags and a hard cap that stops the job visibly before the next paid call, with nothing ever degraded for cost, so that a cheap short is never a worse short. (5.6, 11.3)
39. As an operator, I want the system to propose caps from the cost distribution of shorts that passed the bar after my first ten metered jobs, so that the caps come from evidence and not from the brief's estimate. (11.3)
40. As an operator, I want every job page to show per-step cost in cash and in subscription tokens side by side and a running average per passing short, so that the switch from subscription planner to API planner is arithmetic. (11.3)
41. As an operator, I want the subscription planner refused unless the deployment declares a single operator, so that nobody runs my subscription for outside users by accident. (8.3, 11.3)
42. As an operator, I want a daily cash budget that closes the upload form until midnight IST, so that a runaway day cannot run away. (11.3)

### Quality gates and evidence

43. As a rater, I want a contact sheet showing the hook strip, one frame per second with beat, mode, kind and asset origin under each, rescued and downgraded beats marked, safe-area outlines and a summary panel, so that I can judge a short in thirty seconds. (10.4)
44. As a rater, I want thirteen technical checks run in order on every job with any failure stopping delivery and naming the failing check, so that I never rate a short with a mid-word cut, a frozen frame, a sweep, or a loudness miss. (10.1)
45. As a rater, I want a vision critic scoring every job on ten editorial lines against a library of the market's best shorts plus my own approved ones, with one reason per line and up to five fix notes, so that every short is judged even when I am not looking. (10.2, 10.3)
46. As a rater, I want the critic advisory while I am the only user, my phone rating stored beside its score, and the critic to become blocking only after it agrees with me on four of five consecutive shorts, so that automation is earned, not assumed. (10.2)
47. As a rater, I want a 1–10 slider and a note on the job page, so that my verdict is the feedback loop and is stored on the job. (10.2, 10.3)
48. As a rater, I want to paste the published URL and its views and retention onto the job later, so that the critic can be checked against a real audience. (10.2, 14.1)
49. As an operator, I want a one-command tool that adds a top-performing short to the reference library by URL, downloads it locally, and measures its cuts, caption pages, visual-change rate, presenter modes, hook, transitions and sound-hit density into the reference docs, so that the library grows by one command forever. (10.3)
50. As an operator, I want a gate command that prints the day-14 three-of-five table, per-component status, the cost distribution with proposed caps, the critic-versus-phone match count and the reference library count per category, listing anything incomplete by name, so that the worth-continuing decision is a printout. (14.1)
51. As a reviewer, I want a job's `meta.json` to record technical results, critic scores, human rating, reference pack version, prompt version, style version and the ledger, so that any short's provenance is complete. (10.4)

### Running the system

52. As a creator, I want a shareable job link behind the same passcode, a step list with the current step highlighted, elapsed time and a percentage during rendering, so that I can leave and come back. (11.1)
53. As a creator, I want a failed job to show a plain sentence for the step that failed and a "retry from this step" button that reuses everything already fetched or generated, so that a planner hiccup costs one retry, not a re-upload. (11.1, 5.6)
54. As a creator, I want a list of my last fifty jobs with status, rating and cost, so that I can find a short again within its retention window. (11.1)
55. As a creator, I want my upload and working files deleted after 24 hours and the finished short and its rights evidence kept for 7 days, so that my raw footage does not sit on a server and my credits outlive the upload. (2.2, 11.2)
56. As an operator, I want one shared passcode stored as a signed cookie, a delay and per-IP block on wrong attempts, limits on upload size, jobs per day, queue depth and job minutes, and a disk guard, so that a public link does not become a public problem. (11.2)
57. As an operator, I want one worker running one job at a time in submission order with queued jobs shown their position, so that the laptop never renders two shorts at once. (9.1, 11.1)
58. As an operator, I want one Docker image that runs on my laptop first and any 4 vCPU / 8 GB VPS second, with fonts, geodata, gazetteer, audio library and the render bundle inside so the renderer needs no network, so that deployment is one image. (9.1, 13.1)
59. As an operator, I want the planner to run on my Claude subscription through the CLI by default for the first month and to be switchable to the API without any change in output shape, so that the switch changes cost and nothing else. (8.3)

### Building it

60. As an agent, I want every external service behind an interface with a deterministic fake co-located with it, so that tests and smoke never call a paid API. (12.1, 13.1)
61. As an agent, I want a synthetic six-second fixture with a drawn face and tone bursts generated per test session, so that face detection, word sync and every tier-1 kind are exercised without a committed video. (12.1)
62. As an agent, I want a smoke command that runs the whole pipeline on the fixture with every fake, including the real render engine, and asserts all thirteen technical checks, so that a broken slice shows in ninety seconds. (12.1)
63. As an agent, I want the plan grammar, pager, ladder, sound rules, ledger and sweeper as pure code behind small interfaces with boundary tests at the exact values in the decisions, so that a wrong number is a failing test and not a bad short. (12.2)
64. As an agent, I want the planner's JSON schema generated from the same models the parser validates, so that prompt and parser cannot drift. (8.1)
65. As an agent, I want every style number in front matter and every component behind a registry check, so that a new style or a missing component is a loader error, not a runtime surprise. (1.2, 9.2)
66. As an agent, I want the first slice to be thin and end to end and a day-3 measurement of seconds per frame on the deployment box, so that the engine choice is confirmed before the components pile on. (9.1, brief)
67. As an agent, I want a ticket that needs a new dependency marked HITL with a note rather than installed, so that the operator approves each new package. (board rules)

## Implementation Decisions

The system is a Python 3.12 package in a src layout plus a Node render project at the repo root. All external services sit behind interfaces with fakes (12.1, 13.1). Modules are listed in dependency order; each states its contract in words and cites its decisions. Bold modules are the deep ones: pure code, wide behaviour, narrow interface, boundary-tested (12.2).

### Global contracts

- **Shared models** live in one `contracts` module: Transcript (words with start/end and per-segment logprob flags), PlanRequest, PicturePlan, SoundStory, ValidatedPlan (with `clamps[]`), CaptionPage, AssetManifest, RightsRow, RenderSpec, QaReport, CriticReport, Meta. All Pydantic, planner-facing ones with `extra="forbid"`; the JSON schema embedded in planner prompts is generated from these models so there is one source of truth (2.3, 8.1). Plan JSON is engine-agnostic (8.1).
- **Job directory** per 2.2: `job.json` is the only index, no database. Retention per 2.2 and 11.2.
- **Statuses** per 11.1 with `failed` carrying `{step, message, detail}`; every transition writes `job.json` and appends to `job.log`.
- **Platform safe area** per 6.3 is global and drawn on the contact sheet (10.4); each style picks its caption zone inside it and the loader asserts PIP/caption non-collision.
- **Transition vocabulary** per 9.4 is implemented once in the renderer; styles enable subsets.
- **Sound numbers** per 7.3 are global; the chain is the research §5 graph verbatim.
- **Tier lists** per 4.1 as amended by 9.2: all listed kinds are tier 1; only full parallax and vector-illustration style are tier 2.

### `config`

Loads settings from the environment with defaults matching `.env.example`: planner selection, asset policy, image generation on/off with model and endpoint, judge and critic and planner model strings, budget soft/hard/daily, upload and queue limits, data directory, passcode, single-operator flag (5.2, 5.5, 8.3, 11.2, 11.3). Startup fails with a config error when the subscription planner is selected without the single-operator flag, or when the API planner has no key (11.3). Prices are not settings; they come from an operator-edited prices file read by the ledger (5.6).

### **`styles`**

Loads every spec as YAML front matter plus five prose sections and validates the seven key groups at startup (1.2). Enforces `status`, the PIP/caption collision assertion, and `requires_components` against the renderer's exported registry (1.4, 6.3, 9.2). Exposes the resolver: score the free-text style line by alias hits, highest wins, zero or tie means `explainer`; draft aliases redirect to `explainer` with a notice; the full line becomes the style note (1.1, 1.4). Renderer and QA read only numbers; the planner reads numbers and prose (1.2). References may refine only subject identity, palette on `animated`/`hitech`, and one mood adjective (1.3).

### `jobs`

Creates and loads jobs, owns the directory layout and the status machine, writes `job.json` on every transition and appends the log, stores the resolved style and note, rating, YouTube performance fields and `swept_at` (2.2, 11.1, 10.3, 14.1). Lists the last fifty jobs with status, rating and cost (11.1).

### **`ledger`**

Appends one row per paid call with step, provider, model, units and INR priced from the prices file; adapters report units only (5.6). Checks the hard cap before every paid call and marks the job failed with the step named when it would be exceeded; the soft cap only flags; the daily cap closes uploads until midnight IST (5.6, 11.3). Subscription tokens are recorded as `tokens_estimated` and valued at the API-equivalent rate for display, never counted in INR (8.3, 11.3). Per-step allowances come from style front matter under `budget` (5.6). Prints the passing-job cost distribution and proposed caps for the gate (11.3, 14.1).

### **`ingest`**

Validates the four inputs server-side per 2.1: ffprobe stream and duration checks, mean-volume speech check, the 1.5x upscale rule for the 1080x1920 centre crop, brief length, reference count, size and short side. Stores raw video, brief verbatim, references with `refs.json` carrying caption, original name, dimensions and `rights: owner_supplied` (2.2). Returns the created job or a plain rejection message.

### `transcriber`

Interface `transcribe(audio) -> Transcript` with a Groq Whisper implementation calling the API directly and a fake returning twelve words aligned to the fixture's tone bursts (12.1, 13.1). Applies the ASR fix pass from research §6 (tail re-run, head-smear check, overlap clamp, fix map) so that word times are final before planning; the planner never touches them (6.1).

### `presenter`

Measures the face once per job from eight stills at the research strip times with a face detector, takes the median box, fails early when fewer than six stills have a face, derives the square full-width PIP window with the chin at the configured anchor, grows the circle for large faces, and writes the eight-frame strip for the contact sheet (3.3). Never tracks (14.1). Produces the ffmpeg cut list from the plan's kept and cut spans and the CFR, no-B-frame re-encode of the presenter cut before rendering (9.1).

### `planner`

One prompt builder renders PlanRequest into fixed sections (spec numbers, spec prose, brief, style note, references as a captioned list, transcript) with the generated JSON schema appended (2.3, 8.1). Three adapters behind one interface with one shared parser: API (one Messages call per planner call, model from config, prompt caching on system and spec, cost from usage), CLI (writes the identical prompt to the job's work directory and runs the `claude` CLI non-interactively with JSON output, no tools, ledger row at zero with estimated tokens), and fake (canned plans for the fixture exercising every tier-1 kind) (8.3, 12.1). Two sequential calls per job: picture then sound, the sound call receiving the validated, snapped picture plan and the catalogue tags (8.1). Each call retries once with the violation list appended on rejection; a second failure fails the job with the list on the page (8.2). Prompts are versioned files and the version is recorded on every plan (8.3). The CLI adapter is the default for the first month (8.3).

### **`grammar`** (plan validator)

Pure code over PicturePlan, Transcript and StyleSpec producing ValidatedPlan or a violation list. Snaps boundaries to the nearest word end within tolerance, clamps what can be clamped and logs each clamp, rejects with a full list what cannot, per the three classes in 8.2. Enforces beat min/max and set-piece max, plan mean, density (3.1); mode runs, full-beat fraction and non-consecutiveness, reason tags, hook mode, finale mode (3.2); the two-beat hook shape, title word count, lifted span boundaries, cold-open duplicate without `keep` (3.4); tier membership with nearest substitute named, one motion per non-presenter beat (4.1); subject-kind labels and the entity-per-60 s rule (4.2); unique-asset min/max and reuse cap with the no-reuse warning (4.3); transition names, whip spacing, no cue on a bare transition (9.4); must-use reference ids present (2.3); cue caps and mood-curve bounds on the SoundStory (7.3, 8.2). Every count is read from style front matter so other styles change behaviour without code (3.2).

### **`captions`**

Pure code from the final word list and the plan's keywords to CaptionPage list: paging per 6.1 (never split marked runs, break on segment punctuation and inter-word gaps, fill to max preferring three), page timing per research §4, emphasis cap with one keyword per page, captions hidden from the finale word, cut spans removed before paging. Lays out each word in a fixed-advance box at its scaled width, measures page width at scaled size and wraps before render, asserts at most two lines (6.2). Places the block at the style's anchor inside the safe area and reports which beats have two-line pages so lower-thirds are suppressed there (6.3).

### **`assets`**

Interface `source_assets(validated plan, references, policy) -> AssetManifest`. Holds the `ImageSource` interface with adapters for web image search, Wikimedia Commons, Openverse, Pexels, Pixabay and a fake; the order is a config list and the policy switch removes web search (5.1, 5.2). Holds the `RelevanceJudge` interface (one vision call over up to six thumbnails scoring 0–3 with fixed reasons, model from config, fake scoring by substring) and code-only hard rejects (5.2). Holds the `ImageGenerator` interface with a Gemini direct-REST adapter and a fake writing a solid PNG with the prompt burned in, two prompt templates selected by `depicts`, always 9:16, per-short cap, one retry (5.5). Applies the fallback ladder in code, records the rung per beat, and fails the technical gate above the rescue limit (4.4). Honours `source_intent` per 5.1, enforces the entity/concept/number/quote source rules and the illustration-only rule for named entities (4.2). Classifies each asset by real dimensions into full-bleed photo or card and records downgrades (5.3). Caches per job by hash of query and source and caches judge verdicts by URL (5.6). Emits a RightsRow per unique asset.

### **`rights`**

Writes `rights.json` with one row per unique asset in the 5.4 shape, appended by the renderer for music and SFX. Derives `credits.md` and the AI-disclosure line for the description, never hand-edited. Implements the T9 completeness rules: every beat's asset has a row, every row has a source URL or an owner/generated origin, every generated row has a prompt, named-entity plus photoreal fails (5.4, 4.2).

### `infographics`

Resolves planner recipes into draw-ready layouts for the renderer: maps from bundled Natural Earth geodata and a bundled gazetteer with a Nominatim fallback cached per job, projected and cropped to the region or bbox, markers and routes by real coordinates; charts from planner series and labels; labelled diagrams from a label-free base image plus code-rendered labels (9.3). The planner is never trusted for coordinates and text never goes inside a generated image (9.3). A `FakeGeocoder` holds a ten-place table (12.1).

### **`sound`** (`sound_director`)

Loads the audio catalogue as text (7.2). Selects the bed by tag overlap and energy distance with drop-point tie-break, searches Freesound with the same tags when below threshold, measures and adds the result with a rights row (7.2). Matches each cue intent to an SFX by tag with the Dyson v2 floor as fallback, derives the floor hits from plan events so a short is never flat, layers planner cues on top, applies cue caps and per-class levels (7.1, 7.3). Builds the mood-curve envelope within the swell/drop/ramp bounds with drops as steps at beat boundaries (7.3). Runs the sweep detector R1–R4 on every SFX file at seed time and on the SFX stem at render time (7.3). Builds the ffmpeg mix graph from research §5 verbatim: voice chain, sidechain ducking, master loudnorm and limiter, stems always written beside the mix (7.3). A `FakeAudioSearch` returns seeded catalogue entries only (12.1).

### `render`

Python bridge and Node project. The bridge writes the engine-specific RenderSpec from the validated plan, caption pages, asset manifest, PIP geometry, infographic layouts and sound plan; runs the Remotion CLI with concurrency two and bt709 colour space, reporting frame progress to the job; runs the ffmpeg cut with word removal, the voice stem, the mix and the final mux with video stream copy (9.1). The Node project holds the composition and exports a component registry the style loader cross-checks (9.2): captions, PIP, photo, card, stamp, lower_third, hook_cards, finale, list, chart, split, wall, map, infographic, pin_drop, route_arrow, label_flyin, counter, object_path, and the six transitions (4.1, 9.2, 9.4). Presenter and B-roll motion parameters, Ken Burns alternation, card framing and stamp behaviour follow 4.1. Everything the renderer needs is bundled so it runs with no network (13.1).

### `qa.technical`

One module running T1–T13 in order and writing `qa.json`; any failure stops delivery and names the check (10.1). Revision proofs are commands in the same module, not gates.

### `qa.critic`

Interface `score(inputs) -> CriticReport` with a vision-model implementation (model from config) and a fake with fixed scores (10.2, 12.1). Inputs per 10.3: contact sheet, PIP strip, hook strip, plan summary, stem balance, transcript, the category's measured pattern data and frames, and the approved-shorts anchors. Output is E1–E10 with one reason each, overall, up to five fix notes. Advisory/blocking mode is derived from the calibration streak stored in a calibration file; the page shows the agreement count (10.2, 10.3). Publishing performance is a manual field or a read-only Data API pull, never an upload (14.1).

### `contact_sheet`

Composes `contact.jpg` per 10.4 from the render output, plan, QA report and critic report, under 2 MB.

### **`reference`**

CLI `shortsmith.reference add <url|channel> --category <c>`: downloads with yt-dlp into the git-ignored work directory, extracts frames with the documented ffmpeg command, measures the pattern data listed in 10.3 (cuts, caption pages, visual-change rate, B-roll fraction and mode timeline, hook structure, transition density, sound-hit density), tags each figure MEASURED or ESTIMATED, and writes the category README in the existing format. The analyser is pure code over a video file and is boundary-tested on a synthetic clip (12.2).

### `pipeline`

The worker: runs the step sequence from 11.1 one job at a time in submission order, enforces the job-minute limit, writes `meta.json` per 10.4, applies `delivered`/`passed`/`rejected` semantics, and implements "retry from this step" reusing the per-job cache (11.1, 5.6, 9.1). Queue depth limit and position reporting per 11.2.

### `app`

FastAPI: passcode entry on the root page with a signed cookie derived from the passcode, delay and per-IP block on failures, every route except health behind the cookie (11.2). Upload form with style chips and live resolution, job page with polling, step list, progress, short, contact sheet, critic panel, rating slider and note, download links, copyable title/description/hashtags, per-step cost in cash and tokens and running average, YouTube performance fields; job list page (11.1, 11.3, 10.3). Daily-budget and disk-guard messages on the upload form (11.2, 11.3). Runs the sweeper as an in-process background task (11.2).

### **`sweeper`**

Deletes `input/` and `work/` after 24 h and the whole job at 7 days, never touches a running job, logs each deletion and records `swept_at`; the same code is a CLI with dry-run; takes a clock so it is testable with a fake (2.2, 11.2). Runs immediately when free disk is below the guard (11.2).

### `smoke` and `gate`

`smoke` runs the whole pipeline on the fixture with every fake including the real render engine and asserts T1–T13; over ninety seconds is a bug (12.1). `gate` computes the day-14 three-of-five table from the five jobs' `meta.json` and prints per-component status, cost distribution with proposed caps, critic-versus-phone match count and reference library count per category, naming anything incomplete (14.1).

### Deployment

One Docker image with Python 3.12, Node 22, the Remotion bundle and Chrome headless shell; laptop first, small VPS second; render concurrency two, one job at a time (9.1). A day-3 tracer bullet measures seconds per frame on the deployment box with the real explainer composition; the knobs above the threshold are concurrency and preview resolution, not the engine (9.1).

### Overrides to project rules

Decision 5.1 overrides the brief's rights-safe default and the matching CLAUDE.md rule; both are rewritten with this PRD so that web image search is the default source and the policy switch is web-search on/off (5.1, 5.2). Decision 7.1 supersedes the brief's "short bass hits only on reveals" and the explainer draft's forbidden-list entries for chimes and ticks; the style drafts are rebuilt under 1.2, so those lines change in that ticket, not by hand now (sweeps and risers remain banned per 7.1; ticks become a planner cue choice under the 7.3 caps). Decision 9.2 overrides any reading of the brief that defers hard components.

## Testing Decisions

**What a good test is here.** A test drives a module through its public interface with the values a decision names and asserts the output or the recorded side effect; it never inspects internals, never calls a paid API, never needs a committed video, and fails with the rule number visible. Boundary tests sit exactly on both sides of every threshold in the decisions (12.2). Tests of real adapters assert only request construction and response parsing against recorded JSON fixtures (12.1).

**Fixture and fakes.** The synthetic six-second clip from 12.1 is generated once per session by the test configuration and never committed; nine deterministic fakes are co-located with their interfaces so fake and real share the type (12.1). There is no prior test code in the repo; this fixture and these fakes are the pattern every later test follows. The two prototypes under `proto/` are evidence, not prior art for tests.

**Boundary-tested modules** (12.2), each with a parametrised edge-case test file listed as acceptance criteria on its ticket:

- `styles` loader: missing key group, draft never shipped, PIP/caption collision assert, `requires_components` against the registry.
- `styles` resolver: alias hit, tie, zero hits, draft redirect notice.
- `ingest`: brief 39/40 chars, upscale 1.49x/1.51x, volume −49/−51 dBFS, duration 19.9/20 s.
- `grammar`: snap within 0.15 s, beat 0.69/0.70 s, mean 1.99/3.21 s, full fraction exactly 0.25, seventh consecutive PIP, duplicated cold-open span, whip spacing.
- `captions`: name run never split, 0.35 s gap break, four words never three lines, keyword cap 0.25 with one per page.
- `assets` ladder: each rung, re-dress on reuse, fifth rescue fails, 1079 px portrait becomes a card.
- `sound`: envelope clipped at +4/−8, ramp under 1.5 s rejected, 21st cue dropped, R1–R4 each with a synthetic offender and a clean file.
- `rights`: missing prompt on generated fails T9, named entity plus photoreal fails, scene plus photoreal passes.
- `ledger`: soft cap flags only, hard cap fails before the paid call, subscription tokens never enter INR.
- `sweeper`: 23 h 59 min untouched, 24 h 01 min swept, running job untouched, 7-day full delete, dry-run writes nothing.
- `reference` analyser: synthetic clip with six cuts yields six cuts per 10 s.

**Ordinary unit tests** for every other module: `jobs` transitions and log lines, `presenter` window maths on the fixture face, `planner` prompt rendering and parser on recorded JSON, `infographics` projection and gazetteer lookup with the fake geocoder, `render` spec construction, `qa.technical` each check on a passing and a failing synthetic input, `qa.critic` parsing with the fake, `contact_sheet` layout and size, `app` routes with the test client behind the passcode, `pipeline` status sequence and retry-from-step with fakes, `config` startup errors (11.3).

**Feedback loops** in order before every commit: lint, type check, tests, smoke (board rules). Smoke is the fourth loop and the tracer bullet's proof (12.1).

## Out of Scope

Per 14.1, confirmed from the brief: accounts and billing; direct YouTube upload; in-browser editing; face-tracking crop; multiple candidates per job; avatar or lip-sync; long-form. Two additions: the `cutout` presenter mode with a matte (3.2); full parallax depth and the vector-illustration style for `animated` (9.2). Two clarifications: YouTube performance logging is a manual field or a read-only API pull, never an upload (14.1a); the PIP face point is a one-time measurement per job, never tracking (14.1b).

Also out of scope for v1: licence filtering of web images (5.1); a cross-job asset cache (5.6); a database of any kind (2.2); websockets (11.1); images passed to the planner as pixels (1.3); playback of reference clips (1.3); shipping any style other than `explainer` on day 14 (1.4); pricing in code (5.6).

## Further Notes

**Slice order for tickets.** The board rules want a thin end-to-end slice first, then expansion. Proposed order, each a ticket or small group:

1. Tracer bullet. Opening tickets: package skeleton, config, contracts, fixture generator, fakes, feedback loops green on an empty pipeline. Then ingest, fake transcriber, fake planner, `jobs`, captions and PIP in a minimal Remotion composition, ffmpeg cut and mux, T1–T4, contact sheet with frames only, job page showing the result. Smoke passes end to end on the fixture. Day-3 seconds-per-frame measurement on the deployment box (9.1).
2. Style loader and resolver, then the grammar validator with its boundary tests, then the pager with its boundary tests.
3. Real transcriber adapter and ASR fixes; presenter measurement; planner adapters (CLI first, API second, output-identical).
4. Assets: sources in 5.1 order, judge, generator, ladder, aspect handling, rights log, credits. Then infographics.
5. Sound director, catalogue seed (Shubham hand-listens the seed files per 7.2), mix graph, sweep detector.
6. Remaining tier-1 components in the renderer with the registry check; transitions.
7. Technical gate T5–T13, critic, calibration, contact sheet summary panel, meta.
8. Reference library tool and the seeded categories (Shubham supplies URLs per 10.3).
9. App hardening: passcode, limits, sweeper, queue, retry-from-step, cost panels, job list, Docker image, gate command.
10. The `hitech` smoke render (1.4, 9.2).

**Operator-supplied inputs**, not produced by the agent: the prices file (5.6); the seed audio library with licence text, hand-listened (7.2); reference short URLs per category (10.3); the five raw recordings with briefs for the day-14 gate (14.1); the passcode and API keys in `.env`.

**Dependencies.** Face detection, geodata handling, audio measurement, OCR for the reference analyser, yt-dlp, YAML parsing, the Node toolchain and the Docker toolchain all need new packages. Per the board rules, a ticket that needs a package not already in the project marks itself HITL with a note instead of installing it.

**Day-14 gate** per 14.1: all five jobs `delivered` with T1–T13 passing, phone rating ≥ 6/10 on at least three of five without touching anything, critic advisory. Gaps are reported by name, never hidden, and no component is cut from scope to make the gate comfortable (9.2).
