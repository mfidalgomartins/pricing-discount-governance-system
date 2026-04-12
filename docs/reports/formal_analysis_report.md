# Formal Pricing Discipline Analysis Report

## Executive Summary
Pricing discipline verdict: Discount-reliant growth risk.
Growth is materially supported by high discounting and exposes margin quality.
Revenue growth (2025 vs 2023): 8.54%.
Weighted realized discount: 18.08%; price realization: 81.92%; high-discount revenue share: 32.34%.
Most exposed segment (discount dependency): Enterprise (47.10% high-discount revenue share).
Most exposed segment-category margin erosion pattern: Enterprise / Security (risk score=86.2).
Rep pricing inconsistency: 0 reps flagged as peer outliers (|z|>=2).

## Methodology
- Analysis type: full business diagnostics with validation checks.
- Tables used: order_item_pricing_metrics, customer_pricing_profile, customer_risk_scores, segment_pricing_summary, segment_channel_diagnostics.
- Time period: full available coverage (2023-01-01 to 2025-12-31).
- Metric logic: realized discount, price realization, high-discount revenue share, margin proxy, repeat discount behavior, variance diagnostics.
- Scoring interpretation: customer risk scoring blends peer-relative ranks with absolute policy-threshold breaches.

## Detailed Findings
### A. Overall Pricing Health
- Average realized discount: 16.34%.
- Share of revenue under high discount (>=20%): 32.34%.
- List vs realized performance (price realization): 81.92%.
- Margin proxy: 45.47%.

### B. Discount Dependency
- Segment with highest discount dependency: Enterprise (47.10%).
- Customer top-decile revenue concentration (by dependency): 25.64%.
- Average repeat discount behavior: 11.90%.

### C. Margin Erosion Risk
- Highest risk segment/category: Enterprise / Security.
- Discount leakage value at that intersection: 47681075.32.

### D. Pricing Inconsistency
- No rep-level peer outliers are flagged at |z|>=2; inconsistency signal is concentrated more by channel/region than by individual rep.
- Highest channel-region discount level: Reseller / LATAM (19.43%).

### E. Product-Level Patterns
- Products classified as discount-reliant: 0 of 28.
- Products sold cleanly: 3 of 28.
- Highest governance concern product: Core Product 15 (score=91.4).

### F. Threshold Sensitivity and Decision Impact
How governance exposure changes when the high-discount threshold moves:
- Threshold >= 15%: high-discount revenue share 76.27%, customer exposure >=40% revenue 51.92%, margin-at-risk revenue 138,526,614.92
- Threshold >= 20%: high-discount revenue share 32.34%, customer exposure >=40% revenue 15.17%, margin-at-risk revenue 45,339,566.57
- Threshold >= 25%: high-discount revenue share 3.58%, customer exposure >=40% revenue 0.17%, margin-at-risk revenue 8,001,860.34

Top intervention queue (by priority value proxy):
- C01148 (Enterprise, LATAM) -> redesign discount policy; priority proxy=1,030,872.07, margin-at-risk=1,420,520.97
- C01083 (Enterprise, North America) -> review segment pricing; priority proxy=551,775.25, margin-at-risk=888,240.91
- C01048 (Enterprise, Europe) -> review segment pricing; priority proxy=538,697.49, margin-at-risk=1,113,931.94
- C00642 (Enterprise, Europe) -> redesign discount policy; priority proxy=501,697.06, margin-at-risk=661,433.17
- C00993 (Enterprise, LATAM) -> redesign discount policy; priority proxy=492,255.65, margin-at-risk=693,317.82

## Validation Checks
- row_count_sanity: PASS (pricing rows=38173, enriched rows=38173)
- null_sanity_core_columns: PASS (null count in key columns=0)
- magnitude_checks_positive_revenue: PASS (total_revenue=1842490140.06, total_list_revenue=2249244147.73)
- trend_continuity_monthly: PASS (expected_months=36, observed_months=36)
- time_window_year_coverage: PASS (expected_years=[2023, 2024, 2025], observed_years=[2023, 2024, 2025])
- subtotal_total_consistency: PASS (segment_total=1842490140.06, total=1842490140.06)
- denominator_correctness_shares: PASS (share metrics constrained to [0,1])
- aggregation_logic_weighted_discount: PASS (weighted_direct=0.180840, weighted_ratio=0.180840)
- aggregation_logic_weighted_margin: PASS (weighted_direct=0.454710, weighted_totals=0.454710)
- population_coverage_transacting_customers: PASS (transacting_customers=1173, scored_customers=1173)

## Caveats and Limitations
- Data is synthetic and behaviorally simulated; it supports method validation, not real-world attribution.
- High-discount thresholds are policy assumptions and should be calibrated to commercial context.
- Margin is a proxy using modeled unit cost, not full financial statement gross margin.
- Outlier detection highlights governance signals, not proof of misconduct or causal drivers.

## Recommendations and Next Steps
- tighten approval thresholds for deals above 20% discount in exposed segment/channel combinations
- review segment pricing architecture for Enterprise where high-discount dependency is structurally elevated
- maintain monthly rep-monitoring; no rep outlier currently breaches the z-score threshold
- monitor mixed-pattern products and tighten governance if a discount-reliant cohort emerges
- activate a prioritized intervention queue using margin-at-risk and governance priority score
- track weighted discount, high-discount revenue share, and margin proxy as recurring governance KPIs