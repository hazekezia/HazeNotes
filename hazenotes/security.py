"""Password hashing, session-cookie auth helpers, and permission checks."""
import asyncio
import hashlib
import hmac
import secrets
from typing import Optional, Tuple

from fastapi import Request

from . import config

PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    """PBKDF2-SHA256, salted. Format: pbkdf2_sha256$<iterations>$<salt-hex>$<hash-hex>"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PBKDF2_ITERATIONS)
    return f'pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}'


def check_password(stored: str, password: str) -> Tuple[bool, Optional[str]]:
    """
    Verify a password against its stored hash.

    Returns (ok, upgraded_hash). upgraded_hash is set when a legacy unsalted
    SHA-256 hash (pre-2.0 accounts) matched and should be persisted.
    """
    if stored.startswith('pbkdf2_sha256$'):
        try:
            _, iters, salt_hex, hash_hex = stored.split('$')
            dk = hashlib.pbkdf2_hmac(
                'sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), int(iters)
            )
            return hmac.compare_digest(dk.hex(), hash_hex), None
        except (ValueError, TypeError):
            return False, None
    if len(stored) == 64:  # legacy: bare unsalted SHA-256 hex digest
        legacy = hashlib.sha256(password.encode('utf-8')).hexdigest()
        if hmac.compare_digest(legacy, stored):
            return True, hash_password(password)
    return False, None


def unusable_password() -> str:
    """Hash for accounts that must exist (FK) but must never be logged into."""
    return hash_password(secrets.token_hex(16))


def cookie_secure(request: Request) -> bool:
    return (
        request.url.scheme == 'https'
        or request.headers.get('x-forwarded-proto', '').lower() == 'https'
    )


async def get_current_user(request: Request) -> Optional[str]:
    """Session-cookie auth. Returns the username, 'anonymous' if auth is off, or None.

    Accepts Request or WebSocket (both expose .cookies).
    """
    if not config.AUTH_REQUIRED:
        return 'anonymous'
    token = request.cookies.get('session')
    if not token:
        return None
    from . import db  # local import: db imports this module for hashing

    return await asyncio.to_thread(db.get_session_user, token)


def can_view(user: Optional[str], note: dict) -> bool:
    return (
        not config.AUTH_REQUIRED
        or user == note['owner']
        or user in note['collaborators']
    )


def can_edit(user: Optional[str], note: dict) -> bool:
    return (
        not config.AUTH_REQUIRED
        or user == note['owner']
        or note['collaborators'].get(user) == 'edit'
    )
