# Reference inventory (v2)

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
    `said` (the gist of the words spoken over the shot, at most 12 words,
    in English), `shows` (what the picture literally depicts), `match` (how the picture
    relates to the words), `part`, the shot's `layout`, the `effect` on it (a component
    name, `unregistered`, or null) and the `sound` effect kind on it (or null).

## Shortsmith components (use these exact names in `component` and `effect`)

- `map`: a map with labelled markers
- `stamp`: a number or word slams in with a hit
- `text_pop`: a keyword pops in with an overshoot
- `unregistered`: none of the above draws it

Transitions: `cut`, `flash`, `whip`, or `unregistered`

## Vocabulary

- `layout`: `full_still`, `full_footage`, `card`, `split`, `grid`, `text_only`, `presenter_full`, `presenter_circle`, `map`, `chart`, `other`
- `background`: `still_photo`, `moving_footage`, `generated_or_animated`, `solid_or_gradient`, `blur`
- `footage_kind` (moving footage only, else null): `stock`, `archival_or_news`, `ai_generated`, `screen_recording`, `animation`
- `treatment` (any number, may be empty): `slow_motion`, `speed_ramp`, `zoom`, `colour_grade`, `overlay`
- `emphasis`: `word`, `number`, `image`, `speaker`
- sound `kind`: `whoosh`, `hit`, `riser`, `click`, `ding`, `other`
- sound `event`: `text_pop`, `sticker`, `bubble`, `flash`, `cut`, `stamp`, `reveal`, `other`
- sound `loudness`: `soft`, `medium`, `loud`
- motion `entrance`: `pop_overshoot`, `slide`, `fade`, `wipe`, `draw`, `scale`, `other`
- motion `region`: `top`, `middle`, `bottom`, `left`, `right`, `full`
- story `part`: `hook`, `build_up`, `reveal`, `ending`
- beat `match`: `literal`, `named_entity`, `number`, `illustrative`, `metaphor` (`literal`: the picture shows exactly what is said;
  `named_entity`: the person, place or thing named; `number`: the figure said;
  `illustrative`: a related picture; `metaphor`: an image standing for the idea)
- music change `how`: `crossfade`, `hard_cut`, `drop_to_silence`

### Music moods (`music_mood`)

- `tense_dramatic`: low strings or drones with a slow pulse, rising stakes; a conflict or a threat
- `investigative_pulse`: a steady muted rhythm that keeps moving; laying out evidence, step by step
- `mysterious_curiosity`: sparse plucks or pads with an open question in them; an unexplained fact
- `calm_ambient`: soft pads, no drums, nothing competing with the voice; reflection or an ending
- `eerie_scifi`: synth textures and deep space tones, unsettling but quiet; space or the future
- `upbeat_electronic`: bright synths over a light beat, optimistic; technology, progress, a win
- `energetic_beat`: a driving full beat with a clear groove; sport, speed, a countdown

### Regional flavours (`music_flavour`)

- `middle_east`: oud, ney or darbuka colour over the mood; the Gulf, Iran, the Levant
- `indian`: sitar, tabla, bansuri or tanpura colour over the mood; India and South Asia
- `east_asian`: guzheng, koto, erhu or pentatonic colour over the mood; China, Japan, Korea
- `european`: orchestral strings, accordion or harpsichord colour; Europe and its history

### Topics (`topic`)

- `history`: the past - empires, wars, rulers, ancient places and how things came to be
- `geopolitics`: countries and power now - borders, alliances, sanctions, oil, conflicts between states
- `science`: how nature works - space, physics, the body, animals, the planet
- `business`: money and companies - markets, brands, founders, prices, the economy
- `tech`: technology - AI, phones, the internet, software, gadgets and the firms that make them
- `society`: how people live - culture, religion, law, education, crime, social change
- `sport`: games and athletes - cricket, football, the Olympics, records
- `other`: anything the topics above do not cover

Use only the names in these lists. When nothing fits, pick the closest one.

## JSON schema (InventoryAnswerV2)

```json
{
  "$defs": {
    "Beat": {
      "additionalProperties": false,
      "description": "One shot: what was said over it (a gist, never a transcript) and what it shows.",
      "properties": {
        "start_s": {
          "title": "Start S",
          "type": "number"
        },
        "end_s": {
          "title": "End S",
          "type": "number"
        },
        "said": {
          "description": "a gist in English, at most 12 words",
          "title": "Said",
          "type": "string"
        },
        "shows": {
          "title": "Shows",
          "type": "string"
        },
        "match": {
          "enum": [
            "literal",
            "named_entity",
            "number",
            "illustrative",
            "metaphor"
          ],
          "title": "Match",
          "type": "string"
        },
        "part": {
          "enum": [
            "hook",
            "build_up",
            "reveal",
            "ending"
          ],
          "title": "Part",
          "type": "string"
        },
        "layout": {
          "enum": [
            "full_still",
            "full_footage",
            "card",
            "split",
            "grid",
            "text_only",
            "presenter_full",
            "presenter_circle",
            "map",
            "chart",
            "other"
          ],
          "title": "Layout",
          "type": "string"
        },
        "effect": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "a component name, `unregistered`, or null",
          "title": "Effect"
        },
        "sound": {
          "anyOf": [
            {
              "enum": [
                "whoosh",
                "hit",
                "riser",
                "click",
                "ding",
                "other"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Sound"
        }
      },
      "required": [
        "start_s",
        "end_s",
        "said",
        "shows",
        "match",
        "part",
        "layout",
        "effect",
        "sound"
      ],
      "title": "Beat",
      "type": "object"
    },
    "EffectV2": {
      "additionalProperties": false,
      "properties": {
        "at_s": {
          "title": "At S",
          "type": "number"
        },
        "duration_s": {
          "title": "Duration S",
          "type": "number"
        },
        "emphasis": {
          "enum": [
            "word",
            "number",
            "image",
            "speaker"
          ],
          "title": "Emphasis",
          "type": "string"
        },
        "name": {
          "title": "Name",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        },
        "component": {
          "title": "Component",
          "type": "string"
        },
        "motion": {
          "$ref": "#/$defs/Motion"
        }
      },
      "required": [
        "at_s",
        "duration_s",
        "emphasis",
        "name",
        "description",
        "component",
        "motion"
      ],
      "title": "EffectV2",
      "type": "object"
    },
    "Hook": {
      "additionalProperties": false,
      "properties": {
        "on_screen": {
          "title": "On Screen",
          "type": "string"
        },
        "heard": {
          "title": "Heard",
          "type": "string"
        }
      },
      "required": [
        "on_screen",
        "heard"
      ],
      "title": "Hook",
      "type": "object"
    },
    "Motion": {
      "additionalProperties": false,
      "description": "How an effect moves in: the data later effects are built from (083).",
      "properties": {
        "entrance": {
          "enum": [
            "pop_overshoot",
            "slide",
            "fade",
            "wipe",
            "draw",
            "scale",
            "other"
          ],
          "title": "Entrance",
          "type": "string"
        },
        "entrance_s": {
          "minimum": 0,
          "title": "Entrance S",
          "type": "number"
        },
        "size": {
          "description": "share of the frame width",
          "maximum": 1,
          "minimum": 0,
          "title": "Size",
          "type": "number"
        },
        "region": {
          "enum": [
            "top",
            "middle",
            "bottom",
            "left",
            "right",
            "full"
          ],
          "title": "Region",
          "type": "string"
        }
      },
      "required": [
        "entrance",
        "entrance_s",
        "size",
        "region"
      ],
      "title": "Motion",
      "type": "object"
    },
    "MusicChange": {
      "additionalProperties": false,
      "properties": {
        "at_s": {
          "title": "At S",
          "type": "number"
        },
        "from_part": {
          "enum": [
            "hook",
            "build_up",
            "reveal",
            "ending"
          ],
          "title": "From Part",
          "type": "string"
        },
        "to_part": {
          "enum": [
            "hook",
            "build_up",
            "reveal",
            "ending"
          ],
          "title": "To Part",
          "type": "string"
        },
        "how": {
          "enum": [
            "crossfade",
            "hard_cut",
            "drop_to_silence"
          ],
          "title": "How",
          "type": "string"
        }
      },
      "required": [
        "at_s",
        "from_part",
        "to_part",
        "how"
      ],
      "title": "MusicChange",
      "type": "object"
    },
    "Part": {
      "additionalProperties": false,
      "properties": {
        "part": {
          "enum": [
            "hook",
            "build_up",
            "reveal",
            "ending"
          ],
          "title": "Part",
          "type": "string"
        },
        "start_s": {
          "title": "Start S",
          "type": "number"
        },
        "end_s": {
          "title": "End S",
          "type": "number"
        },
        "music_mood": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "description": "one name from the mood list; null when no music plays in the part",
          "title": "Music Mood"
        },
        "music_flavour": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "one name from the flavours",
          "title": "Music Flavour"
        }
      },
      "required": [
        "part",
        "start_s",
        "end_s",
        "music_mood"
      ],
      "title": "Part",
      "type": "object"
    },
    "Script": {
      "additionalProperties": false,
      "properties": {
        "about": {
          "title": "About",
          "type": "string"
        },
        "topic": {
          "description": "one name from the topic list",
          "title": "Topic",
          "type": "string"
        },
        "tone": {
          "description": "one to three words",
          "title": "Tone",
          "type": "string"
        },
        "language": {
          "title": "Language",
          "type": "string"
        }
      },
      "required": [
        "about",
        "topic",
        "tone",
        "language"
      ],
      "title": "Script",
      "type": "object"
    },
    "Shot": {
      "additionalProperties": false,
      "properties": {
        "start_s": {
          "title": "Start S",
          "type": "number"
        },
        "end_s": {
          "title": "End S",
          "type": "number"
        },
        "layout": {
          "enum": [
            "full_still",
            "full_footage",
            "card",
            "split",
            "grid",
            "text_only",
            "presenter_full",
            "presenter_circle",
            "map",
            "chart",
            "other"
          ],
          "title": "Layout",
          "type": "string"
        },
        "background": {
          "enum": [
            "still_photo",
            "moving_footage",
            "generated_or_animated",
            "solid_or_gradient",
            "blur"
          ],
          "title": "Background",
          "type": "string"
        },
        "footage_kind": {
          "anyOf": [
            {
              "enum": [
                "stock",
                "archival_or_news",
                "ai_generated",
                "screen_recording",
                "animation"
              ],
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Footage Kind"
        },
        "clip_s": {
          "anyOf": [
            {
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Clip S"
        },
        "treatment": {
          "items": {
            "enum": [
              "slow_motion",
              "speed_ramp",
              "zoom",
              "colour_grade",
              "overlay"
            ],
            "type": "string"
          },
          "title": "Treatment",
          "type": "array"
        },
        "note": {
          "default": "",
          "title": "Note",
          "type": "string"
        }
      },
      "required": [
        "start_s",
        "end_s",
        "layout",
        "background"
      ],
      "title": "Shot",
      "type": "object"
    },
    "SoundEffectV2": {
      "additionalProperties": false,
      "properties": {
        "at_s": {
          "title": "At S",
          "type": "number"
        },
        "kind": {
          "enum": [
            "whoosh",
            "hit",
            "riser",
            "click",
            "ding",
            "other"
          ],
          "title": "Kind",
          "type": "string"
        },
        "synced_to": {
          "title": "Synced To",
          "type": "string"
        },
        "event": {
          "enum": [
            "text_pop",
            "sticker",
            "bubble",
            "flash",
            "cut",
            "stamp",
            "reveal",
            "other"
          ],
          "title": "Event",
          "type": "string"
        },
        "loudness": {
          "enum": [
            "soft",
            "medium",
            "loud"
          ],
          "title": "Loudness",
          "type": "string"
        },
        "length_s": {
          "minimum": 0,
          "title": "Length S",
          "type": "number"
        }
      },
      "required": [
        "at_s",
        "kind",
        "synced_to",
        "event",
        "loudness",
        "length_s"
      ],
      "title": "SoundEffectV2",
      "type": "object"
    },
    "SoundV2": {
      "additionalProperties": false,
      "properties": {
        "bed": {
          "title": "Bed",
          "type": "boolean"
        },
        "bed_mood": {
          "default": "",
          "title": "Bed Mood",
          "type": "string"
        },
        "effects": {
          "items": {
            "$ref": "#/$defs/SoundEffectV2"
          },
          "title": "Effects",
          "type": "array"
        }
      },
      "required": [
        "bed"
      ],
      "title": "SoundV2",
      "type": "object"
    },
    "TextLook": {
      "additionalProperties": false,
      "properties": {
        "caption_position": {
          "title": "Caption Position",
          "type": "string"
        },
        "caption_size": {
          "title": "Caption Size",
          "type": "string"
        },
        "caption_colours": {
          "title": "Caption Colours",
          "type": "string"
        },
        "active_word": {
          "title": "Active Word",
          "type": "string"
        },
        "title_entry": {
          "title": "Title Entry",
          "type": "string"
        },
        "number_entry": {
          "title": "Number Entry",
          "type": "string"
        }
      },
      "required": [
        "caption_position",
        "caption_size",
        "caption_colours",
        "active_word",
        "title_entry",
        "number_entry"
      ],
      "title": "TextLook",
      "type": "object"
    },
    "Transition": {
      "additionalProperties": false,
      "properties": {
        "at_s": {
          "title": "At S",
          "type": "number"
        },
        "duration_s": {
          "title": "Duration S",
          "type": "number"
        },
        "name": {
          "title": "Name",
          "type": "string"
        },
        "description": {
          "default": "",
          "title": "Description",
          "type": "string"
        },
        "component": {
          "title": "Component",
          "type": "string"
        }
      },
      "required": [
        "at_s",
        "duration_s",
        "name",
        "component"
      ],
      "title": "Transition",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "description": "The v2 answer: v1's lists with motion and sound-event detail, plus the script.",
  "properties": {
    "duration_s": {
      "exclusiveMinimum": 0,
      "title": "Duration S",
      "type": "number"
    },
    "shots": {
      "items": {
        "$ref": "#/$defs/Shot"
      },
      "title": "Shots",
      "type": "array"
    },
    "effects": {
      "items": {
        "$ref": "#/$defs/EffectV2"
      },
      "title": "Effects",
      "type": "array"
    },
    "transitions": {
      "items": {
        "$ref": "#/$defs/Transition"
      },
      "title": "Transitions",
      "type": "array"
    },
    "text": {
      "$ref": "#/$defs/TextLook"
    },
    "sound": {
      "$ref": "#/$defs/SoundV2"
    },
    "hook": {
      "$ref": "#/$defs/Hook"
    },
    "script": {
      "$ref": "#/$defs/Script"
    },
    "parts": {
      "items": {
        "$ref": "#/$defs/Part"
      },
      "title": "Parts",
      "type": "array"
    },
    "music_changes": {
      "items": {
        "$ref": "#/$defs/MusicChange"
      },
      "title": "Music Changes",
      "type": "array"
    },
    "beats": {
      "items": {
        "$ref": "#/$defs/Beat"
      },
      "title": "Beats",
      "type": "array"
    }
  },
  "required": [
    "duration_s",
    "shots",
    "effects",
    "transitions",
    "text",
    "sound",
    "hook",
    "script",
    "parts",
    "music_changes",
    "beats"
  ],
  "title": "InventoryAnswerV2",
  "type": "object"
}
```

Reply with JSON only: one object that matches the schema above, with no prose before
or after it.
