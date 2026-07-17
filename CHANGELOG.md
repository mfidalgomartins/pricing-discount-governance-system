# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Static-analysis tooling: `ruff` (lint + format) and `mypy` in **strict mode**,
  configured in `pyproject.toml` with the formatter owning line length (100).
- `make` targets: `lint`, `format`, `format-check`, `typecheck`, `compile`, and a
  composite `check` that runs the full local quality gate.
- CI stages for lint, format-check, and type-check, mirroring the local gate.
- Dependency vulnerability scanning with `pip-audit`, plus commit-pinned GitHub Actions.
- Developer-experience config: `.editorconfig` and `.pre-commit-config.yaml`.
- Project governance docs: `CONTRIBUTING.md`, `SECURITY.md`, `ARCHITECTURE.md`,
  and `CHANGELOG.md`.
- Tests for `src/utils/paths.py` (path-traversal guard, directory bootstrap) and for the
  type-guard and table-name-injection branches in `src/utils/io.py`.
- Release integrity tests for gate-before-publication ordering and dashboard SHA-256 binding.
- Fail-closed policy-schema, metric-contract, and release-evidence regression tests.
- Versioned run-manifest metadata with runtime versions, publication state, and duration.

### Changed
- Raised the CI/`make test` coverage gate from 40% to 90% to reflect real coverage (~94%).
- Pinned `ruff`, `mypy`, `pre-commit`, and `pip-audit` with their dependencies in
  `requirements.lock`.
- Declared a pinned Setuptools build backend so wheel metadata and package builds do not
  depend on an implicit frontend default.
- Replaced raw customer price CV in governance scoring with a product/channel-normalized
  residual, exposed its policy thresholds and scaling ranges in configuration, and removed
  unsupported attribution of customer risk to sales-representative behavior.
- Changed the pricing-risk discount input from an unweighted line average to the governed
  list-revenue-weighted customer discount.
- Centralized discounted-line and margin-at-risk definitions for Python/SQL parity, and
  made dashboard policy loading fail closed rather than silently substituting defaults.
- Hardened the release gate against malformed readiness counters, unknown contract statuses,
  empty evidence, stale size metadata, and incomplete release policy.
- Dashboard payload selection now retains every Critical/High account before filling its
  140-account review target, preventing scaled books from undercounting high-risk accounts.
- Upgraded Pillow to 12.3.0 to clear the pinned dependency vulnerability audit.
- Corrected GitHub Pages canonical URLs and added a post-pipeline publication parity gate in CI.
- Dashboard publication now occurs only after final validation and a passing release gate;
  the publisher verifies the exact SHA-256 recorded for the validated artifact.
- Release manifests use repository-relative paths for portable audit evidence.
- Escaped HTML-significant characters in embedded dashboard JSON to prevent source data
  from terminating the inline script element.
- Removed dead assignments and an unnecessary dict comprehension flagged by ruff;
  added explicit `strict=True` to `zip()` calls in report builders.
- Parameterized all generic `dict`/`list[dict]` annotations and removed implicit
  `Any` returns so `src` passes `mypy --strict` with zero errors.
- `scripts/build_report_pdf.py`: wrapped each Appendix subsection (heading + table) in
  `KeepTogether` so a table can no longer split across a page boundary and orphan a row
  (previously Appendix D's region table split, leaving the final page ~80% blank).
- Republished the PDF report, chart pack, and dashboard from a full pipeline run. The
  previously committed baseline no longer matched the output of a fresh `make run` +
  `make report` on the current pinned dependencies (page count, order-line count, and
  the high-risk-account count had all drifted). Updated headline figures in `README.md`
  and `outputs/README.md` to match the regenerated, currently-reproducible baseline:
  38,391 order lines (was 38,349), $1.88B revenue (was $1.87B), $419M forgone to discount
  (was $417M), 66 critical/high-risk accounts (was 35), 34-page report (was 33-page).

## [1.0.0] - 2026-06-23

### Added
- Reproducible synthetic commercial dataset with documented grain and lineage.
- Python + DuckDB SQL pipeline from raw data to governed marts.
- Data-quality checks (schema, PK/FK integrity, row-count gates, bounds, reconciliation,
  no-silent-drop joins).
- Operational customer risk score with config-driven thresholds and sensitivity analysis.
- Accessible HTML dashboard, publication chart pack, and 33-page analytical PDF report.
- Release gate, repository preflight, and a 77-test regression suite.
- Documentation set under `docs/` and an operations runbook.

[Unreleased]: https://github.com/mfidalgomartins/pricing-discount-governance-system/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/mfidalgomartins/pricing-discount-governance-system/releases/tag/v1.0.0
