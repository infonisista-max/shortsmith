# 075 — Audio shortlist and the approved library: three candidates per mood and per effect kind, the operator says yes or no

## Type

AFK to build. The listening is the operator's step, named in the done note. Replaces
`025` (moved to `issues/done/` as superseded).

## Parent PRD

`issues/prd.md`

## What to build

Run04 had no audible music and a "phone ring", because every sound was the first
Freesound hit at job time (068, 069, 070). Operator decisions (grill, 29 Sep 2026):

- **Library first.** Jobs take beds from an approved library. Freesound is only a marked
  fallback for beds (076). Effect sounds come **only** from the approved library, with
  no search at job time (070 as amended).
- **Keep listening time small.** The tool shortlists 3 candidates per slot from free
  sources with a clear licence. The operator only says yes or no.
- **First batch of slots:**
  - beds: `tense_dramatic`, `investigative_pulse`, `mysterious_curiosity`,
    `calm_ambient`, plus the flavours `middle_east` and `indian` (073's `moods.yaml`,
    `active`);
  - effects: `tick`, `whoosh`, `bass`, `drum`, `thump`, and a soft `ding` used only on
    an idea/lightbulb sticker (070).
- **Aim:** about 2–3 approved beds per mood, 1 per flavour, 2 per effect kind.

### Sources (written from memory in the grill, with no web access; the afk run has no network, so it builds against recorded fixtures of each API's documented answer shape, and the operator confirms each source live with `shortlist probe` below)

| source | reach | licence check |
|---|---|---|
| Freesound (APIv2, `sound/freesound.py`) | API search | per-sound `license`; keep CC0 and CC BY only (054), then 068's name/tag check against the slot's kind |
| Openverse audio (`/v1/audio/`, covers Jamendo, ccMixter, Wikimedia audio; no key) | API search, the main source for music beds | request filter `license=cc0,by`; the answer's `license` + `license_version` stored |
| Pixabay (music is not in the documented API) | drop folder | Pixabay Content License text from a committed template |
| YouTube Audio Library (no public API) | drop folder | the track's terms as shown in YouTube Studio; attribution line if shown |
| Mixkit (no public API) | drop folder | Mixkit Free License text from a committed template |
| Incompetech (no API) | drop folder | CC BY 4.0, attribution required |

**The drop folder** (`assets/audio/inbox/`, git-ignored):

1. The operator drops downloaded files in the folder.
2. The tool writes a one-line sidecar template per file: `source` (one of the four
   drop-folder sources), page URL, attribution line.
3. The operator fills it in.
4. The file joins the listening page beside the API candidates. The licence text comes
   from the source's committed template, and the operator's yes is the attestation.

### The tool

`uv run python -m shortsmith.sound.shortlist probe` makes **one live request per API
source**: Freesound with `FREESOUND_API_KEY`, Openverse audio with no key. For each it
prints one line: HTTP status, result count, and the first hit's name, licence field and
duration. It downloads nothing and changes no catalogue. With a key missing it says so
and skips that source.

`uv run python -m shortsmith.sound.shortlist [--slot tense_dramatic ...]`:

- **API searches.** Every rung carries a music anchor for beds, and the kind's words and
  `duration:[0 TO max_len_s]` for effects (moved here from 070).
- **Checks on every candidate**, API or drop folder:
  - 068's kind check;
  - the 023 measure script;
  - the sweep detector (effects exempt as 060/070 allow);
  - 069's audibility bound for beds.

  A candidate that fails any of them never reaches the page. The log line names why.
- **Keeps the best three per slot**, written to `work/shortlist/` (git-ignored) with a
  JSON of each candidate's source, licence, measurements and suggested tags.
- **A listening page** `/audio/shortlist` behind the passcode: each slot, three players,
  the licence line, yes / no, and editable mood/flavour or kind tags.
- **A yes** copies the file to `assets/audio/beds/` or `assets/audio/sfx/`. It adds a
  `catalog.yaml` entry with `source`, `source_url`, `licence`, `author`, `source_name`,
  `source_tags`, the closed-list tags and the measurements, plus a credits line.
- **A no** is remembered, so the candidate is never shortlisted again.

Media stays uncommitted per CLAUDE.md. The catalogue and licence text are committed. Add
`.gitignore` entries for `assets/audio/beds/`, `assets/audio/sfx/`,
`assets/audio/inbox/` and `work/shortlist/` if missing. The catalogue records each file's
source URL, so a fresh machine can re-fetch: `shortlist fetch-approved` downloads the
approved API files again. Drop-folder files are the operator's to keep.

## Acceptance criteria

- [ ] With `httpx.MockTransport` and recorded JSON: a Freesound and an Openverse search
      per slot. A CC BY-NC answer is refused; a vocal "bed" is refused by 068's check; an
      effect over `max_len_s` never downloads.
- [ ] A drop-folder file without a filled sidecar is listed as "needs source" and cannot
      be approved. A filled one gets its source's licence template.
- [ ] A yes writes a valid catalogue entry (validated at startup) with the closed-list
      tags. A no is not shortlisted again on the next run.
- [ ] The listening page renders the three candidates per slot behind the passcode (app
      test).
- [ ] Tests never reach the network. Ruff, pyright and every test file are green in
      foreground chunks.
- [ ] `shortlist probe` against `httpx.MockTransport` prints one line per source from
      recorded answers, reports a missing key without calling that source, and writes
      nothing.
- [ ] Operator step, in the done note (the afk run has `.env` parked and no network):
      - first, the exact probe command to run with `.env` back in place,
        `uv run python -m shortsmith.sound.shortlist probe`, and what each line should
        show (status 200, results above 0, a CC0 or CC BY licence field). If a source
        answers differently from its fixture, the operator pastes the line back and the
        adapter and fixture are fixed before any shortlist is built;
      - then the command to build the first shortlist;
      - the drop-folder steps;
      - the page URL;
      - roughly how many minutes of listening it is (about 12 slots × 3).

## Done (29 Sep 2026, afk session)

Built: `src/shortsmith/sound/shortlist.py` (`python -m shortsmith.sound.shortlist`), the
committed slots `assets/audio/shortlist.yaml`, licence templates
`assets/audio/licences/{pixabay,youtube_audio_library,mixkit,incompetech}.txt`,
`assets/audio/refused.yaml`, the page `/audio/shortlist` (template `shortlist.html`), and
`tests/test_shortlist.py` (27 tests) with recorded fixtures in `tests/fixtures/shortlist/`.

Decisions:

- **Slots** are data (`shortlist.yaml`), checked at load against the closed lists (a bed
  slot is an active mood or flavour, an effect slot a kind of `kinds.yaml` with a
  `max_len_s`). Starting effect lengths: tick 0.25 s, whoosh 0.8 s, ding 0.8 s (070's);
  bass 1.5 s, drum 1.2 s, thump 0.8 s (first guesses from the references' 0.4–1 s hits,
  to check by ear).
- **Order of sources:** Openverse first for a bed (the main music source), Freesound
  first for an effect. "Best three" = the first three that pass every check, in the
  sources' own relevance order, rung by rung. Drop-folder files are added beside them.
- **Checks before any download:** refused, already approved, licence (CC0 / CC BY),
  068's kind check, reported length vs `max_len_s`. **After download:** measured length,
  the sweep detector (every effect but a whoosh), and 069's audibility for beds. Beds are
  levelled `bed_db_under_voice` under a reference voice, using the default style's
  numbers. The voice is the fixture clip through the 7.3 voice chain, or `--voice PATH`.
- **Drop-folder files** get the forbidden-words half of the kind check only
  (`kinds.forbidden`), because a hand-picked file's name rarely says "music". Sidecar:
  `<file>.source.yaml`, one line `{source, page_url, attribution, slot}`. Attribution is
  required for Incompetech.
- **A yes** copies the file into `beds/` or `sfx/` and appends to the tracked
  `catalog.yaml` through `freesound.append_entry`, which validates the file and keeps its
  header. The entry id is `<source>_<id>`: the Freesound id or Openverse UUID unchanged,
  so `fetch-approved` reads it back. New contract fields: `AudioEntry.credit` (the
  credits line) and `AudioTags.flavour`. The closed tags are: a bed has ≥1 mood of
  `moods.yaml` plus its flavours; an effect has exactly one kind as its intent.
- **Startup:** `create_app` runs `shortlist.check_catalogue` on the tracked catalogue
  (the runtime `fetched/` one is not asked). A tag off the closed lists stops the app
  and names the entry.
- **A no** goes into the committed `assets/audio/refused.yaml` as `<source>:<id>`, so
  every machine remembers it.
- The job-time director is unchanged: it still reads `catalog.yaml` (+ `fetched/`) as
  before. 070 and 076 switch jobs over to the approved library.

**Not done — the `.gitignore` edit was refused in this afk session.** Media is already
ignored by `*.mp3 *.wav *.ogg *.m4a` and `work/`, so nothing leaks today. But the folders
are not named, and a `.flac` dropped in `inbox/` would show as untracked. Operator, please
add:

```
assets/audio/beds/
assets/audio/sfx/
assets/audio/inbox/
work/shortlist/
```

### Operator step (with `.env` back in place)

1. Probe the two API sources: `uv run python -m shortsmith.sound.shortlist probe`.
   Expect two lines:
   - `openverse: status 200, N results, first '<title>', licence by 4.0 (or cc0 1.0), <d> s`;
   - `freesound: status 200, N results, first '<name>', licence http://creativecommons.org/licenses/by/4.0/ (or publicdomain/zero), <d> s`.

   Each should have N above 0. If a line differs (a status other than 200, 0 results,
   another licence shape), paste it back. The adapter and its fixture get fixed before
   any shortlist is built.
2. Build the first shortlist: `uv run python -m shortsmith.sound.shortlist` (all 12
   slots), or `--slot tense_dramatic --slot tick` for a few. Add `--voice
   path/to/voice.wav` to judge beds against your real voice instead of the fixture's.
3. Drop folder (Pixabay music, YouTube Audio Library, Mixkit, Incompetech):
   - put the files in `assets/audio/inbox/` and run step 2 once, which writes
     `<file>.source.yaml` beside each;
   - fill in `source` (`pixabay` / `youtube_audio_library` / `mixkit` / `incompetech`),
     `page_url`, `attribution` and `slot`;
   - run step 2 again for that slot.
4. Listen at `http://localhost:8000/audio/shortlist` (behind the passcode). For each
   candidate, say Yes (after confirming the mood / flavour or kind) or No.
5. Listening time: 12 slots × 3 candidates = about 36 files. That is about 10–15 minutes
   if you listen to about 20 s of each bed and all of each effect.
6. On a fresh machine: `uv run python -m shortsmith.sound.shortlist fetch-approved`.

Loops: ruff and pyright clean. All 66 test files are green in foreground chunks after
the last source edit. The smoke passes T1–T13. No `src/remotion` change, so no npm loops.

## Blocked by

- `issues/068-audio-catalogue-tells-the-truth.md` (the kind check)
- `issues/073-reference-card-v2.md` (`moods.yaml`)

## User stories addressed

- Operator, 29 Sep 2026 (grill): "library first, Freesound only as a marked fallback …
  shortlist 3 candidates per mood from free libraries with clear licences, and I only
  say yes or no."
- Operator, run04 QA: no music; "a telephone-ring sound came out of nowhere".
