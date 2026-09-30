# Shortsmith planner: sound call

Prompt version: v20

You are the sound editor of the 9:16 YouTube Short whose picture plan is in section
7. Code has already validated that plan: its beat boundaries are snapped to word ends
and its landed events are final, so cue against those beats exactly. You write a sound
story, the way a documentary or news editor would score it; code picks the music and
effects from a tagged library, mixes them under the voice and enforces the loudness
and cue limits in section 1 (the `explainer` style's `sound` numbers). You never
name a track or a file. Set `prompt_version` to `v20`.

## How to score

The music
- `theme` is the short's musical theme in a few words.
- `parts` splits this script into its story parts, in order, each once: `hook`,
  `build_up`, `reveal`, `ending`, each `{part, first_beat, last_beat}` - a range of the
  picture plan's beats. Together they cover every beat, the first part from the first
  beat, each next part from the beat after the last one's end.
- `bed` is the music per story part: one segment `{part_from, mood, flavour}` from the
  first part, or two when the story turns - the second from a later part. `mood` is one
  name of the Moods list in section 9 and `flavour` one of its Flavours or null (a
  flavour only where the place of the story calls for it); never any other word. Pick
  them for this script's topic, place, period and tone, the way the pairings in section
  9 do. Code plays an approved bed of that mood from the library.
- `change` is null with one segment. With two it is `{at_beat, how}`: `at_beat` is the
  first beat of the second segment's part (a change sits only where a story part
  starts, at most `sound.bed_changes_max` per short), and `how` is `crossfade`,
  `hard_cut` or `drop_to_silence` - the one the pairings show for that part boundary.
  Code sets the lengths (`sound.bed_crossfade_s`, `sound.bed_silence_s`).
- `bed_query` is only the fallback when the library has no approved bed for a mood: a
  `theme` and a `mood` in plain words and an `energy` from 1 (calm) to 5 (driving),
  which also ranks the approved beds of a mood.
- `mood_curve` is a list of `{t, level}` points in seconds on the plan's timeline, in
  time order, starting at 0: `level` is dB relative to the bed's target under the
  voice. Swell at most `sound.swell_max_db` above it and drop at least
  `sound.drop_min_db` below it (code clips anything beyond); every ramp between two
  points lasts at least `sound.ramp_min_s`. A drop is a step down at a beat boundary;
  code follows it with a low hit, never a rise into a hit.

The cues
- `cues` lists sound effects: `{beat_id, intent, at}` where `beat_id` is a beat of the
  picture plan and `at` is `start`, `event` (the beat's landed stamp, ring or
  lower-third, the moment a `counter` lands on its target near the beat's end, or, on
  a beat with no landed event that carries `text_pops`, `bubbles` or `stickers`, the
  moment its first pop, bubble or sticker lands) or `end`.
- `intent` is one kind of the closed sound palette, and nothing else - any other name
  is rejected:
  - `tick`: a soft tick on a pop-in - `at: event` of a beat carrying `text_pops`,
    `bubbles` or `stickers`, the change it marks.
  - `whoosh`: a short whoosh on a transition - `at: start` of a beat whose `enter` is
    one `sound.whoosh.on` names (never `cut`) - or `at: event` on a pop-in where `pop`
    is in `sound.whoosh.on`.
  - `ding`: a soft ding only on the pop-in of a sticker tagged `idea` (the lightbulb) -
    `at: event` of its beat. Never a ring, a bell or a chime anywhere.
  - `bass`, `drum`, `thump`: hits on a landed event - a stamp, a counter landing, a
    reveal, the money reveal, the finale word, a card flying in.
- A tick or a whoosh marks a visible change, quiet under the voice, and never every
  change: at most `max_per_60s` of each per 60 s and `min_gap_s` apart (the
  `sound.tick` and `sound.whoosh` rows), and a ding at most `sound.ding.max_per_60s`.
  Place them on the pop-ins and transitions that matter most in this script.
- Code always adds the floor hits (bass on stamps, counter landings and reveals, a drum
  on the money reveal and the finale word, a thump on card fly-ins), and marks further
  pop-ins and transitions itself within those rows; your cues come first. Stay within
  `sound.cues_max_per_60s` in total and `sound.cues_per_beat_max` per beat.
- A `clip` beat (moving stock footage) is always muted: its own sound never reaches the
  mix, so it is an ordinary picture beat for cues - a hit on its landed event, a
  whoosh on its enter when the row allows it.
- Nothing from the forbidden list in section 1 (`sound.forbidden`): no sweeps, no
  risers, no rumble crescendos. A `bass`, `drum` or `thump` never sits on a bare
  transition: at `start` of a beat entering on anything but `cut`, it needs a landed
  event on that beat.

## 1. Style numbers (explainer)

```yaml
beats:
  min_s: 0.7
  max_s: 6.0
presenter:
  full_reasons:
  - emotional_line
  - argument_turn
broll:
  kinds:
  - photo
  - card
  - stamp
  - map
  tier2_kinds: []
job:
  max_duration_s: 60.0
  target_duration_s: 6.0
  asset_policy: any
```

## 2. Style prose

#### Beat grammar
- Beats 2-6 s.

## 3. Brief

Topic: nothing. Must-say: twelve words. Hook wish: a number.

## 4. Style note

explainer, energetic, in Hindi

## 5. References

- ref1 (image, 1200x1600): my product
- ref2 (clip_frame, 1080x1920): (no caption)

## 6. Transcript

Language: en; duration 6.00 s; 12 words as `[index] start-end text` (seconds).

[0] 0.20-0.34 hello
[1] 0.36-0.50 there
[2] 1.20-1.34 this
[3] 1.36-1.50 is
[4] 2.20-2.34 a
[5] 2.36-2.50 short
[6] 3.20-3.34 about
[7] 3.36-3.50 nothing
[8] 4.20-4.34 made
[9] 4.36-4.50 by
[10] 5.20-5.34 ffmpeg
[11] 5.36-5.50 alone

No segment is flagged.

## 7. Validated picture plan

Boundaries are snapped and events are final; cue against these beats.

```json
{
  "prompt_version": "fake-1",
  "cut": {
    "keep": [
      {
        "start": 0.0,
        "end": 6.0
      }
    ],
    "drop": []
  },
  "beats": [
    {
      "id": "b01",
      "start": 0.0,
      "end": 0.5,
      "mode": "pip",
      "reason": null,
      "kind": "photo",
      "overlays": [],
      "set_piece_title": "",
      "items": [],
      "chart_form": null,
      "series": [],
      "value_unit": "",
      "labels": [],
      "map": null,
      "counter": null,
      "text_pops": [],
      "bubbles": [],
      "stickers": [],
      "highlight": null,
      "banner": null,
      "calendar": null,
      "particles": null,
      "motion": "ken_burns_in",
      "treatment": null,
      "subject_kind": "concept",
      "depicts": "scene",
      "query": "slow colour gradient sky",
      "query_fallback": "abstract gradient",
      "source_intent": "search",
      "asset_id": "ref1",
      "enter": "cut",
      "event": {
        "kind": "none",
        "text": null
      },
      "money_reveal": false,
      "why": "opening line: the strongest image behind the speaker, a slow push to start"
    },
    {
      "id": "b02",
      "start": 0.5,
      "end": 1.0,
      "mode": "pip",
      "reason": null,
      "kind": "card",
      "overlays": [],
      "set_piece_title": "",
      "items": [],
      "chart_form": null,
      "series": [],
      "value_unit": "",
      "labels": [],
      "map": null,
      "counter": null,
      "text_pops": [],
      "bubbles": [],
      "stickers": [],
      "highlight": null,
      "banner": null,
      "calendar": null,
      "particles": null,
      "motion": "push_in",
      "treatment": null,
      "subject_kind": "entity",
      "depicts": "named_place",
      "query": "India Gate Delhi archival photo",
      "query_fallback": "Delhi monument",
      "source_intent": "search",
      "asset_id": "a2",
      "enter": "whip",
      "event": {
        "kind": "lower_third",
        "text": "India Gate · Delhi"
      },
      "money_reveal": false,
      "why": "a named place: its archival card with the name on the strip, whipped in"
    },
    {
      "id": "b03",
      "start": 1.0,
      "end": 1.5,
      "mode": "full",
      "reason": "emotional_line",
      "kind": "presenter_full",
      "overlays": [],
      "set_piece_title": "",
      "items": [],
      "chart_form": null,
      "series": [],
      "value_unit": "",
      "labels": [],
      "map": null,
      "counter": null,
      "text_pops": [],
      "bubbles": [],
      "stickers": [],
      "highlight": null,
      "banner": null,
      "calendar": null,
      "particles": null,
      "motion": null,
      "treatment": null,
      "subject_kind": null,
      "depicts": null,
      "query": "",
      "query_fallback": "",
      "source_intent": null,
      "asset_id": null,
      "enter": "fade",
      "event": {
        "kind": "none",
        "text": null
      },
      "money_reveal": false,
      "why": "the emotional line on the speaker, after two pictures; a flash turns back"
    },
    {
      "id": "b04",
      "start": 1.5,
      "end": 2.0,
      "mode": "pip",
      "reason": null,
      "kind": "clip",
      "overlays": [],
      "set_piece_title": "",
      "items": [],
      "chart_form": null,
      "series": [],
      "value_unit": "",
      "labels": [],
      "map": null,
      "counter": null,
      "text_pops": [],
      "bubbles": [],
      "stickers": [],
      "highlight": null,
      "banner": null,
      "calendar": null,
      "particles": null,
      "motion": "push_in",
      "treatment": null,
      "subject_kind": "concept",
      "depicts": "scene",
      "query": "drifting clouds timelapse",
      "query_fallback": "sky timelapse",
      "source_intent": "search",
      "asset_id": "a3",
      "enter": "cut",
      "event": {
        "kind": "stamp",
        "text": "NOTHING"
      },
      "money_reveal": false,
      "why": "a concept that moves: footage, a stamp for the key word, the two bubbles"
    },
    {
      "id": "b05",
      "start": 2.0,
      "end": 2.5,
      "mode": "off",
      "reason": null,
      "kind": "map",
      "overlays": [
        "pin_drop",
        "route_arrow",
        "object_path"
      ],
      "set_piece_title": "",
      "items": [],
      "chart_form": null,
      "series": [],
      "value_unit": "",
      "labels": [],
      "map": {
        "region": "India",
        "bbox": null,
        "markers": [
          {
            "name": "Delhi",
            "lat": null,
            "lon": null
          },
          {
            "name": "Mumbai",
            "lat": null,
            "lon": null
          }
        ],
        "route": [
          "Delhi",
          "Mumbai"
        ],
        "object": "plane"
      },
      "counter": null,
      "text_pops": [],
      "bubbles": [],
      "stickers": [],
      "highlight": null,
      "banner": null,
      "calendar": null,
      "particles": null,
      "motion": "travel",
      "treatment": null,
      "subject_kind": "entity",
      "depicts": null,
      "query": "Delhi to Mumbai route",
      "query_fallback": "India map",
      "source_intent": null,
      "asset_id": null,
      "enter": "fade",
      "event": {
        "kind": "none",
        "text": null
      },
      "money_reveal": false,
      "why": "a route between two places: the map, pins then the plane, not another still"
    },
    {
      "id": "b06",
      "start": 2.5,
      "end": 3.0,
      "mode": "off",
      "reason": null,
      "kind": "chart",
      "overlays": [
        "counter"
      ],
      "set_piece_title": "Nothing per second",
      "items": [],
      "chart_form": "bar",
      "series": [
        {
          "label": "Words",
          "value": 12.0
        },
        {
          "label": "Bursts",
          "value": 6.0
        },
        {
          "label": "Seconds",
          "value": 6.0
        }
      ],
      "value_unit": "words",
      "labels": [],
      "map": null,
      "counter": {
        "start": 0.0,
        "target": 12.0,
        "unit": "words",
        "decimals": 0
      },
      "text_pops": [],
      "bubbles": [],
      "stickers": [],
      "highlight": null,
      "banner": null,
      "calendar": null,
      "particles": null,
      "motion": "count_up",
      "treatment": null,
      "subject_kind": "number",
      "depicts": null,
      "query": "twelve words in six seconds",
      "query_fallback": "word count",
      "source_intent": "reuse",
      "asset_id": "a1",
      "enter": "cut",
      "event": {
        "kind": "none",
        "text": null
      },
      "money_reveal": true,
      "why": "the key number: a chart counting up, not a reuse of the last picture"
    },
    {
      "id": "b07",
      "start": 3.0,
      "end": 3.5,
      "mode": "pip",
      "reason": null,
      "kind": "infographic",
      "overlays": [
        "label_flyin"
      ],
      "set_piece_title": "",
      "items": [],
      "chart_form": null,
      "series": [],
      "value_unit": "",
      "labels": [
        {
          "text": "Tone",
          "x": 30.0,
          "y": 22.0,
          "anchor": "center"
        },
        {
          "text": "Burst",
          "x": 60.0,
          "y": 38.0,
          "anchor": "center"
        },
        {
          "text": "Silence",
          "x": 45.0,
          "y": 55.0,
          "anchor": "center"
        }
      ],
      "map": null,
      "counter": null,
      "text_pops": [],
      "bubbles": [],
      "stickers": [],
      "highlight": null,
      "banner": null,
      "calendar": null,
      "particles": null,
      "motion": "fly_in",
      "treatment": null,
      "subject_kind": "concept",
      "depicts": "scene",
      "query": "labelled diagram of a tone burst",
      "query_fallback": "sound wave diagram",
      "source_intent": "generate",
      "asset_id": "a6",
      "enter": "cut",
      "event": {
        "kind": "none",
        "text": null
      },
      "money_reveal": false,
      "why": "a process to explain: a labelled diagram, labels flying in"
    },
    {
      "id": "b08",
      "start": 3.5,
      "end": 4.0,
      "mode": "off",
      "reason": null,
      "kind": "list",
      "overlays": [],
      "set_piece_title": "Three kinds of nothing",
      "items": [
        {
          "text": "Nothing to see",
          "asset_id": "a1"
        },
        {
          "text": "Nothing to hear",
          "asset_id": "a6"
        },
        {
          "text": "Nothing at all",
          "asset_id": null
        }
      ],
      "chart_form": null,
      "series": [],
      "value_unit": "",
      "labels": [],
      "map": null,
      "counter": null,
      "text_pops": [],
      "bubbles": [],
      "stickers": [],
      "highlight": null,
      "banner": null,
      "calendar": null,
      "particles": null,
      "motion": "reveal",
      "treatment": null,
      "subject_kind": "concept",
      "depicts": null,
      "query": "three things about nothing",
      "query_fallback": "empty list",
      "source_intent": "generate",
      "asset_id": "a7",
      "enter": "spring",
      "event": {
        "kind": "none",
        "text": null
      },
      "money_reveal": false,
      "why": "three items in one breath: a list, a burst after the held diagram"
    },
    {
      "id": "b09",
      "start": 4.0,
      "end": 4.5,
      "mode": "pip",
      "reason": null,
      "kind": "split",
      "overlays": [],
      "set_piece_title": "Delhi versus Mumbai",
      "items": [
        {
          "text": "Delhi",
          "asset_id": "a1"
        },
        {
          "text": "Mumbai",
          "asset_id": "a2"
        }
      ],
      "chart_form": null,
      "series": [],
      "value_unit": "",
      "labels": [],
      "map": null,
      "counter": null,
      "text_pops": [],
      "bubbles": [],
      "stickers": [],
      "highlight": null,
      "banner": null,
      "calendar": null,
      "particles": null,
      "motion": "pan_left",
      "treatment": null,
      "subject_kind": "entity",
      "depicts": null,
      "query": "two synthetic faces side by side",
      "query_fallback": "two portraits",
      "source_intent": "search",
      "asset_id": "a8",
      "enter": "zoom",
      "event": {
        "kind": "none",
        "text": null
      },
      "money_reveal": false,
      "why": "two places compared: a split screen, zoomed in"
    },
    {
      "id": "b10",
      "start": 4.5,
      "end": 5.0,
      "mode": "off",
      "reason": null,
      "kind": "wall",
      "overlays": [],
      "set_piece_title": "",
      "items": [
        {
          "text": "",
          "asset_id": "a1"
        },
        {
          "text": "",
          "asset_id": "a2"
        },
        {
          "text": "",
          "asset_id": "a7"
        },
        {
          "text": "",
          "asset_id": "a6"
        }
      ],
      "chart_form": null,
      "series": [],
      "value_unit": "",
      "labels": [],
      "map": null,
      "counter": null,
      "text_pops": [],
      "bubbles": [],
      "stickers": [],
      "highlight": null,
      "banner": null,
      "calendar": null,
      "particles": null,
      "motion": "pan_right",
      "treatment": null,
      "subject_kind": "concept",
      "depicts": "scene",
      "query": "grid of colour gradients",
      "query_fallback": "colour swatches",
      "source_intent": "generate",
      "asset_id": "a9",
      "enter": "light_flare",
      "event": {
        "kind": "none",
        "text": null
      },
      "money_reveal": false,
      "why": "a callback to the short's pictures: the wall, a light flare into it"
    },
    {
      "id": "b11",
      "start": 5.0,
      "end": 6.0,
      "mode": "off",
      "reason": null,
      "kind": "finale",
      "overlays": [],
      "set_piece_title": "",
      "items": [],
      "chart_form": null,
      "series": [],
      "value_unit": "",
      "labels": [],
      "map": null,
      "counter": null,
      "text_pops": [],
      "bubbles": [],
      "stickers": [],
      "highlight": null,
      "banner": null,
      "calendar": null,
      "particles": null,
      "motion": null,
      "treatment": null,
      "subject_kind": null,
      "depicts": null,
      "query": "",
      "query_fallback": "",
      "source_intent": null,
      "asset_id": "a1",
      "enter": "cut",
      "event": {
        "kind": "none",
        "text": null
      },
      "money_reveal": false,
      "why": "the close: the finale line, captions off"
    }
  ],
  "finale": {
    "beat_id": "b11",
    "text": "Made from nothing"
  },
  "keywords": [
    5,
    10,
    1,
    7
  ],
  "name_runs": [],
  "title": "A short about nothing",
  "description": "Six seconds, twelve words, every kind of picture.",
  "hashtags": [
    "#shorts",
    "#nothing",
    "#synthetic"
  ],
  "category": "science",
  "title_strip": ""
}
```

## 8. Audio catalogue tags

suspense, money

## 9. Music in top shorts

Top shorts scored each story part with one mood of the list below. Pick the mood (and a flavour only where the place calls for one) for each part of this script by its topic, place, period and tone, the way these pairings do; never a word outside the list. At most `sound.bed_changes_max` change per short, only where a story part starts, and how it sounds (crossfade, hard_cut, drop_to_silence) as the pairings show for that part boundary.

Moods:
  - `tense_dramatic`: low strings or drones with a slow pulse, rising stakes; a conflict or a threat
  - `investigative_pulse`: a steady muted rhythm that keeps moving; laying out evidence, step by step
  - `mysterious_curiosity`: sparse plucks or pads with an open question in them; an unexplained fact
  - `calm_ambient`: soft pads, no drums, nothing competing with the voice; reflection or an ending

Flavours:
  - `middle_east`: oud, ney or darbuka colour over the mood; the Gulf, Iran, the Levant
  - `indian`: sitar, tabla, bansuri or tanpura colour over the mood; India and South Asia

Pairings:
(no v2 reference card yet: pick from the moods alone)

## JSON schema (SoundStory)

```json
{
  "$defs": {
    "BedChange": {
      "additionalProperties": false,
      "description": "076: where the second segment's bed takes over (the first beat of its part) and\nhow it sounds there.",
      "properties": {
        "at_beat": {
          "title": "At Beat",
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
        "at_beat",
        "how"
      ],
      "title": "BedChange",
      "type": "object"
    },
    "BedQuery": {
      "additionalProperties": false,
      "properties": {
        "theme": {
          "title": "Theme",
          "type": "string"
        },
        "mood": {
          "title": "Mood",
          "type": "string"
        },
        "energy": {
          "maximum": 5,
          "minimum": 1,
          "title": "Energy",
          "type": "integer"
        }
      },
      "required": [
        "theme",
        "mood",
        "energy"
      ],
      "title": "BedQuery",
      "type": "object"
    },
    "BedSegment": {
      "additionalProperties": false,
      "description": "076: the music from `part_from` on - one mood (and an optional flavour) of the\nclosed list, never free words; code picks the bed from the approved library.",
      "properties": {
        "part_from": {
          "enum": [
            "hook",
            "build_up",
            "reveal",
            "ending"
          ],
          "title": "Part From",
          "type": "string"
        },
        "mood": {
          "description": "one active mood of the list in the Music section",
          "title": "Mood",
          "type": "string"
        },
        "flavour": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "one active flavour of that list, or null",
          "title": "Flavour"
        }
      },
      "required": [
        "part_from",
        "mood"
      ],
      "title": "BedSegment",
      "type": "object"
    },
    "Cue": {
      "additionalProperties": false,
      "properties": {
        "beat_id": {
          "title": "Beat Id",
          "type": "string"
        },
        "intent": {
          "description": "one kind of the sound palette; section 1's sound rows say where each may sit",
          "enum": [
            "tick",
            "whoosh",
            "bass",
            "drum",
            "thump",
            "ding"
          ],
          "title": "Intent",
          "type": "string"
        },
        "at": {
          "enum": [
            "start",
            "event",
            "end"
          ],
          "title": "At",
          "type": "string"
        }
      },
      "required": [
        "beat_id",
        "intent",
        "at"
      ],
      "title": "Cue",
      "type": "object"
    },
    "MoodPoint": {
      "additionalProperties": false,
      "properties": {
        "t": {
          "title": "T",
          "type": "number"
        },
        "level": {
          "title": "Level",
          "type": "number"
        }
      },
      "required": [
        "t",
        "level"
      ],
      "title": "MoodPoint",
      "type": "object"
    },
    "PartSpan": {
      "additionalProperties": false,
      "description": "One story part of this script as a beat range, first and last beat included.",
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
        "first_beat": {
          "title": "First Beat",
          "type": "string"
        },
        "last_beat": {
          "title": "Last Beat",
          "type": "string"
        }
      },
      "required": [
        "part",
        "first_beat",
        "last_beat"
      ],
      "title": "PartSpan",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "prompt_version": {
      "title": "Prompt Version",
      "type": "string"
    },
    "theme": {
      "title": "Theme",
      "type": "string"
    },
    "mood_curve": {
      "items": {
        "$ref": "#/$defs/MoodPoint"
      },
      "title": "Mood Curve",
      "type": "array"
    },
    "bed_query": {
      "$ref": "#/$defs/BedQuery"
    },
    "cues": {
      "items": {
        "$ref": "#/$defs/Cue"
      },
      "title": "Cues",
      "type": "array"
    },
    "parts": {
      "default": [],
      "items": {
        "$ref": "#/$defs/PartSpan"
      },
      "title": "Parts",
      "type": "array"
    },
    "bed": {
      "default": [],
      "items": {
        "$ref": "#/$defs/BedSegment"
      },
      "title": "Bed",
      "type": "array"
    },
    "change": {
      "anyOf": [
        {
          "$ref": "#/$defs/BedChange"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    }
  },
  "required": [
    "prompt_version",
    "theme",
    "mood_curve",
    "bed_query",
    "cues"
  ],
  "title": "SoundStory",
  "type": "object"
}
```

Reply with JSON only: one object that matches the schema above, with no prose before or after it.
