import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import Cookie, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
ACCESS_CODE = os.getenv("ACCESS_CODE", "changeme")
ADMIN_CODE = os.getenv("ADMIN_CODE", "adminchangeme")

_signer = URLSafeTimedSerializer(SECRET_KEY)


def sign_session(data: dict) -> str:
    return _signer.dumps(data)


def unsign_session(token: str, max_age: int = 86400 * 7) -> Optional[dict]:
    try:
        return _signer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def get_session(request: Request) -> Optional[dict]:
    token = request.cookies.get("session")
    if not token:
        return None
    return unsign_session(token)


def require_session(request: Request) -> dict:
    session = get_session(request)
    if not session:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return session


def require_admin(request: Request) -> dict:
    session = get_session(request)
    if not session or not session.get("is_admin"):
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return session

import hashlib
import os as _os
import secrets
import string


def generate_password() -> str:
    """Generate a readable 3-part password, e.g. Abc1-Xyz2-Def3."""
    alph = string.ascii_letters + string.digits
    return '-'.join(''.join(secrets.choice(alph) for _ in range(5)) for _ in range(3))


def hash_password(password: str) -> str:
    salt = _os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100_000)
    return f"{salt.hex()}:{key.hex()}"


def verify_password(stored: str, password: str) -> bool:
    try:
        salt_hex, key_hex = stored.split(':')
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt_hex), 100_000)
        return secrets.compare_digest(key.hex(), key_hex)
    except Exception:
        return False


def require_user_session(request: Request) -> dict:
    """Allow logged-in regular users (user_id in session)."""
    session = get_session(request)
    if not session or not session.get('user_id'):
        raise HTTPException(status_code=303, headers={"Location": "/user/login"})
    return session


def require_any_session(request: Request) -> dict:
    """Allow either an admin session or a logged-in user session."""
    session = get_session(request)
    if not session:
        raise HTTPException(status_code=303, headers={"Location": "/user/login"})
    if session.get('is_admin') or session.get('user_id'):
        return session
    raise HTTPException(status_code=303, headers={"Location": "/user/login"})
