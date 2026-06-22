from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
RELEASE_OUTPUTS_DIR = OUTPUTS_DIR / "release"
DOCS_DIR = PROJECT_ROOT / "docs"
DASHBOARD_DIR = OUTPUTS_DIR / "dashboard"
CONFIGS_DIR = PROJECT_ROOT / "config"
SQL_DIR = PROJECT_ROOT / "sql"
SQL_STAGING_DIR = SQL_DIR / "staging"
SQL_INTERMEDIATE_DIR = SQL_DIR / "intermediate"
SQL_MARTS_MODELS_DIR = SQL_DIR / "marts"
SQL_MARTS_DIR = DATA_PROCESSED_DIR / "sql_marts"
WAREHOUSE_DB_PATH = DATA_PROCESSED_DIR / "pricing_governance.duckdb"


def resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    resolved = candidate.resolve()

    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(f"Path escapes project root: {path}") from exc

    return resolved


def ensure_project_directories() -> None:
    for directory in [
        DATA_RAW_DIR,
        DATA_PROCESSED_DIR,
        OUTPUTS_DIR,
        RELEASE_OUTPUTS_DIR,
        DASHBOARD_DIR,
        DOCS_DIR,
        CONFIGS_DIR,
        SQL_DIR,
        SQL_STAGING_DIR,
        SQL_INTERMEDIATE_DIR,
        SQL_MARTS_MODELS_DIR,
        SQL_MARTS_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
