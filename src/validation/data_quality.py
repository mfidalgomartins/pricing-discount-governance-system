from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from src.utils.policy import get_high_discount_threshold


DISCOUNT_FORMULA_TOLERANCE = 1e-4

RAW_REQUIRED_COLUMNS = {
    "customers": ["customer_id", "signup_date", "segment", "region", "company_size"],
    "products": ["product_id", "product_name", "category", "list_price", "unit_cost"],
    "orders": ["order_id", "customer_id", "order_date", "sales_channel", "sales_rep_id"],
    "order_items": [
        "order_item_id",
        "order_id",
        "product_id",
        "quantity",
        "list_price_at_sale",
        "realized_unit_price",
        "discount_pct",
    ],
    "sales_reps": ["sales_rep_id", "team", "region"],
}


def _result_row(check_name: str, status: str, failed_rows: int, detail: str) -> dict:
    return {
        "check_name": check_name,
        "status": status,
        "failed_rows": int(failed_rows),
        "detail": detail,
    }


def _missing_columns(table: pd.DataFrame, required_columns: Iterable[str]) -> list[str]:
    return [col for col in required_columns if col not in table.columns]


def validate_raw_tables(raw_tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, bool]:
    checks: list[dict] = []

    for table_name, required in RAW_REQUIRED_COLUMNS.items():
        if table_name not in raw_tables:
            checks.append(_result_row(f"{table_name}_exists", "FAIL", 1, "table missing"))
            continue

        missing_cols = _missing_columns(raw_tables[table_name], required)
        checks.append(
            _result_row(
                f"{table_name}_required_columns",
                "PASS" if not missing_cols else "FAIL",
                len(missing_cols),
                "all required columns present" if not missing_cols else f"missing: {missing_cols}",
            )
        )

    required_tables = {"customers", "products", "orders", "order_items", "sales_reps"}
    any_missing_columns = any(
        bool(_missing_columns(raw_tables[t], RAW_REQUIRED_COLUMNS[t]))
        for t in required_tables
        if t in raw_tables
    )
    if not required_tables.issubset(raw_tables.keys()) or any_missing_columns:
        report = pd.DataFrame(checks)
        return report, bool((report["status"] == "PASS").all())

    customers = raw_tables["customers"].copy()
    products = raw_tables["products"].copy()
    orders = raw_tables["orders"].copy()
    order_items = raw_tables["order_items"].copy()
    sales_reps = raw_tables["sales_reps"].copy()

    minimum_rows = {
        "customers": 1,
        "products": 1,
        "orders": 1,
        "order_items": 1,
        "sales_reps": 1,
    }
    for table_name, minimum in minimum_rows.items():
        row_count = int(len(raw_tables[table_name]))
        checks.append(
            _result_row(
                f"{table_name}_row_count_gate",
                "PASS" if row_count >= minimum else "FAIL",
                0 if row_count >= minimum else minimum - row_count,
                f"row_count={row_count}, minimum={minimum}",
            )
        )

    unique_checks = [
        ("customers_unique_customer_id", customers["customer_id"].duplicated().sum()),
        ("products_unique_product_id", products["product_id"].duplicated().sum()),
        ("orders_unique_order_id", orders["order_id"].duplicated().sum()),
        ("order_items_unique_order_item_id", order_items["order_item_id"].duplicated().sum()),
        ("sales_reps_unique_sales_rep_id", sales_reps["sales_rep_id"].duplicated().sum()),
    ]
    for name, fail_count in unique_checks:
        checks.append(
            _result_row(
                name,
                "PASS" if fail_count == 0 else "FAIL",
                int(fail_count),
                "no duplicates" if fail_count == 0 else "duplicate keys found",
            )
        )

    numeric_columns = {
        "products": (products, ["list_price", "unit_cost"]),
        "order_items": (
            order_items,
            ["quantity", "list_price_at_sale", "realized_unit_price", "discount_pct"],
        ),
    }
    numeric_failures = 0
    for table_name, (frame, columns) in numeric_columns.items():
        for column in columns:
            converted = pd.to_numeric(frame[column], errors="coerce")
            failures = int((frame[column].notna() & converted.isna()).sum())
            numeric_failures += failures
            frame[column] = converted
            checks.append(
                _result_row(
                    f"{table_name}_{column}_numeric",
                    "PASS" if failures == 0 else "FAIL",
                    failures,
                    "values are numeric",
                )
            )

    fk_customer_missing = (~orders["customer_id"].isin(customers["customer_id"])).sum()
    fk_rep_missing = (~orders["sales_rep_id"].isin(sales_reps["sales_rep_id"])).sum()
    fk_order_missing = (~order_items["order_id"].isin(orders["order_id"])).sum()
    fk_product_missing = (~order_items["product_id"].isin(products["product_id"])).sum()

    checks.extend(
        [
            _result_row(
                "orders_customer_fk",
                "PASS" if fk_customer_missing == 0 else "FAIL",
                fk_customer_missing,
                "all orders linked to existing customers",
            ),
            _result_row(
                "orders_sales_rep_fk",
                "PASS" if fk_rep_missing == 0 else "FAIL",
                fk_rep_missing,
                "all orders linked to existing sales reps",
            ),
            _result_row(
                "order_items_order_fk",
                "PASS" if fk_order_missing == 0 else "FAIL",
                fk_order_missing,
                "all order lines linked to existing orders",
            ),
            _result_row(
                "order_items_product_fk",
                "PASS" if fk_product_missing == 0 else "FAIL",
                fk_product_missing,
                "all order lines linked to existing products",
            ),
        ]
    )

    for table_name, frame in raw_tables.items():
        null_count = int(frame.isnull().sum().sum())
        checks.append(
            _result_row(
                f"{table_name}_nulls",
                "PASS" if null_count == 0 else "FAIL",
                null_count,
                "no null values" if null_count == 0 else "null values detected",
            )
        )

    if numeric_failures:
        report = pd.DataFrame(checks)
        return report, False

    discount_out_of_bounds = int(((order_items["discount_pct"] < 0) | (order_items["discount_pct"] > 0.7)).sum())
    realized_gt_list = int((order_items["realized_unit_price"] > order_items["list_price_at_sale"]).sum())
    non_positive_qty = int((order_items["quantity"] <= 0).sum())
    non_positive_list_price = int((order_items["list_price_at_sale"] <= 0).sum())
    non_positive_product_price = int((products["list_price"] <= 0).sum())
    negative_unit_cost = int((products["unit_cost"] < 0).sum())

    recomputed_discount = np.where(
        order_items["list_price_at_sale"] > 0,
        1 - (order_items["realized_unit_price"] / order_items["list_price_at_sale"]),
        np.nan,
    )
    discount_mismatch = int(
        (np.abs(recomputed_discount - order_items["discount_pct"]) > DISCOUNT_FORMULA_TOLERANCE).sum()
    )
    order_customer_dates = orders[["customer_id", "order_date"]].merge(
        customers[["customer_id", "signup_date"]].drop_duplicates("customer_id"),
        on="customer_id",
        how="left",
    )
    parsed_order_dates = pd.to_datetime(order_customer_dates["order_date"], errors="coerce")
    parsed_signup_dates = pd.to_datetime(order_customer_dates["signup_date"], errors="coerce")
    invalid_dates = int(parsed_order_dates.isna().sum() + parsed_signup_dates.isna().sum())
    orders_before_signup = int(
        (parsed_order_dates < parsed_signup_dates).sum()
    )

    checks.extend(
        [
            _result_row(
                "order_items_discount_bounds",
                "PASS" if discount_out_of_bounds == 0 else "FAIL",
                discount_out_of_bounds,
                "discounts are within [0, 0.7]",
            ),
            _result_row(
                "order_items_realized_lte_list",
                "PASS" if realized_gt_list == 0 else "FAIL",
                realized_gt_list,
                "realized price does not exceed list price at sale",
            ),
            _result_row(
                "order_items_positive_quantity",
                "PASS" if non_positive_qty == 0 else "FAIL",
                non_positive_qty,
                "all quantities are positive",
            ),
            _result_row(
                "order_items_positive_list_price",
                "PASS" if non_positive_list_price == 0 else "FAIL",
                non_positive_list_price,
                "list price at sale is positive",
            ),
            _result_row(
                "products_positive_list_price",
                "PASS" if non_positive_product_price == 0 else "FAIL",
                non_positive_product_price,
                "product list prices are positive",
            ),
            _result_row(
                "products_non_negative_unit_cost",
                "PASS" if negative_unit_cost == 0 else "FAIL",
                negative_unit_cost,
                "product unit costs are non-negative",
            ),
            _result_row(
                "order_items_discount_formula_consistency",
                "PASS" if discount_mismatch == 0 else "FAIL",
                discount_mismatch,
                f"discount aligns with price arithmetic within {DISCOUNT_FORMULA_TOLERANCE:.4f}",
            ),
            _result_row(
                "customer_and_order_dates_valid",
                "PASS" if invalid_dates == 0 else "FAIL",
                invalid_dates,
                "customer signup and order dates are parseable",
            ),
            _result_row(
                "orders_not_before_customer_signup",
                "PASS" if orders_before_signup == 0 else "FAIL",
                orders_before_signup,
                "orders occur on or after customer signup",
            ),
        ]
    )

    report = pd.DataFrame(checks)
    is_valid = bool((report["status"] == "PASS").all())
    return report, is_valid


def validate_processed_tables(processed_tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, bool]:
    checks: list[dict] = []

    required_processed = {
        "order_item_pricing_metrics": [
            "order_item_id",
            "order_id",
            "customer_id",
            "realized_price",
            "discount_depth",
            "discount_bucket",
            "margin_proxy_pct",
        ],
        "customer_pricing_profile": [
            "customer_id",
            "avg_discount_pct",
            "share_orders_discounted",
            "revenue_high_discount_share",
            "product_diversity",
            "repeat_discount_behavior",
        ],
        "segment_pricing_summary": [
            "segment",
            "avg_discount_pct",
            "realized_price_variance",
            "margin_erosion_proxy",
        ],
        "customer_risk_scores": [
            "customer_id",
            "pricing_risk_score",
            "discount_dependency_score",
            "margin_erosion_score",
            "governance_priority_score",
            "risk_tier",
            "main_risk_driver",
            "recommended_action",
        ],
    }

    for table_name, required_cols in required_processed.items():
        if table_name not in processed_tables:
            checks.append(_result_row(f"{table_name}_exists", "FAIL", 1, "processed table missing"))
            continue

        frame = processed_tables[table_name]
        missing_cols = _missing_columns(frame, required_cols)
        checks.append(
            _result_row(
                f"{table_name}_required_columns",
                "PASS" if not missing_cols else "FAIL",
                len(missing_cols),
                "all required columns present" if not missing_cols else f"missing: {missing_cols}",
            )
        )

    if "order_item_pricing_metrics" in processed_tables:
        pricing = processed_tables["order_item_pricing_metrics"]

        duplicated_order_item = int(pricing["order_item_id"].duplicated().sum())
        checks.append(
            _result_row(
                "order_item_pricing_metrics_unique_order_item_id",
                "PASS" if duplicated_order_item == 0 else "FAIL",
                duplicated_order_item,
                "order-item grain uniqueness",
            )
        )

        discount_out_of_bounds = int(((pricing["discount_depth"] < 0) | (pricing["discount_depth"] > 1)).sum())
        checks.append(
            _result_row(
                "order_item_pricing_metrics_discount_depth_bounds",
                "PASS" if discount_out_of_bounds == 0 else "FAIL",
                discount_out_of_bounds,
                "discount_depth remains within [0, 1]",
            )
        )

        if {"realized_price", "list_price_at_sale"}.issubset(pricing.columns):
            realized_gt_list = int((pricing["realized_price"] > pricing["list_price_at_sale"]).sum())
            checks.append(
                _result_row(
                    "order_item_pricing_metrics_realized_lte_list",
                    "PASS" if realized_gt_list == 0 else "FAIL",
                    realized_gt_list,
                    "realized price does not exceed list price at sale",
                )
            )

        if {"line_revenue", "line_list_revenue"}.issubset(pricing.columns):
            total_revenue = float(pricing["line_revenue"].sum())
            total_list_revenue = float(pricing["line_list_revenue"].sum())
            if total_list_revenue > 0:
                weighted_direct = float(np.average(pricing["discount_depth"], weights=pricing["line_list_revenue"]))
                weighted_from_totals = float(1 - (total_revenue / total_list_revenue))
                weighted_match = bool(abs(weighted_direct - weighted_from_totals) <= 0.001)
                detail = f"weighted_direct={weighted_direct:.6f}, weighted_from_totals={weighted_from_totals:.6f}"
            else:
                weighted_match = False
                detail = "total_list_revenue must be positive for weighted discount reconciliation"
            checks.append(
                _result_row(
                    "order_item_pricing_metrics_weighted_discount_reconciliation",
                    "PASS" if weighted_match else "FAIL",
                    0 if weighted_match else 1,
                    detail,
                )
            )

        arithmetic_columns = {
            "quantity",
            "realized_price",
            "list_price_at_sale",
            "unit_cost",
            "line_revenue",
            "line_list_revenue",
            "line_cost",
            "gross_margin_value",
            "margin_proxy_pct",
            "discount_depth",
            "high_discount_flag",
        }
        if arithmetic_columns.issubset(pricing.columns):
            expected_revenue = pricing["quantity"] * pricing["realized_price"]
            expected_list_revenue = pricing["quantity"] * pricing["list_price_at_sale"]
            expected_cost = pricing["quantity"] * pricing["unit_cost"]
            expected_margin = pricing["line_revenue"] - pricing["line_cost"]
            expected_margin_pct = np.where(
                pricing["line_revenue"] > 0,
                pricing["gross_margin_value"] / pricing["line_revenue"],
                np.nan,
            )
            expected_high_discount = (pricing["discount_depth"] >= get_high_discount_threshold()).astype(int)

            arithmetic_checks = {
                "order_item_pricing_metrics_line_revenue_formula": np.isclose(
                    pricing["line_revenue"], expected_revenue, rtol=0, atol=0.01
                ),
                "order_item_pricing_metrics_list_revenue_formula": np.isclose(
                    pricing["line_list_revenue"], expected_list_revenue, rtol=0, atol=0.01
                ),
                "order_item_pricing_metrics_line_cost_formula": np.isclose(
                    pricing["line_cost"], expected_cost, rtol=0, atol=0.01
                ),
                "order_item_pricing_metrics_gross_margin_formula": np.isclose(
                    pricing["gross_margin_value"], expected_margin, rtol=0, atol=0.01
                ),
                "order_item_pricing_metrics_margin_proxy_formula": np.isclose(
                    pricing["margin_proxy_pct"], expected_margin_pct, rtol=0, atol=1e-9, equal_nan=True
                ),
                "order_item_pricing_metrics_high_discount_policy": pricing["high_discount_flag"].eq(
                    expected_high_discount
                ),
            }
            for check_name, matches in arithmetic_checks.items():
                failures = int((~matches).sum())
                checks.append(
                    _result_row(
                        check_name,
                        "PASS" if failures == 0 else "FAIL",
                        failures,
                        "derived metric matches source arithmetic and policy",
                    )
                )

    if "customer_risk_scores" in processed_tables:
        risk = processed_tables["customer_risk_scores"]
        score_columns = [
            "pricing_risk_score",
            "discount_dependency_score",
            "margin_erosion_score",
            "governance_priority_score",
        ]
        for col in score_columns:
            invalid = int(((risk[col] < 0) | (risk[col] > 100)).sum())
            checks.append(
                _result_row(
                    f"{col}_bounds",
                    "PASS" if invalid == 0 else "FAIL",
                    invalid,
                    "score remains in [0, 100]",
                )
            )

        unique_customer_risk = int(risk["customer_id"].duplicated().sum())
        checks.append(
            _result_row(
                "customer_risk_scores_unique_customer_id",
                "PASS" if unique_customer_risk == 0 else "FAIL",
                unique_customer_risk,
                "customer-level grain uniqueness",
            )
        )

        allowed_risk_tiers = {"Low", "Medium", "High", "Critical"}
        invalid_tiers = int((~risk["risk_tier"].isin(allowed_risk_tiers)).sum())
        checks.append(
            _result_row(
                "customer_risk_scores_allowed_tiers",
                "PASS" if invalid_tiers == 0 else "FAIL",
                invalid_tiers,
                "risk_tier values align with policy taxonomy",
            )
        )

        allowed_actions = {
            "monitor only",
            "review segment pricing",
            "investigate rep behavior",
            "redesign discount policy",
            "tighten approval thresholds",
        }
        invalid_actions = int((~risk["recommended_action"].isin(allowed_actions)).sum())
        checks.append(
            _result_row(
                "customer_risk_scores_allowed_actions",
                "PASS" if invalid_actions == 0 else "FAIL",
                invalid_actions,
                "recommended_action values align with governance playbook",
            )
        )

    if "customer_pricing_profile" in processed_tables:
        profile = processed_tables["customer_pricing_profile"]

        unique_customer_profile = int(profile["customer_id"].duplicated().sum())
        checks.append(
            _result_row(
                "customer_pricing_profile_unique_customer_id",
                "PASS" if unique_customer_profile == 0 else "FAIL",
                unique_customer_profile,
                "customer-level grain uniqueness",
            )
        )

        share_columns = [
            "share_orders_discounted",
            "share_orders_high_discount",
            "revenue_high_discount_share",
            "repeat_discount_behavior",
        ]
        for col in share_columns:
            if col in profile.columns:
                invalid = int(((profile[col] < 0) | (profile[col] > 1)).sum())
                checks.append(
                    _result_row(
                        f"customer_pricing_profile_{col}_bounds",
                        "PASS" if invalid == 0 else "FAIL",
                        invalid,
                        f"{col} remains within [0, 1]",
                    )
                )

        if "order_item_pricing_metrics" in processed_tables and "avg_margin_proxy_pct" in profile.columns:
            pricing = processed_tables["order_item_pricing_metrics"]
            expected_margin = (
                pricing.groupby("customer_id", as_index=False)
                .agg(total_revenue=("line_revenue", "sum"), gross_margin_value=("gross_margin_value", "sum"))
            )
            expected_margin["expected_margin_proxy_pct"] = np.where(
                expected_margin["total_revenue"] > 0,
                expected_margin["gross_margin_value"] / expected_margin["total_revenue"],
                np.nan,
            )
            margin_comparison = profile[["customer_id", "avg_margin_proxy_pct"]].merge(
                expected_margin[["customer_id", "expected_margin_proxy_pct"]],
                on="customer_id",
                how="outer",
                validate="one_to_one",
            )
            margin_failures = int(
                (
                    ~np.isclose(
                        margin_comparison["avg_margin_proxy_pct"],
                        margin_comparison["expected_margin_proxy_pct"],
                        rtol=0,
                        atol=1e-9,
                        equal_nan=True,
                    )
                ).sum()
            )
            checks.append(
                _result_row(
                    "customer_pricing_profile_weighted_margin_reconciliation",
                    "PASS" if margin_failures == 0 else "FAIL",
                    margin_failures,
                    "customer margin proxy reconciles to gross margin divided by revenue",
                )
            )

    if {"customer_pricing_profile", "customer_risk_scores"}.issubset(processed_tables.keys()):
        profile_count = int(len(processed_tables["customer_pricing_profile"]))
        risk_count = int(len(processed_tables["customer_risk_scores"]))
        checks.append(
            _result_row(
                "customer_profile_to_risk_rowcount_consistency",
                "PASS" if profile_count == risk_count else "FAIL",
                abs(profile_count - risk_count),
                f"profile_rows={profile_count}, risk_rows={risk_count}",
            )
        )

    report = pd.DataFrame(checks)
    is_valid = bool((report["status"] == "PASS").all()) if not report.empty else False
    return report, is_valid
