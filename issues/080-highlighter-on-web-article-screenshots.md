# 080 — Highlighter on web-searched real article screenshots

## Type

HITL — **parked until 079 (run05) is decided go.** First in line after run05 (operator,
grill 29 Sep 2026: "I want this to happen without me uploading every time").

## Parent PRD

`issues/prd.md`

## What to build

078 highlights only an article screenshot the owner uploads. This ticket finds a **real**
article snippet for a spoken claim on the web, so no upload is needed. Before it becomes
AFK, the operator decides:

- **The rights rule for news pages.** Web images are "always re-dressed, never shown raw"
  (5.1/5.2), but a highlighter on a blurred or restyled page doesn't work. Options: an
  exception for text snippets with the source URL and outlet named on screen; or only
  outlets whose terms allow quotation; or a crop limited to the sentence and its
  headline.
- **Where snippets come from.** Web image search for the headline, or a page fetch plus a
  rendered crop of the real page. Never a drawn fake: 078's "no fake newspaper" rule
  stands.
- **How the claim is checked.** The snippet's text must contain the spoken claim. Vision
  finds the lines (078), and a mismatch drops it.

## Acceptance criteria

- [ ] The operator's rights decision recorded here, then this ticket rewritten as AFK
      with test criteria.

## Blocked by

- `issues/078-article-highlighter.md`
- `issues/079-run05-learning-check.md`
