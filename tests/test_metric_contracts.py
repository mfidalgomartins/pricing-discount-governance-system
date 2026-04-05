from __future__ import annotations

from src.analysis.formal_analysis import run_formal_pricing_analysis
from src.features.pricing_features import build_feature_tables
from src.ingestion.synthetic_data import SyntheticDataConfig, generate_synthetic_business_data
from src.processing.build_base_tables import build_order_item_enriched
from src.scoring.risk_scoring import build_risk_outputs
from src.utils.paths import CONFIGS_DIR
from src.validation.metric_contracts import validate_metric_contracts


def _small_config() -> SyntheticDataConfig:
    return SyntheticDataConfig(
        seed=31,
        n_customers=120,
        n_products=12,
        n_sales_reps=10,
        n_orders=1200,
        start_date="2024-01-01",
        end_date="2024-12-31",
    )


def test_metric_contracts_pass_for_pipeline_outputs(tmp_path) -> None:
    raw_tables = generate_synthetic_business_data(_small_config())
    enriched = build_order_item_enriched(raw_tables)
    feature_tables = build_feature_tables(enriched)
    risk_tables = build_risk_outputs(feature_tables)

    processed_tables = {
        "order_item_enriched": enriched,
        **feature_tables,
        **risk_tables,
    }

    outputs_dir = tmp_path / "outputs"
    docs_dir = tmp_path / "docs"
    run_formal_pricing_analysis(
        processed_tables=processed_tables,
        outputs_dir=outputs_dir,
        docs_dir=docs_dir,
    )

    report, is_valid = validate_metric_contracts(
        processed_tables=processed_tables,
        outputs_dir=outputs_dir,
        config_path=CONFIGS_DIR / "metric_contracts.json",
    )

    assert not report.empty
    assert is_valid, f"Metric contracts failed:\n{report[report['status'] == 'FAIL']}"
    assert "overall_pricing_health" in set(report["contract_table"])
