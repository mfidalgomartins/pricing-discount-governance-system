.DEFAULT_GOAL := help

.PHONY: help install run run-smoke report test lint preflight

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  install    Create .venv and install pinned dependencies"
	@echo "  run        Run the full pipeline (default seed, 1200 customers, 18000 orders)"
	@echo "  run-smoke  Run a fast smoke pipeline (220 customers, 2400 orders)"
	@echo "  report     Rebuild the publication chart pack and PDF report"
	@echo "  test       Run the full test suite with coverage"
	@echo "  lint       Compile-check all Python source files"
	@echo "  preflight  Run the repository preflight check"

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
	.venv/bin/python -m pytest -q --cov=src --cov-fail-under=40

lint:
	.venv/bin/python -m compileall -q src scripts tests

preflight:
	.venv/bin/python scripts/preflight_check.py
