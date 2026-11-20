"""Rulebook Red-Team (I3). An adversary writes content that breaks a rule but tries to slip past it.
Every miss is a loophole. The tool proposes a tighter rule, the owner approves it, and the variants are re-tested.

Round 3 additions:
  * Train / hold-out split. A proposal is derived only from the TRAIN variants. The HOLD-OUT variants are never used
    to write the proposal, so catching them after approval shows the rule generalised, not that it memorised.
    Hold-out variants that are still missed are reported as open loopholes, not hidden.
  * Hinglish spelling variants and Devanagari are fixed with `translit_phrases` (see translit.py).
  * False-positive guard. A proposal is checked against normal copy (a fixed corpus, plus compliant sentences the
    AI writes when a key is set). Phrases that would flag normal copy are dropped; if the rule still flags it,
    the proposal is blocked and cannot be approved.
  * Fresh AI variants. Each run tells the AI adversary which variants were already tried and asks for new ones.
"""
import copy
import re
from types import SimpleNamespace

from . import textutil as tu
from . import translit
from . import trust
from .rules import TEXT_METHODS, Ctx

ELIGIBLE = {"TERM-01", "TONE-04", "MSG-07", "ASCI-02"}

# (text, phrase_to_add, technique). phrase None means the fix is a parameter change, not a new phrase.
HAND = {
    "TERM-01": [
        ("You simply cannot lose money with Finora Save.", "cannot lose money", "euphemism"),
        ("Your returns are locked in, forever.", "returns are locked in", "euphemism"),
        ("Enjoy assured income every month.", "assured income", "synonym"),
        ("Pakka munafa, bilkul safe.", "pakka munafa", "hinglish"),
        ("Paka munaafa har mahine.", "paka munaafa", "hinglish spelling"),
        ("Garanteed returns on every deposit.", "garanteed returns", "misspelling"),
        ("Returns guaranteed* by us.", "returns guaranteed", "word order"),
    ],
    "TONE-04": [
        ("The offer disappears at midnight, so grab it now.", "grab it now", "euphemism"),
        ("Don't wait, this will not last.", "will not last", "euphemism"),
        ("Be quick, spots are running out!", "spots are running out", "euphemism"),
        ("Abhi hi karo, warna chhoot jayega.", "abhi hi karo", "hinglish"),
        ("Jaldee karo, offer khatam hone wala hai.", "jaldee karo", "hinglish spelling"),
        ("Act  now and save.", None, "double space"),
        ("A C T   N O W and save.", None, "spaced letters"),
    ],
    "MSG-07": [
        ("Festive cashback offer ends in 3 days.", None, "relative time"),
        ("Special bonus offer, hurry, only 2 days left.", None, "relative time"),
        ("Limited offer valid while 100 slots remain.", None, "number but no date"),
        ("Exclusive discount for the next 50 customers.", None, "number but no date"),
    ],
    "ASCI-02": [
        ("Grow your money at 6.5 percent a year.", "percent", "spelled-out percent"),
        ("Earn 6.5 per cent every year with Finora Save.", "per cent", "spelled-out percent"),
        ("Get a yield you will love on Finora Save.", "yield", "synonym"),
        ("Your balance compounds every month at 6.5 pc.", "pc", "abbreviation"),
    ],
}
# Sentences the rule has never seen. They are NOT used to write a proposal; they only measure how well it generalises.
HOLDOUT = {
    "TERM-01": [
        ("Pakkaa munaaafa, bilkul safe.", "pakka munafa", "hinglish spelling"),
        ("पक्का मुनाफा हर महीने।", "पक्का मुनाफा", "devanagari"),
        ("G.U.A.R.A.N.T.E.E.D returns on every deposit.", "guaranteed returns", "dotted letters"),
        ("Your money can never go down with us.", None, "paraphrase"),
        ("Gaurenteed returns, every single year.", None, "misspelling"),
    ],
    "TONE-04": [
        ("Abhi hee karo, varna chhut jayega.", "abhi hi karo", "hinglish spelling"),
        ("अभी ही करो, मौका मत छोड़ो।", "अभी ही करो", "devanagari"),
        ("Act\u00a0now and start saving.", None, "non-breaking space"),
        ("Don't dilly-dally, sign up today.", None, "paraphrase"),
    ],
    "MSG-07": [
        ("Festive discount ends tomorrow.", None, "relative time"),
        ("Cashback valid for just 48 hours.", None, "relative time"),
        ("Bonus offer closes on Friday.", None, "weekday, no date"),
        ("Offer ends soon, limited seats left.", None, "vague deadline"),
    ],
    "ASCI-02": [
        ("Your savings grow at six and a half percent.", "percent", "spelled-out percent"),
        ("Earn 6.5 pct every year.", None, "abbreviation"),
        ("Enjoy a rate of 6.5 every year.", None, "no unit"),
        ("Get 6.5 per cent a year on Finora Save.", "per cent", "spelled-out percent"),
    ],
}

BENIGN = ["Open an account whenever you are ready.", "Your statement is available in the app.",
          "We are here to help, 9am to 9pm IST.", "Savings goals help you plan ahead.",
          "Download the Finora app from your app store."]
BENIGN_EXTRA = {"MSG-07": ["Refer a friend and earn a ₹200 referral bonus until 31 Dec 2026."],
                "ASCI-02": ["Earn interest up to 6.5% p.a. on Finora Save. T&C apply."]}
# Normal copy a tightened rule must never flag (guards against over-blocking). Includes everyday Hinglish.
CLEAN_CORPUS = [
    "Set a savings goal and watch your progress each month.",
    "Finora Save is simple to open and easy to track.",
    "Your money is held with our banking partner.",
    "Abhi account kholein aur apne goals set karein.",
    "Pakka plan banayein apne savings ka.",
    "Aaram se dekhiye, koi jaldbazi nahi hai.",
    "Interest is credited to your account every month. T&C apply.",
    "Our team will reply within one working day.",
    "The offer is valid until 31 Dec 2026.",
    "Returns can go up or down. T&C apply.",
    "Meet Meera, who saved for her first trip.",
    "Statements are available to download at any time.",
    "We never ask for your OTP or password.",
    "Today we are launching a new way to save.",
    "Small deposits add up over time.",
    "Aaj ka din achha hai, apna goal chuniye.",
]


def _obfuscate(phrase: str) -> list[tuple[str, str]]:
    first, _, rest = phrase.partition(" ")
    tail = (" " + rest) if rest else ""
    out = []
    if len(first) >= 4:
        out.append((" ".join(first) + tail, "spaced letters"))
        out.append((".".join(first) + tail, "dotted letters"))
    leet = first.translate(str.maketrans({"a": "4", "e": "3", "i": "1", "o": "0", "s": "5"}))
    if leet != first:
        out.append((leet + tail, "leetspeak"))
    return out


def mutations(rule) -> list[dict]:
    """Mechanical rewrites of phrases already in the rule (keyword-evasion tricks)."""
    out = []
    phrases = [p for p in rule.params.get("phrases", []) if re.fullmatch(r"[a-z' -]+", p) and len(p) >= 5][:4]
    for ph in phrases:
        for text, tech in _obfuscate(ph)[:2] + _obfuscate(ph)[2:3]:
            out.append({"text": f"Finora Save: {text}.", "phrase": None, "technique": tech, "source": "mutation"})
    return out


TRANSLIT_TECHNIQUES = {"hinglish", "hinglish spelling", "devanagari"}


def handwritten(rule_id: str) -> list[dict]:
    train = [{"text": t, "phrase": ph, "technique": tech, "source": "handwritten", "split": "train"}
             for t, ph, tech in HAND.get(rule_id, [])]
    hold = [{"text": t, "phrase": ph, "technique": tech, "source": "handwritten", "split": "holdout"}
            for t, ph, tech in HOLDOUT.get(rule_id, [])]
    return train + hold


def _clean_strs(items, limit: int, maxlen: int = 240) -> list[str]:
    return [x.strip()[:maxlen] for x in (items if isinstance(items, list) else [])
            if isinstance(x, str) and x.strip()][:limit]


def llm_variants(rule, gateway, asset_id=None, known=()) -> list[dict]:
    """Fresh adversarial sentences from the AI. `known` are texts already tried in earlier runs, so the model is
    asked for new ones. Even-numbered variants are used to write the proposal, odd-numbered ones are held back."""
    if gateway is None or not gateway.enabled:
        return []
    system = "You are a red-team tester for a brand rulebook. Reply with JSON only."
    avoid = "\n".join(f"- {k}" for k in list(known)[:30])
    user = (f"Rule {rule.rule_id}: {rule.title}. {rule.description}\nCurrent phrases: {rule.params.get('phrases', [])}\n"
            + (f"These were already tried; write different ones:\n{avoid}\n" if avoid else "")
            + 'Write 8 short marketing sentences that clearly break this rule in spirit but are worded to evade keyword matching '
            '(euphemisms, Hinglish, misspellings, spacing). Return {"variants":[{"text":"...","core_phrase":"the exact words that break the rule, copied from text","technique":"..."}]}.')
    data = gateway.call_json("redteam_variants", system, user, asset_id=asset_id, max_tokens=1200)
    out = []
    variants = (data or {}).get("variants", [])
    for i, v in enumerate((variants if isinstance(variants, list) else [])[:10]):
        if not isinstance(v, dict):
            continue
        text, core = str(v.get("text", "")).strip(), str(v.get("core_phrase", "")).strip()
        if text and text not in known:
            out.append({"text": text, "phrase": core if core and core.lower() in text.lower() else None,
                        "technique": str(v.get("technique", "llm"))[:40], "source": "llm",
                        "split": "train" if i % 2 == 0 else "holdout"})
    return out


def llm_benign(rule, gateway, asset_id=None) -> list[str]:
    """Compliant sentences that sound close to the rule, written by the AI, to catch over-blocking."""
    if gateway is None or not gateway.enabled:
        return []
    system = "You write test sentences for a brand rulebook. Reply with JSON only."
    user = (f"Rule {rule.rule_id}: {rule.title}. {rule.description}\n"
            'Write 6 short marketing sentences for a savings app that are fully COMPLIANT with this rule but use nearby wording '
            'a keyword filter might wrongly flag. Return {"sentences":["..."]}.')
    data = gateway.call_json("redteam_benign", system, user, asset_id=asset_id, max_tokens=600)
    return _clean_strs((data or {}).get("sentences"), 6)


def _as_rule(rule, params=None):
    return SimpleNamespace(rule_id=rule.rule_id, method=rule.method, params=params if params is not None else rule.params,
                           description=getattr(rule, "description", ""), title=getattr(rule, "title", ""),
                           severity=getattr(rule, "severity", "medium"), version=getattr(rule, "version", 1))


def caught(rule_like, text: str, ai_generated=False) -> bool:
    clean = trust.analyze_plain_text(text).clean_text
    fn = TEXT_METHODS[rule_like.method]
    return bool(fn(rule_like, clean, Ctx(ai_generated=ai_generated)))


def evaluate(rule, variants, params=None) -> list[dict]:
    rl = _as_rule(rule, params)
    return [{**v, "caught": caught(rl, v["text"])} for v in variants]


def _normal_copy(rule, benign_extra=()) -> list[str]:
    return list(dict.fromkeys(BENIGN + BENIGN_EXTRA.get(rule.rule_id, []) + CLEAN_CORPUS + list(benign_extra)))


def false_positives(rule, params=None, benign_extra=()) -> list[str]:
    """Normal sentences that the rule (with these params) flags and the CURRENT rule does not.
    Only newly introduced false positives count, so a rule's existing quirks do not block a proposal."""
    new, cur = _as_rule(rule, params), _as_rule(rule)
    return [t for t in _normal_copy(rule, benign_extra) if caught(new, t) and not caught(cur, t)]


def _split(r) -> str:
    return r.get("split", "train")


def propose(rule, results: list[dict]) -> tuple[dict, str]:
    """Tighter params and a plain-language reason, written from the missed TRAIN variants only."""
    p = copy.deepcopy(rule.params)
    missed = [r for r in results if not r["caught"] and _split(r) == "train"]
    notes = []
    if rule.method == "phrase":
        add, add_tl = [], []
        for r in missed:
            ph = (r.get("phrase") or "").lower()
            if not ph:
                continue
            if r["technique"] in TRANSLIT_TECHNIQUES:
                if translit.usable(ph) and ph not in [x.lower() for x in p.get("translit_phrases", [])]:
                    add_tl.append(ph)
            elif ph not in [x.lower() for x in p.get("phrases", [])]:
                add.append(ph)
        if any(r["technique"] in ("spaced letters", "dotted letters", "leetspeak", "double space", "misspelling") for r in missed):
            if not p.get("normalize"):
                p["normalize"] = True
                notes.append("turn on spacing/leetspeak-tolerant matching")
        if add:
            p["phrases"] = list(p.get("phrases", [])) + sorted(set(add))
            notes.append(f"add {len(set(add))} phrase(s): " + ", ".join(sorted(set(add))))
        if add_tl:
            p["translit_phrases"] = list(p.get("translit_phrases", [])) + sorted(set(add_tl))
            notes.append("match Hinglish spelling variants and Devanagari for: " + ", ".join(sorted(set(add_tl))))
    elif rule.method == "offer_end_date":
        p["require_date"] = True
        notes.append("require a real calendar date; 'in 3 days' or '100 slots' no longer count")
    elif rule.method == "disclaimer":
        terms = sorted({r["phrase"] for r in missed if r.get("phrase")})
        p["extra_terms"] = sorted(set(p.get("extra_terms", [])) | set(terms))
        notes.append("also treat these words as a rate claim: " + ", ".join(terms))
    return p, "; ".join(notes) or "no automatic change available"


def guarded(rule, results: list[dict], benign_extra=()) -> tuple[dict, str, dict]:
    """propose() followed by the false-positive guard. Returns (params, rationale, guard).
    guard = {"blocked": bool, "false_positives": [...], "dropped": [...]}"""
    params, why = propose(rule, results)
    fps = false_positives(rule, params, benign_extra)
    dropped = []
    while fps:
        best = None
        for key in ("phrases", "translit_phrases"):
            for ph in params.get(key, []):
                if ph in rule.params.get(key, []):
                    continue  # only phrases this proposal added may be dropped
                trial = copy.deepcopy(params)
                trial[key] = [x for x in trial[key] if x != ph]
                n = len(false_positives(rule, trial, benign_extra))
                if n < len(fps) and (best is None or n < best[0]):
                    best = (n, key, ph, trial)
        if best is None:
            break
        _, key, ph, params = best
        dropped.append(ph)
        fps = false_positives(rule, params, benign_extra)
    if dropped:
        why += f"; dropped {len(dropped)} phrase(s) that would flag normal copy: " + ", ".join(dropped)
    if fps:
        why += "; BLOCKED: this change would flag normal copy, so it cannot be approved as is"
    return params, why, {"blocked": bool(fps), "false_positives": fps, "dropped": dropped}


def summarise(results: list[dict]) -> dict:
    train = [r for r in results if _split(r) == "train"]
    hold = [r for r in results if _split(r) == "holdout"]
    n_c = sum(1 for r in train if r["caught"])
    return {"total": len(train), "caught": n_c, "missed": len(train) - n_c,
            "catch_rate": round(n_c / len(train), 2) if train else 0.0,
            "holdout": {"total": len(hold), "caught": sum(1 for r in hold if r["caught"]),
                        "open": [r["text"] for r in hold if not r["caught"]]},
            "sources": sorted({r["source"] for r in results})}


def run_variants(rule, gateway=None, asset_id=None, known=()) -> tuple[list[dict], dict]:
    variants = handwritten(rule.rule_id) + [{**m, "split": "train"} for m in mutations(rule)] \
        + llm_variants(rule, gateway, asset_id, known)
    results = evaluate(rule, variants)
    summary = summarise(results)
    summary["benign_llm"] = llm_benign(rule, gateway, asset_id)
    return results, summary


def retest(rule, results: list[dict], params: dict, benign_extra=()) -> dict:
    base = [{k: v for k, v in r.items() if k != "caught"} for r in results]
    after = evaluate(rule, base, params)
    train_b = [r for r in results if _split(r) == "train"]
    train_a = [r for r in after if _split(r) == "train"]
    hold_b = [r for r in results if _split(r) == "holdout"]
    hold_a = [r for r in after if _split(r) == "holdout"]
    return {"total": len(train_b), "before_caught": sum(1 for r in train_b if r["caught"]),
            "after_caught": sum(1 for r in train_a if r["caught"]),
            "still_missed": [r["text"] for r in train_a if not r["caught"]],
            "holdout_total": len(hold_b), "holdout_before": sum(1 for r in hold_b if r["caught"]),
            "holdout_after": sum(1 for r in hold_a if r["caught"]),
            "holdout_open": [r["text"] for r in hold_a if not r["caught"]],
            "false_positives": false_positives(rule, params, benign_extra)}
