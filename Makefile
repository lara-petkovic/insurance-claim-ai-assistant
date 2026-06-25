.PHONY: install-dev backend test lint frontend-build

install-dev:
	python -m pip install -r backend/requirements/dev.txt
	python -m pip install -e backend

backend:
	python -m uvicorn api.main:app --app-dir backend/src --host 127.0.0.1 --port 8000 --reload

test:
	cd backend && python -m pytest

lint:
	cd backend && python -m ruff check src tests

frontend-build:
	cd frontend && npm run build
