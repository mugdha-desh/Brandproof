"""End-to-end smoke test against a RUNNING backend with the demo data loaded (BP_SEED=1).
Usage:  python scripts/smoke_test.py            (default http://localhost:8000)
        python scripts/smoke_test.py https://your-api.onrender.com
Prints PASS/FAIL per check and ends with ALL CHECKS PASSED (exit code 0) or FAILED (exit code 1).
Needs only: pip install httpx"""
import sys

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
PW = "demo1234"
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""))


c = httpx.Client(base_url=BASE, timeout=60)


def login(email):
    r = c.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, f"login failed for {email}: {r.text}"
    return {"Authorization": "Bearer " + r.json()["token"]}


def submit(h, text, intent="Announce our new savings account", title="smoke test"):
    r = c.post("/api/assets", headers=h, data={"title": title, "intent": intent, "channel": "social", "text": text})
    assert r.status_code == 200, r.text
    return c.get(f"/api/assets/{r.json()['id']}", headers=h).json()


try:
    check("API is up", c.get("/api/health").json() == {"ok": True})
    creator, manager = login("creator@finora.example"), login("manager@finora.example")
    reviewer, owner = login("reviewer@finora.example"), login("owner@finora.example")
    agency = login("agency@nova.example")

    d = submit(creator, "Earn guaranteed returns on our new savings account.")
    rules = {(f["rule_id"], f["verdict"]) for f in d["findings"]}
    check("Input 1: 'guaranteed returns' -> TERM-01 flagged", ("TERM-01", "") in rules)
    check("Input 1: claim Contradicted by fact F-12",
          any(f["verdict"] == "Contradicted" and "F-12" in f["citation"].get("facts", []) for f in d["findings"]))
    fx = [f for f in d["findings"] if f["rule_id"] == "TERM-01"][0]["fix"]
    check("Input 1: fix is re-verified and passes Intent Lock", fx and fx["status"] == "verified" and fx["verification"]["intent_lock"]["passed"])
    check("Nothing applied without a click (still 1 version)", len(d["versions"]) == 1 and "guaranteed" in d["version"]["text"])

    fid = [f for f in d["findings"] if f["rule_id"] == "TERM-01"][0]["id"]
    d2 = c.post(f"/api/findings/{fid}/decision", headers=creator, json={"action": "accept_fix"}).json()
    check("Accept fix -> new version 2 with the fixed wording", d2["version"]["n"] == 2 and "competitive interest" in d2["version"]["text"])

    d = submit(creator, "Get 7.5% interest on Finora Save. T&C apply.")
    check("Input 2: '7.5%' Contradicted by F-03",
          any(f["verdict"] == "Contradicted" and "F-03" in f["citation"].get("facts", []) for f in d["findings"]))
    d = submit(creator, "Enjoy our launch cashback this month.")
    check("Input 3: expired offer -> Outdated by F-19",
          any(f["verdict"] == "Outdated" and "F-19" in f["citation"].get("facts", []) for f in d["findings"]))
    d = submit(creator, "Hurry, open an account.")
    check("Input 4: pressure language -> TONE-04", any(f["rule_id"] == "TONE-04" for f in d["findings"]))
    d = submit(creator, "Write to anita.rao@example.com or call 9876543210.")
    check("Input 5: personal data -> PRIV-01", any(f["rule_id"] == "PRIV-01" for f in d["findings"]))
    d = submit(creator, "Open Finora Save in about 5 minutes with Aadhaar eKYC.")
    check("Input 6: clean copy -> zero findings", d["findings"] == [], str([f["rule_id"] for f in d["findings"]]))

    lst = c.get("/api/assets", headers=manager).json()
    hidden = [a for a in lst if a["title"] == "Brochure PDF with hidden text"]
    check("Demo asset with hidden-text PDF exists", bool(hidden))
    if hidden:
        d = c.get(f"/api/assets/{hidden[0]['id']}", headers=manager).json()
        ids = {f["rule_id"] for f in d["findings"]}
        check("Hidden PDF: TRUST-01, TRUST-02, TRUST-03 all raised", {"TRUST-01", "TRUST-02", "TRUST-03"} <= ids, str(ids))
        check("Hidden PDF: raw vs cleaned verdicts differ", d["run"]["differential"]["ran"] and not d["run"]["differential"]["agree"])
        check("Hidden PDF: asset is high risk", d["asset"]["risk"] == "high")
        pack = c.get(f"/api/assets/{hidden[0]['id']}/proofpack", headers=manager).json()
        check("Proof Pack lists what was NOT checked", len(pack["not_checked"]) >= 3)

    check("Agency user only sees own assets", all(a["owner_email"] == "agency@nova.example" for a in c.get("/api/assets", headers=agency).json()))

    # risk routing: manager cannot approve a high-risk asset
    d = submit(creator, "Earn guaranteed returns on Finora Save.", title="smoke routing")
    aid = d["asset"]["id"]
    c.post(f"/api/assets/{aid}/workflow", headers=creator, json={"action": "submit"})
    r = c.post(f"/api/assets/{aid}/workflow", headers=manager, json={"action": "approve"})
    check("Manager cannot approve a high-risk asset (403)", r.status_code == 403)
    r = c.post(f"/api/assets/{aid}/workflow", headers=reviewer, json={"action": "approve"})
    check("Reviewer cannot approve until findings are waived (409)", r.status_code == 409)

    d = submit(creator, "Open Finora Save in about 5 minutes.", title="smoke receipt")
    rid = d["asset"]["id"]
    c.post(f"/api/assets/{rid}/workflow", headers=creator, json={"action": "submit"})
    r = c.post(f"/api/assets/{rid}/workflow", headers=manager, json={"action": "approve"})
    rec = c.get(f"/api/assets/{rid}/proofpack", headers=creator).json().get("receipt") if r.status_code == 200 else None
    check("Approval issues a signed receipt", bool(rec) and rec["code"].startswith("BP-"), r.text[:200])
    pub = c.get(f"/api/verify/{rec['code']}").json() if rec else {}   # no auth header on purpose
    check("Public verify says valid without logging in", pub.get("valid") is True, str(pub)[:200])
    pdf = c.get(f"/api/assets/{rid}/proofpack.pdf", headers=creator)
    check("Proof Pack PDF downloads", pdf.status_code == 200 and pdf.content[:4] == b"%PDF")
    ts = c.get("/api/trust/suite", headers=creator).json()
    check("Trust suite: no unexpected misses or false alarms", not ts["unexpected_misses"] and not ts["false_alarms"], str(ts["unexpected_misses"] + ts["false_alarms"]))

    v = c.get("/api/audit/verify", headers=manager).json()
    check("Audit hash chain verifies", v["ok"] and v["entries"] > 10, str(v))

    run = c.post("/api/redteam/run", headers=owner, json={"rule_id": "TERM-01"}).json()
    check("Red-team finds loopholes in TERM-01", run["summary"]["missed"] > 0)
    rt = (run.get("proposal") or {}).get("retest") or {}
    check("Tighter rule catches more variants, no false positives",
          rt.get("after_caught", 0) > rt.get("before_caught", 0) and rt.get("false_positives") == [], str(rt))
    check("Red-team reports a hold-out set and approval is allowed (no false positives)",
          rt.get("holdout_total", 0) > 0 and not (rt.get("guard") or {}).get("blocked"), str(rt.get("guard")))
    pid = (run.get("proposal") or {}).get("id")
    ap = c.post(f"/api/redteam/proposals/{pid}/decision", headers=owner, json={"action": "approve"}) if pid else None
    check("Owner approves the tighter rule (new rule version)", ap is not None and ap.status_code == 200, getattr(ap, "text", ""))
    d = submit(creator, "पक्का मुनाफा हर महीने, Finora Save के साथ।", title="smoke devanagari")
    check("Approved rule catches Devanagari guarantee wording", "TERM-01" in {f["rule_id"] for f in d["findings"]})
    rb = c.get("/api/rulebook", headers=owner).json()
    row = [x for x in rb["rules"] if x["rule_id"] == "TERM-01"]
    check("Rulebook Health shows diagnosis and red-team history", bool(row) and "diagnosis" in row[0] and len(row[0]["history"]) >= 1)
    d = submit(creator, "Our new savings account is here. Open yours in minutes. Act NOW or lose out forever!", title="smoke intent lock")
    check("Intent elements stored (subject and call to action)", {"subject", "cta"} <= {e["kind"] for e in d["intent_elements"]})
    tone = [f for f in d["findings"] if f["rule_id"] == "TONE-04" and f["fix"]]
    il = tone[0]["fix"]["verification"]["intent_lock"] if tone else {}
    check("Fix for pressure phrase verified and Intent Lock reports the CTA as kept",
          bool(tone) and tone[0]["fix"]["status"] == "verified"
          and any(e["kind"] == "cta" and e["status"] == "kept" for e in il.get("elements", [])), str(il))
    d = submit(creator, "We are the most trusted savings app in India. Interest up to 6.5% p.a.", title="smoke fact request")
    unsup = [x for x in d["claims"] if x["verdict"] == "Unsupported"]
    r = c.post(f"/api/assets/{d['asset']['id']}/fact-requests", headers=creator, json={"claim_label": unsup[0]["label"]}) if unsup else None
    check("Fact request raised for an Unsupported claim", r is not None and r.status_code == 200 and len(r.json()["fact_requests"]) == 1)
    inbox = c.get("/api/fact-requests?status=open", headers=owner).json()
    check("Owner sees the open fact requests", len(inbox) >= 1)
    check("Disclosure page data available", "services" in c.get("/api/disclosure", headers=creator).json())
    # round 3 step 5 and 6
    bad = c.post("/api/assets", headers=creator, data={"title": "x", "intent": "Announce our new savings account"},
                 files={"file": ("virus.exe", b"MZ\x90\x00", "application/octet-stream")})
    check("Upload of an unsupported file type is refused (415)", bad.status_code == 415)
    fake = c.post("/api/assets", headers=creator, data={"title": "x", "intent": "Announce our new savings account"},
                  files={"file": ("fake.pdf", b"not really a pdf", "application/pdf")})
    check("A fake PDF is refused by content check (415)", fake.status_code == 415)
    check("Security headers present on the API", c.get("/api/health").headers.get("x-content-type-options") == "nosniff")
    check("Manager can read stale-approval alerts", c.get("/api/stale", headers=manager).status_code == 200)
    check("Creator cannot read stale-approval alerts", c.get("/api/stale", headers=creator).status_code == 403)
    check("Evaluation page data includes the blind set", c.get("/api/eval", headers=creator).json().get("blind", {}).get("items", 0) >= 30)
    check("Disclosure reports confidential mode", "confidential_mode" in c.get("/api/disclosure", headers=creator).json())
except Exception as e:  # noqa
    check("Smoke test ran to the end", False, repr(e))

print("\n" + ("ALL CHECKS PASSED" if all(results) else "SOME CHECKS FAILED") + f" ({sum(results)}/{len(results)})")
sys.exit(0 if all(results) else 1)
