from __future__ import annotations

from src.analysis.formal_analysis import run_formal_pricing_analysis
from src.features.pricing_features import build_feature_tables
from src.ingestion.synthetic_data import SyntheticDataConfig, generate_synthetic_business_data
from src.processing.build_base_tables import build_order_item_enriched
from src.scoring.risk_scoring import build_risk_outputs


def test_formal_analysis_handles_non_2023_2025_window(tmp_path) -> None:
    config = SyntheticDataConfig(
        seed=17,
        n_customers=120,
        n_products=28,
        n_sales_reps=12,
        n_orders=1000,
        start_date="2024-01-01",
        end_date="2024-12-31",
    )
    raw = generate_synthetic_business_data(config)
    enriched = build_order_item_enriched(raw)
    feature_tables = build_feature_tables(enriched)
    risk_tables = build_risk_outputs(feature_tables)

    processed = {
        "order_item_enriched": enriched,
        **feature_tables,
        **risk_tables,
    }

    run_formal_pricing_analysis(
        processed_tables=processed,
        outputs_dir=tmp_path / "outputs",
        docs_dir=tmp_path / "docs",
    )

    report = (tmp_path / "outputs" / "formal_analysis_report.md").read_text(encoding="utf-8")
    assert "Revenue growth (2025 vs 2023): N/A for current date window." in report
    assert "Time period: full available coverage (2024-01-01 to 2024-12-31)." in report
    assert "Pricing discipline verdict:" in report
    assert (tmp_path / "outputs" / "threshold_sensitivity_analysis.csv").exists()
    assert (tmp_path / "outputs" / "governance_action_queue.csv").exists()
