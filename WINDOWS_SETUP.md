# Run BrandProof on Windows 11

These commands use PowerShell. Docker is optional for local development.

## 1. Requirements

- Python 3.11 or 3.12
- Node.js 20 or newer
- Git (optional, for pushing the repository)
- Docker Desktop only if you want the one-command Compose setup

## 2. Backend setup

Open PowerShell in the extracted `brandproof` folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
```

If PowerShell blocks activation for this terminal, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Start the API in terminal 1:

```powershell
Set-Location backend
$env:BP_LLM_PROVIDER = "offline"
$env:BP_SECRET = "replace-this-with-a-random-secret-of-at-least-32-characters"
python -m uvicorn app.main:app --reload --port 8000
```

The API is at `http://localhost:8000`; health check: `http://localhost:8000/api/health`.

## 3. Frontend setup

Open a second PowerShell window in the extracted `brandproof` folder:

```powershell
Set-Location frontend
npm ci
$env:BACKEND_URL = "http://localhost:8000"
npm run dev
```

Open `http://localhost:3000`. The seeded demo accounts use password `demo1234` while `BP_SEED=1`.

## 4. Verify the project

With the backend running and demo data seeded, open a third PowerShell window in the project folder:

```powershell
.\.venv\Scripts\Activate.ps1
Set-Location backend
python -m pytest -q
Set-Location ..
python scripts\smoke_test.py
```

Expected: **all backend tests passed** (the exact count is in `docs/TEST_REPORT.md`) and **ALL CHECKS PASSED (42/42)**.

Run the offline evaluation report:

```powershell
Set-Location backend
python -m eval.run_eval
```

## 4b. Check the guided tour and pre-publish CLI

```powershell
python scripts\check_tour.py          # static check of every tour step
Set-Location backend
python cli.py check ..\test_files\Diwali_Flyer_HIDDEN_TEXT.pdf --intent "Diwali launch"   # expect exit code 1
```

## 4c. Optional: local OCR on Windows

Text inside images is read by Tesseract when it is installed and on PATH (the Docker image already includes it). Without it the app still runs, and the Proof Pack lists image text as not read. Install from the UB Mannheim Windows build and add it to PATH, plus the Hindi language data if you want Devanagari.

## 5. Production build check

```powershell
Set-Location frontend
npx tsc --noEmit
npm run build
```

Then test the Docker deployment if Docker Desktop is installed:

```powershell
Set-Location ..
docker compose up --build
```

Open `http://localhost:3000`. Stop Compose with `Ctrl+C`; remove the containers with `docker compose down` when finished.

## 6. Enable hosted AI (optional)

For Gemini, set the API key in the backend environment before starting it:

```powershell
$env:GEMINI_API_KEY = "your-key"
$env:BP_GEMINI_MODEL = "gemini-2.0-flash"      # or any Gemini model your key can use
$env:BP_LLM_PROVIDER = "auto"
```

For Anthropic, set `ANTHROPIC_API_KEY` instead. If both provider keys are configured, check `backend/app/llm/adapter.py` for provider selection order. The AI Disclosure page shows the provider and model actually used.

Never commit `.env`, API keys, database passwords or real customer documents. Keep the demo brand fictional for judging.
