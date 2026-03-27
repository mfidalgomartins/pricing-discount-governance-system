from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SQL_MARTS_DIR = DATA_PROCESSED_DIR / "sql_marts"
WAREHOUSE_DB_PATH = DATA_PROCESSED_DIR / "pricing_governance.duckdb"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
DOCS_DIR = PROJECT_ROOT / "docs"
SQL_DIR = PROJECT_ROOT / "sql"
SQL_STAGING_DIR = SQL_DIR / "staging"
SQL_INTERMEDIATE_DIR = SQL_DIR / "intermediate"
SQL_MARTS_MODELS_DIR = SQL_DIR / "marts"


def ensure_project_directories() -> None:
    for directory in [
        DATA_RAW_DIR,
        DATA_PROCESSED_DIR,
        SQL_MARTS_DIR,
        OUTPUTS_DIR,
        DASHBOARD_DIR,
        NOTEBOOKS_DIR,
        DOCS_DIR,
        SQL_STAGING_DIR,
        SQL_INTERMEDIATE_DIR,
        SQL_MARTS_MODELS_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
