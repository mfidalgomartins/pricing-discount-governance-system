# Release and Reproducibility Guide

## Reproducibility Contract
Pipeline execution is deterministic for the same seed and code state.

Core entrypoints:
- `scripts/run_pipeline.py`
- `scripts/preflight_check.py`
- `scripts/cleanup_repository.py` (explicit cleanup only; it is not run implicitly by the main pipeline)

Primary persisted artifacts:
- Executive dashboard in `docs/`
- Runtime analysis, visualization, validation, and SQL warehouse artifacts in `outputs/` when the pipeline runs

## What Is Versioned vs Generated
Versioned:
- Source code (`src/`, `scripts/`)
- Core documentation (`docs/`)
- Final dashboard HTML and its local browser asset

Generated at run time:
- Runtime artifacts in `outputs/`, including analysis, profiling, visualizations, validation reports, and manifests
- SQL warehouse logs in `outputs/warehouse`
- Most `data/processed/*`
- Intermediate run diagnostics and manifests

Repository hygiene is intentionally strict to keep GitHub presentation clean while preserving auditability.
The canonical public artifact is the dashboard in `docs/`; runtime outputs are ignored because they are regenerated from the seed, raw synthetic data, SQL models, and Python pipeline.

## Readiness Semantics
Readiness is explicitly classified by the final validation step as:
- `technically_valid`
- `analytically_acceptable`
- `decision_support_only`
- `screening_grade_only`
- `not_committee_grade`
- `publish_blocked`

This avoids false confidence and clarifies whether outputs are suitable for operations, screening, or committee-level decisions.
