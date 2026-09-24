# Reference tooling - tools for learning from reference videos

STATUS: SUGGESTION. No prior ticket has evaluated these tools. Nothing here has been
decided, tried, benchmarked, or ruled out. Do NOT treat any item as already accounted
for by earlier work. If a ticket points you here, your proposal must give an explicit
written verdict on each tool - use it, or reject it with a reason and say what you
would do instead. Silence on a tool is not an acceptable proposal.
The operator may have a better idea than this document. Argue back if you do.

## Why this exists

Job 20260924-062214-b9ac79 passed every technical gate - T1 through T9 green, loudness
in spec, captions rendered, B-roll correctly placed and technically relevant. The
operator rated it 3/10: editing is entry-level, creativity is missing, this will not go
viral.

Read that carefully. Nothing was broken. Every check we own said pass. Our gates measure
whether the video is correct, and correctness is not the bar. The retention load falls
on the operator's script and delivery; the editing does not take over. A system that
only checks itself against its own gates will keep shipping 3/10 and keep reporting
success.

Better prompting does not fix this. The planner has no notion of a good hook - if it
did, it would have written one. Instead it lifted a line from the operator's own script
and put him on screen. Asking that same planner whether its hook is good returns yes,
because it judges against the taste that produced it. The circle only breaks with a
signal from outside the system.

## What these tools change

They turn a reference from an opinion into measurements: cuts per minute, shot-length
distribution, on-screen-text coverage as a percentage of runtime, longest interval with
nothing moving, where the music bed enters and how far under the voice it sits, count of
distinct graphic elements. The same measurements run on our own output. The difference
is arithmetic.

The split that follows:
- The measured bar is the FLOOR. Machine-checkable, closable with no human in the loop,
  and it is where the 3/10 was lost - no music, no SFX, 2.54 s of nothing moving, inert
  graphics are all numbers we failed to hit, not matters of taste.
- The operator's rating is the CEILING. Two shorts can match on every metric and one
  still dies. Taste stays his channel. Do not build a judge that replaces it.

When you evaluate a tool below, weigh it on whether it yields measurements the planner
can target. "The editing is dynamic and engaging" is worthless here. "14 cuts in 45 s,
text on screen 78 percent of runtime, no gap over 0.8 s" is the product.

## Why this matters beyond the current product

Today the pipeline is spined on the operator's own recording: we transcribe his voice,
and the script, beats, timing and PIP all derive from it. If the system can instead
measure a reference and translate it into its own editing decisions, the input stops
mattering - a raw recording, a prompt with no footage, or an ad brief for a business all
become "here is a target, here is the material, hit the bar." That is the difference
between a tool for one person's shorts and a product that can be sold on subscription.
Reference-matching is the defensible part. A one-stop generator is not.

Engineering consequence: keep the source of the script cleanly separated from everything
downstream of it, so a generated script can enter the same pipe a transcribed one does.
Do not let a ticket blur that seam for convenience.

## The tools

Gemini API - watching and listening.
  Processes audio AND visual streams together, answers questions about content, and
  references specific timestamps. Takes a YouTube URL directly: no download, no upload.
  Default static mode samples frames at 1 FPS. Agentic video understanding shipped
  1 Sep 2026 (model chooses what to look at, at what speed, through frames / audio /
  transcript); vendor-reported and NOT independently reproduced: up to 66 percent
  cheaper, up to 88 percent fewer tokens. Pricing at time of writing: Gemini 3.5
  Flash-Lite 0.30 in / 2.50 out per 1M tokens; Gemini 3.7 Flash 0.75 / 3.75 promotional
  through 31 Dec 2026, DOUBLES 1 Jan 2027.

Demucs - audio stems. Open source, Meta. Install: pip install demucs.
  Hybrid Transformer Demucs v4 splits a mix into vocals, drums, bass, other; a 6-stem
  variant adds guitar and piano. Runs on consumer GPUs, self-hosted, no per-use cost.
  Use: separate a reference's voice from its bed and effects, then measure the bed -
  when music enters, how far under the voice, where it drops out, and where whooshes and
  risers actually land (bears on decision 7.1).
  NOTE: an earlier session asserted that a YouTube video has no recoverable stems and
  therefore could not teach sound design. That was wrong and was asserted without
  checking. Un-mixing is solved and free.

PySceneDetect - cut rhythm. Open source. Install: pip install scenedetect.
  ContentDetector / AdaptiveDetector / HistogramDetector / HashDetector. Gives every
  shot boundary with a timestamp; used academically for shot-length analysis to study a
  director's pacing. Use: cuts per minute, shot-length distribution, whether pace
  accelerates into a reveal.

Already on this board - connect, do not rebuild:
  036 yt-dlp (download), 037 OCR (on-screen text), 034 rating-calibration-youtube-fields
  (the ceiling signal), 038 reference URLs (where the set enters the repo), and Whisper
  transcription which is already live.

Cost escape hatch - Qwen. Operator's standing call, 100 percent, do not re-decide.
  Whenever API cost must come down, go Qwen. Qwen3-VL, open weights, Apache-2.0, OCR in
  32 languages, text-timestamp alignment for video temporal grounding. Flagship 235B is
  roughly 471 GB of weights (hosted inference territory); 2B / 4B / 8B / 32B editions
  exist for local use.

## Commercial note

For a sellable product, Gemini's native YouTube-URL analysis is cleaner than downloading
with yt-dlp: downloading other people's videos sits badly against YouTube's terms, while
analysing by URL never copies the file. Not a blocker for the operator's own reference
set. It matters before this is sold.

## Open question, not decided

Does a reference fingerprint become a committed artifact per reference - a JSON of
measured fields consumed by the planner as targets? Proposed only. Belongs with 038 and
the day-14 gate.

## The reference set

The URLs live in docs/references.md, supplied by the operator.
