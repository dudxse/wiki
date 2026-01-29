.PHONY: install dev-install test lint format typecheck ci up down logs itest

install:
	pip install -r requirements.lock

dev-install:
	pip install -r requirements.lock -r requirements-dev.txt

test:
	pytest

lint:
	ruff check .

format:
	black .

typecheck:
	pyright

ci: lint typecheck test

up:
	docker compose -f infra/docker-compose.yml --env-file .env up --build -d

down:
	docker compose -f infra/docker-compose.yml --env-file .env down -v

logs:
	docker compose -f infra/docker-compose.yml --env-file .env logs -f

itest:
	RUN_INTEGRATION_TESTS=1 pytest -m integration
