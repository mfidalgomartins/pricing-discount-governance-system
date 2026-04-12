# Final Validation Review (/validate-data)

## Overall Assessment
- Legacy assessment: ready
- Release readiness state: not committee-grade

## Readiness Classification
- technically_valid: True
- analytically_acceptable: True
- decision_support_only: True
- screening_grade_only: False
- not_committee_grade: True
- publish_blocked: False

## Issues Found (Severity)
- [Low] Customer population exclusion at analysis layer: 27 customers (2.25%) have no orders and are excluded from customer-level scoring.

## Calculation Spot-Checks
- formal_analysis_validation_passthrough: PASS (gate=analytical, severity=High, blocker=False) passed=10 of 10
- period_completeness_monthly: PASS (gate=analytical, severity=Medium, blocker=False) expected=36, observed=36
- share_denominator_bounds: PASS (gate=analytical, severity=High, blocker=False) all_share_columns_in_[0,1]=True
- weighted_discount_consistency: PASS (gate=analytical, severity=High, blocker=False) weighted_direct=0.180840, weighted_total=0.180840
- cross_output_overall_health_consistency: PASS (gate=consistency, severity=High, blocker=False) max_diff=0.000000
- dashboard_data_as_of_consistency: PASS (gate=consistency, severity=Medium, blocker=False) coverage_end=2025-12-31 present_in_dashboard=True
- dashboard_kpi_all_scope_consistency: PASS (gate=consistency, severity=High, blocker=False) revenue_diff=0.000000, discount_diff=0.000040
- dashboard_payload_data_as_of_consistency: PASS (gate=consistency, severity=Medium, blocker=False) payload_coverage_end=2025-12-31, payload_data_as_of=, coverage_end=2025-12-31
- discount_logic_consistency: PASS (gate=consistency, severity=High, blocker=True) max_abs_diff=0.000053
- margin_proxy_consistency_line_vs_monthly: PASS (gate=consistency, severity=High, blocker=True) line=0.454710, monthly=0.454710
- realized_lte_list: PASS (gate=consistency, severity=High, blocker=True) violations=0
- revenue_total_segment_match: PASS (gate=consistency, severity=High, blocker=True) pricing=1842490140.06, segment=1842490140.06
- run_manifest_rowcount_consistency: PASS (gate=consistency, severity=Medium, blocker=False) manifest_orders=18000, actual_orders=18000, manifest_pricing=38173, actual_pricing=38173
- main_risk_driver_alignment: PASS (gate=governance, severity=High, blocker=False) mismatches=0
- metric_contract_validation_passthrough: PASS (gate=governance, severity=High, blocker=False) passed=33 of 33
- recommended_action_policy_alignment: PASS (gate=governance, severity=Medium, blocker=False) invalid_rows=0
- risk_score_nontrivial_variance: PASS (gate=governance, severity=Medium, blocker=False) governance_score_variance=200.897554
- risk_tier_monotonicity_by_median_score: PASS (gate=governance, severity=High, blocker=False) median_scores=Low:27.77, Medium:51.75, High:68.78
- score_stability_low_data_shrinkage: PASS (gate=governance, severity=Medium, blocker=False) low_data_mean_distance=14.783, high_data_mean_distance=20.126
- fk_order_items_order: PASS (gate=technical, severity=High, blocker=True) missing=0
- fk_order_items_product: PASS (gate=technical, severity=High, blocker=True) missing=0
- fk_orders_customer: PASS (gate=technical, severity=High, blocker=True) missing=0
- fk_orders_sales_rep: PASS (gate=technical, severity=High, blocker=True) missing=0
- join_explosion_enriched_to_pricing: PASS (gate=technical, severity=High, blocker=True) enriched=38173, pricing=38173
- join_explosion_order_items_to_enriched: PASS (gate=technical, severity=High, blocker=True) order_items=38173, enriched=38173

## Required Caveats
- Synthetic data design remains a simulation, not observed commercial history.
- Customer-level results exclude non-transacting customers in the period.
- Margin is a proxy based on modeled unit cost, not accounting gross margin.
- Pricing inconsistency outlier detection is threshold-based and sensitive to peer-group variance.

## Suggested Improvements
- Add sensitivity runs with alternative risk-tier thresholds and component weights.
- Add API-backed dashboard mode for larger datasets and lighter payloads.
- Add committee-grade gates only after replacing synthetic data and margin proxy with ledger-aligned metrics.