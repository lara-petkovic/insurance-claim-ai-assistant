.PHONY: install-dev backend test lint frontend-build

install-dev:
	python -m pip install -r backend/requirements.txt

backend:
	python -m uvicorn main:app --app-dir backend/src --host 127.0.0.1 --port 8000 --reload

test:
	cd backend && set PYTHONPATH=src && python -m pytest tests -p no:cacheprovider

lint:
	cd backend && python -m ruff check src tests --target-version py311 --line-length 120 --select E4,E7,E9,F --ignore F403,F405

frontend-build:
	cd frontend && npm run build
