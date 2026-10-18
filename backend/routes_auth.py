"""Login + current-user routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api_schemas import LoginRequest, TokenResponse, UserOut
from backend.auth import create_access_token, get_current_user, verify_password
from backend.db import get_db
from backend.models_db import User

router = APIRouter(prefix="/api/auth")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        # Same message either way -- don't leak which part was wrong.
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token = create_access_token(user)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
