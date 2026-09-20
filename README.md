<p align="center">
  <img src="hazenotes/static/favicon.png" alt="HazeNotes logo" width="120" height="120">
</p>

<h1 align="center">HazeNotes</h1>

<p align="center">
  Self-hosted, multi-user note taking with real-time collaboration.<br>
  FastAPI · SQLite (WAL) · WebSockets — one process, one file of state, no external services.
</p>

<p align="center">
  <a href="https://github.com/hazekezia/HazeNotes/releases"><img alt="Version" src="https://img.shields.io/badge/version-2.0.0-blue"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="License" src="https://img.shields.io/badge/license-GPL%20v3-green">
  <img alt="Deploy" src="https://img.shields.io/badge/deploy-Docker-2496ED?logo=docker&logoColor=white">
</p>

<p align="center">
  <img src="docs/screenshot.png" alt="HazeNotes editor with a shared note" width="900">
</p>

## Features

- **Rich-text notes** — headings, lists, code blocks, pasted content sanitized in the `contenteditable` editor.
- **Real-time collaboration** — every edit is broadcast over WebSocket to all editors that have the note open.
- **Per-note sharing** — collaborators with `edit` or `read` roles; only the owner manages the share list.
- **Authentication** — PBKDF2-SHA256 (600,000 iterations, per-user salt), HTTP-only session cookies with configurable TTL.
- **Image uploads** — magic-byte validated (PNG/JPEG/GIF/WebP/BMP), 20 MB default cap enforced while streaming, SVG rejected.
- **Security headers** — `nosniff`, `DENY` framing, CSP, `no-referrer` on every response.
- **Zero-config persistence** — SQLite in WAL mode, thread-local connections, automatic one-shot import of the legacy JSON store.
- **Tiny dependency surface** — FastAPI + uvicorn. No database server, broker, or cache to operate.

## Requirements

- **Python 3.10+** (the Docker image ships 3.12)
- **Docker**, for the container path
- **TLS** in front of the app for any non-loopback deployment — see [Production deployment](#production-deployment)

## Quick start

### Docker (recommended)

```bash
docker build -t hazenotes .
docker run -d --name hazenotes \
  --restart unless-stopped \
  -p 127.0.0.1:8123:8123 \
  -v hazenotes-data:/app/storage \
  hazenotes
```

Open `http://localhost:8123` and register the first account. All mutable state lives in the `hazenotes-data` volume (`/app/storage`).

Publish on `127.0.0.1` (or an internal Docker network) and put a TLS-terminating proxy in front — see [Production deployment](#production-deployment).

### Manual

```bash
python -m venv .venv
. .venv/Scripts/activate      # Windows
source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
uvicorn hazenotes.main:app --host 0.0.0.0 --port 8123
```

Run the command from the repository root: state goes to `./storage/data` (SQLite) and `./storage/images`. `python -m hazenotes.main` also works and honours `NOTEPAD_HOST` / `NOTEPAD_PORT`.

## Configuration

Everything is read from environment variables at process start. **HazeNotes does not read a `.env` file itself** — pass variables with `docker run -e`, systemd `Environment=`, or start uvicorn with `--env-file .env`. Starting point: [`.env.example`](.env.example).

| Variable | Default | Description |
|---|---|---|
| `NOTEPAD_AUTH` | `TRUE` | `FALSE` disables authentication entirely (single-user mode, owner `anonymous`). |
| `NOTEPAD_HOST` | `0.0.0.0` | Bind address used by `python -m hazenotes.main`. |
| `NOTEPAD_PORT` | `8123` | Bind port used by `python -m hazenotes.main`. |
| `NOTEPAD_DATA_DIR` | `./storage/data` | SQLite database directory (`notepad.db`). |
| `NOTEPAD_IMAGES_DIR` | `./storage/images` | Uploaded image directory. |
| `NOTEPAD_SESSION_TTL_HOURS` | `168` | Session lifetime (7 days). |
| `NOTEPAD_MAX_UPLOAD_BYTES` | `20971520` | Upload cap (20 MB), enforced while the body streams in. |
| `NOTEPAD_LOGIN_RATE_LIMIT` | `10` | Failed logins per IP before `429`. |
| `NOTEPAD_LOGIN_RATE_WINDOW` | `300` | Rate-limit window, in seconds. |

Two limits are constants in `hazenotes/config.py`, not environment variables: note body 1 MB (`MAX_NOTE_BYTES`) and note title 120 characters (`MAX_TITLE_LEN`).

## Production deployment

Checklist before exposing an instance:

1. **Terminate TLS at a reverse proxy.** Session cookies only get the `Secure` flag when the request arrives over HTTPS (directly or via `X-Forwarded-Proto`). The bundled container already runs uvicorn with `--proxy-headers`.
2. **Publish the app port to the proxy only.** The image trusts `--forwarded-allow-ips *`, so anyone who can reach port 8123 directly can spoof `X-Forwarded-For` / `X-Forwarded-Proto` and influence the per-IP login limiter. Bind it to loopback (`-p 127.0.0.1:8123:8123`), keep it on an internal network, or narrow `--forwarded-allow-ips` in the `Dockerfile` to your proxy address.
3. **Run exactly one worker.** SQLite WAL, the in-process login limiter, and the in-memory WebSocket manager all assume a single process. Do not enable uvicorn `--workers` or multi-worker gunicorn; scale vertically instead.
4. **Mount and watch storage.** `/app/storage` is the only mutable path. Disk usage grows with uploads (up to `NOTEPAD_MAX_UPLOAD_BYTES` each) and note bodies; alert on free space.
5. **Back up before every upgrade.** See [Operations](#operations).
6. **Probe liveness.** `GET /health` is cheap and does not touch SQLite.
7. **Decide about registration.** `POST /api/auth/register` is open and not rate limited; block or filter it at the proxy if the instance is invite-only.

nginx (TLS + WebSocket upgrade):

```nginx
server {
    listen 443 ssl;
    server_name notes.example.com;
    # ssl_certificate / ssl_certificate_key ...

    location / {
        proxy_pass http://127.0.0.1:8123;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # real-time collaboration
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
```

Caddy handles TLS, forwarded headers, and WebSocket upgrades with a single directive:

```caddyfile
notes.example.com {
    reverse_proxy 127.0.0.1:8123
}
```

## Operations

### Backup and restore

WAL mode means the database file alone is not a consistent snapshot while the app runs. Use SQLite's online backup API — safe with the app online:

```bash
docker exec hazenotes python -c "import sqlite3; sqlite3.connect('/app/storage/data/notepad.db').backup(sqlite3.connect('/tmp/backup.db'))"
docker cp hazenotes:/tmp/backup.db "./notepad-$(date +%F).db"
docker cp hazenotes:/app/storage/images "./images-$(date +%F)"
```

Without Docker, the same one-liner works on `storage/data/notepad.db`; images are write-once with random file names, so a plain copy or `rsync` of `storage/images` is enough.

Restore: stop the container, replace `notepad.db` and the `images` directory inside the volume, start it again. Startup is idempotent — schema creation uses `CREATE TABLE IF NOT EXISTS` and the legacy JSON import only runs against empty tables.

### Health and logs

- `GET /health` → `{"status": "ok"}`, liveness only: it does not read or write SQLite.
- Application logs go to stdout at INFO level (`%(asctime)s %(levelname)s %(name)s: %(message)s`); collect them with `docker logs` or journald.
- Container healthcheck (add to the `Dockerfile` or a compose file):

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8123/health')"
```

### Upgrades

1. Take a backup (above).
2. Build/pull the new image or update the checkout plus `pip install -r requirements.txt`.
3. Restart. Schema migrations are additive and idempotent; the legacy JSON import only touches an empty database.

Sessions live in the database, so a restart does not log users out. Template edits need a restart (templates are cached at first use).

## API reference

All JSON endpoints return JSON; errors use `{"error": "..."}` with the matching status code. "cookie" means a valid `session` cookie is required when `NOTEPAD_AUTH=TRUE`.

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/`, `/index.html` | — | Login page for anonymous visitors, editor for authenticated ones |
| `GET` | `/favicon.png` | — | App icon |
| `GET` | `/health` | — | Liveness probe |
| `POST` | `/api/auth/register` | — | Create account. Username 3–32 chars of `[A-Za-z0-9_-]`, password 6–128 chars |
| `POST` | `/api/auth/login` | — | JSON `{username, password}`; sets the `session` cookie; `429` when rate limited |
| `GET` | `/api/auth/login` | — | Only with `NOTEPAD_AUTH=FALSE`: reports the anonymous identity |
| `POST` | `/api/auth/logout` | cookie | Deletes the session row and clears the cookie |
| `POST` | `/api/auth/change-username` | cookie | JSON `{new_username, current_password}`; notes and collaborators follow the rename |
| `POST` | `/api/auth/change-password` | cookie | JSON `{current_password, new_password}` |
| `GET` | `/api/notes` | cookie | Notes owned by or shared with the caller (metadata only) |
| `POST` | `/api/notes` | cookie | JSON `{title?}`; returns `{id, title}` |
| `GET` | `/api/notes/{id}` | cookie | Note body plus owner, timestamps, collaborators (`403` without view access) |
| `POST`, `PUT` | `/api/notes/{id}` | cookie | JSON `{title?, note?}`; requires `edit` permission; body ≤ 1 MB |
| `DELETE` | `/api/notes/{id}` | cookie | Owner: delete note (unreferenced images are removed). Collaborator: leave the note |
| `POST` | `/api/notes/{id}/share` | owner | JSON `{username, role}` with `role` = `edit` or `read` |
| `DELETE` | `/api/notes/{id}/share` | owner | JSON `{username}`; removes the collaborator |
| `POST`, `PUT` | `/api/upload` | cookie | Raw image body; returns `{url}`; `413` when over the cap |
| `GET` | `/images/{file}` | — | Serves an uploaded image (the URL is the only secret) |
| `WS` | `/ws/notes/{id}` | cookie | Server-to-client updates (`note_update`, `note_deleted`); closes `4401` unauthenticated, `4403` without view access |

## Security model

- **Passwords** — PBKDF2-SHA256, 600,000 iterations, random 16-byte salt per user. Legacy unsalted SHA-256 hashes (pre-2.0 accounts) are upgraded transparently on the next successful login.
- **Sessions** — 32-byte random tokens stored server-side with an expiry (`NOTEPAD_SESSION_TTL_HOURS`); expired rows are purged at startup and rejected on access. Changing username keeps the session; a migrated account that never logged in cannot be resumed.
- **Cookies** — `HttpOnly`, `SameSite=Lax`, `path=/`, and `Secure` set automatically when the request is HTTPS (directly or via `X-Forwarded-Proto`).
- **Authorization** — owner plus per-note collaborators with `edit`/`read` roles, enforced both on REST handlers and on WebSocket connect.
- **Uploads** — content is sniffed by magic bytes (extensions are never trusted), SVG is rejected as a script vector, the body is capped while streaming, and files are stored under random UUID names.
- **Response headers** — `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and a CSP limited to self plus Google Fonts.
- **Brute force** — per-IP failed-login counter with configurable limit and window. It is in-process state, so it assumes the single-worker deployment described above.

### Known limitations

Read these before putting an instance on the public internet:

- `POST /api/auth/register` is open and not rate limited — restrict it at the proxy if registration should be invite-only.
- No CSRF tokens. State-changing requests are protected by `SameSite=Lax` cookies only; keep the app on a single origin and do not add permissive CORS.
- The CSP allows `'unsafe-inline'` for scripts and styles because the templates embed them. XSS defence relies on sanitizing/escaping rendered content, not on CSP.
- `GET /images/{file}` is unauthenticated: anyone with the URL can read that image. Random file names are the only secret.
- The WebSocket handshake does not verify `Origin` — it relies on the same `SameSite=Lax` protection.
- No quotas: neither note count nor total storage is limited, so authenticated users can fill the disk.
- Editing a note does not garbage-collect images dropped from its body; only deleting the note does.
- `/health` is a liveness probe only — it does not verify database access.

## Development

Project layout, data model, request lifecycle, and the legacy migration are documented in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

```bash
python tests/test_api.py    # assert-based, 53 checks, no framework needed
pytest tests                # optional, works too
```

## License

GNU General Public License v3 — see [LICENSE](LICENSE).
