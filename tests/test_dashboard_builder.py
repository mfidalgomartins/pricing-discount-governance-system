from __future__ import annotations

import pandas as pd

from src.analysis.dashboard_builder import _select_dashboard_risk_rows, build_executive_dashboard
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


def test_dashboard_builder_outputs_publishable_html(tmp_path) -> None:
    raw_tables = generate_synthetic_business_data(_small_config())
    enriched = build_order_item_enriched(raw_tables)
    feature_tables = build_feature_tables(enriched)
    risk_tables = build_risk_outputs(feature_tables)
    malicious_label = "</script><script>globalThis.injected=true</script>"
    feature_tables["order_item_pricing_metrics"].loc[0, "segment"] = malicious_label

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
    assert "cdn.jsdelivr.net/npm/chart.js" not in html
    assert 'meta name="description"' in html
    assert 'rel="canonical"' in html
    assert 'property="og:title"' in html
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
    assert 'class="sort-button" data-key="governance_priority_score"' in html
    assert 'aria-sort="descending"' in html
    assert 'id="tableSortMeta" aria-live="polite"' in html
    # Every chart ships a table-view twin, so no value is reachable only by hover.
    assert 'id="bridgeChartData"' in html
    assert 'id="trendChartData"' in html
    assert 'id="segmentChartData"' in html
    assert 'id="regionRiskChartData"' in html
    assert 'id="actionChartData"' in html
    # Visual system anchors: the mark palette is validated against the surfaces it
    # renders on, so the tokens must survive edits to the template.
    assert "--accent:    #2a5db0;" in html  # light mark, 6.4:1 on #ffffff
    assert "--ok:        #1a7f37;" in html
    assert "--warn:      #b06000;" in html
    assert "--critical:  #c0362c;" in html
    assert "--graphite:  #7d848c;" in html  # bridge totals, 3.8:1 on #ffffff
    assert '[data-theme="dark"]' in html
    assert "--accent:    #3f74d6;" in html  # dark mark, stepped for #15171a
    assert "Geist" in html  # single UI sans
    assert "Geist Mono" in html  # tabular figures
    assert "Fraunces" not in html  # no display serif on the hero figure
    assert ".masthead {" in html
    assert ".verdict {" in html
    assert ".filters-panel" in html
    assert "position: sticky;" in html  # table thead is sticky inside its scroll container
    # No page-sticky chrome (avoid floating headers over a dense readout)
    assert ".masthead {\n      position: sticky;" not in html
    assert ".filters-panel {\n      position: sticky;" not in html
    assert "Generated " not in html
    assert "Version:" not in html
    assert "Dashboard v" not in html
    assert "Data as of" not in html
    assert "__DATA_JSON__" not in html
    assert malicious_label not in html
    assert "\\u003c/script\\u003e" in html
    assert not (tmp_path / "dashboard_data_snapshot.json").exists()
    assert len(html.encode("utf-8")) < 5_000_000


def test_dashboard_risk_export_never_truncates_high_priority_accounts() -> None:
    risk = pd.DataFrame(
        {
            "customer_id": [f"C{i:03d}" for i in range(170)],
            "governance_priority_score": list(range(170, 0, -1)),
            "risk_tier": ["Critical"] * 80 + ["High"] * 70 + ["Medium"] * 20,
        }
    )

    selected = _select_dashboard_risk_rows(risk)

    assert len(selected) == 150
    assert set(selected["customer_id"]) == set(risk.loc[:149, "customer_id"])
