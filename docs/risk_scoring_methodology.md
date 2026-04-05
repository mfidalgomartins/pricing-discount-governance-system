# Risk Scoring Methodology

## Design Standard
Scoring is intentionally governance-oriented, interpretable, and auditable.  
The objective is intervention prioritization, not causal attribution or churn/win-rate prediction.

## Why the Model Uses Hybrid Signals
Pure percentile ranking can overstate risk in uniformly healthy cohorts.  
Pure threshold logic can miss meaningful peer outliers.  
The implemented model combines both:
- **relative components** (percentile vs peers)
- **absolute components** (policy threshold breach intensity)

This gives stronger operational credibility for Pricing and Finance review.

## Reliability Guardrail
Customers with very low order counts are noisier.  
The model applies a reliability weight:
- `score_reliability_weight = min(total_orders / 6, 1)`
- low-order customers are shrunk toward neutral score (`50`) rather than over-ranked.

Outputs:
- `score_reliability_weight`
- `low_data_flag`

## Component Structure

### `pricing_risk_score`
- Relative block (60%):
  - 50% avg discount percentile
  - 30% realized price CV percentile
  - 20% high-discount order share percentile
- Absolute block (40%):
  - 45% discount depth excess above policy threshold
  - 30% price variability excess
  - 25% high-discount order share excess

### `discount_dependency_score`
- Relative block (55%):
  - 45% high-discount revenue share percentile
  - 35% repeat high-discount behavior percentile
  - 20% high-discount order share percentile
- Absolute block (45%):
  - 45% high-discount revenue share excess
  - 30% repeat behavior excess
  - 25% high-discount order share excess

### `margin_erosion_score`
- Relative block (50%):
  - 55% inverse margin percentile
  - 30% discount depth percentile
  - 15% high-discount revenue percentile
- Absolute block (50%):
  - 55% margin shortfall vs floor
  - 25% discount depth excess
  - 20% high-discount revenue share excess

### `governance_priority_score`
- 40% pricing risk
- 35% dependency risk
- 25% margin erosion risk

## Policy Threshold Anchors
- Avg discount threshold: `18%`
- High-discount order share threshold: `35%`
- High-discount revenue share threshold: `40%`
- Repeat high-discount behavior threshold: `20%`
- Margin proxy floor: `38%`
- Realized price CV threshold: `45%`

These are governance defaults, not universal truths. They should be calibrated in production with policy owners.

## Tiering and Actions
- `Critical`: `>= 80`
- `High`: `65 to < 80`
- `Medium`: `45 to < 65`
- `Low`: `< 45`

Action mapping:
- `Low` -> monitor only
- `Medium` -> review segment pricing
- `High/Critical` -> route by dominant driver:
  - pricing risk -> investigate rep behavior
  - dependency risk -> redesign discount policy
  - margin erosion risk -> tighten approval thresholds

## Limitations
- Scores remain policy heuristics and require periodic recalibration.
- Reliability shrinkage reduces noise but does not fully remove low-volume uncertainty.
- Synthetic data supports method demonstration, not causal commercial claims.
