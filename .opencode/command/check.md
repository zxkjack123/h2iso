---
description: Run h2iso test suite and lint checks
agent: h2iso-test
---

Run the h2iso project quality checks:

1. Run `ruff check src/ tests/` to lint
2. Run `ruff format --check src/ tests/` to verify formatting
3. Run `pytest tests/ -x --tb=short` to execute unit tests
4. If solver deps are installed, run `pytest tests/ --tb=short` for full suite

Report any failures with file paths and error details.
