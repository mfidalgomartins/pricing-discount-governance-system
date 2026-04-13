from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


def _check_row(
    name: str,
    passed: bool,
    detail: str,
    *,
    gate: str,
    severity: str,
    blocker: bool = False,
) -> dict:
    return {
        "check_name": name,
        "status": "PASS" if passed else "FAIL",
        "detail": detail,
        "gate": gate,
        "severity": severity,
        "blocker": blocker,
    }


def _render_review(
    assessment: str,
    release_state: str,
    readiness_flags: dict[str, bool],
    issues: list[tuple[str, str]],
    check_table: pd.DataFrame,
    required_caveats: list[str],
    suggestions: list[str],
) -> str:
    lines = [
        "# Final Validation Review (/validate-data)",
        "",
        "## Overall Assessment",
        f"- Legacy assessment: {assessment}",
        f"- Release readiness state: {release_state}",
        "",
        "## Readiness Classification",
    ]
    for key in [
        "technically_valid",
        "analytically_acceptable",
        "decision_support_only",
        "screening_grade_only",
        "not_committee_grade",
        "publish_blocked",
    ]:
        lines.append(f"- {key}: {readiness_flags[key]}")

    lines.extend(
        [
            "",
            "## Issues Found (Severity)",
        ]
    )

    if not issues:
        lines.append("- No material issues detected in this run.")
    else:
        for severity, message in issues:
            lines.append(f"- [{severity}] {message}")

    lines.extend(
        [
            "",
            "## Calculation Spot-Checks",
        ]
    )
    for row in check_table.itertuples(index=False):
        lines.append(
            (
                f"- {row.check_name}: {row.status} "
                f"(gate={row.gate}, severity={row.severity}, blocker={row.blocker}) {row.detail}"
            )
        )

    lines.extend(
        [
            "",
            "## Required Caveats",
        ]
    )
    for caveat in required_caveats:
        lines.append(f"- {caveat}")

    lines.extend(
        [
            "",
            "## Suggested Improvements",
        ]
    )
    for suggestion in suggestions:
        lines.append(f"- {suggestion}")

    return "\n".join(lines)


def _coverage_window(pricing: pd.DataFrame) -> tuple[str, str]:
    start = pd.to_datetime(pricing["order_date"]).min().strftime("%Y-%m-%d")
    end = pd.to_datetime(pricing["order_date"]).max().strftime("%Y-%m-%d")
    return start, end


def _issue_sort_key(item: tuple[str, str]) -> tuple[int, str]:
    severity, message = item
    order = {"High": 0, "Medium": 1, "Low": 2}
    return (order.get(severity, 3), message)


def _release_readiness(
    check_table: pd.DataFrame,
    committee_constraints: list[str],
) -> tuple[str, dict[str, bool]]:
    fail_mask = check_table["status"] == "FAIL"
    blocker_failures = int((fail_mask & check_table["blocker"]).sum())
    analytical_failures = int(
        (fail_mask & check_table["gate"].isin(["analytical", "consistency", "governance"])).sum()
    )
    technical_failures = int((fail_mask & (check_table["gate"] == "technical")).sum())

    technically_valid = blocker_failures == 0 and technical_failures == 0
    analytically_acceptable = technically_valid and analytical_failures == 0
    publish_blocked = blocker_failures > 0
    screening_grade_only = (not publish_blocked) and technically_valid and not analytically_acceptable
    decision_support_only = analytically_acceptable and not publish_blocked
    not_committee_grade = decision_support_only and len(committee_constraints) > 0

    if publish_blocked:
        release_state = "publish-blocked"
    elif screening_grade_only:
        release_state = "screening-grade only"
    elif not_committee_grade:
        release_state = "not committee-grade"
    elif analytically_acceptable:
        release_state = "analytically acceptable"
    elif technically_valid:
        release_state = "technically valid"
    else:
        release_state = "publish-blocked"

    readiness_flags = {
        "technically_valid": technically_valid,
        "analytically_acceptable": analytically_acceptable,
        "decision_support_only": decision_support_only,
        "screening_grade_only": screening_grade_only,
        "not_committee_grade": not_committee_grade,
        "publish_blocked": publish_blocked,
    }
    return release_state, readiness_flags


def _legacy_assessment(check_table: pd.DataFrame, issues: list[tuple[str, str]]) -> str:
    failed_checks = int((check_table["status"] == "FAIL").sum())
    has_material_issue = any(severity in {"High", "Medium"} for severity, _ in issues)
    if failed_checks == 0:
        return "share with caveats" if has_material_issue else "ready"
    if failed_checks <= 2:
        return "share with caveats"
    return "needs revision"


def _extract_dashboard_payload(dashboard_path: Path) -> dict | None:
    if not dashboard_path.exists():
        return None
    try:
        text = dashboard_path.read_text(encoding="utf-8")
    except OSError:
        return None

    match = re.search(r"const DATA = (\{.*?\});\nconst ALL", text, flags=re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def run_final_validation_review(
    raw_tables: Dict[str, pd.DataFrame],
    processed_tables: Dict[str, pd.DataFrame],
    outputs_dir: Path,
    docs_dir: Path,
    dashboard_path: Path,
) -> dict[str, pd.DataFrame | dict]:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    customers = raw_tables["customers"]
    orders = raw_tables["orders"]
    order_items = raw_tables["order_items"]
    products = raw_tables["products"]
    sales_reps = raw_tables["sales_reps"]

    enriched = processed_tables["order_item_enriched"]
    pricing = processed_tables["order_item_pricing_metrics"]
    customer_profile = processed_tables["customer_pricing_profile"]
    customer_risk_scores = processed_tables["customer_risk_scores"]
    segment_summary = processed_tables["segment_pricing_summary"]

    checks: list[dict] = []

    checks.append(
        _check_row(
            "join_explosion_order_items_to_enriched",
            len(order_items) == len(enriched),
            f"order_items={len(order_items)}, enriched={len(enriched)}",
            gate="technical",
            severity="High",
            blocker=True,
        )
    )
    checks.append(
        _check_row(
            "join_explosion_enriched_to_pricing",
            len(enriched) == len(pricing),
            f"enriched={len(enriched)}, pricing={len(pricing)}",
            gate="technical",
            severity="High",
            blocker=True,
        )
    )
    checks.append(
        _check_row(
            "fk_orders_customer",
            bool(orders["customer_id"].isin(customers["customer_id"]).all()),
            f"missing={(~orders['customer_id'].isin(customers['customer_id'])).sum()}",
            gate="technical",
            severity="High",
            blocker=True,
        )
    )
    checks.append(
        _check_row(
            "fk_orders_sales_rep",
            bool(orders["sales_rep_id"].isin(sales_reps["sales_rep_id"]).all()),
            f"missing={(~orders['sales_rep_id'].isin(sales_reps['sales_rep_id'])).sum()}",
            gate="technical",
            severity="High",
            blocker=True,
        )
    )
    checks.append(
        _check_row(
            "fk_order_items_order",
            bool(order_items["order_id"].isin(orders["order_id"]).all()),
            f"missing={(~order_items['order_id'].isin(orders['order_id'])).sum()}",
            gate="technical",
            severity="High",
            blocker=True,
        )
    )
    checks.append(
        _check_row(
            "fk_order_items_product",
            bool(order_items["product_id"].isin(products["product_id"]).all()),
            f"missing={(~order_items['product_id'].isin(products['product_id'])).sum()}",
            gate="technical",
            severity="High",
            blocker=True,
        )
    )

    recomputed_discount = 1 - (pricing["realized_price"] / pricing["list_price_at_sale"])
    max_abs_diff = float(np.abs(recomputed_discount - pricing["discount_depth"]).max())
    checks.append(
        _check_row(
            "discount_logic_consistency",
            max_abs_diff <= 0.001,
            f"max_abs_diff={max_abs_diff:.6f}",
            gate="consistency",
            severity="High",
            blocker=True,
        )
    )
    realized_violations = int((pricing["realized_price"] > pricing["list_price_at_sale"]).sum())
    checks.append(
        _check_row(
            "realized_lte_list",
            realized_violations == 0,
            f"violations={realized_violations}",
            gate="consistency",
            severity="High",
            blocker=True,
        )
    )

    pricing_revenue = float(pricing["line_revenue"].sum())
    segment_revenue = float(segment_summary["total_revenue"].sum())
    revenue_tol = max(1.0, pricing_revenue * 0.0001)
    checks.append(
        _check_row(
            "revenue_total_segment_match",
            abs(pricing_revenue - segment_revenue) <= revenue_tol,
            f"pricing={pricing_revenue:.2f}, segment={segment_revenue:.2f}",
            gate="consistency",
            severity="High",
            blocker=True,
        )
    )

    monthly = pricing.groupby("order_month", as_index=False).agg(
        revenue=("line_revenue", "sum"),
        gross_margin_value=("gross_margin_value", "sum"),
    )
    margin_line = float(np.average(pricing["margin_proxy_pct"], weights=pricing["line_revenue"]))
    margin_monthly = float(np.average(monthly["gross_margin_value"] / monthly["revenue"], weights=monthly["revenue"]))
    checks.append(
        _check_row(
            "margin_proxy_consistency_line_vs_monthly",
            abs(margin_line - margin_monthly) <= 0.001,
            f"line={margin_line:.6f}, monthly={margin_monthly:.6f}",
            gate="consistency",
            severity="High",
            blocker=True,
        )
    )

    month_series = pd.period_range(pricing["order_date"].min(), pricing["order_date"].max(), freq="M")
    observed_months = pd.PeriodIndex(pd.to_datetime(pricing["order_date"]), freq="M").unique()
    checks.append(
        _check_row(
            "period_completeness_monthly",
            len(month_series) == len(observed_months),
            f"expected={len(month_series)}, observed={len(observed_months)}",
            gate="analytical",
            severity="Medium",
            blocker=False,
        )
    )

    share_cols = [
        "share_orders_discounted",
        "share_orders_high_discount",
        "revenue_high_discount_share",
    ]
    share_bounds_ok = True
    for col in share_cols:
        share_bounds_ok = share_bounds_ok and bool(customer_profile[col].between(0, 1).all())
    checks.append(
        _check_row(
            "share_denominator_bounds",
            share_bounds_ok,
            f"all_share_columns_in_[0,1]={share_bounds_ok}",
            gate="analytical",
            severity="High",
            blocker=False,
        )
    )

    weighted_discount = float(
        np.average(pricing["discount_depth"], weights=pricing["line_list_revenue"])
    )
    weighted_discount_total = float(1 - pricing["line_revenue"].sum() / pricing["line_list_revenue"].sum())
    checks.append(
        _check_row(
            "weighted_discount_consistency",
            abs(weighted_discount - weighted_discount_total) <= 0.001,
            f"weighted_direct={weighted_discount:.6f}, weighted_total={weighted_discount_total:.6f}",
            gate="analytical",
            severity="High",
            blocker=False,
        )
    )

    score_variance = float(customer_risk_scores["governance_priority_score"].var(ddof=0))
    checks.append(
        _check_row(
            "risk_score_nontrivial_variance",
            score_variance > 1.0,
            f"governance_score_variance={score_variance:.6f}",
            gate="governance",
            severity="Medium",
            blocker=False,
        )
    )

    tier_order = ["Low", "Medium", "High", "Critical"]
    observed_tier_medians = (
        customer_risk_scores.groupby("risk_tier", as_index=False)["governance_priority_score"].median()
    )
    observed_tier_medians["tier_rank"] = observed_tier_medians["risk_tier"].map(
        {tier: idx for idx, tier in enumerate(tier_order)}
    )
    observed_tier_medians = observed_tier_medians.dropna(subset=["tier_rank"]).sort_values("tier_rank")
    risk_tier_monotonic = bool(
        observed_tier_medians["governance_priority_score"].is_monotonic_increasing
        if len(observed_tier_medians) > 1
        else True
    )
    checks.append(
        _check_row(
            "risk_tier_monotonicity_by_median_score",
            risk_tier_monotonic,
            "median_scores="
            + ", ".join(
                f"{row.risk_tier}:{row.governance_priority_score:.2f}"
                for row in observed_tier_medians.itertuples(index=False)
            ),
            gate="governance",
            severity="High",
            blocker=False,
        )
    )

    recomputed_driver = customer_risk_scores[
        ["pricing_risk_score", "discount_dependency_score", "margin_erosion_score"]
    ].idxmax(axis=1)
    driver_alignment_ok = bool((recomputed_driver == customer_risk_scores["main_risk_driver"]).all())
    checks.append(
        _check_row(
            "main_risk_driver_alignment",
            driver_alignment_ok,
            f"mismatches={(recomputed_driver != customer_risk_scores['main_risk_driver']).sum()}",
            gate="governance",
            severity="High",
            blocker=False,
        )
    )

    allowed_actions_by_tier = {
        "Low": {"monitor only"},
        "Medium": {"review segment pricing"},
        "High": {
            "investigate rep behavior",
            "redesign discount policy",
            "tighten approval thresholds",
            "review segment pricing",
        },
        "Critical": {
            "investigate rep behavior",
            "redesign discount policy",
            "tighten approval thresholds",
            "review segment pricing",
        },
    }

    action_alignment_mask = customer_risk_scores.apply(
        lambda r: r["recommended_action"] in allowed_actions_by_tier.get(r["risk_tier"], set()),
        axis=1,
    )
    checks.append(
        _check_row(
            "recommended_action_policy_alignment",
            bool(action_alignment_mask.all()),
            f"invalid_rows={(~action_alignment_mask).sum()}",
            gate="governance",
            severity="Medium",
            blocker=False,
        )
    )

    low_data = customer_risk_scores[customer_risk_scores["low_data_flag"] == 1]
    high_data = customer_risk_scores[customer_risk_scores["low_data_flag"] == 0]
    if not low_data.empty and not high_data.empty:
        low_mean_distance = float((low_data["governance_priority_score"] - 50).abs().mean())
        high_mean_distance = float((high_data["governance_priority_score"] - 50).abs().mean())
        shrinkage_ok = low_mean_distance <= high_mean_distance + 2.0
        detail = (
            f"low_data_mean_distance={low_mean_distance:.3f}, "
            f"high_data_mean_distance={high_mean_distance:.3f}"
        )
    else:
        shrinkage_ok = True
        detail = "skipped (insufficient low/high data split)"

    checks.append(
        _check_row(
            "score_stability_low_data_shrinkage",
            shrinkage_ok,
            detail,
            gate="governance",
            severity="Medium",
            blocker=False,
        )
    )

    coverage_start, coverage_end = _coverage_window(pricing)
    manifest_path = outputs_dir / "run_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        manifest_start = manifest.get("configuration", {}).get("start_date")
        manifest_end = manifest.get("configuration", {}).get("end_date")
        if manifest_start == coverage_start and manifest_end == coverage_end:
            manifest_raw_orders = int(manifest["row_counts"]["raw"]["orders"])
            manifest_pricing_rows = int(manifest["row_counts"]["processed"]["order_item_pricing_metrics"])
            checks.append(
                _check_row(
                    "run_manifest_rowcount_consistency",
                    manifest_raw_orders == len(orders) and manifest_pricing_rows == len(pricing),
                    (
                        f"manifest_orders={manifest_raw_orders}, actual_orders={len(orders)}, "
                        f"manifest_pricing={manifest_pricing_rows}, actual_pricing={len(pricing)}"
                    ),
                    gate="consistency",
                    severity="Medium",
                    blocker=False,
                )
            )
        else:
            checks.append(
                _check_row(
                    "run_manifest_rowcount_consistency",
                    True,
                    (
                        "manifest check skipped due differing run window "
                        f"(manifest={manifest_start}..{manifest_end}, current={coverage_start}..{coverage_end})"
                    ),
                    gate="consistency",
                    severity="Low",
                    blocker=False,
                )
            )

    overall_health_path = outputs_dir / "overall_pricing_health.csv"
    if overall_health_path.exists():
        overall_health = pd.read_csv(overall_health_path)
        if not overall_health.empty:
            output_weighted_discount = float(overall_health.iloc[0]["weighted_realized_discount"])
            output_high_discount_share = float(overall_health.iloc[0]["high_discount_revenue_share"])
            output_total_revenue = float(overall_health.iloc[0]["total_revenue"])
            computed_high_discount_share = (
                float(pricing.loc[pricing["discount_depth"] >= 0.20, "line_revenue"].sum() / pricing_revenue)
                if pricing_revenue > 0
                else 0.0
            )
            max_output_diff = max(
                abs(output_weighted_discount - weighted_discount_total),
                abs(output_high_discount_share - computed_high_discount_share),
                abs(output_total_revenue - pricing_revenue) / max(1.0, pricing_revenue),
            )
            checks.append(
                _check_row(
                    "cross_output_overall_health_consistency",
                    max_output_diff <= 0.001,
                    f"max_diff={max_output_diff:.6f}",
                    gate="consistency",
                    severity="High",
                    blocker=False,
                )
            )

    formal_validation_path = outputs_dir / "formal_analysis_validation_checks.csv"
    if formal_validation_path.exists():
        formal_checks = pd.read_csv(formal_validation_path)
        formal_ok = bool((formal_checks["status"] == "PASS").all())
        checks.append(
            _check_row(
                "formal_analysis_validation_passthrough",
                formal_ok,
                f"passed={(formal_checks['status'] == 'PASS').sum()} of {len(formal_checks)}",
                gate="analytical",
                severity="High",
                blocker=False,
            )
        )

    metric_contract_path = outputs_dir / "metric_contract_validation.csv"
    if metric_contract_path.exists():
        metric_contract_checks = pd.read_csv(metric_contract_path)
        metric_contract_ok = bool((metric_contract_checks["status"] == "PASS").all())
        checks.append(
            _check_row(
                "metric_contract_validation_passthrough",
                metric_contract_ok,
                f"passed={(metric_contract_checks['status'] == 'PASS').sum()} of {len(metric_contract_checks)}",
                gate="governance",
                severity="High",
                blocker=False,
            )
        )
    else:
        checks.append(
            _check_row(
                "metric_contract_validation_passthrough",
                False,
                "missing outputs/metric_contract_validation.csv",
                gate="governance",
                severity="High",
                blocker=False,
            )
        )

    if dashboard_path.exists():
        dashboard_text = dashboard_path.read_text(encoding="utf-8")
        checks.append(
            _check_row(
                "dashboard_data_as_of_consistency",
                coverage_end in dashboard_text,
                f"coverage_end={coverage_end} present_in_dashboard={coverage_end in dashboard_text}",
                gate="consistency",
                severity="Medium",
                blocker=False,
            )
        )

    dashboard_payload = _extract_dashboard_payload(dashboard_path)
    if dashboard_payload is not None:
        kpi_rows = dashboard_payload.get("kpiRows", [])
        all_row = next(
            (
                row
                for row in kpi_rows
                if row.get("segment") == "All"
                and row.get("region") == "All"
                and row.get("category") == "All"
                and row.get("sales_channel") == "All"
            ),
            None,
        )
        if all_row is not None:
            dashboard_revenue = float(all_row.get("net_revenue", 0.0))
            dashboard_discount = float(all_row.get("weighted_discount_pct", 0.0))
            revenue_diff = abs(dashboard_revenue - pricing_revenue) / max(1.0, pricing_revenue)
            discount_diff = abs(dashboard_discount - weighted_discount_total)
            checks.append(
                _check_row(
                    "dashboard_kpi_all_scope_consistency",
                    revenue_diff <= 0.001 and discount_diff <= 0.001,
                    f"revenue_diff={revenue_diff:.6f}, discount_diff={discount_diff:.6f}",
                    gate="consistency",
                    severity="High",
                    blocker=False,
                )
            )
        else:
            checks.append(
                _check_row(
                    "dashboard_kpi_all_scope_consistency",
                    False,
                    "kpiRows missing all-scope [All, All, All, All] row",
                    gate="consistency",
                    severity="High",
                    blocker=False,
                )
            )

        payload_data_as_of = str(dashboard_payload.get("meta", {}).get("data_as_of", ""))
        payload_coverage_end = str(dashboard_payload.get("meta", {}).get("coverage_end", ""))
        checks.append(
            _check_row(
                "dashboard_payload_data_as_of_consistency",
                payload_coverage_end == coverage_end,
                (
                    f"payload_coverage_end={payload_coverage_end}, "
                    f"payload_data_as_of={payload_data_as_of}, coverage_end={coverage_end}"
                ),
                gate="consistency",
                severity="Medium",
                blocker=False,
            )
        )
    else:
        checks.append(
            _check_row(
                "dashboard_kpi_all_scope_consistency",
                True,
                "skipped (dashboard payload not embedded or unreadable)",
                gate="consistency",
                severity="Low",
                blocker=False,
            )
        )

    check_table = pd.DataFrame(checks).sort_values(["gate", "check_name"]).reset_index(drop=True)
    failed_checks = int((check_table["status"] == "FAIL").sum())

    issues: list[tuple[str, str]] = []
    for row in check_table[check_table["status"] == "FAIL"].itertuples(index=False):
        issues.append((row.severity, f"{row.check_name} failed ({row.detail})"))

    excluded_customers = int(customers["customer_id"].nunique() - customer_profile["customer_id"].nunique())
    excluded_share = excluded_customers / customers["customer_id"].nunique() if len(customers) else np.nan
    if excluded_customers > 0:
        severity = "Medium" if excluded_share > 0.05 else "Low"
        issues.append(
            (
                severity,
                (
                    "Customer population exclusion at analysis layer: "
                    f"{excluded_customers} customers ({excluded_share:.2%}) have no orders "
                    "and are excluded from customer-level scoring."
                ),
            )
        )

    dashboard_size_mb = dashboard_path.stat().st_size / (1024 * 1024) if dashboard_path.exists() else np.nan
    if not np.isnan(dashboard_size_mb) and dashboard_size_mb > 5.0:
        issues.append(
            (
                "Low",
                (
                    "Dashboard payload remains sizable for a single-file deliverable: "
                    f"HTML size is {dashboard_size_mb:.2f} MB with embedded data."
                ),
            )
        )

    committee_constraints = [
        "Data is synthetic and behaviorally simulated, not observed commercial history.",
        "Margin remains a proxy based on modeled unit cost (not accounting gross margin).",
    ]

    release_state, readiness_flags = _release_readiness(check_table, committee_constraints)
    legacy_assessment = _legacy_assessment(check_table, issues)

    required_caveats = [
        "Synthetic data design remains a simulation, not observed commercial history.",
        "Customer-level results exclude non-transacting customers in the period.",
        "Margin is a proxy based on modeled unit cost, not accounting gross margin.",
        "Pricing inconsistency outlier detection is threshold-based and sensitive to peer-group variance.",
    ]

    suggestions = [
        "Add sensitivity runs with alternative risk-tier thresholds and component weights.",
        "Add API-backed dashboard mode for larger datasets and lighter payloads.",
        "Add committee-grade gates only after replacing synthetic data and margin proxy with ledger-aligned metrics.",
    ]

    issues = sorted(issues, key=_issue_sort_key)
    report_md = _render_review(
        legacy_assessment,
        release_state,
        readiness_flags,
        issues,
        check_table,
        required_caveats,
        suggestions,
    )
    (outputs_dir / "final_validation_review.md").write_text(report_md)

    readiness_df = pd.DataFrame(
        [{"readiness_state": state, "is_true": value} for state, value in readiness_flags.items()]
    )
    readiness_df.to_csv(outputs_dir / "final_validation_readiness.csv", index=False)

    summary_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall_assessment": legacy_assessment,
        "release_readiness_state": release_state,
        "readiness_flags": readiness_flags,
        "failed_checks": failed_checks,
        "failed_blocker_checks": int(((check_table["status"] == "FAIL") & check_table["blocker"]).sum()),
        "failed_technical_checks": int(((check_table["status"] == "FAIL") & (check_table["gate"] == "technical")).sum()),
        "failed_analytical_checks": int(
            (
                (check_table["status"] == "FAIL")
                & check_table["gate"].isin(["analytical", "consistency", "governance"])
            ).sum()
        ),
        "excluded_customers": excluded_customers,
        "excluded_customer_pct": float(excluded_share) if not np.isnan(excluded_share) else None,
        "high_discount_revenue_share": float(
            pricing.loc[pricing["discount_depth"] >= 0.20, "line_revenue"].sum() / pricing["line_revenue"].sum()
        )
        if float(pricing["line_revenue"].sum()) > 0
        else None,
        "dashboard_size_mb": float(round(dashboard_size_mb, 3)) if not np.isnan(dashboard_size_mb) else None,
        "all_checks_passed": failed_checks == 0,
        "share_orders_high_discount_variance": float(customer_profile["share_orders_high_discount"].var(ddof=0)),
    }
    (outputs_dir / "final_validation_summary.json").write_text(json.dumps(summary_payload, indent=2))

    release_dir = outputs_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    release_readiness_md = "\n".join(
        [
            "# Release Readiness Snapshot",
            "",
            f"- Overall assessment: {legacy_assessment}",
            f"- Release readiness state: {release_state}",
            f"- technically_valid: {readiness_flags['technically_valid']}",
            f"- analytically_acceptable: {readiness_flags['analytically_acceptable']}",
            f"- decision_support_only: {readiness_flags['decision_support_only']}",
            f"- screening_grade_only: {readiness_flags['screening_grade_only']}",
            f"- not_committee_grade: {readiness_flags['not_committee_grade']}",
            f"- publish_blocked: {readiness_flags['publish_blocked']}",
            f"- failed_checks: {failed_checks}",
            f"- failed_blocker_checks: {summary_payload['failed_blocker_checks']}",
        ]
    )
    (release_dir / "release_readiness.md").write_text(release_readiness_md, encoding="utf-8")
    (release_dir / "release_readiness.json").write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    issue_rows = pd.DataFrame(
        [{"severity": severity, "message": message} for severity, message in issues]
    )
    issue_rows.to_csv(outputs_dir / "final_validation_issues.csv", index=False)

    return {
        "final_validation_checks": check_table,
        "final_validation_issues": issue_rows,
        "final_validation_summary": pd.DataFrame([summary_payload]),
        "final_validation_readiness": readiness_df,
    }
