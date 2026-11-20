"""Round 3 Step 3: I3 complete. Transliteration, hold-out set, false-positive guard, fresh AI variants, ambiguity."""
import json
from types import SimpleNamespace

import httpx
import pytest

from app.engine import ambiguity, redteam, translit
from app.llm import adapter
from app.seed import RULES
from conftest import login, make_asset


def rule_of(rid):
    r = [x for x in RULES if x[0] == rid][0]
    return SimpleNamespace(rule_id=r[0], title=r[1], method=r[4], params=r[5], description=r[6], severity=r[3], version=1)


# ------------------------------------------------------------------ transliteration
@pytest.mark.parametrize("phrase,text", [
    ("pakka munafa", "Pakkaa munaafa har mahine"), ("pakka munafa", "paka munapha"), ("pakka munafa", "पक्का मुनाफा"),
    ("abhi hi karo", "Abhi hee karo"), ("abhi hi karo", "अभी ही करो"), ("jaldi karo", "jaldee karo"),
    ("chhoot jayega", "chut jaega"),
])
def test_spelling_variants_and_devanagari_match(phrase, text):
    assert translit.find(text, phrase)


def test_translit_does_not_match_ordinary_hinglish_or_short_phrases():
    assert not translit.find("Pakka plan banayein apne savings ka.", "pakka munafa")
    assert not translit.find("Abhi account kholein, aaram se.", "abhi hi karo")
    assert not translit.usable("hi")            # too short to be matched loosely
    assert translit.find("xx hi yy", "hi") == []


def test_translit_span_covers_the_whole_phrase():
    text = "Offer: Pakkaa munaafa today."
    (s, e), = translit.find(text, "pakka munafa")
    assert text[s:e] == "Pakkaa munaafa"


# ------------------------------------------------------------------ hold-out discipline
def test_proposal_is_written_from_train_variants_only():
    rule = rule_of("TERM-01")
    results = [
        {"text": "a", "phrase": "train only phrase", "technique": "euphemism", "source": "x", "split": "train", "caught": False},
        {"text": "b", "phrase": "holdout secret phrase", "technique": "euphemism", "source": "x", "split": "holdout", "caught": False},
    ]
    params, why = redteam.propose(rule, results)
    assert "train only phrase" in params["phrases"] and "holdout secret phrase" not in params["phrases"]


def test_holdout_shows_generalisation_and_reports_open_loopholes():
    rule = rule_of("TERM-01")
    results, summary = redteam.run_variants(rule)
    assert summary["holdout"]["total"] >= 4 and summary["holdout"]["caught"] == 0
    params, _, guard = redteam.guarded(rule, results)
    rt = redteam.retest(rule, results, params)
    assert rt["holdout_after"] > rt["holdout_before"]                 # Hinglish spellings and Devanagari generalise
    assert rt["holdout_after"] < rt["holdout_total"]                  # paraphrase and misspelling stay open, and we say so
    assert any("never go down" in t for t in rt["holdout_open"])
    assert not guard["blocked"] and rt["false_positives"] == []


def test_every_eligible_rule_has_a_holdout_set():
    for rid in redteam.ELIGIBLE:
        assert redteam.HOLDOUT.get(rid), rid


def test_approved_rule_catches_devanagari_in_a_real_submission(client):
    owner, c = login(client, "owner@finora.example"), login(client)
    run = client.post("/api/redteam/run", headers=owner, json={"rule_id": "TERM-01"}).json()
    client.post(f"/api/redteam/proposals/{run['proposal']['id']}/decision", headers=owner, json={"action": "approve"})
    run2 = client.post("/api/redteam/run", headers=owner, json={"rule_id": "TERM-01"}).json()
    assert run2["summary"]["holdout"]["caught"] > 0
    aid = make_asset(client, c, "पक्का मुनाफा हर महीने, Finora Save के साथ।")
    d = client.get(f"/api/assets/{aid}", headers=c).json()
    assert "TERM-01" in {f["rule_id"] for f in d["findings"]}


# ------------------------------------------------------------------ false-positive guard
def test_guard_drops_added_phrases_that_flag_normal_copy():
    rule = rule_of("TONE-04")
    results = [{"text": "t", "phrase": "set a savings goal", "technique": "euphemism", "source": "x", "split": "train", "caught": False},
               {"text": "u", "phrase": "will not last", "technique": "euphemism", "source": "x", "split": "train", "caught": False}]
    params, why, guard = redteam.guarded(rule, results)
    assert "set a savings goal" not in params["phrases"] and "will not last" in params["phrases"]
    assert guard["dropped"] == ["set a savings goal"] and not guard["blocked"]
    assert "dropped 1 phrase" in why


def test_guard_blocks_a_change_it_cannot_repair():
    rule = rule_of("ASCI-02")
    results = [{"text": "t", "phrase": "statements", "technique": "x", "source": "x", "split": "train", "caught": False}]
    params, why, guard = redteam.guarded(rule, results)
    assert guard["blocked"] and guard["false_positives"] and "BLOCKED" in why


def test_ai_written_compliant_sentences_extend_the_guard():
    rule = rule_of("TONE-04")
    params = {**rule.params, "phrases": rule.params["phrases"] + ["start saving"]}
    assert redteam.false_positives(rule, params) == []
    assert redteam.false_positives(rule, params, ["We help you start saving today."]) == ["We help you start saving today."]


def test_blocked_proposal_cannot_be_approved_and_stale_one_cannot_either(client, dbs):
    from app.db import RedTeamRun, RuleProposal
    owner = login(client, "owner@finora.example")
    rule = rule_of("ASCI-02")
    results = [{"text": "t", "phrase": "statements", "technique": "x", "source": "x", "split": "train", "caught": False}]
    params, why, guard = redteam.guarded(rule, results)
    row = RedTeamRun(rule_id="ASCI-02", rule_version=1, created_by="t", results=results, summary={"benign_llm": []}, variants=[])
    dbs.add(row); dbs.flush()
    p = RuleProposal(run_id=row.id, rule_id="ASCI-02", base_version=1, proposed_params=params, rationale=why)
    dbs.add(p); dbs.commit()
    r = client.post(f"/api/redteam/proposals/{p.id}/decision", headers=owner, json={"action": "approve"})
    assert r.status_code == 409 and "normal copy" in r.json()["detail"]
    # two proposals from the same version: the second becomes stale once the first is approved
    a = client.post("/api/redteam/run", headers=owner, json={"rule_id": "MSG-07"}).json()["proposal"]["id"]
    b = client.post("/api/redteam/run", headers=owner, json={"rule_id": "MSG-07"}).json()["proposal"]["id"]
    assert client.post(f"/api/redteam/proposals/{a}/decision", headers=owner, json={"action": "approve"}).status_code == 200
    stale = client.post(f"/api/redteam/proposals/{b}/decision", headers=owner, json={"action": "approve"})
    assert stale.status_code == 409 and "changed" in stale.json()["detail"]


# ------------------------------------------------------------------ fresh AI variants
class FakeGW:
    enabled = True

    def __init__(self, variants=None, benign=None):
        self.variants, self.benign, self.prompts = variants or [], benign or [], []

    def call_json(self, purpose, system, user, **kw):
        self.prompts.append((purpose, user))
        return {"variants": self.variants} if purpose == "redteam_variants" else {"sentences": self.benign}


def test_ai_variants_are_validated_split_and_exclude_known():
    rule = rule_of("TONE-04")
    gw = FakeGW([{"text": f"Move fast number {i}, offer fading", "core_phrase": "move fast" if i % 2 == 0 else "not in text", "technique": "euphemism"}
                 for i in range(6)] + ["junk", {"text": ""}, {"text": "Move fast number 0, offer fading"}])
    out = redteam.llm_variants(rule, gw, known=["Move fast number 0, offer fading"])
    assert len(out) == 5 and all(v["source"] == "llm" for v in out)
    assert {v["split"] for v in out} == {"train", "holdout"}
    assert all(v["phrase"] in (None, "move fast") for v in out)
    assert "Move fast number 0, offer fading" in gw.prompts[0][1]       # told what was already tried


def test_ai_benign_sentences_are_cleaned():
    gw = FakeGW(benign=["Fine one.", "", 5, "x" * 500, "Fine two."])
    got = redteam.llm_benign(rule_of("TONE-04"), gw)
    assert got[0] == "Fine one." and got[1] == "x" * 240 and got[2] == "Fine two." and len(got) == 3
    assert redteam.llm_variants(rule_of("TONE-04"), None) == [] and redteam.llm_benign(rule_of("TONE-04"), None) == []


# ------------------------------------------------------------------ ambiguity score
def test_unanimous_override_is_ignored_not_unclear():
    a = ambiguity.combine(overridden=4, decided=4, ai=None)
    assert a["diagnosis"] == "ignored" and a["signals"]["split"] == 0 and a["ambiguity_score"] >= 0.5


def test_split_decisions_are_unclear():
    a = ambiguity.combine(overridden=3, decided=6, ai=None)
    assert a["diagnosis"] == "unclear" and any("split" in r for r in a["ambiguity_reasons"])


def test_healthy_and_not_enough_data():
    assert ambiguity.combine(0, 8, None)["diagnosis"] == "healthy"
    n = ambiguity.combine(1, 2, None)
    assert n["diagnosis"] == "not enough data" and n["ambiguity_score"] is None


def test_ai_disagreement_alone_makes_a_rule_unclear():
    a = ambiguity.combine(0, 0, 0.5)
    assert a["diagnosis"] == "unclear" and a["ambiguity_score"] == 0.5 and "disagreed with itself" in a["ambiguity_reasons"][0]


class FlakyGW:
    enabled = True

    def __init__(self, flaky):
        self.flaky, self.n, self.seen = flaky, 0, []

    def call_json(self, purpose, system, user, use_cache=True, **kw):
        self.seen.append(use_cache)
        self.n += 1
        fire = self.flaky and self.n % 2 == 0
        return {"findings": [{"rule_id": "TONE-01", "quote": "Everyone knows", "explanation": "x", "confidence": 0.9}] if fire else []}


def test_probe_measures_disagreement_and_bypasses_the_cache():
    rule = rule_of("TONE-01")
    flaky, stable = FlakyGW(True), FlakyGW(False)
    one = [ambiguity.BORDERLINE["TONE-01"][0]]
    assert ambiguity.probe(rule, one, flaky, runs=4)["disagreement"] == 1.0   # 2 fired, 2 did not
    assert ambiguity.probe(rule, one, stable, runs=3)["disagreement"] == 0.0
    assert not any(flaky.seen)                                                # use_cache=False on every call
    assert ambiguity.probe(rule, one, None) is None


@pytest.fixture
def llm(env, monkeypatch):
    state = {"handler": lambda body: {}, "bodies": []}

    def transport(request: httpx.Request):
        body = json.loads(request.content)
        state["bodies"].append(body)
        return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps(state["handler"](body))}]})

    monkeypatch.setenv("BP_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    adapter.set_transport(httpx.MockTransport(transport))
    yield state
    adapter.set_transport(None)


def test_probe_endpoint_needs_a_key_an_owner_and_a_judgment_rule(client):
    owner, c = login(client, "owner@finora.example"), login(client)
    assert client.post("/api/redteam/ambiguity-probe", headers=c, json={"rule_id": "TONE-01"}).status_code == 403
    assert client.post("/api/redteam/ambiguity-probe", headers=owner, json={"rule_id": "TERM-01"}).status_code == 422
    r = client.post("/api/redteam/ambiguity-probe", headers=owner, json={"rule_id": "TONE-01"})
    assert r.status_code == 409 and "LLM key" in r.json()["detail"]


def test_probe_endpoint_feeds_the_rulebook_health_view(client, llm):
    owner = login(client, "owner@finora.example")
    calls = {"n": 0}

    def handler(body):
        text = body["messages"][0]["content"][0]["text"]
        if "Everyone knows saving early" in text:
            calls["n"] += 1
            if calls["n"] % 2 == 0:
                return {"findings": [{"rule_id": "TONE-01", "quote": "Everyone knows", "explanation": "talks down", "confidence": 0.9}]}
        return {"findings": []}

    llm["handler"] = handler
    r = client.post("/api/redteam/ambiguity-probe", headers=owner, json={"rule_id": "TONE-01", "runs": 4})
    assert r.status_code == 200 and r.json()["disagreement"] > 0 and r.json()["detail"][0]["disagreement"] == 1.0
    row = [x for x in client.get("/api/rulebook", headers=owner).json()["rules"] if x["rule_id"] == "TONE-01"][0]
    assert row["probeable"] and row["probe"]["texts"] == 5 and row["signals"]["ai"] == r.json()["disagreement"]
    assert client.post("/api/redteam/ambiguity-probe", headers=owner, json={"rule_id": "TONE-01", "runs": 9}).status_code == 422
    audit = client.get("/api/audit", headers=owner).json()
    assert any(a["action"] == "rule.ambiguity_probe" for a in (audit if isinstance(audit, list) else audit.get("events", audit.get("items", []))))


def test_rulebook_shows_diagnosis_and_before_after_history(client):
    c, owner = login(client), login(client, "owner@finora.example")
    for i in range(3):
        aid = make_asset(client, c, "Hurry, open Finora Save.", title=f"a{i}")
        f = [x for x in client.get(f"/api/assets/{aid}", headers=c).json()["findings"] if x["rule_id"] == "TONE-04"][0]
        client.post(f"/api/findings/{f['id']}/decision", headers=c, json={"action": "reject", "note": "fine"})
    run = client.post("/api/redteam/run", headers=owner, json={"rule_id": "TONE-04"}).json()
    client.post(f"/api/redteam/proposals/{run['proposal']['id']}/decision", headers=owner, json={"action": "approve"})
    client.post("/api/redteam/run", headers=owner, json={"rule_id": "TONE-04"})
    row = [x for x in client.get("/api/rulebook", headers=owner).json()["rules"] if x["rule_id"] == "TONE-04"][0]
    assert row["diagnosis"] == "ignored" and row["ambiguous"] and row["ambiguity_score"] >= 0.5
    h = row["history"]
    assert len(h) == 2 and h[0]["rule_version"] == 1 and h[1]["rule_version"] == 2
    assert h[1]["caught"] > h[0]["caught"] and h[1]["holdout_caught"] > h[0]["holdout_caught"]
    assert row["redteam"]["holdout_total"] == h[1]["holdout_total"] and row["redteam"]["holdout_open"]
