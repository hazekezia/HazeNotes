"""Environment configuration. Parsed once at import. See .env.example."""
import os

AUTH_REQUIRED = os.getenv('NOTEPAD_AUTH', 'TRUE').upper() == 'TRUE'
HOST = os.getenv('NOTEPAD_HOST', '0.0.0.0')
PORT = int(os.getenv('NOTEPAD_PORT', '8123'))

DATA_DIR = os.getenv('NOTEPAD_DATA_DIR', './storage/data')
IMAGES_DIR = os.getenv('NOTEPAD_IMAGES_DIR', './storage/images')
DB_PATH = os.path.join(DATA_DIR, 'notepad.db')

SESSION_TTL_HOURS = int(os.getenv('NOTEPAD_SESSION_TTL_HOURS', '168'))
MAX_UPLOAD_BYTES = int(os.getenv('NOTEPAD_MAX_UPLOAD_BYTES', str(20 * 1024 * 1024)))
MAX_NOTE_BYTES = 1_000_000
MAX_TITLE_LEN = 120

LOGIN_RATE_LIMIT = int(os.getenv('NOTEPAD_LOGIN_RATE_LIMIT', '10'))
LOGIN_RATE_WINDOW = int(os.getenv('NOTEPAD_LOGIN_RATE_WINDOW', '300'))
