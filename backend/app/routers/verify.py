"""Public receipt verification. No login: the snapshot holds no copy, claim text, comments or emails."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import limits, receipts
from ..db import get_db

router = APIRouter(prefix="/api", tags=["verify"])


@router.get("/verify/{code}", dependencies=[Depends(limits.throttle("verify", "BP_RATE_VERIFY", "60/60"))])
def verify_receipt(code: str, digest: str | None = None, sha256: str | None = None, db: Session = Depends(get_db)):
    if len(code) > 40:
        raise HTTPException(404, "No receipt with this code")
    out = receipts.verify(db, code, digest, sha256)
    if not out["found"]:
        raise HTTPException(404, "No receipt with this code")
    return out
