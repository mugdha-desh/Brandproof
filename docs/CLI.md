# brandproof CLI: a pre-publish gate

```bash
export BRANDPROOF_URL=https://your-api.example.com      # default http://localhost:8000
export BRANDPROOF_EMAIL=creator@finora.example           # or BRANDPROOF_TOKEN=...
export BRANDPROOF_PASSWORD=...
cd backend
python cli.py check post.pdf --intent "Announce our new savings account"
python cli.py check copy.txt --intent "Launch post" --fail-on medium --out proof.json
```

| Exit code | Meaning |
|---|---|
| 0 | No open finding at or above `--fail-on` (default `high`) and no manipulation flag |
| 1 | Gate failed: open findings, or raw and cleaned file disagreed (hidden text) |
| 2 | Could not run: bad login, unreadable file, server unreachable |

Options: `--title`, `--channel`, `--ai-generated`, `--out FILE` (Proof Pack and gate result as JSON), `--json` (one JSON line).

What it does not do: it never approves an asset. A human approves in the web app. It also cannot stop someone publishing by hand, so treat the exit code as a gate inside a pipeline, not as a lock.

Needs only `httpx` (already in `requirements.txt`). An example GitHub Actions gate is in `.github/workflows/brandproof-gate.example.yml`.
