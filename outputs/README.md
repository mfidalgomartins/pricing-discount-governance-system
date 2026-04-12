# Outputs Structure

`outputs/` is organized into two groups:

- Stable deliverables for portfolio and review:
  - `dashboard/` (official executive HTML dashboard)
  - `visualizations/` (curated chart exports)

- Runtime artifacts grouped by purpose (created during pipeline runs and cleaned by `scripts/cleanup_repository.py`):
  - `analysis/`
  - `profiling/`

The canonical narrative is `docs/reports/executive_summary.md` to avoid duplicated report surfaces.

This keeps the repository clean on GitHub while preserving operational reproducibility.
