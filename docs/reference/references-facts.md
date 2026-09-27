# Reference set, facts category - supplied by the operator, 27 Sep 2026

Companion to `docs/references.md`, which is operator-edited (the agent's permission
settings deny editing it). Operator: paste the section below into `docs/references.md`
as written; the inventory tool reads both files until then, so nothing waits on the
paste. Ticket 036.

## Facts — category `facts`, Tier A

Added by the operator on 27 Sep 2026, after run03 (score 6): "right now all videos
coming with exactly same style ... with learnings from urls, the system will have much
broader styles to incorporate." His note on the six, verbatim: "these are very important
facts based shorts, all fall under facts catagory and variety of scripts, styles,
background effects, transition effects and sound effects, they can be taken as base for
the system, system can try to replicate these styles and play with these styles".

- https://youtube.com/shorts/VSJzviqMO7k — Facts' Mine, "Amazing Facts About Multinational Companies"
- https://youtube.com/shorts/Q2pquJ2FlzA — NeelFacts, "Amazing Facts About EARTH in Hindi"
- https://youtube.com/shorts/cKxkAjYHXbk — Facts' Mine, "Fun Facts That Are Not Funny"
- https://youtube.com/shorts/zXK42RMPKUY — FactTechz, "CRAZY Facts About BRAIN and BODY!"
- https://youtube.com/shorts/bL3rUtUPYsc — FactTechz, "Highest INSANE Temperatures Ever Achieved By Humans!"
- https://youtube.com/shorts/S5j-2CWYYwM — Dhruv Rathee Shorts, "What Would Happen If the Sun Disappeared?"

The inventory tool (`python -m shortsmith.reference inventory <url>`, ticket 036) reads
each link through Gemini by URL; nothing is downloaded. Its JSON lands under
`docs/reference/inventory/`, the gap report at `docs/reference/inventory/GAPS.md`.
