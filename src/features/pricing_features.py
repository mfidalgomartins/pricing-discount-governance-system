from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


DISCOUNT_BUCKETS = [-0.001, 0.05, 0.10, 0.20, 0.30, 1.0]
DISCOUNT_LABELS = ["0-5%", "5-10%", "10-20%", "20-30%", "30%+"]


def build_order_item_pricing_metrics(enriched: pd.DataFrame) -> pd.DataFrame:
    metrics = enriched.copy()

    metrics["realized_price"] = metrics["realized_unit_price"]
    metrics["discount_depth"] = metrics["discount_pct"]
    metrics["discount_bucket"] = pd.cut(
        metrics["discount_depth"],
        bins=DISCOUNT_BUCKETS,
        labels=DISCOUNT_LABELS,
        include_lowest=True,
    ).astype(str)

    metrics["line_list_revenue"] = metrics["quantity"] * metrics["list_price_at_sale"]
    metrics["line_revenue"] = metrics["quantity"] * metrics["realized_price"]
    metrics["line_cost"] = metrics["quantity"] * metrics["unit_cost"]
    metrics["gross_margin_value"] = metrics["line_revenue"] - metrics["line_cost"]
    metrics["margin_proxy_pct"] = np.where(
        metrics["line_revenue"] > 0,
        metrics["gross_margin_value"] / metrics["line_revenue"],
        np.nan,
    )
    metrics["high_discount_flag"] = (metrics["discount_depth"] >= 0.20).astype(int)
    metrics["discounted_flag"] = (metrics["discount_depth"] >= 0.05).astype(int)

    return metrics


def build_customer_pricing_profile(pricing_metrics: pd.DataFrame) -> pd.DataFrame:
    pricing_metrics = pricing_metrics.copy()
    pricing_metrics["discount_weighted_value"] = pricing_metrics["discount_depth"] * pricing_metrics["line_list_revenue"]
    pricing_metrics["high_discount_revenue_component"] = np.where(
        pricing_metrics["high_discount_flag"] == 1,
        pricing_metrics["line_revenue"],
        0.0,
    )

    order_level = (
        pricing_metrics.groupby(["customer_id", "order_id", "order_date"], as_index=False)
        .agg(
            order_revenue=("line_revenue", "sum"),
            order_discount_depth=("discount_depth", "mean"),
            high_discount_order=("high_discount_flag", "max"),
            discounted_order=("discounted_flag", "max"),
        )
        .sort_values(["customer_id", "order_date", "order_id"])
    )

    order_level["prev_high_discount_order"] = order_level.groupby("customer_id")["high_discount_order"].shift(1).fillna(0)
    order_level["repeat_high_discount_pair"] = (
        (order_level["high_discount_order"] == 1) & (order_level["prev_high_discount_order"] == 1)
    ).astype(int)

    consecutive_denominator = order_level.groupby("customer_id").size().sub(1).clip(lower=1)
    repeat_behavior = (
        order_level.groupby("customer_id")["repeat_high_discount_pair"].sum() / consecutive_denominator
    ).rename("repeat_discount_behavior")

    customer_profile = (
        pricing_metrics.groupby("customer_id", as_index=False)
        .agg(
            segment=("segment", "first"),
            region=("region", "first"),
            company_size=("company_size", "first"),
            total_orders=("order_id", pd.Series.nunique),
            total_order_items=("order_item_id", "count"),
            total_revenue=("line_revenue", "sum"),
            avg_discount_pct=("discount_depth", "mean"),
            total_list_revenue=("line_list_revenue", "sum"),
            weighted_discount_num=("discount_weighted_value", "sum"),
            share_order_items_discounted=("discounted_flag", "mean"),
            revenue_high_discount=("high_discount_revenue_component", "sum"),
            product_diversity=("product_id", pd.Series.nunique),
            avg_margin_proxy_pct=("margin_proxy_pct", "mean"),
            realized_price_cv=("realized_price", lambda s: float(s.std(ddof=0) / s.mean()) if s.mean() > 0 else 0.0),
        )
    )

    order_stats = order_level.groupby("customer_id", as_index=False).agg(
        share_orders_discounted=("discounted_order", "mean"),
        share_orders_high_discount=("high_discount_order", "mean"),
    )

    customer_profile = customer_profile.merge(order_stats, on="customer_id", how="left")
    customer_profile = customer_profile.merge(repeat_behavior.reset_index(), on="customer_id", how="left")
    customer_profile["weighted_discount_pct"] = np.where(
        customer_profile["total_list_revenue"] > 0,
        customer_profile["weighted_discount_num"] / customer_profile["total_list_revenue"],
        0,
    )

    customer_profile["revenue_high_discount_share"] = np.where(
        customer_profile["total_revenue"] > 0,
        customer_profile["revenue_high_discount"] / customer_profile["total_revenue"],
        0,
    )

    fill_cols = [
        "share_orders_discounted",
        "share_orders_high_discount",
        "repeat_discount_behavior",
        "revenue_high_discount_share",
        "realized_price_cv",
    ]
    customer_profile[fill_cols] = customer_profile[fill_cols].fillna(0)

    return customer_profile.drop(
        columns=["revenue_high_discount", "total_list_revenue", "weighted_discount_num"]
    ).sort_values("total_revenue", ascending=False)


def build_segment_pricing_summary(pricing_metrics: pd.DataFrame) -> pd.DataFrame:
    segment_summary = (
        pricing_metrics.groupby("segment", as_index=False)
        .agg(
            total_revenue=("line_revenue", "sum"),
            avg_discount_pct=("discount_depth", "mean"),
            median_discount_pct=("discount_depth", "median"),
            share_high_discount=("high_discount_flag", "mean"),
            avg_margin_proxy_pct=("margin_proxy_pct", "mean"),
            realized_price_variance=("realized_price", "var"),
            realized_price_std=("realized_price", "std"),
        )
    )

    segment_summary["margin_erosion_proxy"] = (
        (1 - segment_summary["avg_margin_proxy_pct"].clip(lower=0, upper=1))
        * segment_summary["share_high_discount"].clip(0, 1)
        * 100
    )
    segment_summary["realized_price_variance"] = segment_summary["realized_price_variance"].fillna(0)
    segment_summary["realized_price_std"] = segment_summary["realized_price_std"].fillna(0)

    return segment_summary.sort_values("margin_erosion_proxy", ascending=False)


def build_segment_channel_diagnostics(pricing_metrics: pd.DataFrame) -> pd.DataFrame:
    diagnostics = (
        pricing_metrics.groupby(["segment", "sales_channel"], as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            avg_discount_pct=("discount_depth", "mean"),
            avg_margin_proxy_pct=("margin_proxy_pct", "mean"),
            high_discount_share=("high_discount_flag", "mean"),
            order_item_count=("order_item_id", "count"),
        )
        .sort_values(["segment", "avg_discount_pct"], ascending=[True, False])
    )

    return diagnostics


def build_feature_tables(enriched: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    order_item_pricing_metrics = build_order_item_pricing_metrics(enriched)
    customer_pricing_profile = build_customer_pricing_profile(order_item_pricing_metrics)
    segment_pricing_summary = build_segment_pricing_summary(order_item_pricing_metrics)
    segment_channel_diagnostics = build_segment_channel_diagnostics(order_item_pricing_metrics)

    return {
        "order_item_pricing_metrics": order_item_pricing_metrics,
        "customer_pricing_profile": customer_pricing_profile,
        "segment_pricing_summary": segment_pricing_summary,
        "segment_channel_diagnostics": segment_channel_diagnostics,
    }
