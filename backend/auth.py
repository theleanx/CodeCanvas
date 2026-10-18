"""
Password hashing, JWT issuance/verification, and the FastAPI dependencies
that gate access to the API.

Deliberately simple for what this is -- a single-tenant internal tool, not
a multi-tenant SaaS: email+password, one role per user, a long-lived
bearer token. No refresh tokens, no password reset flow, no SSO. Those are
real gaps for an actual production deploy, not reproduced here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.config import JWT_ALGORITHM, JWT_EXPIRES_MINUTES, JWT_SECRET
from backend.db import get_db
from backend.models_db import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired, please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session token.")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated.")
    token = auth_header[len("bearer "):].strip()

    payload = _decode_token(token)
    user = db.get(User, payload.get("sub"))
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists.")
    return user


def require_role(*allowed_roles: str):
    """Dependency factory: raises 403 unless the caller's role is in allowed_roles
    (an 'admin' role always passes, as the operator override)."""

    def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role != "admin" and user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"This action requires one of: {', '.join(allowed_roles)} (you are {user.role}).",
            )
        return user

    return _dependency
