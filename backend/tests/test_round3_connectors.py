"""Round 3 additions: Fact Vault import and feed, the scheduler, logo and picture-colour checks, the browser extension package."""
import io
import json
import os

import pytest
from PIL import Image, ImageDraw

from tests.conftest import login

CSV_OK = ("id,statement,kind,keywords,source,owner,valid_from,valid_to\n"
          "F-90,Finora Save pays 6.5% a year.,rate,interest;rate,Product sheet,Treasury,2026-11-01,2027-03-31\n"
          "F-91,Debit card is free.,fee,card,Product sheet,Treasury,,\n")


def owner(client):
    return login(client, "owner@finora.example")


def post_import(client, h, content, name="facts.csv", dry_run=True):
    return client.post("/api/facts/import", headers=h, data={"dry_run": "true" if dry_run else "false"},
                       files={"file": (name, content if isinstance(content, bytes) else content.encode(), "text/csv")})


# ------------------------------------------------------------------ import
def test_only_the_owner_can_import(client):
    r = post_import(client, login(client), CSV_OK)
    assert r.status_code == 403


def test_dry_run_writes_nothing_then_apply_writes(client):
    h = owner(client)
    before = len(client.get("/api/facts", headers=h).json())
    r = post_import(client, h, CSV_OK).json()
    assert r["dry_run"] and r["created"] == ["F-90", "F-91"] and not r["errors"]
    assert len(client.get("/api/facts", headers=h).json()) == before
    r = post_import(client, h, CSV_OK, dry_run=False).json()
    facts = {f["id"]: f for f in client.get("/api/facts", headers=h).json()}
    assert len(facts) == before + 2 and facts["F-90"]["valid_to"] == "2027-03-31" and facts["F-90"]["keywords"] == ["interest", "rate"]
    again = post_import(client, h, CSV_OK, dry_run=False).json()
    assert again["created"] == [] and sorted(again["unchanged"]) == ["F-90", "F-91"]


def test_update_reports_changed_fields_and_never_deletes(client):
    h = owner(client)
    post_import(client, h, CSV_OK, dry_run=False)
    n = len(client.get("/api/facts", headers=h).json())
    changed = CSV_OK.replace("2027-03-31", "2027-06-30")
    r = post_import(client, h, changed, dry_run=False).json()
    assert r["updated"] == [{"id": "F-90", "fields": ["valid_to"]}]
    assert len(client.get("/api/facts", headers=h).json()) == n  # a fact missing from a file is never removed


def test_bad_rows_are_reported_not_imported(client):
    h = owner(client)
    bad = ("id,statement,source,owner,valid_from,valid_to\n"
           "bad id!,Text,Src,Own,,\n"
           "F-92,,Src,Own,,\n"
           "F-93,Text,Src,,,\n"
           "F-94,Text,Src,Own,31/12/2026,\n"
           "F-95,Text,Src,Own,2026-12-31,2026-01-01\n"
           "F-96,Fine,Src,Own,2026-01-01,2026-12-31\n"
           "F-96,Duplicate,Src,Own,,\n")
    r = post_import(client, h, bad, dry_run=False).json()
    assert r["created"] == ["F-96"] and [e["row"] for e in r["errors"]] == [1, 2, 3, 4, 5, 7]


def test_json_and_pattern_rules_from_a_file_only(client):
    h = owner(client)
    ok = json.dumps({"facts": [{"id": "F-97", "statement": "Rates are variable.", "source": "S", "owner": "O",
                                "contradicts": r"guaranteed\s+returns;;fixed\s+for\s+life"}]})
    r = post_import(client, h, ok, "f.json", dry_run=False).json()
    assert r["created"] == ["F-97"]
    f = next(x for x in client.get("/api/facts", headers=h).json() if x["id"] == "F-97")
    assert f["contradicts"] == [r"guaranteed\s+returns", r"fixed\s+for\s+life"]
    nasty = json.dumps([{"id": "F-98", "statement": "x", "source": "S", "owner": "O", "contradicts": "(a+)+$"}])
    assert post_import(client, h, nasty, "f.json").json()["errors"]


def test_unreadable_files_are_refused_with_a_reason(client):
    h = owner(client)
    assert post_import(client, h, b"\xff\xfe\x00bad", "x.csv").status_code == 422
    assert post_import(client, h, "", "x.csv").status_code == 422
    assert post_import(client, h, "[1,2]", "x.json").status_code == 422
    assert post_import(client, h, b"a" * 1_100_000, "x.csv").status_code == 422
    assert post_import(client, h, "name,value\nx,1\n", "x.csv").status_code == 422


def test_import_is_audited_and_runs_the_stale_scan(client, monkeypatch):
    from app import stale
    calls = []
    monkeypatch.setattr(stale, "scan", lambda db, actor, trigger, asset_id=None: calls.append(trigger) or [])
    h = owner(client)
    post_import(client, h, CSV_OK, dry_run=False)
    assert calls and "fact import" in calls[0]
    actions = [a["action"] for a in client.get("/api/audit", headers=h).json()["rows"]] if isinstance(client.get("/api/audit", headers=h).json(), dict) else [a["action"] for a in client.get("/api/audit", headers=h).json()]
    assert "facts.import" in actions and "fact.create" in actions


def test_template_downloads_and_is_valid(client):
    r = client.get("/api/facts/import-template", headers=login(client))
    assert r.status_code == 200 and r.text.startswith("id,statement")
    assert not post_import(client, owner(client), r.text).json()["errors"]


# ------------------------------------------------------------------ feed
def test_feed_url_guard(monkeypatch):
    from app import facts_import as fi
    for url in ("ftp://x.example/f", "http://example.com/f", "https:///nohost", "https://127.0.0.1/f", "https://10.0.0.5/f",
                "https://169.254.169.254/latest", "https://[::1]/f"):
        monkeypatch.delenv("BP_FEED_ALLOW_HTTP", raising=False)
        monkeypatch.delenv("BP_FEED_ALLOW_PRIVATE", raising=False)
        with pytest.raises(fi.ImportProblem):
            fi.check_feed_url(url)
    monkeypatch.setenv("BP_FEED_ALLOW_HTTP", "1")
    monkeypatch.setenv("BP_FEED_ALLOW_PRIVATE", "1")
    fi.check_feed_url("http://127.0.0.1:9000/f")


def test_feed_sync_flow(client, monkeypatch):
    from app import facts_import as fi
    h = owner(client)
    assert client.post("/api/facts/feed/sync", headers=h).status_code == 422  # not configured
    monkeypatch.setenv("BP_FACT_FEED_URL", "https://feeds.example.com/rates.json")
    feed = json.dumps([{"id": "F-80", "statement": "Savings rate is 6.5%.", "valid_to": "2027-03-31"}]).encode()
    monkeypatch.setattr(fi, "fetch_feed", lambda: feed)
    r = client.post("/api/facts/feed/sync", headers=h).json()
    assert r["created"] == ["F-80"] and r["feed"] == "feeds.example.com"
    f = next(x for x in client.get("/api/facts", headers=h).json() if x["id"] == "F-80")
    assert f["owner"] == "Fact feed" and f["source"].startswith("Feed:")
    # a feed may not carry matching rules
    evil = json.dumps([{"id": "F-81", "statement": "x", "contradicts": "anything"}]).encode()
    monkeypatch.setattr(fi, "fetch_feed", lambda: evil)
    r = client.post("/api/facts/feed/sync", headers=h).json()
    assert r["created"] == [] and r["errors"]


def test_feed_is_never_called_in_confidential_mode(client, monkeypatch):
    from app import facts_import as fi
    h = owner(client)
    monkeypatch.setenv("BP_FACT_FEED_URL", "https://feeds.example.com/rates.json")
    monkeypatch.setattr(fi, "fetch_feed", lambda: (_ for _ in ()).throw(AssertionError("the feed must not be called")))
    client.put("/api/settings", headers=h, json={"confidential_mode": True})
    r = client.post("/api/facts/feed/sync", headers=h).json()
    assert "Confidential" in r["skipped"]
    assert client.get("/api/facts/feed", headers=h).json()["confidential"] is True


# ------------------------------------------------------------------ scheduler
def test_scheduler_run_is_logged_and_reported(client, dbs, monkeypatch):
    from app import schedule
    h = owner(client)
    assert client.get("/api/facts/feed", headers=h).json()["last_run"] is None
    res = schedule.run_once(dbs)
    assert res["feed"] == "not configured" and "new_stale_alerts" in res
    st = client.get("/api/facts/feed", headers=h).json()
    assert st["last_run"] and st["enabled"] and st["next_run"] and st["last_result"]["feed"] == "not configured"


def test_scheduler_interval_and_off_switch(monkeypatch):
    import asyncio
    from app import schedule
    monkeypatch.setenv("BP_STALE_SCAN_HOURS", "0")
    assert schedule.interval_hours() == 0
    asyncio.run(asyncio.wait_for(schedule.loop(), 1))  # returns at once when switched off
    monkeypatch.setenv("BP_STALE_SCAN_HOURS", "nonsense")
    assert schedule.interval_hours() == 24


def test_a_failing_feed_does_not_stop_the_scheduled_scan(dbs, monkeypatch):
    from app import facts_import as fi, schedule
    monkeypatch.setenv("BP_FACT_FEED_URL", "https://feeds.example.com/rates.json")
    monkeypatch.setattr(fi, "fetch_feed", lambda: (_ for _ in ()).throw(fi.ImportProblem("The feed could not be reached.")))
    res = schedule.run_once(dbs)
    assert res["feed"].startswith("failed:") and "new_stale_alerts" in res


# ------------------------------------------------------------------ pictures: logo and colour
def _logo(size=200):
    im = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(im)
    d.ellipse((10, 10, size - 10, size - 10), fill=(14, 124, 123))
    d.rectangle((size * .3, size * .3, size * .7, size * .55), fill="white")
    d.polygon([(size * .35, size * .75), (size * .65, size * .75), (size * .5, size * .6)], fill=(20, 33, 61))
    d.rectangle((size * .42, size * .15, size * .58, size * .28), fill=(252, 163, 17))
    return im


def _png(im):
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def _canvas(logo, size, pos=(80, 90), clutter=False, bg=(245, 245, 240)):
    cv = Image.new("RGB", (800, 500), bg)
    d = ImageDraw.Draw(cv)
    if clutter:
        for i in range(0, 800, 7):
            d.line((i, 0, i, 500), fill=(30, 30, 30), width=2)
        d.rectangle((pos[0] - 4, pos[1] - 4, pos[0] + size[0] + 4, pos[1] + size[1] + 4), fill=bg)
    cv.paste(logo.resize(size), pos)
    d.rectangle((420, 300, 760, 420), fill=(14, 124, 123))
    return cv


def _check(client, img):
    h = login(client)
    r = client.post("/api/assets", headers=h, data={"title": "Picture", "intent": "Show the logo", "channel": "social", "alt_text": "Brand banner"},
                    files={"file": ("p.png", _png(img), "image/png")})
    assert r.status_code == 200, r.text
    b = client.get(f"/api/assets/{r.json()['id']}", headers=h).json()
    return b


def _upload_logo(client):
    r = client.post("/api/library/logo", headers=owner(client), data={"name": "Finora mark"}, files={"file": ("logo.png", _png(_logo()), "image/png")})
    assert r.status_code == 200, r.text


def vis(b, rid):
    return [f for f in b["findings"] if f["rule_id"] == rid]


def test_a_correct_logo_raises_nothing(client):
    _upload_logo(client)
    b = _check(client, _canvas(_logo(), (160, 160)))
    assert not vis(b, "VIS-02")
    assert any("image matching" in x for x in b["run"]["not_checked"])


def test_a_stretched_logo_is_flagged(client):
    _upload_logo(client)
    b = _check(client, _canvas(_logo(), (260, 130)))
    assert any("stretched" in f["explanation"] for f in vis(b, "VIS-02"))


def test_a_tiny_logo_is_flagged(client):
    _upload_logo(client)
    b = _check(client, _canvas(_logo(), (28, 28)))
    assert any("minimum" in f["explanation"] for f in vis(b, "VIS-02"))


def test_content_in_the_clear_space_is_flagged(client):
    _upload_logo(client)
    b = _check(client, _canvas(_logo(), (160, 160), pos=(80, 90), clutter=True))
    assert any("clear space" in f["explanation"] for f in vis(b, "VIS-02"))


def test_no_logo_uploaded_is_listed_as_not_checked(client):
    h = owner(client)
    for i in client.get("/api/library", headers=h).json():
        if i["kind"] == "logo":
            client.delete(f"/api/library/{i['id']}", headers=h)
    b = _check(client, _canvas(_logo(), (160, 160)))
    assert not vis(b, "VIS-02")
    assert any("No approved logo" in x for x in b["run"]["not_checked"])


def test_off_palette_picture_colour_is_flagged_and_on_palette_is_not(client):
    off = Image.new("RGB", (800, 500), (255, 0, 140))
    assert vis(_check(client, off), "VIS-01")
    on = Image.new("RGB", (800, 500), (14, 124, 123))
    ImageDraw.Draw(on).rectangle((0, 300, 800, 500), fill=(20, 33, 61))
    assert not vis(_check(client, on), "VIS-01")


# ------------------------------------------------------------------ browser extension package
EXT = os.path.join(os.path.dirname(__file__), "..", "..", "extension")


def test_extension_package_is_safe_and_complete():
    m = json.load(open(os.path.join(EXT, "manifest.json")))
    assert m["manifest_version"] == 3
    assert "<all_urls>" not in m.get("host_permissions", []) and not m.get("host_permissions")
    assert set(m["permissions"]) <= {"activeTab", "scripting", "storage", "contextMenus"}
    assert m["background"]["service_worker"] and os.path.exists(os.path.join(EXT, m["background"]["service_worker"]))
    assert os.path.exists(os.path.join(EXT, m["action"]["default_popup"]))
    for p in m["icons"].values():
        assert os.path.exists(os.path.join(EXT, p))
    assert "content_security_policy" not in m or "unsafe-eval" not in json.dumps(m["content_security_policy"])
    for f in os.listdir(EXT):
        if f.endswith((".js", ".html")):
            src = open(os.path.join(EXT, f)).read()
            assert "innerHTML" not in src and "eval(" not in src, f"{f} must not build markup from server text"
            assert "http://" not in src.replace("http://localhost", "").replace("http://127.0.0.1", "") or f.endswith(".html")
