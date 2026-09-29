# 087 — A facts-default bed, learned from the references, that the director falls back to before any random search

## Type

AFK — no network, no keys. Runs in the same afk run as 086 (operator, 29 Sep 2026).
Approving the first facts-default bed is an operator step afterwards (075's page).

## Parent PRD

`issues/prd.md`

## Why

Operator, 29 Sep 2026 (079 HITL): when a flavour, or even a mood, has no approved bed,
a facts short should take the kind of bed fact channels always use, not a random
Freesound hit. The evidence:

1. Across the 12 reference shorts (long-form `id00R-3OmJ0` left out), `investigative_pulse`
   covers 46% of the runtime and `tense_dramatic` 23% (the reviewer's count over the v2
   cards' parts).
2. The approved old-engine Dyson v2 short: its bed was Mixkit 267 "Trap Hamza" (Arulo,
   Mixkit Stock Music Free License), chosen by spectrum match to two reference clips.
   `research.md:115`: minor key, static harmony, about 15% percussive, no vocals.
   `work/old-engine/08_JOB_RECORDS/DysonToothbrush/v2/v2_reference_analysis.md:13,32`:
   the reference beds were an A-minor sub-bass drone (drums 0%) and an 808 trap bed
   (drums 21%); Trap Hamza is 77–79% sub-bass; all three put under 1% of the music's
   energy above 1 kHz. The audio file itself is not in the archive, only its record.
3. The 079 shortlist is weakest exactly there. `investigative_pulse` got 2 candidates,
   both music boxes. The one real soundtrack was refused on 069's speech-band ceiling.
   Openverse returned 0 for most slots, and `middle_east` got 0.
4. 076 already falls back from a missing flavour to the same mood, then to a Freesound
   search (`FALLBACK_LINE`, `sound/__init__.py:533`). So the gap is mainly the library
   plus that last rung.

## What to build

- **The default mood, learned.** A pure function over the loaded v2-schema cards (so
  086's skip rule applies): the mood with the largest runtime share across the Tier A
  and Tier B short cards' parts, long-form and `null` parts excluded. Runner-up and
  shares are logged. No mood name in code.
- **The profile, as data.** A committed file (e.g. `assets/audio/facts_default.yaml`)
  with the target numbers and a source comment on each: minor key, harmonic-change
  ceiling ("static harmony"), percussive share around 15%, sub-bass share floor,
  energy share above 1 kHz ceiling, no vocals (068's kind check). The starting values
  come from the two documents above. Where a document gives a range, the file says so.
  Measured with the features `sound/seed.py` already computes (chroma/key) plus band
  shares in numpy. No new dependency.
- **The director's chain.** For each segment: the planned mood + flavour → same mood,
  any flavour (076) → **an approved bed tagged `facts_default`** → the Freesound search
  only when the library has no `facts_default` bed at all. Each rung has its own log
  line: `fallback bed: facts_default <id> for <mood>/<flavour>, no approved bed`. The
  facts default is still levelled and checked by 069 like any bed.
- **The shortlist.** A slot `facts_default` in `assets/audio/shortlist.yaml`. It searches
  with the learned mood's queries, and its candidates are ranked by distance to the
  profile (nearest first), not by the source's relevance order. The page shows each
  candidate's distance and its measured profile numbers. A yes tags the catalogue entry
  `facts_default` (closed-list tag, validated at startup).
- **Every 069 line carries its level.** A speech-band refusal or repair line names the
  bed level it was measured at (dB under the voice). A margin without its level is not
  comparable across yardsticks (see below).

## 069 and the facts-default profile: reconcile before any facts-default bed is approved

Reviewer and operator, 29 Sep 2026:

- `styles/vishva.md:150` sets `speech_band_margin_max_db: 20` from run03 (9.4, heard)
  against run04 (28.7, not heard). But run04's bed was `freesound_557546`, adopted by the
  query "regal" (run04 `job.log:112`). The operator identifies it as a Buick exhaust
  recording, not music, so the "not heard" point is confounded.
- The operator played the Dyson v2 short on the phone speaker (29 Sep 2026) and heard its
  bed easily and clearly. The old engine recorded its voice-over-bed margin in the speech
  band as +25.9 dB, at about −10.4 dB bed-under-voice. That was a different measuring
  script, so it may not be the same yardstick.
- A 20 dB ceiling that refuses the one bed the operator knows works on the phone is
  suspect. A sub-bass-heavy bed has, by its profile, little energy in 250–4000 Hz, so the
  profile and the ceiling pull against each other.

How it is settled:

1. **Measured with today's code, by the operator.** Not run in 079 step 3: `.env` was
   parked first. It is the first thing in the next window with `.env` back, together
   with 086's re-run. Download Trap Hamza from its Mixkit page into `assets/audio/inbox/`. Fill its
   sidecar: `source: mixkit`, the page URL, and `slot: investigative_pulse`. Run the
   shortlist for that slot with `--voice` set to run04's voice stem. The log gives the
   margin with today's 069 code at `bed_db_under_voice` −14. Also note roughly where the
   Dyson level (−10.4) would put it: about 3.6 dB less margin, since the bed is louder.
2. **The operator's decision, recorded in this ticket** before the cap changes: keep 20,
   or move the ceiling to a value that admits the bed heard on the phone. The number and
   its evidence comment change together in the style front matter (numbers never in
   code), and the run04 confound is named in that comment.
3. **This afk run does not change the cap on its own.** If step 2 has no recorded
   decision when the run starts, the code in this ticket is built anyway (it needs no
   cap value). The done note says the first `facts_default` approval waits on the
   decision.

Never copied from `work/old-engine`: CLAUDE.md forbids depending on the earlier engine,
and a copied file would bypass the rights log. What the old engine gives this ticket is
its facts. The Trap Hamza file comes back through the drop folder like any other file.

## Acceptance criteria

- [ ] The default mood from hand-built cards: the largest runtime share wins. Long-form,
      `null` parts and cards 086 skips are excluded. A tie is broken by a stated rule
      (logged). On the committed 13 cards it names `investigative_pulse` (a test reads
      them). If 086's re-run changes that, the done note says so.
- [ ] The profile file loads, and a value off its stated range stops startup naming the
      key. The distance is tested on synthetic numpy signals: a sub-bass drone is nearer
      than a bright arpeggio, and a vocal file never ranks.
- [ ] Director tests with a fake library: flavour miss → same mood; mood miss →
      `facts_default` bed with its log line; no `facts_default` in the library → the
      Freesound fallback exactly as today. The facts default still goes through 069.
- [ ] The shortlist `facts_default` slot ranks by distance (recorded fixtures, no
      network). A yes writes the `facts_default` tag. The page shows distance and
      profile numbers (app test).
- [ ] 069's refusal and repair lines name the bed level.
- [ ] Tests never reach the network. Ruff, pyright and every test file are green in
      foreground chunks. The smoke passes T1–T13.

### Operator step, in the done note

The facts-default listening pass: the `facts_default` shortlist command with `--voice`,
Trap Hamza (in the drop folder) plus the ranked candidates, then yes/no on the page. It
comes after the cap decision above and before 079 step 4.

## Blocked by

- 086 (the card check decides which cards the default mood is learned from; the same
  afk run, 086 first).

## User stories addressed

- Operator, 29 Sep 2026 (079 HITL): "a facts short should take the kind of bed fact
  channels always use … learned from the references"; the facts-default bed as the
  fallback before any random search; reconciling it with 069's ceiling.
