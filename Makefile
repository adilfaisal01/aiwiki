.PHONY: dev dev-down test test-docker shell lint typecheck audit sast chaos chaos-tier1 chaos-tier2 chaos-tier3 ci

dev:
	docker compose up --build

dev-down:
	docker compose down -v

test:
	uv run pytest -q

test-docker:
	docker compose -f docker-compose.test.yml up --build --abort-on-container-exit

lint:
	uv run ruff check . && uv run ruff format --check

typecheck:
	uv run mypy .

audit:
	uv run pip-audit

sast:
	uv run bandit -r . -c pyproject.toml

chaos:
	uv run pytest tests/chaos/ -q

chaos-tier1:
	uv run pytest tests/chaos/ -q -m "tier1"

chaos-tier2:
	uv run pytest tests/chaos/ -q -m "tier2"

chaos-tier3:
	uv run pytest tests/chaos/ -q -m "tier3"

ci:
	act -j lint -j typecheck -j test -j audit -j sast -j chaos-tier1

shell:
	docker compose run --rm aiwiki /bin/bash
