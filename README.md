# Insurance Claim Multi-Agent Assessment

Full-stack prototype for explainable insurance claim analysis. The app lets a user upload a policy document, describe a claim, optionally add damage evidence, and receive a structured preliminary coverage opinion.

This is not a final insurance decision system. It is an explainable assistant workflow for claim triage and human adjuster review.

## What It Does

- Extracts text from uploaded policy files and every supporting document.
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

## Bounded orchestration

The backend uses a small internal execution graph with three reasoning roles.
Typed tasks and an allow-listed service registry keep model and tool execution
bounded and observable.

### Reasoning roles and API facade

- `InvestigationPlannerAgent` creates typed tasks only for unresolved state;
  policy, image, calculation, and retrieval branches run only when applicable.
- `CoverageAnalystAgent` consumes coverage-analysis tasks and resolves typed
  coverage and exclusion propositions.
- `EvidenceCriticAgent` accepts or rejects proposition grounding and can request
  proposition-targeted retrieval, re-analysis, and citation repair.
- `OrchestratorAgent` is the API facade over the bounded graph and preserves the
  existing streaming event contract.

The graph invokes the existing functional and technical agents through an
allow-listed registry. Calculation and date comparison remain focused services.

### Functional agents

Functional agents define the rules,
checklists, and guidance that describe what should be checked for the selected
insurance domain and claim type.

- `GeneralInsuranceFunctionalAgent` provides checks that apply to all claim
  types, such as policy period, insured subject, evidence completeness,
  exclusions, and human-review conditions.
- `HomeInsuranceFunctionalAgent` provides home-insurance checks, such as water
  damage, storm damage, theft, glass breakage, missing reports, and exclusions.
- `AutoInsuranceFunctionalAgent` provides auto-insurance checks, such as
  collision cover, vehicle theft conditions, repair estimates, damage photos,
  and mechanical-breakdown or wear-and-tear exclusions.
- `TravelInsuranceFunctionalAgent` provides travel-insurance checks, such as
  baggage loss, medical claims, trip cancellation, carrier reports, proof of
  ownership, medical receipts, and cancellation evidence.

### Technical agents

Technical agents execute concrete analysis tasks. They use the claim request,
policy text, extracted concepts, retrieval evidence, functional checklists,
model calls, image inputs, and shared memory to perform their part of the
workflow.

- `DocumentIngestionAgent` loads extracted policy text and structured supporting
  documents into shared memory. Supporting documents contain filename, inferred
  type, extracted text, text length, and extraction warnings; raw document bytes
  are not stored in shared agent context.
- `DocumentQualityAgent` checks whether the extracted policy text looks usable.
- `PolicyConceptExtractionAgent` extracts normalized policy concepts, covered
  events, exclusions, conditions, and required documents.
- `ClaimExtractionAgent` extracts structured claim facts and classifies the
  claim type, such as `water_damage`, `vehicle_damage`, `baggage_loss`, or
  `medical`.
- `QueryRewriteAgent` builds a better retrieval query from claim facts and the
  active functional checklist.
- `RetrievalAgent` searches policy wording and supporting documents separately,
  preserves each passage's source, and can retry with the rewritten query.
- `CoverageMatchingAgent` supports the coverage role by comparing policy evidence.
- `VisualEvidenceAgent` classifies visible damage from an uploaded image when
  image evidence is present.
- `ImageAuthenticityAgent` estimates image-authenticity risk signals.

### Validation agents and focused services

- `ExclusionCheckingAgent` supports the coverage role with exclusion checks.
- `MissingDocumentsAgent` checks whether required claim evidence is missing.
- `ConsistencyVerificationAgent` uses `DateComparisonService` to cross-check
  facts, insured subjects, visual findings, and dates.
- `CitationAgent` attaches exact policy and supporting-document citations.
- `OutputValidatorAgent` provides deterministic proposition validation to
  the critic.
- `SettlementCalculationService` performs arithmetic only when explicit claim
  amounts and policy deductibles/excesses are available.
- `FinalDecisionSynthesisAgent` creates the final bounded summary without
  resolving unsupported uncertainty.

### Agent Communication

The planner and critic emit messages containing typed task IDs. The graph admits
only the tasks referenced by those messages, then records each action's selection
reason, executor, outcome, repair iteration, model-call estimate, elapsed time,
and estimated cost. Execution stops with `sufficient_evidence`,
`unavoidable_uncertainty`, `budget_exhausted`, or `failure`.

In short:

```text
Planner creates typed work from unresolved state.
The graph executes allow-listed services and reasoning roles.
The critic either accepts evidence or requests targeted bounded repair.
Explicit limits bound repair iterations, model calls, time, and estimated cost.
Shared state carries findings, tasks, actions, propositions, and messages.
```

## OpenAI Setup

Backend model defaults live in separate non-secret config files:
`backend/config/config.dev.json`, `backend/config/config.env.json`, and
`backend/config/config.prod.json`. Keep secrets out of those files and provide
the API key through the process environment:

```powershell
$env:OPENAI_API_KEY='your_api_key_here'
```

Local development uses `gpt-5.4-mini` for text analysis, planning, vision, and
file-based interpretation. The `env` and `prod` profiles retain their separate
`gpt-5.6` model routing.

`APP_ENV` selects the config file and defaults to `dev`. Docker uses `prod`.
Use `APP_ENV=env` when you want `config/config.env.json`. `APP_CONFIG_FILE` can
point to an exact custom config file. `OPENAI_TEXT_MODEL`,
`OPENAI_PLANNING_MODEL`, and `OPENAI_VISION_MODEL` can also override their
matching JSON values.
Containers receive the API key as a Docker secret rather than embedding it in
the rendered Compose configuration.

All analyses require successful model execution. If a configured model is
unavailable or returns an invalid response, the analysis fails instead of
silently switching to deterministic fallback. Controlled automated tests inject
fake model results when they need to exercise a failure or safety path.

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

## Demo Claim Dataset

Fictional policies, claim descriptions, supporting documents, synthetic damage images, and a model-backed batch runner are available in `backend/demo_cases/`. Run all scenarios from the repository root after configuring `OPENAI_API_KEY`:

```powershell
& '.\backend\.venv\Scripts\python.exe' backend\demo_cases\run_demo_cases.py
```

The generated comparison report is written to `backend/demo_cases/results.md`.

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
- `GET /api/health/ready` — performs a bounded, billable LLM readiness probe
- `POST /api/claims/analyze`
- `POST /api/claims/analyze-stream`

The Angular app uses the streaming endpoint so progress can be shown as each agent completes.

## Supporting Documents

The claim endpoints accept multiple `supporting_documents` uploads. Each upload
is read and extracted independently, so an unreadable file does not prevent the
other documents or the claim from being processed. Extraction problems are
recorded against the affected filename and cause the result to require human
review rather than silently treating unverified facts as confirmed.

Text extraction currently supports UTF-8 `.txt`, `.md`, `.json`, and `.csv`
files. PDFs use embedded-text extraction and, when that text is insufficient,
the configured model-based visual fallback. Unsupported formats produce an
extraction warning and no text. Image uploads remain handled through the
separate damage-image workflow rather than supporting-document text retrieval.

The policy is always mandatory and is the only authoritative source for
coverage, exclusions, limits, and policy conditions. Supporting documents such
as reports, invoices, estimates, receipts, and confirmations provide only
claim-specific facts and corroborating evidence. Lexical retrieval labels policy
passages as `policy` and document passages as `supporting:<filename>`; the result
screen displays those sources separately.

Known limitations: retrieval is deterministic lexical matching rather than
semantic/vector search; document-type and missing-document recognition use
normalized filename/content keywords; scanned-PDF quality depends on the
configured visual extraction model; and password-protected, corrupt, or
unsupported files require manual review.

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
