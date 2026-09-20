# HazeNotes usage guide

Everything a normal user needs: creating an account, writing notes, sharing them, and what to do when something looks wrong. No technical knowledge required.

The interface can be switched to Indonesian: pick **ID** on the sign-in page, or **Settings → Language** in the editor. The same menu switches between dark and light.

## Contents

- [Create your account](#create-your-account)
- [Write a note](#write-a-note)
- [Add a picture](#add-a-picture)
- [Write together: sharing a note](#write-together-sharing-a-note)
- [Tabs: rename, close, delete, leave](#tabs-rename-close-delete-leave)
- [Your account and settings](#your-account-and-settings)
- [FAQ and troubleshooting](#faq-and-troubleshooting)
- [Glossary](#glossary)

## Create your account

1. Open the address of your HazeNotes instance (for example `http://localhost:8123`). You land on the sign-in page.
2. Click **Create Account**, choose a username (3–32 characters: letters, numbers, `_` or `-`) and a password (at least 6 characters), then click **Create Account**.
3. Switch back to **Sign In**, enter the same details and click **Continue**.

Two things worth knowing up front:

- There is **no email address** and **no "forgot password" link**. Nobody can email you a reset link. Keep the password safe, and see the [FAQ](#faq-and-troubleshooting) if it is lost.
- There is **no administrator account**. The first account is an ordinary account like every other one — it just happens to be the first. (Your server administrator may also have switched accounts off entirely; ask them if you cannot register.)

## Write a note

The first time you sign in, HazeNotes creates a note called **New Note** for you, so you can start typing straight away.

- **There is no Save button.** About half a second after you stop typing, the note is saved. The top-right of the bar shows `Saving…` and then `Saved`.
- If the status still says `Saving…`, give it a moment before closing the tab or the last characters may be lost.
- The editor accepts one note body up to **1 MB** of text (a very large note — roughly 500 pages) and a title up to **120 characters**.
- Text you paste is inserted as plain text; there is no bold/italic toolbar yet. Images and any HTML already inside a note (headings, lists, code blocks, links) are still rendered and cleaned before display, so pasted junk cannot inject scripts.

## Add a picture

- **Paste** a screenshot or image from the clipboard, or **drag and drop** an image file onto the page. It uploads and appears where your cursor was.
- Allowed: PNG, JPEG, GIF, WebP, BMP up to **20 MB** each. SVG is refused by design.
- **Privacy note:** an uploaded image is served to anyone who has its link (a long random address). Do not put anything secret in an image, and read [Known limitations](SECURITY.md#known-limitations).

## Write together: sharing a note

You share one note at a time, and only the **owner** (the account that created it) can manage the list.

1. On the note's tab at the top, click the small **link icon** (it sits on the tab, right after the title) to open the **Share Note** window.
2. Type the **username** of the person you want to invite and pick a role:
   - **Can edit** — they can type in the note and rename it.
   - **Read only** — they can open and read it, but not change it.
   - The person must already have an account; unknown usernames are rejected.
3. Click **Add Collaborator**. The note now appears in their tab list, marked with a small people icon.
4. To stop sharing, click **Remove** next to their name in the same window, or change their role with the drop-down.
5. Being live: while you both have the note open, what one of you saves appears for the other within a moment, and renames show up on the tab too. If the owner deletes the note, it disappears from everyone else's tab list.

> **About "Your note link" / Copy Link:** the Share window offers a link such as `…?note=<id>`, but the app currently always opens your most recent note and does not read the `?note=` part — so that link does **not** jump to the shared note yet. Invite people by **username** instead. See [Known limitations](SECURITY.md#known-limitations).

## Tabs: rename, close, delete, leave

Every note is a tab in the top bar, and notes shared with you appear there as well.

| Action | How |
|---|---|
| New note | Click **+** on the right of the tab strip |
| Rename a note | Click the tab's title and type the new name |
| Scroll through many tabs | Use the **‹** and **›** arrows (they appear when the strip overflows) |
| Delete a note you own | Click **×** on the tab and confirm |
| Leave a note shared with you | Click **×** on the tab and confirm — the note stays for the owner |

The **×** only shows while you have more than one note, so the last remaining note cannot be closed that way. Owners delete, collaborators leave: same button, different meaning.

## Your account and settings

Click the **gear icon** in the top bar:

- **Username** — change it (your notes and shares follow you).
- **Password** — change it (your current password is required).
- **Language** — English or Indonesian.
- **Logout** is the icon on the far right of the bar, and the sun/moon icon switches the theme.

A sign-in lasts **7 days** by default, then you sign in again. Logging out ends it immediately. Restarting the server does not log you out.

## FAQ and troubleshooting

**I forgot my password. What can I do?**
There is no reset link and no reset screen, by design (there is no email address to send one to). Someone with shell access to the server can set a new one:

```bash
docker exec -it hazenotes python -c "from hazenotes import db, security; print(db.update_user_password('alice', security.hash_password('my-new-password')))"
```

It prints `True` when the password was replaced; the account keeps its notes and shares. Note that **changing a password does not sign other devices out** (this is also true of the in-app password change). If the account may be compromised, clear its sessions too:

```bash
docker exec -it hazenotes python -c "import sqlite3;c=sqlite3.connect('/app/storage/data/notepad.db');print(c.execute('DELETE FROM sessions WHERE username=?',('alice',)).rowcount,'sessions removed');c.commit()"
```

On a manual install, replace `/app/storage/data/notepad.db` with your `storage/data/notepad.db` path.

**My note is not saving, or text vanished.**
Check the status text at the top of the bar. `Saving…` means the request is in flight; `Saved` means it went through. Two known traps:

- Closing the tab while it still says `Saving…` can lose the last characters — saves happen about half a second after you stop typing.
- A note body over **1 MB** is rejected by the server, and the editor does not currently show that error (it may still say `Saved`). Split very large notes.

**Two people typed at the same time and one version won.**
Edits are saved as whole notes, not merged character by character: whoever saves last replaces the body. While you have unsaved keystrokes, incoming live updates are ignored on purpose so they cannot overwrite what you are typing. For real-time co-writing on the same paragraph, agree on who types where.

**A collaborator cannot open the shared note, or live updates never arrive.**
Check in this order: (1) the person was added by **username** in the Share window, and usernames are case-sensitive; (2) you are both looking at the same note; (3) if the instance sits behind a reverse proxy, it must forward the WebSocket upgrade — see [the nginx example](DEPLOYMENT.md#nginx). The browser retries the connection every 2 seconds.

**"Too many attempts. Try again later."**
The login limiter counts failed attempts per IP address: 10 within 5 minutes by default, then it answers `429`. Wait for the window to pass, or restart the app. If *everyone* hits this at once, the proxy is probably not passing the real client IP (`X-Forwarded-For`) — see [the nginx example](DEPLOYMENT.md#nginx).

**My image upload failed.**
- "File too large" (`413`) — the image is bigger than 20 MB.
- "Unsupported image type" — only PNG, JPEG, GIF, WebP and BMP are accepted, and the type is detected from the file content, not the file name. SVG is refused on purpose because it can contain scripts.
- "No file content received" — the paste or drop was empty; try saving the image and dragging the file instead.

**Can I export my notes?**
There is no export button yet. Everything is in one SQLite file, so an admin can read it directly:

```bash
docker exec hazenotes python -c "
import json, sqlite3
c = sqlite3.connect('/app/storage/data/notepad.db')
rows = [{'title': t, 'content': b} for t, b in c.execute('SELECT title, content FROM notes')]
print(json.dumps(rows, indent=2))
"
```

**Where does my data live, and does a restart lose it?**
In `storage/data/notepad.db` plus `storage/images/` (inside the `hazenotes-data` volume for the Docker install). Restarting the app or the server keeps notes and sessions. Only template changes wait for a restart.

**Is it safe to put this on the internet?**
Only with TLS in front, the app port bound to loopback, exactly one worker, and backups running. Read the [deployment checklist](DEPLOYMENT.md#before-you-expose-it-checklist) and the [known limitations](SECURITY.md#known-limitations) — uploaded images are readable by anyone holding their URL, and registration is open unless the proxy blocks it.

**The sign-in page looks plain, or the fonts changed.**
That page loads a Google webfont; without internet access the browser falls back to a system font. It is cosmetic, and nothing else in the app depends on an external service.

**Something broke after an upgrade.**
Restore the backup you took before upgrading ([Backup and restore](DEPLOYMENT.md#backup-and-restore)): stop the container, put back `notepad.db` and `images/`, start it again. Restore *before* starting the old version.

## Glossary

| Term | In plain words |
|---|---|
| **Instance** | One running copy of HazeNotes, on one machine. |
| **Note / tab** | A note is one document; each note is a tab in the top bar. |
| **Owner** | The account that created the note, and the only one that can delete it or manage its share list. |
| **Collaborator** | An account the owner added to a note, with the role `edit` or `read`. |
| **Reverse proxy** | A small web server (nginx, Caddy, Traefik) in front of the app that handles HTTPS and forwards requests to HazeNotes. |
| **TLS / HTTPS** | Transport encryption — the padlock in the browser. Without it, passwords travel in the clear. |
| **Docker / container** | A pre-packaged box holding the app and its dependencies, so you do not install Python packages by hand. |
| **Image** | The recipe/package for a container; `docker build` creates it from the `Dockerfile`. |
| **Volume** | Storage outside the container that survives rebuilds — here it holds `/app/storage`. |
| **Worker** | One process serving requests. HazeNotes must run exactly one. |
| **Environment variable** | A named setting handed to the program at start-up, e.g. `NOTEPAD_PORT=9000`. |
| **Session cookie** | A random token the browser sends with each request, proving you are signed in. |
| **WebSocket** | A connection that stays open, so the server can push changes to your browser without a refresh. |
| **SQLite / WAL** | A database in a single file. WAL (write-ahead log) is a mode that keeps it fast and crash-safe. |
| **Magic bytes** | The first few bytes of a file, used to detect its real type instead of trusting its extension. |
| **PBKDF2** | A deliberately slow one-way function applied to passwords, so a stolen database is expensive to crack. |
| **CSP** | A browser rule set that limits which files and scripts the page may load or run. |
| **Liveness probe** | A cheap URL (`/health`) that monitoring calls to see whether the app is still alive. |

Back to the [README](../README.md) · [Deployment](DEPLOYMENT.md) · [API](API.md) · [Security](SECURITY.md) · [Development](DEVELOPMENT.md)


