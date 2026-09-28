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

### Sources (the tracer step confirms each API with one live call before building on it; the done note corrects this table if anything differs)

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
- [ ] Operator step, in the done note:
      - the command to build the first shortlist with `.env` back;
      - the drop-folder steps;
      - the page URL;
      - roughly how many minutes of listening it is (about 12 slots × 3).

## Blocked by

- `issues/068-audio-catalogue-tells-the-truth.md` (the kind check)
- `issues/073-reference-card-v2.md` (`moods.yaml`)

## User stories addressed

- Operator, 29 Sep 2026 (grill): "library first, Freesound only as a marked fallback …
  shortlist 3 candidates per mood from free libraries with clear licences, and I only
  say yes or no."
- Operator, run04 QA: no music; "a telephone-ring sound came out of nowhere".
