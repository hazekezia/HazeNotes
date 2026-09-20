"""Environment configuration. Parsed once at import. See .env.example."""
import os

# A .env next to the working directory is a convenience for direct (non-Docker)
# runs; containers and cloud platforms inject real environment variables instead.
# utf-8-sig tolerates a BOM, which otherwise silently swallows the first key, and
# override=False keeps variables that are already set authoritative.
try:
    from dotenv import load_dotenv
except ImportError:  # optional; listed in requirements.txt
    pass
else:
    load_dotenv(os.path.join(os.getcwd(), '.env'), encoding='utf-8-sig')

AUTH_REQUIRED = os.getenv('NOTEPAD_AUTH', 'TRUE').upper() == 'TRUE'
HOST = os.getenv('NOTEPAD_HOST', '0.0.0.0')
# NOTEPAD_PORT wins; the bare PORT covers container platforms (Railway, Render,
# Fly.io, Cloud Run) that inject the port the app is expected to listen on.
PORT = int(os.getenv('NOTEPAD_PORT') or os.getenv('PORT') or '8123')

DATA_DIR = os.getenv('NOTEPAD_DATA_DIR', './storage/data')
IMAGES_DIR = os.getenv('NOTEPAD_IMAGES_DIR', './storage/images')
DB_PATH = os.path.join(DATA_DIR, 'notepad.db')

SESSION_TTL_HOURS = int(os.getenv('NOTEPAD_SESSION_TTL_HOURS', '168'))
MAX_UPLOAD_BYTES = int(os.getenv('NOTEPAD_MAX_UPLOAD_BYTES', str(20 * 1024 * 1024)))
MAX_NOTE_BYTES = 1_000_000
MAX_TITLE_LEN = 120

LOGIN_RATE_LIMIT = int(os.getenv('NOTEPAD_LOGIN_RATE_LIMIT', '10'))
LOGIN_RATE_WINDOW = int(os.getenv('NOTEPAD_LOGIN_RATE_WINDOW', '300'))
