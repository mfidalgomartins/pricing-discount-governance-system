from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd


@dataclass
class SyntheticDataConfig:
    seed: int = 42
    n_customers: int = 1200
    n_products: int = 28
    n_sales_reps: int = 45
    n_orders: int = 18000
    start_date: str = "2023-01-01"
    end_date: str = "2025-12-31"


def _generate_customers(config: SyntheticDataConfig, rng: np.random.Generator) -> pd.DataFrame:
    segments = ["SMB", "Mid-Market", "Enterprise", "Public Sector"]
    regions = ["North America", "Europe", "LATAM", "APAC"]

    segment = rng.choice(segments, size=config.n_customers, p=[0.45, 0.30, 0.20, 0.05])
    region = rng.choice(regions, size=config.n_customers, p=[0.42, 0.28, 0.14, 0.16])

    company_size_map = {
        "SMB": ["Small", "Medium"],
        "Mid-Market": ["Medium", "Large"],
        "Enterprise": ["Large", "Enterprise"],
        "Public Sector": ["Large", "Enterprise"],
    }
    company_size = [rng.choice(company_size_map[s], p=[0.7, 0.3] if s == "SMB" else [0.6, 0.4]) for s in segment]

    signup_dates = pd.to_datetime("2019-01-01") + pd.to_timedelta(
        rng.integers(0, 1460, size=config.n_customers), unit="D"
    )

    customers = pd.DataFrame(
        {
            "customer_id": [f"C{idx:05d}" for idx in range(1, config.n_customers + 1)],
            "signup_date": signup_dates,
            "segment": segment,
            "region": region,
            "company_size": company_size,
        }
    )

    dependency_base = {
        "SMB": 0.42,
        "Mid-Market": 0.52,
        "Enterprise": 0.60,
        "Public Sector": 0.56,
    }
    volume_base = {
        "SMB": 0.8,
        "Mid-Market": 1.2,
        "Enterprise": 1.8,
        "Public Sector": 1.0,
    }

    customers["discount_dependency_trait"] = [
        np.clip(rng.beta(2, 3) * 0.7 + dependency_base[s] * 0.3, 0.05, 0.95) for s in segment
    ]
    customers["order_weight"] = [
        np.clip(rng.gamma(2.0, volume_base[s]), 0.15, 12.0) for s in segment
    ]
    return customers


def _generate_products(config: SyntheticDataConfig, rng: np.random.Generator) -> pd.DataFrame:
    categories = ["Core Platform", "Analytics", "Security", "Collaboration", "Professional Services"]
    category_weights = [0.28, 0.22, 0.18, 0.16, 0.16]

    category = rng.choice(categories, size=config.n_products, p=category_weights)

    pricing_rules = {
        "Core Platform": (4500, 18000, 0.36, 0.52, 0.48),
        "Analytics": (1800, 9000, 0.30, 0.45, 0.62),
        "Security": (2200, 11000, 0.34, 0.50, 0.58),
        "Collaboration": (900, 4200, 0.24, 0.40, 0.52),
        "Professional Services": (2500, 14000, 0.60, 0.76, 0.35),
    }

    records = []
    for i, cat in enumerate(category, start=1):
        low_price, high_price, min_cost_ratio, max_cost_ratio, discount_sensitivity = pricing_rules[cat]
        list_price = rng.uniform(low_price, high_price)
        cost_ratio = rng.uniform(min_cost_ratio, max_cost_ratio)
        unit_cost = list_price * cost_ratio
        records.append(
            {
                "product_id": f"P{i:04d}",
                "product_name": f"{cat.split()[0]} Product {i:02d}",
                "category": cat,
                "list_price": round(float(list_price), 2),
                "unit_cost": round(float(unit_cost), 2),
                "discount_sensitivity": discount_sensitivity + rng.normal(0, 0.05),
            }
        )

    products = pd.DataFrame(records)
    products["discount_sensitivity"] = products["discount_sensitivity"].clip(0.2, 0.9)
    return products


def _generate_sales_reps(config: SyntheticDataConfig, rng: np.random.Generator) -> pd.DataFrame:
    teams = ["New Business", "Expansion", "Channel"]
    regions = ["North America", "Europe", "LATAM", "APAC"]

    team = rng.choice(teams, size=config.n_sales_reps, p=[0.44, 0.36, 0.20])
    region = rng.choice(regions, size=config.n_sales_reps, p=[0.40, 0.30, 0.14, 0.16])

    sales_reps = pd.DataFrame(
        {
            "sales_rep_id": [f"SR{idx:04d}" for idx in range(1, config.n_sales_reps + 1)],
            "team": team,
            "region": region,
            "aggressiveness": rng.normal(1.0, 0.14, size=config.n_sales_reps).clip(0.75, 1.35),
        }
    )
    return sales_reps


def _sample_sales_channel(segment: str, rng: np.random.Generator) -> str:
    channel_mix = {
        "SMB": ("Online", [0.42, 0.28, 0.20, 0.10]),
        "Mid-Market": ("Direct", [0.14, 0.44, 0.26, 0.16]),
        "Enterprise": ("Direct", [0.08, 0.66, 0.18, 0.08]),
        "Public Sector": ("Direct", [0.05, 0.57, 0.24, 0.14]),
    }
    channels = ["Online", "Direct", "Partner", "Reseller"]
    _, probs = channel_mix[segment]
    return rng.choice(channels, p=probs)


def _generate_orders(
    config: SyntheticDataConfig,
    customers: pd.DataFrame,
    sales_reps: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    all_dates = pd.date_range(config.start_date, config.end_date, freq="D")
    date_weights = np.ones(len(all_dates), dtype=float)

    quarter_end_mask = all_dates.month.isin([3, 6, 9, 12]) & (all_dates.day >= 20)
    date_weights[quarter_end_mask] *= 1.55
    date_weights[all_dates.month.isin([11, 12])] *= 1.2
    date_weights = date_weights / date_weights.sum()

    customer_probs = customers["order_weight"].to_numpy()
    customer_probs = customer_probs / customer_probs.sum()
    sampled_customer_idx = rng.choice(customers.index.to_numpy(), size=config.n_orders, p=customer_probs)

    order_dates = rng.choice(all_dates, size=config.n_orders, p=date_weights)
    order_dates = pd.to_datetime(order_dates)

    reps_by_region = sales_reps.groupby("region")["sales_rep_id"].apply(list).to_dict()
    primary_rep = {
        row.customer_id: rng.choice(reps_by_region.get(row.region, sales_reps["sales_rep_id"].tolist()))
        for row in customers.itertuples(index=False)
    }

    orders_records = []
    for i, (cust_idx, order_date) in enumerate(zip(sampled_customer_idx, order_dates), start=1):
        customer = customers.loc[cust_idx]
        segment = customer["segment"]
        region = customer["region"]
        channel = _sample_sales_channel(segment, rng)

        regional_reps = reps_by_region.get(region, sales_reps["sales_rep_id"].tolist())
        assigned_rep = primary_rep[customer["customer_id"]] if rng.random() < 0.76 else rng.choice(regional_reps)

        # Keep online deals mostly with non-channel reps to mimic inside sales ownership.
        if channel == "Online" and rng.random() < 0.65:
            non_channel_reps = sales_reps.loc[sales_reps["team"] != "Channel", "sales_rep_id"].to_list()
            assigned_rep = rng.choice(non_channel_reps)

        orders_records.append(
            {
                "order_id": f"O{i:07d}",
                "customer_id": customer["customer_id"],
                "order_date": order_date,
                "sales_channel": channel,
                "sales_rep_id": assigned_rep,
            }
        )

    orders = pd.DataFrame(orders_records).sort_values("order_date").reset_index(drop=True)
    return orders


def _select_product_for_segment(
    products: pd.DataFrame,
    segment: str,
    rng: np.random.Generator,
) -> pd.Series:
    segment_preferences = {
        "SMB": {
            "Collaboration": 0.34,
            "Analytics": 0.24,
            "Core Platform": 0.19,
            "Security": 0.14,
            "Professional Services": 0.09,
        },
        "Mid-Market": {
            "Core Platform": 0.27,
            "Analytics": 0.24,
            "Security": 0.21,
            "Collaboration": 0.18,
            "Professional Services": 0.10,
        },
        "Enterprise": {
            "Core Platform": 0.33,
            "Security": 0.27,
            "Analytics": 0.19,
            "Professional Services": 0.14,
            "Collaboration": 0.07,
        },
        "Public Sector": {
            "Core Platform": 0.30,
            "Security": 0.22,
            "Professional Services": 0.22,
            "Analytics": 0.18,
            "Collaboration": 0.08,
        },
    }

    cat_probs = segment_preferences[segment]
    categories = list(cat_probs.keys())
    probs = np.array(list(cat_probs.values()), dtype=float)
    probs = probs / probs.sum()

    selected_category = rng.choice(categories, p=probs)
    subset = products[products["category"] == selected_category]
    return subset.sample(n=1, random_state=int(rng.integers(0, 10_000_000))).iloc[0]


def _quantity_by_context(category: str, company_size: str, rng: np.random.Generator) -> int:
    base = {
        "Small": 2,
        "Medium": 4,
        "Large": 8,
        "Enterprise": 13,
    }[company_size]

    category_multiplier = {
        "Core Platform": 1.4,
        "Analytics": 1.1,
        "Security": 1.0,
        "Collaboration": 1.8,
        "Professional Services": 0.7,
    }[category]

    quantity = rng.poisson(base * category_multiplier)
    return int(np.clip(quantity, 1, 35))


def _generate_order_items(
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    products: pd.DataFrame,
    sales_reps: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    customer_lookup = customers.set_index("customer_id")
    product_lookup = products.set_index("product_id")
    rep_lookup = sales_reps.set_index("sales_rep_id")

    segment_base_discount = {
        "SMB": 0.030,
        "Mid-Market": 0.060,
        "Enterprise": 0.100,
        "Public Sector": 0.080,
    }
    channel_discount_adj = {
        "Online": 0.000,
        "Direct": 0.012,
        "Partner": 0.032,
        "Reseller": 0.052,
    }

    lines = []
    line_id = 1

    for order in orders.itertuples(index=False):
        customer = customer_lookup.loc[order.customer_id]
        rep = rep_lookup.loc[order.sales_rep_id]

        num_items = int(rng.choice([1, 2, 3, 4, 5], p=[0.42, 0.31, 0.16, 0.08, 0.03]))
        if customer["segment"] in {"Enterprise", "Public Sector"}:
            num_items = min(num_items + int(rng.random() < 0.35), 6)

        for _ in range(num_items):
            product = _select_product_for_segment(products, customer["segment"], rng)
            quantity = _quantity_by_context(product["category"], customer["company_size"], rng)

            year_uplift = 1 + 0.03 * (order.order_date.year - 2023)
            list_price_at_sale = float(product["list_price"]) * year_uplift * (1 + rng.normal(0, 0.015))
            list_price_at_sale = max(list_price_at_sale, float(product["list_price"]) * 0.9)

            quarter_push = 0.02 if (order.order_date.month in [3, 6, 9, 12] and order.order_date.day >= 20) else 0.0
            dependency_effect = float(customer["discount_dependency_trait"]) * 0.10
            rep_effect = (float(rep["aggressiveness"]) - 1.0) * 0.07
            sensitivity_effect = float(product["discount_sensitivity"]) * 0.05
            channel_effect = channel_discount_adj[order.sales_channel]
            random_noise = float(rng.normal(0, 0.022))

            preliminary_discount = (
                segment_base_discount[customer["segment"]]
                + channel_effect
                + quarter_push
                + dependency_effect
                + rep_effect
                + sensitivity_effect
                + random_noise
            )

            if quantity >= 15:
                preliminary_discount += 0.01

            if rng.random() < 0.008:
                preliminary_discount += rng.uniform(0.02, 0.08)

            segment_caps = {
                "SMB": 0.30,
                "Mid-Market": 0.38,
                "Enterprise": 0.46,
                "Public Sector": 0.42,
            }
            discount_pct = float(np.clip(preliminary_discount, 0.0, segment_caps[customer["segment"]]))
            realized_price = list_price_at_sale * (1 - discount_pct)

            # Margin floor prevents impossible pricing but still allows erosion.
            cost_floor = float(product["unit_cost"]) * rng.uniform(0.82, 0.95)
            realized_price = max(realized_price, cost_floor)
            discount_pct = 1 - (realized_price / list_price_at_sale)
            discount_pct = float(np.clip(discount_pct, 0.0, 0.65))

            lines.append(
                {
                    "order_item_id": f"OI{line_id:08d}",
                    "order_id": order.order_id,
                    "product_id": product["product_id"],
                    "quantity": quantity,
                    "list_price_at_sale": round(list_price_at_sale, 2),
                    "realized_unit_price": round(realized_price, 2),
                    "discount_pct": round(discount_pct, 4),
                }
            )
            line_id += 1

    order_items = pd.DataFrame(lines)
    return order_items


def generate_synthetic_business_data(config: SyntheticDataConfig | None = None) -> Dict[str, pd.DataFrame]:
    config = config or SyntheticDataConfig()
    rng = np.random.default_rng(config.seed)

    customers = _generate_customers(config, rng)
    products = _generate_products(config, rng)
    sales_reps = _generate_sales_reps(config, rng)
    orders = _generate_orders(config, customers, sales_reps, rng)
    order_items = _generate_order_items(orders, customers, products, sales_reps, rng)

    raw_tables: Dict[str, pd.DataFrame] = {
        "customers": customers[["customer_id", "signup_date", "segment", "region", "company_size"]],
        "products": products[["product_id", "product_name", "category", "list_price", "unit_cost"]],
        "orders": orders[["order_id", "customer_id", "order_date", "sales_channel", "sales_rep_id"]],
        "order_items": order_items[
            [
                "order_item_id",
                "order_id",
                "product_id",
                "quantity",
                "list_price_at_sale",
                "realized_unit_price",
                "discount_pct",
            ]
        ],
        "sales_reps": sales_reps[["sales_rep_id", "team", "region"]],
    }

    return raw_tables
