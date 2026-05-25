from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

try:
    import duckdb
except ImportError as exc:  # pragma: no cover
    raise ImportError("duckdb is required to run the SQL warehouse layer") from exc


@dataclass(frozen=True)
class SqlLayerRunConfig:
    raw_dir: Path
    sql_dir: Path
    db_path: Path
    marts_output_dir: Path
    outputs_dir: Path


RAW_TABLE_SOURCES = {
    "raw_customers": "customers.csv",
    "raw_products": "products.csv",
    "raw_orders": "orders.csv",
    "raw_order_items": "order_items.csv",
    "raw_sales_reps": "sales_reps.csv",
}

MODEL_ORDER = {
    "staging": [
        "stg_customers.sql",
        "stg_products.sql",
        "stg_orders.sql",
        "stg_order_items.sql",
        "stg_sales_reps.sql",
    ],
    "intermediate": [
        "int_order_item_enriched.sql",
        "int_order_item_pricing_metrics.sql",
    ],
    "marts": [
        "mart_customer_pricing_profile.sql",
        "mart_segment_pricing_summary.sql",
        "mart_segment_channel_diagnostics.sql",
        "mart_product_pricing_summary.sql",
        "mart_monthly_pricing_health.sql",
        "mart_overall_pricing_health.sql",
    ],
}

MART_PRIMARY_KEYS = {
    "mart_customer_pricing_profile": ["customer_id"],
    "mart_segment_pricing_summary": ["segment"],
    "mart_segment_channel_diagnostics": ["segment", "sales_channel"],
    "mart_product_pricing_summary": ["product_id"],
    "mart_monthly_pricing_health": ["order_month"],
    "mart_overall_pricing_health": ["as_of_date"],
}


def _load_raw_tables(conn: duckdb.DuckDBPyConnection, raw_dir: Path) -> None:
    for table_name, file_name in RAW_TABLE_SOURCES.items():
        source_path = raw_dir / file_name
        if not source_path.exists():
            raise FileNotFoundError(f"Missing raw source for SQL warehouse: {source_path}")
        conn.execute(
            f"""
            create or replace table {table_name} as
            select *
            from read_csv_auto(?, header=true)
            """,
            [str(source_path)],
        )


def _run_model_file(conn: duckdb.DuckDBPyConnection, model_path: Path) -> None:
    sql = model_path.read_text()
    conn.execute(sql)


def _run_sql_validations(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    checks: list[dict] = []

    def add_check(name: str, passed: bool, detail: str) -> None:
        checks.append(
            {
                "check_name": name,
                "status": "PASS" if passed else "FAIL",
                "detail": detail,
            }
        )

    for mart_name in MART_PRIMARY_KEYS:
        row_count = int(conn.execute(f"select count(*) from {mart_name}").fetchone()[0])
        add_check(f"{mart_name}_row_count_positive", row_count > 0, f"row_count={row_count}")

    raw_order_items = int(conn.execute("select count(*) from stg_order_items").fetchone()[0])
    enriched_order_items = int(conn.execute("select count(*) from int_order_item_enriched").fetchone()[0])
    add_check(
        "int_order_item_enriched_no_silent_drops",
        raw_order_items == enriched_order_items,
        f"raw_order_items={raw_order_items}, enriched_order_items={enriched_order_items}",
    )

    anti_join_checks = {
        "anti_join_order_items_missing_orders": """
            select count(*)
            from stg_order_items oi
            left join stg_orders o on oi.order_id = o.order_id
            where o.order_id is null
        """,
        "anti_join_orders_missing_customers": """
            select count(*)
            from stg_orders o
            left join stg_customers c on o.customer_id = c.customer_id
            where c.customer_id is null
        """,
        "anti_join_order_items_missing_products": """
            select count(*)
            from stg_order_items oi
            left join stg_products p on oi.product_id = p.product_id
            where p.product_id is null
        """,
        "anti_join_orders_missing_sales_reps": """
            select count(*)
            from stg_orders o
            left join stg_sales_reps sr on o.sales_rep_id = sr.sales_rep_id
            where sr.sales_rep_id is null
        """,
    }
    for check_name, sql in anti_join_checks.items():
        missing_count = int(conn.execute(sql).fetchone()[0])
        add_check(check_name, missing_count == 0, f"missing_rows={missing_count}")

    for mart_name, key_cols in MART_PRIMARY_KEYS.items():
        key_expr = ", ".join(key_cols)
        row_count = int(conn.execute(f"select count(*) from {mart_name}").fetchone()[0])
        distinct_count = int(conn.execute(f"select count(*) from (select distinct {key_expr} from {mart_name})").fetchone()[0])
        add_check(
            f"{mart_name}_primary_key_uniqueness",
            row_count == distinct_count,
            f"rows={row_count}, distinct_keys={distinct_count}",
        )

    base_revenue = float(conn.execute("select sum(line_revenue) from int_order_item_pricing_metrics").fetchone()[0])
    segment_revenue = float(conn.execute("select sum(total_revenue) from mart_segment_pricing_summary").fetchone()[0])
    monthly_revenue = float(conn.execute("select sum(revenue) from mart_monthly_pricing_health").fetchone()[0])

    tol = max(1.0, base_revenue * 0.0001)
    add_check(
        "mart_revenue_reconciliation_segment",
        abs(base_revenue - segment_revenue) <= tol,
        f"base={base_revenue:.2f}, segment={segment_revenue:.2f}",
    )
    add_check(
        "mart_revenue_reconciliation_monthly",
        abs(base_revenue - monthly_revenue) <= tol,
        f"base={base_revenue:.2f}, monthly={monthly_revenue:.2f}",
    )

    share_violations = int(
        conn.execute(
            """
            select count(*)
            from mart_customer_pricing_profile
            where revenue_high_discount_share < 0
               or revenue_high_discount_share > 1
               or share_orders_discounted < 0
               or share_orders_discounted > 1
               or share_orders_high_discount < 0
               or share_orders_high_discount > 1
            """
        ).fetchone()[0]
    )
    add_check(
        "mart_customer_share_bounds",
        share_violations == 0,
        f"violations={share_violations}",
    )

    discount_violations = int(
        conn.execute(
            """
            select count(*)
            from int_order_item_pricing_metrics
            where discount_depth < 0
               or discount_depth > 1
               or realized_price > list_price_at_sale
            """
        ).fetchone()[0]
    )
    add_check(
        "int_pricing_consistency",
        discount_violations == 0,
        f"violations={discount_violations}",
    )

    as_of_matches_data = bool(
        conn.execute(
            """
            select
                max(m.as_of_date) = max(p.order_date)::date as as_of_matches_data
            from mart_overall_pricing_health m
            cross join int_order_item_pricing_metrics p
            """
        ).fetchone()[0]
    )
    add_check(
        "mart_overall_as_of_date_deterministic",
        as_of_matches_data,
        "as_of_date equals max(order_date) from data",
    )

    return pd.DataFrame(checks)


def run_sql_warehouse_models(config: SqlLayerRunConfig) -> dict[str, pd.DataFrame]:
    config.marts_output_dir.mkdir(parents=True, exist_ok=True)
    config.outputs_dir.mkdir(parents=True, exist_ok=True)
    config.db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(str(config.db_path))

    try:
        _load_raw_tables(conn, config.raw_dir)

        model_runs: list[dict] = []
        for layer_name, files in MODEL_ORDER.items():
            layer_dir = config.sql_dir / layer_name
            for file_name in files:
                model_path = layer_dir / file_name
                _run_model_file(conn, model_path)
                model_name = file_name.replace(".sql", "")
                relation_name = model_name
                row_count = int(conn.execute(f"select count(*) from {relation_name}").fetchone()[0])
                model_runs.append(
                    {
                        "layer": layer_name,
                        "model_name": model_name,
                        "relation_name": relation_name,
                        "row_count": row_count,
                        "sql_path": str(model_path),
                    }
                )

        marts: dict[str, pd.DataFrame] = {}
        for mart_sql in MODEL_ORDER["marts"]:
            mart_name = mart_sql.replace(".sql", "")
            mart_df = conn.execute(f"select * from {mart_name}").df()
            marts[mart_name] = mart_df
            mart_df.to_csv(config.marts_output_dir / f"{mart_name}.csv", index=False)

        validation_report = _run_sql_validations(conn)
        validation_report.to_csv(config.outputs_dir / "sql_validation_report.csv", index=False)

        model_run_df = pd.DataFrame(model_runs)
        model_run_df.to_csv(config.outputs_dir / "sql_model_run_log.csv", index=False)

        manifest = {
            "database_path": str(config.db_path),
            "sql_directory": str(config.sql_dir),
            "layers": {layer: files for layer, files in MODEL_ORDER.items()},
            "marts_exported": sorted(marts.keys()),
            "all_sql_checks_passed": bool((validation_report["status"] == "PASS").all()),
        }
        (config.outputs_dir / "sql_model_manifest.json").write_text(json.dumps(manifest, indent=2))

        return {
            "sql_model_run_log": model_run_df,
            "sql_validation_report": validation_report,
            **marts,
        }
    finally:
        conn.close()
