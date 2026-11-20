from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, service
from ..db import RedTeamRun, Rule, RuleProbe, RuleProposal, User, get_db
from ..engine import ambiguity, redteam
from ..llm.adapter import Gateway
from ..security import current_user, require
from .common import need, ser_rule

router = APIRouter(prefix="/api")


def _current(db: Session, rule_id: str) -> Rule:
    return need(db.execute(select(Rule).where(Rule.rule_id == rule_id, Rule.is_current.is_(True))).scalar_one_or_none(), "Rule")


def ser_run(r: RedTeamRun, p: RuleProposal | None) -> dict:
    return {"id": r.id, "rule_id": r.rule_id, "rule_version": r.rule_version, "created_by": r.created_by,
            "created_at": r.created_at.isoformat(timespec="seconds"), "summary": r.summary, "results": r.results,
            "proposal": None if p is None else {"id": p.id, "status": p.status, "rationale": p.rationale,
                                                "base_version": p.base_version, "proposed_params": p.proposed_params,
                                                "retest": p.retest}}


class RunBody(BaseModel):
    rule_id: str


@router.post("/redteam/run")
def run(b: RunBody, user: User = Depends(require("owner")), db: Session = Depends(get_db)):
    if b.rule_id not in redteam.ELIGIBLE:
        raise HTTPException(422, f"Red-team v1 supports: {', '.join(sorted(redteam.ELIGIBLE))}")
    rule = _current(db, b.rule_id)
    prev = db.execute(select(RedTeamRun).where(RedTeamRun.rule_id == rule.rule_id).order_by(RedTeamRun.id.desc()).limit(3)).scalars().all()
    known = [v["text"] for r in prev for v in r.results if v.get("source") == "llm"]
    results, summary = redteam.run_variants(rule, Gateway(db), known=known)
    row = RedTeamRun(rule_id=rule.rule_id, rule_version=rule.version, created_by=user.email,
                     source="+".join(summary["sources"]), variants=[], results=results, summary=summary)
    db.add(row)
    db.flush()
    prop = None
    if summary["missed"]:
        params, why, guard = redteam.guarded(rule, results, summary["benign_llm"])
        prop = RuleProposal(run_id=row.id, rule_id=rule.rule_id, base_version=rule.version, proposed_params=params, rationale=why)
        prop.retest = {**redteam.retest(rule, results, params, summary["benign_llm"]), "guard": guard}
        db.add(prop)
    audit.log(db, user.email, "redteam.run", "rule", rule.rule_id,
              {"missed": summary["missed"], "total": summary["total"], "holdout": summary["holdout"]["caught"], "holdout_total": summary["holdout"]["total"]})
    db.commit()
    return ser_run(row, prop)


@router.get("/redteam/runs")
def runs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = []
    for r in db.execute(select(RedTeamRun).order_by(RedTeamRun.id.desc()).limit(30)).scalars():
        p = db.execute(select(RuleProposal).where(RuleProposal.run_id == r.id)).scalar_one_or_none()
        out.append(ser_run(r, p))
    return out


class PropDecision(BaseModel):
    action: str  # approve | reject


@router.post("/redteam/proposals/{pid}/decision")
def decide(pid: int, b: PropDecision, user: User = Depends(require("owner")), db: Session = Depends(get_db)):
    p = need(db.get(RuleProposal, pid), "Proposal")
    if p.status != "pending":
        raise HTTPException(409, f"Proposal already {p.status}")
    if b.action == "reject":
        p.status = "rejected"
    elif b.action == "approve":
        cur = _current(db, p.rule_id)
        run_row0 = need(db.get(RedTeamRun, p.run_id), "Run")
        fps = redteam.false_positives(cur, p.proposed_params, run_row0.summary.get("benign_llm", []))
        if fps:  # re-checked at approval time, against the rule that is live now
            raise HTTPException(409, "Blocked: this rule would flag normal copy, e.g. " + " | ".join(fps[:2]))
        if p.base_version != cur.version:
            raise HTTPException(409, f"The rule changed (now v{cur.version}) since this proposal was made; run the red-team again")
        cur.is_current = False
        new = Rule(rule_id=cur.rule_id, version=cur.version + 1, title=cur.title, category=cur.category, severity=cur.severity,
                   description=cur.description, method=cur.method, params=p.proposed_params, status="approved",
                   is_current=True, source=cur.source, created_by=f"{user.email} (red-team proposal #{p.id})")
        db.add(new)
        p.status = "approved"
    else:
        raise HTTPException(422, "action must be approve or reject")
    audit.log(db, user.email, f"redteam.proposal.{b.action}", "rule", p.rule_id,
              {"proposal": p.id, "retest": {k: (p.retest or {}).get(k) for k in ("before_caught", "after_caught", "total", "holdout_before", "holdout_after", "holdout_total")}})
    db.commit()
    run_row = db.get(RedTeamRun, p.run_id)
    return ser_run(run_row, p)


@router.post("/redteam/proposals/{pid}/retest")
def retest_proposal(pid: int, user: User = Depends(require("owner")), db: Session = Depends(get_db)):
    p = need(db.get(RuleProposal, pid), "Proposal")
    run_row = need(db.get(RedTeamRun, p.run_id), "Run")
    rule = _current(db, p.rule_id)
    base = [{k: v for k, v in r.items() if k != "caught"} for r in run_row.results]
    before = redteam.evaluate(rule, base)  # against whatever is live now
    benign = run_row.summary.get("benign_llm", [])
    after = redteam.retest(rule, run_row.results, p.proposed_params, benign)
    fps = after["false_positives"]
    p.retest = {**after, "live_caught_now": sum(1 for r in before if r["caught"]),
                "guard": {**(p.retest or {}).get("guard", {}), "blocked": bool(fps), "false_positives": fps}}
    audit.log(db, user.email, "redteam.retest", "rule", p.rule_id, {"proposal": p.id, "after": after["after_caught"]})
    db.commit()
    return ser_run(run_row, p)


class ProbeBody(BaseModel):
    rule_id: str
    runs: int = 3


def _ser_probe(p: RuleProbe | None) -> dict | None:
    return None if p is None else {"id": p.id, "rule_id": p.rule_id, "rule_version": p.rule_version, "runs": p.runs,
                                   "texts": p.texts, "disagreement": p.disagreement, "detail": p.detail,
                                   "created_at": p.created_at.isoformat(timespec="seconds"), "created_by": p.created_by}


@router.post("/redteam/ambiguity-probe")
def ambiguity_probe(b: ProbeBody, user: User = Depends(require("owner")), db: Session = Depends(get_db)):
    """Run the AI judge several times on borderline texts; disagreement with itself feeds the rule's ambiguity score."""
    rule = _current(db, b.rule_id)
    if rule.method != "judgment" or rule.rule_id not in ambiguity.BORDERLINE:
        raise HTTPException(422, "Probe supports the AI-judged tone and messaging rules: " + ", ".join(sorted(ambiguity.BORDERLINE)))
    if not 2 <= b.runs <= 5:
        raise HTTPException(422, "runs must be between 2 and 5")
    gw = Gateway(db)
    if not gw.enabled:
        raise HTTPException(409, "Needs an LLM key. Without one the rules are checked by fixed code, which always gives the same answer, so there is nothing to compare.")
    res = ambiguity.probe(rule, ambiguity.BORDERLINE[rule.rule_id], gw, runs=b.runs)
    if res is None:
        raise HTTPException(502, "The AI did not return enough valid answers to compare. Try again later.")
    row = RuleProbe(rule_id=rule.rule_id, rule_version=rule.version, created_by=user.email, runs=b.runs,
                    texts=len(res["detail"]), disagreement=res["disagreement"], detail=res["detail"])
    db.add(row)
    audit.log(db, user.email, "rule.ambiguity_probe", "rule", rule.rule_id,
              {"runs": b.runs, "texts": row.texts, "disagreement": row.disagreement})
    db.commit()
    return _ser_probe(row)


@router.get("/rulebook")
def rulebook(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ins = service.insights(db)
    runs_by_rule: dict = {}
    for r in db.execute(select(RedTeamRun).order_by(RedTeamRun.id)).scalars():
        runs_by_rule.setdefault(r.rule_id, []).append(r)
    latest, history = {}, {}
    for rid, rs in runs_by_rule.items():
        r = rs[-1]
        hold = r.summary.get("holdout") or {}
        latest[rid] = {"run_id": r.id, "total": r.summary.get("total"), "missed": r.summary.get("missed"),
                       "caught": r.summary.get("caught"), "rule_version": r.rule_version,
                       "holdout_total": hold.get("total"), "holdout_caught": hold.get("caught"),
                       "holdout_open": hold.get("open", [])}
        history[rid] = [{"run_id": x.id, "rule_version": x.rule_version, "caught": x.summary.get("caught"),
                         "total": x.summary.get("total"), "holdout_caught": (x.summary.get("holdout") or {}).get("caught"),
                         "holdout_total": (x.summary.get("holdout") or {}).get("total")} for x in rs]
    probes: dict = {}
    for p in db.execute(select(RuleProbe).order_by(RuleProbe.id)).scalars():
        probes[p.rule_id] = _ser_probe(p)
    rules = {r.rule_id: r for r in db.execute(select(Rule).where(Rule.is_current.is_(True))).scalars()}
    rows, seen = [], set()
    for x in ins["rules"]:
        seen.add(x["rule_id"])
        rows.append({**x, "redteam": latest.get(x["rule_id"]), "history": history.get(x["rule_id"], []),
                     "eligible": x["rule_id"] in redteam.ELIGIBLE, "probeable": x["rule_id"] in ambiguity.BORDERLINE,
                     "probe": probes.get(x["rule_id"]), "version": rules[x["rule_id"]].version if x["rule_id"] in rules else None})
    for rid in sorted((redteam.ELIGIBLE | set(ambiguity.BORDERLINE)) - seen):
        if rid in rules:
            amb = ambiguity.combine(0, 0, probes[rid]["disagreement"] if rid in probes else None)
            rows.append({"rule_id": rid, "title": rules[rid].title, "hits": 0, "assets": 0, "decided": 0,
                         "override_rate": 0.0, "ambiguous": amb["diagnosis"] in ("unclear", "ignored"), **amb,
                         "accepted": 0, "edited": 0, "rejected": 0, "waived": 0, "open": 0,
                         "redteam": latest.get(rid), "history": history.get(rid, []), "eligible": rid in redteam.ELIGIBLE,
                         "probeable": rid in ambiguity.BORDERLINE, "probe": probes.get(rid), "version": rules[rid].version})
    return {"rules": rows, "repeated_by_team": ins["repeated_by_team"]}
