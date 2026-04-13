from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.dashboard_builder import build_executive_dashboard
from src.utils.paths import DASHBOARD_DIR, DATA_PROCESSED_DIR


def load_processed_tables() -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for path in DATA_PROCESSED_DIR.glob("*.csv"):
        tables[path.stem] = pd.read_csv(path)
    return tables


def main() -> None:
    tables = load_processed_tables()
    dashboard_path = build_executive_dashboard(
        processed_tables=tables,
        dashboard_dir=DASHBOARD_DIR,
    )
    print(f"Dashboard created: {dashboard_path}")


if __name__ == "__main__":
    main()
