# Reference inventory ($prompt_version)

You are watching one YouTube Short for the Shortsmith team, who build an automatic
editor for 9:16 facts shorts. Write an inventory of the EDITING TECHNIQUES you see and
hear, and of how the picture and the music follow the script. We learn technique, never
content: never write out what the speaker says. Where a field asks what was said, give a
short gist in your own English words, even when the short is in Hindi.

Watch the whole video at the frame rate you were given. Timestamps are seconds from the
first frame, to one decimal. Every timestamp and duration you give is an estimate from
the frames you saw; that is understood, so do not hedge in prose, just give the number.

## What to inventory

1. **Shots.** Every visually distinct shot from the first frame to the last, in order,
   contiguous (each `start_s` is the previous `end_s`). For each: `layout`, what is
   behind it (`background`), and for moving footage its `footage_kind`, how long the
   clip itself runs (`clip_s`) and its `treatment` list. A short one-line `note` says
   what is on screen.
2. **Effects.** Every visual effect or animation: when it starts, how long it runs,
   what it emphasises (`word`, `number`, `image`, `speaker`), a short snake_case `name`
   you would give it (the same name every time you see the same technique), one line of
   `description`, and `component`: the Shortsmith component from the list below that
   draws it, or `unregistered` when none of them does. When in doubt say `unregistered`;
   a wrong match is worse than a gap. Each effect also has a `motion`: how it enters
   (`entrance`), how long the entrance takes (`entrance_s`), its size as a share of the
   frame width (`size`, 0 to 1) and where it sits (`region`).
3. **Transitions.** Every change between shots that is not a plain cut, plus plain cuts
   as `cut`: when, how long, a snake_case `name`, one line, and `component` from the
   transition names below or `unregistered`.
4. **Text look.** How the captions sit (`caption_position`), their size relative to the
   frame (`caption_size`), their colours (`caption_colours`), what happens to the word
   being spoken (`active_word`), and how titles and numbers animate in (`title_entry`,
   `number_entry`). One line each.
5. **Sound.** Whether a music bed plays (`bed`) and its mood in a few words
   (`bed_mood`); every sound effect with its time, `kind`, `synced_to` (the visual event
   it lands on, in a few words), `event` (that event in our terms), `loudness` against
   the voice and `length_s`.
6. **Hook.** The first three seconds: what is on screen (`on_screen`) and what is
   heard (`heard`), one line each.
7. `duration_s`: the length of the video.
8. **Script.** What the short is about in one sentence (`about`), its `topic` from the
   topic list, its `tone` in one to three words, and its `language` (`hi`, `en`, ...).
9. **Story parts.** The short split into its parts in order (`hook`, `build_up`,
   `reveal`, `ending`; a part may be missing, none repeats), each with `start_s`,
   `end_s`, the `music_mood` playing under it from the mood list (null when no music
   plays) and, when the music carries a regional colour, `music_flavour` from the
   flavour list.
10. **Music changes.** Every point where the bed changes: `at_s`, the part it leaves
    (`from_part`), the part it enters (`to_part`) and `how` it changes. An empty list
    means one bed throughout.
11. **Beats.** One row per shot, the same shots as in 1, in order: `start_s`, `end_s`,
    `said` (the gist of the words spoken over the shot, at most $said_words_max words,
    in English), `shows` (what the picture literally depicts), `match` (how the picture
    relates to the words), `part`, the shot's `layout`, the `effect` on it (a component
    name, `unregistered`, or null) and the `sound` effect kind on it (or null).

## Shortsmith components (use these exact names in `component` and `effect`)

$components

Transitions: $transitions

## Vocabulary

- `layout`: $layouts
- `background`: $backgrounds
- `footage_kind` (moving footage only, else null): $footage_kinds
- `treatment` (any number, may be empty): $treatments
- `emphasis`: $emphases
- sound `kind`: $sfx_kinds
- sound `event`: $events
- sound `loudness`: $loudnesses
- motion `entrance`: $entrances
- motion `region`: $regions
- story `part`: $parts
- beat `match`: $matches (`literal`: the picture shows exactly what is said;
  `named_entity`: the person, place or thing named; `number`: the figure said;
  `illustrative`: a related picture; `metaphor`: an image standing for the idea)
- music change `how`: $hows

### Music moods (`music_mood`)

$moods

### Regional flavours (`music_flavour`)

$flavours

### Topics (`topic`)

$topics

Use only the names in these lists. When nothing fits, pick the closest one.

## JSON schema (InventoryAnswerV2)

```json
$schema
```

Reply with JSON only: one object that matches the schema above, with no prose before
or after it.
