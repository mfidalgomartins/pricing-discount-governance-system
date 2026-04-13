from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TableDefinition:
    name: str
    grain: str
    primary_key: list[str]
    foreign_keys: dict[str, str]


TABLE_DEFINITIONS: dict[str, TableDefinition] = {
    "customers": TableDefinition(
        name="customers",
        grain="1 row per customer account",
        primary_key=["customer_id"],
        foreign_keys={},
    ),
    "products": TableDefinition(
        name="products",
        grain="1 row per product",
        primary_key=["product_id"],
        foreign_keys={},
    ),
    "orders": TableDefinition(
        name="orders",
        grain="1 row per order header",
        primary_key=["order_id"],
        foreign_keys={"customer_id": "customers.customer_id", "sales_rep_id": "sales_reps.sales_rep_id"},
    ),
    "order_items": TableDefinition(
        name="order_items",
        grain="1 row per order line item",
        primary_key=["order_item_id"],
        foreign_keys={"order_id": "orders.order_id", "product_id": "products.product_id"},
    ),
    "sales_reps": TableDefinition(
        name="sales_reps",
        grain="1 row per sales rep",
        primary_key=["sales_rep_id"],
        foreign_keys={},
    ),
    "order_item_enriched": TableDefinition(
        name="order_item_enriched",
        grain="1 row per order line item with all dimensions attached",
        primary_key=["order_item_id"],
        foreign_keys={
            "order_id": "orders.order_id",
            "customer_id": "customers.customer_id",
            "product_id": "products.product_id",
            "sales_rep_id": "sales_reps.sales_rep_id",
        },
    ),
    "order_item_pricing_metrics": TableDefinition(
        name="order_item_pricing_metrics",
        grain="1 row per order line item with pricing metrics",
        primary_key=["order_item_id"],
        foreign_keys={
            "order_id": "orders.order_id",
            "customer_id": "customers.customer_id",
            "product_id": "products.product_id",
            "sales_rep_id": "sales_reps.sales_rep_id",
        },
    ),
    "customer_pricing_profile": TableDefinition(
        name="customer_pricing_profile",
        grain="1 row per customer pricing behavior profile",
        primary_key=["customer_id"],
        foreign_keys={"customer_id": "customers.customer_id"},
    ),
    "segment_pricing_summary": TableDefinition(
        name="segment_pricing_summary",
        grain="1 row per customer segment",
        primary_key=["segment"],
        foreign_keys={},
    ),
    "segment_channel_diagnostics": TableDefinition(
        name="segment_channel_diagnostics",
        grain="1 row per segment x sales_channel",
        primary_key=["segment", "sales_channel"],
        foreign_keys={},
    ),
    "customer_risk_scores": TableDefinition(
        name="customer_risk_scores",
        grain="1 row per customer scored for pricing governance risk",
        primary_key=["customer_id"],
        foreign_keys={"customer_id": "customer_pricing_profile.customer_id"},
    ),
    "risk_tier_summary": TableDefinition(
        name="risk_tier_summary",
        grain="1 row per risk_tier x recommended_action",
        primary_key=["risk_tier", "recommended_action"],
        foreign_keys={},
    ),
    "main_driver_summary": TableDefinition(
        name="main_driver_summary",
        grain="1 row per main risk driver",
        primary_key=["main_risk_driver"],
        foreign_keys={},
    ),
}


STRUCTURAL_COLUMNS = {
    "discount_bucket",
    "risk_tier",
    "main_risk_driver",
    "recommended_action",
    "order_month",
    "order_quarter",
}


def _classify_column(series: pd.Series, column_name: str, pk_cols: Iterable[str], fk_cols: Iterable[str]) -> str:
    lower = column_name.lower()
    if column_name in pk_cols or column_name in fk_cols or lower.endswith("_id"):
        return "identifier"
    if lower in STRUCTURAL_COLUMNS or lower.endswith("_bucket"):
        return "structural"
    if "date" in lower or "month" in lower or "quarter" in lower or lower.endswith("_year"):
        return "temporal"
    if series.dtype == bool or lower.startswith("is_") or lower.endswith("_flag"):
        return "boolean"

    if pd.api.types.is_numeric_dtype(series):
        return "metric"

    if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
        non_null = series.dropna().astype(str)
        avg_len = non_null.str.len().mean() if len(non_null) else 0
        distinct_ratio = (non_null.nunique() / len(series)) if len(series) else 0
        if avg_len > 45 and distinct_ratio > 0.4:
            return "text"
        return "dimension"

    return "dimension"


def _parse_temporal(series: pd.Series, column_name: str) -> pd.Series:
    if "quarter" in column_name.lower():
        return pd.PeriodIndex(series.astype(str), freq="Q").to_timestamp(how="end")
    if "month" in column_name.lower():
        return pd.to_datetime(series.astype(str), errors="coerce")
    return pd.to_datetime(series, errors="coerce")


def _expected_non_negative(column_name: str) -> bool:
    keywords = ["price", "discount", "quantity", "revenue", "cost", "orders", "customers", "share", "variance"]
    return any(key in column_name.lower() for key in keywords)


def _profile_single_table(table_name: str, frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    definition = TABLE_DEFINITIONS.get(
        table_name,
        TableDefinition(name=table_name, grain="Unknown grain", primary_key=[], foreign_keys={}),
    )

    row_count = len(frame)
    column_count = frame.shape[1]
    fk_cols = definition.foreign_keys.keys()

    column_records: list[dict] = []
    for column in frame.columns:
        series = frame[column]
        distinct_count = int(series.nunique(dropna=True))
        cardinality_ratio = distinct_count / row_count if row_count else np.nan
        column_type = _classify_column(series, column, definition.primary_key, fk_cols)

        column_records.append(
            {
                "table_name": table_name,
                "column_name": column,
                "column_type": column_type,
                "dtype": str(series.dtype),
                "null_rate": float(series.isna().mean()) if row_count else np.nan,
                "distinct_count": distinct_count,
                "cardinality_ratio": float(cardinality_ratio) if row_count else np.nan,
            }
        )

    column_profile = pd.DataFrame(column_records)

    temporal_columns = column_profile.loc[column_profile["column_type"] == "temporal", "column_name"].tolist()
    date_min: str | None = None
    date_max: str | None = None
    if temporal_columns:
        parsed_all = []
        for col in temporal_columns:
            try:
                parsed = _parse_temporal(frame[col], col)
                parsed = parsed.dropna()
                if not parsed.empty:
                    parsed_all.append(parsed)
            except Exception:
                continue
        if parsed_all:
            combined = pd.concat(parsed_all)
            date_min = combined.min().strftime("%Y-%m-%d")
            date_max = combined.max().strftime("%Y-%m-%d")

    duplicate_on_pk = int(frame.duplicated(subset=definition.primary_key).sum()) if definition.primary_key else 0

    summary = pd.DataFrame(
        [
            {
                "table_name": table_name,
                "grain": definition.grain,
                "primary_key": ", ".join(definition.primary_key),
                "foreign_keys": ", ".join([f"{k}->{v}" for k, v in definition.foreign_keys.items()]),
                "row_count": row_count,
                "column_count": column_count,
                "date_coverage_start": date_min,
                "date_coverage_end": date_max,
                "duplicate_rows_on_primary_key": duplicate_on_pk,
            }
        ]
    )

    dimension_cols = column_profile.loc[column_profile["column_type"].isin(["dimension", "structural"]), "column_name"].tolist()
    top_values_records: list[dict] = []
    for col in dimension_cols:
        vc = frame[col].astype(str).fillna("<NULL>").value_counts(dropna=False).head(5)
        for value, count in vc.items():
            top_values_records.append(
                {
                    "table_name": table_name,
                    "column_name": col,
                    "value": value,
                    "count": int(count),
                    "share": float(count / row_count) if row_count else np.nan,
                }
            )
    top_values = pd.DataFrame(top_values_records)

    metric_cols = column_profile.loc[column_profile["column_type"] == "metric", "column_name"].tolist()
    numeric_records: list[dict] = []
    for col in metric_cols:
        s = pd.to_numeric(frame[col], errors="coerce")
        numeric_records.append(
            {
                "table_name": table_name,
                "column_name": col,
                "count": int(s.notna().sum()),
                "mean": float(s.mean()) if s.notna().any() else np.nan,
                "std": float(s.std(ddof=0)) if s.notna().any() else np.nan,
                "min": float(s.min()) if s.notna().any() else np.nan,
                "p05": float(s.quantile(0.05)) if s.notna().any() else np.nan,
                "median": float(s.median()) if s.notna().any() else np.nan,
                "p95": float(s.quantile(0.95)) if s.notna().any() else np.nan,
                "max": float(s.max()) if s.notna().any() else np.nan,
                "zero_share": float((s == 0).mean()) if len(s) else np.nan,
                "negative_share": float((s < 0).mean()) if len(s) else np.nan,
            }
        )
    numeric_summary = pd.DataFrame(numeric_records)

    issues: list[dict] = []

    for row in column_records:
        col = row["column_name"]
        col_type = row["column_type"]
        null_rate = row["null_rate"]
        distinct_count = row["distinct_count"]
        cardinality_ratio = row["cardinality_ratio"]

        if null_rate >= 0.30:
            issues.append(
                {
                    "table_name": table_name,
                    "column_name": col,
                    "severity": "High",
                    "issue_type": "high_null_rate",
                    "detail": f"Null rate is {null_rate:.2%}",
                }
            )
        elif null_rate >= 0.05:
            issues.append(
                {
                    "table_name": table_name,
                    "column_name": col,
                    "severity": "Medium",
                    "issue_type": "moderate_null_rate",
                    "detail": f"Null rate is {null_rate:.2%}",
                }
            )

        if col_type in {"dimension", "structural"} and distinct_count > 0 and cardinality_ratio > 0.90 and row_count > 100:
            issues.append(
                {
                    "table_name": table_name,
                    "column_name": col,
                    "severity": "Medium",
                    "issue_type": "high_cardinality_surprise",
                    "detail": f"Cardinality ratio is {cardinality_ratio:.2%} for a dimensional field",
                }
            )

        if col_type == "metric" and 0 < distinct_count <= 5 and row_count > 100:
            issues.append(
                {
                    "table_name": table_name,
                    "column_name": col,
                    "severity": "Low",
                    "issue_type": "low_cardinality_surprise",
                    "detail": f"Only {distinct_count} distinct values for metric",
                }
            )

        if (
            col_type == "identifier"
            and len(definition.primary_key) == 1
            and col == definition.primary_key[0]
            and row_count
            and cardinality_ratio < 0.90
        ):
            issues.append(
                {
                    "table_name": table_name,
                    "column_name": col,
                    "severity": "High",
                    "issue_type": "duplicate_risk_identifier",
                    "detail": f"Identifier cardinality ratio {cardinality_ratio:.2%}",
                }
            )

        if frame[col].dtype == object:
            non_null = frame[col].dropna().astype(str)
            if len(non_null) > 0:
                numeric_like = non_null.str.match(r"^-?\d+(\.\d+)?$")
                ratio_numeric_like = numeric_like.mean()
                if 0.20 < ratio_numeric_like < 0.80:
                    issues.append(
                        {
                            "table_name": table_name,
                            "column_name": col,
                            "severity": "Medium",
                            "issue_type": "mixed_format",
                            "detail": "Column mixes numeric-like and non-numeric formats",
                        }
                    )

    for col in metric_cols:
        s = pd.to_numeric(frame[col], errors="coerce")
        if _expected_non_negative(col):
            negatives = int((s < 0).sum())
            if negatives > 0:
                issues.append(
                    {
                        "table_name": table_name,
                        "column_name": col,
                        "severity": "High",
                        "issue_type": "impossible_negative_value",
                        "detail": f"Found {negatives} negative values in non-negative metric",
                    }
                )

    if {"list_price_at_sale", "realized_unit_price"}.issubset(frame.columns):
        impossible_price = int((frame["realized_unit_price"] > frame["list_price_at_sale"]).sum())
        if impossible_price > 0:
            issues.append(
                {
                    "table_name": table_name,
                    "column_name": "realized_unit_price",
                    "severity": "High",
                    "issue_type": "impossible_pricing",
                    "detail": f"{impossible_price} rows where realized price exceeds list price at sale",
                }
            )

    if {"discount_pct", "list_price_at_sale", "realized_unit_price"}.issubset(frame.columns):
        implied_discount = 1 - (frame["realized_unit_price"] / frame["list_price_at_sale"])
        mismatch = int((np.abs(implied_discount - frame["discount_pct"]) > 0.02).sum())
        if mismatch > 0:
            issues.append(
                {
                    "table_name": table_name,
                    "column_name": "discount_pct",
                    "severity": "High",
                    "issue_type": "pricing_inconsistency",
                    "detail": f"{mismatch} rows with discount arithmetic mismatch >2pp",
                }
            )

    if {"list_price", "unit_cost"}.issubset(frame.columns):
        above_list_cost = int((frame["unit_cost"] > frame["list_price"]).sum())
        if above_list_cost > 0:
            issues.append(
                {
                    "table_name": table_name,
                    "column_name": "unit_cost",
                    "severity": "Medium",
                    "issue_type": "cost_above_list_price",
                    "detail": f"{above_list_cost} products have unit cost above list price",
                }
            )

    issue_df = pd.DataFrame(issues)
    return {
        "summary": summary,
        "column_profile": column_profile,
        "top_values": top_values,
        "numeric_summary": numeric_summary,
        "issues": issue_df,
    }


def _cross_table_join_checks(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    issues: list[dict] = []

    def _record_issue(
        table_name: str,
        column_name: str,
        severity: str,
        issue_type: str,
        detail: str,
    ) -> None:
        issues.append(
            {
                "table_name": table_name,
                "column_name": column_name,
                "severity": severity,
                "issue_type": issue_type,
                "detail": detail,
            }
        )

    if {"orders", "customers"}.issubset(tables):
        missing = int((~tables["orders"]["customer_id"].isin(tables["customers"]["customer_id"])).sum())
        if missing > 0:
            _record_issue("orders", "customer_id", "High", "possible_join_issue", f"{missing} order rows do not match customers")

    if {"orders", "sales_reps"}.issubset(tables):
        missing = int((~tables["orders"]["sales_rep_id"].isin(tables["sales_reps"]["sales_rep_id"])).sum())
        if missing > 0:
            _record_issue("orders", "sales_rep_id", "High", "possible_join_issue", f"{missing} order rows do not match sales reps")

    if {"order_items", "orders"}.issubset(tables):
        missing = int((~tables["order_items"]["order_id"].isin(tables["orders"]["order_id"])).sum())
        if missing > 0:
            _record_issue("order_items", "order_id", "High", "possible_join_issue", f"{missing} order item rows do not match orders")

    if {"order_items", "products"}.issubset(tables):
        missing = int((~tables["order_items"]["product_id"].isin(tables["products"]["product_id"])).sum())
        if missing > 0:
            _record_issue("order_items", "product_id", "High", "possible_join_issue", f"{missing} order item rows do not match products")

    if {"customer_risk_scores", "customer_pricing_profile"}.issubset(tables):
        missing = int(
            (~tables["customer_risk_scores"]["customer_id"].isin(tables["customer_pricing_profile"]["customer_id"])).sum()
        )
        if missing > 0:
            _record_issue(
                "customer_risk_scores",
                "customer_id",
                "High",
                "possible_join_issue",
                f"{missing} risk rows do not match customer pricing profile",
            )

    if {"customers", "customer_pricing_profile"}.issubset(tables):
        total_customers = int(tables["customers"]["customer_id"].nunique())
        covered_customers = int(tables["customer_pricing_profile"]["customer_id"].nunique())
        excluded = total_customers - covered_customers
        if excluded > 0:
            exclusion_share = excluded / total_customers if total_customers else np.nan
            _record_issue(
                "customer_pricing_profile",
                "customer_id",
                "Medium",
                "population_exclusion",
                f"{excluded} customers ({exclusion_share:.2%}) have no transactions in period and are excluded",
            )

    return pd.DataFrame(issues)


def _build_analytical_focus(column_profile: pd.DataFrame) -> pd.DataFrame:
    focus_records: list[dict] = []

    for table_name, subset in column_profile.groupby("table_name"):
        best_dimensions = subset[
            (subset["column_type"].isin(["dimension", "structural"]))
            & (subset["cardinality_ratio"] >= 0.001)
            & (subset["cardinality_ratio"] <= 0.65)
        ]["column_name"].tolist()

        best_metrics = subset[subset["column_type"] == "metric"]["column_name"].tolist()
        join_keys = subset[subset["column_type"] == "identifier"]["column_name"].tolist()

        hierarchy_hint = ""
        if {"order_date", "order_month", "order_quarter"}.issubset(set(subset["column_name"])):
            hierarchy_hint = "order_date > order_quarter > order_month"
        elif {"region", "segment"}.issubset(set(subset["column_name"])):
            hierarchy_hint = "region > segment"
        elif {"category", "product_name"}.issubset(set(subset["column_name"])):
            hierarchy_hint = "category > product_name"

        follow_up = ""
        if "discount_pct" in set(subset["column_name"]) or "discount_depth" in set(subset["column_name"]):
            follow_up = "discount distribution stability and policy threshold adherence"
        elif "governance_priority_score" in set(subset["column_name"]):
            follow_up = "risk tier drift and intervention effectiveness"
        elif "margin_proxy_pct" in set(subset["column_name"]):
            follow_up = "margin erosion diagnostics by segment/channel/product"

        focus_records.append(
            {
                "table_name": table_name,
                "best_dimensions": ", ".join(best_dimensions[:8]),
                "best_metrics": ", ".join(best_metrics[:10]),
                "potential_join_keys": ", ".join(join_keys[:8]),
                "likely_hierarchies": hierarchy_hint,
                "useful_follow_up_analysis": follow_up,
            }
        )

    return pd.DataFrame(focus_records).sort_values("table_name")


def _build_population_coverage(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    total_customers = int(tables.get("customers", pd.DataFrame()).get("customer_id", pd.Series(dtype=str)).nunique())
    transacting_customers = int(
        tables.get("orders", pd.DataFrame()).get("customer_id", pd.Series(dtype=str)).nunique()
    )
    profiled_customers = int(
        tables.get("customer_pricing_profile", pd.DataFrame()).get("customer_id", pd.Series(dtype=str)).nunique()
    )
    scored_customers = int(
        tables.get("customer_risk_scores", pd.DataFrame()).get("customer_id", pd.Series(dtype=str)).nunique()
    )

    excluded_non_transacting = max(total_customers - transacting_customers, 0)
    transacting_not_profiled = max(transacting_customers - profiled_customers, 0)
    profiled_not_scored = max(profiled_customers - scored_customers, 0)

    return pd.DataFrame(
        [
            {
                "total_customers_raw": total_customers,
                "transacting_customers": transacting_customers,
                "profiled_customers": profiled_customers,
                "scored_customers": scored_customers,
                "excluded_non_transacting_customers": excluded_non_transacting,
                "excluded_non_transacting_share": (
                    excluded_non_transacting / total_customers if total_customers else np.nan
                ),
                "transacting_not_profiled_customers": transacting_not_profiled,
                "profiled_not_scored_customers": profiled_not_scored,
            }
        ]
    )


def _render_markdown(
    profile_summary: pd.DataFrame,
    issues: pd.DataFrame,
    analytical_focus: pd.DataFrame,
    column_profile: pd.DataFrame,
    population_coverage: pd.DataFrame,
) -> str:
    lines: list[str] = []
    lines.append("# Formal Data Profiling Report")
    lines.append("")
    lines.append("## Profiling Summary")

    for row in profile_summary.sort_values("table_name").itertuples(index=False):
        lines.append(f"### {row.table_name}")
        lines.append(f"- Grain: {row.grain}")
        lines.append(f"- Likely primary key: {row.primary_key if row.primary_key else 'N/A'}")
        lines.append(f"- Likely foreign keys: {row.foreign_keys if row.foreign_keys else 'N/A'}")
        lines.append(f"- Row count: {row.row_count:,}")
        lines.append(f"- Column count: {row.column_count}")
        coverage = (
            f"{row.date_coverage_start} to {row.date_coverage_end}"
            if pd.notna(row.date_coverage_start) and pd.notna(row.date_coverage_end)
            else "N/A"
        )
        lines.append(f"- Date coverage: {coverage}")
        lines.append(f"- Duplicates on primary key: {row.duplicate_rows_on_primary_key}")

        table_cols = column_profile[column_profile["table_name"] == row.table_name]
        lines.append("- Column classes:")
        for class_name, count in table_cols["column_type"].value_counts().items():
            lines.append(f"  - {class_name}: {int(count)}")
        lines.append("")

    lines.append("## Data Quality Issues (Severity Ranked)")
    if issues.empty:
        lines.append("No material issues detected in this run.")
    else:
        severity_order = pd.CategoricalDtype(["High", "Medium", "Low"], ordered=True)
        issues_sorted = issues.copy()
        issues_sorted["severity"] = issues_sorted["severity"].astype(severity_order)
        issues_sorted = issues_sorted.sort_values(["severity", "table_name", "column_name"])
        for issue in issues_sorted.itertuples(index=False):
            lines.append(
                f"- [{issue.severity}] {issue.table_name}.{issue.column_name}: {issue.issue_type} -> {issue.detail}"
            )

    lines.append("")
    lines.append("## Population Coverage")
    if population_coverage.empty:
        lines.append("Population coverage table unavailable.")
    else:
        row = population_coverage.iloc[0]
        lines.append(f"- Raw customers: {int(row['total_customers_raw']):,}")
        lines.append(f"- Transacting customers: {int(row['transacting_customers']):,}")
        lines.append(f"- Profiled customers: {int(row['profiled_customers']):,}")
        lines.append(f"- Scored customers: {int(row['scored_customers']):,}")
        lines.append(
            f"- Excluded non-transacting customers: {int(row['excluded_non_transacting_customers']):,} ({row['excluded_non_transacting_share']:.2%})"
        )
        lines.append(f"- Transacting but not profiled: {int(row['transacting_not_profiled_customers']):,}")
        lines.append(f"- Profiled but not scored: {int(row['profiled_not_scored_customers']):,}")

    lines.append("")
    lines.append("## Recommended Analytical Focus")
    for row in analytical_focus.itertuples(index=False):
        lines.append(f"### {row.table_name}")
        lines.append(f"- Best dimensions for slicing: {row.best_dimensions if row.best_dimensions else 'N/A'}")
        lines.append(f"- Best metrics for analysis: {row.best_metrics if row.best_metrics else 'N/A'}")
        lines.append(f"- Potential join keys: {row.potential_join_keys if row.potential_join_keys else 'N/A'}")
        lines.append(f"- Likely hierarchies: {row.likely_hierarchies if row.likely_hierarchies else 'N/A'}")
        lines.append(
            f"- Useful follow-up analyses: {row.useful_follow_up_analysis if row.useful_follow_up_analysis else 'N/A'}"
        )

    lines.append("")
    lines.append("## Data Model and Documentation Improvements")
    lines.append("- Add a dedicated data dictionary table with business definitions, allowed ranges, and owners for each field.")
    lines.append("- Introduce explicit data types and constraints (date parsing, numeric precision, enum lists) at ingestion boundaries.")
    lines.append("- Version synthetic generation assumptions in docs so analytical changes are traceable over time.")
    lines.append("- Add relationship tests (FK/PK) as automated checks in CI beyond local pytest execution.")

    return "\n".join(lines)


def run_data_profiling(
    raw_tables: Dict[str, pd.DataFrame],
    processed_tables: Dict[str, pd.DataFrame],
    outputs_dir: Path,
    docs_dir: Path,
) -> Dict[str, pd.DataFrame]:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    table_order = [
        "customers",
        "products",
        "sales_reps",
        "orders",
        "order_items",
        "order_item_enriched",
        "order_item_pricing_metrics",
        "customer_pricing_profile",
        "segment_pricing_summary",
        "segment_channel_diagnostics",
        "customer_risk_scores",
        "risk_tier_summary",
        "main_driver_summary",
    ]

    combined_tables = {**raw_tables, **processed_tables}

    profile_summaries: list[pd.DataFrame] = []
    column_profiles: list[pd.DataFrame] = []
    top_values_tables: list[pd.DataFrame] = []
    numeric_summaries: list[pd.DataFrame] = []
    issues_tables: list[pd.DataFrame] = []

    for table_name in table_order:
        if table_name not in combined_tables:
            continue
        results = _profile_single_table(table_name, combined_tables[table_name])
        profile_summaries.append(results["summary"])
        column_profiles.append(results["column_profile"])
        if not results["top_values"].empty:
            top_values_tables.append(results["top_values"])
        if not results["numeric_summary"].empty:
            numeric_summaries.append(results["numeric_summary"])
        if not results["issues"].empty:
            issues_tables.append(results["issues"])

    profile_summary_df = pd.concat(profile_summaries, ignore_index=True) if profile_summaries else pd.DataFrame()
    column_profile_df = pd.concat(column_profiles, ignore_index=True) if column_profiles else pd.DataFrame()
    top_values_df = pd.concat(top_values_tables, ignore_index=True) if top_values_tables else pd.DataFrame()
    numeric_summary_df = pd.concat(numeric_summaries, ignore_index=True) if numeric_summaries else pd.DataFrame()

    local_issues_df = pd.concat(issues_tables, ignore_index=True) if issues_tables else pd.DataFrame()
    join_issues_df = _cross_table_join_checks(combined_tables)
    issues_df = pd.concat([local_issues_df, join_issues_df], ignore_index=True) if not local_issues_df.empty or not join_issues_df.empty else pd.DataFrame(columns=["table_name", "column_name", "severity", "issue_type", "detail"])

    analytical_focus_df = _build_analytical_focus(column_profile_df)
    population_coverage_df = _build_population_coverage(combined_tables)

    profile_summary_df.to_csv(outputs_dir / "table_profile_summary.csv", index=False)
    column_profile_df.to_csv(outputs_dir / "column_profile.csv", index=False)
    top_values_df.to_csv(outputs_dir / "table_top_values.csv", index=False)
    numeric_summary_df.to_csv(outputs_dir / "table_numeric_summary.csv", index=False)
    issues_df.to_csv(outputs_dir / "data_quality_issues.csv", index=False)
    analytical_focus_df.to_csv(outputs_dir / "recommended_analytical_focus.csv", index=False)
    population_coverage_df.to_csv(outputs_dir / "population_coverage.csv", index=False)

    markdown = _render_markdown(
        profile_summary=profile_summary_df,
        issues=issues_df,
        analytical_focus=analytical_focus_df,
        column_profile=column_profile_df,
        population_coverage=population_coverage_df,
    )
    (outputs_dir / "profiling_summary.md").write_text(markdown)

    return {
        "table_profile_summary": profile_summary_df,
        "column_profile": column_profile_df,
        "table_top_values": top_values_df,
        "table_numeric_summary": numeric_summary_df,
        "data_quality_issues": issues_df,
        "recommended_analytical_focus": analytical_focus_df,
        "population_coverage": population_coverage_df,
    }
