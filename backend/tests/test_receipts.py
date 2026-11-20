"""I2: signed Proof Pack receipts, the PDF export and public verification."""
import hashlib

import pymupdf
from sqlalchemy import select

from app import db as dbm
from app.db import ProofReceipt
from conftest import login, make_asset
from test_workflow import CLEAN, to_review


def approved(client, text=CLEAN):
    c, m = login(client), login(client, "manager@finora.example")
    aid = to_review(client, c, text)
    r = client.post(f"/api/assets/{aid}/workflow", headers=m, json={"action": "approve"})
    assert r.status_code == 200, r.text
    return aid, c, m


def test_receipt_is_issued_on_approval_and_listed_in_the_proof_pack(client):
    aid, c, m = approved(client)
    pp = client.get(f"/api/assets/{aid}/proofpack", headers=c).json()
    rec = pp["receipt"]
    assert rec["code"].startswith("BP-") and rec["current"] and len(rec["digest"]) == 64
    assert any(h["action"] == "asset.approve" for h in pp["humans"])


def test_public_verify_needs_no_login_and_leaks_no_content(client):
    aid, c, m = approved(client)
    code = client.get(f"/api/assets/{aid}/proofpack", headers=c).json()["receipt"]["code"]
    r = client.get(f"/api/verify/{code}")          # no Authorization header
    assert r.status_code == 200
    v = r.json()
    assert v["valid"] and v["signature_valid"] and v["digest_valid"] and v["anchor"]["in_log"] and v["anchor"]["chain_ok"]
    blob = r.text
    for secret in ("creator@finora.example", "manager@finora.example", CLEAN, "Finora Save in about"):
        assert secret not in blob
    assert v["snapshot"]["status"] == "Approved" and v["snapshot"]["ai_use"]["auto_applied"] == 0
    assert v["snapshot"]["not_checked"]


def test_unknown_code_is_a_404(client):
    assert client.get("/api/verify/BP-0000000000000000").status_code == 404
    assert client.get("/api/verify/" + "x" * 200).status_code == 404


def test_file_and_digest_matching(client):
    aid, c, m = approved(client)
    rec = client.get(f"/api/assets/{aid}/proofpack", headers=c).json()
    sha = hashlib.sha256(CLEAN.encode()).hexdigest()
    ok = client.get(f"/api/verify/{rec['receipt']['code']}", params={"sha256": sha, "digest": rec["receipt"]["digest"]}).json()
    assert ok["file_matches"] is True and ok["digest_matches"] is True
    bad = client.get(f"/api/verify/{rec['receipt']['code']}", params={"sha256": hashlib.sha256(b"other").hexdigest(), "digest": "0" * 64}).json()
    assert bad["file_matches"] is False and bad["digest_matches"] is False


def test_tampering_with_the_stored_snapshot_is_detected(client):
    aid, c, m = approved(client)
    code = client.get(f"/api/assets/{aid}/proofpack", headers=c).json()["receipt"]["code"]
    s = dbm.session()
    rec = s.get(ProofReceipt, code)
    snap = dict(rec.snapshot)
    snap["review"] = {**snap["review"], "abstained": 99}
    rec.snapshot = snap
    s.commit()
    s.close()
    v = client.get(f"/api/verify/{code}").json()
    assert v["valid"] is False and v["digest_valid"] is False


def test_tampering_with_the_audit_log_is_detected(client):
    from app.db import Audit
    aid, c, m = approved(client)
    code = client.get(f"/api/assets/{aid}/proofpack", headers=c).json()["receipt"]["code"]
    s = dbm.session()
    row = s.execute(select(Audit).where(Audit.action == "asset.approve").order_by(Audit.id.desc())).scalars().first()
    row.actor = "someone.else@example.com"
    s.commit()
    s.close()
    v = client.get(f"/api/verify/{code}").json()
    assert v["valid"] is False and v["anchor"]["chain_ok"] is False


def test_changing_the_asset_after_approval_is_shown(client):
    aid, c, m = approved(client)
    code = client.get(f"/api/assets/{aid}/proofpack", headers=c).json()["receipt"]["code"]
    r = client.post(f"/api/assets/{aid}/versions", headers=c, data={"text": CLEAN + " Updated.", "note": "edit"})
    assert r.status_code == 200, r.text
    v = client.get(f"/api/verify/{code}").json()
    assert v["valid"] and v["asset_now"]["changed_since"] is True and v["asset_now"]["version"] == 2


def test_no_receipt_for_an_unapproved_asset(client):
    c = login(client)
    aid = to_review(client, c, CLEAN)
    assert client.get(f"/api/assets/{aid}/proofpack", headers=c).json()["receipt"] is None


def test_pdf_export_for_approved_and_unapproved(client):
    aid, c, m = approved(client)
    r = client.get(f"/api/assets/{aid}/proofpack.pdf", headers=c)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    text = "".join(p.get_text() for p in pymupdf.open(stream=r.content, filetype="pdf"))
    code = client.get(f"/api/assets/{aid}/proofpack", headers=c).json()["receipt"]["code"]
    assert "Proof Pack" in text and code in text and "/verify/" in text and "NOT checked" in text and "APPROVED" in text
    aid2 = to_review(client, c, CLEAN)
    t2 = "".join(p.get_text() for p in pymupdf.open(stream=client.get(f"/api/assets/{aid2}/proofpack.pdf", headers=c).content, filetype="pdf"))
    assert "No receipt" in t2 and "BP-" not in t2


def test_old_approved_asset_gets_a_receipt_on_export(client):
    """Approved before receipts existed (the deployed database): the PDF export issues one."""
    aid, c, m = approved(client)
    s = dbm.session()
    s.delete(s.get(ProofReceipt, client.get(f"/api/assets/{aid}/proofpack", headers=c).json()["receipt"]["code"]))
    s.commit()
    s.close()
    assert client.get(f"/api/assets/{aid}/proofpack", headers=c).json()["receipt"] is None
    assert client.get(f"/api/assets/{aid}/proofpack.pdf", headers=c).status_code == 200
    assert client.get(f"/api/assets/{aid}/proofpack", headers=c).json()["receipt"]["current"]
