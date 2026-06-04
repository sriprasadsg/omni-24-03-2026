.PHONY: help dev prod test lint type-check security clean setup

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install all dev dependencies and pre-commit hooks
	pip install pre-commit
	pre-commit install
	cd backend && pip install -r requirements.txt
	npm install

dev: ## Start development stack (Vite + FastAPI + Mongo + Redis)
	docker compose up

prod: ## Start production stack (nginx + FastAPI + Mongo + Redis)
	docker compose --profile production up -d

seed: ## Seed demo data into running stack
	docker compose --profile seed up seeder

test: ## Run all tests (backend + frontend)
	cd backend && pytest tests/ --tb=short -q --cov=. --cov-report=term-missing
	npm test

test-backend: ## Run backend tests only
	cd backend && pytest tests/ --tb=short -q --cov=. --cov-report=term-missing

test-frontend: ## Run frontend tests only
	npm test

lint: ## Run all linters
	cd backend && pip install ruff --quiet && ruff check .
	npx eslint . --max-warnings 0

type-check: ## Run type checkers
	cd backend && pip install pyright --quiet && pyright --pythonversion 3.13
	npx tsc --noEmit

security: ## Run security scans (bandit + safety + gitleaks)
	cd backend && pip install bandit safety --quiet
	cd backend && bandit -r . -ll -x ./tests,./scripts
	cd backend && safety check -r requirements.txt
	gitleaks detect --source . --redact

pin-images: ## Print Docker image digests for pinning (requires docker pull)
	bash scripts/pin-docker-images.sh

clean: ## Stop and remove all containers and volumes
	docker compose down -v --remove-orphans
