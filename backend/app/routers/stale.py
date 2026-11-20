from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, stale
from ..db import Asset, StaleAlert, User, get_db, utcnow
from ..security import require

router = APIRouter(prefix="/api", tags=["stale"])
ALLOWED = ("manager", "reviewer", "owner")


@router.get("/stale")
def list_alerts(status: str = "open", user: User = Depends(require(*ALLOWED)), db: Session = Depends(get_db)):
    q = select(StaleAlert).order_by(StaleAlert.id.desc())
    if status != "all":
        q = q.where(StaleAlert.status == status)
    rows = db.execute(q).scalars().all()
    assets = {a.id: a for a in db.execute(select(Asset)).scalars()}
    return [stale.serialise(x, assets.get(x.asset_id)) for x in rows]


@router.post("/stale/scan")
def scan_now(user: User = Depends(require(*ALLOWED)), db: Session = Depends(get_db)):
    new = stale.scan(db, user.email, "manual scan")
    return {"new_alerts": len(new), "alerts": [stale.serialise(x) for x in new]}


class Handle(BaseModel):
    note: str = ""


@router.post("/stale/{alert_id}/dismiss")
def dismiss(alert_id: int, b: Handle, user: User = Depends(require(*ALLOWED)), db: Session = Depends(get_db)):
    x = db.get(StaleAlert, alert_id)
    if x is None:
        raise HTTPException(404, "Alert not found")
    if x.status != "open":
        raise HTTPException(409, "Alert is already handled")
    if len(b.note.strip()) < 5:
        raise HTTPException(422, "Say why the asset is still fine (at least a few words)")
    x.status, x.handled_by, x.handled_at, x.handled_note = "dismissed", user.email, utcnow(), b.note.strip()
    audit.log(db, user.email, "stale.dismiss", "asset", x.asset_id, {"alert": x.id, "note": b.note.strip()[:200]})
    db.commit()
    return stale.serialise(x)
