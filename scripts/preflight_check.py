from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MAX_TRACKED_FILE_MB = 10
MAX_TRACKED_FILE_BYTES = MAX_TRACKED_FILE_MB * 1024 * 1024

REQUIRED_PATHS = [
    "README.md",
    "LICENSE",
    ".github/workflows/ci.yml",
    "scripts/run_pipeline.py",
    "scripts/cleanup_repository.py",
    "scripts/release_gate.py",
    "scripts/run_sql_models.py",
    "dashboard/pricing_discount_governance_dashboard.html",
    "docs/business_problem_and_metric_framework.md",
    "docs/validation_framework.md",
    "configs/metric_contracts.json",
    "configs/release_policy.json",
]

FORBIDDEN_TRACKED_PATTERNS = [
    ".DS_Store",
    "**/.DS_Store",
    "*.DS_Store",
    "dashboard/dashboard_data_snapshot.json",
]


def _tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], cwd=PROJECT_ROOT, text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _bytes_to_mb(value: int) -> float:
    return round(value / 1024 / 1024, 3)


def main() -> int:
    issues: list[str] = []

    tracked = _tracked_files()

    for rel in REQUIRED_PATHS:
        if not (PROJECT_ROOT / rel).exists():
            issues.append(f"Missing required file: {rel}")

    for pattern in FORBIDDEN_TRACKED_PATTERNS:
        matches = [path for path in tracked if fnmatch.fnmatch(path, pattern)]
        for match in matches:
            if (PROJECT_ROOT / match).exists():
                issues.append(f"Forbidden tracked file: {match}")

    for rel in tracked:
        path = PROJECT_ROOT / rel
        if path.exists() and path.is_file():
            size = path.stat().st_size
            if size > MAX_TRACKED_FILE_BYTES:
                issues.append(
                    f"Tracked file too large: {rel} ({_bytes_to_mb(size)} MB > {MAX_TRACKED_FILE_MB} MB)"
                )

    if issues:
        print("Preflight failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
