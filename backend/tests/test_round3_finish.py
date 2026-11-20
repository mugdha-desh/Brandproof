"""Fixes ported in the final Round 3 pass: future-dated facts, exclamation counting, comment scope,
upload dimension caps, and fact snapshots that keep an old receipt honest."""
import datetime as dt
import io

from conftest import login, make_asset

TEXT = "Our new savings account is here. Interest up to 6.5% p.a."


def _rate_fact(dbs):
    from sqlalchemy import select
    from app.db import Fact
    return [f for f in dbs.execute(select(Fact)).scalars() if f.numeric and f.kind == "rate"][0]


# ---------------------------------------------------------------- future-dated facts
def test_fact_not_valid_yet_cannot_support_a_claim(client, dbs):
    f = _rate_fact(dbs)
    f.valid_from = dt.date(2026, 12, 1)           # BP_TODAY is 2026-11-17
    dbs.commit()
    h = login(client)
    d = client.get(f"/api/assets/{make_asset(client, h, TEXT)}", headers=h).json()
    rate = [c for c in d["claims"] if c["kind"] == "rate"][0]
    assert rate["verdict"] == "Needs human"
    assert "does not become valid until 2026-12-01" in rate["explanation"]


def test_fact_valid_today_still_supports(client, dbs):
    f = _rate_fact(dbs)
    f.valid_from = dt.date(2026, 11, 17)
    dbs.commit()
    h = login(client)
    d = client.get(f"/api/assets/{make_asset(client, h, TEXT)}", headers=h).json()
    assert [c for c in d["claims"] if c["kind"] == "rate"][0]["verdict"] == "Supported"


# ---------------------------------------------------------------- exclamation marks
def test_double_exclamation_counts_as_two():
    from app.engine import rules

    class R:
        params = {"max": 1}
    assert rules.eval_exclaim(R, "Great news!", None) == []
    assert len(rules.eval_exclaim(R, "Great news!!", None)) == 1
    assert len(rules.eval_exclaim(R, "Great!!! News!!", None)) == 4


# ---------------------------------------------------------------- comments stay inside their asset
def test_comment_cannot_point_at_another_assets_finding(client):
    h = login(client)
    a = make_asset(client, h, TEXT + " We guarantee returns!!")
    b = make_asset(client, h, "Hello from a clean post.", title="Other")
    fa = client.get(f"/api/assets/{a}", headers=h).json()["findings"][0]["id"]
    r = client.post(f"/api/assets/{b}/comments", headers=h, json={"body": "x", "finding_id": fa})
    assert r.status_code == 422
    ok = client.post(f"/api/assets/{a}/comments", headers=h, json={"body": "x", "finding_id": fa})
    assert ok.status_code == 200


# ---------------------------------------------------------------- dimension caps
def test_pdf_with_too_many_pages_is_refused(client, monkeypatch):
    import pymupdf
    monkeypatch.setenv("BP_MAX_PDF_PAGES", "3")
    doc = pymupdf.open()
    for _ in range(4):
        doc.new_page().insert_text((72, 72), "Hello")
    h = login(client)
    r = client.post("/api/assets", headers=h, data={"title": "t", "intent": "Announce our new savings account", "channel": "social"},
                    files={"file": ("big.pdf", doc.tobytes(), "application/pdf")})
    assert r.status_code == 413 and "4 pages" in r.json()["detail"]


def test_huge_image_is_refused(client, monkeypatch):
    from PIL import Image
    monkeypatch.setenv("BP_MAX_IMAGE_MEGAPIXELS", "0.01")      # 10,000 pixels
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), "white").save(buf, "PNG")
    h = login(client)
    r = client.post("/api/assets", headers=h, data={"title": "t", "intent": "Announce our new savings account", "channel": "social"},
                    files={"file": ("a.png", buf.getvalue(), "image/png")})
    assert r.status_code == 413 and "megapixels" in r.json()["detail"]


def test_logo_must_be_a_small_image_and_guideline_file_is_capped(client):
    h = login(client, "owner@finora.example")
    bad = client.post("/api/library/logo", headers=h, data={"name": "x"}, files={"file": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 415
    big = client.post("/api/guidelines/import", headers=h, files={"file": ("g.txt", b"a" * (5 * 1024 * 1024 + 1), "text/plain")})
    assert big.status_code == 413


# ---------------------------------------------------------------- fact snapshots
def test_old_review_keeps_the_fact_as_it_was(client, dbs):
    h = login(client)
    aid = make_asset(client, h, TEXT)
    before = client.get(f"/api/assets/{aid}", headers=h).json()
    cl = [c for c in before["claims"] if c["kind"] == "rate"][0]
    original = before["facts"][cl["fact_id"]]
    assert original["historical_snapshot"] is True and original["changed_since"] is False

    f = _rate_fact(dbs)
    f.statement = "EDITED: the rate is now something else entirely."
    dbs.commit()
    after = client.get(f"/api/assets/{aid}", headers=h).json()["facts"][cl["fact_id"]]
    assert after["statement"] == original["statement"]          # evidence not rewritten
    assert after["changed_since"] is True and after["deleted_since"] is False


def test_deleted_fact_is_still_shown_for_the_old_review(client, dbs):
    h = login(client)
    aid = make_asset(client, h, TEXT)
    cl = [c for c in client.get(f"/api/assets/{aid}", headers=h).json()["claims"] if c["kind"] == "rate"][0]
    dbs.delete(_rate_fact(dbs))
    dbs.commit()
    ev = client.get(f"/api/assets/{aid}", headers=h).json()["facts"][cl["fact_id"]]
    assert ev["statement"] and ev["deleted_since"] is True


def test_run_without_snapshot_falls_back_and_says_so(client, dbs):
    from sqlalchemy import select
    from app.db import ReviewRun
    h = login(client)
    aid = make_asset(client, h, TEXT)
    for r in dbs.execute(select(ReviewRun)).scalars():
        r.fact_snapshot = {}                                      # looks like a run from before snapshots
    dbs.commit()
    d = client.get(f"/api/assets/{aid}", headers=h).json()
    cl = [c for c in d["claims"] if c["kind"] == "rate"][0]
    assert d["facts"][cl["fact_id"]]["historical_snapshot"] is False


def test_existing_database_gets_the_snapshot_column(tmp_path):
    import sqlalchemy as sa
    from app import db
    eng = sa.create_engine(f"sqlite:///{tmp_path}/old.db")
    with eng.begin() as cx:
        cx.execute(sa.text("CREATE TABLE review_runs (id INTEGER PRIMARY KEY)"))
    db.migrate(eng)
    assert "fact_snapshot" in {c["name"] for c in sa.inspect(eng).get_columns("review_runs")}
