# HazeNotes

A self-hosted, multi-user note-taking app with real-time collaboration, built with **FastAPI**, **SQLite (WAL)**, and **WebSockets**. Single process, single file of state, no external services.

![Python](https://img.shields.io/badge/python-3.10+-blue) ![License](https://img.shields.io/badge/license-GPL%20v3-green)

## Features

- **Rich-text notes** (contenteditable with paste sanitization, headings, lists, code blocks)
- **Real-time collaboration** — edits broadcast over WebSocket to every open editor
- **Sharing** — per-note collaborators with `edit` / `read` roles
- **Authentication** — PBKDF2-SHA256 password hashing (600k iterations, salted), HTTP-only session cookies (7-day TTL)
- **Image uploads** — magic-byte validated (PNG/JPEG/GIF/WebP/BMP), 20 MB cap, size-limited streaming
- **Security headers** — nosniff, DENY framing, CSP, referrer policy
- **Zero-config persistence** — SQLite with WAL journaling, thread-local connections, automatic legacy JSON migration

## Project Structure

```
hazenotes/
  main.py            # App assembly, middleware, lifespan, /health
  config.py          # Env-driven configuration
  security.py        # Password hashing, session auth, permissions
  db.py              # SQLite persistence (WAL, schema, migrations)
  ws.py              # Connection manager + authenticated WS endpoint
  routers/
    auth.py          # register / login (rate limited) / logout
    notes.py         # CRUD + sharing + broadcast
    pages.py         # HTML pages + favicon
    uploads.py       # image upload + serving
  templates/         # login.html, editor.html
  static/            # favicon
tests/test_api.py    # assert-based API tests
```

## Quickstart

```bash
pip install -r requirements.txt
uvicorn hazenotes.main:app --host 0.0.0.0 --port 8123
```

Open http://localhost:8123, register an account, start writing. All data lives in `./storage/`.

Run tests:

```bash
python tests/test_api.py
```

## Configuration

All optional (defaults shown). See `.env.example`.

| Variable | Default | Description |
|---|---|---|
| `NOTEPAD_AUTH` | `TRUE` | `FALSE` disables auth (single-user mode, owner `anonymous`) |
| `NOTEPAD_HOST` / `NOTEPAD_PORT` | `0.0.0.0` / `8123` | Bind address |
| `NOTEPAD_DATA_DIR` | `./storage/data` | SQLite database directory |
| `NOTEPAD_IMAGES_DIR` | `./storage/images` | Uploaded images |
| `NOTEPAD_SESSION_TTL_HOURS` | `168` | Session lifetime (7 days) |
| `NOTEPAD_MAX_UPLOAD_BYTES` | `20971520` | Upload cap |
| `NOTEPAD_LOGIN_RATE_LIMIT` / `_WINDOW` | `10` / `300` | Failed logins per IP per window (seconds) |

## API

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/` | cookie | Login page (anonymous) or editor (authenticated) |
| `GET` | `/health` | — | Liveness probe |
| `POST` | `/api/auth/register` | — | Create account (3–32 chars `[A-Za-z0-9_-]`, password ≥ 6) |
| `POST` | `/api/auth/login` | — | Login; sets `session` cookie; rate limited |
| `POST` | `/api/auth/logout` | cookie | Destroy session |
| `GET/POST` | `/api/notes` | cookie | List / create notes |
| `GET/POST/DELETE` | `/api/notes/{id}` | cookie | Read / update / delete (or leave, as collaborator) |
| `POST/DELETE` | `/api/notes/{id}/share` | cookie (owner) | Add / remove collaborator |
| `POST/PUT` | `/api/upload` | cookie | Upload image (magic bytes: PNG/JPEG/GIF/WebP/BMP) |
| `GET` | `/images/{file}` | — | Serve uploaded image |
| `WS` | `/ws/notes/{id}` | cookie | Real-time note updates |

## Security Notes

- Passwords: PBKDF2-SHA256, per-user random salt. Pre-2.0 unsalted SHA-256 hashes upgrade transparently on next login.
- Sessions: 32-byte random tokens, stored server-side, expire after TTL, purged at startup and lazily on access.
- Cookies: `HttpOnly`, `SameSite=Lax`, `Secure` (set automatically when the request is HTTPS / via `X-Forwarded-Proto`).
- WebSocket: rejected with `4401` before `accept()` when unauthenticated; `4403` when lacking view access.
- Uploads: never trust extensions — content is sniffed via magic bytes; SVG is rejected (script vector).
- Brute-force login protection is per-process. Run **one worker** (SQLite WAL + in-memory limiter); scale vertically.

## Deployment

Docker:

```bash
docker build -t hazenotes .
docker run -p 8123:8123 -v hazenotes-data:/app/storage hazenotes
```

Behind a reverse proxy (nginx/Caddy) terminating TLS, use `--proxy-headers` (the Dockerfile already does) so secure cookies activate. Non-root user inside the container; all mutable state in the `/app/storage` volume.

## License

GNU GPL v3
