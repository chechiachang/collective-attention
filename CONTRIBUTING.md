# Contributing to Collective Attention

Thank you for your interest in contributing!

---

## Development Setup

1. **Install [uv](https://docs.astral.sh/uv/)**

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Clone and install**

   ```bash
   git clone https://github.com/chechiachang/collective-attention.git
   cd collective-attention
   uv sync --all-extras
   ```

3. **Verify everything works**

   ```bash
   make check
   ```

---

## Running Checks

| Command | What it does |
|---------|-------------|
| `make fmt` | Auto-format with `black` |
| `make lint` | Lint with `ruff` |
| `make type` | Type-check with `mypy` |
| `make test` | Run the test suite with `pytest` |
| `make check` | All of the above |

---

## Coding Standards

- **Formatter**: `black` (line length 88)
- **Linter**: `ruff` (E/F/W/I rules)
- **Type hints**: required for all public functions; `mypy` must pass
- **Tests**: every new agent or formula change must include a corresponding test in `tests/test_system.py`; all tests must be offline (mock any network calls)

---

## Adding a New Signal Source

1. Create `agents/<source>_signal.py` implementing a `.fetch(event: Event) -> None` method that writes to `event.signals`.
2. Register the new agent in `core/pipeline.py` and `api/main.py`.
3. Add the new signal field to `core/models.py:Signals`.
4. Update `core/models.py:compute_score()` and the scoring formula documentation.
5. Add offline unit tests.

---

## Pull Request Process

1. Fork the repository and create a feature branch (`git checkout -b feat/my-feature`).
2. Make your changes, ensuring all CI checks pass (`make check`).
3. Open a pull request against `main` with a clear description of the change.

---

## Reporting Issues

Please use the GitHub [issue tracker](https://github.com/chechiachang/collective-attention/issues) and include:

- A clear description of the problem
- Steps to reproduce
- Expected vs actual behaviour
- Python version and OS
