.DEFAULT_GOAL := help
MPLCONFIGDIR ?= /tmp/pricing-governance-matplotlib
export MPLCONFIGDIR

.PHONY: help install run run-smoke report test lint format format-check typecheck compile audit preflight check

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  install      Create .venv and install pinned dependencies"
	@echo "  run          Run the full pipeline (default seed, 1200 customers, 18000 orders)"
	@echo "  run-smoke    Run a fast smoke pipeline (220 customers, 2400 orders)"
	@echo "  report       Rebuild the publication chart pack and PDF report"
	@echo "  test         Run the full test suite with coverage (gate: 90%)"
	@echo "  lint         Lint with ruff (style + correctness rules)"
	@echo "  format       Auto-format the codebase with ruff"
	@echo "  format-check Verify formatting without writing changes"
	@echo "  typecheck    Static type-check src with mypy"
	@echo "  compile      Byte-compile all Python source files"
	@echo "  audit        Scan pinned dependencies for known vulnerabilities"
	@echo "  preflight    Run the repository preflight check"
	@echo "  check        Run the full local quality gate (lint, format, types, compile, tests, preflight)"

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -r requirements.lock

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

report:
	.venv/bin/python scripts/build_report_assets.py
	.venv/bin/python scripts/build_report_pdf.py

test:
	.venv/bin/python -m pytest -q --cov=src --cov-fail-under=90

lint:
	.venv/bin/ruff check src scripts tests

format:
	.venv/bin/ruff format src scripts tests

format-check:
	.venv/bin/ruff format --check src scripts tests

typecheck:
	.venv/bin/mypy

compile:
	.venv/bin/python -m compileall -q src scripts tests

audit:
	.venv/bin/pip-audit -r requirements.lock --progress-spinner off

preflight:
	.venv/bin/python scripts/preflight_check.py

check: lint format-check typecheck compile test preflight
	@echo "All quality gates passed."
