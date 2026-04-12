from __future__ import annotations

from pathlib import Path

import nbformat as nbf


def build_project_notebook(project_root: Path) -> Path:
    notebook_path = project_root / "notebooks" / "pricing_discount_governance_system.ipynb"

    nb = nbf.v4.new_notebook()
    cells = []

    cells.append(
        nbf.v4.new_markdown_cell(
            """
# Pricing Discipline & Margin Protection Analytics System

## Main Business Question
Is the company growing with healthy pricing discipline, or relying on discounting patterns that erode margin and weaken commercial behavior?

## Audience and Purpose
- **Audience:** Commercial leadership, Finance, RevOps, and Pricing governance owners
- **Purpose:** support pricing decisions with clear diagnostics and operational recommendations
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
from pathlib import Path
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

sns.set_theme(style="whitegrid")

project_root = Path.cwd().resolve()
if not (project_root / "data").exists():
    project_root = project_root.parent

raw_dir = project_root / "data" / "raw"
processed_dir = project_root / "data" / "processed"
outputs_dir = project_root / "outputs"

customers = pd.read_csv(raw_dir / "customers.csv", parse_dates=["signup_date"])
products = pd.read_csv(raw_dir / "products.csv")
orders = pd.read_csv(raw_dir / "orders.csv", parse_dates=["order_date"])
order_items = pd.read_csv(raw_dir / "order_items.csv")
sales_reps = pd.read_csv(raw_dir / "sales_reps.csv")

pricing = pd.read_csv(processed_dir / "order_item_pricing_metrics.csv", parse_dates=["order_date"])
customer_profile = pd.read_csv(processed_dir / "customer_pricing_profile.csv")
customer_risk = pd.read_csv(processed_dir / "customer_risk_scores.csv")
sql_customer_profile = pd.read_csv(processed_dir / "sql_marts" / "mart_customer_pricing_profile.csv")
sql_segment_summary = pd.read_csv(processed_dir / "sql_marts" / "mart_segment_pricing_summary.csv")
sql_validation = pd.read_csv(outputs_dir / "sql_validation_report.csv")

profile_summary = pd.read_csv(outputs_dir / "table_profile_summary.csv")
quality_issues = pd.read_csv(outputs_dir / "data_quality_issues.csv")
overall_health = pd.read_csv(outputs_dir / "overall_pricing_health.csv")
yearly_health = pd.read_csv(outputs_dir / "yearly_pricing_health.csv")
segment_dependency = pd.read_csv(outputs_dir / "segment_discount_dependency.csv")
margin_risk = pd.read_csv(outputs_dir / "margin_erosion_risk.csv")
rep_inconsistency = pd.read_csv(outputs_dir / "rep_pricing_inconsistency.csv")
product_patterns = pd.read_csv(outputs_dir / "product_governance_patterns.csv")
validation_checks = pd.read_csv(outputs_dir / "formal_analysis_validation_checks.csv")
threshold_sensitivity = pd.read_csv(outputs_dir / "threshold_sensitivity_analysis.csv")
governance_action_queue = pd.read_csv(outputs_dir / "governance_action_queue.csv")

print("Loaded tables successfully")
print("Raw rows:", {"customers": len(customers), "orders": len(orders), "order_items": len(order_items), "products": len(products), "sales_reps": len(sales_reps)})
print("Processed rows:", {"pricing": len(pricing), "customer_profile": len(customer_profile), "customer_risk": len(customer_risk)})
print("SQL mart rows:", {"sql_customer_profile": len(sql_customer_profile), "sql_segment_summary": len(sql_segment_summary)})
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_markdown_cell(
            """
## Data Profiling Summary
This section validates grain, cardinality, coverage, and quality before interpreting pricing conclusions.
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
profile_summary[["table_name", "row_count", "column_count", "date_coverage_start", "date_coverage_end", "duplicate_rows_on_primary_key"]].sort_values("table_name")
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
quality_issues.sort_values(["severity", "table_name"]).head(20)
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_markdown_cell(
            """
## Methodology and Scope
- **Core tables used:** `order_item_pricing_metrics`, `customer_pricing_profile`, `customer_risk_scores`, and SQL marts from `data/processed/sql_marts/`.
- **Key dimensions:** segment, channel, region, rep, category, product.
- **Time window:** full available period.
- **Primary metrics:** realized discount, high-discount revenue share, price realization, margin proxy, repeat discount behavior, inconsistency indicators.
- **Engineering pattern:** Python orchestration + warehouse-style SQL layer (`staging` -> `intermediate` -> `marts`).
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_markdown_cell(
            """
## A. Overall Pricing Health
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
overall_health
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
fig, ax = plt.subplots(1, 2, figsize=(14, 5))

sns.lineplot(data=yearly_health, x="year", y="revenue", marker="o", ax=ax[0], color="#1f77b4")
ax[0].set_title("Revenue Trend")

sns.lineplot(data=yearly_health, x="year", y="weighted_discount", marker="o", ax=ax[1], color="#d62728")
ax[1].set_title("Weighted Discount Trend")
ax[1].set_ylabel("Weighted discount")

plt.tight_layout()
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_markdown_cell(
            """
## B. Discount Dependency
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
segment_dependency[["segment", "revenue", "avg_discount_pct", "high_discount_revenue_share"]].sort_values("high_discount_revenue_share", ascending=False)
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
customer_profile[["customer_id", "segment", "total_revenue", "revenue_high_discount_share", "repeat_discount_behavior"]].sort_values(
    ["revenue_high_discount_share", "total_revenue"], ascending=[False, False]
).head(20)
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_markdown_cell(
            """
## C. Margin Erosion Risk
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
margin_risk[["segment", "category", "revenue", "avg_discount_pct", "margin_proxy_pct", "margin_erosion_risk_score"]].head(20)
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_markdown_cell(
            """
## D. Pricing Inconsistency
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
rep_inconsistency[["sales_rep_id", "team", "rep_region", "avg_discount_pct", "discount_zscore_vs_peers", "discount_outlier_flag"]].sort_values(
    "discount_zscore_vs_peers", ascending=False
).head(20)
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_markdown_cell(
            """
## E. Product-Level Patterns
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
product_patterns[["product_id", "product_name", "category", "revenue", "avg_discount_pct", "high_discount_share", "avg_margin_proxy_pct", "pricing_pattern", "governance_concern_score"]].head(25)
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_markdown_cell(
            """
## Warehouse SQL Layer Checks
This confirms warehouse-model quality controls (grain uniqueness, reconciliation, and bounds) pass in the current run.
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_markdown_cell(
            """
## Decision Engine Views
Threshold sensitivity and action queue outputs support governance planning beyond static diagnosis.
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
threshold_sensitivity
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
governance_action_queue.head(20)
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
sql_validation
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_markdown_cell(
            """
## Publication-Quality Visualization Pack

![Discount Distribution](../outputs/visualizations/discount_distribution.png)

![Realized vs List Price](../outputs/visualizations/realized_price_vs_list_price.png)

![High-Risk Segments Comparison](../outputs/visualizations/high_risk_segments_comparison.png)

![Revenue Under High Discount](../outputs/visualizations/revenue_under_high_discount.png)

![Channel Pricing Comparison](../outputs/visualizations/channel_pricing_comparison.png)

![Product Pricing Dependence Ranking](../outputs/visualizations/product_pricing_dependence_ranking.png)
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_markdown_cell(
            """
## Validation Before Conclusions
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_code_cell(
            """
validation_checks
""".strip()
        )
    )

    cells.append(
        nbf.v4.new_markdown_cell(
            """
## Stakeholder Conclusion
Main finding: growth appears **discount-led rather than pricing-discipline-led**, with meaningful margin erosion and inconsistency risk signals.

## Recommendations
1. Tighten discount approval thresholds for high-risk segment/channel combinations.
2. Review segment pricing architecture where high-discount share is structurally elevated.
3. Continue rep-level monitoring and escalate only if peer outlier signals become persistent.
4. Prioritize intervention on discount-reliant products with weak margin proxy outcomes.

Executive HTML dashboard: `../outputs/dashboard/pricing-discipline-command-center.html`

## Caveats
- Synthetic dataset with realistic behavior design.
- Margin remains a proxy, not full financial gross margin.
""".strip()
        )
    )

    nb["cells"] = cells
    nb["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.14",
        },
    }

    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    with notebook_path.open("w", encoding="utf-8") as f:
        nbf.write(nb, f)

    return notebook_path
