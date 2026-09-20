# 040 — Passcode entry, signed cookie, delay and per-IP block

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Every route except `/health` goes behind one shared passcode: entered once on `/`, stored as a signed cookie for 7 days with the signing key derived from the passcode so rotating it invalidates every cookie; a wrong passcode gets a 2 s delay and a per-IP counter; 10 failures in 10 minutes block that IP for an hour, in memory. Signing uses stdlib `hmac`; no new package.

Covers PRD `app` (auth). Decisions 11.2.

## Acceptance criteria

- [ ] `GET /` without a valid cookie shows the passcode form; a correct passcode sets the signed cookie (HttpOnly, SameSite=Lax, 7-day expiry) and redirects to the upload form.
- [ ] Every route except `/health` returns the passcode form or 401 for JSON without a valid cookie; job links stay shareable behind the same cookie.
- [ ] Wrong passcode: 2 s delay, per-IP counter; the eleventh failure inside 10 minutes is blocked for one hour with a plain message; counters live in memory with a fake clock in tests.
- [ ] Changing `SHORTSMITH_PASSCODE` invalidates existing cookies (test signs with the old passcode).
- [ ] Tests with the FastAPI test client cover all of the above without sleeping (the delay is injectable).

## Blocked by

- Blocked by `issues/002-upload-to-job-page.md`

## User stories addressed

- User story 52
- User story 56
