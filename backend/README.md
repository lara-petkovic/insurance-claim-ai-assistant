# Backend

FastAPI backend for the insurance claim multi-agent assessment prototype.

## Setup

From the project root:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

If `python` is not available on Windows but Anaconda is installed, create the virtual environment with:

```powershell
& "$env:USERPROFILE\anaconda3\python.exe" -m venv backend\.venv
```

Edit `backend\.env` and add your OpenAI API key:

```env
MODEL_PROVIDER=openai
OPENAI_API_KEY=your_api_key_here
OPENAI_TEXT_MODEL=gpt-5.4-mini
OPENAI_VISION_MODEL=gpt-5.4-mini
OPENAI_REQUIRE_MODELS=true
```

Never commit `backend\.env`.

## Run

From the project root:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Docs:

```text
http://127.0.0.1:8000/docs
```

## Useful Checks

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/model-status
```

## Main Endpoints

- `GET /api/health`
- `GET /api/agents`
- `GET /api/model-status`
- `POST /api/model-test`
- `POST /api/documents/extract`
- `POST /api/claims/analyze`
- `POST /api/claims/analyze-stream`

The frontend uses `/api/claims/analyze-stream` for live agent progress.
