from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.features.pricing_features import build_feature_tables
from src.ingestion.synthetic_data import SyntheticDataConfig, generate_synthetic_business_data
from src.processing.build_base_tables import build_order_item_enriched
from src.scoring.risk_scoring import build_risk_outputs
from src.validation.final_review import run_final_validation_review


def _small_config() -> SyntheticDataConfig:
    return SyntheticDataConfig(
        seed=23,
        n_customers=100,
        n_products=10,
        n_sales_reps=8,
        n_orders=900,
        start_date="2024-01-01",
        end_date="2024-12-31",
    )


def test_final_validation_review_generates_outputs(tmp_path: Path) -> None:
    raw_tables = generate_synthetic_business_data(_small_config())
    enriched = build_order_item_enriched(raw_tables)
    feature_tables = build_feature_tables(enriched)
    risk_tables = build_risk_outputs(feature_tables)

    processed_tables = {
        "order_item_enriched": enriched,
        **feature_tables,
        **risk_tables,
    }

    dashboard_path = tmp_path / "dashboard.html"
    dashboard_path.write_text("<html><body>dashboard</body></html>", encoding="utf-8")
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {
                "contract_table": "order_item_pricing_metrics",
                "check_name": "required_columns_present",
                "status": "PASS",
                "severity": "High",
                "detail": "test",
            }
        ]
    ).to_csv(outputs_dir / "metric_contract_validation.csv", index=False)

    result_tables = run_final_validation_review(
        raw_tables=raw_tables,
        processed_tables=processed_tables,
        outputs_dir=outputs_dir,
        docs_dir=tmp_path / "docs",
        dashboard_path=dashboard_path,
    )

    assert "final_validation_checks" in result_tables
    assert not result_tables["final_validation_checks"].empty
    assert {"gate", "severity", "blocker"}.issubset(result_tables["final_validation_checks"].columns)
    assert "metric_contract_validation_passthrough" in set(result_tables["final_validation_checks"]["check_name"])
    assert "final_validation_readiness" in result_tables
    assert (tmp_path / "outputs" / "final_validation_review.md").exists()
    assert (tmp_path / "outputs" / "final_validation_summary.json").exists()
    assert (tmp_path / "outputs" / "final_validation_readiness.csv").exists()
    assert (tmp_path / "outputs" / "release" / "release_readiness.json").exists()
    assert (tmp_path / "outputs" / "release" / "release_readiness.md").exists()

    payload = json.loads((tmp_path / "outputs" / "final_validation_summary.json").read_text(encoding="utf-8"))
    assert "release_readiness_state" in payload
    assert "readiness_flags" in payload
    assert set(payload["readiness_flags"]) == {
        "technically_valid",
        "analytically_acceptable",
        "decision_support_only",
        "screening_grade_only",
        "not_committee_grade",
        "publish_blocked",
    }
