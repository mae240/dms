.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down build logs ps migrate revision seed test lint fmt shell-backend shell-db

help: ## Zeigt diese Hilfe
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

up: ## Startet den gesamten Stack (dev)
	$(COMPOSE) up -d --build

down: ## Stoppt den Stack
	$(COMPOSE) down

build: ## Baut alle Images
	$(COMPOSE) build

logs: ## Folgt den Logs aller Services
	$(COMPOSE) logs -f

ps: ## Status der Services
	$(COMPOSE) ps

migrate: ## Wendet alle Alembic-Migrationen an
	$(COMPOSE) run --rm backend alembic upgrade head

revision: ## Erzeugt eine Autogenerate-Migration: make revision m="nachricht"
	$(COMPOSE) run --rm backend alembic revision --autogenerate -m "$(m)"

check-migrations: ## Prueft, ob Models und Migrationen synchron sind
	$(COMPOSE) run --rm backend alembic check

seed: ## Befuellt die DB mit Demo-Daten
	$(COMPOSE) run --rm backend python -m app.seed

test: ## Fuehrt die Backend-Tests aus
	$(COMPOSE) run --rm -w /app/backend backend pytest

test-worker: ## Fuehrt die Worker-Tests aus
	$(COMPOSE) run --rm --no-deps -w /app/worker worker pytest

lint: ## Ruff Lint
	ruff check .

fmt: ## Ruff Format
	ruff format .

shell-backend: ## Shell im Backend-Container
	$(COMPOSE) run --rm backend bash

shell-db: ## psql in der Datenbank
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-dms} -d $${POSTGRES_DB:-dms}
