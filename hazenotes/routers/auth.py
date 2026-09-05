"""Authentication: register, login (rate limited), logout, anonymous probe."""
import asyncio
import re
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import config, db
from ..security import check_password, cookie_secure, get_current_user, hash_password

router = APIRouter()

# ponytail: per-process limiter; fine for single-instance deploys.
# Move to Redis/slowapi when running multiple workers.
_username_re = re.compile(r'^[A-Za-z0-9_-]{3,32}$')
_failed_logins = {}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else 'unknown'


def _rate_limited(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _failed_logins.get(ip, []) if now - t < config.LOGIN_RATE_WINDOW]
    _failed_logins[ip] = recent
    return len(recent) >= config.LOGIN_RATE_LIMIT


@router.post('/api/auth/login')
async def handle_login(request: Request):
    ip = _client_ip(request)
    if _rate_limited(ip):
        return JSONResponse({'error': 'Too many attempts. Try again later.'}, status_code=429)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Invalid request body'}, status_code=400)

    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))
    if not username or not password:
        return JSONResponse({'error': 'Invalid username or password'}, status_code=401)

    user = await asyncio.to_thread(db.get_user, username)
    ok, upgraded = check_password(user['password'], password) if user else (False, None)
    if not ok:
        _failed_logins.setdefault(ip, []).append(time.time())
        return JSONResponse({'error': 'Invalid username or password'}, status_code=401)

    if upgraded:  # transparent upgrade of legacy unsalted SHA-256 hashes
        await asyncio.to_thread(db.update_user_password, username, upgraded)

    token = await asyncio.to_thread(db.create_session, username)
    response = JSONResponse({'status': 'ok', 'username': username})
    response.set_cookie('session', token, httponly=True, samesite='lax',
                        secure=cookie_secure(request), path='/')
    return response


@router.get('/api/auth/login')
async def handle_anonymous_login():
    if config.AUTH_REQUIRED:
        return JSONResponse({'error': 'Authentication required'}, status_code=401)
    return JSONResponse({'status': 'ok', 'username': 'anonymous'})


@router.post('/api/auth/register')
async def handle_register(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Invalid request body'}, status_code=400)

    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))

    if not _username_re.fullmatch(username):
        return JSONResponse({'error': 'Username must be 3-32 characters (letters, numbers, _ or -)'}, status_code=400)
    if not password or len(password) < 6:
        return JSONResponse({'error': 'Password must be at least 6 characters'}, status_code=400)
    if len(password) > 128:
        return JSONResponse({'error': 'Password must be at most 128 characters'}, status_code=400)

    pwd_hash = await asyncio.to_thread(hash_password, password)
    success = await asyncio.to_thread(db.create_user, username, pwd_hash)
    if not success:
        return JSONResponse({'error': 'Username already exists'}, status_code=400)

    return JSONResponse({'status': 'ok', 'message': 'Account created successfully'})


@router.post('/api/auth/change-username')
async def handle_change_username(request: Request):
    user = await get_current_user(request)
    if not user or user == 'anonymous':
        return JSONResponse({'error': 'Authentication required'}, status_code=401)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Invalid request body'}, status_code=400)

    new_username = str(data.get('new_username', '')).strip()
    current_password = str(data.get('current_password', ''))

    if not _username_re.fullmatch(new_username):
        return JSONResponse({'error': 'Username must be 3-32 characters (letters, numbers, _ or -)'}, status_code=400)

    row = await asyncio.to_thread(db.get_user, user)
    ok, _ = check_password(row['password'], current_password) if row else (False, None)
    if not ok:
        return JSONResponse({'error': 'Current password is incorrect'}, status_code=403)

    if new_username != user:
        renamed = await asyncio.to_thread(db.rename_user, user, new_username)
        if not renamed:
            return JSONResponse({'error': 'Username already exists'}, status_code=400)
    return JSONResponse({'status': 'ok', 'username': new_username})


@router.post('/api/auth/change-password')
async def handle_change_password(request: Request):
    user = await get_current_user(request)
    if not user or user == 'anonymous':
        return JSONResponse({'error': 'Authentication required'}, status_code=401)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Invalid request body'}, status_code=400)

    current_password = str(data.get('current_password', ''))
    new_password = str(data.get('new_password', ''))
    if not new_password or len(new_password) < 6:
        return JSONResponse({'error': 'Password must be at least 6 characters'}, status_code=400)
    if len(new_password) > 128:
        return JSONResponse({'error': 'Password must be at most 128 characters'}, status_code=400)

    row = await asyncio.to_thread(db.get_user, user)
    ok, _ = check_password(row['password'], current_password) if row else (False, None)
    if not ok:
        return JSONResponse({'error': 'Current password is incorrect'}, status_code=403)

    pwd_hash = await asyncio.to_thread(hash_password, new_password)
    await asyncio.to_thread(db.update_user_password, user, pwd_hash)
    return JSONResponse({'status': 'ok'})


@router.post('/api/auth/logout')
async def handle_logout(request: Request):
    token = request.cookies.get('session')
    if token:
        await asyncio.to_thread(db.delete_session, token)
    response = JSONResponse({'status': 'ok'})
    response.delete_cookie('session', path='/')
    return response
