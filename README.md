# Notepad Web

A lightweight, tabbed note-taking web app with a zero-dependency Python backend. Write notes in your browser, organize them in tabs, and keep everything synced across open clients — no database, no frameworks, just Python's standard library. test

## Features

- 📝 **Tabbed notes** — create, rename, and delete notes from a browser-style tab bar
- 💾 **Autosave** — notes are saved automatically ~500 ms after you stop typing
- 🔄 **Live sync** — the server is polled every second, so multiple open tabs/clients stay in sync
- 🖼️ **Image support** — paste (`Ctrl+V`) or drag-and-drop images straight into a note
- 🌗 **Dark/light theme** — manual toggle, remembers your choice
- 🌐 **Bilingual UI** — English and Indonesian, switchable from the toolbar
- 🗑️ **Automatic cleanup** — images no longer referenced by any note are garbage-collected
- 🔒 **Sensible safeguards** — image uploads are validated by magic bytes (SVG is rejected to block active scripts), note bodies are sanitized before rendering, and request sizes are capped

## Requirements

- Python 3 (any recent version)

No `pip install` needed — the server uses only the standard library.

## Getting Started

1. Clone the repository:

   ```bash
   git clone https://github.com/hazekezia/NotepadWeb.git
   cd NotepadWeb
   ```

2. Start the server:

   ```bash
   python server.py
   ```

3. Open <http://localhost:8123> in your browser and start typing.

The server listens on `0.0.0.0:8123`, so other devices on your network can reach it at `http://<your-ip>:8123` (firewall permitting).

## Usage

| Action | How |
| --- | --- |
| Create a note | Click the **+** tab at the end of the tab bar |
| Switch notes | Click a tab |
| Rename a note | Click the tab's title, type a new name, press `Enter` (or `Esc` to cancel) |
| Delete a note | Click the **×** on the tab, then confirm |
| Add an image | Paste it (`Ctrl+V`) or drag and drop it into the note |
| Change theme | Click the 🌙 / ☀️ button in the top-right corner |
| Change language | Use the `EN` / `ID` selector in the top-right corner |

Notes autosave as you type — no save button needed.

## How It Works

### Storage

- **Notes** are stored as JSON files in the [`notes/`](notes/) directory — one `.txt` file per note, containing a `title` and a `body` (HTML). Plain-text files from older versions are still read, using the first non-empty line as the title.
- **Images** are stored in an `images/` directory (created automatically) with random filenames. Uploaded images are limited to PNG, JPEG, GIF, WebP, and BMP — up to 20 MB each — and are verified by their magic bytes rather than the `Content-Type` header. When a note is deleted, unreferenced images are removed automatically.

### API

The frontend ([`index.html`](index.html)) talks to the backend ([`server.py`](server.py)) over a small JSON API:

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/notes` | List all notes (id + title) |
| `POST` | `/api/notes` | Create a new note |
| `GET` | `/api/notes/<id>` | Read a single note |
| `POST` | `/api/notes/<id>` | Update a note's title and body |
| `POST` | `/api/notes/<id>/title` | Rename a note (plain-text body) |
| `DELETE` | `/api/notes/<id>` | Delete a note (and garbage-collect orphaned images) |
| `POST` | `/api/upload` | Upload an image, returns its `/images/...` URL |
| `GET` | `/images/<file>` | Serve an uploaded image |

### Limits

- Note body: 1 MB
- Image upload: 20 MB
- Note title: 120 characters
- Connection timeout: 10 s (guards against slow clients)

## Project Structure

```
NotepadWeb/
├── index.html     # The entire frontend — UI, tabs, autosave, i18n, theming
├── server.py      # Backend — stdlib-only HTTP server, note/image storage, API
├── favicon.png    # App icon
└── notes/         # Note files (created automatically)
```

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).
