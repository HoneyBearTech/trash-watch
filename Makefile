.PHONY: test lint build run-once suggest

PYTHON ?= python3
VENV := .venv

# Check and test tools, pinned with hashes; the venv is rebuilt when the requirements change
$(VENV)/.installed: requirements.txt requirements-dev.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --require-hashes --no-deps -r requirements-dev.txt
	touch $@

# Unit tests against the fixtures in tests/fixtures, with the coverage floor from pyproject.toml:
# no network, no Docker, no real config
test: $(VENV)/.installed
	$(VENV)/bin/coverage run -m pytest -q
	$(VENV)/bin/coverage report

# The Python and YAML linters CI runs (the workflow, Dockerfile and secret scanners run in containers; see ci.yml)
lint: $(VENV)/.installed
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .
	$(VENV)/bin/yamllint --strict .

build:
	docker compose build

# One check against the real config from .env, then exit (sends notifications if any are set)
run-once: build
	docker compose run --rm -e RUN_ONCE=1 trash-watch

# Paste-ready Recyclarr YAML for each missing CF, printed to the console only (no notifications, no state)
suggest: build
	docker compose run --rm trash-watch python -u trash_watch.py --suggest
