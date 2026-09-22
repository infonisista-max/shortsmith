# Style specs

One markdown file per style: YAML front matter between `---` fences, then the five prose sections. `shortsmith.styles.load_all` validates every file at app startup; a broken spec stops the app with the spec name and the problem (grill decisions 1.2, 1.4).

Front matter must carry the seven key groups plus five more keys:

| key | who reads it |
| --- | --- |
| `aliases` | the resolver (1.1): words in the style line that pick this spec |
| `beats` | grammar validator (3.1, 3.4) |
| `presenter` | grammar validator (3.2) |
| `broll` | grammar validator, asset step, renderer (4.1, 4.3, 9.2, 9.4) |
| `captions` | pager and renderer (6.1, 6.2, 6.3) |
| `sound` | sound director and gate (7.1, 7.3) |
| `finale` | grammar validator and gate |
| `status` | `shipped` or `draft` (1.4): only shipped styles are offered and used; a draft's alias resolves to `explainer` with a notice |
| `requires_components` | cross-checked against the renderer registry; a shipped spec may not require a missing one (9.2) |
| `budget` | ledger caps (5.5, 5.6) |
| `pip` | PIP geometry (3.3); the loader asserts `pip.top + pip.diameter <= captions.anchor_y - captions.max_lines x line height` (6.3) |
| `palette` | renderer gradient and accent |

The prose sections are exactly, in order: **Beat grammar**, **B-roll**, **Captions**, **Sound**, **Finale**. The renderer and QA read only the numbers; the planner reads numbers and prose.

Rules: numbers are contracts (a sweep, a tight PIP crop, a collision fails QC). Add a style by adding a file; never hard-code a style rule in code. Quote `"off"` in YAML (a bare `off` is a boolean). Every `sound.forbidden` list bans sweeps and risers; chimes and ticks are ordinary planner cue choices under the 7.3 caps (7.1).
