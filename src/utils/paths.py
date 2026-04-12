from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
RELEASE_OUTPUTS_DIR = OUTPUTS_DIR / "release"
DASHBOARD_DIR = OUTPUTS_DIR / "dashboard"
DOCS_DIR = PROJECT_ROOT / "docs"
DOCS_REPORTS_DIR = DOCS_DIR / "reports"
CONFIGS_DIR = PROJECT_ROOT / "config"
SQL_DIR = PROJECT_ROOT / "sql"
SQL_STAGING_DIR = SQL_DIR / "staging"
SQL_INTERMEDIATE_DIR = SQL_DIR / "intermediate"
SQL_MARTS_MODELS_DIR = SQL_DIR / "marts"
SQL_MARTS_DIR = DATA_PROCESSED_DIR / "sql_marts"
WAREHOUSE_DB_PATH = DATA_PROCESSED_DIR / "pricing_governance.duckdb"


def ensure_project_directories() -> None:
    for directory in [
        DATA_RAW_DIR,
        DATA_PROCESSED_DIR,
        OUTPUTS_DIR,
        RELEASE_OUTPUTS_DIR,
        DASHBOARD_DIR,
        DOCS_DIR,
        DOCS_REPORTS_DIR,
        CONFIGS_DIR,
        SQL_DIR,
        SQL_STAGING_DIR,
        SQL_INTERMEDIATE_DIR,
        SQL_MARTS_MODELS_DIR,
        SQL_MARTS_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
