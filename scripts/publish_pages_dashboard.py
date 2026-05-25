"""Refresh the GitHub Pages entrypoint for the canonical dashboard."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_FILENAME = "pricing-discipline-command-center.html"
OUTPUTS_DASHBOARD_DIR = ROOT / "outputs" / "dashboard"
OUTPUTS_DASHBOARD = OUTPUTS_DASHBOARD_DIR / DASHBOARD_FILENAME
OUTPUTS_VENDOR = OUTPUTS_DASHBOARD_DIR / "vendor" / "chart.umd.min.js"
DOCS_DIR = ROOT / "docs"
DOCS_INDEX = DOCS_DIR / "index.html"
DOCS_DASHBOARD = DOCS_DIR / DASHBOARD_FILENAME
DOCS_VENDOR_DIR = DOCS_DIR / "vendor"
DOCS_VENDOR = DOCS_VENDOR_DIR / "chart.umd.min.js"
DOCS_NOJEKYLL = DOCS_DIR / ".nojekyll"

DOCS_INDEX_TEMPLATE = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Pricing Discipline Command Center</title>
  <meta name=\"description\" content=\"Synthetic pricing governance analytics project with reproducible pipeline and dashboard.\" />
  <link rel=\"canonical\" href=\"https://mfidalgomartins.github.io/pricing-discount-governance-system/\" />
  <meta property=\"og:title\" content=\"Pricing Discipline Command Center\" />
  <meta property=\"og:description\" content=\"Synthetic pricing governance analytics project with discount leakage, margin risk, and customer-level intervention views.\" />
  <meta property=\"og:type\" content=\"website\" />
  <meta property=\"og:url\" content=\"https://mfidalgomartins.github.io/pricing-discount-governance-system/\" />
  <meta http-equiv=\"refresh\" content=\"0; url=./{DASHBOARD_FILENAME}\" />
</head>
<body>
  <p>Redirecting to <a href=\"./{DASHBOARD_FILENAME}\">{DASHBOARD_FILENAME}</a>...</p>
</body>
</html>
"""


def publish() -> None:
    missing = [p for p in (OUTPUTS_DASHBOARD, OUTPUTS_VENDOR) if not p.exists()]
    if missing:
        missing_list = ", ".join(str(p) for p in missing)
        raise FileNotFoundError(f"Missing required dashboard asset(s): {missing_list}")

    html_text = OUTPUTS_DASHBOARD.read_text(encoding="utf-8")
    if 'src="vendor/chart.umd.min.js"' not in html_text:
        raise RuntimeError("Dashboard source does not reference expected local vendor path.")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(OUTPUTS_DASHBOARD, DOCS_DASHBOARD)
    shutil.copy2(OUTPUTS_VENDOR, DOCS_VENDOR)
    DOCS_INDEX.write_text(DOCS_INDEX_TEMPLATE, encoding="utf-8")
    DOCS_NOJEKYLL.write_text("", encoding="utf-8")

    logger.info("GitHub Pages dashboard published.")
    logger.info("  source: %s", OUTPUTS_DASHBOARD)
    logger.info("  index:  %s", DOCS_INDEX)
    logger.info("  copy:   %s", DOCS_DASHBOARD)


if __name__ == "__main__":
    publish()
