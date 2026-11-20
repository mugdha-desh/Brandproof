"""The evaluation numbers must come with intervals, and the blind set must keep its misses visible."""
from eval.run_eval import wilson
from conftest import login


def test_wilson_interval_is_wide_for_small_samples_and_bounded():
    lo, hi = wilson(5, 5)
    assert hi == 1.0 and lo < 0.6          # 5 of 5 is NOT proof of 100%
    lo, hi = wilson(0, 0)
    assert (lo, hi) == (0.0, 1.0)
    lo, hi = wilson(50, 100)
    assert 0.39 < lo < 0.41 and 0.59 < hi < 0.61


def test_eval_endpoint_needs_login_and_reports_blind_misses(client):
    assert client.get("/api/eval").status_code in (401, 403)
    r = client.get("/api/eval", headers=login(client)).json()
    assert r["blind"]["items"] >= 30
    assert len(r["blind"]["precision_ci"]) == 2 and len(r["blind"]["recall_ci"]) == 2
    assert r["blind"]["misses"], "the blind set must not be tuned to a perfect score"
    assert r["heldout"] and r["seeded"]["items"] >= 52 and "note" in r
