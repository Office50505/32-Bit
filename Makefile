.PHONY: frontend-install frontend-dev frontend-build backend-install backend-dev backend-test

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

backend-install:
	python3.11 -m venv .venv
	.venv/bin/pip install -e './backend[dev]'

backend-dev:
	.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000

backend-test:
	.venv/bin/pytest backend/tests
