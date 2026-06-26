# Backend

FastAPI backend for the Claim Checker multi-agent assessment prototype.

## Structure

```text
backend/
  src/
    main.py    FastAPI app entrypoint
    api/       API routes
    core/      Business logic, agents, orchestration, and domain models
    data/      Document extraction and policy retrieval
    models/    OpenAI model adapter
    utils/     Project logging helpers
    config.py  Typed JSON configuration loader
  config/
    config.dev.json
    config.env.json
    config.prod.json
  tests/
    unit/
    integration/
    e2e/
  requirements.txt
  Dockerfile
```

## Setup

From the repository root:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Edit non-secret defaults in `backend\config\config.dev.json`,
`backend\config\config.env.json`, or `backend\config\config.prod.json`. Set the
OpenAI API key in the environment before starting the backend:

```powershell
$env:OPENAI_API_KEY='your_api_key_here'
```

`APP_ENV` selects the config file and defaults to `dev`. Docker sets
`APP_ENV=prod`; use `APP_ENV=env` for `config\config.env.json`.
`APP_CONFIG_FILE` can point to an exact custom config file.

Application logging is configured in the selected backend config file under
`logging`. Logs are written to `backend\logs\claim-checker.log` by default.
`PROJECT_LOG_LEVEL`, `PROJECT_LOG_FILE`, and `PROJECT_LOG_TO_CONSOLE` can
override the JSON values.

## Run

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend\src --host 127.0.0.1 --port 8000 --reload
```

API documentation: `http://127.0.0.1:8000/docs`

## PyCharm

Use a Python run configuration with:

```text
Module: uvicorn
Parameters: main:app --app-dir src --host 127.0.0.1 --port 8000 --reload
Working directory: C:\Users\Lara\Desktop\insurance-claim-ai-assistant\backend
Interpreter: backend\.venv\Scripts\python.exe
```

When opening `backend` as a standalone PyCharm project, `src` should be marked
as **Sources Root** and `tests` as **Test Sources Root**. The included local
module configuration already applies those markings.

## Tests

```powershell
cd backend
$env:OPENAI_REQUIRE_MODELS='false'
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m pytest tests -p no:cacheprovider
```

## Dependencies

Backend dependencies are kept in `requirements.txt`.
