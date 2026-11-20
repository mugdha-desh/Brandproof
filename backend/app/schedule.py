"""Scheduled checks: pull the fact feed (if one is configured) and re-judge approved assets against the current facts.

BP_STALE_SCAN_HOURS sets the interval (default 24; 0 turns the scheduler off). The result of every run is written to the
audit log, which is also how the last run is shown in the app, so it survives a restart. If you run several server
instances, run the scheduler on one of them (or set it to 0 and call POST /api/stale/scan from a cron job).
"""
import asyncio
import datetime as dt
import logging
import os

from sqlalchemy import select

from . import audit, db as dbm, facts_import, stale

log = logging.getLogger("brandproof")


def interval_hours() -> float:
    try:
        return max(0.0, float(os.getenv("BP_STALE_SCAN_HOURS", "24")))
    except ValueError:
        return 24.0


def run_once(db, actor: str = "scheduler") -> dict:
    summary: dict = {"feed": "not configured"}
    if facts_import.feed_url():
        try:
            r = facts_import.sync_feed(db, actor)
            summary["feed"] = r.get("skipped") or f"{len(r['created'])} added, {len(r['updated'])} changed, {len(r['errors'])} rows rejected"
        except facts_import.ImportProblem as e:
            summary["feed"] = f"failed: {e}"
    new = stale.scan(db, actor, "scheduled check")
    summary["new_stale_alerts"] = len(new)
    audit.log(db, actor, "schedule.run", "system", "stale-scan", summary)
    db.commit()
    return summary


def status(db) -> dict:
    last = db.execute(select(dbm.Audit).where(dbm.Audit.action == "schedule.run").order_by(dbm.Audit.id.desc()).limit(1)).scalar_one_or_none()
    h = interval_hours()
    nxt = None
    if last and h:
        nxt = (dt.datetime.fromisoformat(last.ts) + dt.timedelta(hours=h)).isoformat(timespec="minutes")
    return {"enabled": h > 0, "every_hours": h, "last_run": last.ts if last else None, "last_result": last.detail if last else None,
            "next_run": nxt, "feed_configured": bool(facts_import.feed_url()), "feed_host": facts_import.feed_host()}


def _tick() -> None:
    s = dbm.session()
    try:
        run_once(s)
    except Exception:
        log.exception("scheduled check failed")
    finally:
        s.close()


async def loop() -> None:
    h = interval_hours()
    if not h:
        return
    while True:
        await asyncio.sleep(h * 3600)
        await asyncio.to_thread(_tick)
