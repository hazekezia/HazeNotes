# HTTP API

All JSON endpoints return JSON; errors use `{"error": "..."}` with the matching status code. "cookie" means a valid `session` cookie is required when `NOTEPAD_AUTH=TRUE`. Interactive docs are disabled on purpose (`docs_url=None`), so this table is the reference.

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

The WebSocket is server-to-client only: the HTTP handler is the source of truth, and it broadcasts to every other subscriber of that note. Payload shape and reconnect behaviour are described in [DEVELOPMENT.md](DEVELOPMENT.md#real-time-flow).

Back to the [README](../README.md) · [Usage](USAGE.md) · [Deployment](DEPLOYMENT.md) · [Security](SECURITY.md) · [Development](DEVELOPMENT.md)
