# 058 — Moving footage: free stock video clips from Pexels and Pixabay on concept beats

## Type

AFK — no new packages (Remotion's own video component, the existing httpx adapters).

## Parent PRD

`issues/prd.md`

## What to build

Operator, 27 Sep 2026: "video clips can also be used from various free resources, other
youtubers use this only why only stick to photos". Today every B-roll beat is a still
(`photo`, `card`, the set pieces) or a drawn component; the renderer has no moving
footage. The Pexels and Pixabay adapters (018) search photos only. Both sites serve free
video with the same keys (their API pages, read 27 Sep 2026):

- Pexels: `GET https://api.pexels.com/v1/videos/search` (`query`, `orientation`, `size`,
  `per_page`), key in the `Authorization` header; each video has `width`, `height`,
  `duration`, a preview `image`, the page `url`, the `user`, and `video_files` (`link`,
  `width`, `height`, `quality`, `fps`). 200 requests an hour, 20,000 a month. Asks for a
  visible credit ("Video by <name> on Pexels").
- Pixabay: `GET https://pixabay.com/api/videos/` (`q`, `video_type`, `min_width`,
  `min_height`, `per_page`), key as a query parameter; each hit has `duration` and
  `videos.large/medium/small/tiny` with `url`, `width`, `height`, `size`, `thumbnail`.
  100 requests a minute. Recommends storing the file rather than hotlinking.

Operator decisions, 27 Sep 2026, approved in the paired review at 23:12 IST (amend 4.1
B-roll kinds and 5.1 source order; the operator records them in `docs/grill-decisions.md`
from the done note):

1. **A new B-roll kind `clip`:** a full-screen moving shot, always muted, under the PIP
   circle and the captions exactly like `photo`. The planner may ask `clip` on concept
   beats (a thing, a kind of place, a process, nature, science: "cheese", "the sun",
   "the brain") and on the opening when the topic is a concept.
2. **Never for a named entity.** A beat whose subject is a named person, place, product
   or event (053) never takes a stock clip: King Saud is never a stranger in a video
   either. Those beats keep today's still ladder.
3. **Sources:** Pexels video, then Pixabay video (`film`; `animation` only when the beat
   asks for it). Portrait first; a landscape clip is accepted when its 9:16 crop covers
   1080 × 1920 at ≤ `broll.full_bleed_max_upscale` (2.0). The file downloaded is the
   smallest that meets that bar, capped at 80 MB, into the job's asset folder — never
   committed, never hotlinked at render time.
4. **Relevance:** the existing judge scores the clip's preview image (Pexels `image`,
   Pixabay `thumbnail`) against the beat's query on the same 0–3 scale; 053's
   stock-host and watermark rules apply to clips too.
5. **Length:** a clip is used only when it is at least as long as its beat; otherwise
   the next candidate; if none fits, the beat falls back to the still ladder, logged.
6. **Motion and speed:** the style's `broll.motion.clip` — a slow push and a playback
   speed — and the share of runtime clips may take (`broll.clip_max_fraction`). The
   numbers come from the reference inventory (036, 12 shorts, ESTIMATED; read in the
   paired review 28 Sep 2026): push none, `scale_from 1.0, scale_to 1.0` (4 of the 119
   reference clips were pushed: the clip's own movement is the motion); speed `1.0` (5 of
   119 were slowed or ramped); `clip_max_fraction: 0.35` in explainer, educational,
   animated and hitech (median moving-footage share across the 12 is 31%; the footage-led
   facts shorts run far higher, which the recipe styles of 059 set for themselves).
7. **No repeats:** a clip counts as an image for 056's reuse rule (at most two showings).
8. **Rights:** one rights row per clip (source, page URL, author, licence: "Pexels
   License" / "Pixabay Content License"); `out/credits.md` carries "Video by <name> on
   Pexels" / "on Pixabay". The Pixabay key never appears in a log line or a rights row.

## Acceptance criteria

- [x] A fake video source and a synthetic 3 s clip made in the test with ffmpeg
      (`testsrc`): a `clip` beat renders full-screen, muted, under the PIP circle and
      captions, and a frame at the beat's middle differs from its first.
- [x] The smoke plan gains one `clip` beat; smoke explainer and hitech pass T1–T13; the
      render time is logged next to the previous smoke's.
- [x] A named-entity beat (053's F1 fixture) is never offered a clip.
- [x] A 1920 × 1080 clip is accepted (1.78x); a 1280 × 720 clip (2.67x) is not; a clip
      shorter than its beat is skipped; with no usable clip the beat takes the still
      ladder and `job.log` says why.
- [x] Pexels sends the key in the header; Pixabay's key is scrubbed from every logged
      URL (test on the log text); both searches log source, query, status and hit count.
- [x] The master carries no clip audio (checked on the mix stems).
- [x] Rights rows and credits lines exist for every clip; the contact sheet marks clip
      beats with their own origin letter.
- [x] Planner prompt version bumped by one: when to ask `clip`, never for a named
      entity; the fake planner emits one `clip` beat.
- [x] `npm run typecheck`, `npm test`, ruff, pyright, every test file green in foreground
      chunks.
- [x] Done note: the amendment lines for 4.1 and 5.1 for the operator to paste, and what
      to look at on the next real job (clip count, clip relevance, render time).

## Blocked by

- Nothing.

## User stories addressed

- Operator, 27 Sep 2026: "video clips can also be used from various free resources".
- Operator, 27 Sep 2026: the six facts references "variety of ... background effects".

## Done note (28 Sep 2026)

Finished in a recovery session: an earlier session was killed with the whole slice in the
working tree and nothing committed. This session checked it against every criterion above,
fixed the one red test file (the recorded Claude CLI and Anthropic API replies in
`tests/fixtures/claude_cli/picture.json` and `tests/fixtures/anthropic/picture.json` still
held the fake plan from before 058; their beats were re-recorded from `FakePlanner` by a
throwaway script under `work/`, so only the `result` / `text` line changed), added a
`test_rights.py` unit for the clip row and its "Video by … on Pexels / Pixabay" credit, and
ran every loop.

What was built:
- `Tier1Kind` `clip`; `AssetRecord.kind` / `RightsKind` `clip`, `duration_s` on the
  candidate and the record; `VisualSpec` `clip` with `speed` and `start_s`.
- `assets/clips.py`: `PexelsClipSource` (key in the `Authorization` header),
  `PixabayClipSource` (key as a query parameter, `scrub` removes it from every note and
  log line; `film` unless the query asks for animation), `choose_file` (the smallest file
  that covers 1080x1920 at ≤ `full_bleed_max_upscale`, ≤ 80 MB), a streamed, type-checked
  download, and `FakeClipSource` (a `testsrc2` clip with a 440 Hz tone, so a render that
  carried the clip's sound would be caught).
- The asset step runs the clip ladder before the still ladder: a planned reuse, then Pexels
  video, then Pixabay video on `query` then `query_fallback`, judged on the preview image,
  long enough for the beat and the `number` / `quote` beats that carry it on. A named
  entity is never searched for a clip; no usable clip → the still ladder; both are logged
  in `job.log`.
- Grammar: `clip` on concept beats and the opening only, never a named entity, at most
  `broll.clip_max_fraction` of the runtime, the asset is footage and never a set piece's
  still. Styles v9 carry `clip_max_fraction: 0.35` and `motion.clip`
  (`scale_from 1.0, scale_to 1.0, speed 1.0`).
- Render: the Remotion `Clip` component, muted, in the photo's layer; no face detection runs
  on a clip. The contact sheet marks a clip beat `Pv` (Pexels video) / its own letter.
- Prompt v12 (picture and sound) with recorded snapshots; the fake plan's b04 is the clip
  beat (b02 is planned as the card, b06 reuses a1). The smoke checks the clip end to end
  and prints the picture render seconds.

Render time: smoke explainer 56.4 s total (picture render 25.9 s) against 55.4 s before
058; hitech 55.8 s (render 24.6 s) against 55.4 s.

Amendment lines for the operator to paste into `docs/grill-decisions.md`:
- **4.1 (amended by 058, 27 Sep 2026):** tier 1 gains `clip` - a full-screen moving shot
  from a free stock video library, always muted, under the PIP circle and the captions like
  `photo`; only on concept beats and a concept opening, never for a named person, place,
  product or event; clip beats take at most `broll.clip_max_fraction` of the runtime
  (0.35 in the four styles), drawn at `broll.motion.clip` (no push, speed 1.0); a clip
  counts as an image for the reuse rule.
- **5.1 (amended by 058, 27 Sep 2026):** a `clip` beat's sources are Pexels video, then
  Pixabay video (`film`; `animation` only when asked), before the still ladder; the file is
  the smallest whose 9:16 crop covers 1080x1920 at ≤ `full_bleed_max_upscale` under 80 MB,
  downloaded into the job folder; the relevance judge scores its preview image; a clip
  shorter than its beat is skipped; no usable clip → the still ladder, logged. Rights rows
  say "Pexels License" / "Pixabay Content License" and credits say "Video by <name> on
  Pexels / Pixabay".

On the next real job, look at:
- clip count: how many beats the planner asked `clip` and how many got one (`job.log`
  "no usable clip" lines against `sourcing:` lines);
- clip relevance: the judge's scores on the preview images, and whether the moving shot
  matches the words on the phone;
- render time: `render.log`'s `render_s` against a stills-only job of the same length
  (real clips are bigger files than the smoke's 3 s synthetic one).
