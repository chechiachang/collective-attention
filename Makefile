.PHONY: install fmt lint type test check dev-server

# Install all dependencies including dev extras
install:
	uv sync --all-extras

# Auto-format with black
fmt:
	uv run black .

# Lint with ruff
lint:
	uv run ruff check .

# Type-check with mypy
type:
	uv run mypy .

# Run test suite
test:
	uv run pytest

# Run all checks (CI-equivalent)
check: fmt lint type test

# Start the API development server
dev-server:
	uv run uvicorn api.main:app --reload

# Run the CLI pipeline (top 10)
run:
	uv run python run_pipeline.py
