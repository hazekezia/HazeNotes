"""HazeNotes API tests. Assert-based, no test framework required.

Run either way:
    python tests/test_api.py
    pytest tests          (if pytest is installed)
"""
import hashlib
import os
import sys
import tempfile
from datetime import datetime, timedelta

# Isolate storage BEFORE importing hazenotes (config reads env at import time)
_TMP = tempfile.mkdtemp(prefix='hazetest-')
os.environ['NOTEPAD_DATA_DIR'] = os.path.join(_TMP, 'data')
os.environ['NOTEPAD_IMAGES_DIR'] = os.path.join(_TMP, 'images')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from hazenotes import __version__, config, db
from hazenotes.main import app

CHECKS = []


def check(name, cond):
    CHECKS.append((name, bool(cond)))
    print(('PASS' if cond else 'FAIL'), name)


PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
WEBP = b'RIFF\x24\x00\x00\x00WEBPVP8 ' + b'\x00' * 16


def run():
    with TestClient(app) as client:
        # --- health, headers, login page ---
        r = client.get('/health')
        check('health ok', r.status_code == 200 and r.json()['status'] == 'ok')
        r = client.get('/')
        check('anonymous gets login page', r.status_code == 200 and 'Sign In' in r.text)
        check('security headers', r.headers.get('x-content-type-options') == 'nosniff'
              and r.headers.get('x-frame-options') == 'DENY')

        # --- register validation ---
        r = client.post('/api/auth/register', json={'username': 'ab', 'password': 'secret1'})
        check('short username rejected', r.status_code == 400)
        r = client.post('/api/auth/register', json={'username': 'bad user!', 'password': 'secret1'})
        check('bad-charset username rejected', r.status_code == 400)
        r = client.post('/api/auth/register', json={'username': 'alice</script>', 'password': 'secret1'})
        check('xss username rejected', r.status_code == 400)
        r = client.post('/api/auth/register', json={'username': 'alice', 'password': 'secret1'})
        check('register alice', r.status_code == 200)
        r = client.post('/api/auth/register', json={'username': 'alice', 'password': 'secret2'})
        check('duplicate register rejected', r.status_code == 400)

        # --- login ---
        r = client.post('/api/auth/login', json={'username': 'alice', 'password': 'wrong'})
        check('wrong password 401', r.status_code == 401)
        r = client.post('/api/auth/login', json={'username': 'alice', 'password': 'secret1'})
        token = client.cookies.get('session')
        check('login alice', r.status_code == 200 and token)

        # --- notes CRUD ---
        r = client.post('/api/notes', json={})
        check('create note', r.status_code == 200 and r.json().get('id'))
        note_id = r.json()['id']
        r = client.get('/api/notes')
        check('list notes', r.status_code == 200 and any(n['id'] == note_id for n in r.json()['notes']))
        r = client.post(f'/api/notes/{note_id}', json={'title': 'Hello', 'note': '<p>world</p>'})
        check('update note', r.status_code == 200)
        r = client.get(f'/api/notes/{note_id}')
        check('get note detail', r.status_code == 200 and r.json()['note'] == '<p>world</p>')
        r = client.post(f'/api/notes/{note_id}', json={'title': 'x' * 500})
        check('oversized title rejected', r.status_code == 400)
        r = client.post(f'/api/notes/{note_id}', json={'note': 'x' * (config.MAX_NOTE_BYTES + 1)})
        check('oversized content rejected', r.status_code == 413)

        # --- editor page for logged-in user (placeholders resolved) ---
        r = client.get('/')
        check('editor page rendered', 'CURRENT_USER_PLACEHOLDER_' not in r.text
              and '[LOGOUT_BUTTON_PLACEHOLDER]' not in r.text)
        check('settings modal rendered', 'settingsModal' in r.text
              and f'v{__version__}' in r.text and 'AUTH_USER_PLACEHOLDER_' not in r.text
              and 'APP_VERSION_PLACEHOLDER_' not in r.text)

        # --- account settings: change username / password ---
        r = client.post('/api/auth/change-username', json={'new_username': 'alice2', 'current_password': 'wrong'})
        check('change-username wrong password rejected', r.status_code == 403)
        r = client.post('/api/auth/change-username', json={'new_username': 'bad name!', 'current_password': 'secret1'})
        check('change-username bad charset rejected', r.status_code == 400)
        r = client.post('/api/auth/change-username', json={'new_username': 'anonymous', 'current_password': 'secret1'})
        check('change-username duplicate rejected', r.status_code == 400)
        r = client.post('/api/auth/change-username', json={'new_username': 'alice2', 'current_password': 'secret1'})
        check('change-username ok', r.status_code == 200 and r.json()['username'] == 'alice2')
        check('notes carried to renamed user', db.get_note(note_id)['owner'] == 'alice2')
        check('session survives rename', db.get_session_user(token) == 'alice2')
        r = TestClient(app).post('/api/auth/change-username', json={'new_username': 'x', 'current_password': 'y'})
        check('change-username anonymous blocked', r.status_code == 401)
        r = client.post('/api/auth/change-password', json={'current_password': 'wrong', 'new_password': 'secret9'})
        check('change-password wrong current rejected', r.status_code == 403)
        r = client.post('/api/auth/change-password', json={'current_password': 'secret1', 'new_password': 'short'})
        check('change-password too short rejected', r.status_code == 400)
        r = client.post('/api/auth/change-password', json={'current_password': 'secret1', 'new_password': 'secret9'})
        check('change-password ok', r.status_code == 200)
        fresh = TestClient(app)
        r = fresh.post('/api/auth/login', json={'username': 'alice2', 'password': 'secret9'})
        check('login with new credentials', r.status_code == 200)

        # --- sharing / permissions ---
        r = client.post('/api/auth/register', json={'username': 'bob', 'password': 'secret2'})
        check('register bob', r.status_code == 200)
        r = client.post(f'/api/notes/{note_id}/share', json={'username': 'bob', 'role': 'read'})
        check('share with bob', r.status_code == 200)
        bob = TestClient(app)
        bob.post('/api/auth/login', json={'username': 'bob', 'password': 'secret2'})
        r = bob.get(f'/api/notes/{note_id}')
        check('read-only collab can view', r.status_code == 200)
        r = bob.post(f'/api/notes/{note_id}', json={'note': 'hacked'})
        check('read-only collab cannot edit', r.status_code == 403)
        stranger = TestClient(app)
        r = stranger.get(f'/api/notes/{note_id}')
        check('stranger blocked (401)', r.status_code == 401)

        # --- uploads ---
        r = stranger.post('/api/upload', content=PNG)
        check('anonymous upload rejected', r.status_code == 401)
        r = client.post('/api/upload', content=PNG)
        check('png upload ok', r.status_code == 200 and r.json()['url'].endswith('.png'))
        url = r.json()['url']
        r = client.get(url)
        check('uploaded image served', r.status_code == 200)
        r = client.post('/api/upload', content=WEBP)
        check('webp upload ok', r.status_code == 200 and r.json()['url'].endswith('.webp'))
        r = client.post('/api/upload', content=b'not-an-image-at-all')
        check('garbage upload rejected', r.status_code == 400)

        # --- websocket auth ---
        try:
            with client.websocket_connect(f'/ws/notes/{note_id}', cookies={'session': token}):
                pass
            check('ws with session ok', True)
        except Exception as e:
            check('ws with session ok', False)
            print('   ws error:', e)
        try:
            with stranger.websocket_connect(f'/ws/notes/{note_id}'):
                pass
            check('ws without session rejected', False)
        except Exception:
            check('ws without session rejected', True)

        # --- session expiry ---
        exp_token = db.create_session('alice2')
        check('fresh session valid', db.get_session_user(exp_token) == 'alice2')
        conn = db.get_db_connection()
        conn.execute('UPDATE sessions SET expires_at = ? WHERE token = ?',
                     ((datetime.now() - timedelta(hours=1)).isoformat(), exp_token))
        conn.commit()
        check('expired session invalid', db.get_session_user(exp_token) is None)

        # --- legacy password upgrade on login ---
        legacy = hashlib.sha256(b'oldpass').hexdigest()
        db.create_user('carol', legacy)
        carol = TestClient(app)
        r = carol.post('/api/auth/login', json={'username': 'carol', 'password': 'oldpass'})
        check('legacy hash login ok', r.status_code == 200)
        check('legacy hash upgraded to pbkdf2',
              db.get_user('carol')['password'].startswith('pbkdf2_sha256$'))

    failed = [n for n, ok in CHECKS if not ok]
    print(f'\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed')
    if failed:
        print('FAILED:', failed)
        sys.exit(1)


if __name__ == '__main__':
    run()
