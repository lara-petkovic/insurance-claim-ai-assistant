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
    api/                 FastAPI app, routes, and API schemas
    core/                Multi-agent business logic and domain schemas
    data/                Document extraction and policy retrieval
    models/              OpenAI model adapter
    utils/               Logging and tiny shared helpers
    config.py            Typed JSON configuration loader
  config.json            Non-secret backend configuration
  tests/
    unit/
    integration/
    e2e/
  requirements/          base.txt, dev.txt, prod.txt
  pyproject.toml         Pytest and Ruff configuration
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

Backend model defaults live in `backend/config.json`. Keep secrets out of that
file and provide the API key through the process environment:

```powershell
$env:OPENAI_API_KEY='your_api_key_here'
```

`MODEL_PROVIDER`, `OPENAI_TEXT_MODEL`, `OPENAI_VISION_MODEL`, and
`OPENAI_REQUIRE_MODELS` can also override their matching JSON values.
Containers receive the API key as a Docker secret rather than embedding it in
the rendered Compose configuration.

## Run The Backend

From the project root:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements\dev.txt
.\backend\.venv\Scripts\python.exe -m pip install -e backend
.\backend\.venv\Scripts\python.exe -m uvicorn api.main:app --app-dir backend\src --host 127.0.0.1 --port 8000 --reload
```

If `python` is not available on Windows but Anaconda is installed, create the virtual environment with:

```powershell
& "$env:USERPROFILE\anaconda3\python.exe" -m venv backend\.venv
```

Open the API docs:

```text
http://127.0.0.1:8000/docs
```

Check model configuration:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/model-status
```

Expected result:

```json
{
  "provider": "openai",
  "client_available": true,
  "require_models": true,
  "openai_configured": true,
  "text_model": "gpt-5.4-mini",
  "vision_model": "gpt-5.4-mini",
  "init_error": null
}
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
- `GET /api/agents`
- `GET /api/model-status`
- `POST /api/model-test`
- `POST /api/documents/extract`
- `POST /api/claims/analyze`
- `POST /api/claims/analyze-stream`

The Angular app uses the streaming endpoint so progress can be shown as each agent completes.

## Terminal Logging

The backend prints agent progress while a claim is analyzed:

```text
[12:57:17] [OrchestratorAgent] Analysis started. | agents=14 ...
[12:57:18] [PolicyConceptExtractionAgent] Started. | step='2/14'
[12:57:19] [ModelClient] Calling OpenAI JSON model. | model='gpt-5.4-mini' ...
[12:57:22] [PolicyConceptExtractionAgent] Completed. | confidence=0.78 warnings=1 human_review=false
```

These logs are intentionally short and do not print the API key.

## Tests

Backend tests:

From the project root:

```powershell
$env:OPENAI_REQUIRE_MODELS='false'
cd backend
.\.venv\Scripts\python.exe -m pytest
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

If `/api/model-status` shows `ollama`, an old backend process is still running. Stop Python/Uvicorn processes on port `8000`, then restart the backend with the command above.

If Python reports missing compiled packages such as `jiter.jiter` or `pydantic_core._pydantic_core`, reinstall dependencies in the backend venv:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install --force-reinstall -r backend\requirements\dev.txt
```

If the model returns a slightly different JSON shape, the backend normalizes common list/dictionary fields before validating the final response.
