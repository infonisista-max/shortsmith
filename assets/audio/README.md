# The audio library (decision 7.2)

`catalog.yaml` is the library **as text**: the sound director reads it, scores beds by
tag overlap and energy, and matches cue intents to SFX by tag. The planner is shown only
the tag words (`## 8. Audio catalogue tags` in the sound prompt) and never names a track.

The audio files themselves live beside it (`beds/`, `sfx/`) and are **never committed** —
`*.mp3`, `*.wav` and `*.m4a` are git-ignored repo-wide. A clone therefore has the
catalogue but no files; an entry whose file is missing fails the mix step with its id, and
an empty catalogue simply leaves the short as the voice alone.

## Seeding it: the shortlist and the approved library (ticket 075, replaces 025)

`uv run python -m shortsmith.sound.shortlist [--slot NAME ...]` shortlists three candidates
per slot of `shortlist.yaml` (the active moods and flavours of `moods.yaml`, and the effect
kinds with their `max_len_s`) from Openverse audio (no key; CC0 / CC BY only) and
Freesound (`FREESOUND_API_KEY`; CC0 / CC BY only). Every candidate passes 068's kind check
on its own name and tags, the 023 measure, the sweep detector (effects but a whoosh) and
069's audibility against a reference voice (beds) before it reaches the page; an effect
longer than its `max_len_s` is never downloaded. The files and `shortlist.json` land in
`work/shortlist/` (git-ignored).

Sources with no API (Pixabay music, the YouTube Audio Library, Mixkit, Incompetech): drop
the file into `inbox/` (git-ignored) and run the shortlist; it writes a one-line sidecar
`<file>.source.yaml` beside it. Fill in `source` (`pixabay`, `youtube_audio_library`,
`mixkit` or `incompetech`), `page_url`, `attribution` (required for Incompetech) and
`slot`, then run it again: the file joins its slot with the licence text of
`licences/<source>.txt`. Until then it is listed as "needs source" and cannot be approved.

Listen at `/audio/shortlist` (behind the passcode). **Yes** copies the file into `beds/` or
`sfx/` (git-ignored) and appends its entry to `catalog.yaml` with its source, page URL,
licence, author, credits line, the source's own name and tags, the measurements and the
closed-list tags you confirm (a bed: a mood, optionally a flavour; an effect: its kind).
**No** adds it to `refused.yaml`, so it is never offered again. The app refuses to start
on a `catalog.yaml` tag off the closed lists. `shortlist probe` makes one live request per
API source and prints what it answered; `shortlist fetch-approved` downloads every
approved API file a fresh clone lacks (drop-folder files are yours to keep).

## The facts-default bed (ticket 087)

When a segment's planned flavour, or its mood, has no approved bed, a facts short takes an
approved bed tagged `role: [facts_default]` (the only role on the closed list), not a
random Freesound hit. The director's order per segment is: the planned mood + flavour →
the facts default → a same-mood bed of any flavour → the Freesound search, which runs only
when the library has no `facts_default` bed at all. A style with `sound.facts_default_first:
false` swaps the middle two (076's order). The facts default is levelled and checked by
069 like any bed, and its `fallback bed: facts_default <id> for <mood>/<flavour>` line
reaches `job.log` and the job page.

`facts_default.yaml` is what that bed sounds like, as numbers with their sources: minor
key, static harmony, about 15 % percussive, a sub-bass floor, a ceiling on the energy above
1 kHz, no vocals. The shortlist's `facts_default` slot asks its `queries` first, then the
words of the default mood learned from the reference short cards (the largest runtime
share), and ranks every candidate by its distance to the profile, nearest first; the page
shows the distance and the measured numbers, and a **Yes** writes the `facts_default` role
with the learned mood. The drop folder (Mixkit, Pixabay: dark, minimal, bass-led,
documentary tracks) is probably its main source; give a dropped file `slot:
facts_default` in its sidecar.

## Grown at runtime: `fetched/` (ticket 024)

Effects are never searched for at job time (ticket 070): every cue is one kind of the
closed palette - tick, whoosh, bass, drum, thump, ding - and plays the shortest file the
operator approved into the tracked `catalog.yaml` tagged with that kind and no longer
than the style's length for it; a `fetched/` effect is never played, and a kind with no
approved file drops its cues with a `job.log` line. The cue a mood drop is followed by
plays the approved bass. The rest of this section is the bed's runtime path.

When no catalogue bed clears the style's `sound.bed_score_threshold` (ticket 054), the
sound director asks the Freesound adapter (`sound.freesound`, enabled by `FREESOUND_API_KEY` in `.env`; the key
is free and the search is not metered). It asks with a few plain words, specific to
broad, never the planner's sentence: keywords from the bed query's theme and mood, fewer
of them, the mood alone, one mood word, then the style's `sound.default_bed_query`; an
SFX intent asks with its words and a floor class asks for "`<class> hit`" then the class
word. The search stops at the first adoption. Only CC0 and CC BY results are adopted
(the request carries the licence filter and the result is checked again). The adopted
result's HQ preview is downloaded into `fetched/` (git-ignored like every audio file),
measured by the same script as a seeded entry, and appended to `catalog.yaml` with
`source: freesound`, its licence text, its author, and Freesound's own name and tags
(`source_name`, `source_tags`); its `theme` / `mood` / `intent` are derived from those,
never from the query words (ticket 068). Before any of that, the hit's own name and tags
must fit the kind it is fetched for, per `kinds.yaml`: a bed needs a music word and
carries no vocals and no field recording; no SFX kind may be a ring, phone, bell, chime,
alarm, beep, buzzer, ringtone or siren. A hit that fails is skipped with a note naming
the words. `uv run python -m shortsmith.sound.seed retag` (needs `FREESOUND_API_KEY`)
reads every `fetched/` entry back from Freesound, keeps its name and tags, and removes
each entry - and its file - that fails its kind; it never touches the tracked
`catalog.yaml`. It is then an ordinary library entry with an ordinary rights row (the licence
also appears on its `credits.md` line), and the next job finds it without a call. A
fetched SFX goes through the sweep detector first and is rejected on any hit; beds do
not (a bed is one sound longer than 5 s by definition). Every search is one line in
`job.log` (source, query, HTTP status, hit count, what was adopted) and every cue placed,
fallen back or dropped is another. Without a key the director has no search, says so in
the job log, and a short that goes out voice-only says why on the job page too.

## Tests and the smoke

Neither uses this catalogue. `shortsmith.fixture.make_catalogue` synthesises a temporary
one with ffmpeg (tone beds and click SFX) into a temp directory, the same way
`make_fixture` synthesises the clip; `tests/conftest.py` exposes it as the `library`
fixture and the smoke builds its own. No test reads or writes anything under this folder.
