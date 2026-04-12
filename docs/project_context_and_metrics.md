# Project Context and Metric Governance

## Business Context
The project addresses a practical pricing-governance question: growth can look healthy in topline terms while commercial quality deteriorates because discounting becomes the default closing mechanism.

The analytical objective is to separate tactical discounting from structural discount dependency and quantify where margin exposure is operationally relevant.

## Decision Question
Is the company growing through pricing discipline, or through discounting patterns that reduce margin quality and weaken commercial governance?

## Scope and Population
- Transaction layer: all order items in the modeled period.
- Scoring layer: transacting customers only.
- Non-transacting customers remain in the master table but are excluded from behavioral metrics and risk ranking.

## Decision-Critical Metrics
- `discount_depth`: order-item realized discount (`discount_pct`).
- `price_realization`: `sum(line_revenue) / sum(line_list_revenue)`.
- `weighted_realized_discount`: `1 - sum(line_revenue) / sum(line_list_revenue)`.
- `high_discount_revenue_share`: revenue share from order lines with discount >= 20%.
- `margin_proxy_pct`: `(line_revenue - line_cost) / line_revenue`.
- `repeat_discount_behavior`: share of consecutive customer orders where both were high-discount.

Denominator logic is explicitly enforced in validation to avoid average-of-averages and shifting-population distortions.

## Risk Scoring Design
Scores are governance-oriented and interpretable. They combine:
- Relative positioning (peer percentiles)
- Absolute policy-breach intensity (threshold excess)

Score families:
- `pricing_risk_score`
- `discount_dependency_score`
- `margin_erosion_score`
- `governance_priority_score` (weighted composite for intervention sequencing)

Reliability guardrail:
- Low-volume customers are shrunk toward neutral scores to reduce false escalation.

## Policy Anchors
Default thresholds are explicit policy assumptions, not universal constants:
- Avg discount threshold: 18%
- High-discount order share threshold: 35%
- High-discount revenue share threshold: 40%
- Repeat high-discount threshold: 20%
- Margin proxy floor: 38%
- Realized price CV threshold: 45%

## Interpretation Guardrails
- Scores indicate intervention priority, not causal proof.
- Segment/channel outliers are triage signals; policy action still requires commercial context.
- Synthetic data supports method design and governance logic testing, not claims about a real company.

