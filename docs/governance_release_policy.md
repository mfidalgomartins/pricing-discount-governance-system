# Governance and Release Policy

## Objective
Prevent silent degradation between a technically successful pipeline run and a decision-ready analytical release.

## Policy Inputs
- `config/metric_contracts.json`
- `config/release_policy.json`

## Metric Contract Layer
Metric contracts enforce governed schema and KPI constraints for critical tables:
- `order_item_pricing_metrics`
- `customer_pricing_profile`
- `customer_risk_scores`
- `overall_pricing_health`

Validation output:
- `outputs/metric_contract_validation.csv`

Each run checks:
- required columns
- key null-rate sanity
- numeric bounds for governed KPI fields
- allowed categorical values for governance taxonomy

## Release Gate Layer
Release gate consumes:
- `outputs/final_validation_summary.json`
- `outputs/metric_contract_validation.csv`
- `config/release_policy.json`

Gate output artifacts:
- `outputs/release/release_gate_report.json`
- `outputs/release/release_gate_report.md`
- `outputs/release/release_readiness.json`
- `outputs/release/release_readiness.md`

## Default Publication Criteria
Current default policy requires:
- `technically_valid = true`
- `analytically_acceptable = true`
- `decision_support_only = true`
- `publish_blocked = false`
- zero failed blocker checks
- dashboard payload size within configured limit
- metric-contract failures not exceeding configured maximum

## Interpretation of States
- `decision_support_only = true` with `not_committee_grade = true` is acceptable in portfolio synthetic mode.
- Committee-grade evidence requires replacing synthetic data and proxy margin assumptions with production ledger-aligned evidence.

## Why This Matters
This governance layer stops two common portfolio-quality failures:
1. Presenting polished outputs with weak metric controls.
2. Passing tests while releasing analytically inconsistent KPI artifacts.

The release gate formalizes the difference between a runnable project and a trustworthy decision-support artifact.
