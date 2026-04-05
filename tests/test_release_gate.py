from __future__ import annotations

import json

import pandas as pd

from src.utils.paths import CONFIGS_DIR
from src.validation.release_gate import evaluate_release_gate


def _summary_payload() -> dict:
    return {
        "release_readiness_state": "not committee-grade",
        "failed_checks": 0,
        "failed_blocker_checks": 0,
        "dashboard_size_mb": 3.0,
        "readiness_flags": {
            "technically_valid": True,
            "analytically_acceptable": True,
            "decision_support_only": True,
            "screening_grade_only": False,
            "not_committee_grade": True,
            "publish_blocked": False,
        },
    }


def test_release_gate_passes_with_compliant_inputs(tmp_path) -> None:
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    summary_path = outputs_dir / "final_validation_summary.json"
    summary_path.write_text(json.dumps(_summary_payload()), encoding="utf-8")

    metric_contract_path = outputs_dir / "metric_contract_validation.csv"
    pd.DataFrame(
        [
            {"contract_table": "order_item_pricing_metrics", "check_name": "required_columns_present", "status": "PASS"}
        ]
    ).to_csv(metric_contract_path, index=False)

    report, passed = evaluate_release_gate(
        summary_path=summary_path,
        metric_contract_report_path=metric_contract_path,
        policy_path=CONFIGS_DIR / "release_policy.json",
        outputs_dir=outputs_dir,
    )

    assert passed
    assert report["gate_passed"] is True
    assert (outputs_dir / "release" / "release_gate_report.json").exists()
    assert (outputs_dir / "release" / "release_gate_report.md").exists()


def test_release_gate_fails_when_publish_blocked(tmp_path) -> None:
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    payload = _summary_payload()
    payload["readiness_flags"]["publish_blocked"] = True

    summary_path = outputs_dir / "final_validation_summary.json"
    summary_path.write_text(json.dumps(payload), encoding="utf-8")

    metric_contract_path = outputs_dir / "metric_contract_validation.csv"
    pd.DataFrame(
        [
            {"contract_table": "order_item_pricing_metrics", "check_name": "required_columns_present", "status": "PASS"}
        ]
    ).to_csv(metric_contract_path, index=False)

    report, passed = evaluate_release_gate(
        summary_path=summary_path,
        metric_contract_report_path=metric_contract_path,
        policy_path=CONFIGS_DIR / "release_policy.json",
        outputs_dir=outputs_dir,
    )

    assert not passed
    assert report["gate_passed"] is False
    assert any("publish_blocked" in reason for reason in report["blocking_reasons"])
