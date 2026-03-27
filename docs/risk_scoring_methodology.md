# Risk Scoring Methodology

## Design Principles
- Interpretable to commercial and finance stakeholders.
- Based on observable pricing behavior, not opaque model artifacts.
- Stable percentile scoring for comparability across cohorts.
- Explicitly designed for prioritization, not causal inference or predictive probability.

## Why Percentile Scoring
- Different components have different scales and distributions (e.g., discount %, variability, margin proxy).
- Percentile normalization keeps components comparable while preserving directional ordering.
- Scores are robust for cross-segment prioritization when absolute scale units differ.

## Component Scores
- **pricing_risk_score**
  - 50% avg discount percentile
  - 30% realized price variation percentile
  - 20% share of high-discount orders percentile

- **discount_dependency_score**
  - 45% high-discount revenue share percentile
  - 35% repeat high-discount behavior percentile
  - 20% share of high-discount orders percentile

- **margin_erosion_score**
  - 55% inverse margin proxy percentile
  - 30% avg discount percentile
  - 15% high-discount revenue share percentile

- **governance_priority_score**
  - 40% pricing risk
  - 35% discount dependency
  - 25% margin erosion

## Tiering
- `Critical`: score >= 80
- `High`: 65 to < 80
- `Medium`: 45 to < 65
- `Low`: < 45

## Action Mapping Rationale
- `Low`: monitor only (no immediate governance intervention).
- `Medium`: review segment pricing (structural review before rep-level intervention).
- `High/Critical`: route action by dominant risk driver to keep interventions specific:
  - pricing risk driver -> investigate rep behavior
  - dependency driver -> redesign discount policy
  - margin erosion driver -> tighten approval thresholds

## Recommended Action Rules
- `Low`: monitor only
- `Medium`: review segment pricing
- `High/Critical` + pricing risk driver: investigate rep behavior
- `High/Critical` + dependency driver: redesign discount policy
- `High/Critical` + margin erosion driver: tighten approval thresholds

## Limitations and Calibration Notes
- Weights are governance-priority assumptions and should be calibrated with policy owners.
- Threshold sensitivity (discount and risk tiers) should be tested before production rollout.
- Scores are only as reliable as the transactional completeness and pricing field quality in source systems.
