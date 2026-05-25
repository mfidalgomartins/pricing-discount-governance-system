from __future__ import annotations

import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
logger = logging.getLogger(__name__)

from src.processing.sql_warehouse import SqlLayerRunConfig, run_sql_warehouse_models
from src.utils.paths import OUTPUTS_DIR, SQL_DIR, SQL_MARTS_DIR, WAREHOUSE_DB_PATH, DATA_RAW_DIR


def main() -> None:
    run_sql_warehouse_models(
        SqlLayerRunConfig(
            raw_dir=DATA_RAW_DIR,
            sql_dir=SQL_DIR,
            db_path=WAREHOUSE_DB_PATH,
            marts_output_dir=SQL_MARTS_DIR,
            outputs_dir=OUTPUTS_DIR / "warehouse",
        )
    )
    logger.info("SQL warehouse models executed successfully.")


if __name__ == "__main__":
    main()
