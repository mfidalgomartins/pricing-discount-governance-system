from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

READINESS_FLAG_NAMES = {
    "technically_valid",
    "analytically_acceptable",
    "decision_support_only",
    "publish_blocked",
}
RELEASE_POLICY_KEYS = {
    "required_readiness_flags",
    "required_release_readiness_state",
    "max_failed_checks",
    "max_failed_blocker_checks",
    "max_dashboard_size_mb",
    "require_dashboard_hash_match",
    "require_metric_contracts_pass",
    "max_metric_contract_failures",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required JSON file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    data: dict[str, Any] = payload
    return data


def _require_non_negative_int(policy: dict[str, Any], key: str) -> int:
    value = policy[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Release policy {key} must be a non-negative integer")
    return value


def load_release_policy(path: Path) -> dict[str, Any]:
    policy = _load_json(path)
    missing = RELEASE_POLICY_KEYS - policy.keys()
    unexpected = policy.keys() - RELEASE_POLICY_KEYS
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing={sorted(missing)}")
        if unexpected:
            details.append(f"unexpected={sorted(unexpected)}")
        raise ValueError("Invalid release policy keys: " + ", ".join(details))

    readiness_flags = policy["required_readiness_flags"]
    if not isinstance(readiness_flags, dict) or set(readiness_flags) != READINESS_FLAG_NAMES:
        raise ValueError(
            "Release policy required_readiness_flags must define exactly "
            + ", ".join(sorted(READINESS_FLAG_NAMES))
        )
    if any(not isinstance(value, bool) for value in readiness_flags.values()):
        raise ValueError("Release policy readiness flag values must be booleans")

    required_state = policy["required_release_readiness_state"]
    if not isinstance(required_state, str) or not required_state.strip():
        raise ValueError("Release policy required_release_readiness_state must be non-empty")

    _require_non_negative_int(policy, "max_failed_checks")
    _require_non_negative_int(policy, "max_failed_blocker_checks")
    _require_non_negative_int(policy, "max_metric_contract_failures")

    max_dashboard_size_mb = policy["max_dashboard_size_mb"]
    if (
        isinstance(max_dashboard_size_mb, bool)
        or not isinstance(max_dashboard_size_mb, (int, float))
        or not math.isfinite(float(max_dashboard_size_mb))
        or float(max_dashboard_size_mb) <= 0
    ):
        raise ValueError("Release policy max_dashboard_size_mb must be a positive number")

    for key in ("require_dashboard_hash_match", "require_metric_contracts_pass"):
        if not isinstance(policy[key], bool):
            raise ValueError(f"Release policy {key} must be a boolean")

    return policy


def _summary_non_negative_int(summary: dict[str, Any], key: str) -> int | None:
    value = summary.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _summary_non_negative_number(summary: dict[str, Any], key: str) -> float | None:
    value = summary.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        return None
    return float(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_path(path: Path, project_root: Path) -> str:
    """Return a repository-relative path when the artifact is inside the project."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


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
        lines.append(f"- {row['rule_name']}: {row['status']} ({row['detail']})")

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
) -> tuple[dict[str, Any], bool]:
    project_root = outputs_dir.resolve().parent
    summary = _load_json(summary_path)
    policy = load_release_policy(policy_path)

    rule_rows: list[dict[str, str]] = []
    blockers: list[str] = []

    readiness_flags = summary.get("readiness_flags", {})
    if not isinstance(readiness_flags, dict):
        readiness_flags = {}
    required_flags = policy["required_readiness_flags"]
    for flag_name, required_value in required_flags.items():
        observed = readiness_flags.get(flag_name)
        passed = isinstance(observed, bool) and observed is required_value
        rule_rows.append(
            {
                "rule_name": f"readiness_flag_{flag_name}",
                "status": "PASS" if passed else "FAIL",
                "detail": f"expected={required_value}, observed={observed}",
            }
        )
        if not passed:
            blockers.append(
                f"Readiness flag {flag_name} expected {required_value}, observed {observed}"
            )

    required_state = str(policy["required_release_readiness_state"])
    observed_state = summary.get("release_readiness_state")
    readiness_state_ok = observed_state == required_state
    rule_rows.append(
        {
            "rule_name": "release_readiness_state",
            "status": "PASS" if readiness_state_ok else "FAIL",
            "detail": f"expected={required_state}, observed={observed_state}",
        }
    )
    if not readiness_state_ok:
        blockers.append(
            f"Release readiness state expected {required_state}, observed {observed_state}"
        )

    max_failed_checks = _require_non_negative_int(policy, "max_failed_checks")
    failed_checks = _summary_non_negative_int(summary, "failed_checks")
    failed_checks_ok = failed_checks is not None and failed_checks <= max_failed_checks
    rule_rows.append(
        {
            "rule_name": "max_failed_checks",
            "status": "PASS" if failed_checks_ok else "FAIL",
            "detail": f"max={max_failed_checks}, observed={failed_checks}",
        }
    )
    if not failed_checks_ok:
        blockers.append(f"failed_checks={failed_checks} is invalid or exceeds {max_failed_checks}")

    max_blocker_checks = _require_non_negative_int(policy, "max_failed_blocker_checks")
    failed_blocker_checks = _summary_non_negative_int(summary, "failed_blocker_checks")
    blocker_ok = failed_blocker_checks is not None and failed_blocker_checks <= max_blocker_checks
    rule_rows.append(
        {
            "rule_name": "max_failed_blocker_checks",
            "status": "PASS" if blocker_ok else "FAIL",
            "detail": f"max={max_blocker_checks}, observed={failed_blocker_checks}",
        }
    )
    if not blocker_ok:
        blockers.append(
            f"failed_blocker_checks={failed_blocker_checks} is invalid or exceeds {max_blocker_checks}"
        )

    dashboard_path = outputs_dir / "dashboard" / "pricing-discipline-command-center.html"
    dashboard_size_mb = (
        dashboard_path.stat().st_size / (1024 * 1024) if dashboard_path.exists() else None
    )
    summary_dashboard_size_mb = _summary_non_negative_number(summary, "dashboard_size_mb")
    max_dashboard_size_mb = float(policy["max_dashboard_size_mb"])
    dashboard_ok = dashboard_size_mb is not None and dashboard_size_mb <= max_dashboard_size_mb
    rule_rows.append(
        {
            "rule_name": "max_dashboard_size_mb",
            "status": "PASS" if dashboard_ok else "FAIL",
            "detail": f"max={max_dashboard_size_mb:.3f}, actual={dashboard_size_mb}",
        }
    )
    if not dashboard_ok:
        blockers.append(
            f"Dashboard is missing or exceeds max_dashboard_size_mb={max_dashboard_size_mb:.3f}"
        )

    dashboard_size_summary_ok = (
        dashboard_size_mb is not None
        and summary_dashboard_size_mb is not None
        and abs(dashboard_size_mb - summary_dashboard_size_mb) <= 0.001
    )
    rule_rows.append(
        {
            "rule_name": "dashboard_size_summary_match",
            "status": "PASS" if dashboard_size_summary_ok else "FAIL",
            "detail": (
                f"summary={summary_dashboard_size_mb}, actual={dashboard_size_mb}, tolerance=0.001"
            ),
        }
    )
    if not dashboard_size_summary_ok:
        blockers.append("Dashboard size does not match the artifact inspected by final review")

    require_dashboard_hash_match = bool(policy["require_dashboard_hash_match"])
    expected_dashboard_sha256 = summary.get("dashboard_sha256")
    actual_dashboard_sha256 = _sha256(dashboard_path) if dashboard_path.exists() else None
    dashboard_hash_ok = (
        isinstance(expected_dashboard_sha256, str)
        and actual_dashboard_sha256 == expected_dashboard_sha256
    )
    rule_rows.append(
        {
            "rule_name": "dashboard_sha256_match",
            "status": "PASS" if dashboard_hash_ok or not require_dashboard_hash_match else "FAIL",
            "detail": (
                f"required={require_dashboard_hash_match}, "
                f"expected={expected_dashboard_sha256}, actual={actual_dashboard_sha256}"
            ),
        }
    )
    if require_dashboard_hash_match and not dashboard_hash_ok:
        blockers.append("Dashboard SHA-256 does not match the artifact validated by final review")

    require_metric_contracts_pass = bool(policy["require_metric_contracts_pass"])
    max_metric_contract_failures = _require_non_negative_int(policy, "max_metric_contract_failures")

    if metric_contract_report_path.exists():
        try:
            metric_report = pd.read_csv(metric_contract_report_path)
        except pd.errors.EmptyDataError:
            metric_report = pd.DataFrame()
        if metric_report.empty or "status" not in metric_report.columns:
            metric_failures = None
            metric_invalid_statuses = None
            metric_pass = False
            detail = "report must be non-empty and contain a status column"
        else:
            statuses = metric_report["status"].astype("string")
            metric_failures = int(statuses.eq("FAIL").sum())
            metric_invalid_statuses = int((~statuses.isin(["PASS", "FAIL"])).sum())
            metric_pass = (
                metric_invalid_statuses == 0 and metric_failures <= max_metric_contract_failures
            )
            detail = (
                f"max_failures={max_metric_contract_failures}, failures={metric_failures}, "
                f"invalid_statuses={metric_invalid_statuses}, rows={len(metric_report)}"
            )

        effective_metric_pass = metric_pass or not require_metric_contracts_pass
        if metric_invalid_statuses not in (None, 0):
            effective_metric_pass = False
        rule_rows.append(
            {
                "rule_name": "metric_contract_report_valid",
                "status": "PASS" if effective_metric_pass else "FAIL",
                "detail": f"required={require_metric_contracts_pass}; {detail}",
            }
        )
        if not effective_metric_pass:
            blockers.append("Metric contract report is malformed or exceeds the failure policy")
    else:
        metric_failures = None
        metric_invalid_statuses = None
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
        "evaluated_at_utc": datetime.now(UTC).isoformat(),
        "gate_passed": gate_passed,
        "release_readiness_state": observed_state,
        "failed_checks": failed_checks,
        "failed_blocker_checks": failed_blocker_checks,
        "dashboard_size_mb": dashboard_size_mb,
        "summary_dashboard_size_mb": summary_dashboard_size_mb,
        "dashboard_sha256": actual_dashboard_sha256,
        "metric_contract_failures": metric_failures,
        "metric_contract_invalid_statuses": metric_invalid_statuses,
        "policy_path": _portable_path(policy_path, project_root),
        "summary_path": _portable_path(summary_path, project_root),
        "metric_contract_report_path": _portable_path(metric_contract_report_path, project_root),
        "rule_evaluation": rule_rows,
        "blocking_reasons": blockers,
    }

    release_dir = outputs_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)

    (release_dir / "release_gate_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (release_dir / "release_gate_report.md").write_text(_render_markdown(report), encoding="utf-8")

    return report, gate_passed
