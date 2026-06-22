from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import tomllib
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
PINNED_REQUIREMENT_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([A-Za-z0-9!+_.-]+)\s*$"
)
ALLOWED_EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:")

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


def _normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _project_path(rel: str | Path) -> Path:
    candidate = (PROJECT_ROOT / rel).resolve()
    try:
        candidate.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(f"Path escapes project root: {rel}") from exc
    return candidate


def _tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], cwd=PROJECT_ROOT, text=True, stderr=subprocess.STDOUT)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _bytes_to_mb(value: int) -> float:
    return round(value / 1024 / 1024, 3)


def _broken_relative_markdown_links(tracked: list[str]) -> list[str]:
    issues: list[str] = []
    for rel in tracked:
        if not rel.endswith(".md"):
            continue
        try:
            path = _project_path(rel)
        except ValueError as exc:
            issues.append(str(exc))
            continue
        if not path.exists():
            continue
        for target in MARKDOWN_LINK_PATTERN.findall(path.read_text(encoding="utf-8")):
            if target.startswith(ALLOWED_EXTERNAL_LINK_PREFIXES):
                continue
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
                issues.append(f"Unsupported Markdown link scheme: {rel} -> {target}")
                continue
            if Path(target).is_absolute():
                issues.append(f"Unsafe absolute Markdown link: {rel} -> {target}")
                continue
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(PROJECT_ROOT)
            except ValueError:
                issues.append(f"Markdown link escapes project root: {rel} -> {target}")
                continue
            if not resolved.exists():
                issues.append(f"Broken relative Markdown link: {rel} -> {target}")
    return issues


def _parse_pinned_requirement(raw_requirement: str) -> tuple[str, str] | None:
    requirement = raw_requirement.split(";", 1)[0].strip()
    match = PINNED_REQUIREMENT_PATTERN.fullmatch(requirement)
    if not match:
        return None
    return _normalize_package_name(match.group(1)), match.group(2)


def _dependency_spec_issues() -> list[str]:
    issues: list[str] = []
    pyproject_path = _project_path("pyproject.toml")
    lock_path = _project_path("requirements.lock")

    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = pyproject.get("project", {})
    declared_requirements = list(project.get("dependencies", []))
    for optional_requirements in project.get("optional-dependencies", {}).values():
        declared_requirements.extend(optional_requirements)

    declared: dict[str, str] = {}
    for requirement in declared_requirements:
        parsed = _parse_pinned_requirement(requirement)
        if parsed is None:
            issues.append(f"Dependency is not exactly pinned in pyproject.toml: {requirement}")
            continue
        package_name, version = parsed
        declared[package_name] = version

    locked: dict[str, str] = {}
    for line_number, raw_line in enumerate(lock_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parsed = _parse_pinned_requirement(line)
        if parsed is None:
            issues.append(f"Unsupported requirement format in requirements.lock:{line_number}: {raw_line}")
            continue
        package_name, version = parsed
        locked[package_name] = version

    for package_name, version in declared.items():
        locked_version = locked.get(package_name)
        if locked_version is None:
            issues.append(f"Dependency missing from requirements.lock: {package_name}=={version}")
        elif locked_version != version:
            issues.append(
                f"Dependency version drift: {package_name} pyproject={version} lock={locked_version}"
            )

    return issues


def _config_json_issues() -> list[str]:
    issues: list[str] = []
    config_dir = _project_path("config")
    for path in sorted(config_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(f"Invalid JSON config: {path.relative_to(PROJECT_ROOT)} ({exc})")
            continue
        if not isinstance(payload, dict):
            issues.append(f"JSON config must contain an object at top level: {path.relative_to(PROJECT_ROOT)}")
    return issues


def main() -> int:
    issues: list[str] = []

    try:
        tracked = _tracked_files()
    except subprocess.CalledProcessError as exc:
        print(f"Preflight failed: git ls-files failed with exit code {exc.returncode}")
        if exc.output:
            print(exc.output.strip())
        return 1

    for rel in REQUIRED_PATHS:
        try:
            path = _project_path(rel)
        except ValueError as exc:
            issues.append(str(exc))
            continue
        if not path.exists():
            issues.append(f"Missing required file: {rel}")
        elif rel not in tracked:
            issues.append(f"Required file is not tracked: {rel}")

    for pattern in FORBIDDEN_TRACKED_PATTERNS:
        matches = [path for path in tracked if fnmatch.fnmatch(path, pattern)]
        for match in matches:
            try:
                path = _project_path(match)
            except ValueError as exc:
                issues.append(str(exc))
                continue
            if path.exists():
                issues.append(f"Forbidden tracked file: {match}")

    for rel in tracked:
        try:
            path = _project_path(rel)
        except ValueError as exc:
            issues.append(str(exc))
            continue
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
        source = _project_path(source_rel)
        published = _project_path(published_rel)
        if source.exists() and published.exists() and source.read_bytes() != published.read_bytes():
            issues.append(f"Published artifact is stale: {published_rel} differs from {source_rel}")

    issues.extend(_broken_relative_markdown_links(tracked))
    issues.extend(_dependency_spec_issues())
    issues.extend(_config_json_issues())

    if issues:
        print("Preflight failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
