from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, limits
from ..db import User, get_db
from ..security import current_user, hash_password, make_token, verify_password

router = APIRouter(prefix="/api")
_DUMMY = hash_password("not-a-real-password", "0000000000000000")


class Login(BaseModel):
    email: str
    password: str


def ser_user(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "team": u.team}


@router.post("/auth/login")
def login(body: Login, request: Request, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    limits.login_blocked(request, email)
    u = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    # Same work whether or not the account exists, so response time does not reveal which emails are registered.
    ok = verify_password(body.password, u.pw_hash if u else _DUMMY)
    if not u or not ok:
        limits.login_failed(request, email)
        raise HTTPException(401, "Wrong email or password")
    return {"token": make_token(u), "user": ser_user(u)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return ser_user(user)


@router.get("/demo-users")
def demo_users(db: Session = Depends(get_db)):
    """Lists seeded demo accounts for one-click demo sign-in. Disabled when BP_SEED=0 (production)."""
    if not config.seed_enabled():
        return []
    return [ser_user(u) for u in db.execute(select(User).order_by(User.id)).scalars()]
