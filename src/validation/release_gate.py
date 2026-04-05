from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Tuple

import pandas as pd


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Release Gate Report",
        "",
        f"- Gate passed: {report['gate_passed']}",
        f"- Evaluated at: {report['evaluated_at_utc']}",
        f"- Release readiness state: {report['release_readiness_state']}",
        f"- Failed checks reported: {report['failed_checks']}",
        f"- Failed blocker checks: {report['failed_blocker_checks']}",
        "",
        "## Rule Evaluation",
    ]

    for row in report["rule_evaluation"]:
        lines.append(
            f"- {row['rule_name']}: {row['status']} ({row['detail']})"
        )

    lines.extend(["", "## Blocking Reasons"])
    if report["blocking_reasons"]:
        for reason in report["blocking_reasons"]:
            lines.append(f"- {reason}")
    else:
        lines.append("- none")

    return "\n".join(lines)


def evaluate_release_gate(
    summary_path: Path,
    metric_contract_report_path: Path,
    policy_path: Path,
    outputs_dir: Path,
) -> Tuple[dict[str, Any], bool]:
    summary = _load_json(summary_path)
    policy = _load_json(policy_path)

    rule_rows: list[dict[str, str]] = []
    blockers: list[str] = []

    readiness_flags = summary.get("readiness_flags", {})
    required_flags = policy.get("required_readiness_flags", {})
    for flag_name, required_value in required_flags.items():
        observed = readiness_flags.get(flag_name)
        passed = observed == required_value
        rule_rows.append(
            {
                "rule_name": f"readiness_flag_{flag_name}",
                "status": "PASS" if passed else "FAIL",
                "detail": f"expected={required_value}, observed={observed}",
            }
        )
        if not passed:
            blockers.append(f"Readiness flag {flag_name} expected {required_value}, observed {observed}")

    max_failed_checks = int(policy.get("max_failed_checks", 0))
    failed_checks = int(summary.get("failed_checks", 999999))
    failed_checks_ok = failed_checks <= max_failed_checks
    rule_rows.append(
        {
            "rule_name": "max_failed_checks",
            "status": "PASS" if failed_checks_ok else "FAIL",
            "detail": f"max={max_failed_checks}, observed={failed_checks}",
        }
    )
    if not failed_checks_ok:
        blockers.append(f"failed_checks={failed_checks} exceeds max_failed_checks={max_failed_checks}")

    max_blocker_checks = int(policy.get("max_failed_blocker_checks", 0))
    failed_blocker_checks = int(summary.get("failed_blocker_checks", 999999))
    blocker_ok = failed_blocker_checks <= max_blocker_checks
    rule_rows.append(
        {
            "rule_name": "max_failed_blocker_checks",
            "status": "PASS" if blocker_ok else "FAIL",
            "detail": f"max={max_blocker_checks}, observed={failed_blocker_checks}",
        }
    )
    if not blocker_ok:
        blockers.append(
            f"failed_blocker_checks={failed_blocker_checks} exceeds max_failed_blocker_checks={max_blocker_checks}"
        )

    max_dashboard_size_mb = float(policy.get("max_dashboard_size_mb", 9999.0))
    dashboard_size_mb = float(summary.get("dashboard_size_mb", 9999.0))
    dashboard_ok = dashboard_size_mb <= max_dashboard_size_mb
    rule_rows.append(
        {
            "rule_name": "max_dashboard_size_mb",
            "status": "PASS" if dashboard_ok else "FAIL",
            "detail": f"max={max_dashboard_size_mb:.3f}, observed={dashboard_size_mb:.3f}",
        }
    )
    if not dashboard_ok:
        blockers.append(
            f"dashboard_size_mb={dashboard_size_mb:.3f} exceeds max_dashboard_size_mb={max_dashboard_size_mb:.3f}"
        )

    require_metric_contracts_pass = bool(policy.get("require_metric_contracts_pass", True))
    max_metric_contract_failures = int(policy.get("max_metric_contract_failures", 0))

    if metric_contract_report_path.exists():
        metric_report = pd.read_csv(metric_contract_report_path)
        metric_failures = int((metric_report["status"] == "FAIL").sum())
        metric_pass = metric_failures <= max_metric_contract_failures
        rule_rows.append(
            {
                "rule_name": "metric_contract_failures",
                "status": "PASS" if metric_pass else "FAIL",
                "detail": f"max={max_metric_contract_failures}, observed={metric_failures}",
            }
        )
        if require_metric_contracts_pass and not metric_pass:
            blockers.append(
                f"metric_contract_failures={metric_failures} exceeds max_metric_contract_failures={max_metric_contract_failures}"
            )
    else:
        metric_failures = None
        rule_rows.append(
            {
                "rule_name": "metric_contract_report_exists",
                "status": "FAIL" if require_metric_contracts_pass else "PASS",
                "detail": f"required={require_metric_contracts_pass}, exists=False",
            }
        )
        if require_metric_contracts_pass:
            blockers.append("metric_contract_validation.csv not found")

    gate_passed = len(blockers) == 0

    report = {
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "gate_passed": gate_passed,
        "release_readiness_state": summary.get("release_readiness_state"),
        "failed_checks": failed_checks,
        "failed_blocker_checks": failed_blocker_checks,
        "dashboard_size_mb": dashboard_size_mb,
        "metric_contract_failures": metric_failures,
        "policy_path": str(policy_path),
        "summary_path": str(summary_path),
        "metric_contract_report_path": str(metric_contract_report_path),
        "rule_evaluation": rule_rows,
        "blocking_reasons": blockers,
    }

    release_dir = outputs_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)

    (release_dir / "release_gate_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (release_dir / "release_gate_report.md").write_text(_render_markdown(report), encoding="utf-8")

    return report, gate_passed
