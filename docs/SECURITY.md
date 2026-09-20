# Security model and limitations

What HazeNotes does to protect an instance — and, just as important, what it does not do. Read this before putting an instance on the public internet, together with the [deployment checklist](DEPLOYMENT.md#before-you-expose-it-checklist).

## What is in place

- **Passwords** — PBKDF2-SHA256, 600,000 iterations, random 16-byte salt per user. Legacy unsalted SHA-256 hashes (pre-2.0 accounts) are upgraded transparently on the next successful login.
- **Sessions** — 32-byte random tokens stored server-side with an expiry (`NOTEPAD_SESSION_TTL_HOURS`); expired rows are purged at startup and rejected on access. Changing username keeps the session; a migrated account that never logged in cannot be resumed.
- **Cookies** — `HttpOnly`, `SameSite=Lax`, `path=/`, and `Secure` set automatically when the request is HTTPS (directly or via `X-Forwarded-Proto`).
- **Authorization** — owner plus per-note collaborators with `edit`/`read` roles, enforced both on REST handlers and on WebSocket connect.
- **Uploads** — content is sniffed by magic bytes (extensions are never trusted), SVG is rejected as a script vector, the body is capped while streaming, and files are stored under random UUID names.
- **Response headers** — `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and a CSP limited to self plus Google Fonts (the sign-in page uses a webfont; without internet access the page falls back to a system font).
- **Brute force** — per-IP failed-login counter with configurable limit and window. It is in-process state, so it assumes the single-worker deployment described in the checklist.
- **Forwarded headers** — they are trusted from any address while `FORWARDED_ALLOW_IPS` keeps its `*` default (the image sets that so cloud load balancers work). Anyone who can reach the app directly — every machine on the LAN in the default setup — can then spoof `X-Forwarded-For` and influence the per-IP login limiter and the cookie flags. Set `FORWARDED_ALLOW_IPS` to your proxy's address when the app is not behind a cloud load balancer.

## Known limitations

- `POST /api/auth/register` is open and not rate limited — restrict it at the proxy if registration should be invite-only.
- No CSRF tokens. State-changing requests are protected by `SameSite=Lax` cookies only; keep the app on a single origin and do not add permissive CORS.
- The CSP allows `'unsafe-inline'` for scripts and styles because the templates embed them. XSS defence relies on sanitizing/escaping rendered content, not on CSP.
- `GET /images/{file}` is unauthenticated: anyone with the URL can read that image. Random file names are the only secret.
- The WebSocket handshake does not verify `Origin` — it relies on the same `SameSite=Lax` protection.
- No quotas: neither note count nor total storage is limited, so authenticated users can fill the disk.
- Editing a note does not garbage-collect images dropped from its body; only deleting the note does.
- `/health` is a liveness probe only — it does not verify database access.
- Changing a password (in the app or with the admin snippet in [USAGE.md](USAGE.md#faq-and-troubleshooting)) does not revoke existing sessions on other devices.
- There is no password reset (neither self-service nor a UI for it) and no export feature; [USAGE.md](USAGE.md#faq-and-troubleshooting) documents the admin workaround.
- The editor has no formatting toolbar and paste is inserted as plain text; formatting from earlier notes still renders (and is sanitized) because note bodies may contain HTML.
- The "Your note link" shown in the Share window (`…?note=<id>`) is not read by the client — the app opens the most recent note instead. Invite people by username.

Back to the [README](../README.md) · [Usage](USAGE.md) · [Deployment](DEPLOYMENT.md) · [API](API.md) · [Development](DEVELOPMENT.md)
