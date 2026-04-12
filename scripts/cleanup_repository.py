from __future__ import annotations

import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _safe_unlink(path: Path) -> None:
    if path.exists() and path.is_file():
        path.unlink()


def _safe_rmtree(path: Path) -> None:
    if path.exists() and path.is_dir():
        shutil.rmtree(path)


def _move_if_exists(src: Path, dst: Path) -> None:
    if not src.exists() or not src.is_file():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def _move_many(output_dir: Path, subdir: str, file_names: list[str]) -> int:
    moved = 0
    target_dir = output_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in file_names:
        src = output_dir / name
        dst = target_dir / name
        if src.exists() and src.is_file():
            _move_if_exists(src, dst)
            moved += 1
    return moved


def main() -> int:
    removed_files = 0
    removed_dirs = 0
    moved_files = 0

    # Remove OS and python cache clutter.
    for p in PROJECT_ROOT.rglob(".DS_Store"):
        _safe_unlink(p)
        removed_files += 1

    for pattern in ["__pycache__", ".pytest_cache"]:
        for p in PROJECT_ROOT.rglob(pattern):
            _safe_rmtree(p)
            removed_dirs += 1

    # Dashboard legacy CSV exports are no longer used.
    dashboard_dir = PROJECT_ROOT / "outputs" / "dashboard"
    for csv_name in [
        "monthly_pricing_performance.csv",
        "segment_channel_diagnostics.csv",
        "customer_risk_scores.csv",
        "risk_tier_summary.csv",
    ]:
        path = dashboard_dir / csv_name
        if path.exists():
            _safe_unlink(path)
            removed_files += 1

    # No report relocation; reports are not versioned in this portfolio.

    # Organize non-critical runtime output artifacts under domain folders.
    outputs_dir = PROJECT_ROOT / "outputs"
    moved_files += _move_many(
        outputs_dir,
        "analysis",
        [
            "overall_pricing_health.csv",
            "yearly_pricing_health.csv",
            "formal_analysis_summary.json",
            "key_findings.json",
            "risk_by_segment.csv",
            "segment_discount_dependency.csv",
            "customer_discount_dependency.csv",
            "product_discount_dependency.csv",
            "discount_dependency_concentration.csv",
            "margin_erosion_risk.csv",
            "rep_pricing_inconsistency.csv",
            "channel_region_pricing_inconsistency.csv",
            "product_price_variance.csv",
            "channel_pricing_summary.csv",
            "rep_pricing_diagnostics.csv",
            "product_pricing_summary.csv",
            "product_governance_patterns.csv",
            "governance_action_queue.csv",
            "top_risk_customers.csv",
            "recommended_analytical_focus.csv",
            "threshold_sensitivity_analysis.csv",
            "monthly_pricing_performance.csv",
        ],
    )
    moved_files += _move_many(
        outputs_dir,
        "profiling",
        [
            "table_profile_summary.csv",
            "column_profile.csv",
            "table_numeric_summary.csv",
            "table_top_values.csv",
            "data_quality_issues.csv",
            "population_coverage.csv",
            "profiling_summary.md",
        ],
    )
    # Reports are kept canonical under docs/reports to avoid duplicated narrative surfaces.

    # Remove OS clutter inside outputs.
    for p in (PROJECT_ROOT / "outputs").rglob(".DS_Store"):
        _safe_unlink(p)
        removed_files += 1

    print(f"Cleanup done. removed_files={removed_files}, removed_dirs={removed_dirs}, moved_files={moved_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
