.PHONY: help lint format typecheck test check install clean

help:
	@echo "Available commands:"
	@echo "  make install    - Install all dependencies"
	@echo "  make format     - Format code with ruff"
	@echo "  make lint       - Run all linters (ruff + wemake)"
	@echo "  make typecheck  - Run mypy type checking"
	@echo "  make check      - Run all checks (format + lint + typecheck)"
	@echo "  make test       - Run tests in Docker"
	@echo "  make clean      - Clean cache and temporary files"

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	.venv/bin/pre-commit install

format:
	.venv/bin/ruff format .
	.venv/bin/ruff check --fix --unsafe-fixes .

lint:
	.venv/bin/ruff check .
	.venv/bin/flake8 . --select=WPS

typecheck:
	.venv/bin/mypy src/

check: format lint typecheck
	@echo "All checks passed!"

test:
	docker compose --profile test run --rm test

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
