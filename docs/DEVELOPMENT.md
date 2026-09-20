# Development guide

Architecture, project layout, and internals. Installation and settings live in the [README](../README.md); operations in [DEPLOYMENT.md](DEPLOYMENT.md); endpoints in [API.md](API.md); the security model in [SECURITY.md](SECURITY.md); the end-user guide in [USAGE.md](USAGE.md).

## Project layout

```
hazenotes/
  __init__.py        # __version__
  main.py            # app assembly, security-header middleware, lifespan, /health, router wiring
  config.py          # environment-driven settings (read at import time)
  security.py        # password hashing, legacy hash upgrade, cookie_secure(), get_current_user(), can_view/can_edit
  db.py              # SQLite (WAL): schema, indexes, thread-local connections, migrations, all queries
  ws.py              # ConnectionManager + authenticated /ws/notes/{id} endpoint
  routers/
    auth.py          # register, login (rate limited), logout, change-username, change-password
    notes.py         # notes CRUD, sharing, image garbage collection, WebSocket broadcasts
    uploads.py       # /api/upload (magic bytes, streamed cap) and /images/{file}
    pages.py         # HTML pages (template cache + placeholder substitution), favicon
  templates/
    login.html       # single-file page: inline CSS/JS, no build step
    editor.html      # editor + sidebar + sharing UI
  static/
    favicon.png      # served at /favicon.png, also used as the project logo
tests/
  test_api.py        # end-to-end assert-based tests
docs/
  USAGE.md           # end-user guide (accounts, writing, sharing, FAQ, glossary)
  DEPLOYMENT.md      # production checklist, reverse proxy, container platforms, backup, upgrades
  API.md             # HTTP + WebSocket endpoint reference
  SECURITY.md        # security model and known limitations
  DEVELOPMENT.md     # this file
Dockerfile           # python:3.12-slim, non-root, PORT / FORWARDED_ALLOW_IPS knobs, HEALTHCHECK
docker-compose.yml   # LAN-accessible stack that reads .env
requirements.txt     # fastapi, uvicorn[standard], python-dotenv, httpx (tests)
.env.example         # every supported environment variable with its default
```

## Request lifecycle

1. Middleware sets the security headers on every response.
2. The router resolves the caller with `get_current_user()` (reads the `session` cookie, then `db.get_session_user()`).
3. Permission checks (`can_view` / `can_edit`) run against the note dict, which includes the collaborator map.
4. Database work is dispatched with `asyncio.to_thread(...)` — every blocking SQLite call runs off the event loop and reuses a thread-local connection.
5. Write handlers `await ws_manager.broadcast(...)` so other open editors see the change immediately.

`get_current_user()` accepts both `Request` and `WebSocket` objects, because Starlette exposes `.cookies` on each.

## Data model

| Table | Columns | Notes |
|---|---|---|
| `users` | `username` PK, `password_hash`, `created_at` | Hash format `pbkdf2_sha256$<iterations>$<salt>$<hash>`; the `anonymous` row exists for auth-disabled mode |
| `notes` | `id` PK, `title`, `content`, `owner` FK → `users`, `created_at`, `updated_at` | `updated_at` changes on body edits and on share changes |
| `collaborators` | `note_id`, `username`, `role` | PK `(note_id, username)`, roles `edit` / `read`, both FKs cascade |
| `sessions` | `token` PK, `username` FK → `users`, `created_at`, `expires_at` | `expires_at` NULL means no expiry check |

Indexes: `notes(owner)`, `notes(updated_at DESC)`, `collaborators(username)`, `collaborators(note_id)`, `sessions(username)`. Per-connection PRAGMAs: `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=30000`, `foreign_keys=ON`, `cache_size=-64000`.

## Real-time flow

Updates are server-to-client only; the HTTP handler is the source of truth and pushes to subscribers.

| Message | Sent when | Payload |
|---|---|---|
| `note_update` | a note body or title is saved | `note_id`, `sender`, `note` (when the body changed), `title` (when the title changed) |
| `note_deleted` | the owner deletes the note | `note_id` |

Clients keep the socket open and reconnect automatically when it drops (`editor.html` schedules a reconnect while the same note is open). Unauthenticated connections are closed with `4401` before `accept()`, callers without view access with `4403`.

## Templates and frontend

No template engine: `_load_template()` reads the HTML once and caches it, then `_render_editor_page()` substitutes placeholders (`CURRENT_USER_PLACEHOLDER_`, `LOGOUT_BUTTON_PLACEHOLDER`, `APP_VERSION_PLACEHOLDER_`, …). User data is injected with `json.dumps(...).replace('</', '<\\/')` so it cannot break out of the inline `<script>`. Template edits require a restart.

## Configuration internals

`hazenotes/config.py` reads the environment once, at import time — tests must therefore set `NOTEPAD_DATA_DIR` / `NOTEPAD_IMAGES_DIR` *before* importing the package (`tests/test_api.py` does exactly that, into a temp directory). Settings also configurable at runtime do not exist by design: restart to change configuration. Limits that are code constants rather than environment variables: `MAX_NOTE_BYTES` (1,000,000), `MAX_TITLE_LEN` (120). `PORT` is consulted only when `NOTEPAD_PORT` is unset — that is the variable container platforms inject.

`config.py` also loads a `.env` from the working directory through `python-dotenv`, parsed as `utf-8-sig` so a byte-order mark cannot swallow the first key, and with `override=False`: variables already present in the real environment always win, which is what containers and cloud platforms rely on. Docker images contain no `.env` at all, so there it is a no-op. `python-dotenv` is the one dependency added for this; it is already part of `uvicorn[standard]` and is pinned in `requirements.txt`.

## Legacy JSON migration

`migrate_legacy_data()` runs at startup and only while the corresponding table is empty:

- `users.json` → `users`: plain SHA-256 hashes are imported as-is and upgraded on the next successful login; the original file is kept as `<file>.bak`.
- `notes.json` → `notes` plus `collaborators` (a list of usernames becomes `edit` roles); again with a `.bak` copy.

Migrated accounts receive a random, unusable password hash — the pre-2.0 code shipped a hardcoded default password, which is deliberately not carried over. Such accounts cannot be logged into and there is no password-reset endpoint, so to hand ownership back you must write a new hash produced by `security.hash_password()` into the `users` row directly. Usernames are taken: re-registering the same name is rejected as a duplicate.

## Tests

`tests/test_api.py` is assert-based and needs no test framework:

```bash
python tests/test_api.py     # prints PASS/FAIL per check, exits non-zero on failure
pytest tests                 # optional; pytest picks up the same file
```

It isolates storage in a temp directory, then covers health and security headers, registration and login validation, notes CRUD and permission checks for owners/collaborators/strangers, sharing, the settings endpoints (username and password changes), image upload validation plus orphan-image garbage collection (including a path-traversal attempt), WebSocket auth, session expiry, and the legacy hash upgrade — 55 checks in total. Two of them re-import the package in a fresh subprocess to prove that a BOM-prefixed `.env` is still parsed and that a bare `PORT` is honoured. `httpx` is the only test extra (`fastapi.testclient`), listed in `requirements.txt`. The per-IP login limiter is not covered yet; it needs a test that drives `NOTEPAD_LOGIN_RATE_LIMIT` low.

## Conventions

- No new runtime dependencies without a strong reason — stdlib first (`hashlib`, `secrets`, `hmac`, `sqlite3`, `asyncio.to_thread`).
- Comments marked `ponytail:` name a deliberate simplification together with the point at which it has to be revisited.
- Errors are returned as `{"error": "..."}` with an explicit status code; no custom exception hierarchy.
- Adding a setting means adding an env var in `config.py` plus a row in the README configuration table and `.env.example`.

## Where to extend next

- Registration limiting / invite codes (today: open endpoint, mitigated at the proxy).
- Per-user storage quotas; the disk is currently unbounded.
- Garbage collection of images removed from a note body during an edit (today only note deletion does it).
- Multiple instances would need shared session storage, a shared rate limiter, and a WebSocket fan-out (e.g. Redis) — out of scope for the single-file design.
