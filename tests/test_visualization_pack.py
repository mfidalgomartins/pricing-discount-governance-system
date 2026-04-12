from __future__ import annotations

from src.analysis.visualization_pack import create_visualization_pack
from src.features.pricing_features import build_feature_tables
from src.ingestion.synthetic_data import SyntheticDataConfig, generate_synthetic_business_data
from src.processing.build_base_tables import build_order_item_enriched
from src.scoring.risk_scoring import build_risk_outputs


def test_visualization_pack_runs_headless(tmp_path) -> None:
    config = SyntheticDataConfig(
        seed=31,
        n_customers=100,
        n_products=12,
        n_sales_reps=8,
        n_orders=700,
        start_date="2024-01-01",
        end_date="2024-12-31",
    )
    raw = generate_synthetic_business_data(config)
    enriched = build_order_item_enriched(raw)
    features = build_feature_tables(enriched)
    risks = build_risk_outputs(features)
    processed = {
        "order_item_pricing_metrics": features["order_item_pricing_metrics"],
        "customer_risk_scores": risks["customer_risk_scores"],
        "segment_pricing_summary": features["segment_pricing_summary"],
    }

    create_visualization_pack(
        processed_tables=processed,
        outputs_dir=tmp_path / "outputs",
        docs_dir=tmp_path / "docs",
    )

    assert (tmp_path / "outputs" / "visualizations" / "discount_distribution.png").exists()
    assert (tmp_path / "outputs" / "visualization_pack.md").exists()
