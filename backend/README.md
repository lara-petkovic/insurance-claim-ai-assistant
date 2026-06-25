# Backend

FastAPI backend for the Claim Checker multi-agent assessment prototype.

## Structure

```text
backend/
  src/
    api/       FastAPI app, routes, and API schemas
    core/      Business logic, agents, orchestration, and domain schemas
    data/      Document extraction and policy retrieval
    models/    OpenAI model adapter
    utils/     Logging helpers
    config/    Environment-backed settings
  tests/
    unit/
    integration/
    e2e/
  requirements/
    base.txt
    dev.txt
    prod.txt
  pyproject.toml
  Dockerfile
```

## Setup

From the repository root:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements\dev.txt
.\backend\.venv\Scripts\python.exe -m pip install -e backend
Copy-Item backend\.env.example backend\.env
```

The editable install makes the packages under `backend\src` importable by
Python and IDEs without manually setting `PYTHONPATH`.

Add your OpenAI key to `backend\.env`. Never commit this file.

## Run

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn api.main:app --app-dir backend\src --host 127.0.0.1 --port 8000 --reload
```

API documentation: `http://127.0.0.1:8000/docs`

## PyCharm

Use a Python run configuration with:

```text
Module: uvicorn
Parameters: api.main:app --app-dir src --host 127.0.0.1 --port 8000 --reload
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
.\.venv\Scripts\python.exe -m pytest
```

## Dependency Sets

- `requirements/base.txt`: application libraries shared by all environments.
- `requirements/dev.txt`: base dependencies plus tests, linting, and local Uvicorn.
- `requirements/prod.txt`: base dependencies plus production Uvicorn.
