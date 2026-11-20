"""The scoreboard itself is tested: it must be honest and it must not regress."""
from app.engine import trust_suite
from conftest import login


def test_every_attack_except_the_declared_gaps_is_caught_and_no_control_is_flagged():
    r = trust_suite.run()
    assert r["unexpected_misses"] == [], r["unexpected_misses"]
    assert r["false_alarms"] == [], r["false_alarms"]
    assert r["controls"]["clean"] == r["controls"]["total"] >= 8
    assert r["attacks"]["total"] >= 24


def test_known_gaps_are_reported_as_misses_with_a_reason():
    r = trust_suite.run()
    gaps = {g["id"]: g for g in r["known_gaps"]}
    assert "G01" in gaps and "G02" in gaps
    assert all(g["why"] and g["caught"] is False for g in gaps.values() if g["id"] in ("G01", "G02"))
    assert r["attacks"]["caught"] < r["attacks"]["total"]   # the scoreboard never claims a perfect score


def test_suite_endpoint_needs_login_and_returns_the_scoreboard(client):
    assert client.get("/api/trust/suite").status_code in (401, 403)
    r = client.get("/api/trust/suite", headers=login(client)).json()
    assert r["attacks"]["total"] and {"results", "controls", "known_gaps", "ocr"} <= set(r)
