.PHONY: setup etl dev api test eval build-frontend up down logs

PY := backend/.venv/bin

setup:
	uv venv --python 3.11 backend/.venv
	uv pip install --python backend/.venv/bin/python -r backend/pyproject.toml --extra dev
	cd frontend && (npm ci || npm install)

etl:
	cd backend && .venv/bin/python -m etl.build_index

api:
	cd backend && .venv/bin/uvicorn app.main:app --port 8000

dev:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000 & \
	cd frontend && npm run dev; kill %1 2>/dev/null || true

test:
	cd backend && .venv/bin/python -m pytest tests

eval:
	cd backend && .venv/bin/python ../eval/run_eval.py

build-frontend:
	cd frontend && npm run build

up:
	docker compose -f deploy/docker-compose.yml up --build -d

down:
	docker compose -f deploy/docker-compose.yml down

logs:
	docker compose -f deploy/docker-compose.yml logs -f
