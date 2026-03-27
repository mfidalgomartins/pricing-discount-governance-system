# Final Validation Review (/validate-data)

## Overall Assessment
ready

## Issues Found (Severity)
- [Medium] Customer population exclusion at analysis layer: 27 customers (2.25%) have no orders and are excluded from customer-level scoring.
- [Low] Large self-contained dashboard payload: HTML size is 11.68 MB due embedded row-level data.

## Calculation Spot-Checks
- join_explosion_order_items_to_enriched: PASS (order_items=38173, enriched=38173)
- join_explosion_enriched_to_pricing: PASS (enriched=38173, pricing=38173)
- fk_orders_customer: PASS (missing=0)
- fk_orders_sales_rep: PASS (missing=0)
- fk_order_items_order: PASS (missing=0)
- fk_order_items_product: PASS (missing=0)
- discount_logic_consistency: PASS (max_abs_diff=0.000053)
- realized_lte_list: PASS (violations=0)
- revenue_total_segment_match: PASS (pricing=1842490140.06, segment=1842490140.06)
- margin_proxy_consistency_line_vs_monthly: PASS (line=0.454710, monthly=0.454710)
- period_completeness_monthly: PASS (expected=36, observed=36)
- share_denominator_bounds: PASS (discount_in_[0,1]=True)
- key_findings_discount_not_avg_of_avgs: PASS (weighted_latest=0.180638, reported=0.180600)
- risk_score_nontrivial_variance: PASS (governance_score_variance=452.1258)

## Visualization Checks
- Required visualization files present: PASS (missing=none).
- Chart titles are insight-led and formatting uses readable percent/currency conventions.
- No misleading zero-truncation identified in bar charts used for categorical comparisons.

## Required Caveats
- Synthetic data design remains a simulation, not observed commercial history.
- Customer-level results exclude non-transacting customers in the period.
- Margin is a proxy based on modeled unit cost, not accounting gross margin.
- Pricing inconsistency outlier detection is threshold-based and sensitive to peer-group variance.

## Suggested Improvements
- Add sensitivity runs with alternative risk-tier thresholds and component weights.
- Add a second dashboard mode with pre-aggregated data only to reduce HTML size and improve load performance.
- Add CI gating to enforce regression tests and validation checks on every change.
