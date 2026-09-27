# Reference inventory ($prompt_version)

You are watching one YouTube Short for the Shortsmith team, who build an automatic
editor for 9:16 facts shorts. Write an inventory of the EDITING TECHNIQUES you see and
hear. We learn technique, never content: do not summarise the script, do not repeat
what the speaker says beyond what is needed to name what an effect emphasises.

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
   a wrong match is worse than a gap.
3. **Transitions.** Every change between shots that is not a plain cut, plus plain cuts
   as `cut`: when, how long, a snake_case `name`, one line, and `component` from the
   transition names below or `unregistered`.
4. **Text look.** How the captions sit (`caption_position`), their size relative to the
   frame (`caption_size`), their colours (`caption_colours`), what happens to the word
   being spoken (`active_word`), and how titles and numbers animate in (`title_entry`,
   `number_entry`). One line each.
5. **Sound.** Whether a music bed plays (`bed`) and its mood in a few words
   (`bed_mood`); every sound effect with its time, `kind` (`whoosh`, `hit`, `riser`,
   `click`, `ding`, `other`) and `synced_to`: the visual event it lands on.
6. **Hook.** The first three seconds: what is on screen (`on_screen`) and what is
   heard (`heard`), one line each.
7. `duration_s`: the length of the video.

## Shortsmith components (use these exact names in `component`)

$components

Transitions: $transitions

## Vocabulary

- `layout`: $layouts
- `background`: $backgrounds
- `footage_kind` (moving footage only, else null): $footage_kinds
- `treatment` (any number, may be empty): $treatments
- `emphasis`: $emphases
- sound `kind`: $sfx_kinds

## JSON schema (InventoryAnswer)

```json
$schema
```

Reply with JSON only: one object that matches the schema above, with no prose before
or after it.
