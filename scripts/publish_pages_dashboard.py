"""Publish the executive dashboard to GitHub Pages docs/ folder.

This keeps a single deployable entrypoint at docs/index.html and ensures
required static assets are present for browser delivery.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_FILENAME = "pricing-discipline-command-center.html"
SOURCE_HTML = ROOT / "outputs" / "dashboard" / DASHBOARD_FILENAME
SOURCE_VENDOR = ROOT / "outputs" / "dashboard" / "vendor" / "chart.umd.min.js"
TARGET_DOCS = ROOT / "docs"
TARGET_HTML = TARGET_DOCS / "index.html"
TARGET_NAMED = TARGET_DOCS / DASHBOARD_FILENAME
TARGET_VENDOR_DIR = TARGET_DOCS / "vendor"
TARGET_VENDOR = TARGET_VENDOR_DIR / "chart.umd.min.js"
TARGET_NOJEKYLL = TARGET_DOCS / ".nojekyll"


def ensure_source_files() -> None:
    missing = [p for p in (SOURCE_HTML, SOURCE_VENDOR) if not p.exists()]
    if missing:
        missing_list = ", ".join(str(p) for p in missing)
        raise FileNotFoundError(f"Missing source file(s): {missing_list}")


def publish() -> None:
    ensure_source_files()

    TARGET_DOCS.mkdir(parents=True, exist_ok=True)
    TARGET_VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(SOURCE_HTML, TARGET_NAMED)
    shutil.copy2(SOURCE_HTML, TARGET_HTML)
    shutil.copy2(SOURCE_VENDOR, TARGET_VENDOR)
    TARGET_NOJEKYLL.touch(exist_ok=True)

    html_text = TARGET_HTML.read_text(encoding="utf-8")
    if 'src="vendor/chart.umd.min.js"' not in html_text:
        raise RuntimeError("Dashboard entrypoint is not using expected local vendor path.")

    print("GitHub Pages dashboard published:")
    print(f"- {TARGET_HTML}")
    print(f"- {TARGET_NAMED}")


if __name__ == "__main__":
    publish()
