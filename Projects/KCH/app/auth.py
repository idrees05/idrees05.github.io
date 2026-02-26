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
