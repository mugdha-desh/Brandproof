"""Signed Proof Pack receipts (I2).

A receipt is issued when an asset is approved. It holds a public-safe snapshot of what the review covered
(no copy, no claim text, no emails), a SHA-256 digest of that snapshot, an HMAC signature, and an anchor in the
tamper-evident audit log. Anyone with the code can check three things without logging in:
  1. the signature and digest are intact (the receipt was not edited),
  2. the audit-log entry that recorded the issue still exists and the whole chain verifies,
  3. optionally, that a file they hold is byte-for-byte the approved version (SHA-256 match).
"""
import hashlib
import hmac
import html
import io
import json
import secrets
from collections import Counter

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, config, stale
from .db import Asset, ProofReceipt, User, utcnow


def _digest(snapshot: dict) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _sign(code: str, digest: str, anchor_hash: str) -> str:
    return hmac.new(config.secret().encode(), f"{code}|{digest}|{anchor_hash}".encode(), hashlib.sha256).hexdigest()


def build_snapshot(pp: dict, code: str) -> dict:
    """The public part of a Proof Pack. Deliberately leaves out the copy itself, claim text, comments and emails."""
    fs = pp["findings"]
    claims = pp["claim_ledger"]
    s = pp["summary"]
    tr = pp["trust"] or {}
    return {
        "code": code,
        "asset": {"title": pp["asset"]["title"], "channel": pp["asset"]["channel"], "ai_generated": pp["asset"]["ai_generated"],
                  "version": pp["version"]["n"], "kind": pp["version"]["kind"], "content_sha256": pp["version"]["sha256"]},
        "status": pp["asset"]["status"],
        "approvals": [{"role": (h["detail"] or {}).get("role", ""), "at": h["ts"]} for h in pp["humans"] if h["action"] == "asset.approve"],
        "review": {"findings": len(fs), "by_severity": dict(Counter(f["severity"] for f in fs)),
                   "by_status": dict(Counter(f["status"] for f in fs)), "abstained": s.get("abstained", 0),
                   "fixes": s.get("fixes", {}), "checks": pp["checks"] or {}, "method": (pp["checks"] or {}).get("judgment_method", "")},
        "claim_ledger": [{"label": c["label"], "kind": c["kind"], "verdict": c["verdict"], "fact": c["fact"]} for c in claims],
        "claim_verdicts": dict(Counter(c["verdict"] for c in claims)),
        "intent_lock": {"elements": [e["kind"] for e in pp.get("intent_elements", [])]},
        "trust": {"hidden_items": len(tr.get("hidden", [])), "injection_signals": len(tr.get("injections", [])),
                  "lookalike_words": len(tr.get("lookalikes", [])),
                  "manipulation_flag": bool(pp["differential"].get("ran") and not pp["differential"].get("agree"))},
        "fact_requests": dict(Counter(r["status"] for r in pp.get("fact_requests", []))),
        "not_checked": pp["not_checked"],
        "ai_use": {"provider": pp["ai_use"]["provider"], "model": pp["ai_use"]["model"], "calls": pp["ai_use"]["calls"],
                   "redactions": pp["ai_use"]["redactions"], "auto_applied": 0},
        "facts_as_of": s.get("facts_as_of", ""),
    }


def latest_receipt(db: Session, asset: Asset) -> ProofReceipt | None:
    return db.execute(select(ProofReceipt).where(ProofReceipt.asset_id == asset.id)
                      .order_by(ProofReceipt.created_at.desc())).scalars().first()


def issue(db: Session, user: User, asset: Asset) -> ProofReceipt:
    from . import service
    if asset.status != "Approved":
        raise HTTPException(409, "A receipt is only issued for an approved asset")
    v = service.latest_version(db, asset)
    existing = latest_receipt(db, asset)
    if existing and existing.version_n == v.n:
        return existing
    code = "BP-" + secrets.token_hex(8).upper()
    snap = build_snapshot(service.proofpack(db, asset), code)
    digest = _digest(snap)
    row = audit.log(db, user.email, "receipt.issue", "asset", asset.id, {"code": code, "digest": digest, "version": v.n})
    rec = ProofReceipt(code=code, asset_id=asset.id, version_n=v.n, digest=digest, signature=_sign(code, digest, row.hash),
                       snapshot=snap, anchor_id=row.id, anchor_hash=row.hash, issued_by=user.email)
    db.add(rec)
    db.flush()
    return rec


def verify(db: Session, code: str, digest: str | None = None, sha256: str | None = None) -> dict:
    rec = db.get(ProofReceipt, code.strip().upper())
    if rec is None:
        return {"found": False, "code": code}
    sig_ok = hmac.compare_digest(rec.signature, _sign(rec.code, rec.digest, rec.anchor_hash))
    dig_ok = _digest(rec.snapshot) == rec.digest
    row = db.get(audit.Audit, rec.anchor_id)
    chain = audit.verify(db)
    in_log = bool(row and row.hash == rec.anchor_hash and row.action == "receipt.issue" and (row.detail or {}).get("code") == rec.code)
    asset = db.get(Asset, rec.asset_id)
    cur = None
    if asset is not None:
        from . import service
        cur = service.latest_version(db, asset).n
    out = {
        "found": True, "code": rec.code, "issued_at": rec.created_at.isoformat(timespec="seconds"), "digest": rec.digest,
        "signature_valid": sig_ok, "digest_valid": dig_ok,
        "anchor": {"id": rec.anchor_id, "hash": rec.anchor_hash, "in_log": in_log, "chain_ok": chain["ok"], "entries": chain["entries"]},
        "asset_now": {"version": cur, "changed_since": cur is not None and cur != rec.version_n,
                      "status": asset.status if asset else "deleted"},
        "stale_alerts_open": stale.open_count(db, rec.asset_id) if asset is not None else 0,
        "snapshot": rec.snapshot,
        "digest_matches": None if not digest else digest.strip().lower() == rec.digest,
        "file_matches": None if not sha256 else sha256.strip().lower() == rec.snapshot["asset"]["content_sha256"],
    }
    out["valid"] = bool(sig_ok and dig_ok and in_log and chain["ok"])
    return out


# ------------------------------------------------------------------ PDF
_CSS = """
body { font-family: sans-serif; font-size: 9.5pt; color: #14213D; }
h1 { font-size: 22pt; margin: 0 0 2pt 0; }
h2 { font-size: 11pt; margin: 12pt 0 3pt 0; border-bottom: 1px solid #999999; color: #14213D; }
td, th { padding: 2pt 4pt; vertical-align: top; text-align: left; font-size: 9pt; }
th { color: #555555; }
.ok { color: #176b3a; font-weight: bold; } .bad { color: #b3261e; font-weight: bold; }
.box { border: 1px solid #14213D; padding: 6pt; }
.mono { font-family: monospace; font-size: 8pt; }
.small { font-size: 8pt; color: #444444; }
"""


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def render_pdf(pp: dict, rec: ProofReceipt | None) -> bytes:
    import pymupdf
    a, s, c = pp["asset"], pp["summary"], pp["checks"] or {}
    tr = pp["trust"] or {}
    approved = a["status"] == "Approved" and rec is not None
    h = [f"<h1>Proof Pack</h1><p><b>{_e(a['title'])}</b> ({_e(a['channel'])}) &nbsp; "
         f"<span class='{'ok' if approved else 'bad'}'>{_e(a['status']).upper()}</span> &nbsp; version {pp['version']['n']}</p>"]
    if rec:
        url = f"{config.public_url()}/verify/{rec.code}"
        h.append(f"<div class='box'><b>Receipt {_e(rec.code)}</b> issued {_e(rec.created_at.isoformat(timespec='seconds')).replace('T', ' ')} UTC by {_e(rec.issued_by)}<br/>"
                 f"Verify without logging in: {_e(url)}<br/><span class='mono'>digest {rec.digest}</span><br/>"
                 f"<span class='mono'>content sha256 {_e(pp['version']['sha256'])}</span></div>")
    else:
        h.append("<div class='box'><b class='bad'>No receipt.</b> This asset is not approved, so nothing here can be used as proof of approval.</div>")
    h.append(f"<h2>Creator intent</h2><p>{_e(a['intent'])}</p>")
    if pp.get("intent_elements"):
        h.append("<p class='small'>Must-keep elements (Intent Lock): " + "; ".join(f"{_e(e['kind'])}: {_e(e['text'])}" for e in pp["intent_elements"]) + "</p>")
    h.append("<h2>Trust Layer</h2><p>" + (f"<span class='bad'>{len(tr.get('hidden', []))} hidden item(s) found and removed.</span> " if tr.get("hidden") else "<span class='ok'>No hidden text.</span> ")
             + (f"<span class='bad'>{len(tr.get('injections', []))} instruction(s) aimed at AI reviewers, not obeyed.</span> " if tr.get("injections") else "<span class='ok'>0 injection signals.</span> ")
             + (f"{len(tr.get('lookalikes', []))} word(s) with look-alike letters folded. " if tr.get("lookalikes") else "")
             + "<br/>Raw vs cleaned review: " + ("identical, single review" if not pp["differential"].get("ran") else ("verdicts agree" if pp["differential"].get("agree") else "<span class='bad'>VERDICTS DIFFER (manipulation flag)</span>")) + "</p>")
    h.append(f"<h2>Checks run</h2><p>{c.get('deterministic_rules', 0)} deterministic rules, {c.get('file_checks', 0)} file checks, {c.get('claims_judged', 0)} claims judged, "
             f"{c.get('judgment_rules', 0)} tone and messaging rules via {_e(c.get('judgment_method', ''))}. {s.get('abstained', 0)} finding(s) routed to a human because the reviewer was not confident.</p>")
    if pp["claim_ledger"]:
        rows = "".join(f"<tr><td>{_e(x['label'])}</td><td>{_e(x['text'])}</td><td><b>{_e(x['verdict'])}</b></td><td>{_e(x['fact'] or 'no fact')}</td></tr>" for x in pp["claim_ledger"])
        h.append(f"<h2>Claim Ledger</h2><table width='100%'><tr><th>#</th><th>Claim</th><th>Verdict</th><th>Fact</th></tr>{rows}</table>")
    else:
        h.append("<h2>Claim Ledger</h2><p>No promotional claims.</p>")
    fx = s.get("fixes", {})
    h.append(f"<h2>Findings</h2><p>{len(pp['findings'])} total. Fixes proposed {fx.get('proposed', 0)}, verified {fx.get('verified', 0)}, withheld {fx.get('withheld', 0)}.</p><ul>"
             + "".join(f"<li>#{f['id']} {_e(f['rule'])} [{_e(f['severity'])}, {_e(f['method'])}] {_e(f['title'])}: <b>{_e(f['status'])}</b>{(' by ' + _e(f['decided_by'])) if f['decided_by'] else ''}</li>" for f in pp["findings"][:60]) + "</ul>")
    h.append("<h2>NOT checked</h2><ul>" + "".join(f"<li>{_e(n)}</li>" for n in pp["not_checked"]) + f"</ul><p class='small'>Facts were valid as of {_e(s.get('facts_as_of', ''))}.</p>")
    if pp.get("fact_requests"):
        h.append("<h2>Fact requests</h2><ul>" + "".join(f"<li>{_e(r['claim_label'])} {_e(r['claim_text'])}: <b>{_e(r['status'])}</b>{(' (' + _e(r['fact_id']) + ')') if r['fact_id'] else ''}</li>" for r in pp["fact_requests"]) + "</ul>")
    h.append("<h2>Humans</h2><ul>" + "".join(f"<li>{_e(x['ts']).replace('T', ' ')} {_e(x['actor'])}: {_e(x['action'])}</li>" for x in pp["humans"]) + "</ul><p class='small'>Nothing was applied or approved by AI.</p>")
    ai = pp["ai_use"]
    h.append(f"<h2>AI use</h2><p>Provider {_e(ai['provider'])} {_e(ai['model'])}; {ai['calls']} external call(s); {ai['redactions']} personal-data item(s) redacted. {_e(ai['note'])}</p>")
    ch = pp["audit_chain"]
    h.append(f"<h2>Audit chain</h2><p><span class='{'ok' if ch['ok'] else 'bad'}'>{'Verified' if ch['ok'] else 'FAILED'}</span>, {ch['entries']} entries.<br/><span class='mono'>head {_e(ch['head'])}</span></p>")
    story = pymupdf.Story(html="".join(h), user_css=_CSS)
    buf = io.BytesIO()
    w = pymupdf.DocumentWriter(buf)
    mb = pymupdf.paper_rect("a4")
    where = mb + (40, 40, -40, -40)
    more = 1
    while more:
        dev = w.begin_page(mb)
        more, _ = story.place(where)
        story.draw(dev)
        w.end_page()
    w.close()
    return buf.getvalue()
