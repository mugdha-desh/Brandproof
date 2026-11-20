"""Stale-approval alerts: the receipt stays true, or BrandProof says it no longer is.

When a fact changes, is deleted, or simply passes its valid-until date, every Approved asset is re-judged against the
current Fact Vault. A claim that was fine at approval and is now Contradicted or Outdated raises an alert.

Design limits, on purpose:
- Local and deterministic only. No LLM call, nothing leaves the server, so it works in confidential mode.
- Nothing is changed automatically. The asset stays Approved; people see the alert and decide (new version, or dismiss with a note).
- It re-checks claims only. Tone, terms and visuals do not depend on the Fact Vault.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, config
from .db import Asset, AssetVersion, Claim, Fact, StaleAlert, utcnow
from .engine import claims as cl

BAD = (cl.CONTRADICTED, cl.OUTDATED)


def _text_of(v: AssetVersion) -> str:
    return (v.text_clean or v.text_raw or "").strip()


def scan(db: Session, actor: str = "system", trigger: str = "manual", asset_id: int | None = None) -> list[StaleAlert]:
    """Re-judge approved assets. Returns the NEW alerts only (an open alert is never duplicated)."""
    from . import service
    facts = db.execute(select(Fact)).scalars().all()
    today = config.today()
    q = select(Asset).where(Asset.status == "Approved")
    if asset_id is not None:
        q = q.where(Asset.id == asset_id)
    created: list[StaleAlert] = []
    for a in db.execute(q).scalars():
        v = service.latest_version(db, a)
        run = service.latest_run(db, a, v)
        text = _text_of(v)
        if v.purged or not text or run is None:
            continue
        before = {c.text.strip().lower(): c for c in db.execute(select(Claim).where(Claim.run_id == run.id)).scalars()}
        open_keys = {(x.claim_text.strip().lower(), x.now_verdict) for x in db.execute(
            select(StaleAlert).where(StaleAlert.asset_id == a.id, StaleAlert.status == "open")).scalars()}
        for c in cl.ledger(text, facts, today):
            if c.verdict not in BAD:
                continue
            key = c.text.strip().lower()
            old = before.get(key)
            if old is not None and old.verdict == c.verdict and old.fact_id == c.fact_id:
                continue  # it was already like this at approval: not stale, that is a finding a human already saw
            if (key, c.verdict) in open_keys:
                continue
            row = StaleAlert(asset_id=a.id, version_n=v.n, claim_text=c.text, was_verdict=old.verdict if old else "new claim",
                             now_verdict=c.verdict, fact_id=c.fact_id or "", reason=c.explanation or "", trigger=trigger)
            db.add(row)
            db.flush()
            audit.log(db, actor, "stale.raise", "asset", a.id, {"alert": row.id, "claim": c.text[:80], "now": c.verdict,
                                                                "fact": c.fact_id, "trigger": trigger})
            created.append(row)
    db.commit()
    return created


def resolve_for_asset(db: Session, asset: Asset, actor: str) -> int:
    """A new version supersedes the approved one, so its open alerts are resolved."""
    n = 0
    for x in db.execute(select(StaleAlert).where(StaleAlert.asset_id == asset.id, StaleAlert.status == "open")).scalars():
        x.status, x.handled_by, x.handled_at, x.handled_note = "resolved", actor, utcnow(), "New version submitted"
        n += 1
    if n:
        audit.log(db, actor, "stale.resolve", "asset", asset.id, {"alerts": n})
    return n


def open_count(db: Session, asset_id: int) -> int:
    return len(db.execute(select(StaleAlert.id).where(StaleAlert.asset_id == asset_id, StaleAlert.status == "open")).all())


def serialise(x: StaleAlert, asset: Asset | None = None) -> dict:
    return {"id": x.id, "asset_id": x.asset_id, "asset_title": asset.title if asset else "", "version": x.version_n,
            "claim": x.claim_text, "was": x.was_verdict, "now": x.now_verdict, "fact": x.fact_id, "reason": x.reason,
            "trigger": x.trigger, "status": x.status, "handled_by": x.handled_by, "note": x.handled_note,
            "created_at": x.created_at.isoformat(timespec="seconds"),
            "handled_at": x.handled_at.isoformat(timespec="seconds") if x.handled_at else None}
