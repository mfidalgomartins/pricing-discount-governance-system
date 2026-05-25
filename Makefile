.DEFAULT_GOAL := help

.PHONY: help install run run-smoke test lint clean preflight

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  install    Create .venv and install pinned dependencies"
	@echo "  run        Run the full pipeline (default seed, 1200 customers, 18000 orders)"
	@echo "  run-smoke  Run a fast smoke pipeline (220 customers, 2400 orders)"
	@echo "  test       Run the full test suite with coverage"
	@echo "  lint       Compile-check all Python source files"
	@echo "  preflight  Run the repository preflight check"
	@echo "  clean      Remove runtime caches and reorganise output artifacts"

install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.lock

run:
	.venv/bin/python scripts/run_pipeline.py

run-smoke:
	.venv/bin/python scripts/run_pipeline.py \
		--seed 11 \
		--customers 220 \
		--products 28 \
		--sales-reps 14 \
		--orders 2400 \
		--start-date 2024-01-01 \
		--end-date 2024-12-31

test:
	.venv/bin/python -m pytest -q --cov=src --cov-fail-under=40

lint:
	.venv/bin/python -m compileall -q src scripts tests

preflight:
	.venv/bin/python scripts/preflight_check.py

clean:
	.venv/bin/python scripts/cleanup_repository.py
