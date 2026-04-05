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
    dashboard_dir = PROJECT_ROOT / "dashboard"
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

    # Move generated docs into docs/reports for cleaner top-level docs.
    docs_dir = PROJECT_ROOT / "docs"
    reports_dir = docs_dir / "reports"
    report_files = [
        "data_profiling_report.md",
        "executive_summary.md",
        "formal_analysis_report.md",
        "final_validation_review.md",
        "visualization_pack.md",
    ]
    for name in report_files:
        src = docs_dir / name
        dst = reports_dir / name
        if src.exists() and src.is_file():
            _move_if_exists(src, dst)
            moved_files += 1

    print(f"Cleanup done. removed_files={removed_files}, removed_dirs={removed_dirs}, moved_files={moved_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
