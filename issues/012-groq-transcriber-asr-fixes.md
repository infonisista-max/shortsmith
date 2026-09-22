# 012 — Groq Whisper transcriber adapter and the ASR fix pass

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The real transcriber: one direct Groq Whisper call on the job's audio returning word timestamps, followed by the research §6 fix pass (tail re-run, head-smear check, overlap clamp, fix map) so word times are final before planning. Selected by config; the fake stays the test and smoke default. The call is a ledger row priced per audio minute. Tests assert request construction and response parsing against recorded JSON only.

Covers PRD `transcriber` (real half). Decisions 6.1, 12.1, 13.1.

## Acceptance criteria

- [ ] `GroqTranscriber.transcribe(audio_path) -> Transcript` extracts the audio with ffmpeg, calls the Groq audio transcription endpoint with word-level timestamps, and maps the response to Transcript with per-segment logprob flags.
- [ ] Fix pass functions are pure and unit-tested on synthetic word lists: tail re-run (re-transcribe the last segment when its flag is low and splice), head-smear check (first word start not before speech onset by more than the research threshold), overlap clamp (no word starts before the previous ends), fix map (the documented substitution table applied to text only).
- [ ] The planner never receives word times it can change: `PlanRequest.transcript` is built from the fixed list and the grammar snaps to it (already in 009).
- [ ] `TRANSCRIBER` selection lives in `config` (`fake | groq`), defaulting to `groq` outside tests; smoke and tests force `fake`.
- [ ] Every Groq call records a ledger row with units in audio minutes.
- [ ] Tests under `tests/fixtures/groq/` hold recorded request and response JSON; no network in tests (a transport stub asserts the URL, headers minus the key, and body).

## Notes from 011

- Take the `ledger.Ledger` at construction (the app holds one on `app.state.ledger`, built in the lifespan). Before the call: `ledger.check_before_call(job, "transcribing", estimated_inr)`; after: `ledger.record(job, "transcribing", "groq", model, {"audio_minutes": minutes})`. The transcriber interface takes only the audio path today, so either pass the job in or return the minutes for the pipeline to record; do not compute INR in the adapter. `ledger.providers_in_use` already requires a `groq` price when `GROQ_API_KEY` is set.

## Blocked by

- Blocked by `issues/011-ledger-prices-caps.md`

## User stories addressed

- User story 26
- User story 60
