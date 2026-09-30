# 104 — Maps a viewer can read: the named country filled and named, a minimum span, the target circle

## Type

AFK (touches `src/remotion`)

## Parent PRD

`issues/prd.md`

## Why

Run05 b08/b09 (0:13-0:16):
- The editor's b09 repair framed on the markers only (bbox about 3°x5°), so Riyadh sat on
  empty blue. `infographics.py:926-936` has no minimum span.
- `map.tsx:112-165` draws land, borders, coast and one pill per marker: no country names,
  no fill for the named country, no region label.
- b07 drew a lone Riyadh dot, with the stamp over the country.
- Land `#2F5597` is close to the background `#1F3B73`.
- The travelling glyph sits on the endpoint dot.

## What to build

- **Minimum span** in degrees (`map.min_span_deg`, front matter) for every map, the
  editor's repair included: the frame widens around the markers to at least that.
- **The named country or region** gets a highlighted fill (front-matter colour) and a
  name label; neighbouring countries in view get small name labels (collision rules from
  072).
- **Target circle + angled label** (083, `ePTZVwipoAM` 26 s, 48 s): a circle drawn round
  the named place with an angled label, numbers from the card's `motion` data.
- **A dot is never unlabelled:** a marker with no name is dropped, not drawn.
- The travelling object is drawn beside the endpoint dot, never over it.
- **Land/sea contrast:** the land colour is re-picked so land and sea can be told apart on
  a phone, checked against the reference map frames.
- Country names come from the local geo data (`geo.py`; no network).

## Acceptance criteria

- [ ] A 3°x5° repair bbox renders at the minimum span (test).
- [ ] A map with `region: Saudi Arabia` fills and names Saudi Arabia; neighbours are named.
- [ ] No unnamed marker in any render spec (test).
- [ ] Remotion tests + a bench frame; typecheck green; smoke green.

## Blocked by

None.

## User stories addressed

Operator, 30 Sep 2026, finding 1: "framed so tight on Kuwait-Riyadh that the place can't
be read ... no country names or borders, a lone unlabeled dot at 0:13."
