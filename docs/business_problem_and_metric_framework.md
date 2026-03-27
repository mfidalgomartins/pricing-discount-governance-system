# Business Problem and Metric Framework

## Decision Context
Leadership needs to distinguish revenue quality from headline growth. Repeated discounting can increase short-term bookings while weakening long-term margin performance and pricing governance.

## Business Objectives
1. Quantify where discounting is concentrated.
2. Separate acceptable tactical discounting from structural dependency.
3. Prioritize intervention targets (customer, segment, channel, rep).
4. Operationalize action recommendations for Pricing and RevOps.

## Metric Definitions
- **Discount depth** (`order_item_pricing_metrics.discount_depth`): realized unit discount at order-item grain (`discount_pct`).
- **Share orders discounted** (`customer_pricing_profile.share_orders_discounted`): customer-level denominator is total customer orders; numerator is orders with at least one line discounted >= 5%.
- **Share orders high discount** (`customer_pricing_profile.share_orders_high_discount`): customer-level denominator is total customer orders; numerator is orders with at least one line discounted >= 20%.
- **High-discount revenue share** (`customer_pricing_profile.revenue_high_discount_share`): denominator is customer total revenue; numerator is revenue from order lines discounted >= 20%.
- **Weighted realized discount** (`overall_pricing_health.weighted_realized_discount`): `1 - sum(line_revenue) / sum(line_list_revenue)`; avoids average-of-averages distortion.
- **Price realization** (`overall_pricing_health.price_realization`): `sum(line_revenue) / sum(line_list_revenue)`.
- **Margin proxy %** (`order_item_pricing_metrics.margin_proxy_pct`): `(line_revenue - line_cost) / line_revenue`; interpreted as unit-economics proxy, not accounting margin.
- **Margin erosion proxy (segment)** (`segment_pricing_summary.margin_erosion_proxy`): `(1 - avg_margin_proxy_pct) * share_high_discount * 100`.
- **Repeat discount behavior** (`customer_pricing_profile.repeat_discount_behavior`): customer share of consecutive order pairs where both orders are high discount.

## Analytical Population
- Base transaction population: all order items in the modeled period.
- Customer scoring population: transacting customers only.
- Non-transacting customers are retained in `customers` but excluded from behavior/scoring tables and flagged in profiling outputs.

## Thresholds Used
- Discounted order threshold: 5%.
- High-discount threshold: 20%.
- Risk tiers: Low (<45), Medium (45-64.99), High (65-79.99), Critical (>=80).

## Interpretation Guardrails
- High score indicates governance priority, not proof of causal underperformance.
- Segment/channel outliers indicate where policy review is likely highest ROI, not automatic policy breach.
- Findings should be combined with commercial context (deal type, competition, strategic accounts) before enforcement.

## Governance Interpretation
- Rising revenue with rising discount depth and lower margin proxy indicates growth quality deterioration.
- High discount dependency score implies behavior risk and policy non-compliance pressure.
- Margin erosion score indicates likely commercial value leakage.
