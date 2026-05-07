SHELL := /bin/zsh

BACKEND_DIR := backend
FRONTEND_DIR := frontend
PYTHON := python3
VENV := $(BACKEND_DIR)/.venv
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn

.PHONY: help setup setup-backend setup-frontend app backend backend-reload frontend batch batch-list batch-file process-excel health clean db-up db-down

help:
	@echo "TalentMetrics commands"
	@echo ""
	@echo "  make setup          Install backend and frontend dependencies"
	@echo "  make app            Run backend and frontend together"
	@echo "  make backend        Run FastAPI backend on http://localhost:8000"
	@echo "  make frontend       Run React frontend on http://localhost:5173"
	@echo "  make batch          Import sample_engineers.csv"
	@echo "  make batch-list     Import /Users/manmohankumar/Downloads/List.csv"
	@echo "  make batch-file FILE=/path/file.csv  Import any CSV/XLSX file"
	@echo "  make process-excel FILE=/path/file.xlsx  Process multi-sheet Excel analytics JSON"
	@echo "  make health         Check backend health"
	@echo "  make db-up          Start PostgreSQL with Docker, optional"
	@echo "  make db-down        Stop PostgreSQL with Docker"
	@echo "  make clean          Remove local cache files"

setup: setup-backend setup-frontend

app:
	@./scripts/run_app.sh

setup-backend:
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@$(PIP) install -r $(BACKEND_DIR)/requirements.txt
	@test -f $(BACKEND_DIR)/.env || cp $(BACKEND_DIR)/.env.example $(BACKEND_DIR)/.env
	@echo "Backend setup complete."

setup-frontend:
	@cd $(FRONTEND_DIR) && npm install
	@echo "Frontend setup complete."

backend:
	@test -d $(VENV) || $(MAKE) setup-backend
	@cd $(BACKEND_DIR) && .venv/bin/uvicorn app.main:app --port 8000

backend-reload:
	@test -d $(VENV) || $(MAKE) setup-backend
	@cd $(BACKEND_DIR) && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	@test -d $(FRONTEND_DIR)/node_modules/@tanstack/react-query || $(MAKE) setup-frontend
	@cd $(FRONTEND_DIR) && npm run dev

batch:
	@test -d $(VENV) || $(MAKE) setup-backend
	@cd $(BACKEND_DIR) && .venv/bin/python -m app.batch.daily_sync --file ../sample_engineers.csv

batch-list:
	@test -d $(VENV) || $(MAKE) setup-backend
	@cd $(BACKEND_DIR) && .venv/bin/python -m app.batch.daily_sync --file /Users/manmohankumar/Downloads/List.csv

batch-file:
	@test -n "$(FILE)" || (echo "Usage: make batch-file FILE=/path/to/file.csv" && exit 1)
	@test -d $(VENV) || $(MAKE) setup-backend
	@cd $(BACKEND_DIR) && .venv/bin/python -m app.batch.daily_sync --file "$(FILE)"

process-excel:
	@test -n "$(FILE)" || (echo "Usage: make process-excel FILE=/path/to/file.xlsx" && exit 1)
	@test -d $(VENV) || $(MAKE) setup-backend
	@cd $(BACKEND_DIR) && .venv/bin/python -m app.batch.process_engineer_excel --file "$(FILE)"

health:
	@curl http://localhost:8000/health

db-up:
	@docker compose up -d

db-down:
	@docker compose down

clean:
	@find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	@find . -name ".pytest_cache" -type d -prune -exec rm -rf {} +
	@rm -rf backend/.pycache
	@echo "Cleaned local cache files."

