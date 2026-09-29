# 092 — An off-list label on a reference card lands as "other" with a log line instead of failing the card

## Type

AFK — no network in tests, no new packages. The operator re-runs the link afterwards.

## Parent PRD

`issues/prd.md`

## Why

Operator, 30 Sep 2026 (079 HITL, the 086 re-run of `FbaBcWgMIEY`): 3 of 4 answers failed
on closed-list misses, not on 086's check. The misses were `sound.effects.N.kind` and
`beats.N.sound` outside `whoosh/hit/riser/click/ding/other`. The other failures were one
broken-JSON reply and one "said is 13 words". One off-list label kills the whole card, and
every inventory run pays for the call again.

The list already has an `other` word for exactly this case. A label the model invents
("swoosh", "boom") is information about a sound, not a broken answer.

## What to build

- **Coerce, don't fail.** In `reference.parse_answer`, a string that is not on a closed list
  that **already contains `other`** is stored as `other`. Today those lists are `SfxKind`
  (both fields above), `SfxEvent`, `Entrance` and `Layout`; the rule follows the list, so no
  names are hard-coded. Lists without `other` (`Match`, `Loudness`, `Region`, …) stay strict,
  and so do the vocab moods, flavours and topics (they already have their own rule).
- **One log line each:** `<video>: sound.effects.3.kind 'swoosh' is not on the list; stored as other`.
- **Kept as evidence.** The card gets an optional `off_list` list of `{field, said}` rows
  (empty by default, so older cards load unchanged and every v2 reader is untouched). `gaps`
  prints the off-list words across all cards with their counts. That is the evidence 083
  would use to grow a list, which stays an operator decision.
- **What stays strict:** a wrong type (a number or object where a word belongs, or `null`
  where the schema does not allow it), broken JSON, and `said` over `SAID_WORDS_MAX`. A
  gist cut short mid-sentence is worse than the retry, so those keep the one retry as
  today.
- The prompt is unchanged (v3 stays the version), so cards stay comparable with the
  committed ones.

## Acceptance criteria

- [ ] Fake analyser, one answer with an off-list `sound.effects.N.kind` and an off-list
      `beats.N.sound`: the card is written on the **first** attempt (no retry), both fields
      read `other`, `off_list` has both rows, and both log lines appear.
- [ ] An off-list word on a list without `other` still fails and retries as today.
- [ ] Broken JSON and a 13-word `said` still take the retry.
- [ ] Every committed card (v1 fixtures and v2) still loads, and `v2_cards` is unchanged
      for them.
- [ ] `gaps` lists off-list words with counts (test over hand-built cards).
- [ ] Tests never reach the network. Ruff, pyright and every test file are green in
      foreground chunks. The smoke passes T1–T13.

### Operator step, in the done note

Re-run `FbaBcWgMIEY` (and `ePTZVwipoAM` if it failed the same way), then `gaps`, as in
079's agreed order.

## Done (afk, 30 Sep 2026)

All acceptance boxes are met.
- `reference.parse_reply` returns `Parsed(answer, off_list)`. Before the schema check it
  walks the answer model's own field annotations (nested models, lists, `X | None`). A
  string off any `Literal` that holds `other` is replaced with `other` and recorded as
  `{field, said}`. The rule follows the list: today that covers `SfxKind` (in
  `sound.effects.N.kind` and `beats.N.sound`), `SfxEvent`, `Entrance` and `Layout` (in
  `shots.N.layout` and `beats.N.layout`). No names are hard-coded. `parse_answer` keeps
  its signature and returns `.answer`.
- `inventory` logs `<video>: <field> '<said>' is not on the list; stored as other` once
  per word and passes the rows to `from_answer(off_list=...)`.
- `ReferenceInventory.off_list` (and v2) defaults to empty with `exclude_if` empty. A
  clean card's JSON has no `off_list` key, so every committed v1 and v2 card loads and
  dumps unchanged. The field is on the card, not the answer, so the prompt's generated
  schema is unchanged (the v2 snapshot test pins it).
- `gaps` gets an "Off-list labels" section (field with row numbers as `N`, word
  lower-cased and stripped, times, references), ranked by count. It appears only when
  some card has an off-list word, so the committed `GAPS.md` stays unchanged.
- Still strict, with the one retry: `Match`, `Loudness`, `Region`, `StoryPart`,
  `MusicHow`, the vocab moods, flavours and topics, a number or `null` where a word
  belongs, broken JSON, and `said` over 12 words.
- `tests/test_reference_v2.py`: the case with an unknown `sound.effects.2.event` was
  expected to be invalid. `SfxEvent` holds `other`, so 092 now coerces it on purpose. The
  row now uses `loudness`, which stays strict.

Loops: ruff and pyright are clean. All 75 test files are green in 9 foreground chunks.
The smoke delivered with T1–T13 passing.

**Operator step:** re-run `FbaBcWgMIEY` (and `ePTZVwipoAM` if it failed the same way),
then `gaps`, as in 079's agreed order.

## Blocked by

None - can start immediately.

## User stories addressed

- Operator, 30 Sep 2026: "One off-list label kills the whole card, and every inventory run
  keeps paying for it."
