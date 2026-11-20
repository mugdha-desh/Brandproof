"""Intent Lock v2: structured elements, element-by-element checking, AI elements validated in code."""
from app.engine import intent as it
from conftest import login, make_asset

INTENT = "Announce our new savings account"
OLD = "Our new savings account is here. Open yours in minutes. Act NOW or lose out forever!"


def test_pressure_phrases_are_never_the_creators_cta():
    assert it.find_cta("Act NOW or lose out forever!") == ""
    assert it.find_cta("A C T  N O W") == ""
    assert it.find_cta("Open yours in minutes.").lower().startswith("open yours")


def test_offline_elements_cover_subject_and_cta():
    kinds = {e["kind"] for e in it.extract_offline(INTENT, OLD)}
    assert {"subject", "cta"} <= kinds


def test_fix_that_drops_the_cta_fails_intent_lock():
    els = it.extract_offline(INTENT, OLD)
    bad = it.check(els, INTENT, OLD, "Our new savings account is here.")
    assert not bad["passed"] and any(e["kind"] == "cta" and e["status"] == "lost" for e in bad["elements"])
    assert "cta" in bad["reason"].lower()


def test_removing_only_the_pressure_phrase_passes():
    els = it.extract_offline(INTENT, OLD)
    ok = it.check(els, INTENT, OLD, "Our new savings account is here. Open yours in minutes.")
    assert ok["passed"] and all(e["status"] in ("kept", "n/a") for e in ok["elements"])


def test_element_already_missing_before_the_fix_is_not_blamed_on_the_fix():
    els = it.extract_offline(INTENT, "Our new savings account is here. Open yours in minutes.")
    old_without_cta = "Our new savings account is here."
    r = it.check(els, INTENT, old_without_cta, "Our savings account is here.")
    assert [e for e in r["elements"] if e["kind"] == "cta"][0]["status"] == "n/a"


class FakeGateway:
    enabled = True

    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def call_json(self, *a, **k):
        self.calls += 1
        return self.reply


def test_ai_elements_must_quote_real_text():
    gw = FakeGateway({"elements": [
        {"kind": "cta", "text": "open an account", "quote": "Open yours in minutes"},
        {"kind": "offer", "text": "free gold coin", "quote": "win a free gold coin"},      # invented: dropped
        {"kind": "bogus", "text": "x", "quote": "Our new savings account is here"},        # unknown kind: dropped
        {"kind": "cta", "text": "hurry", "quote": "Act NOW"},                               # pressure phrase: dropped
    ]})
    els = it.extract_ai(INTENT, OLD, gw)
    assert [(e["kind"], e["source"]) for e in els] == [("cta", "ai")]


def test_ai_failure_falls_back_to_code():
    for bad in (None, {"elements": "nope"}, {}):
        els = it.extract(INTENT, OLD, FakeGateway(bad))
        assert {e["kind"] for e in els} >= {"subject", "cta"} and all(e["source"] == "code" for e in els)


def test_elements_are_stored_once_and_returned_by_the_api(client):
    h = login(client)
    aid = make_asset(client, h, OLD)
    d = client.get(f"/api/assets/{aid}", headers=h).json()
    assert {e["kind"] for e in d["intent_elements"]} >= {"subject", "cta"}
    tone = [f for f in d["findings"] if f["rule_id"] == "TONE-04"][0]
    il = tone["fix"]["verification"]["intent_lock"]
    assert tone["fix"]["status"] == "verified" and il["method"] == "elements"
    assert {e["kind"] for e in il["elements"]} >= {"subject", "cta"}
    f = client.post(f"/api/findings/{tone['id']}/decision", headers=h, json={"action": "accept_fix"}).json()
    assert [e["kind"] for e in f["intent_elements"]] == [e["kind"] for e in d["intent_elements"]]  # not re-derived
    assert "Open yours" in f["version"]["text"]
