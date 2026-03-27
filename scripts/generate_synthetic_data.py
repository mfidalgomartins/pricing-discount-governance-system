from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.load_raw import save_raw_tables
from src.ingestion.synthetic_data import SyntheticDataConfig, generate_synthetic_business_data
from src.utils.paths import DATA_RAW_DIR, ensure_project_directories
from src.validation.data_quality import validate_raw_tables


def main() -> None:
    ensure_project_directories()
    config = SyntheticDataConfig()
    raw_tables = generate_synthetic_business_data(config)
    save_raw_tables(raw_tables, DATA_RAW_DIR)

    report, is_valid = validate_raw_tables(raw_tables)
    report_path = PROJECT_ROOT / "outputs" / "raw_validation_report.csv"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(report_path, index=False)

    if not is_valid:
        raise RuntimeError(f"Raw data validation failed: {report_path}")

    print("Synthetic raw data generated and validated.")


if __name__ == "__main__":
    main()
