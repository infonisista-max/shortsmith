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

- [ ] A fake video source and a synthetic 3 s clip made in the test with ffmpeg
      (`testsrc`): a `clip` beat renders full-screen, muted, under the PIP circle and
      captions, and a frame at the beat's middle differs from its first.
- [ ] The smoke plan gains one `clip` beat; smoke explainer and hitech pass T1–T13; the
      render time is logged next to the previous smoke's.
- [ ] A named-entity beat (053's F1 fixture) is never offered a clip.
- [ ] A 1920 × 1080 clip is accepted (1.78x); a 1280 × 720 clip (2.67x) is not; a clip
      shorter than its beat is skipped; with no usable clip the beat takes the still
      ladder and `job.log` says why.
- [ ] Pexels sends the key in the header; Pixabay's key is scrubbed from every logged
      URL (test on the log text); both searches log source, query, status and hit count.
- [ ] The master carries no clip audio (checked on the mix stems).
- [ ] Rights rows and credits lines exist for every clip; the contact sheet marks clip
      beats with their own origin letter.
- [ ] Planner prompt version bumped by one: when to ask `clip`, never for a named
      entity; the fake planner emits one `clip` beat.
- [ ] `npm run typecheck`, `npm test`, ruff, pyright, every test file green in foreground
      chunks.
- [ ] Done note: the amendment lines for 4.1 and 5.1 for the operator to paste, and what
      to look at on the next real job (clip count, clip relevance, render time).

## Blocked by

- Nothing.

## User stories addressed

- Operator, 27 Sep 2026: "video clips can also be used from various free resources".
- Operator, 27 Sep 2026: the six facts references "variety of ... background effects".
