# Deployment and operations

Everything needed to run HazeNotes somewhere real: TLS in front of it, backups, upgrades and monitoring. The install commands themselves are in the [README](../README.md); the user-facing behaviour is in the [usage guide](USAGE.md).

## Requirements and sizing

- **Python 3.10+** (the Docker image ships 3.12), or **Docker** for the container path.
- **TLS** in front of the app for any non-loopback deployment — see the checklist below.

Rough sizing, as guidance rather than a benchmark: a small VPS (1 vCPU, 512 MB RAM) is comfortable for a handful of accounts; the app is one Python process over a single SQLite file and idle load is near zero. Disk is the thing to watch — a note can reach 1 MB of text and every uploaded image takes up to 20 MB and is never resized, so give the storage volume room to grow and back it up.

## LAN access

Both the Compose stack and the "Docker (build and run)" command in the [README](../README.md) publish port `8123` on every interface, and the manual uvicorn command binds `0.0.0.0`, so another machine on the same network can reach the app out of the box:

1. Find the host's address: `hostname -I` (or `ip -4 addr show scope global`).
2. Open the port in the host firewall if it filters inbound traffic — `sudo ufw allow 8123/tcp`, or `sudo firewall-cmd --add-port=8123/tcp --permanent && sudo firewall-cmd --reload` on firewalld.
3. Browse to `http://<host-ip>:8123` from the other machine and register an account there.

On a LAN the traffic is plain HTTP: passwords are not encrypted on the wire and the session cookie carries no `Secure` flag. That is acceptable on a network you control; anything else belongs behind the TLS proxy described below. Note also that registration is open, so anyone who can reach the port can create an account unless you block `POST /api/auth/register` at the proxy.

## Before you expose it (checklist)

A default install is already reachable from the LAN (see above). The list below is what changes when the instance should be reachable from the internet.

1. **Terminate TLS at a reverse proxy.** Session cookies only get the `Secure` flag when the request arrives over HTTPS (directly or via `X-Forwarded-Proto`). The bundled container already runs uvicorn with `--proxy-headers`.
2. **Publish the app port to the proxy only.** The image ships `FORWARDED_ALLOW_IPS=*` so cloud load balancers work out of the box; on a plain LAN that also lets any client spoof `X-Forwarded-For` / `X-Forwarded-Proto` and influence the login limiter and the cookie flags. Set `FORWARDED_ALLOW_IPS` to your proxy's address (`127.0.0.1` when the proxy runs on the same host) and publish the port to that proxy only — `-p 127.0.0.1:8123:8123` instead of `-p 8123:8123`.
3. **Run exactly one worker.** SQLite WAL, the in-process login limiter, and the in-memory WebSocket manager all assume a single process. Do not enable uvicorn `--workers` or multi-worker gunicorn; scale vertically instead.
4. **Mount and watch storage.** `/app/storage` is the only mutable path. Disk usage grows with uploads (up to `NOTEPAD_MAX_UPLOAD_BYTES` each) and note bodies; alert on free space.
5. **Back up before every upgrade.** See [Backup and restore](#backup-and-restore).
6. **Probe liveness.** `GET /health` is cheap and does not touch SQLite.
7. **Decide about registration.** `POST /api/auth/register` is open and not rate limited; block or filter it at the proxy if the instance is invite-only.

## Container platforms (Docker cloud)

The image is self-contained, so a platform that builds a Dockerfile (Railway, Render, Fly.io, Cloud Run, a plain Kubernetes or Swarm cluster) can run it as-is:

- **Environment** — set the `NOTEPAD_*` variables in the platform dashboard; the platform's own `$PORT` is picked up automatically ([configuration table](../README.md#configuration-env)).
- **Persistence** — attach a volume or disk at `/app/storage`. Without one, every deploy starts from an empty database. On platforms without volumes, point `NOTEPAD_DATA_DIR` and `NOTEPAD_IMAGES_DIR` at a mounted path instead.
- **One replica** — never scale past a single instance: SQLite WAL, the in-process login limiter and the WebSocket manager all assume one process. A rolling deploy briefly runs two containers against the same volume, so take a [backup](#backup-and-restore) before shipping.
- **TLS** — the platform's load balancer usually terminates HTTPS, so `X-Forwarded-Proto` is what gives the session cookie its `Secure` flag. That header is only trusted from an address inside `FORWARDED_ALLOW_IPS`, which defaults to `*` for exactly this case.
- **Health probe** — point the platform's probe at `/health`; the image also ships a `HEALTHCHECK`.

## Reverse proxy

### nginx

TLS plus the WebSocket upgrade that real-time collaboration needs:

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

### Caddy

Caddy handles TLS, forwarded headers, and WebSocket upgrades with a single directive:

```caddyfile
notes.example.com {
    reverse_proxy 127.0.0.1:8123
}
```

## Run it as a service (systemd)

Docker: `--restart unless-stopped` (or `restart:` in compose) is already enough. For a manual install, a unit file such as `/etc/systemd/system/hazenotes.service` (adjust the paths to your checkout) keeps the app alive:

```ini
[Unit]
Description=HazeNotes
After=network.target

[Service]
User=hazenotes
WorkingDirectory=/opt/HazeNotes
EnvironmentFile=/opt/HazeNotes/.env
ExecStart=/opt/HazeNotes/.venv/bin/uvicorn hazenotes.main:app --host 127.0.0.1 --port 8123 --proxy-headers
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then `sudo systemctl enable --now hazenotes`. Binding to `127.0.0.1` keeps the app reachable only by the proxy on the same host, and because uvicorn's default `--forwarded-allow-ips` is `127.0.0.1`, only that proxy may set the forwarded headers.

`EnvironmentFile` points at your `.env`, so the settings listed in the [README](../README.md#configuration-env) apply to the service as well.

## Backup and restore

WAL mode means the database file alone is not a consistent snapshot while the app runs. Two safe options:

**Stop, copy, start** — the simplest and enough for a home server:

```bash
docker stop hazenotes
docker cp hazenotes:/app/storage "./hazenotes-backup-$(date +%F)"
docker start hazenotes
```

**Without stopping anything** — use SQLite's online backup API, which is safe while the app serves traffic:

```bash
docker exec hazenotes python -c "import sqlite3; sqlite3.connect('/app/storage/data/notepad.db').backup(sqlite3.connect('/tmp/backup.db'))"
docker cp hazenotes:/tmp/backup.db "./notepad-$(date +%F).db"
docker cp hazenotes:/app/storage/images "./images-$(date +%F)"
```

Without Docker, the same one-liner works on `storage/data/notepad.db`; images are write-once with random file names, so a plain copy or `rsync` of `storage/images` is enough.

**Restore:** stop the container, replace `notepad.db` and the `images` directory inside the volume, start it again. Startup is idempotent — schema creation uses `CREATE TABLE IF NOT EXISTS` and the legacy JSON import only runs against empty tables.

## Health and logs

- `GET /health` → `{"status": "ok"}`, liveness only: it does not read or write SQLite.
- Application logs go to stdout at INFO level (`%(asctime)s %(levelname)s %(name)s: %(message)s`); collect them with `docker logs` or journald.
- The image ships a `HEALTHCHECK` that calls `/health` on the port the app listens on, so `docker ps` reports `healthy` and container platforms can reuse it:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8123') + '/health')"
```

- Expired sessions are purged once, at startup; until the next restart the expired rows stay in the `sessions` table but are rejected on access.

## Upgrades

1. Take a backup (above).
2. Build/pull the new image or update the checkout plus `pip install -r requirements.txt`.
3. Restart. Schema migrations are additive and idempotent; the legacy JSON import only touches an empty database.

Sessions live in the database, so a restart does not log users out. Template edits need a restart (templates are cached at first use).

Back to the [README](../README.md) · [Usage](USAGE.md) · [API](API.md) · [Security](SECURITY.md) · [Development](DEVELOPMENT.md)

