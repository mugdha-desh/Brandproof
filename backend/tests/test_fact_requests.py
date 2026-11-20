"""I1: claim evidence and the request-a-fact flow."""
from conftest import login, make_asset

TEXT = "Our new savings account is here. We are the most trusted savings app in India. Interest up to 6.5% p.a."


def _claim(d, kind):
    return [c for c in d["claims"] if c["kind"] == kind][0]


def test_bundle_carries_evidence_for_cited_facts(client):
    h = login(client)
    d = client.get(f"/api/assets/{make_asset(client, h, TEXT)}", headers=h).json()
    rate = _claim(d, "rate")
    ev = d["facts"][rate["fact_id"]]
    assert ev["statement"] and ev["source"] and ev["owner"] and "expired" in ev and "days_left" in ev


def test_request_fact_for_unsupported_claim_and_dedupe(client):
    h = login(client)
    aid = make_asset(client, h, TEXT)
    d = client.get(f"/api/assets/{aid}", headers=h).json()
    label = _claim(d, "superlative")["label"]
    r1 = client.post(f"/api/assets/{aid}/fact-requests", headers=h, json={"claim_label": label, "note": "Survey result"})
    assert r1.status_code == 200 and len(r1.json()["fact_requests"]) == 1
    r2 = client.post(f"/api/assets/{aid}/fact-requests", headers=h, json={"claim_label": label})
    assert len(r2.json()["fact_requests"]) == 1  # no duplicate for the same open claim


def test_supported_claim_cannot_be_requested(client):
    h = login(client)
    aid = make_asset(client, h, TEXT)
    d = client.get(f"/api/assets/{aid}", headers=h).json()
    sup = [c for c in d["claims"] if c["verdict"] == "Supported"][0]
    r = client.post(f"/api/assets/{aid}/fact-requests", headers=h, json={"claim_label": sup["label"]})
    assert r.status_code == 422


def test_only_the_fact_owner_resolves(client):
    h = login(client)
    aid = make_asset(client, h, TEXT)
    label = _claim(client.get(f"/api/assets/{aid}", headers=h).json(), "superlative")["label"]
    client.post(f"/api/assets/{aid}/fact-requests", headers=h, json={"claim_label": label})
    rid = client.get("/api/fact-requests", headers=login(client, "owner@finora.example")).json()[0]["id"]
    for who in ("creator@finora.example", "manager@finora.example"):
        r = client.post(f"/api/fact-requests/{rid}/resolve", headers=login(client, who), json={"action": "decline", "note": "no"})
        assert r.status_code == 403


def test_owner_adds_fact_and_rerun_turns_the_claim_supported(client):
    h, oh = login(client), login(client, "owner@finora.example")
    aid = make_asset(client, h, TEXT)
    label = _claim(client.get(f"/api/assets/{aid}", headers=h).json(), "superlative")["label"]
    client.post(f"/api/assets/{aid}/fact-requests", headers=h, json={"claim_label": label})
    req = client.get("/api/fact-requests?status=open", headers=oh).json()[0]
    assert req["claim_text"].lower().startswith(("the most trusted", "most trusted")) and req["asset_title"]
    bad = client.post(f"/api/fact-requests/{req['id']}/resolve", headers=oh,
                      json={"action": "add", "fact": {"statement": "x", "source": "", "owner": "", "keywords": []}})
    assert bad.status_code == 422
    ok = client.post(f"/api/fact-requests/{req['id']}/resolve", headers=oh, json={
        "action": "add", "note": "Approved by Brand Legal",
        "fact": {"statement": "Finora was rated most trusted savings app in the 2026 Pune survey.", "kind": "superlative",
                 "keywords": ["most trusted"], "source": "Pune survey Oct 2026", "owner": "Legal", "valid_to": "2027-06-30"}})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "resolved" and ok.json()["fact_id"].startswith("F-")
    d = client.post(f"/api/assets/{aid}/rerun", headers=h).json()
    c = _claim(d, "superlative")
    assert c["verdict"] == "Supported" and c["fact_id"] == ok.json()["fact_id"]
    assert d["facts"][c["fact_id"]]["owner"] == "Legal"
    assert d["fact_requests"][0]["status"] == "resolved"
    assert client.get("/api/audit/verify", headers=oh).json()["ok"]


def test_decline_needs_a_reason_and_shows_in_proof_pack(client):
    h, oh = login(client), login(client, "owner@finora.example")
    aid = make_asset(client, h, TEXT)
    label = _claim(client.get(f"/api/assets/{aid}", headers=h).json(), "superlative")["label"]
    client.post(f"/api/assets/{aid}/fact-requests", headers=h, json={"claim_label": label})
    rid = client.get("/api/fact-requests", headers=oh).json()[0]["id"]
    assert client.post(f"/api/fact-requests/{rid}/resolve", headers=oh, json={"action": "decline"}).status_code == 422
    assert client.post(f"/api/fact-requests/{rid}/resolve", headers=oh,
                       json={"action": "decline", "note": "No survey exists"}).json()["status"] == "declined"
    pp = client.get(f"/api/assets/{aid}/proofpack", headers=h).json()
    assert pp["fact_requests"][0]["status"] == "declined" and pp["intent_elements"]


def test_existing_database_gets_the_new_column(tmp_path, monkeypatch):
    """The deployed Postgres already has an assets table: init must add intent_elements without losing data."""
    import sqlalchemy as sa
    url = f"sqlite:///{tmp_path}/old.db"
    eng = sa.create_engine(url)
    with eng.begin() as cx:
        cx.execute(sa.text("CREATE TABLE assets (id INTEGER PRIMARY KEY, title VARCHAR(300))"))
        cx.execute(sa.text("INSERT INTO assets VALUES (1, 'kept')"))
    from app import db
    db.migrate(eng)
    db.migrate(eng)  # idempotent
    with eng.begin() as cx:
        assert cx.execute(sa.text("SELECT title, intent_elements FROM assets")).one() == ("kept", None)
