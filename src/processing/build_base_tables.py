from __future__ import annotations

from typing import Dict

import pandas as pd


def build_order_item_enriched(raw_tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    customers = raw_tables["customers"].copy()
    products = raw_tables["products"].copy()
    orders = raw_tables["orders"].copy()
    order_items = raw_tables["order_items"].copy()
    sales_reps = raw_tables["sales_reps"].copy()

    customers["signup_date"] = pd.to_datetime(customers["signup_date"])
    orders["order_date"] = pd.to_datetime(orders["order_date"])

    enriched = (
        order_items.merge(orders, on="order_id", how="left")
        .merge(customers, on="customer_id", how="left")
        .merge(products, on="product_id", how="left", suffixes=("", "_product"))
        .merge(sales_reps.rename(columns={"region": "rep_region"}), on="sales_rep_id", how="left")
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

    return enriched[ordered_columns].sort_values(["order_date", "order_id", "order_item_id"]).reset_index(drop=True)
