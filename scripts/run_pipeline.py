from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.business_analysis import generate_analysis_outputs
from src.analysis.data_profiling import run_data_profiling
from src.analysis.dashboard_builder import build_executive_dashboard
from src.analysis.formal_analysis import run_formal_pricing_analysis
from src.analysis.visualization_pack import create_visualization_pack
from src.features.pricing_features import build_feature_tables
from src.ingestion.load_raw import save_raw_tables
from src.ingestion.synthetic_data import SyntheticDataConfig, generate_synthetic_business_data
from src.processing.build_base_tables import build_order_item_enriched
from src.scoring.risk_scoring import build_risk_outputs
from src.utils.paths import (
    CONFIGS_DIR,
    DASHBOARD_DIR,
    DATA_PROCESSED_DIR,
    DATA_RAW_DIR,
    DOCS_DIR,
    DOCS_REPORTS_DIR,
    OUTPUTS_DIR,
    PROJECT_ROOT,
    ensure_project_directories,
)
from src.validation.final_review import run_final_validation_review
from src.validation.metric_contracts import validate_metric_contracts
from src.validation.data_quality import validate_processed_tables, validate_raw_tables
from scripts.cleanup_repository import main as cleanup_repository_main


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Pricing & Discount Governance pipeline end-to-end.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for synthetic data generation")
    parser.add_argument("--customers", type=int, default=1200)
    parser.add_argument("--products", type=int, default=28)
    parser.add_argument("--sales-reps", type=int, default=45)
    parser.add_argument("--orders", type=int, default=18000)
    parser.add_argument("--start-date", type=str, default="2023-01-01")
    parser.add_argument("--end-date", type=str, default="2025-12-31")
    return parser.parse_args()


def save_processed_tables(processed_tables: dict[str, pd.DataFrame]) -> None:
    DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name, table in processed_tables.items():
        table.to_csv(DATA_PROCESSED_DIR / f"{name}.csv", index=False)


def main() -> None:
    args = parse_args()
    ensure_project_directories()

    config = SyntheticDataConfig(
        seed=args.seed,
        n_customers=args.customers,
        n_products=args.products,
        n_sales_reps=args.sales_reps,
        n_orders=args.orders,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    raw_tables = generate_synthetic_business_data(config)
    save_raw_tables(raw_tables, DATA_RAW_DIR)

    raw_validation_report, raw_valid = validate_raw_tables(raw_tables)
    raw_validation_report.to_csv(OUTPUTS_DIR / "raw_validation_report.csv", index=False)
    if not raw_valid:
        raise RuntimeError("Raw validation failed. Check outputs/raw_validation_report.csv")

    order_item_enriched = build_order_item_enriched(raw_tables)
    feature_tables = build_feature_tables(order_item_enriched)
    risk_tables = build_risk_outputs(feature_tables)

    processed_tables: dict[str, pd.DataFrame] = {
        "order_item_enriched": order_item_enriched,
        **feature_tables,
        **risk_tables,
    }
    save_processed_tables(processed_tables)

    processed_validation_report, processed_valid = validate_processed_tables(processed_tables)
    processed_validation_report.to_csv(OUTPUTS_DIR / "processed_validation_report.csv", index=False)
    if not processed_valid:
        raise RuntimeError("Processed validation failed. Check outputs/processed_validation_report.csv")

    analysis_tables = generate_analysis_outputs(
        feature_tables=feature_tables,
        risk_tables=risk_tables,
        outputs_dir=OUTPUTS_DIR,
    )

    profiling_tables = run_data_profiling(
        raw_tables=raw_tables,
        processed_tables=processed_tables,
        outputs_dir=OUTPUTS_DIR,
        docs_dir=DOCS_REPORTS_DIR,
    )

    formal_analysis_tables = run_formal_pricing_analysis(
        processed_tables=processed_tables,
        outputs_dir=OUTPUTS_DIR,
        docs_dir=DOCS_REPORTS_DIR,
    )

    metric_contract_report, metric_contract_valid = validate_metric_contracts(
        processed_tables=processed_tables,
        outputs_dir=OUTPUTS_DIR,
        config_path=CONFIGS_DIR / "metric_contracts.json",
    )
    metric_contract_report.to_csv(OUTPUTS_DIR / "metric_contract_validation.csv", index=False)
    if not metric_contract_valid:
        raise RuntimeError("Metric contracts failed. Check outputs/metric_contract_validation.csv")

    visualization_tables = create_visualization_pack(
        processed_tables=processed_tables,
        outputs_dir=OUTPUTS_DIR,
        docs_dir=DOCS_REPORTS_DIR,
    )

    dashboard_path = build_executive_dashboard(
        processed_tables=processed_tables,
        dashboard_dir=DASHBOARD_DIR,
        publish_dir=DOCS_DIR,
    )

    run_manifest = {
        "project": "Pricing Discipline & Discount Governance System",
        "configuration": {
            "seed": args.seed,
            "n_customers": args.customers,
            "n_products": args.products,
            "n_sales_reps": args.sales_reps,
            "n_orders": args.orders,
            "start_date": args.start_date,
            "end_date": args.end_date,
        },
        "row_counts": {
            "raw": {k: int(len(v)) for k, v in raw_tables.items()},
            "processed": {k: int(len(v)) for k, v in processed_tables.items()},
            "analysis": {k: int(len(v)) for k, v in analysis_tables.items()},
            "profiling": {k: int(len(v)) for k, v in profiling_tables.items()},
            "formal_analysis": {k: int(len(v)) for k, v in formal_analysis_tables.items()},
            "visualization": {k: int(len(v)) for k, v in visualization_tables.items()},
        },
        "validation": {
            "raw_passed": raw_valid,
            "processed_passed": processed_valid,
            "metric_contracts_passed": metric_contract_valid,
            "raw_report": str(OUTPUTS_DIR / "raw_validation_report.csv"),
            "processed_report": str(OUTPUTS_DIR / "processed_validation_report.csv"),
            "metric_contract_report": str(OUTPUTS_DIR / "metric_contract_validation.csv"),
        },
        "dashboard": str(dashboard_path),
    }

    (OUTPUTS_DIR / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2))

    final_validation_tables = run_final_validation_review(
        raw_tables=raw_tables,
        processed_tables=processed_tables,
        outputs_dir=OUTPUTS_DIR,
        docs_dir=DOCS_REPORTS_DIR,
        dashboard_path=dashboard_path,
    )
    run_manifest["row_counts"]["final_validation"] = {k: int(len(v)) for k, v in final_validation_tables.items()}

    (OUTPUTS_DIR / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2))
    cleanup_repository_main()

    print("Pipeline completed successfully.")
    print(f"Raw tables: {', '.join(raw_tables.keys())}")
    print(f"Processed tables: {', '.join(processed_tables.keys())}")
    print(f"Metric contracts passed: {metric_contract_valid}")
    print("Release gate: not applicable in portfolio mode.")


if __name__ == "__main__":
    main()
