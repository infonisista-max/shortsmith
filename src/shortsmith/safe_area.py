"""The platform safe area (decisions 6.2, 6.3, ticket 067): the one definition.

The composition is 1080 x 1920. Every style keeps a 60 px left margin (6.2), and the
platform reserves three zones nothing may land in (6.3): the top 250 px, the bottom
320 px and the right rail, 140 px wide, under the like and comment buttons. The safe
band is what lies between the left margin and the rail: x 60 to 940, 880 px wide,
centred on x 500. The caption pager lays its lines out in it (067).

`captions`, `render`, `infographics`, `qa.technical` (T12) and `contact_sheet` read
these values from here; none keeps a copy. This module imports nothing from
`shortsmith`, so `captions` can use it without a cycle through `render`.
"""

from __future__ import annotations

WIDTH, HEIGHT = 1080, 1920  # the composition, in pixels

SAFE_LEFT = 60.0  # the style's left margin, the caption band's left edge (6.2)
SAFE_RIGHT_PX = 140.0  # the platform's right rail: nothing lands under it (6.3)
SAFE_TOP_PX = 250.0  # the platform's top zone (6.3)
SAFE_BOTTOM_PX = 320.0  # the platform's bottom zone (6.3)

BAND_LEFT = SAFE_LEFT
BAND_RIGHT = WIDTH - SAFE_RIGHT_PX
BAND_WIDTH = BAND_RIGHT - BAND_LEFT
BAND_CENTRE = (BAND_LEFT + BAND_RIGHT) / 2
