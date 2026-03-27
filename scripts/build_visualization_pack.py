from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.visualization_pack import create_visualization_pack
from src.utils.paths import DATA_PROCESSED_DIR, DOCS_DIR, OUTPUTS_DIR


def load_processed_tables() -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for path in DATA_PROCESSED_DIR.glob("*.csv"):
        tables[path.stem] = pd.read_csv(path)
    return tables


def main() -> None:
    tables = load_processed_tables()
    create_visualization_pack(
        processed_tables=tables,
        outputs_dir=OUTPUTS_DIR,
        docs_dir=DOCS_DIR,
    )
    print(f"Visualization pack created at: {OUTPUTS_DIR / 'visualizations'}")


if __name__ == "__main__":
    main()
