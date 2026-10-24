#!/usr/bin/env bash
# Run the same checks as CI: lint, format check and fast tests.
# Slow tests (crash simulation, about 2 minutes): uv run pytest -m slow
set -euo pipefail
cd "$(dirname "$0")/.."

uv run ruff check .
uv run ruff format --check .
uv run pytest -m "not slow"
