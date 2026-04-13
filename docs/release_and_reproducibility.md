# Release and Reproducibility Guide

## Reproducibility Contract
Pipeline execution is deterministic for the same seed and code state.

Core entrypoints:
- `scripts/run_pipeline.py`
- `scripts/preflight_check.py`

Primary persisted artifacts:
- Executive dashboard in `outputs/dashboard/`
- GitHub Pages publish artifacts in `docs/`
- Visualization pack charts in `outputs/visualizations/` (with an optional `outputs/visualization_pack.md` manifest)
- Validation evidence in `outputs/` (raw, processed, metric-contract, and final review files)
- SQL warehouse evidence in `outputs/warehouse/`

## What Is Versioned vs Generated
Versioned:
- Source code (`src/`, `scripts/`)
- Core documentation (`docs/`)
- Final portfolio deliverables (dashboard HTML, key visuals)

Generated at run time:
- Runtime artifacts in `outputs/analysis` and `outputs/profiling`
- SQL warehouse logs in `outputs/warehouse`
- Most `data/processed/*`
- Intermediate run diagnostics and manifests

Repository hygiene is intentionally strict to keep GitHub presentation clean while preserving auditability.

## Readiness Semantics
Readiness is explicitly classified in `outputs/final_validation_readiness.csv` as:
- `technically_valid`
- `analytically_acceptable`
- `decision_support_only`
- `screening_grade_only`
- `not_committee_grade`
- `publish_blocked`

This avoids false confidence and clarifies whether outputs are suitable for operations, screening, or committee-level decisions.
