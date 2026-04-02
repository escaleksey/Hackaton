.PHONY: install-backend lint-backend test-backend

install-backend:
	pip install -r requirements.txt -r requirements-dev.txt

lint-backend:
	python -m ruff check src tests --config ruff.toml

test-backend:
	python -m pytest
