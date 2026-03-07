import os
import time
from collections import defaultdict
from typing import Optional

from dotenv import load_dotenv
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

_signer = URLSafeTimedSerializer(SECRET_KEY)
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Rate limiting: {ip: [timestamp, ...]}
_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = 5       # max failures
_RATE_WINDOW = 300    # seconds (5 min)


# ── Password helpers ─────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# ── Session helpers ───────────────────────────────────────────────────────────

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


# ── Route guards ──────────────────────────────────────────────────────────────

def require_session(request: Request) -> dict:
    session = get_session(request)
    if not session:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return session


def require_admin(request: Request) -> dict:
    session = get_session(request)
    if not session:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    if not session.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return session


# ── Rate limiter ──────────────────────────────────────────────────────────────

def is_rate_limited(ip: str) -> bool:
    now = time.time()
    attempts = _login_attempts[ip]
    # Prune old attempts
    _login_attempts[ip] = [t for t in attempts if now - t < _RATE_WINDOW]
    return len(_login_attempts[ip]) >= _RATE_LIMIT


def record_failed_login(ip: str) -> None:
    _login_attempts[ip].append(time.time())


def clear_login_attempts(ip: str) -> None:
    _login_attempts.pop(ip, None)
