# 086 — A reference card's music changes must match its story parts, boundary by boundary

## Type

AFK — no network, no keys. Blocks step 4 of 079 (the King Saud re-render).

## Parent PRD

`issues/prd.md`

## Why

Found in 079 step 2 (operator's reviewer, 29 Sep 2026, confirmed by the operator by ear):
two of the three Tier B vishva cards contradict themselves.

- `FbaBcWgMIEY`: flavour middle_east → european → indian across its parts;
  `music_changes` is empty.
- `ePTZVwipoAM`: mood tense_dramatic → investigative_pulse → mysterious_curiosity →
  tense_dramatic; `music_changes` is empty.

`reference/music.py` `pairing()` prints "no change" for both. A vishva history job
(079's King Saud re-render) learns "one bed, never change" from the wrong half of the
card.

## What to build

One pure check, used in two places.

- **The check (per boundary, not "non-empty").** For every neighbouring pair of parts
  (in order) whose `music_mood` or `music_flavour` differs, including music starting or
  stopping (`null` against a mood), `music_changes` holds a change with
  `from_part` = the earlier part and `to_part` = the later one. A card with three
  differing boundaries and one change fails and names the two uncovered boundaries.
  A change at a boundary where nothing differs is allowed (a bed can change inside
  one mood); the check only goes one way.
- **At write time (`reference inventory`).** A failed check is an invalid answer like
  a closed-list miss: it takes 073's one retry, with the uncovered boundaries named in
  the retry reasons. A second failure writes no card (073's rule, unchanged). The log
  names the video and the boundaries, so the operator re-runs that one link.
- **At read time (`v2_cards`, so every reader).** A stored v2 card that fails the check
  is skipped with a log line
  `<id>: music_changes misses <from> -> <to>; skipped`, the same way a v1 card is
  skipped. A stale, contradictory card never teaches a job, and it never crashes one.
  `pairing()` and the worked examples (077) see only cards that pass.
- **The prompt, as a new version.** Every text change bumps the version, as the planner
  prompts do (`picture_v19`): write `prompts/inventory_v3.md` and leave `inventory_v2.md`
  unchanged, as v1 was left. v3's `music_changes` paragraph says it in the model's
  terms: one entry per boundary where the part's mood or flavour differs. v3 is the
  default for `--prompt`; `--prompt v2` stays possible. Cards made with it carry
  `"prompt_version": "v3"`, so every card says which instruction made it. The schema
  does not change: the v2 model reads v3 cards, and every v2-field reader (`v2_cards`,
  `pairing`, `gaps`, 077's worked examples) takes v2 and v3 cards alike. A mix (11 v2
  cards + 2 v3) is normal. **Trap:** `reference/__init__.py` picks the model with
  `== "v2"` (the loader near line 434, the answer model near line 582, the vocabulary near
  line 834, `PromptVersion = Literal["v1", "v2"]` at 62). Left alone, a v3 card would be
  read as a v1 card and silently lose every v2 field. Replace the equality checks with
  "uses the v2 schema" (v2 or v3), with a test that loads a v3 card as
  `ReferenceInventoryV2`. Two more places write or expect the literal (operator,
  29 Sep 2026):
  - **line 418 writes** `"prompt_version": "v2"` into every new v2-schema card, whatever
    prompt made it. Left alone, a v3 card is saved labelled v2, so the version never says
    which instruction made it. Write the version actually used.
  - **`smoke.py:1543` expects** `"v2"` on the self-inventory card (074, `reference/own.py`).
    Own jobs will make v3 cards after the bump, so it expects `PROMPT_VERSION`.

  The full sweep at the time of writing: `rg '"v2"|PROMPT_VERSION' src tests` finds the
  above plus 5 matches in `tests/test_reference_v2.py` (2), `tests/test_self_inventory.py`
  (2) and `tests/test_worked_examples.py` (1). A test pinning the v2 prompt's own text or
  snapshot keeps `"v2"`. A test about "the current card" follows `PROMPT_VERSION`. Re-run
  the sweep before closing, and name any match left on purpose in the done note. New snapshot `inventory_v3.snapshot.md`; the v2 snapshot
  stays pinned.
- **The retry reasons.** A boundary miss is fixed by adding the change, never by
  editing the parts: the retry text says "keep `parts` as they are; add the missing
  `music_changes` entry". The code cannot tell a flattened retry from an honest
  correction (it has no ground truth), so that judgement is the operator's (below).

No number is needed: the check matches part names, not times.

## Acceptance criteria

- [ ] Unit tests on hand-built cards: no boundary differs + empty list passes; one
      differing flavour boundary + empty list fails naming it; three differing mood
      boundaries + one change fails naming the other two; `null` → mood counts as a
      difference; an extra change where nothing differs passes.
- [ ] The two committed cards `FbaBcWgMIEY` and `ePTZVwipoAM` fail the check (a test
      reads them from `docs/reference/inventory/`); the other 11 pass. If another card
      fails, that is logged in the done note, not hidden.
- [ ] `FakeAnalyser` test: a first answer that fails the check triggers one retry whose
      prompt names the boundary; a second failing answer writes no card.
- [ ] `v2_cards` skips a failing card with the log line above; `pairing()` never sees it.
- [ ] `inventory_v3.md` exists with its snapshot; `inventory_v2.md` and its snapshot are
      byte-for-byte unchanged. A card written with the default prompt carries
      `prompt_version: "v3"`; a v3 card and a v2 card load side by side and both reach
      `pairing()`. The retry text for a boundary miss says to keep `parts`.
- [ ] Tests never reach the network. Ruff, pyright and every test file green in
      foreground chunks; the smoke passes T1–T13.

### Operator step, in the done note (with `.env` back)

The exact two re-run commands (`uv run python -m shortsmith.reference inventory <url>
--style vishva` for each link, using the style/topic flags each card was made with) and
`uv run python -m shortsmith.reference gaps`, then a one-line read-only command that
prints each re-run card's `prompt_version`, its parts (mood, flavour) and its
`music_changes`.

The operator's check after the re-run: the operator has confirmed by ear that the music
changes in both shorts, so **each of the two cards has at least one music change**, and
the parts still differ where the music does. A card that passes the check by flattening
its parts to one mood and one flavour is still wrong. It counts as a failed re-run, the
same as a link that fails twice and writes no card. For either: record in 079 how many
vishva cards the King Saud job learns from, and the operator decides whether 079 step 4
goes ahead with fewer, or the link is re-run once more.

## Blocked by

- Nothing.

## User stories addressed

- Operator, 29 Sep 2026 (079 HITL): "handle the card finding the Matt way before
  step 4"; per-boundary check and the second-failure rule settled in that session.
