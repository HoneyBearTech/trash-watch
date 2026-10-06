.PHONY: test build run-once suggest

PYTHON ?= python3
VENV := .venv

# Test venv, rebuilt when the requirements change
$(VENV)/.installed: requirements.txt requirements-dev.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q -r requirements-dev.txt
	touch $@

# Unit tests against the fixtures in tests/fixtures: no network, no Docker, no real config
test: $(VENV)/.installed
	$(VENV)/bin/pytest -q

build:
	docker compose build

# One check against the real config from .env, then exit (sends notifications if any are set)
run-once: build
	docker compose run --rm -e RUN_ONCE=1 trash-watch

# Paste-ready Recyclarr YAML for each missing CF, printed to the console only (no notifications, no state)
suggest: build
	docker compose run --rm trash-watch python -u trash_watch.py --suggest
