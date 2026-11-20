"""brandproof: a pre-publish gate for CI, a CMS hook or a terminal.

    python cli.py check post.pdf --intent "Announce our new savings account"
    python cli.py check copy.txt --intent "Launch post" --fail-on medium --out proof.json

Exit codes (so a pipeline can block publishing):
    0  no open finding at or above --fail-on, and no manipulation flag
    1  the gate failed: open findings at or above --fail-on, a manipulation flag, or the asset needs a human
    2  the tool could not run (bad file, bad login, server unreachable)

Settings come from the environment: BRANDPROOF_URL (default http://localhost:8000), and either BRANDPROOF_TOKEN or
BRANDPROOF_EMAIL + BRANDPROOF_PASSWORD. The CLI never approves anything: approval stays with a human in the web app.
"""
import argparse
import json
import mimetypes
import os
import sys

import httpx

SEV = {"low": 1, "medium": 2, "high": 3}


def _login(c: httpx.Client) -> dict:
    tok = os.getenv("BRANDPROOF_TOKEN")
    if not tok:
        email, pw = os.getenv("BRANDPROOF_EMAIL"), os.getenv("BRANDPROOF_PASSWORD")
        if not (email and pw):
            raise SystemExit(_die("Set BRANDPROOF_TOKEN, or BRANDPROOF_EMAIL and BRANDPROOF_PASSWORD."))
        r = c.post("/api/auth/login", json={"email": email, "password": pw})
        if r.status_code != 200:
            raise SystemExit(_die(f"Login failed ({r.status_code})."))
        tok = r.json()["token"]
    return {"Authorization": "Bearer " + tok}


def _die(msg: str) -> int:
    print(f"brandproof: {msg}", file=sys.stderr)
    return 2


def gate(pack: dict, bundle: dict, fail_on: str) -> tuple[int, list[str]]:
    """Pure decision logic, easy to test. Returns (exit_code, reasons)."""
    reasons: list[str] = []
    need = SEV[fail_on]
    for f in bundle.get("findings", []):
        if f["status"] == "open" and SEV.get(f["severity"], 1) >= need:
            reasons.append(f"{f['severity']}: {f['rule_id']} {f['title']}")
    if (pack.get("summary") or {}).get("manipulation_flag"):
        reasons.append("manipulation flag: raw and cleaned file got different verdicts")
    return (1 if reasons else 0), reasons


def check(client: httpx.Client, path: str, intent: str, title: str | None, channel: str, ai_generated: bool,
          fail_on: str, out: str | None, as_json: bool) -> int:
    try:
        headers = _login(client)
        name = os.path.basename(path)
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as e:
        return _die(f"cannot read {path}: {e}")
    except httpx.HTTPError as e:
        return _die(f"server unreachable: {e}")
    data = {"title": title or name, "intent": intent, "channel": channel, "ai_generated": str(ai_generated).lower()}
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    try:
        if name.lower().endswith((".txt", ".md")):
            data["text"] = raw.decode("utf-8", "replace")
            r = client.post("/api/assets", data=data, headers=headers)
        else:
            r = client.post("/api/assets", data=data, files={"file": (name, raw, mime)}, headers=headers)
        if r.status_code != 200:
            return _die(f"upload refused ({r.status_code}): {r.text[:200]}")
        aid = r.json()["id"]
        bundle = client.get(f"/api/assets/{aid}", headers=headers).json()
        pack = client.get(f"/api/assets/{aid}/proofpack", headers=headers).json()
    except httpx.HTTPError as e:
        return _die(f"server unreachable: {e}")
    code, reasons = gate(pack, bundle, fail_on)
    if out:
        with open(out, "w") as fh:
            json.dump({"asset_id": aid, "gate": "fail" if code else "pass", "reasons": reasons, "proof_pack": pack}, fh, indent=1)
    if as_json:
        print(json.dumps({"asset_id": aid, "gate": "fail" if code else "pass", "reasons": reasons}))
    else:
        nf = len(bundle.get("findings", []))
        print(f"BrandProof: {name} -> asset #{aid}, {nf} finding(s). Gate: {'FAIL' if code else 'PASS'} (threshold: {fail_on}).")
        for x in reasons:
            print("  -", x)
        nc = pack.get("not_checked") or []
        if nc:
            print("  Not checked:", "; ".join(str(x) for x in nc[:4]))
        print("  A human still approves in the web app. This command never approves anything.")
    return code


def main(argv=None, client: httpx.Client | None = None) -> int:
    ap = argparse.ArgumentParser(prog="brandproof")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="review a file before publishing")
    c.add_argument("file")
    c.add_argument("--intent", required=True, help="one line: what the creator wants this to say")
    c.add_argument("--title")
    c.add_argument("--channel", default="social")
    c.add_argument("--ai-generated", action="store_true")
    c.add_argument("--fail-on", choices=list(SEV), default="high")
    c.add_argument("--out", help="write the Proof Pack and gate result as JSON")
    c.add_argument("--json", action="store_true", help="print one JSON line instead of text")
    a = ap.parse_args(argv)
    own = client is None
    client = client or httpx.Client(base_url=os.getenv("BRANDPROOF_URL", "http://localhost:8000"), timeout=60)
    try:
        return check(client, a.file, a.intent, a.title, a.channel, a.ai_generated, a.fail_on, a.out, a.json)
    finally:
        if own:
            client.close()


if __name__ == "__main__":
    sys.exit(main())
