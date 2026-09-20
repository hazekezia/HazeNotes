FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY hazenotes/ ./hazenotes/

# Non-root user + writable storage volume
RUN useradd --system --no-create-home app \
    && mkdir -p /app/storage/data /app/storage/images \
    && chown -R app:app /app/storage
USER app

# PORT is injected by most container platforms (Railway, Render, Fly.io, Cloud
# Run); without one the app falls back to NOTEPAD_PORT, then 8123.
ENV NOTEPAD_DATA_DIR=/app/storage/data \
    NOTEPAD_IMAGES_DIR=/app/storage/images \
    NOTEPAD_HOST=0.0.0.0 \
    PORT=8123 \
    FORWARDED_ALLOW_IPS=*

VOLUME /app/storage
EXPOSE 8123

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8123') + '/health')"

# --proxy-headers so secure cookies work behind a TLS-terminating reverse proxy.
# --forwarded-allow-ips defaults to * so cloud load balancers work out of the box;
# set FORWARDED_ALLOW_IPS to your proxy address to stop clients spoofing
# X-Forwarded-For (see docs/DEPLOYMENT.md).
CMD ["sh", "-c", "uvicorn hazenotes.main:app --host 0.0.0.0 --port ${NOTEPAD_PORT:-$PORT} --proxy-headers --forwarded-allow-ips ${FORWARDED_ALLOW_IPS}"]
