from __future__ import annotations

from src.analysis.dashboard_builder import build_executive_dashboard
from src.features.pricing_features import build_feature_tables
from src.ingestion.synthetic_data import SyntheticDataConfig, generate_synthetic_business_data
from src.processing.build_base_tables import build_order_item_enriched
from src.scoring.risk_scoring import build_risk_outputs


def _small_config() -> SyntheticDataConfig:
    return SyntheticDataConfig(
        seed=19,
        n_customers=120,
        n_products=12,
        n_sales_reps=10,
        n_orders=1200,
        start_date="2024-01-01",
        end_date="2024-12-31",
    )


def test_dashboard_builder_outputs_self_contained_html(tmp_path) -> None:
    raw_tables = generate_synthetic_business_data(_small_config())
    enriched = build_order_item_enriched(raw_tables)
    feature_tables = build_feature_tables(enriched)
    risk_tables = build_risk_outputs(feature_tables)

    dashboard_path = build_executive_dashboard(
        processed_tables={
            "order_item_pricing_metrics": feature_tables["order_item_pricing_metrics"],
            "customer_risk_scores": risk_tables["customer_risk_scores"],
        },
        dashboard_dir=tmp_path,
    )

    assert dashboard_path.exists()
    html = dashboard_path.read_text(encoding="utf-8")

    assert "vendor/chart.umd.min.js" in html
    assert "cdn.jsdelivr.net/npm/chart.js" in html
    assert "kpiRows" in html
    assert "pricingAggRows" in html
    assert "customerPricingRows" in html
    assert "filtered_revenue" in html
    assert "customerScopeRows" not in html
    assert 'id="segmentFilter"' in html
    assert 'id="regionFilter"' in html
    assert 'id="categoryFilter"' in html
    assert 'id="channelFilter"' in html
    assert 'id="themeToggle"' in html
    assert "Generated " not in html
    assert "Version:" not in html
    assert "Dashboard v" not in html
    assert "Data as of" not in html
    assert "__DATA_JSON__" not in html
    assert not (tmp_path / "dashboard_data_snapshot.json").exists()
    assert len(html.encode("utf-8")) < 5_000_000
