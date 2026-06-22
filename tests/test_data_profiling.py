from __future__ import annotations

import pandas as pd

from src.analysis.data_profiling import (
    _build_population_coverage,
    _classify_column,
    _cross_table_join_checks,
    _expected_non_negative,
    _parse_temporal,
    _profile_single_table,
    _render_markdown,
    run_data_profiling,
)


def test_column_classification_and_temporal_parsing() -> None:
    assert _classify_column(pd.Series(["C1", "C2"]), "customer_id", ["customer_id"], []) == "identifier"
    assert _classify_column(pd.Series([1, 0]), "high_discount_flag", [], []) == "boolean"
    assert _classify_column(pd.Series([10.5, 11.2]), "line_revenue", [], []) == "metric"
    assert _classify_column(pd.Series(["2024-01", "2024-02"]), "order_month", [], []) == "structural"
    assert _classify_column(pd.Series(["Enterprise", "SMB"]), "segment", [], []) == "dimension"

    parsed_quarter = _parse_temporal(pd.Series(["2024Q1", "2024Q2"]), "order_quarter")
    parsed_month = _parse_temporal(pd.Series(["2024-01", "bad-value"]), "order_month")

    assert parsed_quarter.notna().all()
    assert parsed_month.notna().sum() == 1
    assert _expected_non_negative("line_revenue")
    assert not _expected_non_negative("realized_price_residual_pct")


def test_profile_single_table_detects_pricing_and_quality_issues() -> None:
    frame = pd.DataFrame(
        {
            "order_item_id": ["OI1", "OI1", "OI3"],
            "order_date": ["2024-01-01", "2024-01-02", "bad-date"],
            "list_price_at_sale": [100.0, 100.0, 120.0],
            "realized_unit_price": [90.0, 110.0, 80.0],
            "line_revenue": [90.0, -5.0, 80.0],
            "mixed_code": ["100", "ABC", None],
            "mostly_null_dimension": [None, None, "A"],
        }
    )

    result = _profile_single_table("order_items", frame)
    issues = result["issues"]

    assert int(result["summary"]["duplicate_rows_on_primary_key"].iloc[0]) == 1
    assert "numeric_summary" in result
    assert {
        "impossible_pricing",
        "impossible_negative_value",
        "mixed_format",
        "high_null_rate",
    }.issubset(set(issues["issue_type"]))


def test_cross_table_join_checks_and_population_coverage() -> None:
    tables = {
        "customers": pd.DataFrame({"customer_id": ["C1", "C2", "C3"]}),
        "sales_reps": pd.DataFrame({"sales_rep_id": ["S1"]}),
        "products": pd.DataFrame({"product_id": ["P1"]}),
        "orders": pd.DataFrame(
            {
                "order_id": ["O1", "O2"],
                "customer_id": ["C1", "missing-customer"],
                "sales_rep_id": ["S1", "missing-rep"],
            }
        ),
        "order_items": pd.DataFrame({"order_id": ["O1", "missing-order"], "product_id": ["P1", "missing-product"]}),
        "customer_pricing_profile": pd.DataFrame({"customer_id": ["C1"]}),
        "customer_risk_scores": pd.DataFrame({"customer_id": ["C1", "missing-profile"]}),
    }

    issues = _cross_table_join_checks(tables)
    coverage = _build_population_coverage(tables)

    assert {
        "possible_join_issue",
        "population_exclusion",
    }.issubset(set(issues["issue_type"]))
    assert int(coverage["total_customers_raw"].iloc[0]) == 3
    assert int(coverage["excluded_non_transacting_customers"].iloc[0]) == 1
    assert int(coverage["profiled_not_scored_customers"].iloc[0]) == 0


def test_run_data_profiling_writes_expected_outputs(tmp_path) -> None:
    raw_tables = {
        "customers": pd.DataFrame({"customer_id": ["C1", "C2"], "signup_date": ["2024-01-01", "2024-01-03"]}),
        "products": pd.DataFrame({"product_id": ["P1"], "list_price": [100.0], "unit_cost": [40.0]}),
        "sales_reps": pd.DataFrame({"sales_rep_id": ["S1"], "region": ["North"]}),
        "orders": pd.DataFrame(
            {
                "order_id": ["O1"],
                "customer_id": ["C1"],
                "order_date": ["2024-02-01"],
                "sales_rep_id": ["S1"],
            }
        ),
        "order_items": pd.DataFrame(
            {
                "order_item_id": ["OI1"],
                "order_id": ["O1"],
                "product_id": ["P1"],
                "quantity": [2],
                "list_price_at_sale": [100.0],
                "realized_unit_price": [90.0],
            }
        ),
    }
    processed_tables = {
        "customer_pricing_profile": pd.DataFrame({"customer_id": ["C1"], "avg_discount_pct": [0.10]}),
        "customer_risk_scores": pd.DataFrame(
            {
                "customer_id": ["C1"],
                "risk_tier": ["Medium"],
                "main_risk_driver": ["pricing_risk_score"],
                "recommended_action": ["review segment pricing"],
            }
        ),
    }

    outputs = run_data_profiling(raw_tables, processed_tables, tmp_path / "outputs", tmp_path / "docs")

    assert set(outputs) == {
        "table_profile_summary",
        "column_profile",
        "table_top_values",
        "table_numeric_summary",
        "data_quality_issues",
        "population_coverage",
    }
    assert (tmp_path / "outputs" / "profiling_summary.md").exists()
    assert (tmp_path / "outputs" / "data_quality_issues.csv").exists()
    assert "population_exclusion" in set(outputs["data_quality_issues"]["issue_type"])


def test_render_markdown_handles_empty_issues() -> None:
    profile_summary = pd.DataFrame(
        [
            {
                "table_name": "customers",
                "grain": "1 row per customer",
                "primary_key": "customer_id",
                "foreign_keys": "",
                "row_count": 2,
                "column_count": 1,
                "date_coverage_start": None,
                "date_coverage_end": None,
                "duplicate_rows_on_primary_key": 0,
            }
        ]
    )
    column_profile = pd.DataFrame(
        [{"table_name": "customers", "column_name": "customer_id", "column_type": "identifier"}]
    )
    population_coverage = pd.DataFrame(
        [
            {
                "total_customers_raw": 2,
                "transacting_customers": 1,
                "profiled_customers": 1,
                "scored_customers": 1,
                "excluded_non_transacting_customers": 1,
                "excluded_non_transacting_share": 0.5,
                "transacting_not_profiled_customers": 0,
                "profiled_not_scored_customers": 0,
            }
        ]
    )

    markdown = _render_markdown(profile_summary, pd.DataFrame(), column_profile, population_coverage)

    assert "# Formal Data Profiling Report" in markdown
    assert "No material issues detected" in markdown
    assert "Excluded non-transacting customers: 1 (50.00%)" in markdown
