from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from src.utils.paths import CONFIGS_DIR
from src.validation.release_gate import evaluate_release_gate


def _summary_payload() -> dict:
    return {
        "release_readiness_state": "decision-support only",
        "failed_checks": 0,
        "failed_blocker_checks": 0,
        "dashboard_size_mb": 0.0,
        "dashboard_sha256": hashlib.sha256(b"dashboard").hexdigest(),
        "readiness_flags": {
            "technically_valid": True,
            "analytically_acceptable": True,
            "decision_support_only": True,
            "publish_blocked": False,
        },
    }


def test_release_gate_passes_with_compliant_inputs(tmp_path) -> None:
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    dashboard_dir = outputs_dir / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "pricing-discipline-command-center.html").write_bytes(b"dashboard")

    summary_path = outputs_dir / "final_validation_summary.json"
    summary_path.write_text(json.dumps(_summary_payload()), encoding="utf-8")

    metric_contract_path = outputs_dir / "metric_contract_validation.csv"
    pd.DataFrame(
        [
            {
                "contract_table": "order_item_pricing_metrics",
                "check_name": "required_columns_present",
                "status": "PASS",
            }
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
    assert report["summary_path"] == "outputs/final_validation_summary.json"
    assert report["metric_contract_report_path"] == "outputs/metric_contract_validation.csv"
    assert (outputs_dir / "release" / "release_gate_report.json").exists()
    assert (outputs_dir / "release" / "release_gate_report.md").exists()


def test_release_gate_fails_when_publish_blocked(tmp_path) -> None:
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    dashboard_dir = outputs_dir / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "pricing-discipline-command-center.html").write_bytes(b"dashboard")

    payload = _summary_payload()
    payload["readiness_flags"]["publish_blocked"] = True

    summary_path = outputs_dir / "final_validation_summary.json"
    summary_path.write_text(json.dumps(payload), encoding="utf-8")

    metric_contract_path = outputs_dir / "metric_contract_validation.csv"
    pd.DataFrame(
        [
            {
                "contract_table": "order_item_pricing_metrics",
                "check_name": "required_columns_present",
                "status": "PASS",
            }
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


def test_release_gate_rejects_dashboard_changed_after_final_review(tmp_path) -> None:
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    dashboard_dir = outputs_dir / "dashboard"
    dashboard_dir.mkdir()
    dashboard_path = dashboard_dir / "pricing-discipline-command-center.html"
    dashboard_path.write_bytes(b"changed-dashboard")

    summary_path = outputs_dir / "final_validation_summary.json"
    summary_path.write_text(json.dumps(_summary_payload()), encoding="utf-8")
    metric_contract_path = outputs_dir / "metric_contract_validation.csv"
    pd.DataFrame([{"status": "PASS"}]).to_csv(metric_contract_path, index=False)

    report, passed = evaluate_release_gate(
        summary_path=summary_path,
        metric_contract_report_path=metric_contract_path,
        policy_path=CONFIGS_DIR / "release_policy.json",
        outputs_dir=outputs_dir,
    )

    assert not passed
    assert any("SHA-256" in reason for reason in report["blocking_reasons"])


def test_release_gate_rejects_unknown_metric_contract_status(tmp_path) -> None:
    outputs_dir = tmp_path / "outputs"
    dashboard_dir = outputs_dir / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "pricing-discipline-command-center.html").write_bytes(b"dashboard")

    summary_path = outputs_dir / "final_validation_summary.json"
    summary_path.write_text(json.dumps(_summary_payload()), encoding="utf-8")
    metric_contract_path = outputs_dir / "metric_contract_validation.csv"
    pd.DataFrame([{"status": "SKIPPED"}]).to_csv(metric_contract_path, index=False)

    report, passed = evaluate_release_gate(
        summary_path=summary_path,
        metric_contract_report_path=metric_contract_path,
        policy_path=CONFIGS_DIR / "release_policy.json",
        outputs_dir=outputs_dir,
    )

    assert not passed
    assert report["metric_contract_invalid_statuses"] == 1


def test_release_gate_rejects_empty_metric_contract_report(tmp_path) -> None:
    outputs_dir = tmp_path / "outputs"
    dashboard_dir = outputs_dir / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "pricing-discipline-command-center.html").write_bytes(b"dashboard")

    summary_path = outputs_dir / "final_validation_summary.json"
    summary_path.write_text(json.dumps(_summary_payload()), encoding="utf-8")
    metric_contract_path = outputs_dir / "metric_contract_validation.csv"
    metric_contract_path.write_text("", encoding="utf-8")

    report, passed = evaluate_release_gate(
        summary_path=summary_path,
        metric_contract_report_path=metric_contract_path,
        policy_path=CONFIGS_DIR / "release_policy.json",
        outputs_dir=outputs_dir,
    )

    assert not passed
    assert report["metric_contract_failures"] is None
    assert any("malformed" in reason for reason in report["blocking_reasons"])


def test_release_gate_rejects_incomplete_policy(tmp_path) -> None:
    policy = json.loads((CONFIGS_DIR / "release_policy.json").read_text(encoding="utf-8"))
    del policy["max_dashboard_size_mb"]
    policy_path = tmp_path / "release_policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(_summary_payload()), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid release policy keys"):
        evaluate_release_gate(
            summary_path=summary_path,
            metric_contract_report_path=tmp_path / "contracts.csv",
            policy_path=policy_path,
            outputs_dir=tmp_path / "outputs",
        )
