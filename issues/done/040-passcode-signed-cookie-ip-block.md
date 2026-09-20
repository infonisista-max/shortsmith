# 040 — Passcode entry, signed cookie, delay and per-IP block

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Every route except `/health` goes behind one shared passcode: entered once on `/`, stored as a signed cookie for 7 days with the signing key derived from the passcode so rotating it invalidates every cookie; a wrong passcode gets a 2 s delay and a per-IP counter; 10 failures in 10 minutes block that IP for an hour, in memory. Signing uses stdlib `hmac`; no new package.

Covers PRD `app` (auth). Decisions 11.2.

## Acceptance criteria

- [x] `GET /` without a valid cookie shows the passcode form; a correct passcode sets the signed cookie (HttpOnly, SameSite=Lax, 7-day expiry) and redirects to the upload form.
- [x] Every route except `/health` returns the passcode form or 401 for JSON without a valid cookie; job links stay shareable behind the same cookie.
- [x] Wrong passcode: 2 s delay, per-IP counter; the eleventh failure inside 10 minutes is blocked for one hour with a plain message; counters live in memory with a fake clock in tests.
- [x] Changing `SHORTSMITH_PASSCODE` invalidates existing cookies (test signs with the old passcode).
- [x] Tests with the FastAPI test client cover all of the above without sleeping (the delay is injectable).

## Done — 21 Sep 2026

- `auth.py` (stdlib only): the cookie is `<issued_unix>.<hmac_sha256_hex>` signed with a key derived from the passcode (`hmac(passcode, label)`), so a rotated passcode is a new key and every old cookie fails. The 7-day life is checked against the signed timestamp, not just the browser's `Max-Age`, so a kept cookie cannot outlive it. Comparisons use `hmac.compare_digest`.
- `auth.FailureLog(clock)`: per-IP sliding window; the tenth failure inside ten minutes sets a one-hour block and clears the window; a blocked attempt is refused without being counted or delayed; the block expiring clears the counter.
- `app.PasscodeGuard` is a pure ASGI middleware (not `BaseHTTPMiddleware`) in front of every route except `/health` and `POST /passcode`. Without a valid cookie: `GET /` → the passcode form with 200; any other HTML request → the form with 401 and the requested path in a hidden `next` field; a `.json` path or an `Accept: application/json` request → 401 `{"error": "passcode required"}`. Nothing about a job leaks before login.
- `POST /passcode`: right passcode → cookie (HttpOnly, SameSite=Lax, `Max-Age` 7 days, `Secure` when served over https) and 303 to `next`; `next` must be a same-site absolute path (`/...`, not `//`, no backslash) or it falls back to `/`. Wrong passcode → failure recorded, then `await delay(2.0)` (injectable; `asyncio.sleep` in production), then the form again with 401. Blocked IP → 429 with "Too many wrong passcodes from this address. Try again in N minutes."
- Startup: the lifespan raises `RuntimeError` naming `SHORTSMITH_PASSCODE` when it is unset or empty, so an open link never serves. Kept out of `create_app` so importing `shortsmith.app` without a `.env` still works. `.env.example` now ships the key with an empty value; no default or real passcode value exists anywhere in the repo, tests inject theirs through `Settings`.
- The client IP is the socket peer (`request.client.host`). Behind a reverse proxy every visitor would share the proxy's IP; honouring `X-Forwarded-For` from a trusted proxy belongs with the Docker ticket 046.
- Tests: `tests/test_auth.py` (signing, expiry, tampering, rotation, block window with a fake clock) and `tests/test_app.py` (every acceptance criterion through the test client with the fake clock and a recording delay; per-IP via `TestClient(client=(ip, port))`). The existing app tests log in through a shared `client` fixture; `anon` is the logged-out one. Smoke is untouched: it never goes through HTTP.

## Blocked by

- Blocked by `issues/002-upload-to-job-page.md`

## User stories addressed

- User story 52
- User story 56
