from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import limits, audit, config, receipts, service, storage
from ..db import Asset, AssetVersion, Comment, Finding, User, get_db
from ..security import current_user
from .common import need, ser_asset, ser_claim, ser_comment, ser_finding, ser_run
from ..db import Claim, FactRequest

router = APIRouter(prefix="/api")


def _perms(user: User, a: Asset, db: Session) -> dict:
    is_owner = a.owner_id == user.id
    return {"can_edit": is_owner and a.status != "Approved",
            "can_submit": is_owner and a.status in ("Auto-reviewed", "Changes requested"),
            "can_approve": user.role in ("manager", "reviewer") and a.status == "In review",
            "needs_reviewer": a.risk == "high",
            "can_waive": user.role in ("manager", "reviewer"),
            "can_request_changes": user.role in ("manager", "reviewer") and a.status == "In review"}


@router.get("/assets")
def list_assets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = []
    for a in db.execute(select(Asset).order_by(Asset.updated_at.desc())).scalars():
        if not service.can_view(user, a):
            continue
        run = service.latest_run(db, a)
        row = ser_asset(a)
        row["summary"] = (run.summary if run else {})
        out.append(row)
    return out


@router.post("/assets", dependencies=[Depends(limits.throttle("upload", "BP_RATE_UPLOAD", "30/60"))])
async def create_asset(title: str = Form(...), intent: str = Form(...), channel: str = Form("social"),
                       ai_generated: bool = Form(False), alt_text: str = Form(""), text: str = Form(""),
                       file: UploadFile | None = File(None), user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    if user.role == "owner":
        raise HTTPException(403, "Guideline owners manage rules; they do not submit content")
    data = await limits.read_upload(file) if file is not None and file.filename else None
    a = service.create_asset(db, user, title, intent, channel, ai_generated, alt_text, text=text or None, data=data,
                             mime=(file.content_type if file is not None and file.filename else "text/plain"),
                             filename=(file.filename if file is not None else ""))
    return ser_asset(a)


def _bundle(db: Session, user: User, a: Asset, n: int | None) -> dict:
    versions = db.execute(select(AssetVersion).where(AssetVersion.asset_id == a.id).order_by(AssetVersion.n)).scalars().all()
    v = next((x for x in versions if x.n == n), versions[-1]) if n else versions[-1]
    run = service.latest_run(db, a, v)
    fs = service.findings_of(db, run)
    claims = db.execute(select(Claim).where(Claim.run_id == (run.id if run else -1)).order_by(Claim.start)).scalars().all()
    fact_ids = {c.fact_id for c in claims if c.fact_id} | {i for f in fs for i in (f.citation or {}).get("facts", [])}
    facts = {i: service.fact_evidence(db, i, run) for i in fact_ids}
    reqs = db.execute(select(FactRequest).where(FactRequest.asset_id == a.id).order_by(FactRequest.id)).scalars().all()
    return {"asset": ser_asset(a), "permissions": _perms(user, a, db),
            "facts": {k: v for k, v in facts.items() if v}, "fact_requests": [service.ser_fact_request(r, a) for r in reqs],
            "intent_elements": a.intent_elements or [],
            "versions": [{"n": x.n, "kind": x.kind, "note": x.note, "by": x.created_by, "sha256": x.sha256[:12],
                          "created_at": x.created_at.isoformat(timespec="seconds"), "purged": x.purged} for x in versions],
            "version": {"n": v.n, "kind": v.kind, "text": v.text_clean, "raw_differs": v.text_raw.strip() != v.text_clean.strip(),
                        "purged": v.purged, "is_latest": v.n == versions[-1].n},
            "run": ser_run(run), "findings": [ser_finding(f) for f in fs], "claims": [ser_claim(c) for c in claims]}


@router.get("/assets/{asset_id}")
def get_asset(asset_id: int, n: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _bundle(db, user, service.get_asset(db, user, asset_id), n)


@router.post("/assets/{asset_id}/versions", dependencies=[Depends(limits.throttle("upload", "BP_RATE_UPLOAD", "30/60"))])
async def new_version(asset_id: int, text: str = Form(""), note: str = Form(""), file: UploadFile | None = File(None),
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = service.get_asset(db, user, asset_id)
    if a.status == "Approved":
        pass  # a new version reopens an approved asset
    data = await limits.read_upload(file) if file is not None and file.filename else None
    service.add_version(db, user, a, text=text or None, data=data,
                        mime=(file.content_type if file is not None and file.filename else "text/plain"),
                        filename=(file.filename if file is not None else ""), note=note)
    return _bundle(db, user, a, None)


@router.post("/assets/{asset_id}/rerun")
def rerun(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = service.get_asset(db, user, asset_id)
    if a.status == "Approved":
        raise HTTPException(409, "Approved assets are locked")
    service.rerun(db, user, a)
    return _bundle(db, user, a, None)


@router.get("/assets/{asset_id}/diff")
def diff(asset_id: int, a: int, b: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.diff_versions(db, service.get_asset(db, user, asset_id), a, b)


@router.get("/assets/{asset_id}/preview")
def preview(asset_id: int, n: int | None = None, page: int = 1, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = service.get_asset(db, user, asset_id)
    q = select(AssetVersion).where(AssetVersion.asset_id == a.id)
    v = db.execute((q.where(AssetVersion.n == n) if n else q.order_by(AssetVersion.n.desc())).limit(1)).scalar_one_or_none()
    need(v, "Version")
    if not v.file_path:
        raise HTTPException(404, "No file for this version")
    data = storage.read(v.file_path, db)
    if v.kind == "image":
        return Response(data, media_type=v.mime)
    import pymupdf
    doc = pymupdf.open(stream=data, filetype="pdf")
    pg = doc[max(0, min(page - 1, len(doc) - 1))]
    return Response(pg.get_pixmap(dpi=90).tobytes("png"), media_type="image/png")


class WorkflowBody(BaseModel):
    action: str
    note: str = ""


@router.post("/assets/{asset_id}/workflow")
def workflow(asset_id: int, body: WorkflowBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = service.get_asset(db, user, asset_id)
    service.workflow(db, user, a, body.action, body.note)
    return _bundle(db, user, a, None)


class Decision(BaseModel):
    action: str
    text: str | None = None
    note: str = ""


@router.post("/findings/{finding_id}/decision")
def decision(finding_id: int, body: Decision, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = need(db.get(Finding, finding_id), "Finding")
    service.decide(db, user, f, body.action, body.text, body.note)
    a = service.get_asset(db, user, f.asset_id)
    return _bundle(db, user, a, None)


class CommentBody(BaseModel):
    body: str
    finding_id: int | None = None


@router.get("/assets/{asset_id}/comments")
def comments(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = service.get_asset(db, user, asset_id)
    return [ser_comment(c) for c in db.execute(select(Comment).where(Comment.asset_id == a.id).order_by(Comment.id)).scalars()]


@router.post("/assets/{asset_id}/comments")
def add_comment(asset_id: int, body: CommentBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = service.get_asset(db, user, asset_id)
    if len(body.body.strip()) < 1:
        raise HTTPException(422, "Empty comment")
    if body.finding_id is not None:
        f = db.get(Finding, body.finding_id)
        if f is None or f.asset_id != a.id:
            raise HTTPException(422, "That finding does not belong to this asset")
    c = Comment(asset_id=a.id, finding_id=body.finding_id, author=user.email, role=user.role, body=body.body.strip())
    db.add(c)
    audit.log(db, user.email, "comment.add", "asset", a.id, {"finding": body.finding_id})
    db.commit()
    return ser_comment(c)


@router.get("/assets/{asset_id}/proofpack")
def proofpack(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = service.get_asset(db, user, asset_id)
    pp = service.proofpack(db, a)
    rec = receipts.latest_receipt(db, a)
    pp["receipt"] = None if rec is None else {"code": rec.code, "digest": rec.digest, "version": rec.version_n,
                                              "issued_at": rec.created_at.isoformat(timespec="seconds"), "issued_by": rec.issued_by,
                                              "verify_url": f"{config.public_url()}/verify/{rec.code}",
                                              "current": rec.version_n == pp["version"]["n"]}
    return pp


@router.get("/assets/{asset_id}/proofpack.pdf")
def proofpack_pdf(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = service.get_asset(db, user, asset_id)
    rec = receipts.latest_receipt(db, a)
    if a.status == "Approved" and (rec is None or rec.version_n != service.latest_version(db, a).n):
        rec = receipts.issue(db, user, a)  # approved before receipts existed: issue one now
        db.commit()
    data = receipts.render_pdf(service.proofpack(db, a), rec if a.status == "Approved" else None)
    name = f"proof-pack-{a.id}-v{service.latest_version(db, a).n}.pdf"
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/queue")
def queue(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in ("manager", "reviewer"):
        return []
    rows = []
    for a in db.execute(select(Asset).where(Asset.status == "In review")).scalars():
        if user.role == "manager" and a.risk == "high":
            tag = "needs reviewer"
        else:
            tag = "ready for you"
        rows.append({**ser_asset(a), "route": tag})
    rows.sort(key=lambda r: (r["risk"] != "high", r["updated_at"]))
    return rows


class FactRequestBody(BaseModel):
    claim_label: str
    note: str = ""


@router.post("/assets/{asset_id}/fact-requests")
def create_fact_request(asset_id: int, body: FactRequestBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = service.get_asset(db, user, asset_id)
    service.request_fact(db, user, a, body.claim_label, body.note)
    return _bundle(db, user, a, None)
