PYTHON = .venv/bin/python
RUFF    = .venv/bin/ruff
PYTEST  = .venv/bin/python -m pytest
MKDOGS  = .venv/bin/mkdocs

.PHONY: lint format test test-fast test-all bench docs clean help

lint:
	$(RUFF) check src/ tests/

format:
	$(RUFF) format src/ tests/

test-fast:
	$(PYTEST) tests/ --ignore=tests/benchmark --ignore=tests/e2e \
		--ignore=tests/test_mesh --ignore=tests/test_flowsheet \
		--ignore=tests/property \
		--ignore=tests/test_uq/test_cd2_uq.py \
		--ignore=tests/test_uq/test_isso_uq.py \
		-x --tb=short

test:
	$(PYTEST) tests/ --ignore=tests/benchmark --ignore=tests/e2e -x --tb=short

test-all:
	$(PYTEST) tests/ --tb=short

bench:
	$(PYTEST) tests/benchmark/ --benchmark-enable --override-ini="addopts="

docs:
	$(MKDOGS) serve

clean:
	rm -rf dist/ build/ .pytest_cache/ .mypy_cache/ htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

help:
	@echo "lint      Run ruff check"
	@echo "format    Run ruff format"
	@echo "test-fast Run fast tests only (no solver, <30s)"
	@echo "test      Run all tests except benchmark/e2e"
	@echo "test-all  Run every test including benchmark/e2e"
	@echo "bench     Run performance benchmarks"
	@echo "docs      Serve documentation locally"
	@echo "clean     Remove build artifacts"
