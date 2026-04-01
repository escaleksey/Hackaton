.PHONY: help install install-backend install-frontend lint lint-backend lint-frontend test test-backend test-frontend build build-frontend docker-build ci

PYTHON ?= python
PIP ?= pip
NPM ?= npm
DOCKER_COMPOSE ?= docker compose

help:
	@echo "Available targets:"
	@echo "  make install         - install backend and frontend dependencies"
	@echo "  make lint            - run backend and frontend linters"
	@echo "  make test            - run backend and frontend tests"
	@echo "  make build           - build frontend"
	@echo "  make docker-build    - build Docker images"
	@echo "  make ci              - run lint, tests, frontend build and Docker build"

install: install-backend install-frontend

install-backend:
	cd backend && $(PIP) install -r requirements.txt -r requirements-dev.txt

install-frontend:
	cd frontend && $(NPM) install

lint: lint-backend lint-frontend

lint-backend:
	cd backend && $(PYTHON) -m ruff check src tests --config ruff.toml

lint-frontend:
	cd frontend && $(NPM) run lint

test: test-backend test-frontend

test-backend:
	cd backend && $(PYTHON) -m pytest

test-frontend:
	cd frontend && $(NPM) run test -- --run

build: build-frontend

build-frontend:
	cd frontend && $(NPM) run build

docker-build:
	$(DOCKER_COMPOSE) build

ci: lint test build docker-build
