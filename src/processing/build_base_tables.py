from __future__ import annotations

import pandas as pd

REQUIRED_RAW_COLUMNS = {
    "customers": {"customer_id", "signup_date", "segment", "region", "company_size"},
    "products": {"product_id", "product_name", "category", "list_price", "unit_cost"},
    "orders": {"order_id", "customer_id", "order_date", "sales_channel", "sales_rep_id"},
    "order_items": {
        "order_item_id",
        "order_id",
        "product_id",
        "quantity",
        "list_price_at_sale",
        "realized_unit_price",
        "discount_pct",
    },
    "sales_reps": {"sales_rep_id", "team", "region"},
}


def _require_raw_tables(raw_tables: dict[str, pd.DataFrame]) -> None:
    missing_tables = sorted(set(REQUIRED_RAW_COLUMNS) - set(raw_tables))
    if missing_tables:
        raise KeyError(f"Missing required raw table(s): {', '.join(missing_tables)}")

    missing_columns = {
        table_name: sorted(required_cols - set(raw_tables[table_name].columns))
        for table_name, required_cols in REQUIRED_RAW_COLUMNS.items()
        if required_cols - set(raw_tables[table_name].columns)
    }
    if missing_columns:
        details = "; ".join(
            f"{table}: {', '.join(columns)}" for table, columns in missing_columns.items()
        )
        raise KeyError(f"Missing required raw column(s): {details}")


def _merge_many_to_one(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    on: str,
    dimension_name: str,
    how: str = "left",
    suffixes: tuple[str, str] = ("", "_dim"),
) -> pd.DataFrame:
    merged = left.merge(
        right,
        on=on,
        how=how,
        validate="many_to_one",
        indicator=True,
        suffixes=suffixes,
    )
    missing = merged["_merge"].ne("both")
    if missing.any():
        examples = merged.loc[missing, on].dropna().astype(str).drop_duplicates().head(5).tolist()
        raise ValueError(
            f"Merge integrity failed for {dimension_name}: {int(missing.sum())} rows have no matching {on}. "
            f"Examples: {examples}"
        )
    return merged.drop(columns="_merge")


def build_order_item_enriched(raw_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    _require_raw_tables(raw_tables)

    customers = raw_tables["customers"].copy()
    products = raw_tables["products"].copy()
    orders = raw_tables["orders"].copy()
    order_items = raw_tables["order_items"].copy()
    sales_reps = raw_tables["sales_reps"].copy()

    customers["signup_date"] = pd.to_datetime(customers["signup_date"])
    orders["order_date"] = pd.to_datetime(orders["order_date"])

    enriched = _merge_many_to_one(
        order_items,
        orders,
        on="order_id",
        dimension_name="orders",
    )
    enriched = _merge_many_to_one(
        enriched,
        customers,
        on="customer_id",
        dimension_name="customers",
    )
    enriched = _merge_many_to_one(
        enriched,
        products,
        on="product_id",
        dimension_name="products",
        suffixes=("", "_product"),
    )
    enriched = _merge_many_to_one(
        enriched,
        sales_reps.rename(columns={"region": "rep_region"}),
        on="sales_rep_id",
        dimension_name="sales_reps",
    )

    enriched["order_month"] = enriched["order_date"].dt.to_period("M").astype(str)
    enriched["order_quarter"] = enriched["order_date"].dt.to_period("Q").astype(str)
    enriched["days_since_signup"] = (enriched["order_date"] - enriched["signup_date"]).dt.days

    ordered_columns = [
        "order_item_id",
        "order_id",
        "order_date",
        "order_month",
        "order_quarter",
        "customer_id",
        "segment",
        "region",
        "company_size",
        "sales_channel",
        "sales_rep_id",
        "team",
        "rep_region",
        "product_id",
        "product_name",
        "category",
        "quantity",
        "list_price_at_sale",
        "realized_unit_price",
        "discount_pct",
        "list_price",
        "unit_cost",
        "days_since_signup",
    ]

    return (
        enriched[ordered_columns]
        .sort_values(["order_date", "order_id", "order_item_id"])
        .reset_index(drop=True)
    )
