"""Fact Vault import: CSV or JSON files, and an optional feed that is pulled on a schedule.

Rules that keep this safe:
- Only the guideline owner can import, and every run is written to the audit log.
- Import MERGES: it adds and updates facts by ID and never deletes one that is missing from the file.
- A dry run shows exactly what would change before anything is written.
- Pattern fields (supports / contradicts) and numeric rules are accepted from an owner's uploaded file only. A feed
  can supply the plain facts (statement, source, owner, dates), never the matching rules, so a changed feed cannot
  quietly change how claims are judged.
- The feed URL comes from server configuration (BP_FACT_FEED_URL), not from a form. It is never called in confidential mode.
- After a real import the stale-approval scan runs, so an approved asset that is now wrong raises an alert.
"""
import csv
import datetime as dt
import hashlib
import io
import ipaddress
import json
import os
import re
import socket
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, stale
from .db import Fact, Setting

MAX_BYTES = 1_000_000
MAX_ROWS = 1000
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,19}$")
LIST_SEP, PATTERN_SEP = ";", ";;"
NESTED_QUANTIFIER = re.compile(r"\([^)]*[+*][^)]*\)\s*[+*{]")

TEMPLATE = (
    "id,statement,kind,keywords,source,owner,valid_from,valid_to,qualifier\n"
    "F-40,Finora Save pays 6.5% a year on balances up to Rs 5 lakh.,rate,interest;rate;savings,Product sheet v12,Treasury,2026-11-01,2027-03-31,\n"
)


class ImportProblem(ValueError):
    """The file or feed cannot be read at all (as opposed to a bad row, which is reported per row)."""


# ------------------------------------------------------------------ reading a file
def parse_file(data: bytes) -> list[dict]:
    if len(data) > MAX_BYTES:
        raise ImportProblem("The file is larger than 1 MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportProblem("The file must be UTF-8 text (CSV or JSON).")
    if not text.strip():
        raise ImportProblem("The file is empty.")
    if text.lstrip()[0] in "[{":
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            raise ImportProblem(f"The JSON is not valid: {e.msg} (line {e.lineno}).")
        rows = obj.get("facts") if isinstance(obj, dict) else obj
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise ImportProblem('JSON must be a list of fact objects, or {"facts": [...]}.')
    else:
        try:
            rows = [dict(r) for r in csv.DictReader(io.StringIO(text))]
        except csv.Error as e:
            raise ImportProblem(f"The CSV could not be read: {e}")
        if rows and "id" not in rows[0]:
            raise ImportProblem("The CSV needs a header row with at least: id, statement, source, owner.")
    if not rows:
        raise ImportProblem("No facts were found in the file.")
    if len(rows) > MAX_ROWS:
        raise ImportProblem(f"More than {MAX_ROWS} facts in one file. Split it.")
    return rows


def _list(v, sep) -> list:
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return v
    return [x.strip() for x in str(v).split(sep) if x.strip()]


def _json(v, want):
    if v is None or v == "":
        return want()
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except json.JSONDecodeError:
            raise ValueError("is not valid JSON")
    if not isinstance(v, want):
        raise ValueError(f"must be a {want.__name__}")
    return v


def _date(v, name):
    if v in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(v).strip())
    except ValueError:
        raise ValueError(f"{name} must look like 2026-12-31")


def clean_row(raw: dict, allow_patterns: bool, defaults: dict | None = None) -> tuple[dict, list[str]]:
    """Return only the fields the row actually supplied, plus a list of problems."""
    defaults = defaults or {}
    raw = {str(k).strip().lower(): v for k, v in raw.items() if k is not None}
    out, bad = {}, []

    def need(key, limit):
        v = str(raw.get(key) if raw.get(key) not in (None, "") else defaults.get(key, "")).strip()
        if not v:
            bad.append(f"{key} is required")
        elif len(v) > limit:
            bad.append(f"{key} is longer than {limit} characters")
        else:
            out[key] = v

    fid = str(raw.get("id", "")).strip()
    if not ID_RE.match(fid):
        bad.append("id must be 1-20 letters, digits, dash, dot or underscore (for example F-40)")
    out["id"] = fid
    need("statement", 1000)
    need("source", 300)
    need("owner", 100)
    if raw.get("kind") not in (None, ""):
        k = str(raw["kind"]).strip().lower()
        out["kind"] = k[:30]
    if raw.get("qualifier") not in (None, ""):
        out["qualifier"] = str(raw["qualifier"]).strip()[:60]
    if "keywords" in raw and raw["keywords"] not in (None, ""):
        kws = [str(x).strip().lower() for x in _list(raw["keywords"], LIST_SEP)]
        if any(len(x) > 40 for x in kws) or len(kws) > 20:
            bad.append("keywords: at most 20, each up to 40 characters")
        out["keywords"] = kws[:20]
    for key in ("valid_from", "valid_to"):
        try:
            if key in raw:
                out[key] = _date(raw[key], key)
        except ValueError as e:
            bad.append(str(e))
    if out.get("valid_from") and out.get("valid_to") and out["valid_to"] < out["valid_from"]:
        bad.append("valid_to is before valid_from")

    pattern_keys = [k for k in ("supports", "contradicts", "numeric", "rewrite") if raw.get(k) not in (None, "", [], {})]
    if pattern_keys and not allow_patterns:
        bad.append("matching rules (" + ", ".join(pattern_keys) + ") are only accepted from an uploaded file, not from a feed")
    elif allow_patterns:
        for key in ("supports", "contradicts"):
            if key in raw and raw[key] not in (None, ""):
                pats = _list(raw[key], PATTERN_SEP)
                for p in pats:
                    try:
                        if len(p) > 200 or NESTED_QUANTIFIER.search(p):
                            raise ValueError("too long or too complex")
                        re.compile(p)
                    except (re.error, ValueError):
                        bad.append(f"{key}: pattern {p[:40]!r} is not allowed")
                out[key] = pats
        for key, want in (("numeric", dict), ("rewrite", list)):
            if key in raw and raw[key] not in (None, ""):
                try:
                    out[key] = _json(raw[key], want)
                except ValueError as e:
                    bad.append(f"{key} {e}")
    return out, bad


# ------------------------------------------------------------------ applying
COLS = ("statement", "kind", "keywords", "supports", "contradicts", "numeric", "qualifier", "rewrite", "source", "owner",
        "valid_from", "valid_to")


def apply(db: Session, rows: list[dict], actor: str, label: str, allow_patterns: bool, dry_run: bool,
          defaults: dict | None = None) -> dict:
    existing = {f.id: f for f in db.execute(select(Fact)).scalars()}
    created, updated, unchanged, errors, seen = [], [], [], [], set()
    for n, raw in enumerate(rows, start=1):
        row, bad = clean_row(raw, allow_patterns, defaults)
        fid = row.get("id", "")
        if fid in seen:
            bad.append("this id appears twice in the file")
        if bad:
            errors.append({"row": n, "id": fid, "problems": bad})
            continue
        seen.add(fid)
        f = existing.get(fid)
        if f is None:
            created.append(fid)
            if not dry_run:
                f = Fact(id=fid, kind="general", keywords=[], supports=[], contradicts=[], numeric={}, qualifier="", rewrite=[],
                         source="", owner="")
                db.add(f)
                for k in COLS:
                    if k in row:
                        setattr(f, k, row[k])
                audit.log(db, actor, "fact.create", "fact", fid, {"via": label})
        else:
            changed = [k for k in COLS if k in row and getattr(f, k) != row[k]]
            if not changed:
                unchanged.append(fid)
                continue
            updated.append({"id": fid, "fields": changed})
            if not dry_run:
                for k in changed:
                    setattr(f, k, row[k])
                audit.log(db, actor, "fact.update", "fact", fid, {"via": label, "fields": changed})
    result = {"dry_run": dry_run, "rows": len(rows), "created": created, "updated": updated, "unchanged": unchanged,
              "errors": errors, "new_stale_alerts": 0}
    if not dry_run and (created or updated):
        audit.log(db, actor, "facts.import", "facts", label, {"created": len(created), "updated": len(updated),
                                                              "errors": len(errors), "rows": len(rows)})
        db.commit()
        new = stale.scan(db, actor, f"fact import ({len(created)} added, {len(updated)} changed)")
        result["new_stale_alerts"] = len(new)
    return result


# ------------------------------------------------------------------ the feed
def feed_url() -> str:
    return os.getenv("BP_FACT_FEED_URL", "").strip()


def feed_host() -> str:
    return urlparse(feed_url()).hostname or ""


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def check_feed_url(url: str) -> None:
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ImportProblem("The feed URL must start with https://")
    if u.scheme == "http" and not _flag("BP_FEED_ALLOW_HTTP"):
        raise ImportProblem("The feed URL must use https:// (set BP_FEED_ALLOW_HTTP=1 only for local testing).")
    if _flag("BP_FEED_ALLOW_PRIVATE"):
        return
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ImportProblem("The feed host could not be found.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ImportProblem("The feed host resolves to a private or internal address, which is not allowed.")


def fetch_feed() -> bytes:
    url = feed_url()
    if not url:
        raise ImportProblem("No feed is configured. Set BP_FACT_FEED_URL on the server.")
    check_feed_url(url)
    headers = {"Accept": "application/json, text/csv"}
    if os.getenv("BP_FACT_FEED_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["BP_FACT_FEED_TOKEN"]
    try:
        with httpx.stream("GET", url, headers=headers, timeout=10.0, follow_redirects=False) as r:
            if r.status_code != 200:
                raise ImportProblem(f"The feed answered with HTTP {r.status_code}.")
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf += chunk
                if len(buf) > MAX_BYTES:
                    raise ImportProblem("The feed is larger than 1 MB.")
            return bytes(buf)
    except httpx.HTTPError as e:
        raise ImportProblem(f"The feed could not be reached ({type(e).__name__}).")


def confidential(db: Session) -> bool:
    row = db.get(Setting, "confidential_mode")
    return bool(row and row.value.get("value"))


def sync_feed(db: Session, actor: str, dry_run: bool = False) -> dict:
    if confidential(db):
        return {"skipped": "Confidential mode is on, so the feed was not called."}
    data = fetch_feed()
    digest = hashlib.sha256(data).hexdigest()[:16]
    res = apply(db, parse_file(data), actor, f"feed {feed_host()} sha256:{digest}", allow_patterns=False, dry_run=dry_run,
                defaults={"source": f"Feed: {feed_host()}", "owner": "Fact feed"})
    res["feed"] = feed_host()
    return res
