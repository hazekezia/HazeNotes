#!/usr/bin/env python3
import json, os, re, uuid, socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
NOTES_DIR = os.path.join(HERE, "notes")
IMG_DIR = os.path.join(HERE, "images")
PORT = 8123
MAX_UPLOAD = 20 * 1024 * 1024  # 20 MB
MAX_NOTE = 1 * 1024 * 1024  # 1 MB (DoS guard)
MAX_TITLE = 120
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

MAGIC = [
    (b"\x89PNG\r\n\x1a\n", ".png", "image/png"),
    (b"\xff\xd8\xff", ".jpg", "image/jpeg"),
    (b"GIF87a", ".gif", "image/gif"),
    (b"GIF89a", ".gif", "image/gif"),
    (b"RIFF", ".webp", "image/webp"),
]
# Hanya ekstensi gambar raster yang diizinkan. SVG dihapus agar file yang
# bisa membawa script aktif tidak pernah disimpan/disajikan.
CTYPE_EXT = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
    "image/webp": ".webp", "image/bmp": ".bmp",
}
STATIC_CTYPE = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def sniff(data, ctype):
    # Hanya percaya magic bytes sungguhan, bukan header Content-Type.
    # Jika tidak ada magic raster yang cocok, tolak (return None, None).
    for magic, ext, mime in MAGIC:
        if data.startswith(magic):
            if ext == ".webp" and data[8:12] != b"WEBP":
                continue
            return ext, mime
    return None, None


def read_note(nid):
    fp = os.path.join(NOTES_DIR, nid + ".txt")
    if not os.path.isfile(fp):
        return None
    try:
        with open(fp, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return None
    try:
        d = json.loads(raw)
        if isinstance(d, dict) and "body" in d:
            return {"title": (d.get("title") or "")[:MAX_TITLE], "body": d.get("body") or ""}
    except json.JSONDecodeError:
        pass
    # legacy: raw text, first non-empty line = title
    title = ""
    body = raw
    for line in raw.splitlines():
        if line.strip():
            title = line.strip()[:MAX_TITLE]
            idx = raw.index(line)
            body = raw[idx+len(line):].lstrip("\n")
            break
    return {"title": title, "body": body}


def write_note(nid, title, body):
    fp = os.path.join(NOTES_DIR, nid + ".txt")
    payload = json.dumps({"title": (title or "")[:MAX_TITLE], "body": body or ""}, ensure_ascii=False)
    with open(fp, "w", encoding="utf-8") as f:
        f.write(payload)


IMG_REF_RE = re.compile(r"/images/([A-Za-z0-9_.-]+)")


def collect_referenced_images():
    """Kumpulkan nama file gambar yang masih dirujuk oleh note mana pun."""
    refs = set()
    for fn in os.listdir(NOTES_DIR) if os.path.isdir(NOTES_DIR) else []:
        if not fn.endswith(".txt"):
            continue
        nid = fn[:-4]
        if not ID_RE.match(nid):
            continue
        d = read_note(nid)
        if d is None:
            continue
        refs.update(m.group(1) for m in IMG_REF_RE.finditer(d["body"]))
    return refs


def gc_images():
    """Hapus file gambar di IMG_DIR yang tidak lagi dirujuk note mana pun."""
    if not os.path.isdir(IMG_DIR):
        return
    refs = collect_referenced_images()
    for name in os.listdir(IMG_DIR):
        if name in (".", ".."):
            continue
        if name not in refs:
            try:
                os.remove(os.path.join(IMG_DIR, name))
            except OSError:
                pass


def list_notes():
    os.makedirs(NOTES_DIR, exist_ok=True)
    out = []
    for fn in os.listdir(NOTES_DIR):
        if not fn.endswith(".txt"):
            continue
        nid = fn[:-4]
        if not ID_RE.match(nid):
            continue
        d = read_note(nid)
        if d is None:
            continue
        out.append({"id": nid, "title": d["title"]})
    out.sort(key=lambda x: x["id"])
    return out


class H(BaseHTTPRequestHandler):
    timeout = 10  # detik; tutup koneksi lambat (slowloris) agar thread tidak macet
    disable_nagle_algorithm = True

    def log_message(self, *a):
        pass

    def _read_body(self):
        # Baca body dengan aman: panjang dibatasi & timeout diterapkan.
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None, -1
        if n < 0:
            return None, -1
        try:
            return self.rfile.read(n), n
        except (socket.timeout, TimeoutError):
            return None, -1

    def _send(self, code, body=b"", ctype="text/plain"):
        if ctype.startswith("text/") or ctype == "application/json":
            ctype += "; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send(200, open(os.path.join(HERE, "index.html"), "rb").read(), "text/html")
        elif path == "/favicon.png":
            fp = os.path.join(HERE, "favicon.png")
            if os.path.isfile(fp):
                self._send(200, open(fp, "rb").read(), "image/png")
            else:
                self._send(404)
        elif path == "/api/notes":
            self._send(200, json.dumps({"notes": list_notes()}).encode(), "application/json")
        elif path.startswith("/api/notes/"):
            nid = path[len("/api/notes/"):]
            if not ID_RE.match(nid):
                self._send(400, b"bad id"); return
            d = read_note(nid)
            if d is None:
                self._send(404); return
            self._send(200, json.dumps({"id": nid, "title": d["title"], "note": d["body"]}).encode(), "application/json")
        elif path.startswith("/images/"):
            name = os.path.basename(path)
            fp = os.path.join(IMG_DIR, name)
            if name and os.path.isfile(fp) and name not in (".", ".."):
                ctype = STATIC_CTYPE.get(os.path.splitext(name)[1].lower(), "application/octet-stream")
                self._send(200, open(fp, "rb").read(), ctype)
            else:
                self._send(404)
        else:
            self._send(404)

    def do_POST(self):
        data, n = self._read_body()
        path = self.path.split("?")[0]
        if data is None:
            self._send(400, b"bad request"); return
        if path == "/api/notes":
            if n > 64:
                self._send(413, b"too large"); return
            try:
                d = json.loads(data.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._send(400, b"bad json"); return
            title = (d.get("title") or "Tanpa judul").strip()[:MAX_TITLE] or "Tanpa judul"
            os.makedirs(NOTES_DIR, exist_ok=True)
            nid = uuid.uuid4().hex[:12]
            write_note(nid, title, "")
            self._send(200, json.dumps({"id": nid, "title": title}).encode(), "application/json")
        elif path.startswith("/api/notes/") and self.path.endswith("/title"):
            # POST /api/notes/<id>/title — body = plain text title
            nid = path[len("/api/notes/"):-len("/title")]
            if not ID_RE.match(nid):
                self._send(400, b"bad id"); return
            if n > 256:
                self._send(413, b"too large"); return
            d = read_note(nid)
            if d is None:
                self._send(404); return
            new_title = data.decode("utf-8").strip()[:MAX_TITLE]
            write_note(nid, new_title, d["body"])
            self._send(200, json.dumps({"title": new_title}).encode(), "application/json")
        elif path.startswith("/api/notes/"):
            nid = path[len("/api/notes/"):]
            if not ID_RE.match(nid):
                self._send(400, b"bad id"); return
            if n > MAX_NOTE:
                self._send(413, b"too large"); return
            os.makedirs(NOTES_DIR, exist_ok=True)
            d = read_note(nid)
            if d is None:
                self._send(404); return
            try:
                payload = json.loads(data.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._send(400, b"bad json"); return
            body = payload.get("note", "")
            title = (payload.get("title") or d["title"])[:MAX_TITLE]
            write_note(nid, title, body)
            self._send(200)
        elif path == "/api/upload":
            if n > MAX_UPLOAD:
                self._send(413, b"too large"); return
            ext, mime = sniff(data, self.headers.get("Content-Type"))
            if ext is None:
                self._send(400, b"invalid image"); return
            os.makedirs(IMG_DIR, exist_ok=True)
            fname = uuid.uuid4().hex + ext
            with open(os.path.join(IMG_DIR, fname), "wb") as f:
                f.write(data)
            self._send(200, json.dumps({"url": "/images/" + fname}).encode(), "application/json")
        else:
            self._send(404)

    def do_DELETE(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/notes/"):
            nid = path[len("/api/notes/"):]
            if not ID_RE.match(nid):
                self._send(400, b"bad id"); return
            fp = os.path.join(NOTES_DIR, nid + ".txt")
            if os.path.isfile(fp):
                os.remove(fp)
                gc_images()
                self._send(200)
            else:
                self._send(404)
        else:
            self._send(404)


ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
