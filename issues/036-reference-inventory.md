# 036 — Reference inventory: what top shorts put on screen, read from the YouTube link alone, and what we cannot draw yet

## Type

AFK — no new packages. Replaces the earlier 036 design (yt-dlp download, frame
extraction, scene-change measurement). 037, 038 and 039 stay parked.

## Parent PRD

`issues/prd.md`

## What to build

Operator, 27 Sep 2026, after run03 (score 6): "right now all videos coming with exactly
same style ... with learnings from urls, the system will have much broader styles to
incorporate." Every short so far is drawn from one style spec (`styles/explainer.md`),
written by hand from the references once; nothing in the system reads a reference.

He added six facts shorts (four creators) as the base for the system, verbatim: "these
are very important facts based shorts, all fall under facts catagory and variety of
scripts, styles, background effects, transition effects and sound effects, they can be
taken as base for the system, system can try to replicate these styles and play with
these styles".

- https://youtube.com/shorts/VSJzviqMO7k — Facts' Mine, "Amazing Facts About Multinational Companies"
- https://youtube.com/shorts/Q2pquJ2FlzA — NeelFacts, "Amazing Facts About EARTH in Hindi"
- https://youtube.com/shorts/cKxkAjYHXbk — Facts' Mine, "Fun Facts That Are Not Funny"
- https://youtube.com/shorts/zXK42RMPKUY — FactTechz, "CRAZY Facts About BRAIN and BODY!"
- https://youtube.com/shorts/bL3rUtUPYsc — FactTechz, "Highest INSANE Temperatures Ever Achieved By Humans!"
- https://youtube.com/shorts/S5j-2CWYYwM — Dhruv Rathee Shorts, "What Would Happen If the Sun Disappeared?"

This ticket builds the tool that turns a reference link into a written inventory of
techniques, and a gap report against what our renderer can draw. It learns techniques
(layouts, effects, transitions, text, sound timing), never content: no video is
downloaded or stored, only JSON and Markdown are committed.

### Tool verdicts (the ones `docs/reference-tooling.md` asks for)

- **Gemini API — use.** It takes a public YouTube URL directly. Google's video
  understanding page, read 27 Sep 2026: YouTube URL input is in preview "at no charge";
  about 100 tokens per second of video at default resolution, about 300 at high; a
  custom `fps` and clip offsets per video; public videos only. The example there calls
  `v1beta/interactions` with `gemini-3.8-flash`; our image adapter calls
  `generateContent`. Use whichever works on the operator's key in the spike below, same
  `GEMINI_API_KEY`, direct REST with httpx like the image adapter.
- **yt-dlp — not used.** Nothing is downloaded, so nothing to add.
- **PySceneDetect, Demucs — not used.** Frame-exact pacing figures are 037's job and 037
  stays parked.
- **Qwen — the operator's standing cost call.** It slots in later as a second adapter
  behind the same `ReferenceAnalyser` interface; a Qwen-VL model needs the video file,
  so it waits until volume makes the cost matter.
- **`046` Docker image — no impact** (no new binary, no new package).

### What the tool does

1. `python -m shortsmith.reference inventory <url> [--category facts] [--tier A]`
   normalises shorts and youtu.be links to `https://www.youtube.com/watch?v=<id>`
   (tracking parameters such as `si=` dropped), sends one request with the video and
   the versioned prompt `reference/prompts/inventory_v1.md`, at a frame rate that
   catches a 0.2 s whip (`REFERENCE_FPS` in config; propose the value and say why),
   parses the answer into a Pydantic `ReferenceInventory` and writes
   `docs/reference/inventory/<video_id>.json`. Model and fps come from config
   (`REFERENCE_MODEL`, `REFERENCE_FPS`, both in `.env.example`).
   `inventory --all` does every link in `docs/references.md`, one request each.
2. The inventory, every field tagged ESTIMATED (model-observed, timestamps approximate):
   - every shot: start and end (s), layout (full-screen still, full-screen moving
     footage, card, split, grid, text-only, presenter full, presenter circle, map,
     chart, other) and what is behind it (still photo, moving footage,
     generated or animated, solid or gradient, blur); for moving footage also what kind
     it looks like (stock footage, archival or news, AI-generated, screen recording,
     animation), how long each clip runs, and its treatment (slow motion, speed ramp,
     zoom, colour grade, overlay);
   - every effect: time, duration, what it emphasises (word, number, image, speaker),
     one-line description, and our component name from `src/remotion/registry.json`
     or `unregistered`;
   - every transition: time, kind, duration, registered or `unregistered`;
   - the text look: caption position, size, colours, active-word treatment, how titles
     and numbers animate in;
   - sound: bed yes/no and its mood; every sound effect with time and kind (whoosh,
     hit, riser, click, ding, other) and what it is synced to;
   - the hook: what is on screen and heard in the first 3 s;
   - counts: shots, effects and sound effects per 10 s.
3. The prompt lists the registry names with their one-line meaning from
   `docs/components.md` so the model can label; code checks every label against the
   registry, and an unknown name becomes `unregistered`.
4. `python -m shortsmith.reference gaps` reads every inventory JSON and writes
   `docs/reference/inventory/GAPS.md`:
   - unregistered effects and transitions ranked by how many references use them, each
     with up to three example links at the moment (`&t=<s>s`) so the operator can watch
     them;
   - per reference: share of runtime by layout and by background kind (moving footage
     split by kind), median clip length, shots per 10 s, sound effects per 10 s;
   - Tier A, Tier B and facts kept in separate tables, never pooled.
5. `docs/references.md` gains a section "Facts — category `facts`, Tier A" with the six
   links, creators, titles and the operator note above verbatim.

## Acceptance criteria

- [ ] Tracer bullet first: before the rest is built, two live calls succeed on the
      operator's key — `S5j-2CWYYwM` (Dhruv) and `zXK42RMPKUY` (FactTechz). The done
      note names the endpoint, model and fps that worked.
- [ ] URL normalisation: the six operator links, a youtu.be link and a watch link with
      extra parameters all become plain watch URLs (unit test).
- [ ] A recorded answer fixture parses into `ReferenceInventory`; an unknown component
      label becomes `unregistered`; a malformed answer is retried once, then the tool
      stops with one message naming the video and writes no partial JSON.
- [ ] A private or failing video logs its HTTP status and the tool moves on to the next
      link under `--all`.
- [ ] `gaps` on three fixture inventories ranks unregistered items by reference count,
      with timestamped example links, and prints the layout/background share tables
      per tier.
- [ ] Every request logs tokens used, so a price change after the preview is visible.
- [ ] The two spike inventories are committed under `docs/reference/inventory/`; the
      full `--all` run is NOT part of this ticket (the operator reviews the prompt and
      the two spikes first). No video file is written anywhere.
- [ ] Tests never reach the network; ruff, pyright, every test file green in foreground
      chunks.
- [ ] Done note: the path of `inventory_v1.md` for the operator to read, what the two
      spikes found (layout shares, the unregistered items), the command for the full
      run, and the one line for 10.3 ("the reference tool reads the YouTube link through
      Gemini; nothing is downloaded") for the operator to paste.

## Blocked by

- Nothing.

## User stories addressed

- User story 49.
- Operator, 27 Sep 2026: "system must learn from urls we provided including dhruv
  rathi"; "all videos coming with exactly same style".
