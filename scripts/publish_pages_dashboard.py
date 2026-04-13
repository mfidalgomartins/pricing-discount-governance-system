"""Publish dashboard assets for GitHub Pages using docs/ as the source."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_FILENAME = "pricing-discipline-command-center.html"
DASHBOARD_PATH = ROOT / "outputs" / "dashboard" / DASHBOARD_FILENAME
VENDOR_PATH = ROOT / "outputs" / "dashboard" / "vendor" / "chart.umd.min.js"

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
  <meta http-equiv=\"refresh\" content=\"0; url=./{DASHBOARD_FILENAME}\" />
</head>
<body>
  <p>Redirecting to <a href=\"./{DASHBOARD_FILENAME}\">{DASHBOARD_FILENAME}</a>...</p>
</body>
</html>
"""


def publish() -> None:
    missing = [p for p in (DASHBOARD_PATH, VENDOR_PATH) if not p.exists()]
    if missing:
        missing_list = ", ".join(str(p) for p in missing)
        raise FileNotFoundError(f"Missing required dashboard asset(s): {missing_list}")

    html_text = DASHBOARD_PATH.read_text(encoding="utf-8")
    if 'src="vendor/chart.umd.min.js"' not in html_text:
        raise RuntimeError("Dashboard source does not reference expected local vendor path.")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(DASHBOARD_PATH, DOCS_DASHBOARD)
    shutil.copy2(VENDOR_PATH, DOCS_VENDOR)
    DOCS_INDEX.write_text(DOCS_INDEX_TEMPLATE, encoding="utf-8")
    DOCS_NOJEKYLL.write_text("", encoding="utf-8")

    print("GitHub Pages dashboard published:")
    print(f"- {DOCS_INDEX}")
    print(f"- {DOCS_DASHBOARD}")


if __name__ == "__main__":
    publish()
