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

ENV NOTEPAD_DATA_DIR=/app/storage/data \
    NOTEPAD_IMAGES_DIR=/app/storage/images \
    NOTEPAD_HOST=0.0.0.0 \
    NOTEPAD_PORT=8123

VOLUME /app/storage
EXPOSE 8123

# --proxy-headers so secure cookies work behind a TLS-terminating reverse proxy
CMD ["uvicorn", "hazenotes.main:app", "--host", "0.0.0.0", "--port", "8123", "--proxy-headers", "--forwarded-allow-ips", "*"]
