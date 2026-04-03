# Copilot Instructions – Collective Attention

## Mandatory checks before completing any task

Before marking a task as done, **all** of the following must pass locally:

```bash
uv run black --check .          # formatting
uv run ruff check .             # linting
uv run mypy .                   # type checking
uv run pytest                   # full test suite (includes frontend tests)
```

Run these in the order above.  Fix any failure before proceeding.

## Project overview

This project quantifies **collective attention** of real-world Taiwan events
using multi-source signals (Wikipedia, RSS news, Google Trends).

Key directories:

| Path | Purpose |
|------|---------|
| `agents/` | Signal-fetching & event agents |
| `core/` | Data models, scoring formula, cache |
| `api/` | FastAPI HTTP API |
| `frontend/` | Static single-page HTML frontend |
| `tests/` | pytest test suite (system + frontend) |
| `output/` | Pre-generated demo results (JSON + Markdown) |

## Code style

- Python 3.11+, formatted with **black** (line-length 88)
- Linted with **ruff** (rules E, F, W, I)
- Type-annotated; **mypy** must pass with `strict = false`
- No new third-party libraries without updating `pyproject.toml` first

## Testing

- `tests/test_system.py` – backend unit/integration tests (33 cases)
- `tests/test_frontend.py` – structural tests for `frontend/index.html`
- All tests must remain green after every change
- Use `pytest-mock` and `requests-mock`; no real network calls in tests

## CI requirements

All five CI jobs in `.github/workflows/ci.yml` are required to pass:

1. `fmt` – black format check
2. `lint` – ruff lint
3. `type-check` – mypy
4. `test` – pytest (all tests)
5. `frontend-test` – pytest `tests/test_frontend.py`

## Commit hygiene

- Use conventional-commit style: `feat:`, `fix:`, `chore:`, `docs:`
- Do **not** commit `.cache/`, `__pycache__/`, or `.venv/`

## Mock / offline mode

Use `python run_pipeline.py --mock` when network access is unavailable.
Update `output/results.json` and `output/report.md` after any change to
seed events or scoring logic.
