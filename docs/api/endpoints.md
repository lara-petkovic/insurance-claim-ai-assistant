# API Endpoints

The FastAPI application is defined in `backend/src/main.py`; claim routes live in
`backend/src/api/claim_request_api.py` and health routes in `backend/src/api/health_api.py`.

- `GET /api/health`
- `GET /api/health/ready` — verifies the configured text model with a bounded structured-output call
- `POST /api/claims/analyze`
- `POST /api/claims/analyze-stream`

Interactive documentation is available at `http://127.0.0.1:8000/docs`.
