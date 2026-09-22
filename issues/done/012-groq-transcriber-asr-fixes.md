# 012 — Groq Whisper transcriber adapter and the ASR fix pass

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The real transcriber: one direct Groq Whisper call on the job's audio returning word timestamps, followed by the research §6 fix pass (tail re-run, head-smear check, overlap clamp, fix map) so word times are final before planning. Selected by config; the fake stays the test and smoke default. The call is a ledger row priced per audio minute. Tests assert request construction and response parsing against recorded JSON only.

Covers PRD `transcriber` (real half). Decisions 6.1, 12.1, 13.1.

## Acceptance criteria

- [x] `GroqTranscriber.transcribe(audio_path) -> Transcript` extracts the audio with ffmpeg, calls the Groq audio transcription endpoint with word-level timestamps, and maps the response to Transcript with per-segment logprob flags.
- [x] Fix pass functions are pure and unit-tested on synthetic word lists: tail re-run (re-transcribe the last segment when its flag is low and splice), head-smear check (first word start not before speech onset by more than the research threshold), overlap clamp (no word starts before the previous ends), fix map (the documented substitution table applied to text only).
- [x] The planner never receives word times it can change: `PlanRequest.transcript` is built from the fixed list and the grammar snaps to it (already in 009).
- [x] `TRANSCRIBER` selection lives in `config` (`fake | groq`), defaulting to `groq` outside tests; smoke and tests force `fake`.
- [x] Every Groq call records a ledger row with units in audio minutes.
- [x] Tests under `tests/fixtures/groq/` hold recorded request and response JSON; no network in tests (a transport stub asserts the URL, headers minus the key, and body).

## Done (22 Sep 2026)

- `transcriber` is now a package: `base` (interface, `bind(job)`, `TranscriberError`), `fake`, `fixes` (pure §6 pass), `groq` (adapter), `fixmaps/hi.json` (a copy of `work/asr-fixmap.json`, 38 keys + the In/fact rule). `transcriber.from_settings(settings, ledger=...)` mirrors the planner's; the pipeline calls `transcriber.bind(job).transcribe(raw)`.
- Groq call through the groq SDK (already a dependency): `whisper-large-v3`, `verbose_json`, word + segment timestamps, temperature 0, `language=hi` by default (`TRANSCRIBER_LANGUAGE`, empty = auto-detect; `TRANSCRIBER_MODEL`). Audio is 16 kHz mono MP3 64 kbps at `work/asr/audio.mp3`; raw replies kept as `work/asr/main.json` / `tail.json`; each fix that changed something is a `job.log` line.
- Tail re-run: research rule verbatim (gap > 1.5 s, cut at floor(last_end - 3), splice at last_end); a low-confidence last segment is re-run the same way, spliced at its start. Head smear: words more than 0.3 s before the ffmpeg-detected speech onset (silencedetect -35 dB, 0.3 s) move to the onset. The 0.3 s is ours; research only had a manual check. Overlap clamp 0.05 / 0.12 s verbatim. Segment flags use Whisper's own thresholds (logprob < -1.0, no_speech_prob > 0.6).
- Ledger: `Ledger.estimate(provider, units)` for `check_before_call`; one row per call (main, and tail when it runs) recorded after the API answers, so a refused call is not billed. `providers_in_use` now bills `groq` when `TRANSCRIBER=groq`, not when a key is present.
- `config.check_startup`: `TRANSCRIBER=groq` without `GROQ_API_KEY` is a `ConfigError`.
- **OPERATOR ACTION:** add `TRANSCRIBER=groq`, `TRANSCRIBER_LANGUAGE=hi` (and optionally `TRANSCRIBER_MODEL`) to `.env.example` / `.env`; the agent does not touch `.env*`. The server now refuses to start without `GROQ_API_KEY` unless `TRANSCRIBER=fake`.
- The fixtures in `tests/fixtures/groq/` are hand-written in the documented `verbose_json` shape; the request fixture was captured from the SDK through an httpx MockTransport. Replace the replies with real ones from the first live job. No live Groq call was made from a session.

## Notes from 011

- Take the `ledger.Ledger` at construction (the app holds one on `app.state.ledger`, built in the lifespan). Before the call: `ledger.check_before_call(job, "transcribing", estimated_inr)`; after: `ledger.record(job, "transcribing", "groq", model, {"audio_minutes": minutes})`. The transcriber interface takes only the audio path today, so either pass the job in or return the minutes for the pipeline to record; do not compute INR in the adapter. `ledger.providers_in_use` already requires a `groq` price when `GROQ_API_KEY` is set.

## Blocked by

- Blocked by `issues/011-ledger-prices-caps.md`

## User stories addressed

- User story 26
- User story 60
