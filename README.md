# Insurance Claim Multi-Agent Assessment

Full-stack prototype for explainable insurance claim analysis. The app lets a user upload a policy document, describe a claim, optionally add damage evidence, and receive a structured preliminary coverage opinion.

This is not a final insurance decision system. It is an explainable assistant workflow for claim triage and human adjuster review.

## What It Does

- Extracts text from uploaded policy files.
- Runs a multi-agent backend pipeline for policy concepts, claim facts, retrieval, coverage matching, exclusions, missing documents, citations, and output validation.
- Uses OpenAI models for semantic and vision-backed agents.
- Streams live agent progress to the Angular frontend.
- Prints backend terminal logs for each agent and OpenAI model call.
- Returns a final recommendation with evidence, warnings, confidence values, and human-review flags.

## Current Architecture

```text
backend/
  src/
    main.py              FastAPI app entrypoint
    api/                 API routes
    core/                Multi-agent business logic and domain models
    data/                Document extraction and policy retrieval
    models/              OpenAI model adapter
    utils/               Project logging and tiny shared helpers
    config.py            Typed JSON configuration loader
  config/
    config.dev.json      Local development backend configuration
    config.env.json      Environment-profile backend configuration
    config.prod.json     Production backend configuration
  tests/
    unit/
    integration/
    e2e/
  requirements.txt       Backend dependencies
  Dockerfile

frontend/
  src/app/
    components/          Result and agent trace UI
    models/              TypeScript API types
    pages/               Claim form and results views
    services/            API streaming client
  package.json           Angular scripts and dependencies
```

## Agents

The backend runs these agents in order:

1. `DocumentIngestionAgent`
2. `PolicyConceptExtractionAgent`
3. `ClaimExtractionAgent`
4. `GeneralInsuranceFunctionalAgent`
5. `HomeInsuranceFunctionalAgent`
6. `RetrievalAgent`
7. `VisualEvidenceAgent`
8. `ImageAuthenticityAgent`
9. `CoverageMatchingAgent`
10. `ExclusionCheckingAgent`
11. `MissingDocumentsAgent`
12. `ConsistencyVerificationAgent`
13. `CitationAgent`
14. `OutputValidatorAgent`

The `OrchestratorAgent` combines their outputs into the final `ClaimAnalysisResult`.

## OpenAI Setup

Backend model defaults live in separate non-secret config files:
`backend/config/config.dev.json`, `backend/config/config.env.json`, and
`backend/config/config.prod.json`. Keep secrets out of those files and provide
the API key through the process environment:

```powershell
$env:OPENAI_API_KEY='your_api_key_here'
```

`APP_ENV` selects the config file and defaults to `dev`. Docker uses `prod`.
Use `APP_ENV=env` when you want `config/config.env.json`. `APP_CONFIG_FILE` can
point to an exact custom config file. `OPENAI_TEXT_MODEL`,
`OPENAI_VISION_MODEL`, and `OPENAI_REQUIRE_MODELS` can also override their
matching JSON values.
Containers receive the API key as a Docker secret rather than embedding it in
the rendered Compose configuration.

Logging is configured in the same backend config files under `logging`.
By default, backend application logs are written to
`backend/logs/claim-checker.log`. `PROJECT_LOG_LEVEL`, `PROJECT_LOG_FILE`, and
`PROJECT_LOG_TO_CONSOLE` can override those values.

## Run The Backend

From the project root:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\backend\.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend\src --host 127.0.0.1 --port 8000 --reload
```

If `python` is not available on Windows but Anaconda is installed, create the virtual environment with:

```powershell
& "$env:USERPROFILE\anaconda3\python.exe" -m venv backend\.venv
```

Open the API docs:

```text
http://127.0.0.1:8000/docs
```

## Run The Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm start
```

Open:

```text
http://localhost:4200
```

The frontend calls the backend through the Angular proxy at:

```text
/api
```

## API Endpoints

- `GET /api/health`
- `POST /api/documents/extract`
- `POST /api/claims/analyze`
- `POST /api/claims/analyze-stream`

The Angular app uses the streaming endpoint so progress can be shown as each agent completes.

## Application Logging

The backend writes agent and model progress to the configured log file while a
claim is analyzed:

```text
2026-06-26 12:57:17 INFO [claim_checker.agents.OrchestratorAgent] Analysis started. | agents=14 ...
2026-06-26 12:57:19 INFO [claim_checker.model_client] Calling OpenAI JSON model. | model='gpt-5.4-mini' ...
```

These logs are intentionally short and do not print the API key.

## Tests

Backend tests:

From the project root:

```powershell
$env:OPENAI_REQUIRE_MODELS='false'
$env:PYTHONPATH='src'
cd backend
.\.venv\Scripts\python.exe -m pytest tests -p no:cacheprovider
```

Frontend build:

From the project root:

```powershell
cd frontend
npm run build
```

## Cleanup Notes

The project was cleaned so generated files are not part of the source:

- Removed Python `__pycache__` folders.
- Removed `.pytest_cache`.
- Removed Angular `frontend/dist`.
- Removed the generated PPTX extraction dump under `outputs/pptx_extract_...`.
- Removed unused frontend service methods that were not called by the UI.

`node_modules`, virtual environments, Angular caches, and build output are
ignored by Git and should be recreated locally as needed.

## Troubleshooting

If Python reports missing compiled packages such as `jiter.jiter` or `pydantic_core._pydantic_core`, reinstall dependencies in the backend venv:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install --force-reinstall -r backend\requirements.txt
```

If the model returns a slightly different JSON shape, the backend normalizes common list/dictionary fields before validating the final response.
