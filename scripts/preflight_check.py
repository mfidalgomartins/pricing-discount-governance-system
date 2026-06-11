from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MAX_TRACKED_FILE_MB = 10
MAX_TRACKED_FILE_BYTES = MAX_TRACKED_FILE_MB * 1024 * 1024

REQUIRED_PATHS = [
    "README.md",
    "LICENSE",
    "Makefile",
    "pyproject.toml",
    ".github/workflows/ci.yml",
    ".github/dependabot.yml",
    "requirements.lock",
    "scripts/run_pipeline.py",
    "scripts/build_report_assets.py",
    "scripts/build_report_pdf.py",
    "outputs/dashboard/pricing-discipline-command-center.html",
    "outputs/dashboard/vendor/chart.umd.min.js",
    "outputs/graphs/07_segment_pricing_health.png",
    "outputs/reports/pricing_discount_governance_report.pdf",
    "docs/.nojekyll",
    "docs/index.html",
    "docs/pricing-discipline-command-center.html",
    "docs/vendor/chart.umd.min.js",
    "docs/project_context_and_metrics.md",
    "docs/validation_framework.md",
    "docs/data_dictionary.md",
    "config/metric_contracts.json",
    "config/dashboard_policy.json",
    "config/policy_thresholds.json",
]

MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")

FORBIDDEN_TRACKED_PATTERNS = [
    ".DS_Store",
    "**/.DS_Store",
    "*.DS_Store",
    "**/.gitkeep",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "CHANGELOG.md",
    "TODO.md",
    "NOTES.md",
    "requirements.txt",
    "scripts/cleanup_repository.py",
    "scripts/generate_graphs.py",
    "outputs/dashboard/dashboard_data_snapshot.json",
]


def _tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], cwd=PROJECT_ROOT, text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _bytes_to_mb(value: int) -> float:
    return round(value / 1024 / 1024, 3)


def _broken_relative_markdown_links(tracked: list[str]) -> list[str]:
    issues: list[str] = []
    for rel in tracked:
        if not rel.endswith(".md"):
            continue
        path = PROJECT_ROOT / rel
        if not path.exists():
            continue
        for target in MARKDOWN_LINK_PATTERN.findall(path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                issues.append(f"Broken relative Markdown link: {rel} -> {target}")
    return issues


def main() -> int:
    issues: list[str] = []

    tracked = _tracked_files()

    for rel in REQUIRED_PATHS:
        if not (PROJECT_ROOT / rel).exists():
            issues.append(f"Missing required file: {rel}")
        elif rel not in tracked:
            issues.append(f"Required file is not tracked: {rel}")

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

    parity_pairs = [
        (
            "outputs/dashboard/pricing-discipline-command-center.html",
            "docs/pricing-discipline-command-center.html",
        ),
        ("outputs/dashboard/vendor/chart.umd.min.js", "docs/vendor/chart.umd.min.js"),
    ]
    for source_rel, published_rel in parity_pairs:
        source = PROJECT_ROOT / source_rel
        published = PROJECT_ROOT / published_rel
        if source.exists() and published.exists() and source.read_bytes() != published.read_bytes():
            issues.append(f"Published artifact is stale: {published_rel} differs from {source_rel}")

    issues.extend(_broken_relative_markdown_links(tracked))

    if issues:
        print("Preflight failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
