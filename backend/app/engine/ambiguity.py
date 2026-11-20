"""Ambiguity score for a rule (I3). A rule is unclear when people or the AI cannot agree what it means.

Three signals, each 0 to 1, combined as a weighted mean over the signals that have evidence:
  override  (0.4) share of decided findings that reviewers rejected or waived.
  split     (0.3) how evenly reviewers are divided: 4 * p * (1 - p), where p is the override share. Unanimous = 0.
  ai        (0.3) disagreement between repeated runs of the AI judge on the same texts (needs an LLM key).

The diagnosis tells the owner what to do:
  unclear   people or AI disagree: rewrite the rule with examples.
  ignored   people consistently override it: the rule may be wrong, out of date or too broad.
  healthy   no sign of trouble. 'not enough data' means fewer than 3 decisions and no AI probe.
"""
from . import judgment

MIN_DECIDED = 3
WEIGHTS = {"override": 0.4, "split": 0.3, "ai": 0.3}

# Borderline copy for the AI-judged tone rules: honest people could read these either way.
BORDERLINE = {
    "TONE-01": ["Everyone knows saving early matters.", "Obviously, a goal helps, so set one today.",
                "No excuses: even ₹100 a month counts.", "You already know you should be saving.",
                "What are you waiting for? Your future self will thank you."],
    "TONE-02": ["Inflation reduces what your savings can buy over time.", "Don't wait to start; small steps add up.",
                "Many people feel anxious about money, and that is normal.", "Prices rise every year, so plan ahead.",
                "Your savings deserve a plan before the year ends."],
    "TONE-03": ["Unlike some apps, we show every fee up front.", "Other apps can be confusing; we aim to be clear.",
                "We are different from a traditional bank.", "Switching from another app takes five minutes.",
                "Some providers hide charges; we do not."],
}


def split_signal(overridden: int, decided: int) -> float:
    if decided <= 0:
        return 0.0
    p = overridden / decided
    return round(4 * p * (1 - p), 2)


def combine(overridden: int, decided: int, ai: float | None) -> dict:
    """Score, diagnosis and plain-language reasons for one rule."""
    sig, reasons = {}, []
    rate = round(overridden / decided, 2) if decided else 0.0
    if decided >= MIN_DECIDED:
        sig["override"], sig["split"] = rate, split_signal(overridden, decided)
        if rate >= 0.34:
            reasons.append(f"Overridden in {overridden} of {decided} decisions.")
        if sig["split"] >= 0.7:
            reasons.append(f"Reviewers are split ({decided - overridden} accepted, {overridden} overridden).")
    if ai is not None:
        sig["ai"] = ai
        if ai >= 0.3:
            reasons.append(f"The AI judge disagreed with itself on {round(ai * 100)}% of probe texts.")
    if not sig:
        return {"ambiguity_score": None, "diagnosis": "not enough data", "ambiguity_reasons": [], "signals": {}}
    total_w = sum(WEIGHTS[k] for k in sig)
    score = round(sum(WEIGHTS[k] * v for k, v in sig.items()) / total_w, 2)
    if (ai is not None and ai >= 0.3) or (sig.get("split", 0) >= 0.7 and decided >= 4):
        diagnosis = "unclear"
    elif sig.get("override", 0) >= 0.34:
        diagnosis = "ignored"
    else:
        diagnosis = "healthy"
    return {"ambiguity_score": score, "diagnosis": diagnosis, "ambiguity_reasons": reasons, "signals": sig}


def probe(rule, texts: list[str], gateway, runs: int = 3, asset_id=None) -> dict | None:
    """Run the AI judge `runs` times on each text (cache bypassed) and measure disagreement about whether the rule
    fires. Returns None when no AI is configured or no text got at least two successful runs."""
    if gateway is None or not gateway.enabled:
        return None
    detail = []
    for text in texts:
        fires = ok = 0
        for _ in range(runs):
            res = judgment.run_ai([rule], text, gateway, asset_id, use_cache=False)
            if res is None:
                continue
            ok += 1
            fires += any(f["rule"].rule_id == rule.rule_id and f["confidence"] >= 0.5 for f in res)
        if ok >= 2:
            detail.append({"text": text, "runs": ok, "fired": fires,
                           "disagreement": round(2 * (1 - max(fires, ok - fires) / ok), 2)})
    if not detail:
        return None
    return {"disagreement": round(sum(d["disagreement"] for d in detail) / len(detail), 2), "detail": detail}
